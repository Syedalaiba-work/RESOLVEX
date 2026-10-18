"""Part II §5.4 stream key lifecycle — STRUCTURAL SCAFFOLD ONLY (team implements the business logic).

Answers 501 NOT_IMPLEMENTED until implemented; acceptance tests: tests/test_day2_contracts.py.
Building blocks: core.read_json / validation_error / ApiError / sign_day2, db.tx, Phase II tables.
"""
from fastapi import APIRouter, Request

from app.core import ApiError

router = APIRouter()


def _todo(name: str):
    raise ApiError(501, "NOT_IMPLEMENTED", f"{name} is not implemented yet.", {})


@router.post("/audit/v1/stream/key")
async def stream_key(request: Request):
    """§5.4. 201 for generate, 200 for rotate/revoke.
    TODO: validate action in {generate, rotate, revoke}, player_id required, label 1-64 (default "default").
    TODO: player must exist -> else 404 PLAYER_NOT_FOUND.
    TODO: stream_key_override if given, else a fresh key matching ^sk_live_[a-f0-9]{16}$.
    TODO: rotate/generate invalidate the player's previous active key; revoke with no key -> 404 STREAM_NOT_FOUND.
    TODO: revoked -> ingest_endpoints null, playback_url null; later use of the key -> 409 KEY_REVOKED.
    TODO: signature = sign_day2(stream_key, {action, player_id, status, stream_key}) (Table 5.3).
    """
    _todo("POST /audit/v1/stream/key")
