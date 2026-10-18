"""Part II NFR-1: score events reach WebSocket clients on ws://.../ws/matches/{match_id} in < 500 ms."""
import time

import pytest
from starlette.websockets import WebSocketDisconnect

GOAL = {"match_id": "match-m1", "type": "score", "payload": {"team_id": "club-alpha-1", "event_type": "goal"}}


def test_ws_pushes_current_score_then_new_score_quickly(fresh):
    with fresh.websocket_connect("/ws/matches/match-m1") as ws:
        first = ws.receive_json()
        assert (first["match_id"], first["score_text"], first["status"]) == ("match-m1", "1 - 0", "in_progress")
        t0 = time.monotonic()
        assert fresh.post("/audit/v1/events", json=dict(GOAL, event_id="ws-g1")).status_code == 201
        update = ws.receive_json()
        assert update["score_text"] == "2 - 0" and update["version"] == first["version"] + 1
        assert time.monotonic() - t0 < 0.5


def test_ws_counts_active_connections_in_metrics(fresh):
    def gauge():
        line = next(x for x in fresh.get("/metrics").text.splitlines() if x.startswith("nascon_active_ws_connections "))
        return int(line.split()[1])

    before = gauge()
    with fresh.websocket_connect("/ws/matches/match-m1") as ws:
        ws.receive_json()
        assert gauge() == before + 1


def test_ws_unknown_match_is_closed_with_error(fresh):
    with fresh.websocket_connect("/ws/matches/nope") as ws:
        msg = ws.receive_json()
        assert msg["error"]["code"] == "MATCH_NOT_FOUND"
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
        assert exc.value.code == 4404
