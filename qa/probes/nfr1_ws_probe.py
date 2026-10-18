"""Part II NFR-1 probe: 25 concurrent WebSocket clients, one score event, p95 delivery < 500 ms.

Posts a real score event, so run it only against a test stack:
  qa/.venv/Scripts/python qa/probes/nfr1_ws_probe.py http://127.0.0.1:18080
"""
import asyncio
import json
import statistics
import sys
import time
import urllib.request
import uuid

import websockets

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:18080").rstrip("/")
WS = BASE.replace("http", "ws", 1) + "/ws/matches/match-m1"
CLIENTS = 25


def post_goal():
    body = {"event_id": f"ws-probe-{uuid.uuid4().hex[:10]}", "match_id": "match-m1", "type": "score",
            "payload": {"team_id": "club-alpha-1", "event_type": "goal"}}
    req = urllib.request.Request(BASE + "/audit/v1/events", data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as r:
        assert r.status == 201


def gauge():
    with urllib.request.urlopen(BASE + "/metrics", timeout=5) as r:
        line = next(x for x in r.read().decode().splitlines() if x.startswith("nascon_active_ws_connections "))
    return int(line.split()[1])


async def client(ready, go, arrivals):
    async with websockets.connect(WS) as ws:
        first = json.loads(await ws.recv())
        ready.append(first["version"])
        await go.wait()
        while True:
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            if msg["version"] > first["version"]:
                arrivals.append(time.perf_counter())
                return


async def main():
    ready, arrivals, go = [], [], asyncio.Event()
    tasks = [asyncio.create_task(client(ready, go, arrivals)) for _ in range(CLIENTS)]
    while len(ready) < CLIENTS:
        await asyncio.sleep(0.02)
    connected = gauge()
    t0 = time.perf_counter()
    await asyncio.to_thread(post_goal)
    go.set()
    await asyncio.gather(*tasks)
    lat = sorted((a - t0) * 1000 for a in arrivals)
    p95 = lat[int(0.95 * len(lat)) - 1]
    print(f"clients={len(lat)} gauge_during={connected} median={statistics.median(lat):.1f}ms "
          f"p95={p95:.1f}ms max={lat[-1]:.1f}ms")
    assert len(lat) == CLIENTS and connected >= CLIENTS
    assert p95 < 500, f"p95 {p95:.1f} ms >= 500 ms"
    print("NFR-1 probe PASSED")


asyncio.run(main())
