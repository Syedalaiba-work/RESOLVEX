from app import worker
from app.db import tx


def test_order_events_reach_the_queue_and_get_processed(fresh):
    body = {"order_id": "wq-1", "customer_id": "c", "items": [{"variant_id": "var-jersey-001-L", "quantity": 1}],
            "discount_code": None, "payment": {"token": "tok_success"}}
    assert fresh.post("/audit/v1/checkout", json=body).status_code == 201
    with tx() as conn:
        pending = conn.execute("SELECT type, payload FROM domain_events WHERE processed_at IS NULL").fetchall()
    assert any(r["type"] == "order.status_changed" and r["payload"]["to"] == "paid" for r in pending)
    assert worker.process_batch() >= 1
    with tx() as conn:
        assert conn.execute("SELECT count(*) AS n FROM domain_events WHERE processed_at IS NULL").fetchone()["n"] == 0
