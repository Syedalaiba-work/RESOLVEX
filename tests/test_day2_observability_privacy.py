"""NFR-6 (GET /metrics) and NFR-9 (DELETE /audit/v1/privacy/user/{user_id}), Part II §5.9."""
import re

from conftest import err
from app.db import tx

METRICS = ["nascon_active_ws_connections", "nascon_active_streams_total", "nascon_stream_bitrate_kbps",
           "nascon_dlq_depth", "nascon_qr_scans_total"]
SAMPLE = re.compile(r"^([a-zA-Z_:][a-zA-Z0-9_:]*)(\{[^}]*\})? (-?[0-9.eE+]+|NaN|\+Inf|-Inf)$")


def parse(text):
    values, types = {}, {}
    for line in text.splitlines():
        if line.startswith("# TYPE "):
            _, _, name, kind = line.split(" ")
            types[name] = kind
        elif line and not line.startswith("#"):
            m = SAMPLE.match(line)
            assert m, f"not a Prometheus sample line: {line!r}"
            values[m.group(1)] = float(m.group(3))
    return values, types


def test_metrics_exposition_format_and_required_series(fresh):
    r = fresh.get("/metrics")
    assert r.status_code == 200
    assert r.headers["content-type"] == "text/plain; version=0.0.4"
    values, types = parse(r.text)
    for name in METRICS:
        assert name in values and types.get(name) in ("gauge", "counter"), name
    assert r.text.endswith("\n")


def test_metrics_reflect_database_state(fresh):
    with tx() as conn:
        conn.execute("UPDATE qr_codes SET scan_count = 2 WHERE entity_id = 'match-m1'")
        conn.execute("INSERT INTO notification_dlq (event, attempts) VALUES ('{}', 3), ('{}', 3)")
        conn.execute("INSERT INTO stream_keys (stream_key, player_id, label, status) VALUES "
                     "('sk_live_aaaaaaaaaaaaaaaa', 'player-alpha-1', 'x', 'active'), "
                     "('sk_live_bbbbbbbbbbbbbbbb', 'player-alpha-2', 'x', 'revoked')")
    values, _ = parse(fresh.get("/metrics").text)
    assert values["nascon_qr_scans_total"] == 2
    assert values["nascon_dlq_depth"] == 2
    assert values["nascon_active_streams_total"] == 1


def test_privacy_erasure_anonymizes_user_and_wipes_tokens(fresh):
    with tx() as conn:
        conn.execute("UPDATE guest_tokens SET status = 'merged', user_id = 'player-alpha-1'")
    r = fresh.delete("/audit/v1/privacy/user/player-alpha-1")
    assert r.status_code == 200
    assert r.json() == {"user_id": "player-alpha-1", "status": "anonymized", "pii_retained": False,
                        "tokens_wiped": True}
    with tx() as conn:
        player = conn.execute("SELECT name FROM players WHERE player_id = 'player-alpha-1'").fetchone()
        assert player["name"] != "Ahmed Raza"
        users = conn.execute("SELECT email, display_name FROM users WHERE player_id = 'player-alpha-1'").fetchall()
        assert users and all("nascon.test" not in u["email"] for u in users)
        assert all(u["display_name"] != "Ahmed Raza" for u in users)
        tok = conn.execute("SELECT status, user_id FROM guest_tokens WHERE guest_token = 'guest_anon_tok_7721'").fetchone()
        assert (tok["status"], tok["user_id"]) == ("wiped", None)
    # Anonymized user can no longer sign in with the old e-mail.
    login = fresh.post("/api/v1/auth/login", json={"email": "player@nascon.test", "password": "Nascon@26"})
    assert login.status_code == 401


def test_privacy_erasure_is_idempotent(fresh):
    first = fresh.delete("/audit/v1/privacy/user/player-alpha-1").json()
    second = fresh.delete("/audit/v1/privacy/user/player-alpha-1")
    assert second.status_code == 200 and second.json() == first


def test_privacy_erasure_unknown_user_404(fresh):
    r = fresh.delete("/audit/v1/privacy/user/nobody-1")
    assert r.status_code == 404 and err(r) == "PLAYER_NOT_FOUND"


def test_scan_telemetry_table_has_no_pii_columns(fresh):
    with tx() as conn:
        cols = {r["column_name"] for r in conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'qr_scans'").fetchall()}
    assert cols == {"entity_id", "device_family", "bucket"}
