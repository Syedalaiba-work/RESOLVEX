"""HTTP layer: maps the /audit/v1/* contract (spec section 5) onto the domain modules."""
import logging
import threading
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import fixtures, seed, sports
from app.core import MAX_BODY_BYTES, ApiError, error_response, read_json
from app.db import create_schema, tx, wait_for_db

log = logging.getLogger("nascon")


@asynccontextmanager
async def lifespan(app: FastAPI):
    wait_for_db()
    create_schema()
    with tx() as conn:
        seeded = seed.is_seeded(conn)
    if not seeded:
        seed.reset()
    yield


app = FastAPI(title="NaSCon League Platform", lifespan=lifespan)


# --- errors: every non-2xx uses {"error": {code, message, details}} --------------------------------

@app.exception_handler(ApiError)
async def api_error_handler(_: Request, exc: ApiError):
    return error_response(exc.status, exc.code, exc.message, exc.details)


@app.exception_handler(RequestValidationError)
async def request_validation_handler(_: Request, exc: RequestValidationError):
    fields = []
    for err in exc.errors():
        loc = [str(p) for p in err.get("loc", []) if p not in ("body", "query", "path")]
        if loc and loc[0] not in fields:
            fields.append(loc[0])
    return error_response(400, "VALIDATION_ERROR", "Request validation failed.", {"fields": fields})


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(_: Request, exc: StarletteHTTPException):
    code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(exc.status_code, "HTTP_ERROR")
    return error_response(exc.status_code, code, str(exc.detail))


@app.exception_handler(Exception)
async def unexpected_error_handler(_: Request, exc: Exception):
    log.exception("Unhandled error", exc_info=exc)
    return error_response(500, "INTERNAL_ERROR", "Unexpected server error.")


# --- middleware: body size limit + /api/v1 rate limit ----------------------------------------------

RATE_LIMIT = 100
RATE_WINDOW_S = 10.0
_hits: dict[str, deque] = defaultdict(deque)
_hits_lock = threading.Lock()


def _rate_limited(client_ip: str) -> float | None:
    """Rolling-window limiter. Returns seconds to wait if the request must be refused."""
    now = time.monotonic()
    with _hits_lock:
        q = _hits[client_ip]
        while q and now - q[0] >= RATE_WINDOW_S:
            q.popleft()
        if len(q) >= RATE_LIMIT:
            return max(0.0, RATE_WINDOW_S - (now - q[0]))
        q.append(now)
        return None


@app.middleware("http")
async def guards(request: Request, call_next):
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > MAX_BODY_BYTES:
        return error_response(413, "PAYLOAD_TOO_LARGE", "Request body exceeds 1 MB.")
    if request.url.path.startswith("/api/v1/"):
        client_ip = request.client.host if request.client else "unknown"
        wait_s = _rate_limited(client_ip)
        if wait_s is not None:
            return error_response(
                429, "RATE_LIMITED", "Too many requests. Please slow down.", {},
                headers={"Retry-After": str(max(1, int(wait_s + 0.999)))},
            )
    return await call_next(request)


# --- 5.4 health / 5.5 reset / 5.6 sports -----------------------------------------------------------

@app.get("/health")
def health():
    try:
        with tx() as conn:
            ready = seed.is_seeded(conn)
    except Exception:
        ready = False
    if not ready:
        return error_response(503, "NOT_READY", "Database unreachable or baseline data not seeded.")
    return {"status": "ok"}


@app.post("/audit/v1/reset")
async def reset(request: Request):
    body = await read_json(request, required=False)
    seed_value, stock = seed.parse_reset(body)
    return seed.reset(seed_value, stock)


@app.post("/audit/v1/sports", status_code=201)
async def create_sport(request: Request):
    return sports.create_sport(await read_json(request))


@app.post("/audit/v1/fixtures")
async def generate_fixtures(request: Request):
    return fixtures.generate(await read_json(request))


@app.get("/api/v1/ping")
def ping():
    return {"pong": True}


@app.get("/")
def root():
    return JSONResponse({"service": "nascon-league-platform", "health": "/health"})
