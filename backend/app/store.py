"""Concurrency-safe checkout with a mock payment gateway and signed PDF receipts (spec 5.12, NFR-3)."""
import base64
import math

from app.core import ApiError, Checker, canonical, is_id, is_int, is_str, sign, utc_now
from app.db import J, tx
from app.pdf import money, text_pdf

DISCOUNTS = {"WELCOME10": 10}  # percent off subtotal
TOKENS = {"tok_success", "tok_declined", "tok_capture_fail"}


def validate_checkout(body: dict) -> dict:
    c = Checker()
    c.check(is_id(body.get("order_id")), "order_id")
    customer = body.get("customer_id")
    c.check(is_str(customer) and 1 <= len(customer) <= 200, "customer_id")
    items = body.get("items")
    items_ok = isinstance(items, list) and 1 <= len(items) <= 10 and all(isinstance(i, dict) for i in items)
    if items_ok:
        ids = [i.get("variant_id") for i in items]
        items_ok = (all(is_id(v) for v in ids) and len(set(ids)) == len(ids)
                    and all(is_int(i.get("quantity")) and 1 <= i["quantity"] <= 10 for i in items))
    c.check(items_ok, "items")
    code = body.get("discount_code")
    c.check(code is None or is_str(code), "discount_code")
    payment = body.get("payment")
    c.check(isinstance(payment, dict) and payment.get("token") in TOKENS, "payment")
    c.raise_if_any()
    return {
        "order_id": body["order_id"], "customer_id": customer,
        "items": [{"variant_id": i["variant_id"], "quantity": i["quantity"]} for i in items],
        "discount_code": code, "payment": {"token": payment["token"]},
    }


def checkout(body: dict) -> tuple[int, dict]:
    req = validate_checkout(body)
    order_id = req["order_id"]
    with tx() as conn:
        existing = conn.execute("SELECT request, response FROM orders WHERE order_id = %s", (order_id,)).fetchone()
        if existing:
            if canonical(existing["request"]) == canonical(req):
                return 200, existing["response"]
            raise ApiError(409, "DUPLICATE_ORDER_ID", f"Order {order_id} was already used with a different body.",
                           {"order_id": order_id})
        prices = {}
        for item in req["items"]:
            row = conn.execute("SELECT price_minor FROM variants WHERE variant_id = %s",
                               (item["variant_id"],)).fetchone()
            if row is None:
                raise ApiError(404, "VARIANT_NOT_FOUND", f"Variant {item['variant_id']} does not exist.",
                               {"variant_id": item["variant_id"]})
            prices[item["variant_id"]] = row["price_minor"]
    if req["discount_code"] is not None and req["discount_code"] not in DISCOUNTS:
        raise ApiError(400, "INVALID_DISCOUNT_CODE", "This discount code is not valid.",
                       {"discount_code": req["discount_code"]})

    # 1) Atomically reserve every item, or nothing. Lock rows in a fixed order to avoid deadlocks.
    items = sorted(req["items"], key=lambda i: i["variant_id"])
    with tx() as conn:
        for item in items:
            ok = conn.execute(
                "UPDATE variants SET stock = stock - %s, reserved = reserved + %s "
                "WHERE variant_id = %s AND stock >= %s RETURNING stock",
                (item["quantity"], item["quantity"], item["variant_id"], item["quantity"]),
            ).fetchone()
            if ok is None:
                raise ApiError(409, "OUT_OF_STOCK", f"Variant {item['variant_id']} has no stock left.",
                               {"variant_id": item["variant_id"]})  # rollback releases earlier items

    # 2) Mock payment gateway.
    token = req["payment"]["token"]
    with tx() as conn:
        auth_id = _payment_id(conn, order_id, "authorization")
    if token == "tok_declined":
        _release(items, order_id, "authorization_declined")
        raise ApiError(402, "PAYMENT_DECLINED", "The payment was declined.", {"order_id": order_id})
    if token == "tok_capture_fail":
        _release(items, order_id, "capture_failed_authorization_voided")
        raise ApiError(402, "PAYMENT_CAPTURE_FAILED", "The payment could not be captured.", {"order_id": order_id})

    # 3) Capture: commit the reservation, record the paid order, emit the domain event.
    subtotal = sum(prices[i["variant_id"]] * i["quantity"] for i in req["items"])
    discount = math.floor(subtotal * DISCOUNTS[req["discount_code"]] / 100) if req["discount_code"] else 0
    total = subtotal - discount
    lines = [{"variant_id": i["variant_id"], "quantity": i["quantity"],
              "unit_price_minor": prices[i["variant_id"]]} for i in req["items"]]
    payload = {"order_id": order_id, "customer_id": req["customer_id"], "items": lines,
               "subtotal_minor": subtotal, "discount_minor": discount, "total_minor": total,
               "currency": "PKR", "paid_at": utc_now()}
    try:
        with tx() as conn:
            cap_id = _payment_id(conn, order_id, "capture")
            response = {
                "order_id": order_id, "status": "paid", "currency": "PKR", "items": lines,
                "subtotal_minor": subtotal, "discount_minor": discount, "total_minor": total,
                "payment": {"authorization_id": auth_id, "capture_id": cap_id, "state": "captured"},
                "receipt": {"payload": payload, "signature": sign(order_id, payload),
                            "pdf_base64": base64.b64encode(_receipt_pdf(payload)).decode("ascii")},
            }
            for item in items:
                conn.execute("UPDATE variants SET reserved = reserved - %s WHERE variant_id = %s",
                             (item["quantity"], item["variant_id"]))
            inserted = conn.execute(
                "INSERT INTO orders (order_id, request, status_code, response, status) "
                "VALUES (%s, %s, 201, %s, 'paid') ON CONFLICT DO NOTHING RETURNING order_id",
                (order_id, J(req), J(response)),
            ).fetchone()
            if inserted is None:
                raise _Conflict()
            conn.execute("INSERT INTO domain_events (type, payload) VALUES ('order.status_changed', %s)",
                         (J({"order_id": order_id, "from": "pending", "to": "paid", "total_minor": total}),))
    except _Conflict:
        # Another request with the same order_id won the race: undo our reservation, replay theirs.
        _release(items, order_id, "duplicate_order")
        return checkout(body)
    return 201, response


class _Conflict(Exception):
    pass


def _release(items, order_id, reason):
    with tx() as conn:
        for item in items:
            conn.execute("UPDATE variants SET stock = stock + %s, reserved = reserved - %s WHERE variant_id = %s",
                         (item["quantity"], item["quantity"], item["variant_id"]))
        conn.execute("INSERT INTO domain_events (type, payload) VALUES ('order.payment_failed', %s)",
                     (J({"order_id": order_id, "reason": reason}),))


def _payment_id(conn, order_id, kind) -> str:
    row = conn.execute("INSERT INTO payments (order_id, kind) VALUES (%s, %s) RETURNING id",
                       (order_id, kind)).fetchone()
    return f"{'auth' if kind == 'authorization' else 'cap'}_{row['id']}"


def _receipt_pdf(payload) -> bytes:
    lines = [f"Order: {payload['order_id']}", f"Customer: {payload['customer_id']}", f"Paid at: {payload['paid_at']}", ""]
    for item in payload["items"]:
        lines.append(f"{item['variant_id']}  x{item['quantity']}  @ {money(item['unit_price_minor'])}")
    lines += ["", f"Subtotal: {money(payload['subtotal_minor'])}", f"Discount: {money(payload['discount_minor'])}",
              f"Total: {money(payload['total_minor'])}"]
    return text_pdf(lines, title="NaSCon Club Store - Receipt")


def inventory(variant_id: str) -> dict:
    with tx() as conn:
        row = conn.execute("SELECT variant_id, stock, reserved FROM variants WHERE variant_id = %s",
                           (variant_id,)).fetchone()
    if row is None:
        raise ApiError(404, "VARIANT_NOT_FOUND", f"Variant {variant_id} does not exist.", {"variant_id": variant_id})
    return dict(row)
