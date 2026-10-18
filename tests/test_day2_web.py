"""Guest Web Player support routes (Part II §1.1, §6.2.2, FR-4.2)."""
from conftest import err
from app.db import tx

TESTIDS = ["guest-video-player", "live-score-banner", "pinned-merch-card", "add-to-guest-cart-btn", "guest-cart-count",
           "chat-message-list", "chat-input-field", "chat-send-btn", "progressive-auth-modal"]


def test_live_page_has_all_nine_testids_and_no_login_wall(fresh):
    for path in ("/web/matches/match-m1/live", "/web/costream/cs-session-101"):
        r = fresh.get(path)
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
        for t in TESTIDS:
            assert f'data-testid="{t}"' in r.text, (path, t)
        assert 'id="auth-modal" role="dialog" aria-modal="true" aria-labelledby="auth-title" aria-describedby="auth-desc" hidden' in r.text


def test_guest_session_issues_read_only_token(fresh):
    j = fresh.post("/api/v1/guest/session").json()
    assert j["guest_token"].startswith("guest_anon_tok_") and j["role"] == "guest"
    with tx() as conn:
        assert conn.execute("SELECT status FROM guest_tokens WHERE guest_token = %s", (j["guest_token"],)).fetchone()["status"] == "active"
    r = fresh.post("/api/v1/chat", json={"text": "hi"}, headers={"Authorization": "Bearer " + j["guest_token"]})
    assert r.status_code == 403 and err(r) == "GUEST_WRITE_FORBIDDEN"


def test_web_match_summary_has_score_and_pinned_jersey(fresh):
    j = fresh.get("/web/api/matches/match-m1").json()
    assert (j["status"], j["score_text"], j["home"]["name"], j["away"]["name"]) == ("in_progress", "1 - 0", "Alpha United", "Alpha Rovers")
    assert j["pinned_product"]["product_id"] == "prod-jersey-001"
    assert "var-jersey-001-L" in {v["variant_id"] for v in j["pinned_product"]["variants"]}


def test_unknown_match_404(fresh):
    assert fresh.get("/web/api/matches/nope").status_code == 404
    assert fresh.get("/api/v1/matches/nope/stream").status_code == 404
