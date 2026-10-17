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

from starlette.concurrency import run_in_threadpool

from app import api_v1, demo, fixtures, rbac, roster, scoring, seed, sports, standings, store, sync
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
        full_reset(seed.DEFAULT_SEED, None)
    yield


app = FastAPI(title="NaSCon League Platform", lifespan=lifespan)
app.include_router(api_v1.router)


def full_reset(seed_value, stock):
    result = seed.reset(seed_value, stock)
    demo.seed_demo()  # mobile desk-check data, rebuilt through the normal domain services
    return result


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
    return await run_in_threadpool(full_reset, seed_value, stock)


@app.post("/audit/v1/sports", status_code=201)
async def create_sport(request: Request):
    return await run_in_threadpool(sports.create_sport, await read_json(request))


@app.post("/audit/v1/fixtures")
async def generate_fixtures(request: Request):
    return await run_in_threadpool(fixtures.generate, await read_json(request))


@app.post("/audit/v1/leagues", status_code=201)
async def register_league(request: Request):
    return await run_in_threadpool(scoring.register_league, await read_json(request))


@app.post("/audit/v1/events")
async def append_event(request: Request):
    body = await read_json(request)
    code, response = await run_in_threadpool(scoring.append_event, body)
    return JSONResponse(status_code=code, content=response)


@app.get("/audit/v1/score/{match_id}")
def get_score(match_id: str):
    return scoring.score_view(match_id)


@app.get("/audit/v1/standings/{league_id}")
def get_standings(league_id: str):
    return standings.standings(league_id)


@app.post("/audit/v1/checkout")
async def checkout(request: Request):
    body = await read_json(request)
    code, response = await run_in_threadpool(store.checkout, body)
    return JSONResponse(status_code=code, content=response)


@app.get("/audit/v1/inventory/{variant_id}")
def get_inventory(variant_id: str):
    return store.inventory(variant_id)


@app.post("/audit/v1/roster/setup", status_code=201)
async def roster_setup(request: Request):
    return await run_in_threadpool(roster.setup, await read_json(request))


@app.post("/audit/v1/roster/transfer")
async def roster_transfer(request: Request):
    body = await read_json(request)
    code, response = await run_in_threadpool(roster.transfer, body)
    return JSONResponse(status_code=code, content=response)


@app.get("/audit/v1/roster/history/{player_id}")
def roster_history(player_id: str, as_of: str | None = None):
    return roster.history(player_id, as_of)


@app.post("/audit/v1/offline-sync")
async def offline_sync(request: Request):
    return await run_in_threadpool(sync.sync, await read_json(request))


@app.post("/audit/v1/rbac-matrix")
def rbac_matrix():
    return rbac.rbac_matrix()


# Probe routes: authorize only, no mutation, body ignored (spec 5.13).
@app.post("/audit/v1/rbac/tenants")
def probe_tenants(request: Request):
    return rbac.probe(request, "tenants.create")


@app.post("/audit/v1/rbac/leagues/{league_id}/fixtures")
def probe_league_fixtures(request: Request, league_id: str):
    return rbac.probe(request, "league.fixtures.write", "league", league_id)


@app.post("/audit/v1/rbac/clubs/{club_id}/roster")
def probe_club_roster(request: Request, club_id: str):
    return rbac.probe(request, "club.roster.write", "club", club_id)


@app.post("/audit/v1/rbac/clubs/{club_id}/products")
def probe_club_products(request: Request, club_id: str):
    return rbac.probe(request, "club.products.write", "club", club_id)


@app.patch("/audit/v1/rbac/players/{player_id}")
def probe_player(request: Request, player_id: str):
    return rbac.probe(request, "player.update", "player", player_id)


@app.get("/audit/v1/rbac/clubs/{club_id}")
def probe_club_read(request: Request, club_id: str):
    return rbac.probe(request, "club.read", "club", club_id)


@app.get("/audit/v1/rbac/platform/config")
def probe_platform_config(request: Request):
    return rbac.probe(request, "platform.config.read")


@app.post("/api/v1/auth/login")
async def login(request: Request):
    body = await read_json(request)
    return await run_in_threadpool(rbac.login, body.get("email"), body.get("password"))


@app.get("/api/v1/ping")
def ping():
    return {"pong": True}


@app.get("/")
def root():
    return JSONResponse({"service": "nascon-league-platform", "health": "/health"})
