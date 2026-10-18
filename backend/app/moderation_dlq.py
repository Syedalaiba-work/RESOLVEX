"""Part II §5.8 / FR-5.2 / FR-5.3: synchronous chat moderation and the notification dead-letter queue."""
import re
import uuid

from fastapi import APIRouter, Request

from app.core import ApiError, is_id, read_json, sign_day2, validation_error
from app.db import J, tx

router = APIRouter()

PROFANITY = {"badword", "porn", "scam", "fuck", "shit", "bitch", "asshole", "idiotspam"}
LEET = str.maketrans({"@": "a", "0": "o", "1": "i", "!": "i", "3": "e", "$": "s"})
SEPARATORS = re.compile(r"[_.\-*​‌‍⁠﻿]")
FLOOD = re.compile(r"(.)\1{3,}|[!?]{3,}", re.IGNORECASE)  # >= 4 identical chars, or >= 3 '!'/'?'
MAX_ATTEMPTS = 3  # bounded retry before a notification is dead-lettered


def _is_profane(token: str) -> bool:
    core = token.strip(",.;:()[]{}\"'")
    if core.endswith(("!", "?")) and len(core) > 1:  # sentence punctuation, not leetspeak
        core = core.rstrip("!?")
    norm = SEPARATORS.sub("", core.lower()).translate(LEET)
    norm = re.sub(r"[^a-z]", "", norm)
    return norm in PROFANITY or (norm.endswith("s") and norm[:-1] in PROFANITY)


def _mask(text: str) -> tuple[str, bool]:
    """Replace each offending whitespace-separated token in place with ***, keeping trailing punctuation."""
    flagged = False
    out = []
    for token in re.split(r"(\s+)", text):
        if token and not token.isspace() and _is_profane(token):
            trail = re.search(r"[!?.,;:]+$", token)
            keep = trail.group(0) if trail and trail.start() > 0 and _is_profane(token[: trail.start()]) else ""
            out.append("***" + keep)
            flagged = True
        else:
            out.append(token)
    return "".join(out), flagged


def _validate(body: dict) -> dict:
    bad = []
    if not is_id(body.get("chat_room_id")):
        bad.append("chat_room_id")
    msgs = body.get("incoming_messages")
    if not (isinstance(msgs, list) and msgs and all(
            isinstance(m, dict) and isinstance(m.get("message_id"), str) and isinstance(m.get("sender"), str)
            and isinstance(m.get("text"), str) for m in msgs)):
        bad.append("incoming_messages")
    check_dlq = body.get("check_dlq", False)
    if not isinstance(check_dlq, bool):
        bad.append("check_dlq")
    fails = body.get("simulate_failed_notifications", 0)
    if not (isinstance(fails, int) and not isinstance(fails, bool) and 0 <= fails <= 1000):
        bad.append("simulate_failed_notifications")
    if bad:
        raise validation_error(bad)
    return {"room": body["chat_room_id"], "messages": msgs, "fails": fails}


@router.post("/audit/v1/moderation/test")
async def moderation_test(request: Request):
    req = _validate(await read_json(request))
    room = req["room"]
    filtered, kicks, mutes = [], [], []
    for m in req["messages"]:
        if FLOOD.search(m["text"]):  # rule 3: never broadcast
            if m["sender"] not in mutes:
                mutes.append(m["sender"])
            continue
        text, flagged = _mask(m["text"])
        if flagged and m["sender"] not in kicks:
            kicks.append(m["sender"])
        filtered.append({"message_id": m["message_id"], "sender": m["sender"], "text": text,
                         "flagged": flagged, "reason": "profanity_leetspeak" if flagged else None})
    with tx() as conn:
        # Idempotent under concurrent moderators (edge case 3): the primary key absorbs duplicates.
        for user, action in [(u, "kick") for u in kicks] + [(u, "mute") for u in mutes]:
            conn.execute("INSERT INTO moderation_actions (chat_room_id, user_id, action) VALUES (%s, %s, %s) "
                         "ON CONFLICT DO NOTHING", (room, user, action))
        for _ in range(req["fails"]):
            # Delivery is attempted MAX_ATTEMPTS times (simulated failure each time), then dead-lettered.
            event = {"event_id": f"ntf-{uuid.uuid4().hex[:12]}", "type": "notification", "chat_room_id": room,
                     "attempts": MAX_ATTEMPTS, "error": "simulated_delivery_failure"}
            conn.execute("INSERT INTO notification_dlq (event, attempts) VALUES (%s, %s)", (J(event), MAX_ATTEMPTS))
        state = {a: [r["user_id"] for r in conn.execute(
            "SELECT user_id FROM moderation_actions WHERE chat_room_id = %s AND action = %s ORDER BY created_order",
            (room, a)).fetchall()] for a in ("kick", "mute")}
        dlq = [r["event"] for r in conn.execute("SELECT event FROM notification_dlq ORDER BY id").fetchall()]
    flagged_count = sum(1 for m in filtered if m["flagged"])
    kicked = state["kick"]
    return {
        "chat_room_id": room,
        "filtered_messages": filtered,
        "kicked_users": kicked,
        "muted_users": state["mute"],
        "dlq_status": {"queue_depth": len(dlq), "undelivered_events": dlq},
        "signature": sign_day2(room, {"chat_room_id": room, "flagged_count": flagged_count,
                                      "kicked_users": kicked, "queue_depth": len(dlq)}),
    }
