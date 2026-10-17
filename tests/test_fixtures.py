import itertools
from collections import Counter

import pytest

from app.fixtures import seed_order
from conftest import err


def post(client, fmt, teams, params=None):
    return client.post("/audit/v1/fixtures", json={"format": fmt, "teams": teams, "params": params or {}})


def T(n):
    return [f"t{i}" for i in range(1, n + 1)]


# --- round robin --------------------------------------------------------------------------------

@pytest.mark.parametrize("n", list(range(2, 41)))
@pytest.mark.parametrize("legs", [1, 2])
def test_round_robin_properties(client, n, legs):
    r = post(client, "round_robin", T(n), {"legs": legs})
    assert r.status_code == 200
    body = r.json()
    per_leg = n - 1 if n % 2 == 0 else n
    assert body["round_count"] == per_leg * legs and body["team_count"] == n and body["legs"] == legs
    pair_count, ordered = Counter(), Counter()
    for rnd in body["rounds"]:
        assert len(rnd["matches"]) == n // 2
        assert len(rnd["byes"]) == (n % 2)
        seen = [t for m in rnd["matches"] for t in (m["home"], m["away"])] + rnd["byes"]
        assert sorted(seen) == sorted(T(n))  # everyone exactly once per round
        for idx, m in enumerate(rnd["matches"], 1):
            assert m["match_id"] == f"RR-L{m['leg']}-R{rnd['round']}-M{idx}"
            pair_count[frozenset((m["home"], m["away"]))] += 1
            ordered[(m["home"], m["away"])] += 1
    assert all(v == legs for v in pair_count.values()) and len(pair_count) == n * (n - 1) // 2
    if legs == 2:
        assert all(v == 1 for v in ordered.values()) and len(ordered) == n * (n - 1)
    for leg in range(1, legs + 1):
        home, away, byes = Counter(), Counter(), Counter()
        for rnd in body["rounds"]:
            for m in rnd["matches"]:
                if m["leg"] == leg:
                    home[m["home"]] += 1
                    away[m["away"]] += 1
            if (rnd["round"] - 1) // per_leg + 1 == leg:
                byes.update(rnd["byes"])
        for t in T(n):
            assert abs(home[t] - away[t]) <= 1, (t, home[t], away[t])
            if n % 2:
                assert byes[t] == 1


def test_round_robin_forfeit_remaining(client):
    params = {"legs": 1, "withdrawals": [{"team_id": "t3", "after_round": 2}], "withdrawal_policy": "forfeit_remaining"}
    body = post(client, "round_robin", T(5), params).json()
    for rnd in body["rounds"]:
        for m in rnd["matches"]:
            if "t3" in (m["home"], m["away"]) and rnd["round"] > 2:
                assert m["status"] == "forfeit"
                assert m["awarded_to"] == (m["away"] if m["home"] == "t3" else m["home"])
            else:
                assert m["status"] == "scheduled" and m["awarded_to"] is None
    s = body["summary"]
    assert s["total"] == 10 and s["forfeit"] + s["scheduled"] == 10 and s["voided"] == 0


def test_round_robin_void_all_and_both_withdrawn(client):
    params = {"withdrawals": [{"team_id": "t1", "after_round": 1}, {"team_id": "t2", "after_round": 0}],
              "withdrawal_policy": "void_all"}
    body = post(client, "round_robin", T(4), params).json()
    for rnd in body["rounds"]:
        for m in rnd["matches"]:
            involved = {"t1", "t2"} & {m["home"], m["away"]}
            assert m["status"] == ("voided" if involved else "scheduled")
            assert m["awarded_to"] is None
    assert body["summary"]["voided"] == 5


def test_round_robin_both_withdrawn_forfeit_policy_is_voided(client):
    params = {"withdrawals": [{"team_id": "t1", "after_round": 0}, {"team_id": "t2", "after_round": 0}]}
    body = post(client, "round_robin", T(4), params).json()
    m = [m for r in body["rounds"] for m in r["matches"] if {m["home"], m["away"]} == {"t1", "t2"}][0]
    assert m["status"] == "voided" and m["awarded_to"] is None


@pytest.mark.parametrize("params", [
    {"withdrawals": [{"team_id": "zz", "after_round": 1}]},
    {"withdrawals": [{"team_id": "t1", "after_round": 99}]},
    {"withdrawals": [{"team_id": "t1", "after_round": -1}]},
    {"legs": 3},
    {"withdrawal_policy": "nope"},
])
def test_round_robin_bad_params(client, params):
    r = post(client, "round_robin", T(5), params)
    assert r.status_code == 400 and err(r) == "VALIDATION_ERROR"


@pytest.mark.parametrize("fmt, n", [("round_robin", 1), ("round_robin", 41), ("swiss", 65), ("single_elim", 1),
                                    ("single_elim", 129), ("double_elim", 2)])
def test_team_count_limits(client, fmt, n):
    r = post(client, fmt, T(n))
    assert r.status_code == 400 and err(r) == "VALIDATION_ERROR"


def test_duplicate_teams_and_bad_format(client):
    assert post(client, "round_robin", ["a", "a"]).status_code == 400
    assert post(client, "league", ["a", "b"]).status_code == 400


# --- swiss -----------------------------------------------------------------------------------------

def test_swiss_round_1_exact_odd(client):
    body = post(client, "swiss", T(5), {"total_rounds": 3, "round": 1}).json()
    assert [(p["home"], p["away"]) for p in body["pairings"]] == [("t1", "t3"), ("t2", "t4")]
    assert body["bye"] == "t5" and body["pairings"][0]["match_id"] == "SW-R1-M1"
    assert [s["team_id"] for s in body["standings"]] == T(5)


def test_swiss_round_1_default_total_rounds(client):
    body = post(client, "swiss", T(8)).json()
    assert body["total_rounds"] == 3 and body["round"] == 1 and body["bye"] is None
    assert [(p["home"], p["away"]) for p in body["pairings"]] == [("t1", "t5"), ("t2", "t6"), ("t3", "t7"), ("t4", "t8")]


def test_swiss_spec_example_round_2(client):
    params = {"total_rounds": 3, "round": 2, "history": [
        {"round": 1, "bye": "t5", "matches": [{"home": "t1", "away": "t3", "result": "home"},
                                               {"home": "t2", "away": "t4", "result": "draw"}]}]}
    body = post(client, "swiss", T(5), params).json()
    st = {s["team_id"]: s for s in body["standings"]}
    assert st["t1"]["score"] == 1.0 and st["t5"]["score"] == 1.0 and st["t2"]["score"] == 0.5
    assert st["t2"]["buchholz"] == 0.5 and st["t1"]["buchholz"] == 0.0
    assert [s["team_id"] for s in body["standings"]][:3] == ["t1", "t5", "t2"]
    assert [s["rank"] for s in body["standings"]] == [1, 2, 3, 4, 5]
    assert body["bye"] == "t3"  # lowest score, no bye yet
    paired = {frozenset((p["home"], p["away"])) for p in body["pairings"]}
    assert frozenset(("t2", "t4")) not in paired  # rematch forbidden
    score = {t: s["score"] for t, s in st.items()}
    assert sum(abs(score[p["home"]] - score[p["away"]]) for p in body["pairings"]) == 1.0


def _brute_min(teams, score, met):
    best = None

    def rec(rest, acc):
        nonlocal best
        if not rest:
            best = acc if best is None else min(best, acc)
            return
        a = rest[0]
        for b in rest[1:]:
            if frozenset((a, b)) not in met:
                rec([x for x in rest if x not in (a, b)], acc + abs(score[a] - score[b]))

    rec(teams, 0.0)
    return best


def test_swiss_matches_bruteforce_minimum(client):
    import random
    rng = random.Random(5)
    checked = 0
    for _ in range(60):
        n = rng.choice([4, 6, 8, 10])
        teams = T(n)
        hist, met = [], set()
        for rd in range(1, rng.randint(1, 3) + 1):
            pool = teams[:]
            rng.shuffle(pool)
            ms = [{"home": pool[i], "away": pool[i + 1], "result": rng.choice(["home", "away", "draw"])}
                  for i in range(0, n, 2)]
            if any(frozenset((m["home"], m["away"])) in met for m in ms):
                break
            met.update(frozenset((m["home"], m["away"])) for m in ms)
            hist.append({"round": rd, "bye": None, "matches": ms})
        if not hist:
            continue
        r = post(client, "swiss", teams, {"total_rounds": n - 1, "round": len(hist) + 1, "history": hist})
        assert r.status_code == 200
        body = r.json()
        score = {s["team_id"]: s["score"] for s in body["standings"]}
        got = sum(abs(score[p["home"]] - score[p["away"]]) for p in body["pairings"])
        assert got == _brute_min(teams, score, met)
        assert all(frozenset((p["home"], p["away"])) not in met for p in body["pairings"])
        assert sorted(t for p in body["pairings"] for t in (p["home"], p["away"])) == sorted(teams)
        checked += 1
    assert checked > 20


def test_swiss_no_valid_pairing_409(client):
    # t1 has already met everyone, so no rematch-free pairing exists.
    hist = [{"round": 1, "bye": None, "matches": [{"home": "t1", "away": "t2", "result": "home"},
                                                   {"home": "t1", "away": "t3", "result": "home"},
                                                   {"home": "t1", "away": "t4", "result": "home"}]}]
    r = post(client, "swiss", T(4), {"total_rounds": 3, "round": 2, "history": hist})
    assert r.status_code == 409 and err(r) == "NO_VALID_PAIRING"
    assert r.json()["error"]["details"] == {"round": 2}


def test_swiss_odd_tries_next_bye_candidate(client):
    # t3 is the natural bye, but then t1/t2/t4/t5 cannot be paired without a rematch unless t5 sits out.
    hist = [{"round": 1, "bye": None, "matches": [
        {"home": "t1", "away": "t2", "result": "home"}, {"home": "t1", "away": "t4", "result": "home"},
        {"home": "t2", "away": "t4", "result": "draw"}]}]
    body = post(client, "swiss", T(5), {"total_rounds": 3, "round": 2, "history": hist}).json()
    players = {t for p in body["pairings"] for t in (p["home"], p["away"])}
    assert body["bye"] not in players and len(players) == 4
    for p in body["pairings"]:
        assert frozenset((p["home"], p["away"])) not in {frozenset(("t1", "t2")), frozenset(("t1", "t4")),
                                                          frozenset(("t2", "t4"))}


def test_swiss_history_must_match_round(client):
    r = post(client, "swiss", T(4), {"round": 2, "history": []})
    assert r.status_code == 400 and err(r) == "VALIDATION_ERROR"


def test_swiss_bye_goes_to_lowest_without_bye(client):
    hist = [{"round": 1, "bye": "t5", "matches": [{"home": "t1", "away": "t3", "result": "home"},
                                                   {"home": "t2", "away": "t4", "result": "home"}]}]
    body = post(client, "swiss", T(5), {"total_rounds": 4, "round": 2, "history": hist}).json()
    # zero-score teams without bye: t3, t4 -> lowest seed = largest index = t4
    assert body["bye"] == "t4"


# --- single elimination ---------------------------------------------------------------------------

def test_seed_order():
    assert seed_order(8) == [1, 8, 4, 5, 2, 7, 3, 6]
    assert seed_order(2) == [1, 2]


def test_single_elim_six_teams_exact(client):
    body = post(client, "single_elim", T(6)).json()
    assert body["bracket_size"] == 8 and len(body["rounds"]) == 3
    r1 = body["rounds"][0]["matches"]
    assert [(m["home"], m["away"], m["bye"]) for m in r1] == [
        ("t1", None, True), ("t4", "t5", False), ("t2", None, True), ("t3", "t6", False)]
    assert r1[0]["winner"] == "t1" and r1[1]["winner_to"] == {"match_id": "R2M1", "slot": "away"}
    r2 = body["rounds"][1]["matches"]
    assert r2[0]["home"] == "t1" and r2[0]["away"] is None and r2[1]["home"] == "t2"
    final = body["rounds"][2]["matches"][0]
    assert final["match_id"] == "R3M1" and final["winner_to"] is None
    for m in r1:
        assert set(m) >= {"match_id", "bracket", "round", "index", "home", "away", "home_seed", "away_seed",
                          "bye", "winner", "loser", "winner_to", "loser_to"}


def test_single_elim_results_and_third_place(client):
    results = [{"match_id": "R1M2", "winner": "t4"}, {"match_id": "R1M4", "winner": "t6"},
               {"match_id": "R2M1", "winner": "t4"}, {"match_id": "R2M2", "winner": "t2"}]
    body = post(client, "single_elim", T(6), {"third_place_match": True, "results": results}).json()
    r2 = body["rounds"][1]["matches"]
    assert r2[0]["home"] == "t1" and r2[0]["away"] == "t4" and r2[0]["winner"] == "t4" and r2[0]["loser"] == "t1"
    assert r2[1]["home"] == "t2" and r2[1]["away"] == "t6"
    assert r2[0]["loser_to"] == {"match_id": "TP", "slot": "home"}
    final = [m for m in body["rounds"][2]["matches"] if m["match_id"] == "R3M1"][0]
    tp = [m for m in body["rounds"][2]["matches"] if m["match_id"] == "TP"][0]
    assert (final["home"], final["away"]) == ("t4", "t2")
    assert tp["bracket"] == "third_place" and (tp["home"], tp["away"]) == ("t1", "t6")


@pytest.mark.parametrize("results", [[{"match_id": "R9M9", "winner": "t1"}], [{"match_id": "R1M2", "winner": "t1"}]])
def test_single_elim_bad_results(client, results):
    r = post(client, "single_elim", T(6), {"results": results})
    assert r.status_code == 400 and err(r) == "VALIDATION_ERROR"


@pytest.mark.parametrize("n", [2, 3, 5, 7, 9, 16, 33, 128])
def test_single_elim_structure(client, n):
    body = post(client, "single_elim", T(n)).json()
    size = body["bracket_size"]
    assert size >= n and size // 2 < n
    assert sum(len(r["matches"]) for r in body["rounds"]) == size - 1
    byes = [m for m in body["rounds"][0]["matches"] if m["bye"]]
    assert len(byes) == size - n


# --- double elimination ---------------------------------------------------------------------------

def _all(body):
    return [m for r in body["winners"] for m in r["matches"]] + \
           [m for r in body["losers"] for m in r["matches"]] + body["grand_final"]


@pytest.mark.parametrize("n", [3, 4, 5, 8, 12, 16, 32])
def test_double_elim_counts_and_routing(client, n):
    body = post(client, "double_elim", T(n), {"bracket_reset": True}).json()
    size = body["bracket_size"]
    k = size.bit_length() - 1
    assert [len(r["matches"]) for r in body["winners"]] == [size // 2 ** r for r in range(1, k + 1)]
    assert len(body["losers"]) == 2 * (k - 1)
    assert sum(len(r["matches"]) for r in body["losers"]) == size - 2
    for j in range(1, k):
        assert len(body["losers"][2 * j - 2]["matches"]) == size // 2 ** (j + 1)
        assert len(body["losers"][2 * j - 1]["matches"]) == size // 2 ** (j + 1)
    ms = {m["match_id"]: m for m in _all(body)}
    feeds = Counter()
    for m in ms.values():
        for key in ("winner_to", "loser_to"):
            if m[key]:
                assert m[key]["match_id"] in ms
                feeds[(m[key]["match_id"], m[key]["slot"])] += 1
        if m["bracket"] == "winners":
            assert m["loser_to"] is not None
        if m["bracket"] == "losers":
            assert m["loser_to"] is None
    for mid, m in ms.items():
        for slot in ("home", "away"):
            if mid.startswith("WR1M"):
                assert feeds[(mid, slot)] == 0
            else:
                assert feeds[(mid, slot)] == 1, (mid, slot)
    wf = ms[f"WR{k}M1"]
    lf = ms[f"LR{2 * (k - 1)}M1"]
    assert wf["winner_to"] == {"match_id": "GF1", "slot": "home"}
    assert wf["loser_to"] == {"match_id": lf["match_id"], "slot": "away"}
    assert lf["winner_to"] == {"match_id": "GF1", "slot": "away"}
    gf2 = ms["GF2"]
    assert gf2["conditional"] is True and gf2["required"] is None


def _play_all(client, n, pick_gf1_away):
    """Plays the bracket by always taking the home team, except GF1 per flag."""
    results = []
    for _ in range(200):
        body = post(client, "double_elim", T(n), {"bracket_reset": True, "results": results}).json()
        ms = _all(body)
        todo = [m for m in ms if m["winner"] is None and m["home"] and m["away"] and m["match_id"] != "GF2"]
        if not todo:
            return body
        m = todo[0]
        winner = m["away"] if (m["match_id"] == "GF1" and pick_gf1_away) else m["home"]
        results.append({"match_id": m["match_id"], "winner": winner})
    raise AssertionError("bracket did not finish")


def test_double_elim_bracket_reset_required(client):
    body = _play_all(client, 8, pick_gf1_away=True)
    gf1, gf2 = body["grand_final"]
    assert gf1["winner"] == gf1["away"]
    assert gf2["required"] is True and {gf2["home"], gf2["away"]} == {gf1["home"], gf1["away"]}


def test_double_elim_no_reset_needed(client):
    body = _play_all(client, 6, pick_gf1_away=False)
    gf1, gf2 = body["grand_final"]
    assert gf1["winner"] == gf1["home"] and gf2["required"] is False


def test_double_elim_without_reset_has_single_final(client):
    body = post(client, "double_elim", T(4), {"bracket_reset": False}).json()
    assert [m["match_id"] for m in body["grand_final"]] == ["GF1"] and body["bracket_reset"] is False


def test_double_elim_wr1_seeding_matches_single_elim(client):
    de = post(client, "double_elim", T(6)).json()["winners"][0]["matches"]
    se = post(client, "single_elim", T(6)).json()["rounds"][0]["matches"]
    assert [(m["home"], m["away"], m["bye"]) for m in de] == [(m["home"], m["away"], m["bye"]) for m in se]
