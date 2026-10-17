"""POST /audit/v1/fixtures (spec 5.7): pure computation, nothing is stored.

Custom implementations of round robin (circle method), Swiss (minimum-cost rematch-free matching),
single elimination and double elimination. No fixture-generation library is used; Swiss uses a
general graph-matching routine (networkx blossom) only to find an optimal matching.
"""
import math

import networkx as nx

from app.core import ApiError, Checker, is_id, is_int, validation_error

LIMITS = {"round_robin": (2, 40), "swiss": (2, 64), "single_elim": (2, 128), "double_elim": (3, 128)}


def generate(body: dict) -> dict:
    c = Checker()
    fmt = body.get("format")
    c.check(fmt in LIMITS, "format")
    teams = body.get("teams")
    teams_ok = isinstance(teams, list) and all(is_id(t) for t in teams) and len(set(teams)) == len(teams or [])
    if teams_ok and fmt in LIMITS:
        lo, hi = LIMITS[fmt]
        teams_ok = lo <= len(teams) <= hi
    c.check(teams_ok, "teams")
    params = body.get("params", {})
    if params is None:
        params = {}
    c.check(isinstance(params, dict), "params")
    c.raise_if_any()
    if fmt == "round_robin":
        return round_robin(teams, params)
    if fmt == "swiss":
        return swiss(teams, params)
    if fmt == "single_elim":
        return single_elim(teams, params)
    return double_elim(teams, params)


# --- A) round robin --------------------------------------------------------------------------------

def circle_rounds(teams: list[str]) -> list[list[tuple]]:
    """One leg of rounds via the circle method. Returns [[(home, away), ...], ...]; None = bye slot.

    The dummy (bye) or first team stays fixed; the rest rotate. Home/away alternates for the fixed
    team and by position for the others, which keeps |home - away| <= 1 for every team.
    """
    arr = list(teams)
    if len(arr) % 2 == 1:
        arr = [None] + arr  # fixed dummy: whoever meets it has the bye
    n = len(arr)
    rounds = []
    for r in range(n - 1):
        pairs = []
        for i in range(n // 2):
            a, b = arr[i], arr[n - 1 - i]
            if i == 0:
                home, away = (a, b) if r % 2 == 0 else (b, a)
            else:
                home, away = (a, b) if i % 2 == 1 else (b, a)
            pairs.append((home, away))
        rounds.append(pairs)
        arr = [arr[0]] + [arr[-1]] + arr[1:-1]  # rotate everyone except the fixed element
    return rounds


def round_robin(teams: list[str], params: dict) -> dict:
    c = Checker()
    legs = params.get("legs", 1)
    c.check(legs in (1, 2) and is_int(legs), "legs")
    withdrawals = params.get("withdrawals", [])
    c.check(isinstance(withdrawals, list) and all(isinstance(w, dict) for w in withdrawals), "withdrawals")
    policy = params.get("withdrawal_policy", "forfeit_remaining")
    c.check(policy in ("void_all", "forfeit_remaining"), "withdrawal_policy")
    c.raise_if_any()

    one_leg = circle_rounds(teams)
    per_leg = len(one_leg)
    round_count = per_leg * legs

    withdrawn: dict[str, int] = {}
    for w in withdrawals:
        team, after = w.get("team_id"), w.get("after_round")
        if team not in teams or not is_int(after) or not 0 <= after <= round_count or team in withdrawn:
            raise validation_error(["withdrawals"])
        withdrawn[team] = after

    rounds_out = []
    summary = {"total": 0, "scheduled": 0, "forfeit": 0, "voided": 0}
    for leg in range(1, legs + 1):
        for r_index, pairs in enumerate(one_leg):
            global_round = (leg - 1) * per_leg + r_index + 1
            matches, byes = [], []
            for home, away in pairs:
                if leg == 2:
                    home, away = away, home
                if home is None or away is None:
                    byes.append(home if away is None else away)
                    continue
                status, awarded = _withdrawal_outcome(home, away, global_round, withdrawn, policy)
                matches.append({
                    "match_id": f"RR-L{leg}-R{global_round}-M{len(matches) + 1}",
                    "leg": leg, "home": home, "away": away, "status": status, "awarded_to": awarded,
                })
                summary["total"] += 1
                summary[status] += 1
            rounds_out.append({"round": global_round, "matches": matches, "byes": byes})
    return {
        "format": "round_robin", "legs": legs, "team_count": len(teams), "round_count": round_count,
        "rounds": rounds_out, "summary": summary,
    }


def _withdrawal_outcome(home, away, rnd, withdrawn, policy):
    if policy == "void_all":
        if home in withdrawn or away in withdrawn:
            return "voided", None
        return "scheduled", None
    home_out = home in withdrawn and rnd > withdrawn[home]
    away_out = away in withdrawn and rnd > withdrawn[away]
    if home in withdrawn and away in withdrawn and (home_out or away_out):
        return "voided", None
    if home_out and away_out:
        return "voided", None
    if home_out:
        return "forfeit", away
    if away_out:
        return "forfeit", home
    return "scheduled", None


# --- B) swiss --------------------------------------------------------------------------------------

def swiss(teams: list[str], params: dict) -> dict:
    n = len(teams)
    c = Checker()
    total_rounds = params.get("total_rounds", max(1, math.ceil(math.log2(n))))
    c.check(is_int(total_rounds) and 1 <= total_rounds <= max(1, n - 1), "total_rounds")
    rnd = params.get("round", 1)
    c.check(is_int(rnd) and 1 <= rnd <= (total_rounds if is_int(total_rounds) else rnd), "round")
    history = params.get("history", [])
    c.check(isinstance(history, list), "history")
    c.raise_if_any()

    seed = {t: i for i, t in enumerate(teams)}
    score = {t: 0.0 for t in teams}
    opponents = {t: [] for t in teams}
    had_bye = set()
    met = set()

    rounds_seen = sorted(h.get("round") for h in history if isinstance(h, dict) and is_int(h.get("round")))
    if len(rounds_seen) != len(history) or rounds_seen != list(range(1, rnd)):
        raise validation_error(["history"])
    for h in sorted(history, key=lambda x: x["round"]):
        bye = h.get("bye")
        matches = h.get("matches")
        if (bye is not None and bye not in seed) or not isinstance(matches, list):
            raise validation_error(["history"])
        if bye is not None:
            score[bye] += 1.0
            had_bye.add(bye)
        for m in matches:
            if not isinstance(m, dict):
                raise validation_error(["history"])
            home, away, result = m.get("home"), m.get("away"), m.get("result")
            if home not in seed or away not in seed or home == away or result not in ("home", "away", "draw"):
                raise validation_error(["history"])
            if result == "home":
                score[home] += 1.0
            elif result == "away":
                score[away] += 1.0
            else:
                score[home] += 0.5
                score[away] += 0.5
            opponents[home].append(away)
            opponents[away].append(home)
            met.add(frozenset((home, away)))

    buchholz = {t: sum(score[o] for o in opponents[t]) for t in teams}
    ordered = sorted(teams, key=lambda t: (-score[t], -buchholz[t], seed[t]))
    standings = [
        {"rank": i + 1, "team_id": t, "score": score[t], "buchholz": buchholz[t]} for i, t in enumerate(ordered)
    ]
    rank = {t: i for i, t in enumerate(ordered)}

    if rnd == 1:
        m = n // 2
        bye = teams[-1] if n % 2 == 1 else None
        pairs = [(teams[i], teams[i + m]) for i in range(m)]
    else:
        pairs, bye = _swiss_pairing(teams, score, rank, seed, met, had_bye, rnd)

    pairings = [{"match_id": f"SW-R{rnd}-M{i + 1}", "home": h, "away": a} for i, (h, a) in enumerate(pairs)]
    return {"format": "swiss", "round": rnd, "total_rounds": total_rounds, "pairings": pairings,
            "bye": bye, "standings": standings}


def _swiss_pairing(teams, score, rank, seed, met, had_bye, rnd):
    if len(teams) % 2 == 1:
        # Lowest score first; ties -> lowest seed (largest index). Teams without a bye come first.
        by_low = sorted(teams, key=lambda t: (score[t], -seed[t]))
        candidates = [t for t in by_low if t not in had_bye] or by_low
    else:
        candidates = [None]
    for bye in candidates:
        players = [t for t in teams if t != bye]
        pairs = _min_cost_matching(players, score, met)
        if pairs is not None:
            # Higher-ranked team at home; list pairings from the top board down.
            pairs = [tuple(sorted(p, key=lambda t: rank[t])) for p in pairs]
            pairs.sort(key=lambda p: rank[p[0]])
            return pairs, bye
    raise ApiError(409, "NO_VALID_PAIRING", f"No rematch-free pairing exists for round {rnd}.", {"round": rnd})


def _min_cost_matching(players, score, met):
    """Perfect matching without rematches minimising sum |score diff|, or None if none exists."""
    if not players:
        return []
    g = nx.Graph()
    g.add_nodes_from(players)
    big = 10_000
    for i, a in enumerate(players):
        for b in players[i + 1:]:
            if frozenset((a, b)) in met:
                continue
            cost = int(round(abs(score[a] - score[b]) * 2))  # scores are multiples of 0.5
            g.add_edge(a, b, weight=big - cost)
    matching = nx.max_weight_matching(g, maxcardinality=True)
    if len(matching) * 2 != len(players):
        return None
    return [tuple(p) for p in matching]


# --- C/D) elimination brackets ----------------------------------------------------------------------

def seed_order(size: int) -> list[int]:
    order = [1, 2]
    while len(order) < size:
        k2 = len(order) * 2
        order = [x for s in order for x in (s, k2 + 1 - s)]
    return order[:size] if size >= 2 else [1]


EMPTY = "__empty__"  # a slot whose source produced no team (bye)


class Bracket:
    """Generic bracket: matches with slot sources, propagation of byes and results."""

    def __init__(self, teams):
        self.teams = teams
        self.seed_of = {t: i + 1 for i, t in enumerate(teams)}
        self.matches: dict[str, dict] = {}
        self.order: list[str] = []
        self.slot_value: dict[tuple, str | None] = {}   # (match_id, slot) -> team / EMPTY / None (pending)
        self.outputs: dict[tuple, str | None] = {}      # (match_id, 'winner'|'loser') -> team / EMPTY / None

    def add(self, match_id, bracket, rnd, index, extra=None):
        m = {"match_id": match_id, "bracket": bracket, "round": rnd, "index": index,
             "home": None, "away": None, "home_seed": None, "away_seed": None, "bye": False,
             "winner": None, "loser": None, "winner_to": None, "loser_to": None}
        if extra:
            m.update(extra)
        self.matches[match_id] = m
        self.order.append(match_id)
        self.slot_value[(match_id, "home")] = None
        self.slot_value[(match_id, "away")] = None
        self.outputs[(match_id, "winner")] = None
        self.outputs[(match_id, "loser")] = None
        return m

    def route(self, src, outcome, dst, slot):
        self.matches[src]["winner_to" if outcome == "winner" else "loser_to"] = {"match_id": dst, "slot": slot}

    def set_slot(self, match_id, slot, value):
        self.slot_value[(match_id, slot)] = value
        m = self.matches[match_id]
        team = value if value not in (None, EMPTY) else None
        m[slot] = team
        m[f"{slot}_seed"] = self.seed_of.get(team) if team else None

    def propagate(self):
        changed = True
        while changed:
            changed = False
            for mid in self.order:
                m = self.matches[mid]
                h, a = self.slot_value[(mid, "home")], self.slot_value[(mid, "away")]
                if self.outputs[(mid, "winner")] is None and h is not None and a is not None:
                    if h == EMPTY and a == EMPTY:
                        self.outputs[(mid, "winner")] = EMPTY
                        self.outputs[(mid, "loser")] = EMPTY
                        changed = True
                    elif h == EMPTY or a == EMPTY:
                        present = a if h == EMPTY else h
                        m["bye"] = True
                        m["winner"] = present
                        self.outputs[(mid, "winner")] = present
                        self.outputs[(mid, "loser")] = EMPTY
                        changed = True
                for outcome in ("winner", "loser"):
                    out = self.outputs[(mid, outcome)]
                    dest = m["winner_to" if outcome == "winner" else "loser_to"]
                    if out is not None and dest and self.slot_value[(dest["match_id"], dest["slot"])] is None:
                        self.set_slot(dest["match_id"], dest["slot"], out)
                        changed = True

    def apply_results(self, results):
        if not isinstance(results, list) or not all(isinstance(r, dict) for r in results):
            raise validation_error(["results"])
        for r in results:
            if r.get("match_id") not in self.matches or not is_id(r.get("winner")):
                raise validation_error(["results"])
        pending = list(results)
        self.propagate()
        while pending:
            progress = False
            for r in list(pending):
                m = self.matches[r["match_id"]]
                if m["home"] is None or m["away"] is None:
                    if m["bye"] and r["winner"] == m["winner"]:
                        pending.remove(r)
                        progress = True
                    continue
                if r["winner"] not in (m["home"], m["away"]):
                    raise validation_error(["results"])
                if m["winner"] is None:
                    m["winner"] = r["winner"]
                    m["loser"] = m["away"] if r["winner"] == m["home"] else m["home"]
                    self.outputs[(m["match_id"], "winner")] = m["winner"]
                    self.outputs[(m["match_id"], "loser")] = m["loser"]
                    self.propagate()
                pending.remove(r)
                progress = True
            if not progress:
                raise validation_error(["results"])  # winner is not a participant of that match

    def seed_first_round(self, prefix, size):
        order = seed_order(size)
        n = len(self.teams)
        for i in range(size // 2):
            mid = f"{prefix}1M{i + 1}"
            s1, s2 = order[2 * i], order[2 * i + 1]
            lo, hi = min(s1, s2), max(s1, s2)
            self.set_slot(mid, "home", self.teams[lo - 1] if lo <= n else EMPTY)
            self.set_slot(mid, "away", self.teams[hi - 1] if hi <= n else EMPTY)


def _bracket_size(n):
    size = 1
    while size < n:
        size *= 2
    return max(size, 2)


def single_elim(teams, params):
    c = Checker()
    third = params.get("third_place_match", False)
    c.check(isinstance(third, bool), "third_place_match")
    results = params.get("results", [])
    c.check(isinstance(results, list), "results")
    c.raise_if_any()

    size = _bracket_size(len(teams))
    k = int(math.log2(size))
    b = Bracket(teams)
    for r in range(1, k + 1):
        for i in range(1, size // 2 ** r + 1):
            b.add(f"R{r}M{i}", "main", r, i)
    for r in range(1, k):
        for i in range(1, size // 2 ** r + 1):
            b.route(f"R{r}M{i}", "winner", f"R{r + 1}M{(i + 1) // 2}", "home" if i % 2 else "away")
    if third and k >= 2:
        b.add("TP", "third_place", k, 2)
        b.route(f"R{k - 1}M1", "loser", "TP", "home")
        b.route(f"R{k - 1}M2", "loser", "TP", "away")
    b.seed_first_round("R", size)
    b.apply_results(results)

    rounds = [{"round": r, "matches": [_public(b.matches[mid]) for mid in b.order
                                       if b.matches[mid]["round"] == r]} for r in range(1, k + 1)]
    return {"format": "single_elim", "bracket_size": size, "rounds": rounds}


def double_elim(teams, params):
    c = Checker()
    reset = params.get("bracket_reset", True)
    c.check(isinstance(reset, bool), "bracket_reset")
    results = params.get("results", [])
    c.check(isinstance(results, list), "results")
    c.raise_if_any()

    size = _bracket_size(len(teams))
    k = int(math.log2(size))
    b = Bracket(teams)
    common = {"conditional": False, "required": True}
    for r in range(1, k + 1):
        for i in range(1, size // 2 ** r + 1):
            b.add(f"WR{r}M{i}", "winners", r, i, common)
    lr_rounds = 2 * (k - 1)
    for j in range(1, k):
        count = size // 2 ** (j + 1)
        for rr in (2 * j - 1, 2 * j):
            for i in range(1, count + 1):
                b.add(f"LR{rr}M{i}", "losers", rr, i, common)
    b.add("GF1", "grand_final", 1, 1, common)
    if reset:
        b.add("GF2", "grand_final", 2, 1, {"conditional": True, "required": None})

    # winners bracket advancement
    for r in range(1, k):
        for i in range(1, size // 2 ** r + 1):
            b.route(f"WR{r}M{i}", "winner", f"WR{r + 1}M{(i + 1) // 2}", "home" if i % 2 else "away")
    b.route(f"WR{k}M1", "winner", "GF1", "home")
    # drops into the losers bracket: WR1 losers meet in LR1; WRr (r >= 2) losers drop into LR(2r-2)
    for i in range(1, size // 2 + 1):
        b.route(f"WR1M{i}", "loser", f"LR1M{(i + 1) // 2}", "home" if i % 2 else "away")
    for r in range(2, k + 1):
        for i in range(1, size // 2 ** r + 1):
            b.route(f"WR{r}M{i}", "loser", f"LR{2 * r - 2}M{i}", "away")
    # losers bracket advancement
    for j in range(1, k):
        count = size // 2 ** (j + 1)
        for i in range(1, count + 1):
            b.route(f"LR{2 * j - 1}M{i}", "winner", f"LR{2 * j}M{i}", "home")
            if j < k - 1:
                b.route(f"LR{2 * j}M{i}", "winner", f"LR{2 * j + 1}M{(i + 1) // 2}", "home" if i % 2 else "away")
    b.route(f"LR{lr_rounds}M1", "winner", "GF1", "away")
    if reset:
        b.route("GF1", "winner", "GF2", "home")
        b.route("GF1", "loser", "GF2", "away")

    b.seed_first_round("WR", size)
    b.apply_results(results)

    gf1 = b.matches["GF1"]
    if reset:
        gf2 = b.matches["GF2"]
        if gf2["home"] is None and gf2["away"] is None:
            # Before GF1 is played, GF2 lists the same two teams as GF1.
            gf2["home"], gf2["away"] = gf1["home"], gf1["away"]
            gf2["home_seed"], gf2["away_seed"] = gf1["home_seed"], gf1["away_seed"]
        gf2["required"] = None if gf1["winner"] is None else (gf1["winner"] == gf1["away"])

    winners = [{"round": r, "matches": [_public(b.matches[f"WR{r}M{i}"]) for i in range(1, size // 2 ** r + 1)]}
               for r in range(1, k + 1)]
    losers = []
    for j in range(1, k):
        count = size // 2 ** (j + 1)
        for rr in (2 * j - 1, 2 * j):
            losers.append({"round": rr, "matches": [_public(b.matches[f"LR{rr}M{i}"]) for i in range(1, count + 1)]})
    grand_final = [_public(gf1)] + ([_public(b.matches["GF2"])] if reset else [])
    return {"format": "double_elim", "bracket_size": size, "bracket_reset": reset,
            "winners": winners, "losers": losers, "grand_final": grand_final}


def _public(m):
    return dict(m)
