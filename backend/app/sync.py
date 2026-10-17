"""POST /audit/v1/offline-sync (spec 5.14): replay actions a device queued while offline."""
from app import roster, scoring
from app.core import ApiError, Checker, canonical, is_id, is_int, is_timestamp
from app.db import J, tx

ACTION_TYPES = {"score_event", "roster_transfer"}


def validate(body: dict):
    c = Checker()
    c.check(is_id(body.get("device_id")), "device_id")
    actions = body.get("actions")
    ok = isinstance(actions, list) and 1 <= len(actions) <= 100
    if ok:
        for a in actions:
            if not (isinstance(a, dict) and is_id(a.get("action_id")) and a.get("type") in ACTION_TYPES
                    and is_timestamp(a.get("queued_at")) and is_int(a.get("base_version"))
                    and a["base_version"] >= 0 and isinstance(a.get("payload"), dict)):
                ok = False
                break
    c.check(ok, "actions")
    c.raise_if_any()


def sync(body: dict) -> dict:
    validate(body)
    device = body["device_id"]
    actions = body["actions"]
    order = sorted(range(len(actions)), key=lambda i: (actions[i]["queued_at"], i))
    results: list[dict | None] = [None] * len(actions)
    with scoring.WRITE_LOCK, tx() as conn:
        for processed, idx in enumerate(order, 1):
            action = actions[idx]
            result = _process(conn, device, action)
            result["processed_order"] = processed
            results[idx] = {"action_id": action["action_id"], **result}
            if result["status"] != "duplicate" or not _seen(conn, device, action["action_id"]):
                conn.execute("INSERT INTO sync_actions VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                             (device, action["action_id"], J(results[idx])))
    summary = {"applied": 0, "rejected": 0, "duplicate": 0}
    for r in results:
        summary[r["status"]] += 1
    return {"device_id": device, "results": results, "summary": summary}


def _seen(conn, device, action_id):
    return conn.execute("SELECT 1 FROM sync_actions WHERE device_id = %s AND action_id = %s",
                        (device, action_id)).fetchone() is not None


def _result(status, resolution, code, version, signature=None):
    order_key = {"status": status, "resolution": resolution, "error_code": code}
    return {**order_key, "server_version": version, "signature": signature}


def _process(conn, device, action) -> dict:
    kind, base, payload = action["type"], action["base_version"], action["payload"]
    version = _version(conn, kind, payload)
    if _seen(conn, device, action["action_id"]):
        return _result("duplicate", "skipped_duplicate", None, version)
    try:
        with conn.transaction():  # savepoint: a rejected action leaves no trace
            if kind == "score_event":
                req = scoring.validate_event(payload)
                same = conn.execute("SELECT request FROM events WHERE event_id = %s", (req["event_id"],)).fetchone()
                if same and canonical(same["request"]) == canonical(req):
                    return _result("duplicate", "skipped_duplicate", None, version)
                if req["type"] != "match_init" and not same:
                    if conn.execute("SELECT 1 FROM matches WHERE match_id = %s", (req["match_id"],)).fetchone() is None:
                        raise ApiError(404, "MATCH_NOT_FOUND", "Match does not exist.")
                if base > version:
                    return _result("rejected", "server_wins", "INVALID_BASE_VERSION", version)
                _, resp = scoring._append(conn, req)
                new_version = scoring.match_version(conn, req["match_id"])
                return _result("applied", "appended" if base == version else "rebased_append", None,
                               new_version, resp["signature"])
            req = roster.validate_transfer(payload)
            _check_roster_ids(conn, req)
            if base > version:
                return _result("rejected", "server_wins", "INVALID_BASE_VERSION", version)
            status, _ = roster._transfer(conn, req)
            if status == 200:
                return _result("duplicate", "skipped_duplicate", None, version)
            new_version = roster.player_audit_count(conn, req["player_id"])
            return _result("applied", "appended" if base == version else "rebased_append", None, new_version)
    except ApiError as e:
        return _result("rejected", "server_wins", e.code, version)


def _version(conn, kind, payload) -> int:
    if kind == "score_event":
        mid = payload.get("match_id")
        return scoring.match_version(conn, mid) if isinstance(mid, str) else 0
    pid = payload.get("player_id")
    return roster.player_audit_count(conn, pid) if isinstance(pid, str) else 0


def _check_roster_ids(conn, req):
    row = conn.execute("SELECT state FROM roster_leagues WHERE league_id = %s", (req["league_id"],)).fetchone()
    if row is None:
        raise ApiError(404, "LEAGUE_NOT_FOUND", "League does not exist.")
    state = row["state"]
    if req["player_id"] not in state["players"]:
        raise ApiError(404, "PLAYER_NOT_FOUND", "Player does not exist.")
    for sq in (req["from_squad_id"], req["to_squad_id"]):
        if sq is not None and sq not in state["squads"]:
            raise ApiError(404, "SQUAD_NOT_FOUND", "Squad does not exist.")
