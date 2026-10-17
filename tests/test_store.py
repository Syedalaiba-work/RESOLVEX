import base64
import io
import os
import threading

import pytest
from pypdf import PdfReader

from app.core import sign
from app.pdf import money
from conftest import err

M, L = "var-jersey-001-M", "var-jersey-001-L"


def order(order_id, variant=M, qty=1, token="tok_success", code=None, customer="cust-001"):
    return {"order_id": order_id, "customer_id": customer, "items": [{"variant_id": variant, "quantity": qty}],
            "discount_code": code, "payment": {"token": token}}


def inv(client, variant=M):
    return client.get(f"/audit/v1/inventory/{variant}").json()


def test_successful_checkout_receipt_and_signature(fresh):
    r = fresh.post("/audit/v1/checkout", json=order("ord-001"))
    assert r.status_code == 201
    b = r.json()
    assert b["status"] == "paid" and b["currency"] == "PKR"
    assert b["items"] == [{"variant_id": M, "quantity": 1, "unit_price_minor": 450000}]
    assert (b["subtotal_minor"], b["discount_minor"], b["total_minor"]) == (450000, 0, 450000)
    assert b["payment"]["state"] == "captured"
    assert b["payment"]["authorization_id"].startswith("auth_") and b["payment"]["capture_id"].startswith("cap_")
    p = b["receipt"]["payload"]
    assert set(p) == {"order_id", "customer_id", "items", "subtotal_minor", "discount_minor", "total_minor",
                      "currency", "paid_at"}
    assert b["receipt"]["signature"] == sign("ord-001", p, key=os.environ["DAY1_SALT"])
    pdf = base64.b64decode(b["receipt"]["pdf_base64"])
    assert pdf.startswith(b"%PDF")
    text = "".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages)
    assert "ord-001" in text and "PKR 4500.00" in text
    assert inv(fresh) == {"variant_id": M, "stock": 0, "reserved": 0}


def test_idempotent_replay_and_duplicate_order_id(fresh):
    fresh.post("/audit/v1/reset", json={"stock": {L: 5}})
    first = fresh.post("/audit/v1/checkout", json=order("o1", variant=L))
    again = fresh.post("/audit/v1/checkout", json=order("o1", variant=L))
    assert first.status_code == 201 and again.status_code == 200 and again.json() == first.json()
    assert inv(fresh, L)["stock"] == 4  # no second reservation
    diff = fresh.post("/audit/v1/checkout", json=order("o1", variant=L, qty=2))
    assert diff.status_code == 409 and err(diff) == "DUPLICATE_ORDER_ID"


def test_discount_code(fresh):
    b = fresh.post("/audit/v1/checkout", json=order("o2", variant=L, qty=3, code="WELCOME10")).json()
    assert (b["subtotal_minor"], b["discount_minor"], b["total_minor"]) == (1350000, 135000, 1215000)
    r = fresh.post("/audit/v1/checkout", json=order("o3", variant=L, code="FREE"))
    assert r.status_code == 400 and err(r) == "INVALID_DISCOUNT_CODE"


def test_out_of_stock_reserves_nothing(fresh):
    fresh.post("/audit/v1/reset", json={"stock": {M: 0, L: 5}})
    body = {"order_id": "o4", "customer_id": "c", "discount_code": None, "payment": {"token": "tok_success"},
            "items": [{"variant_id": L, "quantity": 2}, {"variant_id": M, "quantity": 1}]}
    r = fresh.post("/audit/v1/checkout", json=body)
    assert r.status_code == 409 and err(r) == "OUT_OF_STOCK"
    assert r.json()["error"]["details"] == {"variant_id": M}
    assert inv(fresh, L) == {"variant_id": L, "stock": 5, "reserved": 0}


@pytest.mark.parametrize("token, code", [("tok_declined", "PAYMENT_DECLINED"), ("tok_capture_fail", "PAYMENT_CAPTURE_FAILED")])
def test_payment_failures_release_stock(fresh, token, code):
    r = fresh.post("/audit/v1/checkout", json=order("o5", token=token))
    assert r.status_code == 402 and err(r) == code
    assert inv(fresh) == {"variant_id": M, "stock": 1, "reserved": 0}
    assert fresh.post("/audit/v1/checkout", json=order("o6")).status_code == 201  # released stock is buyable


def test_validation_order(fresh):
    assert err(fresh.post("/audit/v1/checkout", json=order("o7", variant="var-nope"))) == "VARIANT_NOT_FOUND"
    for bad in (order("o8", qty=0), order("o9", qty=11), order("o|x"), order("o10", token="tok_magic"),
                {**order("o11"), "items": []}):
        r = fresh.post("/audit/v1/checkout", json=bad)
        assert r.status_code == 400 and err(r) == "VALIDATION_ERROR", bad
    two = {**order("o12"), "items": [{"variant_id": M, "quantity": 1}, {"variant_id": M, "quantity": 1}]}
    assert fresh.post("/audit/v1/checkout", json=two).status_code == 400


def test_hostile_customer_id_is_plain_data(fresh):
    nasty = "x'\"; DROP TABLE orders;-- <script>alert(1)</script> (paren)"
    r = fresh.post("/audit/v1/checkout", json=order("o13", customer=nasty))
    assert r.status_code == 201
    assert r.json()["receipt"]["payload"]["customer_id"] == nasty


def test_twenty_concurrent_buyers_last_unit(fresh):
    fresh.post("/audit/v1/reset", json={"stock": {M: 1}})
    barrier = threading.Barrier(20)
    codes = []
    lock = threading.Lock()

    def buy(i):
        barrier.wait()
        r = fresh.post("/audit/v1/checkout", json=order(f"burst-{i}"))
        with lock:
            codes.append(r.status_code)

    threads = [threading.Thread(target=buy, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    assert sorted(codes) == [201] + [409] * 19
    assert inv(fresh) == {"variant_id": M, "stock": 0, "reserved": 0}


def test_inventory_unknown(fresh):
    r = fresh.get("/audit/v1/inventory/nope")
    assert r.status_code == 404 and err(r) == "VARIANT_NOT_FOUND"


def test_money_format():
    assert money(450000) == "PKR 4500.00" and money(5) == "PKR 0.05" and money(123456789) == "PKR 1234567.89"
