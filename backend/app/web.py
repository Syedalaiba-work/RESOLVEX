"""Guest Web Player (Part II §1.1, §6.2.2, NFR-1, NFR-8) and its read-only support routes.

Guests get an anonymous token (FR-4.2) and can only read; every write they attempt is rejected by
main.guards with 403 GUEST_WRITE_FORBIDDEN (FR-4.3), which the page turns into the registration modal.
"""
import asyncio
import json
import pathlib
import secrets

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from starlette.concurrency import run_in_threadpool

from app import observability, scoring
from app.core import ApiError
from app.db import tx

router = APIRouter()
_PAGE = (pathlib.Path(__file__).parent / "web" / "player.html").read_text(encoding="utf-8")
SSE_POLL_S = 0.1  # score changes reach clients well inside the 500 ms budget


def _pinned(conn, match_id):
    row = conn.execute("SELECT value FROM meta WHERE key = 'pinned'").fetchone()
    product_id = (row["value"] if row else {}).get(match_id, "prod-jersey-001")
    p = conn.execute("SELECT * FROM products WHERE product_id = %s", (product_id,)).fetchone()
    if not p:
        return None
    variants = conn.execute("SELECT variant_id, label, price_minor, currency, stock FROM variants "
                            "WHERE product_id = %s ORDER BY variant_id", (product_id,)).fetchall()
    return {"product_id": p["product_id"], "name": p["name"], "variants": [dict(v) for v in variants]}


def match_summary(match_id: str) -> dict:
    view = scoring.score_view(match_id)  # 404 MATCH_NOT_FOUND for unknown ids
    with tx() as conn:
        names = conn.execute("SELECT value FROM meta WHERE key = 'team_names'").fetchone()
        names = names["value"] if names else {}
        pinned = _pinned(conn, match_id)
    return {
        "match_id": view["match_id"], "status": view["status"], "version": view["version"],
        "home": {"team_id": view["home"]["team_id"], "name": names.get(view["home"]["team_id"], view["home"]["team_id"]),
                 "score": view["home"]["score"]},
        "away": {"team_id": view["away"]["team_id"], "name": names.get(view["away"]["team_id"], view["away"]["team_id"]),
                 "score": view["away"]["score"]},
        "score_text": f'{view["home"]["score"]} - {view["away"]["score"]}',
        "pinned_product": pinned,
    }


@router.post("/api/v1/guest/session")
def guest_session():
    token = "guest_anon_tok_" + secrets.token_hex(8)
    with tx() as conn:
        conn.execute("INSERT INTO guest_tokens (guest_token, status) VALUES (%s, 'active')", (token,))
    return {"guest_token": token, "role": "guest", "scopes": ["playback", "score_read", "guest_cart"]}


@router.get("/web/api/matches/{match_id}")
def web_match(match_id: str):
    return match_summary(match_id)


@router.get("/api/v1/matches/{match_id}/stream")
async def match_stream(match_id: str, request: Request):
    first = await run_in_threadpool(match_summary, match_id)  # 404 before the stream starts

    async def events():
        observability.ws_connected(+1)
        try:
            last = None
            current = first
            while True:
                if current["version"] != last:
                    last = current["version"]
                    yield f"event: score\ndata: {json.dumps(current)}\n\n"
                if await request.is_disconnected():
                    return
                await asyncio.sleep(SSE_POLL_S)
                try:
                    current = await run_in_threadpool(match_summary, match_id)
                except ApiError:
                    return
        finally:
            observability.ws_connected(-1)

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/web/{path:path}", response_class=HTMLResponse)
def web_app(path: str):
    # One accessible page shell; the script reads the route (matches/{id}/live|preview|vod|notice,
    # costream/{id}, players/{id}, clubs/{id}).
    return HTMLResponse(_PAGE)
