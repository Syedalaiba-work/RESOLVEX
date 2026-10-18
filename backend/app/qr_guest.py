"""Part II §5.6 dynamic QR + §5.7 guest cart merge — STRUCTURAL SCAFFOLD ONLY (team implements the business logic).

Answers 501 NOT_IMPLEMENTED until implemented; acceptance tests: tests/test_day2_contracts.py.
Building blocks: core.read_json / validation_error / ApiError / sign_day2, db.tx, Phase II tables.
"""
from fastapi import APIRouter, Request

from app.core import ApiError

router = APIRouter()


def _todo(name: str):
    raise ApiError(501, "NOT_IMPLEMENTED", f"{name} is not implemented yet.", {})


@router.get("/audit/v1/qr/{entity_id}")
def qr_resolve(entity_id: str, request: Request):
    """§5.6 and hidden scenario 2.
    TODO: unknown mapping -> 404 QR_NOT_FOUND; increment scan_count unless ?inspect=true.
    TODO: target_route computed from the entity's state at scan time (table in §5.6).
    TODO: record telemetry as (entity_id, device_family mobile|desktop, time bucket) only — no IP/UA (NFR-9).
    TODO: signature = sign_day2(entity_id, {entity_id, short_url, target_route}).
    """
    _todo("GET /audit/v1/qr/{entity_id}")


@router.get("/audit/v1/qr/{entity_id}/export.{fmt}")
def qr_export(entity_id: str, fmt: str):
    """§5.6 exports. TODO: svg (image/svg+xml), png (image/png, PNG magic), pdf (application/pdf, %PDF-),
    each encoding the short_url; the PDF also shows entity_id. Unknown -> 404 QR_NOT_FOUND."""
    _todo("GET /audit/v1/qr/{entity_id}/export.{fmt}")


@router.get("/q/{short_code}")
def short_link(short_code: str, request: Request):
    """§5.6 public short link. TODO: 302 Found with Location = current target_route; counts as a scan."""
    _todo("GET /q/{short_code}")


@router.post("/audit/v1/guest/cart-merge")
async def guest_cart_merge(request: Request):
    """§5.7 and hidden scenario 4.
    TODO: schema (guest_ prefix, 1-10 items, quantity >= 1) -> 404 user / variant -> 409 OUT_OF_STOCK.
    TODO: test_write_block: prove the guard rejects a guest write with 403 (see main.guards) and report it.
    TODO: merge atomically into carts (sum same variant, cap by stock, no stock reservation).
    TODO: identical replay -> 200 same cart; same token, other user/payload -> 409 GUEST_TOKEN_ALREADY_MERGED.
    TODO: signature = sign_day2(guest_token, {cart_merged, guest_token, registered_user_id, total_items,
          write_rejection_code}).
    """
    _todo("POST /audit/v1/guest/cart-merge")
