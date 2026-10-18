"""Part II §5.6 dynamic QR deep-linking (resolve, exports, /q redirect) and §5.7 guest cart merge.

The cart-merge handler below is still a scaffold (501 until implemented).
"""
import hashlib
import io
from datetime import datetime, timezone

import segno
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, Response

from app import pdf
from app.core import ApiError, sign_day2
from app.db import tx

router = APIRouter()

BASE_URL = "http://localhost:8080"
PREFIXES = (("cs-session-", "costream"), ("match-", "match"), ("player-", "player"), ("club-", "club"))
EXPORTS = {"svg": "image/svg+xml", "png": "image/png", "pdf": "application/pdf"}


def _todo(name: str):
    raise ApiError(501, "NOT_IMPLEMENTED", f"{name} is not implemented yet.", {})


def _not_found(entity_id: str):
    return ApiError(404, "QR_NOT_FOUND", f"No dynamic QR mapping for {entity_id}.", {"entity_id": entity_id})


def _entity_type(entity_id: str) -> str | None:
    return next((t for prefix, t in PREFIXES if entity_id.startswith(prefix)), None)


def _entity_exists(conn, entity_id: str, entity_type: str) -> bool:
    table, col = {"match": ("matches", "match_id"), "player": ("players", "player_id"),
                  "club": ("clubs", "club_id"), "costream": ("costream_sessions", "session_id")}[entity_type]
    return conn.execute(f"SELECT 1 FROM {table} WHERE {col} = %s", (entity_id,)).fetchone() is not None


def _mapping(conn, entity_id: str, create: bool = True):
    """Seeded mappings, or a system-generated one for any existing match/club/player/co-stream (FR-4.1)."""
    row = conn.execute("SELECT * FROM qr_codes WHERE entity_id = %s", (entity_id,)).fetchone()
    if row or not create:
        return row
    entity_type = _entity_type(entity_id)
    if not entity_type or not _entity_exists(conn, entity_id, entity_type):
        return None
    short_code = "e-" + hashlib.sha256(entity_id.encode("utf-8")).hexdigest()[:10]  # stable: posters never change
    conn.execute("INSERT INTO qr_codes (entity_id, entity_type, short_code) VALUES (%s, %s, %s) "
                 "ON CONFLICT (entity_id) DO NOTHING", (entity_id, entity_type, short_code))
    return conn.execute("SELECT * FROM qr_codes WHERE entity_id = %s", (entity_id,)).fetchone()


def _match_status(conn, match_id: str) -> str:
    """Same answer as scoring.score_view()["status"]: lifecycle events cannot be compensated (Part I 5.9),
    so the presence of match_start / match_end decides it. One indexed query instead of replaying the log."""
    row = conn.execute("SELECT bool_or(type = 'match_end') AS ended, bool_or(type = 'match_start') AS started "
                       "FROM events WHERE match_id = %s", (match_id,)).fetchone()
    return "completed" if row["ended"] else ("in_progress" if row["started"] else "upcoming")


def _state(conn, entity_id: str, entity_type: str) -> tuple[str, str]:
    """(entity_status, target_route) from the entity's state at this moment (edge case 2).
    Uses the caller's connection only: a second pool connection per request deadlocks under load."""
    if entity_type == "match":
        status = _match_status(conn, entity_id)
        route = {"upcoming": "preview", "in_progress": "live", "completed": "vod"}.get(status)
        if route:
            return status, f"/web/matches/{entity_id}/{route}"
        return status, f"/web/matches/{entity_id}/notice?state={status}"  # postponed / cancelled / abandoned
    if entity_type == "costream":
        row = conn.execute("SELECT response FROM costream_sessions WHERE session_id = %s", (entity_id,)).fetchone()
        return (row["response"]["status"] if row else "active"), f"/web/costream/{entity_id}"
    return "active", f"/web/{entity_type}s/{entity_id}"


def _record_scan(conn, entity_id: str, user_agent: str) -> int:
    # NFR-9: only a device family and a minute bucket; no IP, no User-Agent string, no fingerprint.
    family = "mobile" if any(t in user_agent for t in ("Mobile", "Android", "iPhone", "iPad")) else "desktop"
    bucket = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    conn.execute("INSERT INTO qr_scans (entity_id, device_family, bucket) VALUES (%s, %s, %s)",
                 (entity_id, family, bucket))
    return conn.execute("UPDATE qr_codes SET scan_count = scan_count + 1 WHERE entity_id = %s RETURNING scan_count",
                        (entity_id,)).fetchone()["scan_count"]


@router.get("/audit/v1/qr/{entity_id}")
def qr_resolve(entity_id: str, request: Request, inspect: bool = False):
    with tx() as conn:  # one connection per request
        row = _mapping(conn, entity_id)
        if not row:
            raise _not_found(entity_id)
        status, route = _state(conn, entity_id, row["entity_type"])
        scans = row["scan_count"] if inspect else _record_scan(conn, entity_id, request.headers.get("user-agent", ""))
    short_url = f"{BASE_URL}/q/{row['short_code']}"
    return {
        "entity_id": entity_id,
        "entity_type": row["entity_type"],
        "entity_status": status,
        "short_url": short_url,
        "target_route": route,
        "deep_link_uri": f"nascon://entity/{entity_id}",
        "scan_count": scans,
        "export_formats": {f: f"{BASE_URL}/audit/v1/qr/{entity_id}/export.{f}" for f in EXPORTS},
        "signature": sign_day2(entity_id, {"entity_id": entity_id, "short_url": short_url, "target_route": route}),
    }


@router.get("/audit/v1/qr/{entity_id}/export.{fmt}")
def qr_export(entity_id: str, fmt: str):
    if fmt not in EXPORTS:
        raise ApiError(404, "QR_NOT_FOUND", f"Unknown export format {fmt}.", {"format": fmt})
    with tx() as conn:
        row = _mapping(conn, entity_id)
    if not row:
        raise _not_found(entity_id)
    short_url = f"{BASE_URL}/q/{row['short_code']}"
    qr = segno.make(short_url, error="m")
    if fmt == "pdf":
        body = pdf.qr_poster_pdf([list(r) for r in qr.matrix], f"Scan to watch: {entity_id}", [short_url])
    else:
        buf = io.BytesIO()
        qr.save(buf, kind=fmt, scale=8, border=4)
        body = buf.getvalue()
    return Response(content=body, media_type=EXPORTS[fmt])


@router.get("/q/{short_code}")
def short_link(short_code: str, request: Request):
    with tx() as conn:
        row = conn.execute("SELECT * FROM qr_codes WHERE short_code = %s", (short_code,)).fetchone()
        if not row:
            raise _not_found(short_code)
        _, route = _state(conn, row["entity_id"], row["entity_type"])
        _record_scan(conn, row["entity_id"], request.headers.get("user-agent", ""))
    return RedirectResponse(url=route, status_code=302)


@router.post("/audit/v1/guest/cart-merge")
async def guest_cart_merge(request: Request):
    """§5.7 and hidden scenario 4.
    TODO: schema (guest_ prefix, 1-10 items, quantity >= 1) -> 404 user / variant -> 409 OUT_OF_STOCK.
    TODO: test_write_block: prove the guard rejects a guest write with 403 (see main.guards) and report it.
    TODO: merge atomically into carts (sum same variant, cap by stock, no stock reservation).
    TODO: identical replay -> 200 same cart; same token, other user/payload -> 409 GUEST_TOKEN_ALREADY_MERGED.
    TODO: signature = sign_day2(guest_token, {cart_merged, guest_token, registered_user_id, total_items,
          write_rejection_code}).
    """
    _todo("POST /audit/v1/guest/cart-merge")
