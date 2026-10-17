"""Event-sourced match scoring (spec 5.8, 5.9).

The events table is append-only. Every read rebuilds the score from the log; corrections are new
signed `compensation` events. All rules come from the sport's JSON config - no sport/event names here.
"""
import threading

from app.core import ApiError, Checker, canonical, is_id, is_int, is_str, sign, validation_error
from app.db import J, tx
from app.seed import current_seed
from app.sports import TIE_BREAK_TOKENS, get_sport

# One writer at a time for event streams, rosters and offline sync (single API process).
WRITE_LOCK = threading.RLock()

EVENT_TYPES = {"match_init", "match_start", "score", "discipline", "tiebreak_winner", "match_end", "compensation"}
COMPENSABLE = {"score", "discipline", "tiebreak_winner"}


# --- leagues (5.8) ---------------------------------------------------------------------------------

def register_league(body: dict) -> dict:
    c = Checker()
    league_id, sport_id = body.get("league_id"), body.get("sport_id")
    c.check(is_id(league_id), "league_id")
    c.check(is_id(sport_id), "sport_id")
    teams = body.get("teams")
    teams_ok = (isinstance(teams, list) and all(is_id(t) for t in teams)
                and len(set(teams)) == len(teams) and 2 <= len(teams) <= 40)
    c.check(teams_ok, "teams")
    fixtures = body.get("fixtures")
    fx_ok = isinstance(fixtures, list) and all(isinstance(f, dict) for f in fixtures)
    if fx_ok:
        for f in fixtures:
            if not (is_id(f.get("match_id")) and is_id(f.get("home")) and is_id(f.get("away"))
                    and f.get("home") != f.get("away")
                    and (not teams_ok or (f.get("home") in teams and f.get("away") in teams))):
                fx_ok = False
                break
    c.check(fx_ok, "fixtures")
    points = body.get("points") or {}
    c.check(isinstance(points, dict) and all(is_int(points.get(k, 0)) for k in ("win", "draw", "loss")), "points")
    order = body.get("tie_break_order")
    if order is not None:
        c.check(isinstance(order, list) and all(t in TIE_BREAK_TOKENS for t in order)
                and len(set(order)) == len(order), "tie_break_order")
    qual = body.get("qualification")
    spots = qual.get("spots") if isinstance(qual, dict) else None
    c.check(is_int(spots) and 1 <= spots <= (len(teams) if teams_ok else 40), "qualification")
    lots_seed = body.get("lots_seed")
    c.check(lots_seed is None or is_int(lots_seed), "lots_seed")
    c.raise_if_any()

    with WRITE_LOCK, tx() as conn:
        sport = get_sport(conn, sport_id)
        if sport is None:
            raise ApiError(404, "SPORT_NOT_FOUND", f"Sport {sport_id} does not exist.", {"sport_id": sport_id})
        if conn.execute("SELECT 1 FROM standings_leagues WHERE league_id = %s", (league_id,)).fetchone():
            raise ApiError(409, "LEAGUE_EXISTS", f"League {league_id} already exists.", {"league_id": league_id})
        seen = set()
        for f in fixtures:
            mid = f["match_id"]
            if mid in seen or conn.execute("SELECT 1 FROM matches WHERE match_id = %s", (mid,)).fetchone():
                raise ApiError(409, "MATCH_EXISTS", f"Match {mid} already exists.", {"match_id": mid})
            seen.add(mid)
        config = {
            "league_id": league_id, "sport_id": sport_id, "teams": teams,
            "fixtures": [{"match_id": f["match_id"], "home": f["home"], "away": f["away"]} for f in fixtures],
            "points": {"win": points.get("win", 3), "draw": points.get("draw", 1), "loss": points.get("loss", 0)},
            "tie_break_order": order if order is not None else sport["tie_break_order"],
            "spots": spots,
            "lots_seed": lots_seed if lots_seed is not None else current_seed(conn),
        }
        conn.execute("INSERT INTO standings_leagues VALUES (%s, %s)", (league_id, J(config)))
        for f in fixtures:
            conn.execute(
                "INSERT INTO matches (match_id, sport_id, league_id, home_team_id, away_team_id, origin) "
                "VALUES (%s, %s, %s, %s, %s, 'league')",
                (f["match_id"], sport_id, league_id, f["home"], f["away"]),
            )
    return {"league_id": league_id, "status": "created", "team_count": len(teams), "fixture_count": len(fixtures)}


# --- projection --------------------------------------------------------------------------------------

def load_events(conn, match_id):
    return conn.execute(
        "SELECT sequence, event_id, type, payload, signature FROM events WHERE match_id = %s ORDER BY sequence",
        (match_id,),
    ).fetchall()


def project(match: dict, sport: dict, events: list[dict]) -> dict:
    """Rebuilds the match state from its event log."""
    compensated_by = {}
    for e in events:
        if e["type"] == "compensation":
            compensated_by[e["payload"]["compensates"]] = e["event_id"]
    home, away = match["home_team_id"], match["away_team_id"]
    model = sport["scoring_model"]
    defs = sport["scoring_events"]
    side = {home: _blank(), away: _blank()}
    status = "upcoming"
    tiebreak = None
    for e in events:
        t, p = e["type"], e["payload"]
        if t == "match_start":
            status = "in_progress"
        elif t == "match_end":
            status = "completed"
        if e["event_id"] in compensated_by or t == "compensation":
            continue  # compensated events and compensations are neutral
        if t == "score":
            s = side[p["team_id"]]
            d = defs[p["event_type"]]
            if model == "event":
                s["score"] += d["points"]
            elif model == "innings":
                s["score"] += d["runs"]
                s["balls"] += 1 if d["legal_ball"] else 0
                s["wickets"] += 1 if d["wicket"] else 0
            else:
                s["score"] += d["rounds"]
        elif t == "discipline":
            side[p["team_id"]]["fair_play"] += p["points"]
        elif t == "tiebreak_winner":
            tiebreak = p["team_id"]
    hs, as_ = side[home]["score"], side[away]["score"]
    if hs != as_:
        winner = home if hs > as_ else away
    else:
        winner = tiebreak
    if status != "completed":
        outcome = "pending"
    elif winner is not None:
        outcome = "home_win" if winner == home else "away_win"
    elif sport["draw_allowed"]:
        outcome = "draw"
    else:
        outcome = "undecided"
    return {"status": status, "outcome": outcome, "winner": winner, "tiebreak": tiebreak,
            "side": side, "compensated_by": compensated_by}


def _blank():
    return {"score": 0, "wickets": 0, "balls": 0, "fair_play": 0}


def _side_out(team_id, s, sport):
    innings = sport["scoring_model"] == "innings"
    bpo = sport["periods"].get("balls_per_over", 6) if innings else None
    return {
        "team_id": team_id,
        "score": s["score"],
        "wickets": s["wickets"] if innings else None,
        "balls": s["balls"] if innings else None,
        "overs": f"{s['balls'] // bpo}.{s['balls'] % bpo}" if innings else None,
        "fair_play": s["fair_play"],
    }


def score_view(match_id: str) -> dict:
    with tx() as conn:
        match = conn.execute("SELECT * FROM matches WHERE match_id = %s", (match_id,)).fetchone()
        if match is None:
            raise ApiError(404, "MATCH_NOT_FOUND", f"Match {match_id} does not exist.", {"match_id": match_id})
        sport = get_sport(conn, match["sport_id"])
        events = load_events(conn, match_id)
    state = project(match, sport, events)
    return {
        "match_id": match_id, "sport_id": match["sport_id"], "league_id": match["league_id"],
        "status": state["status"], "outcome": state["outcome"],
        "winner_team_id": state["winner"], "tiebreak_winner_team_id": state["tiebreak"],
        "home": _side_out(match["home_team_id"], state["side"][match["home_team_id"]], sport),
        "away": _side_out(match["away_team_id"], state["side"][match["away_team_id"]], sport),
        "version": len(events),
        "events": [
            {"sequence": e["sequence"], "event_id": e["event_id"], "type": e["type"], "payload": e["payload"],
             "signature": e["signature"], "compensated": e["event_id"] in state["compensated_by"],
             "compensated_by": state["compensated_by"].get(e["event_id"])}
            for e in events
        ],
    }


# --- appending events (5.9) ------------------------------------------------------------------------

def validate_event(body: dict) -> dict:
    c = Checker()
    c.check(is_id(body.get("event_id")), "event_id")
    c.check(is_id(body.get("match_id")), "match_id")
    etype = body.get("type")
    c.check(etype in EVENT_TYPES, "type")
    p = body.get("payload")
    if not isinstance(p, dict):
        c.check(False, "payload")
    elif etype == "match_init":
        ok = (is_id(p.get("sport_id")) and is_id(p.get("home_team_id")) and is_id(p.get("away_team_id"))
              and p.get("home_team_id") != p.get("away_team_id")
              and (p.get("league_id") is None or is_id(p.get("league_id"))))
        c.check(ok, "payload")
    elif etype == "score":
        c.check(is_id(p.get("team_id")) and is_str(p.get("event_type")), "payload")
    elif etype == "discipline":
        c.check(is_id(p.get("team_id")) and is_int(p.get("points")), "payload")
    elif etype == "tiebreak_winner":
        c.check(is_id(p.get("team_id")), "payload")
    elif etype == "compensation":
        c.check(is_id(p.get("compensates")) and is_str(p.get("reason")), "payload")
    c.raise_if_any()
    return {"event_id": body["event_id"], "match_id": body["match_id"], "type": etype, "payload": p}


def append_event(body: dict, conn=None) -> tuple[int, dict]:
    """Returns (http_status, response). Raises ApiError on rejection."""
    req = validate_event(body)
    if conn is None:
        with WRITE_LOCK, tx() as own:
            return _append(own, req)
    return _append(conn, req)


def _append(conn, req) -> tuple[int, dict]:
    event_id, match_id, etype, p = req["event_id"], req["match_id"], req["type"], req["payload"]

    existing = conn.execute("SELECT match_id, request FROM events WHERE event_id = %s", (event_id,)).fetchone()
    if existing:
        if canonical(existing["request"]) == canonical(req):
            return 200, _stored_response(conn, event_id)
        raise ApiError(409, "DUPLICATE_EVENT_ID", f"Event {event_id} was already used with a different body.",
                       {"event_id": event_id})

    match = conn.execute("SELECT * FROM matches WHERE match_id = %s FOR UPDATE", (match_id,)).fetchone()
    if etype == "match_init":
        sport = get_sport(conn, p["sport_id"])
        if sport is None:
            raise ApiError(404, "SPORT_NOT_FOUND", f"Sport {p['sport_id']} does not exist.",
                           {"sport_id": p["sport_id"]})
        if match is not None:
            raise ApiError(409, "MATCH_EXISTS", f"Match {match_id} already exists.", {"match_id": match_id})
        conn.execute(
            "INSERT INTO matches (match_id, sport_id, league_id, home_team_id, away_team_id, origin) "
            "VALUES (%s, %s, %s, %s, %s, 'init')",
            (match_id, p["sport_id"], p.get("league_id"), p["home_team_id"], p["away_team_id"]),
        )
        return 201, _insert(conn, req, [])

    if match is None:
        raise ApiError(404, "MATCH_NOT_FOUND", f"Match {match_id} does not exist.", {"match_id": match_id})
    sport = get_sport(conn, match["sport_id"])
    events = load_events(conn, match_id)
    state = project(match, sport, events)
    teams = (match["home_team_id"], match["away_team_id"])

    if etype == "compensation":
        target = conn.execute("SELECT match_id, event_id, type FROM events WHERE event_id = %s",
                              (p["compensates"],)).fetchone()
        if target is None:
            raise ApiError(404, "EVENT_NOT_FOUND", f"Event {p['compensates']} does not exist.",
                           {"event_id": p["compensates"]})
        if (target["match_id"] != match_id or target["type"] not in COMPENSABLE
                or target["event_id"] in state["compensated_by"]):
            raise ApiError(409, "INVALID_COMPENSATION", "This event cannot be compensated.",
                           {"event_id": p["compensates"]})
        return 201, _insert(conn, req, events)

    if etype in ("score", "discipline", "tiebreak_winner") and p["team_id"] not in teams:
        raise validation_error(["payload"], "team_id must be the home or away team.")
    if etype == "score" and p["event_type"] not in sport["scoring_events"]:
        raise ApiError(400, "UNKNOWN_EVENT_TYPE", f"Event type {p['event_type']} is not defined for this sport.",
                       {"event_type": p["event_type"]})

    status = state["status"]
    if etype == "match_start":
        if status != "upcoming":
            raise ApiError(409, "ILLEGAL_TRANSITION", f"Cannot start a match that is {status}.",
                           {"match_id": match_id, "status": status})
    elif etype == "match_end":
        if status != "in_progress":
            raise ApiError(409, "ILLEGAL_TRANSITION", f"Cannot end a match that is {status}.",
                           {"match_id": match_id, "status": status})
        side = state["side"]
        level = side[teams[0]]["score"] == side[teams[1]]["score"]
        if level and not sport["draw_allowed"] and state["tiebreak"] is None:
            raise ApiError(409, "TIE_NOT_ALLOWED", "Scores are level and this sport does not allow draws.",
                           {"match_id": match_id})
    else:  # score, discipline, tiebreak_winner
        if status != "in_progress":
            raise ApiError(409, "MATCH_NOT_IN_PROGRESS", f"Match is {status}.", {"match_id": match_id})
        if etype == "score":
            _check_limits(sport, state, p["team_id"], match_id)
    return 201, _insert(conn, req, events)


def _check_limits(sport, state, team_id, match_id):
    periods = sport["periods"]
    if sport["scoring_model"] == "innings":
        s = state["side"][team_id]
        max_balls = periods["innings_per_team"] * periods["overs_per_innings"] * periods["balls_per_over"]
        max_wkts = periods["innings_per_team"] * periods["wickets_per_innings"]
        if s["balls"] >= max_balls or s["wickets"] >= max_wkts:
            raise ApiError(409, "INNINGS_COMPLETE", "This team's innings is complete.",
                           {"match_id": match_id, "team_id": team_id})
    elif sport["scoring_model"] == "round":
        needed = (periods["best_of"] + 1) // 2
        if any(s["score"] >= needed for s in state["side"].values()):
            raise ApiError(409, "SERIES_ALREADY_DECIDED", "The series is already decided.", {"match_id": match_id})


def _insert(conn, req, events) -> dict:
    sequence = len(events) + 1
    signature = sign(req["event_id"], req["payload"])
    conn.execute(
        "INSERT INTO events (match_id, sequence, event_id, type, payload, request, signature) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (req["match_id"], sequence, req["event_id"], req["type"], J(req["payload"]), J(req), signature),
    )
    return {"event_id": req["event_id"], "match_id": req["match_id"], "type": req["type"],
            "sequence": sequence, "match_version": sequence, "signature": signature}


def _stored_response(conn, event_id) -> dict:
    e = conn.execute("SELECT match_id, sequence, type, signature FROM events WHERE event_id = %s",
                     (event_id,)).fetchone()
    return {"event_id": event_id, "match_id": e["match_id"], "type": e["type"], "sequence": e["sequence"],
            "match_version": e["sequence"], "signature": e["signature"]}


def match_version(conn, match_id) -> int:
    row = conn.execute("SELECT count(*) AS n FROM events WHERE match_id = %s", (match_id,)).fetchone()
    return row["n"]
