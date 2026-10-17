import os
import itertools

import pytest

from app.core import lots_key, sign
from conftest import err

SALT = os.environ["DAY1_SALT"]  # the same salt the API reads from the environment


def ev(client, event_id, match_id, etype, payload=None):
    return client.post("/audit/v1/events", json={"event_id": event_id, "match_id": match_id, "type": etype,
                                                 "payload": payload or {}})


def init(client, mid, sport="football", home="t1", away="t2", **extra):
    payload = {"sport_id": sport, "home_team_id": home, "away_team_id": away, **extra}
    return ev(client, f"{mid}-init", mid, "match_init", payload)


_n = itertools.count(1)


def nid():
    return f"e{next(_n)}"


def play(client, mid, scores, end=True):
    """scores: list of (team, event_type)."""
    assert ev(client, nid(), mid, "match_start").status_code == 201
    for team, etype in scores:
        r = ev(client, nid(), mid, "score", {"team_id": team, "event_type": etype})
        assert r.status_code == 201, r.json()
    if end:
        r = ev(client, nid(), mid, "match_end")
        assert r.status_code == 201, r.json()


# --- events ---------------------------------------------------------------------------------------

def test_event_flow_signature_sequence_and_projection(fresh):
    r = init(fresh, "m1")
    assert r.status_code == 201
    body = r.json()
    assert body["sequence"] == 1 and body["match_version"] == 1 and body["type"] == "match_init"
    assert body["signature"] == sign("m1-init", {"sport_id": "football", "home_team_id": "t1", "away_team_id": "t2"},
                                     key=SALT)
    ev(fresh, "s", "m1", "match_start")
    g = ev(fresh, "evt-0003", "m1", "score", {"team_id": "t1", "event_type": "goal"}).json()
    assert g["sequence"] == 3 and len(g["signature"]) == 64
    assert g["signature"] == sign("evt-0003", {"team_id": "t1", "event_type": "goal"}, key=SALT)
    ev(fresh, "d1", "m1", "discipline", {"team_id": "t2", "points": -1})
    ev(fresh, "end", "m1", "match_end")
    s = fresh.get("/audit/v1/score/m1").json()
    assert s["status"] == "completed" and s["outcome"] == "home_win" and s["winner_team_id"] == "t1"
    assert s["home"] == {"team_id": "t1", "score": 1, "wickets": None, "balls": None, "overs": None, "fair_play": 0}
    assert s["away"]["fair_play"] == -1 and s["version"] == 5 and s["league_id"] is None
    assert [e["sequence"] for e in s["events"]] == [1, 2, 3, 4, 5]
    assert s["events"][2]["signature"] == g["signature"] and s["events"][2]["compensated"] is False


def test_idempotent_replay_and_duplicate_id(fresh):
    init(fresh, "m1")
    ev(fresh, "st", "m1", "match_start")
    first = ev(fresh, "g1", "m1", "score", {"team_id": "t1", "event_type": "goal"})
    again = ev(fresh, "g1", "m1", "score", {"team_id": "t1", "event_type": "goal"})
    assert first.status_code == 201 and again.status_code == 200 and again.json() == first.json()
    assert fresh.get("/audit/v1/score/m1").json()["home"]["score"] == 1
    diff = ev(fresh, "g1", "m1", "score", {"team_id": "t2", "event_type": "goal"})
    assert diff.status_code == 409 and err(diff) == "DUPLICATE_EVENT_ID"


def test_state_machine_errors(fresh):
    assert err(ev(fresh, "x", "nope", "match_start")) == "MATCH_NOT_FOUND"
    assert err(init(fresh, "m1", sport="curling")) == "SPORT_NOT_FOUND"
    init(fresh, "m1")
    assert err(ev(fresh, "dup-init", "m1", "match_init",
                  {"sport_id": "football", "home_team_id": "a", "away_team_id": "b"})) == "MATCH_EXISTS"
    assert err(ev(fresh, "g", "m1", "score", {"team_id": "t1", "event_type": "goal"})) == "MATCH_NOT_IN_PROGRESS"
    assert err(ev(fresh, "e", "m1", "match_end")) == "ILLEGAL_TRANSITION"
    ev(fresh, "s", "m1", "match_start")
    assert err(ev(fresh, "s2", "m1", "match_start")) == "ILLEGAL_TRANSITION"
    r = ev(fresh, "g2", "m1", "score", {"team_id": "zz", "event_type": "goal"})
    assert r.status_code == 400
    r = ev(fresh, "g3", "m1", "score", {"team_id": "t1", "event_type": "touchdown"})
    assert r.status_code == 400 and err(r) == "UNKNOWN_EVENT_TYPE"
    ev(fresh, "end", "m1", "match_end")
    assert err(ev(fresh, "g4", "m1", "score", {"team_id": "t1", "event_type": "goal"})) == "MATCH_NOT_IN_PROGRESS"


@pytest.mark.parametrize("body", [
    {"event_id": "a", "match_id": "m", "type": "explode", "payload": {}},
    {"event_id": "a|b", "match_id": "m", "type": "match_start", "payload": {}},
    {"event_id": "a", "match_id": "m", "type": "score", "payload": {"team_id": "t1"}},
    {"event_id": "a", "match_id": "m", "type": "discipline", "payload": {"team_id": "t1", "points": "x"}},
    {"event_id": "a", "match_id": "m", "type": "score"},
])
def test_event_schema_errors(fresh, body):
    r = fresh.post("/audit/v1/events", json=body)
    assert r.status_code == 400 and err(r) == "VALIDATION_ERROR"


def test_compensation_rules(fresh):
    init(fresh, "m1")
    ev(fresh, "s", "m1", "match_start")
    ev(fresh, "g1", "m1", "score", {"team_id": "t1", "event_type": "goal"})
    ev(fresh, "g2", "m1", "score", {"team_id": "t2", "event_type": "goal"})
    c = ev(fresh, "c1", "m1", "compensation", {"compensates": "g1", "reason": "offside"})
    assert c.status_code == 201
    assert c.json()["signature"] == sign("c1", {"compensates": "g1", "reason": "offside"}, key=SALT)
    assert err(ev(fresh, "c2", "m1", "compensation", {"compensates": "g1", "reason": "again"})) == "INVALID_COMPENSATION"
    assert err(ev(fresh, "c3", "m1", "compensation", {"compensates": "s", "reason": "x"})) == "INVALID_COMPENSATION"
    assert err(ev(fresh, "c4", "m1", "compensation", {"compensates": "ghost", "reason": "x"})) == "EVENT_NOT_FOUND"
    init(fresh, "m2")
    assert err(ev(fresh, "c5", "m2", "compensation", {"compensates": "g2", "reason": "x"})) == "INVALID_COMPENSATION"
    ev(fresh, "end", "m1", "match_end")
    s = fresh.get("/audit/v1/score/m1").json()
    assert s["home"]["score"] == 0 and s["away"]["score"] == 1 and s["outcome"] == "away_win"
    g1 = [e for e in s["events"] if e["event_id"] == "g1"][0]
    assert g1["compensated"] is True and g1["compensated_by"] == "c1"
    assert g1["payload"] == {"team_id": "t1", "event_type": "goal"}  # original stays unchanged
    # compensation is allowed after completion
    assert ev(fresh, "c6", "m1", "compensation", {"compensates": "g2", "reason": "VAR"}).status_code == 201
    assert fresh.get("/audit/v1/score/m1").json()["outcome"] == "draw"


def test_tie_not_allowed_and_tiebreak_winner(fresh):
    init(fresh, "b1", sport="basketball")
    ev(fresh, "s", "b1", "match_start")
    ev(fresh, "p1", "b1", "score", {"team_id": "t1", "event_type": "three_pointer"})
    ev(fresh, "p2", "b1", "score", {"team_id": "t2", "event_type": "free_throw"})
    ev(fresh, "p3", "b1", "score", {"team_id": "t2", "event_type": "two_pointer"})
    assert err(ev(fresh, "end", "b1", "match_end")) == "TIE_NOT_ALLOWED"
    ev(fresh, "tb", "b1", "tiebreak_winner", {"team_id": "t2"})
    assert ev(fresh, "end2", "b1", "match_end").status_code == 201
    s = fresh.get("/audit/v1/score/b1").json()
    assert s["outcome"] == "away_win" and s["winner_team_id"] == "t2" and s["tiebreak_winner_team_id"] == "t2"
    ev(fresh, "ctb", "b1", "compensation", {"compensates": "tb", "reason": "overturned"})
    s = fresh.get("/audit/v1/score/b1").json()
    assert s["outcome"] == "undecided" and s["winner_team_id"] is None


def test_innings_model_limits_and_overs(fresh):
    body = {"sport_id": "mini_cricket", "name": "Mini", "scoring_model": "innings",
            "periods": {"innings_per_team": 1, "overs_per_innings": 1, "balls_per_over": 6, "wickets_per_innings": 2},
            "scoring_events": {"hit": {"runs": 4, "legal_ball": True, "wicket": False},
                               "extra": {"runs": 1, "legal_ball": False, "wicket": False},
                               "out": {"runs": 0, "legal_ball": True, "wicket": True}},
            "draw_allowed": True, "overtime": {"policy": "super_over"},
            "roster": {"min_squad_size": 2, "max_squad_size": 5, "required_positions": {}}}
    assert fresh.post("/audit/v1/sports", json=body).status_code == 201
    init(fresh, "c1", sport="mini_cricket")
    ev(fresh, "s", "c1", "match_start")
    for i in range(5):
        assert ev(fresh, f"h{i}", "c1", "score", {"team_id": "t1", "event_type": "hit"}).status_code == 201
    ev(fresh, "x1", "c1", "score", {"team_id": "t1", "event_type": "extra"})
    s = fresh.get("/audit/v1/score/c1").json()["home"]
    assert s == {"team_id": "t1", "score": 21, "wickets": 0, "balls": 5, "overs": "0.5", "fair_play": 0}
    ev(fresh, "h5", "c1", "score", {"team_id": "t1", "event_type": "hit"})  # 6th legal ball
    assert err(ev(fresh, "h6", "c1", "score", {"team_id": "t1", "event_type": "hit"})) == "INNINGS_COMPLETE"
    # compensated events don't count toward limits
    ev(fresh, "ch", "c1", "compensation", {"compensates": "h5", "reason": "no-ball recount"})
    assert ev(fresh, "h7", "c1", "score", {"team_id": "t1", "event_type": "hit"}).status_code == 201
    ev(fresh, "o1", "c1", "score", {"team_id": "t2", "event_type": "out"})
    ev(fresh, "o2", "c1", "score", {"team_id": "t2", "event_type": "out"})
    assert err(ev(fresh, "o3", "c1", "score", {"team_id": "t2", "event_type": "hit"})) == "INNINGS_COMPLETE"


def test_round_model_series_decided(fresh):
    init(fresh, "e1", sport="esports")
    ev(fresh, "s", "e1", "match_start")
    ev(fresh, "r1", "e1", "score", {"team_id": "t1", "event_type": "round_win"})
    ev(fresh, "r2", "e1", "score", {"team_id": "t2", "event_type": "round_win"})
    ev(fresh, "r3", "e1", "score", {"team_id": "t1", "event_type": "round_win"})
    assert err(ev(fresh, "r4", "e1", "score", {"team_id": "t2", "event_type": "round_win"})) == "SERIES_ALREADY_DECIDED"
    ev(fresh, "end", "e1", "match_end")
    s = fresh.get("/audit/v1/score/e1").json()
    assert s["home"]["score"] == 2 and s["outcome"] == "home_win"


def test_mystery_sport_works_without_restart(fresh):
    sport = {"sport_id": "kabaddi", "name": "Kabaddi", "scoring_model": "event",
             "periods": {"count": 2, "duration_minutes": 20},
             "scoring_events": {"raid_point": {"points": 1}, "all_out": {"points": 2}},
             "draw_allowed": False, "overtime": {"policy": "golden_score"},
             "roster": {"min_squad_size": 7, "max_squad_size": 12, "required_positions": {}}}
    assert fresh.post("/audit/v1/sports", json=sport).status_code == 201
    init(fresh, "k1", sport="kabaddi")
    play(fresh, "k1", [("t1", "all_out"), ("t2", "raid_point")])
    s = fresh.get("/audit/v1/score/k1").json()
    assert (s["home"]["score"], s["away"]["score"], s["outcome"]) == (2, 1, "home_win")


def test_score_unknown_match_404(fresh):
    r = fresh.get("/audit/v1/score/ghost")
    assert r.status_code == 404 and err(r) == "MATCH_NOT_FOUND"


# --- leagues + standings ---------------------------------------------------------------------------

def league(client, league_id="lg-1", teams=("t1", "t2", "t3", "t4"), fixtures=None, sport="football", **extra):
    if fixtures is None:
        fixtures = [{"match_id": f"{league_id}-{a}-{b}", "home": a, "away": b}
                    for a, b in itertools.combinations(teams, 2)]
    body = {"league_id": league_id, "sport_id": sport, "teams": list(teams), "fixtures": fixtures,
            "qualification": {"spots": 2}, **extra}
    return client.post("/audit/v1/leagues", json=body)


def result(client, mid, home_goals, away_goals, home="", away=""):
    m = fresh_match_teams(client, mid)
    play(client, mid, [(m[0], "goal")] * home_goals + [(m[1], "goal")] * away_goals)


def fresh_match_teams(client, mid):
    s = client.get(f"/audit/v1/score/{mid}").json()
    return s["home"]["team_id"], s["away"]["team_id"]


def test_league_registration_and_errors(fresh):
    r = league(fresh)
    assert r.status_code == 201
    assert r.json() == {"league_id": "lg-1", "status": "created", "team_count": 4, "fixture_count": 6}
    assert err(league(fresh)) == "LEAGUE_EXISTS"
    assert err(league(fresh, league_id="lg-2", fixtures=[{"match_id": "lg-1-t1-t2", "home": "t1", "away": "t2"}])) == "MATCH_EXISTS"
    assert err(league(fresh, league_id="lg-3", sport="curling")) == "SPORT_NOT_FOUND"
    assert league(fresh, league_id="lg-4", fixtures=[{"match_id": "x", "home": "t1", "away": "t9"}]).status_code == 400
    assert league(fresh, league_id="lg-5", fixtures=[{"match_id": "y", "home": "t1", "away": "t1"}]).status_code == 400
    s = fresh.get("/audit/v1/score/lg-1-t1-t2").json()
    assert s["status"] == "upcoming" and s["league_id"] == "lg-1" and s["version"] == 0
    assert err(fresh.get("/audit/v1/standings/nope")) == "LEAGUE_NOT_FOUND"


def test_standings_basic_table_and_h2h(fresh):
    league(fresh, teams=("t1", "t2", "t3"))
    result(fresh, "lg-1-t1-t2", 2, 1)
    result(fresh, "lg-1-t1-t3", 1, 1)
    st = fresh.get("/audit/v1/standings/lg-1").json()
    rows = {r["team_id"]: r for r in st["table"]}
    assert rows["t1"] == {"rank": 1, "team_id": "t1", "played": 2, "won": 1, "drawn": 1, "lost": 0, "scored": 3,
                          "conceded": 2, "diff": 1, "points": 4, "fair_play": 0, "status": rows["t1"]["status"],
                          "resolved_by": None}
    assert st["h2h"]["t1"]["t2"] == {"played": 1, "points": 3, "scored": 2, "conceded": 1}
    assert st["h2h"]["t2"]["t3"] == {"played": 0, "points": 0, "scored": 0, "conceded": 0}
    assert st["qualification_spots"] == 2 and st["sport_id"] == "football"


def test_three_way_h2h_mini_league(fresh):
    # t1, t2, t3 all on 6 points; mini-league decides; t4 loses everything.
    league(fresh, teams=("t1", "t2", "t3", "t4"))
    result(fresh, "lg-1-t1-t2", 3, 0)   # t1 beats t2
    result(fresh, "lg-1-t2-t3", 1, 0)   # t2 beats t3
    result(fresh, "lg-1-t1-t3", 0, 1)   # t3 beats t1
    result(fresh, "lg-1-t1-t4", 1, 0)
    result(fresh, "lg-1-t2-t4", 1, 0)
    result(fresh, "lg-1-t3-t4", 1, 0)
    st = fresh.get("/audit/v1/standings/lg-1").json()
    order = [r["team_id"] for r in st["table"]]
    # h2h points all 3; h2h diff: t1 +2, t2 -2, t3 0
    assert order == ["t1", "t3", "t2", "t4"]
    by = {r["team_id"]: r["resolved_by"] for r in st["table"]}
    assert by == {"t1": "h2h_diff", "t3": "h2h_diff", "t2": None, "t4": None}


def test_draw_lots_order_exact(fresh):
    league(fresh, teams=("t1", "t2", "t3"), lots_seed=42)
    st = fresh.get("/audit/v1/standings/lg-1").json()
    expected = sorted(["t1", "t2", "t3"], key=lambda t: lots_key(42, "lg-1", t))
    assert [r["team_id"] for r in st["table"]] == expected == ["t1", "t3", "t2"]
    assert [r["resolved_by"] for r in st["table"]] == ["draw_lots", "draw_lots", None]


def test_qualification_status_and_compensation_recompute(fresh):
    teams = ("t1", "t2", "t3")
    league(fresh, teams=teams, qualification={"spots": 1})
    result(fresh, "lg-1-t1-t2", 1, 0)
    result(fresh, "lg-1-t1-t3", 1, 0)
    st = {r["team_id"]: r for r in fresh.get("/audit/v1/standings/lg-1").json()["table"]}
    # t1 has 6; t2 and t3 max = 3 -> t1 clinched; t2/t3 eliminated (t1 points 6 > their max 3)
    assert st["t1"]["status"] == "clinched"
    assert st["t2"]["status"] == "eliminated" and st["t3"]["status"] == "eliminated"
    # Edge case 5: correct a result after qualification was determined.
    goal = [e for e in fresh.get("/audit/v1/score/lg-1-t1-t2").json()["events"] if e["type"] == "score"][0]
    ev(fresh, "fix", "lg-1-t1-t2", "compensation", {"compensates": goal["event_id"], "reason": "own goal reversed"})
    st2 = {r["team_id"]: r for r in fresh.get("/audit/v1/standings/lg-1").json()["table"]}
    assert st2["t1"]["points"] == 4 and st2["t2"]["points"] == 1 and st2["t2"]["drawn"] == 1
    # t2 can now reach 4 (= t1's points), so t1 is no longer clinched under the exact rule.
    assert st2["t1"]["status"] == "still_possible"
    # original event still present and unchanged
    events = fresh.get("/audit/v1/score/lg-1-t1-t2").json()["events"]
    assert any(e["event_id"] == goal["event_id"] and e["compensated"] for e in events)


def test_undecided_match_is_not_played(fresh):
    league(fresh, league_id="bb", teams=("t1", "t2"), sport="basketball")
    mid = "bb-t1-t2"
    ev(fresh, "s", mid, "match_start")
    ev(fresh, "a", mid, "score", {"team_id": "t1", "event_type": "two_pointer"})
    ev(fresh, "b", mid, "score", {"team_id": "t2", "event_type": "two_pointer"})
    ev(fresh, "tb", mid, "tiebreak_winner", {"team_id": "t1"})
    ev(fresh, "end", mid, "match_end")
    ev(fresh, "ctb", mid, "compensation", {"compensates": "tb", "reason": "x"})
    st = fresh.get("/audit/v1/standings/bb").json()
    assert all(r["played"] == 0 for r in st["table"])


def test_custom_points_and_tiebreak_win_counts_as_win(fresh):
    league(fresh, league_id="bb", teams=("t1", "t2"), sport="basketball", points={"win": 2, "draw": 0, "loss": 1})
    mid = "bb-t1-t2"
    ev(fresh, "s", mid, "match_start")
    ev(fresh, "tb", mid, "tiebreak_winner", {"team_id": "t2"})
    ev(fresh, "end", mid, "match_end")
    rows = {r["team_id"]: r for r in fresh.get("/audit/v1/standings/bb").json()["table"]}
    assert rows["t2"]["won"] == 1 and rows["t2"]["points"] == 2 and rows["t1"]["points"] == 1


def test_net_run_rate(fresh):
    league(fresh, league_id="cr", teams=("t1", "t2"), sport="cricket")
    mid = "cr-t1-t2"
    ev(fresh, "s", mid, "match_start")
    for i in range(12):  # t1: 12 legal balls (2 overs), 12 singles
        ev(fresh, f"a{i}", mid, "score", {"team_id": "t1", "event_type": "single"})
    for i in range(10):  # t2 all out: 10 wickets -> counts as full 20 overs
        ev(fresh, f"w{i}", mid, "score", {"team_id": "t2", "event_type": "wicket"})
    ev(fresh, "end", mid, "match_end")
    rows = {r["team_id"]: r for r in fresh.get("/audit/v1/standings/cr").json()["table"]}
    # t1: 12/2 - 0/20 = 6.0 ; t2: 0/20 - 12/2 = -6.0
    assert rows["t1"]["diff"] == 6.0 and rows["t2"]["diff"] == -6.0
    assert rows["t1"]["scored"] == 12
