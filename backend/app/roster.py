"""Roster scenarios, transfers/loans/releases and the immutable audit trail (spec 5.11, FR-2.2).

roster_leagues.state holds one league's squads, players and current registrations.
roster_audit is append-only; "current squad as of a date" is derived by replaying it.
"""
from datetime import date, timedelta

from app.core import ApiError, Checker, canonical, is_date, is_id, is_str, today, utc_now
from app.db import J, tx
from app.scoring import WRITE_LOCK
from app.sports import get_sport

ROLES = {"captain", "vice_captain", "starter", "substitute"}
TYPES = {"transfer", "loan", "release"}


# --- setup ------------------------------------------------------------------------------------------

def setup(body: dict) -> dict:
    c = Checker()
    lg = body.get("league")
    lg_ok = isinstance(lg, dict) and is_id(lg.get("league_id")) and is_id(lg.get("tenant_id")) \
        and is_id(lg.get("sport_id"))
    window = lg.get("transfer_window") if isinstance(lg, dict) else None
    if lg_ok:
        lg_ok = (isinstance(window, dict) and is_date(window.get("open")) and is_date(window.get("close"))
                 and window["open"] <= window["close"])
        mx = lg.get("max_squad_size")
        req = lg.get("required_positions")
        lg_ok = lg_ok and (mx is None or (isinstance(mx, int) and not isinstance(mx, bool) and mx >= 1)) \
            and (req is None or (isinstance(req, dict) and all(isinstance(v, int) and v >= 0 for v in req.values())))
    c.check(lg_ok, "league")
    squads = body.get("squads")
    sq_ok = isinstance(squads, list) and all(
        isinstance(s, dict) and is_id(s.get("squad_id")) and is_id(s.get("club_id")) and is_id(s.get("tenant_id"))
        for s in squads)
    if sq_ok:
        sq_ok = len({s["squad_id"] for s in squads}) == len(squads)
    c.check(sq_ok, "squads")
    players = body.get("players", [])
    squad_ids = {s["squad_id"] for s in squads} if sq_ok else set()
    pl_ok = isinstance(players, list) and all(
        isinstance(p, dict) and is_id(p.get("player_id")) and is_str(p.get("position"))
        and (p.get("squad_id") is None or p.get("squad_id") in squad_ids)
        and p.get("role", "substitute") in ROLES for p in players)
    if pl_ok:
        pl_ok = len({p["player_id"] for p in players}) == len(players)
    c.check(pl_ok, "players")
    mip = body.get("matches_in_progress", [])
    c.check(isinstance(mip, list) and all(isinstance(m, dict) and is_id(m.get("match_id")) for m in mip),
            "matches_in_progress")
    c.raise_if_any()

    with WRITE_LOCK, tx() as conn:
        sport = get_sport(conn, lg["sport_id"])
        if sport is None:
            raise ApiError(404, "SPORT_NOT_FOUND", f"Sport {lg['sport_id']} does not exist.",
                           {"sport_id": lg["sport_id"]})
        league_id = lg["league_id"]
        state = {
            "league": {
                "league_id": league_id, "tenant_id": lg["tenant_id"], "sport_id": lg["sport_id"],
                "transfer_window": {"open": window["open"], "close": window["close"]},
                "max_squad_size": lg.get("max_squad_size") or sport["roster"]["max_squad_size"],
                "required_positions": lg.get("required_positions")
                if lg.get("required_positions") is not None else sport["roster"]["required_positions"],
            },
            "squads": {s["squad_id"]: {"club_id": s["club_id"], "tenant_id": s["tenant_id"],
                                       "name": s.get("name", s["squad_id"])} for s in squads},
            "players": {p["player_id"]: {"name": p.get("name", p["player_id"]), "position": p["position"],
                                         "initial_squad_id": p.get("squad_id"),
                                         "initial_role": p.get("role", "substitute")} for p in players},
            "registrations": {p["player_id"]: _reg(p.get("squad_id"), None, "initial", None, None,
                                                   p.get("role", "substitute"))
                              for p in players if p.get("squad_id")},
            "matches_in_progress": [{"match_id": m["match_id"], "home_squad_id": m.get("home_squad_id"),
                                     "away_squad_id": m.get("away_squad_id")} for m in mip],
        }
        # Re-sending the same league replaces its scenario (and its history).
        conn.execute("DELETE FROM roster_audit WHERE league_id = %s", (league_id,))
        conn.execute("DELETE FROM roster_requests WHERE request->>'league_id' = %s", (league_id,))
        conn.execute(
            "INSERT INTO roster_leagues VALUES (%s, %s) ON CONFLICT (league_id) DO UPDATE SET state = EXCLUDED.state",
            (league_id, J(state)),
        )
    counts = {sid: 0 for sid in state["squads"]}
    for reg in state["registrations"].values():
        counts[reg["squad_id"]] += 1
    return {"league_id": league_id, "status": "configured", "squad_counts": counts}


def _reg(squad_id, parent, rtype, start, loan_end, role):
    return {"squad_id": squad_id, "parent_squad_id": parent, "registration_type": rtype,
            "start_date": start, "loan_end_date": loan_end, "role": role}


# --- transfers --------------------------------------------------------------------------------------

def validate_transfer(body: dict) -> dict:
    c = Checker()
    for f in ("request_id", "league_id", "player_id", "from_squad_id"):
        c.check(is_id(body.get(f)), f)
    t = body.get("type")
    c.check(t in TYPES, "type")
    if t != "release":
        c.check(is_id(body.get("to_squad_id")), "to_squad_id")
    c.check(is_date(body.get("effective_date")), "effective_date")
    if t == "loan":
        end = body.get("loan_end_date")
        c.check(is_date(end) and is_date(body.get("effective_date")) and end > body["effective_date"],
                "loan_end_date")
    c.check(is_str(body.get("reason")), "reason")
    c.check(is_str(body.get("requested_by")), "requested_by")
    c.raise_if_any()
    return {"request_id": body["request_id"], "league_id": body["league_id"], "player_id": body["player_id"],
            "type": t, "from_squad_id": body["from_squad_id"],
            "to_squad_id": body.get("to_squad_id") if t != "release" else None,
            "effective_date": body["effective_date"],
            "loan_end_date": body.get("loan_end_date") if t == "loan" else None,
            "reason": body["reason"], "requested_by": body["requested_by"]}


def transfer(body: dict, conn=None) -> tuple[int, dict]:
    req = validate_transfer(body)
    if conn is None:
        with WRITE_LOCK, tx() as own:
            return _transfer(own, req)
    return _transfer(conn, req)


def _transfer(conn, req) -> tuple[int, dict]:
    stored = conn.execute("SELECT request, response FROM roster_requests WHERE request_id = %s",
                          (req["request_id"],)).fetchone()
    if stored:
        if canonical(stored["request"]) == canonical(req):
            return 200, stored["response"]
        raise ApiError(409, "DUPLICATE_REQUEST_ID", "request_id was already used with a different body.",
                       {"request_id": req["request_id"]})

    row = conn.execute("SELECT state FROM roster_leagues WHERE league_id = %s FOR UPDATE",
                       (req["league_id"],)).fetchone()
    if row is None:
        raise ApiError(404, "LEAGUE_NOT_FOUND", f"League {req['league_id']} does not exist.",
                       {"league_id": req["league_id"]})
    state = row["state"]
    pid = req["player_id"]
    if pid not in state["players"]:
        raise ApiError(404, "PLAYER_NOT_FOUND", f"Player {pid} does not exist.", {"player_id": pid})
    for sq in (req["from_squad_id"], req["to_squad_id"]):
        if sq is not None and sq not in state["squads"]:
            raise ApiError(404, "SQUAD_NOT_FOUND", f"Squad {sq} does not exist.", {"squad_id": sq})
    tenant = state["league"]["tenant_id"]
    for sq in (req["from_squad_id"], req["to_squad_id"]):
        if sq is not None and state["squads"][sq]["tenant_id"] != tenant:
            raise ApiError(409, "CROSS_TENANT_TRANSFER", "Both squads must belong to the league's tenant.",
                           {"squad_id": sq, "tenant_id": tenant})

    _materialize_returns(conn, state, req["effective_date"])
    reg = state["registrations"].get(pid)
    current = reg["squad_id"] if reg else None
    if current != req["from_squad_id"]:
        raise ApiError(409, "NOT_IN_SQUAD", f"Player {pid} is not in squad {req['from_squad_id']}.",
                       {"player_id": pid, "squad_id": req["from_squad_id"], "current_squad_id": current})
    win = state["league"]["transfer_window"]
    if req["type"] != "release" and not (win["open"] <= req["effective_date"] <= win["close"]):
        raise ApiError(409, "TRANSFER_WINDOW_CLOSED", "The transfer window is closed on that date.",
                       {"effective_date": req["effective_date"], "transfer_window": win})
    if reg and reg["registration_type"] == "loan":
        raise ApiError(409, "PLAYER_ON_LOAN", f"Player {pid} is currently on loan.", {"player_id": pid})
    if req["type"] != "release":
        size = _squad_size(state, req["to_squad_id"])
        if size + 1 > state["league"]["max_squad_size"]:
            raise ApiError(409, "SQUAD_FULL", f"Squad {req['to_squad_id']} is full.",
                           {"squad_id": req["to_squad_id"], "max_squad_size": state["league"]["max_squad_size"]})
    position = state["players"][pid]["position"]
    required = state["league"]["required_positions"].get(position)
    if required is not None:
        remaining = sum(1 for p, r in state["registrations"].items()
                        if r["squad_id"] == req["from_squad_id"] and state["players"][p]["position"] == position) - 1
        if remaining < required:
            raise ApiError(409, "MIN_POSITION_VIOLATION",
                           f"Squad {req['from_squad_id']} would have fewer than {required} {position}.",
                           {"squad_id": req["from_squad_id"], "position": position, "required": required})

    blocking = next((m["match_id"] for m in state["matches_in_progress"]
                     if req["from_squad_id"] in (m["home_squad_id"], m["away_squad_id"])), None)
    move_state = "deferred_until_match_end" if blocking else "active"
    if req["type"] == "transfer":
        new_reg = _reg(req["to_squad_id"], None, "transfer", req["effective_date"], None, "substitute")
    elif req["type"] == "loan":
        new_reg = _reg(req["to_squad_id"], req["from_squad_id"], "loan", req["effective_date"],
                       req["loan_end_date"], "substitute")
    else:
        new_reg = None
    if new_reg is None:
        state["registrations"].pop(pid, None)
    else:
        state["registrations"][pid] = new_reg
    entry = _audit(conn, {
        "action": req["type"], "player_id": pid, "league_id": req["league_id"],
        "from_squad_id": req["from_squad_id"], "to_squad_id": req["to_squad_id"],
        "effective_date": req["effective_date"], "state": move_state, "who": req["requested_by"],
        "when": utc_now(), "why": req["reason"],
    })
    conn.execute("UPDATE roster_leagues SET state = %s WHERE league_id = %s", (J(state), req["league_id"]))
    registration = None if new_reg is None else {"player_id": pid, "league_id": req["league_id"], **new_reg}
    response = {"request_id": req["request_id"], "status": "accepted", "state": move_state,
                "blocking_match_id": blocking, "registration": registration, "audit_entry": entry}
    conn.execute("INSERT INTO roster_requests VALUES (%s, %s, 201, %s)", (req["request_id"], J(req), J(response)))
    return 201, response


def _squad_size(state, squad_id):
    return sum(1 for r in state["registrations"].values() if r["squad_id"] == squad_id)


def _audit(conn, entry: dict) -> dict:
    seq = conn.execute("SELECT count(*) AS n FROM roster_audit").fetchone()["n"] + 1
    audit_id = f"au-{seq:04d}"
    while conn.execute("SELECT 1 FROM roster_audit WHERE audit_id = %s", (audit_id,)).fetchone():
        seq += 1
        audit_id = f"au-{seq:04d}"
    full = {"audit_id": audit_id, **entry}
    conn.execute("INSERT INTO roster_audit (audit_id, player_id, league_id, entry) VALUES (%s, %s, %s, %s)",
                 (audit_id, entry["player_id"], entry["league_id"], J(full)))
    return full


def _materialize_returns(conn, state, as_of: str) -> bool:
    """Writes each due loan_return exactly once (the day after loan_end_date). Returns True if any."""
    changed = False
    for pid, reg in list(state["registrations"].items()):
        if reg["registration_type"] != "loan" or not reg["loan_end_date"]:
            continue
        return_day = (date.fromisoformat(reg["loan_end_date"]) + timedelta(days=1)).isoformat()
        if as_of >= return_day:
            _audit(conn, {"action": "loan_return", "player_id": pid, "league_id": state["league"]["league_id"],
                          "from_squad_id": reg["squad_id"], "to_squad_id": reg["parent_squad_id"],
                          "effective_date": return_day, "state": "active", "who": "system",
                          "when": utc_now(), "why": "Loan period ended"})
            state["registrations"][pid] = _reg(reg["parent_squad_id"], None, "loan_return", return_day, None,
                                               "substitute")
            changed = True
    return changed


def player_audit_count(conn, player_id) -> int:
    return conn.execute("SELECT count(*) AS n FROM roster_audit WHERE player_id = %s", (player_id,)).fetchone()["n"]


def _league_of_player(conn, player_id):
    rows = conn.execute("SELECT league_id, state FROM roster_leagues").fetchall()
    for row in rows:
        if player_id in row["state"]["players"]:
            return row
    return None


def history(player_id: str, as_of: str | None) -> dict:
    if as_of is not None and not is_date(as_of):
        raise ApiError(400, "VALIDATION_ERROR", "as_of must be YYYY-MM-DD.", {"fields": ["as_of"]})
    as_of = as_of or today()
    with WRITE_LOCK, tx() as conn:
        row = _league_of_player(conn, player_id)
        if row is None:
            raise ApiError(404, "PLAYER_NOT_FOUND", f"Player {player_id} does not exist.", {"player_id": player_id})
        conn.execute("SELECT 1 FROM roster_leagues WHERE league_id = %s FOR UPDATE", (row["league_id"],))
        state = row["state"]
        if _materialize_returns(conn, state, as_of):
            conn.execute("UPDATE roster_leagues SET state = %s WHERE league_id = %s", (J(state), row["league_id"]))
        entries = [r["entry"] for r in conn.execute(
            "SELECT entry FROM roster_audit WHERE player_id = %s ORDER BY seq", (player_id,)).fetchall()]
    squad = state["players"][player_id]["initial_squad_id"]
    parent = None
    for e in entries:
        if e["effective_date"] > as_of:
            continue
        if e["action"] == "release":
            squad, parent = None, None
        elif e["action"] == "loan":
            squad, parent = e["to_squad_id"], e["from_squad_id"]
        else:  # transfer, loan_return
            squad, parent = e["to_squad_id"], None
    return {"player_id": player_id, "as_of": as_of, "league_id": state["league"]["league_id"],
            "current_squad_id": squad, "parent_squad_id": parent, "history": entries}
