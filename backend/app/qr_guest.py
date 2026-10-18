"""Part II §5.6 dynamic QR deep-linking (resolve, exports, /q redirect) and §5.7 guest cart merge.

"""
import hashlib
import io
from datetime import datetime, timezone

import segno
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, Response

from app import pdf
from app.core import ApiError, is_id, read_json, sign_day2, validation_error
from app.db import J, tx

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


def _validate_merge(body: dict) -> dict:
    bad = []
    token = body.get("guest_token")
    if not (isinstance(token, str) and token.startswith("guest_") and len(token) > len("guest_")):
        bad.append("guest_token")
    if not is_id(body.get("registered_user_id")):
        bad.append("registered_user_id")
    cart = body.get("guest_cart")
    if not (isinstance(cart, list) and 1 <= len(cart) <= 10 and all(
            isinstance(i, dict) and is_id(i.get("variant_id")) and isinstance(i.get("quantity"), int)
            and not isinstance(i.get("quantity"), bool) and i["quantity"] >= 1 for i in cart)):
        bad.append("guest_cart")
    block = body.get("test_write_block", True)
    if not isinstance(block, bool):
        bad.append("test_write_block")
    if bad:
        raise validation_error(bad)
    return {"guest_token": token, "registered_user_id": body["registered_user_id"],
            "guest_cart": [{"variant_id": i["variant_id"], "quantity": i["quantity"]} for i in cart],
            "test_write_block": block}


@router.post("/audit/v1/guest/cart-merge")
async def guest_cart_merge(request: Request):
    req = _validate_merge(await read_json(request))
    token, user = req["guest_token"], req["registered_user_id"]
    with tx() as conn:
        # Serialise per token: a replay racing the first call (edge case 4) waits and then sees "merged".
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("guest_token:" + token,))
        tok = conn.execute("SELECT * FROM guest_tokens WHERE guest_token = %s", (token,)).fetchone()
        if tok and tok["status"] != "active":
            if tok["status"] == "merged" and tok["merged_request"] == req:
                return tok["merged_response"]  # identical replay: stored result, nothing re-added
            raise ApiError(409, "GUEST_TOKEN_ALREADY_MERGED", f"Guest token {token} was already merged.",
                           {"guest_token": token})
        if not conn.execute("SELECT 1 FROM players WHERE player_id = %s", (user,)).fetchone():
            raise ApiError(404, "PLAYER_NOT_FOUND", f"Player {user} does not exist.", {"user_id": user})
        ids = [i["variant_id"] for i in req["guest_cart"]]
        variants = {r["variant_id"]: r for r in conn.execute(
            "SELECT variant_id, price_minor, currency, stock FROM variants WHERE variant_id = ANY(%s)", (ids,)).fetchall()}
        missing = [v for v in ids if v not in variants]
        if missing:
            raise ApiError(404, "VARIANT_NOT_FOUND", f"Variant {missing[0]} does not exist.", {"variant_id": missing[0]})
        row = conn.execute("SELECT items FROM carts WHERE user_id = %s FOR UPDATE", (user,)).fetchone()
        merged = {i["variant_id"]: i["quantity"] for i in (row["items"] if row else [])}
        for item in req["guest_cart"]:
            merged[item["variant_id"]] = merged.get(item["variant_id"], 0) + item["quantity"]
        stock = {r["variant_id"]: r for r in conn.execute(
            "SELECT variant_id, price_minor, stock FROM variants WHERE variant_id = ANY(%s)", (list(merged),)).fetchall()}
        for variant_id, qty in merged.items():
            if qty > stock[variant_id]["stock"]:  # checked, never reserved: stock is only taken at checkout
                raise ApiError(409, "OUT_OF_STOCK", f"Variant {variant_id} has only {stock[variant_id]['stock']} left.",
                               {"variant_id": variant_id})
        items = [{"variant_id": v, "quantity": q, "unit_price_minor": stock[v]["price_minor"]} for v, q in merged.items()]
        conn.execute("INSERT INTO carts (user_id, items) VALUES (%s, %s) ON CONFLICT (user_id) DO UPDATE SET items = EXCLUDED.items",
                     (user, J([{"variant_id": i["variant_id"], "quantity": i["quantity"]} for i in items])))
        total_items = sum(i["quantity"] for i in items)
        # test_write_block: the same guard main.guards applies to every guest write (FR-4.3).
        rejection = 403 if req["test_write_block"] and token.startswith("guest_anon_tok_") else None
        response = {
            "guest_token": token,
            "write_block_verified": rejection == 403,
            "write_rejection_code": rejection,
            "cart_merged": True,
            "active_cart": {"user_id": user, "currency": "PKR", "total_items": total_items,
                            "subtotal_minor": sum(i["quantity"] * i["unit_price_minor"] for i in items), "items": items},
            "signature": sign_day2(token, {"cart_merged": True, "guest_token": token, "registered_user_id": user,
                                           "total_items": total_items, "write_rejection_code": rejection}),
        }
        conn.execute(
            "INSERT INTO guest_tokens (guest_token, status, user_id, merged_request, merged_response) "
            "VALUES (%s, 'merged', %s, %s, %s) ON CONFLICT (guest_token) DO UPDATE SET status = 'merged', "
            "user_id = EXCLUDED.user_id, merged_request = EXCLUDED.merged_request, merged_response = EXCLUDED.merged_response",
            (token, user, J(req), J(response)))
    return response
