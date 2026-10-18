"""Shared building blocks: contract error format, strict JSON validation, HMAC signing (spec 5.2, 5.3)."""
import hashlib
import hmac
import json
import os
import re
from datetime import date, datetime, timezone

from fastapi import Request
from fastapi.responses import JSONResponse

MAX_BODY_BYTES = 1024 * 1024
ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")


class ApiError(Exception):
    """Raised anywhere in the domain; rendered as {"error": {code, message, details}}."""

    def __init__(self, status: int, code: str, message: str = "", details: dict | None = None):
        super().__init__(message or code)
        self.status = status
        self.code = code
        self.message = message or code.replace("_", " ").capitalize()
        self.details = details or {}


def error_response(status: int, code: str, message: str, details: dict | None = None, headers=None):
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "details": details or {}}},
        headers=headers,
    )


def validation_error(fields: list[str], message: str = "Request validation failed."):
    return ApiError(400, "VALIDATION_ERROR", message, {"fields": fields})


async def read_json(request: Request, required: bool = True):
    """Reads the body as a JSON object. Too large -> 413, malformed -> 400."""
    body = await request.body()
    if len(body) > MAX_BODY_BYTES:
        raise ApiError(413, "PAYLOAD_TOO_LARGE", "Request body exceeds 1 MB.")
    if not body.strip():
        if required:
            raise validation_error([], "Request body is required.")
        return {}
    try:
        data = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        raise validation_error([], "Malformed JSON.")
    if not isinstance(data, dict):
        raise validation_error([], "Body must be a JSON object.")
    return data


# --- strict type checks (JSON true/false are NOT integers here) --------------------------------

def is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def is_str(value) -> bool:
    return isinstance(value, str)


def is_id(value) -> bool:
    return isinstance(value, str) and bool(ID_RE.match(value))


def is_date(value) -> bool:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return False
    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        return False


def is_timestamp(value) -> bool:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value):
        return False
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
        return True
    except ValueError:
        return False


class Checker:
    """Collects the names of invalid fields, then raises one VALIDATION_ERROR listing all of them."""

    def __init__(self):
        self.fields: list[str] = []

    def check(self, ok: bool, field: str) -> bool:
        if not ok and field not in self.fields:
            self.fields.append(field)
        return ok

    def raise_if_any(self):
        if self.fields:
            raise validation_error(self.fields)


# --- signatures (spec 5.3, Appendix A) ----------------------------------------------------------

def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def salt() -> str:
    # Read at call time from the environment; never hard-coded or committed.
    return os.environ.get("DAY1_SALT", "")


def sign(id_: str, payload_obj, key: str | None = None) -> str:
    message = (id_ + "|" + canonical(payload_obj)).encode("utf-8")
    return hmac.new((salt() if key is None else key).encode("utf-8"), message, hashlib.sha256).hexdigest()


def day2_salt() -> str:
    # Part II §1.2/§7.3: read from the environment at call time; never hard-coded or committed.
    return os.environ.get("DAY2_SALT", "")


def sign_day2(entity_id: str, sig_payload: dict) -> str:
    """Part II §5.3: same recipe as Day 1 (entity_id + "|" + canonical), keyed with DAY2_SALT."""
    return sign(entity_id, sig_payload, key=day2_salt())


def lots_key(seed: int, league_id: str, team_id: str) -> str:
    return hashlib.sha256(f"{seed}|{league_id}|{team_id}".encode("utf-8")).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def today() -> str:
    return datetime.now(timezone.utc).date().isoformat()
