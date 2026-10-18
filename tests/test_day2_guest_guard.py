"""FR-4.3 / Part II §5.7 "Direct Write Enforcement Check": guest tokens can never write."""
import pytest

from conftest import err

GUEST = {"Authorization": "Bearer guest_anon_tok_7721"}
CHECKOUT = {"order_id": "g-ord-1", "customer_id": "c", "items": [{"variant_id": "var-jersey-001-L", "quantity": 1}],
            "discount_code": None, "payment": {"token": "tok_success"}}
EVENT = {"event_id": "g-ev-1", "match_id": "match-m1", "type": "score",
         "payload": {"team_id": "club-alpha-1", "event_type": "goal"}}


@pytest.mark.parametrize("path, body", [
    ("/api/v1/chat", {"chat_room_id": "chat-cs-session-101", "text": "hi"}),
    ("/audit/v1/checkout", CHECKOUT),
    ("/audit/v1/events", EVENT),
])
def test_guest_token_writes_are_forbidden(fresh, path, body):
    r = fresh.post(path, json=body, headers=GUEST)
    assert r.status_code == 403
    e = r.json()["error"]
    assert e["code"] == "GUEST_WRITE_FORBIDDEN"
    assert e["details"] == {"guest_token": "guest_anon_tok_7721"}
    assert isinstance(e["message"], str) and e["message"]


def test_guest_block_precedes_body_validation_and_has_no_side_effects(fresh):
    assert fresh.post("/audit/v1/checkout", content=b"{not json", headers=GUEST).status_code == 403
    assert fresh.post("/audit/v1/checkout", json=CHECKOUT, headers=GUEST).status_code == 403
    assert fresh.get("/audit/v1/inventory/var-jersey-001-L").json()["stock"] == 5
    assert fresh.get("/audit/v1/score/match-m1").json()["version"] == 3


@pytest.mark.parametrize("method", ["put", "patch", "delete"])
def test_other_write_methods_are_forbidden_for_guests(fresh, method):
    r = getattr(fresh, method)("/api/v1/roster/transfer", headers=GUEST)
    assert r.status_code == 403 and err(r) == "GUEST_WRITE_FORBIDDEN"


def test_guest_token_can_still_read(fresh):
    assert fresh.get("/audit/v1/score/match-m1", headers=GUEST).status_code == 200
    assert fresh.get("/health", headers=GUEST).status_code == 200


def test_day1_unauthenticated_audit_writes_unchanged(fresh):
    r = fresh.post("/audit/v1/events", json=EVENT)
    assert r.status_code == 201
    assert fresh.post("/audit/v1/checkout", json=CHECKOUT).status_code == 201
