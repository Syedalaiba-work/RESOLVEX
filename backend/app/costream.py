"""Part II §5.5 4-way co-stream orchestration — STRUCTURAL SCAFFOLD ONLY (team implements the business logic).

Answers 501 NOT_IMPLEMENTED until implemented; acceptance tests: tests/test_day2_contracts.py.
Building blocks: core.read_json / validation_error / ApiError / sign_day2, db.tx, Phase II tables.
"""
from fastapi import APIRouter, Request

from app.core import ApiError

router = APIRouter()


def _todo(name: str):
    raise ApiError(501, "NOT_IMPLEMENTED", f"{name} is not implemented yet.", {})


@router.post("/audit/v1/costream/session")
async def costream_session(request: Request):
    """§5.5 and hidden scenario 1. 201 new, 200 identical replay.
    TODO: rules in the exact order of §5.5 (schema, existence, host in participants, capacity > 4 -> 409,
          layout capacity -> 400 UNSUPPORTED_LAYOUT, then the three handoff cases).
    TODO: chat_room_id = "chat-" + session_id and composite URL stay stable across handoff.
    TODO: signature = sign_day2(session_id, {active_host, handoff_occurred, layout, participant_count,
          session_id, status}).
    """
    _todo("POST /audit/v1/costream/session")
