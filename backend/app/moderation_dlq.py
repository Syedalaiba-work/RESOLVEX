"""Part II §5.8 chat moderation + notification DLQ — STRUCTURAL SCAFFOLD ONLY (team implements the business logic).

Answers 501 NOT_IMPLEMENTED until implemented; acceptance tests: tests/test_day2_contracts.py.
Building blocks: core.read_json / validation_error / ApiError / sign_day2, db.tx, Phase II tables.
"""
from fastapi import APIRouter, Request

from app.core import ApiError

router = APIRouter()


def _todo(name: str):
    raise ApiError(501, "NOT_IMPLEMENTED", f"{name} is not implemented yet.", {})


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
