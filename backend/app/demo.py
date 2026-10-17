"""Demo data for the mobile app desk check, recreated on every reset.

Uses the same domain services as the API (no special-case code paths), so it also exercises them.
"""
from datetime import datetime, timedelta, timezone

from app import roster, scoring
from app.db import J, tx

DEMO_LEAGUE = "league-alpha-1"
TEAM_NAMES = {
    "club-alpha-1": "Alpha United", "club-alpha-2": "Alpha Rovers",
    "alpha-falcons": "Alpha Falcons", "alpha-tigers": "Alpha Tigers",
}
FIXTURES = [  # match_id, home, away, day offset, final score (None = not finished)
    ("la1-m1", "club-alpha-1", "club-alpha-2", -6, (2, 1)),
    ("la1-m2", "alpha-falcons", "alpha-tigers", -6, (0, 0)),
    ("la1-m3", "club-alpha-1", "alpha-falcons", -3, (1, 1)),
    ("la1-m4", "club-alpha-2", "alpha-tigers", -3, (3, 2)),
    ("la1-m5", "club-alpha-1", "alpha-tigers", 0, "live"),
    ("la1-m6", "club-alpha-2", "alpha-falcons", 2, None),
]


def seed_demo() -> None:
    base = datetime.now(timezone.utc).replace(hour=15, minute=0, second=0, microsecond=0)
    scoring.register_league({
        "league_id": DEMO_LEAGUE, "sport_id": "football", "teams": list(TEAM_NAMES),
        "fixtures": [{"match_id": m, "home": h, "away": a} for m, h, a, _, _ in FIXTURES],
        "qualification": {"spots": 2},
    })
    schedule = {}
    for mid, home, away, offset, score in FIXTURES:
        schedule[mid] = (base + timedelta(days=offset)).strftime("%Y-%m-%dT%H:%M:%SZ")
        if score is None:
            continue
        _ev(f"{mid}-start", mid, "match_start", {})
        goals = (1, 0) if score == "live" else score
        for i in range(goals[0]):
            _ev(f"{mid}-h{i}", mid, "score", {"team_id": home, "event_type": "goal"})
        for i in range(goals[1]):
            _ev(f"{mid}-a{i}", mid, "score", {"team_id": away, "event_type": "goal"})
        if score != "live":
            _ev(f"{mid}-end", mid, "match_end", {})

    today = datetime.now(timezone.utc).date()
    players = [
        ("player-alpha-1", "Ahmed Raza", "gk", "sq-alpha-1", "captain"),
        ("pa1-02", "Usman Ghani", "df", "sq-alpha-1", "vice_captain"),
        ("pa1-03", "Hamza Iqbal", "df", "sq-alpha-1", "starter"),
        ("pa1-04", "Saad Mir", "mf", "sq-alpha-1", "starter"),
        ("pa1-05", "Zain Abbas", "fw", "sq-alpha-1", "substitute"),
        ("player-alpha-2", "Bilal Shah", "fw", "sq-alpha-2", "starter"),
        ("pa2-02", "Omar Farooq", "gk", "sq-alpha-2", "captain"),
        ("pa2-03", "Ali Haider", "df", "sq-alpha-2", "starter"),
    ]
    roster.setup({
        "league": {"league_id": DEMO_LEAGUE, "tenant_id": "tenant-alpha", "sport_id": "football",
                   "transfer_window": {"open": (today - timedelta(days=30)).isoformat(),
                                       "close": (today + timedelta(days=30)).isoformat()}},
        "squads": [{"squad_id": "sq-alpha-1", "club_id": "club-alpha-1", "tenant_id": "tenant-alpha",
                    "name": "Alpha United"},
                   {"squad_id": "sq-alpha-2", "club_id": "club-alpha-2", "tenant_id": "tenant-alpha",
                    "name": "Alpha Rovers"}],
        "players": [{"player_id": p, "name": n, "position": pos, "squad_id": s, "role": r}
                    for p, n, pos, s, r in players],
        "matches_in_progress": [],
    })
    with tx() as conn:
        conn.execute("INSERT INTO meta VALUES ('team_names', %s), ('schedule', %s), ('pinned', %s)",
                     (J(TEAM_NAMES), J(schedule), J({m: "prod-jersey-001" for m, *_ in FIXTURES})))


def _ev(event_id, match_id, etype, payload):
    status, _ = scoring.append_event({"event_id": event_id, "match_id": match_id, "type": etype, "payload": payload})
    assert status == 201
