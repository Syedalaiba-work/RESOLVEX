"""Data-driven sport configuration (spec 5.6). No sport or event name is ever special-cased."""
import re

from app.core import ApiError, Checker, is_int, is_str
from app.db import J, tx

TIE_BREAK_TOKENS = ["h2h_points", "h2h_diff", "overall_diff", "scored", "fair_play", "draw_lots"]
OVERTIME_POLICIES = {"none", "extra_time", "shootout", "golden_score", "super_over"}
SPORT_ID_RE = re.compile(r"^[a-z0-9_-]{2,40}$")
EVENT_KEY_RE = re.compile(r"^[a-z0-9_]{1,40}$")


def _int_ge(value, minimum: int) -> bool:
    return is_int(value) and value >= minimum


def validate_sport(body: dict) -> dict:
    """Returns the normalized config to store, or raises VALIDATION_ERROR listing every bad field."""
    c = Checker()
    sport_id = body.get("sport_id")
    c.check(is_str(sport_id) and bool(SPORT_ID_RE.match(sport_id)), "sport_id")
    name = body.get("name")
    c.check(is_str(name) and 1 <= len(name) <= 80, "name")
    model = body.get("scoring_model")
    c.check(model in ("event", "innings", "round"), "scoring_model")

    periods = body.get("periods")
    if not isinstance(periods, dict):
        c.check(False, "periods")
    elif model == "event":
        c.check(_int_ge(periods.get("count"), 1) and _int_ge(periods.get("duration_minutes"), 1), "periods")
    elif model == "innings":
        keys = ["innings_per_team", "overs_per_innings", "balls_per_over", "wickets_per_innings"]
        c.check(all(_int_ge(periods.get(k), 1) for k in keys), "periods")
    elif model == "round":
        best_of = periods.get("best_of")
        c.check(_int_ge(best_of, 1) and best_of % 2 == 1, "periods")

    events = body.get("scoring_events")
    if not isinstance(events, dict) or not events:
        c.check(False, "scoring_events")
    else:
        for key, value in events.items():
            ok = bool(EVENT_KEY_RE.match(key)) and isinstance(value, dict)
            if ok and model == "event":
                ok = _int_ge(value.get("points"), 1)
            elif ok and model == "innings":
                ok = (_int_ge(value.get("runs"), 0) and isinstance(value.get("legal_ball"), bool)
                      and isinstance(value.get("wicket"), bool))
            elif ok and model == "round":
                ok = _int_ge(value.get("rounds"), 1)
            if not c.check(ok, "scoring_events"):
                break

    c.check(isinstance(body.get("draw_allowed"), bool), "draw_allowed")

    overtime = body.get("overtime")
    c.check(
        isinstance(overtime, dict) and overtime.get("policy") in OVERTIME_POLICIES
        and ("duration_minutes" not in overtime or _int_ge(overtime.get("duration_minutes"), 0)),
        "overtime",
    )

    order = body.get("tie_break_order", None)
    if order is not None:
        c.check(
            isinstance(order, list) and all(t in TIE_BREAK_TOKENS for t in order) and len(set(order)) == len(order),
            "tie_break_order",
        )

    roster = body.get("roster")
    roster_ok = isinstance(roster, dict)
    if roster_ok:
        mn, mx, req = roster.get("min_squad_size"), roster.get("max_squad_size"), roster.get("required_positions")
        roster_ok = (_int_ge(mn, 1) and _int_ge(mx, 1) and mn <= mx and isinstance(req, dict)
                     and all(is_str(k) and _int_ge(v, 0) for k, v in req.items()))
    c.check(roster_ok, "roster")
    c.raise_if_any()

    config = {
        "sport_id": sport_id,
        "name": name,
        "scoring_model": model,
        "periods": periods,
        "scoring_events": events,
        "draw_allowed": body["draw_allowed"],
        "overtime": overtime,
        "tie_break_order": list(order) if order is not None else list(TIE_BREAK_TOKENS),
        "roster": roster,
    }
    return config


def create_sport(body: dict) -> dict:
    config = validate_sport(body)
    with tx() as conn:
        inserted = conn.execute(
            "INSERT INTO sports (sport_id, config) VALUES (%s, %s) ON CONFLICT DO NOTHING RETURNING sport_id",
            (config["sport_id"], J(config)),
        ).fetchone()
    if inserted is None:
        raise ApiError(409, "SPORT_EXISTS", f"Sport {config['sport_id']} already exists.",
                       {"sport_id": config["sport_id"]})
    return {"sport_id": config["sport_id"], "status": "created", "config": config}


def get_sport(conn, sport_id) -> dict | None:
    row = conn.execute("SELECT config FROM sports WHERE sport_id = %s", (sport_id,)).fetchone()
    return row["config"] if row else None


def effective_tie_break_order(order: list[str]) -> list[str]:
    """draw_lots is always applied last, even if omitted."""
    return [t for t in order if t != "draw_lots"] + ["draw_lots"]


# Baseline sports (spec 5.5), stored as ordinary data in the same schema as POST /sports.
SEED_SPORTS = [
    {
        "sport_id": "football", "name": "Football", "scoring_model": "event",
        "periods": {"count": 2, "duration_minutes": 45},
        "scoring_events": {"goal": {"points": 1}},
        "draw_allowed": True, "overtime": {"policy": "none"},
        "roster": {"min_squad_size": 11, "max_squad_size": 25, "required_positions": {"gk": 1}},
    },
    {
        "sport_id": "basketball", "name": "Basketball", "scoring_model": "event",
        "periods": {"count": 4, "duration_minutes": 12},
        "scoring_events": {"free_throw": {"points": 1}, "two_pointer": {"points": 2}, "three_pointer": {"points": 3}},
        "draw_allowed": False, "overtime": {"policy": "extra_time", "duration_minutes": 5},
        "roster": {"min_squad_size": 5, "max_squad_size": 15, "required_positions": {}},
    },
    {
        "sport_id": "cricket", "name": "Cricket", "scoring_model": "innings",
        "periods": {"innings_per_team": 1, "overs_per_innings": 20, "balls_per_over": 6, "wickets_per_innings": 10},
        "scoring_events": {
            "dot_ball": {"runs": 0, "legal_ball": True, "wicket": False},
            "single": {"runs": 1, "legal_ball": True, "wicket": False},
            "two": {"runs": 2, "legal_ball": True, "wicket": False},
            "four": {"runs": 4, "legal_ball": True, "wicket": False},
            "six": {"runs": 6, "legal_ball": True, "wicket": False},
            "wide": {"runs": 1, "legal_ball": False, "wicket": False},
            "no_ball": {"runs": 1, "legal_ball": False, "wicket": False},
            "wicket": {"runs": 0, "legal_ball": True, "wicket": True},
        },
        "draw_allowed": True, "overtime": {"policy": "super_over"},
        "roster": {"min_squad_size": 11, "max_squad_size": 18, "required_positions": {"wicketkeeper": 1}},
    },
    {
        "sport_id": "esports", "name": "Esports", "scoring_model": "round",
        "periods": {"best_of": 3},
        "scoring_events": {"round_win": {"rounds": 1}},
        "draw_allowed": False, "overtime": {"policy": "none"},
        "roster": {"min_squad_size": 5, "max_squad_size": 8, "required_positions": {}},
    },
]
