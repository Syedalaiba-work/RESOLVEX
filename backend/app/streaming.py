"""Part II §5.4: creator stream-key lifecycle (generate / rotate / revoke), signed with DAY2_SALT."""
import secrets

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.core import ApiError, is_id, read_json, sign_day2, validation_error
from app.db import tx

router = APIRouter()

ACTIONS = {"generate", "rotate", "revoke"}


def _validate(body: dict) -> dict:
    bad = []
    action = body.get("action")
    if action not in ACTIONS:
        bad.append("action")
    if not is_id(body.get("player_id")):
        bad.append("player_id")
    label = body.get("label", "default")
    if not (isinstance(label, str) and 1 <= len(label) <= 64):
        bad.append("label")
    override = body.get("stream_key_override")
    if override is not None and not is_id(override):
        bad.append("stream_key_override")
    if bad:
        raise validation_error(bad)
    return {"action": action, "player_id": body["player_id"], "label": label, "override": override}


def _response(action: str, player_id: str, label: str, key: str, status: str) -> dict:
    active = status == "active"
    return {
        "player_id": player_id,
        "label": label,
        "stream_key": key,
        "status": status,
        "ingest_endpoints": {"rtmp": f"rtmp://localhost:1935/live/{key}",
                             "webrtc": f"http://localhost:8889/live/{key}/whip"} if active else None,
        "playback_url": f"http://localhost:8888/live/{key}/index.m3u8" if active else None,
        # Table 5.3: entity_id = stream_key, sig_payload = {action, player_id, status, stream_key}.
        "signature": sign_day2(key, {"action": action, "player_id": player_id, "status": status, "stream_key": key}),
    }


@router.post("/audit/v1/stream/key")
async def stream_key(request: Request):
    req = _validate(await read_json(request))
    action, player_id = req["action"], req["player_id"]
    with tx() as conn:
        if not conn.execute("SELECT 1 FROM players WHERE player_id = %s", (player_id,)).fetchone():
            raise ApiError(404, "PLAYER_NOT_FOUND", f"Player {player_id} does not exist.", {"player_id": player_id})
        # Serialise lifecycle changes per player so concurrent rotates never leave two active keys.
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("stream_key:" + player_id,))
        current = conn.execute("SELECT stream_key, label FROM stream_keys WHERE player_id = %s AND status = 'active'",
                               (player_id,)).fetchall()
        if action == "revoke":
            if not current:
                raise ApiError(404, "STREAM_NOT_FOUND", f"Player {player_id} has no active stream key.",
                               {"player_id": player_id})
            conn.execute("UPDATE stream_keys SET status = 'revoked', revoked_at = now() "
                         "WHERE player_id = %s AND status = 'active'", (player_id,))
            key, label = current[0]["stream_key"], current[0]["label"]
            return _response(action, player_id, label, key, "revoked")

        # generate / rotate: the previous key stops working immediately.
        conn.execute("UPDATE stream_keys SET status = 'revoked', revoked_at = now() "
                     "WHERE player_id = %s AND status = 'active'", (player_id,))
        key = req["override"] or "sk_live_" + secrets.token_hex(8)
        conn.execute(
            "INSERT INTO stream_keys (stream_key, player_id, label, status) VALUES (%s, %s, %s, 'active') "
            "ON CONFLICT (stream_key) DO UPDATE SET player_id = EXCLUDED.player_id, label = EXCLUDED.label, "
            "status = 'active', revoked_at = NULL",
            (key, player_id, req["label"]),
        )
    body = _response(action, player_id, req["label"], key, "active")
    return JSONResponse(status_code=201 if action == "generate" else 200, content=body)
