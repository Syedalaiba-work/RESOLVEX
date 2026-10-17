import pytest

from conftest import err

KABADDI = {
    "sport_id": "kabaddi",
    "name": "Kabaddi",
    "scoring_model": "event",
    "periods": {"count": 2, "duration_minutes": 20},
    "scoring_events": {"raid_point": {"points": 1}, "tackle_point": {"points": 1}, "all_out": {"points": 2}},
    "draw_allowed": False,
    "overtime": {"policy": "golden_score", "duration_minutes": 5},
    "tie_break_order": ["h2h_points", "h2h_diff", "overall_diff", "scored", "fair_play", "draw_lots"],
    "roster": {"min_squad_size": 7, "max_squad_size": 12, "required_positions": {"raider": 2, "defender": 3}},
}


def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_reset_default_response(client):
    r = client.post("/audit/v1/reset")
    assert r.status_code == 200
    assert r.json() == {
        "status": "reset_complete",
        "seed": 42,
        "sports": ["football", "basketball", "cricket", "esports"],
        "tenants": ["tenant-alpha", "tenant-beta"],
        "stock": {"var-jersey-001-M": 1, "var-jersey-001-L": 5},
    }


def test_reset_with_seed_and_stock_and_repeatable(client):
    body = {"seed": 7, "stock": {"var-jersey-001-M": 3}}
    first = client.post("/audit/v1/reset", json=body).json()
    second = client.post("/audit/v1/reset", json=body).json()
    assert first == second
    assert first["seed"] == 7
    assert first["stock"] == {"var-jersey-001-M": 3, "var-jersey-001-L": 5}


@pytest.mark.parametrize("body", [{"seed": "x"}, {"stock": {"var-jersey-001-M": -1}}, {"seed": True}])
def test_reset_validation(client, body):
    r = client.post("/audit/v1/reset", json=body)
    assert r.status_code == 400
    assert err(r) == "VALIDATION_ERROR"


def test_malformed_json_is_400(client):
    r = client.post("/audit/v1/sports", content=b"{not json", headers={"content-type": "application/json"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"
    assert r.json()["error"]["details"] == {"fields": []}


def test_body_over_1mb_is_413(client):
    r = client.post("/audit/v1/sports", content=b"x" * (1024 * 1024 + 10),
                    headers={"content-type": "application/json"})
    assert r.status_code == 413
    assert err(r) == "PAYLOAD_TOO_LARGE"


def test_create_mystery_sport_then_duplicate(fresh):
    r = fresh.post("/audit/v1/sports", json=KABADDI)
    assert r.status_code == 201
    body = r.json()
    assert body["sport_id"] == "kabaddi" and body["status"] == "created"
    assert body["config"]["scoring_events"]["all_out"] == {"points": 2}
    r2 = fresh.post("/audit/v1/sports", json=KABADDI)
    assert r2.status_code == 409 and err(r2) == "SPORT_EXISTS"


def test_seeded_sport_id_conflicts(fresh):
    r = fresh.post("/audit/v1/sports", json={**KABADDI, "sport_id": "football"})
    assert r.status_code == 409 and err(r) == "SPORT_EXISTS"


def test_reset_removes_custom_sports(fresh):
    assert fresh.post("/audit/v1/sports", json=KABADDI).status_code == 201
    fresh.post("/audit/v1/reset")
    assert fresh.post("/audit/v1/sports", json=KABADDI).status_code == 201


@pytest.mark.parametrize(
    "patch, field",
    [
        ({"sport_id": "x'; DROP TABLE sports;--"}, "sport_id"),
        ({"sport_id": "A"}, "sport_id"),
        ({"name": ""}, "name"),
        ({"scoring_model": "points"}, "scoring_model"),
        ({"periods": {"count": 0, "duration_minutes": 20}}, "periods"),
        ({"scoring_events": {}}, "scoring_events"),
        ({"scoring_events": {"Bad Key": {"points": 1}}}, "scoring_events"),
        ({"scoring_events": {"raid": {"points": 0}}}, "scoring_events"),
        ({"draw_allowed": "no"}, "draw_allowed"),
        ({"overtime": {"policy": "coin_toss"}}, "overtime"),
        ({"tie_break_order": ["h2h_points", "h2h_points"]}, "tie_break_order"),
        ({"roster": {"min_squad_size": 9, "max_squad_size": 3, "required_positions": {}}}, "roster"),
    ],
)
def test_sport_validation_lists_bad_field(fresh, patch, field):
    r = fresh.post("/audit/v1/sports", json={**KABADDI, **patch})
    assert r.status_code == 400
    assert err(r) == "VALIDATION_ERROR"
    assert field in r.json()["error"]["details"]["fields"]


def test_round_model_requires_odd_best_of(fresh):
    body = {**KABADDI, "sport_id": "chess_bo", "scoring_model": "round",
            "periods": {"best_of": 4}, "scoring_events": {"map_win": {"rounds": 1}}}
    r = fresh.post("/audit/v1/sports", json=body)
    assert r.status_code == 400 and "periods" in r.json()["error"]["details"]["fields"]
    body["periods"] = {"best_of": 5}
    assert fresh.post("/audit/v1/sports", json=body).status_code == 201


def test_unknown_route_uses_error_shape(client):
    r = client.get("/audit/v1/nope")
    assert r.status_code == 404
    assert "error" in r.json()
