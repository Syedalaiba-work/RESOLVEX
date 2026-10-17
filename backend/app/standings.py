"""GET /audit/v1/standings/{league_id} (spec 5.10) - recomputed from the event logs on every call."""
from app.core import ApiError, lots_key
from app.db import tx
from app.scoring import load_events, project
from app.sports import effective_tie_break_order, get_sport


def standings(league_id: str) -> dict:
    with tx() as conn:
        row = conn.execute("SELECT config FROM standings_leagues WHERE league_id = %s", (league_id,)).fetchone()
        if row is None:
            raise ApiError(404, "LEAGUE_NOT_FOUND", f"League {league_id} does not exist.", {"league_id": league_id})
        cfg = row["config"]
        sport = get_sport(conn, cfg["sport_id"])
        results = []  # one entry per played match
        remaining = {t: 0 for t in cfg["teams"]}
        for f in cfg["fixtures"]:
            match = conn.execute("SELECT * FROM matches WHERE match_id = %s", (f["match_id"],)).fetchone()
            state = project(match, sport, load_events(conn, f["match_id"]))
            if state["status"] == "completed" and state["outcome"] != "undecided":
                results.append(_result(match, state, sport))
            else:
                remaining[f["home"]] += 1
                remaining[f["away"]] += 1
    return compute_table(cfg, sport, results, remaining)


def _result(match, state, sport):
    home, away = match["home_team_id"], match["away_team_id"]
    hs, as_ = state["side"][home], state["side"][away]
    return {
        "home": home, "away": away, "winner": state["winner"] if state["outcome"] != "draw" else None,
        "score": {home: hs["score"], away: as_["score"]},
        "overs": {home: _overs_faced(hs, sport), away: _overs_faced(as_, sport)},
        "fair_play": {home: hs["fair_play"], away: as_["fair_play"]},
    }


def _overs_faced(side, sport):
    if sport["scoring_model"] != "innings":
        return 0.0
    p = sport["periods"]
    if side["wickets"] >= p["wickets_per_innings"] * p["innings_per_team"]:
        return float(p["overs_per_innings"] * p["innings_per_team"])  # all out -> full quota
    return side["balls"] / p["balls_per_over"]


def _aggregate(team, matches, points_cfg, model):
    agg = {"played": 0, "won": 0, "drawn": 0, "lost": 0, "scored": 0, "conceded": 0, "points": 0,
           "fair_play": 0, "overs_faced": 0.0, "overs_bowled": 0.0}
    for m in matches:
        if team not in (m["home"], m["away"]):
            continue
        opp = m["away"] if team == m["home"] else m["home"]
        agg["played"] += 1
        agg["scored"] += m["score"][team]
        agg["conceded"] += m["score"][opp]
        agg["fair_play"] += m["fair_play"][team]
        agg["overs_faced"] += m["overs"][team]
        agg["overs_bowled"] += m["overs"][opp]
        if m["winner"] is None:
            agg["drawn"] += 1
            agg["points"] += points_cfg["draw"]
        elif m["winner"] == team:
            agg["won"] += 1
            agg["points"] += points_cfg["win"]
        else:
            agg["lost"] += 1
            agg["points"] += points_cfg["loss"]
    agg["diff"] = _diff(agg, model)
    return agg


def _diff(agg, model):
    if model != "innings":
        return agg["scored"] - agg["conceded"]
    rate_for = agg["scored"] / agg["overs_faced"] if agg["overs_faced"] else 0.0
    rate_against = agg["conceded"] / agg["overs_bowled"] if agg["overs_bowled"] else 0.0
    return round(rate_for - rate_against, 3)


def compute_table(cfg, sport, results, remaining) -> dict:
    model = sport["scoring_model"]
    teams = cfg["teams"]
    pts_cfg = cfg["points"]
    overall = {t: _aggregate(t, results, pts_cfg, model) for t in teams}
    order = effective_tie_break_order(cfg["tie_break_order"])
    seed, league_id = cfg["lots_seed"], cfg["league_id"]

    def criterion(name, group):
        if name in ("h2h_points", "h2h_diff"):
            members = set(group)
            mini = [m for m in results if m["home"] in members and m["away"] in members]
            vals = {t: _aggregate(t, mini, pts_cfg, model) for t in group}
            return {t: vals[t]["points" if name == "h2h_points" else "diff"] for t in group}
        if name == "overall_diff":
            return {t: overall[t]["diff"] for t in group}
        if name == "scored":
            return {t: overall[t]["scored"] for t in group}
        if name == "fair_play":
            return {t: overall[t]["fair_play"] for t in group}
        # draw_lots: ascending hash is best -> negate ordering by using the key itself (lower first)
        return {t: lots_key(seed, league_id, t) for t in group}

    split_by = {}  # (upper_team, lower_team) adjacent pair -> criterion that separated them

    def resolve(group):
        if len(group) == 1:
            return group
        for name in order:
            values = criterion(name, group)
            distinct = sorted(set(values.values()), reverse=(name != "draw_lots"))
            if len(distinct) == 1:
                continue
            ordered = []
            subgroups = [[t for t in group if values[t] == v] for v in distinct]
            for i, sub in enumerate(subgroups):
                resolved = resolve(sorted(sub)) if len(sub) > 1 else sub
                if ordered:
                    split_by[(ordered[-1], resolved[0])] = name
                ordered.extend(resolved)
            return ordered
        return sorted(group)  # unreachable: draw_lots always separates distinct team ids

    by_points = {}
    for t in teams:
        by_points.setdefault(overall[t]["points"], []).append(t)
    final = []
    for pts in sorted(by_points, reverse=True):
        final.extend(resolve(sorted(by_points[pts])))

    w = pts_cfg["win"]
    k = cfg["spots"]
    max_pts = {t: overall[t]["points"] + w * remaining[t] for t in teams}
    table = []
    for i, t in enumerate(final):
        nxt = final[i + 1] if i + 1 < len(final) else None
        resolved_by = split_by.get((t, nxt)) if nxt and overall[nxt]["points"] == overall[t]["points"] else None
        others = [x for x in teams if x != t]
        if sum(1 for x in others if max_pts[x] >= overall[t]["points"]) < k:
            status = "clinched"
        elif sum(1 for x in others if overall[x]["points"] > max_pts[t]) >= k:
            status = "eliminated"
        else:
            status = "still_possible"
        a = overall[t]
        table.append({
            "rank": i + 1, "team_id": t, "played": a["played"], "won": a["won"], "drawn": a["drawn"],
            "lost": a["lost"], "scored": a["scored"], "conceded": a["conceded"], "diff": a["diff"],
            "points": a["points"], "fair_play": a["fair_play"], "status": status, "resolved_by": resolved_by,
        })

    h2h = {}
    for a in teams:
        h2h[a] = {}
        for b in teams:
            if a == b:
                continue
            pair = [m for m in results if {m["home"], m["away"]} == {a, b}]
            agg = _aggregate(a, pair, pts_cfg, model)
            h2h[a][b] = {"played": agg["played"], "points": agg["points"], "scored": agg["scored"],
                         "conceded": agg["conceded"]}
    return {"league_id": cfg["league_id"], "sport_id": cfg["sport_id"], "qualification_spots": k,
            "table": table, "h2h": h2h}
