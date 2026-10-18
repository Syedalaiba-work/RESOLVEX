"""Acceptance tests for the five Part II handlers you implement (§5.4–5.8, §8, Appendix B).

While a route still answers 501 NOT_IMPLEMENTED (the scaffold), its tests report XFAIL; once you implement
it they must pass for real, and a wrong implementation FAILS. Signatures are checked with the Appendix A
reference function and the DAY2_SALT of the running environment, never a hard-coded team salt.
"""
import hashlib
import hmac
import json
import os
import re
import threading

import pytest

from conftest import err


def ref_sign(entity_id, sig_payload):
    canonical = json.dumps(sig_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hmac.new(os.environ.get("DAY2_SALT", "").encode("utf-8"),
                    (entity_id + "|" + canonical).encode("utf-8"), hashlib.sha256).hexdigest()


def live(r):
    """XFAIL while the scaffold answers 501; otherwise return the response for real assertions."""
    if r.status_code == 501:
        pytest.xfail("handler not implemented yet (scaffold returns 501)")
    return r


# ---------------------------------------------------------------- 5.4 stream keys
SK = "/audit/v1/stream/key"


def test_stream_key_generate_201_shape_and_signature(fresh):
    r = live(fresh.post(SK, json={"action": "generate", "player_id": "player-alpha-1"}))
    assert r.status_code == 201
    j = r.json()
    key = j["stream_key"]
    assert re.fullmatch(r"sk_live_[a-f0-9]{16}", key)
    assert (j["player_id"], j["label"], j["status"]) == ("player-alpha-1", "default", "active")
    assert j["ingest_endpoints"] == {"rtmp": f"rtmp://localhost:1935/live/{key}",
                                     "webrtc": f"http://localhost:8889/live/{key}/whip"}
    assert j["playback_url"] == f"http://localhost:8888/live/{key}/index.m3u8"
    full = {"action": "generate", "player_id": "player-alpha-1", "status": "active", "stream_key": key}
    assert j["signature"] in {ref_sign(key, full), ref_sign(key, {"action": "generate", "player_id": "player-alpha-1"})}


def test_stream_key_rotate_uses_override_and_invalidates_old_key(fresh):
    first = live(fresh.post(SK, json={"action": "generate", "player_id": "player-alpha-1"})).json()["stream_key"]
    body = {"action": "rotate", "player_id": "player-alpha-1", "label": "OBS-Main-Desk",
            "stream_key_override": "sk_live_9f83a1b2c3d4e5f6"}
    r = live(fresh.post(SK, json=body))
    assert r.status_code == 200
    j = r.json()
    assert (j["stream_key"], j["label"], j["status"]) == ("sk_live_9f83a1b2c3d4e5f6", "OBS-Main-Desk", "active")
    sig = {"action": "rotate", "player_id": "player-alpha-1", "status": "active", "stream_key": "sk_live_9f83a1b2c3d4e5f6"}
    assert j["signature"] == ref_sign("sk_live_9f83a1b2c3d4e5f6", sig)
    assert first != j["stream_key"]
    assert "nascon_active_streams_total 1" in fresh.get("/metrics").text  # old key no longer active


def test_stream_key_revoke_and_revoke_without_key(fresh):
    r = live(fresh.post(SK, json={"action": "revoke", "player_id": "player-alpha-2"}))
    assert r.status_code == 404 and err(r) == "STREAM_NOT_FOUND"
    fresh.post(SK, json={"action": "generate", "player_id": "player-alpha-2"})
    j = fresh.post(SK, json={"action": "revoke", "player_id": "player-alpha-2"}).json()
    assert (j["status"], j["ingest_endpoints"], j["playback_url"]) == ("revoked", None, None)


@pytest.mark.parametrize("body, status, code", [
    ({"action": "explode", "player_id": "player-alpha-1"}, 400, "VALIDATION_ERROR"),
    ({"player_id": "player-alpha-1"}, 400, "VALIDATION_ERROR"),
    ({"action": "generate", "player_id": "nobody"}, 404, "PLAYER_NOT_FOUND"),
])
def test_stream_key_errors(fresh, body, status, code):
    r = live(fresh.post(SK, json=body))
    assert r.status_code == status and err(r) == code


# ---------------------------------------------------------------- 5.5 co-stream
CS = "/audit/v1/costream/session"
CS_BODY = {"session_id": "cs-session-101", "host_player_id": "player-alpha-1",
           "participants": ["player-alpha-1", "player-alpha-2", "player-beta-1", "player-beta-2"],
           "layout": "grid_4", "simulate_host_drop": True}


def test_costream_host_drop_handoff_matches_spec_example(fresh):
    r = live(fresh.post(CS, json=CS_BODY))
    assert r.status_code == 201
    j = r.json()
    expected = {"session_id": "cs-session-101", "status": "active", "active_host": "player-alpha-2",
                "handoff_occurred": True, "participant_count": 3,
                "active_participants": ["player-alpha-2", "player-beta-1", "player-beta-2"], "layout": "grid_4",
                "composite_playback_url": "http://localhost:8888/costream/cs-session-101/index.m3u8",
                "chat_room_id": "chat-cs-session-101"}
    assert {k: j[k] for k in expected} == expected
    sig = {"active_host": "player-alpha-2", "handoff_occurred": True, "layout": "grid_4",
           "participant_count": 3, "session_id": "cs-session-101", "status": "active"}
    assert j["signature"] == ref_sign("cs-session-101", sig)
    replay = fresh.post(CS, json=CS_BODY)
    assert replay.status_code == 200 and replay.json() == j


def test_costream_sole_host_drop_terminates(fresh):
    body = dict(CS_BODY, session_id="cs-solo", participants=["player-alpha-1"], layout="solo")
    j = live(fresh.post(CS, json=body)).json()
    assert (j["status"], j["active_host"], j["handoff_occurred"], j["participant_count"]) == ("terminated", None, False, 0)


@pytest.mark.parametrize("change, status, code", [
    ({"participants": ["player-alpha-1", "player-alpha-2", "player-beta-1", "player-beta-2", "player-alpha-1x"]}, 404, "PLAYER_NOT_FOUND"),
    ({"host_player_id": "player-beta-2", "participants": ["player-alpha-1", "player-alpha-2"]}, 400, "VALIDATION_ERROR"),
    ({"layout": "grid_2", "simulate_host_drop": False}, 400, "UNSUPPORTED_LAYOUT"),
    ({"participants": []}, 400, "VALIDATION_ERROR"),
    ({"layout": "mosaic"}, 400, "VALIDATION_ERROR"),
])
def test_costream_validation_order(fresh, change, status, code):
    r = live(fresh.post(CS, json=dict(CS_BODY, **change)))
    assert r.status_code == status and err(r) == code


def test_costream_more_than_four_is_full(fresh, monkeypatch):
    from app.db import tx
    with tx() as conn:
        conn.execute("INSERT INTO players VALUES ('player-gamma-1', 'tenant-alpha', 'club-alpha-1', 'G', 'fw', 'starter')")
    body = dict(CS_BODY, participants=CS_BODY["participants"] + ["player-gamma-1"])
    r = live(fresh.post(CS, json=body))
    assert r.status_code == 409 and err(r) == "COSTREAM_SESSION_FULL"


# ---------------------------------------------------------------- 5.6 dynamic QR
QR = "/audit/v1/qr"


def test_qr_resolve_match_m1_live(fresh):
    r = live(fresh.get(f"{QR}/match-m1"))
    assert r.status_code == 200
    j = r.json()
    expected = {"entity_id": "match-m1", "entity_type": "match", "entity_status": "in_progress",
                "short_url": "http://localhost:8080/q/m1-live", "target_route": "/web/matches/match-m1/live",
                "deep_link_uri": "nascon://entity/match-m1", "scan_count": 1,
                "export_formats": {f: f"http://localhost:8080/audit/v1/qr/match-m1/export.{f}" for f in ("svg", "png", "pdf")}}
    assert {k: j[k] for k in expected} == expected
    assert j["signature"] == ref_sign("match-m1", {"entity_id": "match-m1", "short_url": expected["short_url"],
                                                   "target_route": expected["target_route"]})


def test_qr_inspect_does_not_count(fresh):
    live(fresh.get(f"{QR}/match-m1"))
    assert fresh.get(f"{QR}/match-m1?inspect=true").json()["scan_count"] == 1
    assert fresh.get(f"{QR}/match-m1?inspect=true").json()["scan_count"] == 1


def test_qr_target_mutates_after_match_end_edge_case_2(fresh):
    before = live(fresh.get(f"{QR}/match-m1?inspect=true")).json()
    assert fresh.post("/audit/v1/events", json={"event_id": "m1-end", "match_id": "match-m1",
                                                "type": "match_end", "payload": {}}).status_code == 201
    after = fresh.get(f"{QR}/match-m1?inspect=true").json()
    assert after["short_url"] == before["short_url"]
    assert after["target_route"] == "/web/matches/match-m1/vod"
    assert after["signature"] != before["signature"]


@pytest.mark.parametrize("entity, route", [("player-alpha-1", "/web/players/player-alpha-1"),
                                           ("club-alpha-1", "/web/clubs/club-alpha-1")])
def test_qr_player_and_club_routes(fresh, entity, route):
    assert live(fresh.get(f"{QR}/{entity}")).json()["target_route"] == route


def test_qr_unknown_entity_404(fresh):
    r = live(fresh.get(f"{QR}/match-nope"))
    assert r.status_code == 404 and err(r) == "QR_NOT_FOUND"


@pytest.mark.parametrize("fmt, ctype, magic", [("svg", "image/svg+xml", None), ("png", "image/png", b"\x89PNG\r\n\x1a\n"),
                                               ("pdf", "application/pdf", b"%PDF-")])
def test_qr_exports(fresh, fmt, ctype, magic):
    r = live(fresh.get(f"{QR}/match-m1/export.{fmt}"))
    assert r.status_code == 200 and r.headers["content-type"].split(";")[0] == ctype
    if magic:
        assert r.content.startswith(magic)
    else:
        assert r.text.lstrip().startswith(("<svg", "<?xml"))


def test_short_link_redirects_302_and_records_privacy_safe_scan(fresh):
    r = live(fresh.get("/q/m1-live", follow_redirects=False,
                       headers={"User-Agent": "Mozilla/5.0 (Linux; Android 14) Mobile"}))
    assert r.status_code == 302 and r.headers["location"].endswith("/web/matches/match-m1/live")
    from app.db import tx
    with tx() as conn:
        rows = conn.execute("SELECT device_family FROM qr_scans").fetchall()
    assert [x["device_family"] for x in rows] == ["mobile"]


# ---------------------------------------------------------------- 5.7 guest cart merge
CM = "/audit/v1/guest/cart-merge"
CM_BODY = {"guest_token": "guest_anon_tok_7721", "registered_user_id": "player-alpha-1",
           "guest_cart": [{"variant_id": "var-jersey-001-L", "quantity": 1}], "test_write_block": True}


def test_cart_merge_matches_spec_example_and_replay_edge_case_4(fresh):
    r = live(fresh.post(CM, json=CM_BODY))
    assert r.status_code == 200
    j = r.json()
    assert (j["guest_token"], j["write_block_verified"], j["write_rejection_code"], j["cart_merged"]) == \
        ("guest_anon_tok_7721", True, 403, True)
    assert j["active_cart"] == {"user_id": "player-alpha-1", "currency": "PKR", "total_items": 1, "subtotal_minor": 450000,
                                "items": [{"variant_id": "var-jersey-001-L", "quantity": 1, "unit_price_minor": 450000}]}
    sig = {"cart_merged": True, "guest_token": "guest_anon_tok_7721", "registered_user_id": "player-alpha-1",
           "total_items": 1, "write_rejection_code": 403}
    assert j["signature"] == ref_sign("guest_anon_tok_7721", sig)
    replay = fresh.post(CM, json=CM_BODY)
    assert replay.status_code == 200 and replay.json()["active_cart"]["total_items"] == 1
    assert fresh.get("/audit/v1/inventory/var-jersey-001-L").json() == {"variant_id": "var-jersey-001-L", "stock": 5, "reserved": 0}


def test_cart_merge_reuse_with_other_user_is_409(fresh):
    live(fresh.post(CM, json=CM_BODY))
    r = fresh.post(CM, json=dict(CM_BODY, registered_user_id="player-alpha-2"))
    assert r.status_code == 409 and err(r) == "GUEST_TOKEN_ALREADY_MERGED"


@pytest.mark.parametrize("change, status, code", [
    ({"guest_token": "anon_7721"}, 400, "VALIDATION_ERROR"),
    ({"guest_cart": []}, 400, "VALIDATION_ERROR"),
    ({"guest_cart": [{"variant_id": "var-jersey-001-L", "quantity": 0}]}, 400, "VALIDATION_ERROR"),
    ({"registered_user_id": "nobody"}, 404, "PLAYER_NOT_FOUND"),
    ({"guest_cart": [{"variant_id": "var-nope", "quantity": 1}]}, 404, "VARIANT_NOT_FOUND"),
    ({"guest_cart": [{"variant_id": "var-jersey-001-M", "quantity": 2}]}, 409, "OUT_OF_STOCK"),
])
def test_cart_merge_errors(fresh, change, status, code):
    r = live(fresh.post(CM, json=dict(CM_BODY, **change)))
    assert r.status_code == status and err(r) == code


# ---------------------------------------------------------------- 5.8 moderation + DLQ
MOD = "/audit/v1/moderation/test"
MOD_BODY = {"chat_room_id": "chat-cs-session-101", "incoming_messages": [
    {"message_id": "msg-1", "sender": "user-guest-1", "text": "Clean sports commentary"},
    {"message_id": "msg-2", "sender": "user-spammer", "text": "Watch this illegal stream b@d_w0rd now!"},
    {"message_id": "msg-3", "sender": "user-flooder", "text": "GOAL! AAAA!!!"}],
    "check_dlq": True, "simulate_failed_notifications": 0}


def test_moderation_matches_spec_example(fresh):
    r = live(fresh.post(MOD, json=MOD_BODY))
    assert r.status_code == 200
    j = r.json()
    assert j["filtered_messages"] == [
        {"message_id": "msg-1", "sender": "user-guest-1", "text": "Clean sports commentary", "flagged": False, "reason": None},
        {"message_id": "msg-2", "sender": "user-spammer", "text": "Watch this illegal stream *** now!", "flagged": True,
         "reason": "profanity_leetspeak"}]
    assert (j["kicked_users"], j["muted_users"]) == (["user-spammer"], ["user-flooder"])
    assert j["dlq_status"] == {"queue_depth": 0, "undelivered_events": []}
    # flagged_count is not echoed in the body; accept either reading (flagged survivors, or all flagged).
    candidates = {ref_sign("chat-cs-session-101", {"chat_room_id": "chat-cs-session-101", "flagged_count": n,
                                                   "kicked_users": ["user-spammer"], "queue_depth": 0}) for n in (1, 2)}
    assert j["signature"] in candidates


@pytest.mark.parametrize("text", ["sc@m", "p.0.r.n", "a$$h0le", "f*u*c*k", "bad_word", "idiot_spam"])
def test_moderation_leetspeak_variants_are_masked(fresh, text):
    body = {"chat_room_id": "chat-x", "incoming_messages": [{"message_id": "m", "sender": "u", "text": f"you {text}"}]}
    msg = live(fresh.post(MOD, json=body)).json()["filtered_messages"][0]
    assert msg["flagged"] is True and msg["reason"] == "profanity_leetspeak" and "***" in msg["text"]


def test_moderation_dlq_simulated_failures(fresh):
    body = dict(MOD_BODY, simulate_failed_notifications=3)
    j = live(fresh.post(MOD, json=body)).json()
    assert j["dlq_status"]["queue_depth"] == 3 and len(j["dlq_status"]["undelivered_events"]) == 3
    assert "nascon_dlq_depth 3" in fresh.get("/metrics").text


def test_moderation_concurrent_kick_race_edge_case_3(fresh):
    live(fresh.post(MOD, json={"chat_room_id": "chat-race", "incoming_messages": [
        {"message_id": "warm", "sender": "x", "text": "hello"}]}))
    body = {"chat_room_id": "chat-race", "incoming_messages": [
        {"message_id": "r", "sender": "user-spammer", "text": "b@d_w0rd"}], "check_dlq": True}
    results, barrier = [], threading.Barrier(10)

    def fire():
        barrier.wait()
        results.append(fresh.post(MOD, json=body))

    threads = [threading.Thread(target=fire) for _ in range(10)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert [r.status_code for r in results] == [200] * 10
    assert all(r.json()["kicked_users"] == ["user-spammer"] for r in results)
