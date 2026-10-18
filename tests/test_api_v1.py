import pytest

from conftest import err


def login(client, who):
    r = client.post("/api/v1/auth/login", json={"email": f"{who}@nascon.test", "password": "Nascon@26"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture
def api(fresh):
    from app import main
    main._hits.clear()  # the /api/v1 rate limiter is per IP; tests share one client
    return fresh


def test_requires_token(api):
    assert api.get("/api/v1/fixtures").status_code == 401


def test_fixtures_matches_and_standings_for_viewer(api):
    h = login(api, "viewer")
    fx = api.get("/api/v1/fixtures", headers=h).json()
    assert len(fx) == 7  # six demo fixtures + Part II 5.2 match-m1 (league-alpha-1, in progress)
    statuses = {f["match_id"]: f["status"] for f in fx}
    assert statuses["la1-m1"] == "completed" and statuses["la1-m5"] == "in_progress" and statuses["la1-m6"] == "upcoming"
    m1 = next(f for f in fx if f["match_id"] == "la1-m1")
    assert (m1["home_name"], m1["home_score"], m1["away_score"]) == ("Alpha United", 2, 1)
    assert m1["scoring_events"] == ["goal"]  # cached with the fixture so offline scoring works
    detail = api.get("/api/v1/matches/la1-m1", headers=h).json()
    assert detail["outcome"] == "home_win" and detail["pinned_product"]["product_id"] == "prod-jersey-001"
    assert detail["scoring_events"] == ["goal"]
    st = api.get("/api/v1/standings/league-alpha-1", headers=h).json()
    assert st["names"]["club-alpha-1"] == "Alpha United" and len(st["table"]) == 4
    assert st["table"][0]["team_id"] == "club-alpha-1"


def test_match_detail_lists_scoring_events_from_sport_config(api):
    sport = {"sport_id": "kabaddi", "name": "Kabaddi", "scoring_model": "event",
             "periods": {"count": 2, "duration_minutes": 20},
             "scoring_events": {"raid_point": {"points": 1}, "all_out": {"points": 2}},
             "draw_allowed": False, "overtime": {"policy": "golden_score"},
             "roster": {"min_squad_size": 7, "max_squad_size": 12, "required_positions": {}}}
    assert api.post("/audit/v1/sports", json=sport).status_code == 201
    init = {"event_id": "k-0", "match_id": "k-m1", "type": "match_init",
            "payload": {"sport_id": "kabaddi", "home_team_id": "h", "away_team_id": "a"}}
    assert api.post("/audit/v1/events", json=init).status_code == 201
    detail = api.get("/api/v1/matches/k-m1", headers=login(api, "admin")).json()
    assert detail["scoring_events"] == ["all_out", "raid_point"]


def test_clubs_products_and_tenant_isolation(api):
    h = login(api, "player")
    assert {c["club_id"] for c in api.get("/api/v1/clubs", headers=h).json()} == {"club-alpha-1", "club-alpha-2"}
    club = api.get("/api/v1/clubs/club-alpha-1", headers=h).json()
    assert club["home_venue"]["name"] == "Alpha Arena" and len(club["staff"]) == 3
    assert any(p["player_id"] == "player-alpha-1" for p in club["roster"])
    assert api.get("/api/v1/clubs/club-beta-1", headers=h).status_code == 403
    products = api.get("/api/v1/products", headers=h).json()
    assert products[0]["variants"][0]["price_minor"] == 450000


def test_checkout_forces_customer(api):
    h = login(api, "viewer")
    body = {"order_id": "app-1", "customer_id": "spoofed", "items": [{"variant_id": "var-jersey-001-L", "quantity": 1}],
            "discount_code": None, "payment": {"token": "tok_success"}}
    r = api.post("/api/v1/checkout", json=body, headers=h)
    assert r.status_code == 201 and r.json()["receipt"]["payload"]["customer_id"] == "viewer@nascon.test"


def test_scoring_entry_only_for_own_league_organizer(api):
    ev = {"event_id": "app-g1", "match_id": "la1-m5", "type": "score",
          "payload": {"team_id": "club-alpha-1", "event_type": "goal"}}
    assert err(api.post("/api/v1/events", json=ev, headers=login(api, "viewer"))) == "FORBIDDEN"
    assert err(api.post("/api/v1/events", json=ev, headers=login(api, "manager"))) == "FORBIDDEN"
    r = api.post("/api/v1/events", json=ev, headers=login(api, "organizer"))
    assert r.status_code == 201
    comp = {"event_id": "app-c1", "match_id": "la1-m5", "type": "compensation",
            "payload": {"compensates": "app-g1", "reason": "offside"}}
    assert api.post("/api/v1/events", json=comp, headers=login(api, "organizer")).status_code == 201


def test_roster_management_for_manager(api):
    assert api.get("/api/v1/roster/league-alpha-1", headers=login(api, "viewer")).status_code == 403
    h = login(api, "manager")
    view = api.get("/api/v1/roster/league-alpha-1", headers=h).json()
    assert {s["squad_id"] for s in view["squads"]} == {"sq-alpha-1", "sq-alpha-2"}
    from datetime import date
    body = {"request_id": "app-tr1", "league_id": "league-alpha-1", "player_id": "pa1-05", "type": "loan",
            "from_squad_id": "sq-alpha-1", "to_squad_id": "sq-alpha-2", "effective_date": date.today().isoformat(),
            "loan_end_date": "2099-01-01", "reason": "Game time", "requested_by": "spoof"}
    r = api.post("/api/v1/roster/transfer", json=body, headers=h)
    assert r.status_code == 201 and r.json()["audit_entry"]["who"] == "manager@nascon.test"
    back = {**body, "request_id": "app-tr2", "player_id": "pa2-03", "type": "transfer", "loan_end_date": None,
            "from_squad_id": "sq-alpha-2", "to_squad_id": "sq-alpha-1"}
    assert err(api.post("/api/v1/roster/transfer", json=back, headers=h)) == "FORBIDDEN"  # not own club


def test_sync_applies_role_rules(api):
    action = {"action_id": "q1", "type": "score_event", "queued_at": "2026-10-17T11:00:00Z", "base_version": 2,
              "payload": {"event_id": "app-off-1", "match_id": "la1-m5", "type": "score",
                          "payload": {"team_id": "club-alpha-1", "event_type": "goal"}}}
    r = api.post("/api/v1/sync", json={"device_id": "phone-1", "actions": [action]}, headers=login(api, "viewer"))
    assert r.json()["results"][0]["error_code"] == "FORBIDDEN"
    r = api.post("/api/v1/sync", json={"device_id": "phone-2", "actions": [action]}, headers=login(api, "organizer"))
    res = r.json()["results"][0]
    assert res["status"] == "applied" and res["resolution"] == "appended" and res["server_version"] == 3
