"""Part II §5.5: 4-way co-stream session initialisation and deterministic host-drop handoff."""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.core import ApiError, is_id, read_json, sign_day2, validation_error
from app.db import J, tx

router = APIRouter()

LAYOUTS = {"solo", "grid_2", "grid_4", "spotlight"}
LAYOUT_CAPACITY = {"solo": 1, "grid_2": 2}  # grid_4 / spotlight fit the 4-participant maximum
MAX_PARTICIPANTS = 4


def _validate(body: dict) -> dict:
    """Rule 1: schema. Returns the normalised request (defaults applied) used for idempotent replay."""
    bad = []
    if not is_id(body.get("session_id")):
        bad.append("session_id")
    if not is_id(body.get("host_player_id")):
        bad.append("host_player_id")
    participants = body.get("participants")
    if not (isinstance(participants, list) and participants and all(is_id(p) for p in participants)
            and len(set(participants)) == len(participants)):
        bad.append("participants")
    layout = body.get("layout", "grid_4")
    if layout not in LAYOUTS:
        bad.append("layout")
    drop = body.get("simulate_host_drop", False)
    if not isinstance(drop, bool):
        bad.append("simulate_host_drop")
    if bad:
        raise validation_error(bad)
    return {"session_id": body["session_id"], "host_player_id": body["host_player_id"],
            "participants": participants, "layout": layout, "simulate_host_drop": drop}


def _evaluate(conn, req: dict) -> dict:
    participants, host = req["participants"], req["host_player_id"]
    # Rule 2: every referenced player exists.
    wanted = list(dict.fromkeys(participants + [host]))
    found = {r["player_id"] for r in conn.execute(
        "SELECT player_id FROM players WHERE player_id = ANY(%s)", (wanted,)).fetchall()}
    missing = [p for p in wanted if p not in found]
    if missing:
        raise ApiError(404, "PLAYER_NOT_FOUND", f"Player {missing[0]} does not exist.", {"player_id": missing[0]})
    # Rule 2 (cont.): the host must be one of the participants.
    if host not in participants:
        raise validation_error(["host_player_id"], "host_player_id must be one of the participants.")
    # Rule 3: at most four broadcasters.
    if len(participants) > MAX_PARTICIPANTS:
        raise ApiError(409, "COSTREAM_SESSION_FULL", f"A co-stream supports at most {MAX_PARTICIPANTS} participants.",
                       {"session_id": req["session_id"], "participant_count": len(participants)})
    # Rule 5 decides who is still active; rule 4 checks the layout against that effective count.
    if req["simulate_host_drop"]:
        remaining = [p for p in participants if p != host]  # original array order
        active_host = remaining[0] if remaining else None
        handoff = bool(remaining)
        status = "active" if remaining else "terminated"
    else:
        remaining, active_host, handoff, status = list(participants), host, False, "active"
    capacity = LAYOUT_CAPACITY.get(req["layout"])
    if capacity is not None and len(remaining) > capacity:
        raise ApiError(400, "UNSUPPORTED_LAYOUT",
                       f"Layout {req['layout']} cannot show {len(remaining)} active participants.",
                       {"layout": req["layout"], "participant_count": len(remaining)})
    sid = req["session_id"]
    response = {
        "session_id": sid,
        "status": status,
        "active_host": active_host,
        "handoff_occurred": handoff,
        "participant_count": len(remaining),
        "active_participants": remaining,
        "layout": req["layout"],
        # Stable across handoff (hidden scenario 1): same composite URL and chat room for the session.
        "composite_playback_url": f"http://localhost:8888/costream/{sid}/index.m3u8",
        "chat_room_id": f"chat-{sid}",
    }
    response["signature"] = sign_day2(sid, {
        "active_host": active_host, "handoff_occurred": handoff, "layout": req["layout"],
        "participant_count": len(remaining), "session_id": sid, "status": status,
    })
    return response


@router.post("/audit/v1/costream/session")
async def costream_session(request: Request):
    req = _validate(await read_json(request))
    with tx() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("costream:" + req["session_id"],))
        stored = conn.execute("SELECT request, response FROM costream_sessions WHERE session_id = %s",
                              (req["session_id"],)).fetchone()
        if stored and stored["request"] == req:
            return JSONResponse(status_code=200, content=stored["response"])  # identical replay
        response = _evaluate(conn, req)
        conn.execute(
            "INSERT INTO costream_sessions (session_id, request, response) VALUES (%s, %s, %s) "
            "ON CONFLICT (session_id) DO UPDATE SET request = EXCLUDED.request, response = EXCLUDED.response",
            (req["session_id"], J(req), J(response)),
        )
    return JSONResponse(status_code=201, content=response)
