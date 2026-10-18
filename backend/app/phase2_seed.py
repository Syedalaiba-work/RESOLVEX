"""Phase II baseline (Part II §5.2), recreated on every /audit/v1/reset after the Day 1 data.

match-m1 is built through the normal scoring service (signed events), like the Day 1 demo data.
"""
from app import scoring
from app.db import J, tx

MATCH_M1 = "match-m1"
GUEST_TOKEN = "guest_anon_tok_7721"
# entity_id -> (entity_type, short_code); short_url = http://localhost:8080/q/{short_code}
QR_MAPPINGS = {
    "match-m1": ("match", "m1-live"),
    "player-alpha-1": ("player", "p-alpha-1"),
    "club-alpha-1": ("club", "c-alpha-1"),
}


def _ev(event_id, event_type, payload):
    scoring.append_event({"event_id": event_id, "match_id": MATCH_M1, "type": event_type, "payload": payload})


def seed_day2() -> None:
    _ev("match-m1-init", "match_init", {"sport_id": "football", "home_team_id": "club-alpha-1",
                                        "away_team_id": "club-alpha-2", "league_id": "league-alpha-1"})
    _ev("match-m1-start", "match_start", {})
    _ev("match-m1-h0", "score", {"team_id": "club-alpha-1", "event_type": "goal"})
    with tx() as conn:
        for entity_id, (entity_type, short_code) in QR_MAPPINGS.items():
            conn.execute("INSERT INTO qr_codes (entity_id, entity_type, short_code) VALUES (%s, %s, %s)",
                         (entity_id, entity_type, short_code))
        conn.execute("INSERT INTO guest_tokens (guest_token, status) VALUES (%s, 'active')", (GUEST_TOKEN,))
        conn.execute("INSERT INTO carts (user_id, items) VALUES ('player-alpha-1', %s)", (J([]),))
