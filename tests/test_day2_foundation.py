"""Part II foundation: DAY2_SALT signing (§5.3, Appendix A) and the reset baseline (§5.2)."""
import hashlib
import hmac
import json
import pathlib

from app import core
from app.db import tx

REFERENCE_SALT = "T01D27ad7ffff12e"  # Appendix A reference salt (published test vector, not a team salt)


def reference_sign_day2(day2_salt, entity_id, sig_payload):
    """Verbatim copy of the Appendix A reference function."""
    canonical = json.dumps(sig_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    msg = (entity_id + "|" + canonical).encode("utf-8")
    return hmac.new(day2_salt.encode("utf-8"), msg, hashlib.sha256).hexdigest()


def test_appendix_a_vectors_match_reference(monkeypatch):
    monkeypatch.setenv("DAY2_SALT", REFERENCE_SALT)
    v1 = {"action": "rotate", "player_id": "player-alpha-1", "status": "active",
          "stream_key": "sk_live_9f83a1b2c3d4e5f6"}
    v2 = {"action": "rotate", "player_id": "player-alpha-1"}
    for entity_id, payload in (("sk_live_9f83a1b2c3d4e5f6", v1), ("sk_live_101", v2)):
        got = core.sign_day2(entity_id, payload)
        assert got == reference_sign_day2(REFERENCE_SALT, entity_id, payload)
        assert len(got) == 64 and got == got.lower()


def test_day2_salt_is_read_from_environment(monkeypatch):
    payload = {"entity_id": "match-m1"}
    monkeypatch.setenv("DAY2_SALT", "aaaaaaaaaaaaaaaa")
    a = core.sign_day2("match-m1", payload)
    monkeypatch.setenv("DAY2_SALT", "bbbbbbbbbbbbbbbb")
    assert core.sign_day2("match-m1", payload) != a
    # Day 1 and Day 2 keys are independent.
    monkeypatch.setenv("DAY1_SALT", "aaaaaaaaaaaaaaaa")
    assert core.sign("match-m1", payload) == a


def test_no_salt_literal_in_backend_source():
    src = pathlib.Path(core.__file__).resolve().parent
    for f in src.rglob("*.py"):
        text = f.read_text(encoding="utf-8")
        assert REFERENCE_SALT not in text, f
        assert "DAY2_SALT =" not in text and "DAY2_SALT=" not in text, f


def test_reset_seeds_phase2_baseline(fresh):
    m1 = fresh.get("/audit/v1/score/match-m1").json()
    assert (m1["status"], m1["league_id"]) == ("in_progress", "league-alpha-1")
    assert (m1["home"]["team_id"], m1["home"]["score"], m1["away"]["team_id"], m1["away"]["score"]) == \
        ("club-alpha-1", 1, "club-alpha-2", 0)
    with tx() as conn:
        assert conn.execute("SELECT club_id FROM players WHERE player_id = 'player-beta-2'").fetchone()["club_id"] == "club-beta-1"
        qr = {r["entity_id"]: (r["short_code"], r["scan_count"])
              for r in conn.execute("SELECT * FROM qr_codes").fetchall()}
        assert qr == {"match-m1": ("m1-live", 0), "player-alpha-1": ("p-alpha-1", 0), "club-alpha-1": ("c-alpha-1", 0)}
        tok = conn.execute("SELECT status, user_id FROM guest_tokens WHERE guest_token = 'guest_anon_tok_7721'").fetchone()
        assert (tok["status"], tok["user_id"]) == ("active", None)
        assert conn.execute("SELECT items FROM carts WHERE user_id = 'player-alpha-1'").fetchone()["items"] == []


def test_reset_is_repeatable_with_phase2_state(fresh):
    with tx() as conn:
        conn.execute("UPDATE qr_codes SET scan_count = 9")
        conn.execute("UPDATE guest_tokens SET status = 'merged'")
    assert fresh.post("/audit/v1/reset", json={}).status_code == 200
    with tx() as conn:
        assert conn.execute("SELECT SUM(scan_count) AS s FROM qr_codes").fetchone()["s"] == 0
        assert conn.execute("SELECT status FROM guest_tokens").fetchone()["status"] == "active"
    assert fresh.get("/audit/v1/score/match-m1").json()["version"] == 3
