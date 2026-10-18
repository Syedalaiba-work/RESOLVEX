"""Part II restricted handlers — STRUCTURAL SCAFFOLD ONLY (team implements the business logic).

Each route is registered with its exact path and answers 501 NOT_IMPLEMENTED until implemented.
Acceptance tests: tests/test_day2_contracts.py (XFAIL while 501, must PASS once implemented).
Available building blocks: core.read_json, core.validation_error, core.ApiError, core.sign_day2,
db.tx (one transaction; use row locks / ON CONFLICT for concurrency), the Phase II tables in db.SCHEMA,
phase2_seed constants. Validation order everywhere: 400 -> 404 -> 403 -> 409 (Part II §5.2).
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


@router.get("/audit/v1/qr/{entity_id}")
def qr_resolve(entity_id: str, request: Request):
    """§5.6 and hidden scenario 2.
    TODO: unknown mapping -> 404 QR_NOT_FOUND; increment scan_count unless ?inspect=true.
    TODO: target_route computed from the entity's state at scan time (table in §5.6).
    TODO: record telemetry as (entity_id, device_family mobile|desktop, time bucket) only — no IP/UA (NFR-9).
    TODO: signature = sign_day2(entity_id, {entity_id, short_url, target_route}).
    """
    _todo("GET /audit/v1/qr/{entity_id}")


@router.get("/audit/v1/qr/{entity_id}/export.{fmt}")
def qr_export(entity_id: str, fmt: str):
    """§5.6 exports. TODO: svg (image/svg+xml), png (image/png, PNG magic), pdf (application/pdf, %PDF-),
    each encoding the short_url; the PDF also shows entity_id. Unknown -> 404 QR_NOT_FOUND."""
    _todo("GET /audit/v1/qr/{entity_id}/export.{fmt}")


@router.get("/q/{short_code}")
def short_link(short_code: str, request: Request):
    """§5.6 public short link. TODO: 302 Found with Location = current target_route; counts as a scan."""
    _todo("GET /q/{short_code}")


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


@router.post("/audit/v1/moderation/test")
async def moderation_test(request: Request):
    """§5.8, FR-5.2/5.3 and hidden scenario 3.
    TODO: design your own normalisation + dictionary match (spec lists the substitutions and words);
          masked tokens become ***, flagged/reason as in §5.8.
    TODO: flood rule (§5.8 rule 3) drops the message and mutes the sender.
    TODO: kicks/mutes must be idempotent under 10 concurrent requests (moderation_actions primary key).
    TODO: simulate_failed_notifications > 0 enqueues that many DLQ rows after bounded retry (max 3).
    TODO: signature = sign_day2(chat_room_id, {chat_room_id, flagged_count, kicked_users, queue_depth}).
    """
    _todo("POST /audit/v1/moderation/test")
