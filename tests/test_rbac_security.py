import base64
import json
import time

import jwt
import pytest

from app.rbac import _secret
from conftest import err

ROLES = ["super_admin", "league_organizer", "club_manager", "player", "viewer"]
A, D = 200, 403

# (method, path template, target key in context or None, expected per role in ROLES order) - spec 5.13 table
MATRIX = [
    ("POST", "/audit/v1/rbac/tenants", None, [A, D, D, D, D]),
    ("POST", "/audit/v1/rbac/leagues/{}/fixtures", "own_league_id", [A, A, D, D, D]),
    ("POST", "/audit/v1/rbac/leagues/{}/fixtures", "other_league_id", [A, D, D, D, D]),
    ("POST", "/audit/v1/rbac/leagues/{}/fixtures", "foreign_league_id", [A, D, D, D, D]),
    ("POST", "/audit/v1/rbac/clubs/{}/roster", "own_club_id", [A, D, A, D, D]),
    ("POST", "/audit/v1/rbac/clubs/{}/roster", "other_club_id", [A, D, D, D, D]),
    ("POST", "/audit/v1/rbac/clubs/{}/roster", "foreign_club_id", [A, D, D, D, D]),
    ("POST", "/audit/v1/rbac/clubs/{}/products", "own_club_id", [A, D, A, D, D]),
    ("POST", "/audit/v1/rbac/clubs/{}/products", "other_club_id", [A, D, D, D, D]),
    ("POST", "/audit/v1/rbac/clubs/{}/products", "foreign_club_id", [A, D, D, D, D]),
    ("PATCH", "/audit/v1/rbac/players/{}", "own_player_id", [A, D, A, A, D]),
    ("PATCH", "/audit/v1/rbac/players/{}", "other_player_id", [A, D, D, D, D]),
    ("PATCH", "/audit/v1/rbac/players/{}", "foreign_player_id", [A, D, D, D, D]),
    ("GET", "/audit/v1/rbac/clubs/{}", "own_club_id", [A, A, A, A, A]),
    ("GET", "/audit/v1/rbac/clubs/{}", "other_club_id", [A, A, A, A, A]),
    ("GET", "/audit/v1/rbac/clubs/{}", "foreign_club_id", [A, D, D, D, D]),
    ("GET", "/audit/v1/rbac/platform/config", None, [A, D, D, D, D]),
]


@pytest.fixture(scope="module")
def matrix(client):
    client.post("/audit/v1/reset")
    r = client.post("/audit/v1/rbac-matrix")
    assert r.status_code == 200
    return r.json()


def call(client, method, path, token=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.request(method, path, headers=headers, json={} if method != "GET" else None)


def test_matrix_shape(matrix):
    assert set(matrix["tokens"]) == set(ROLES)
    assert matrix["context"]["own_league_id"] == "league-alpha-1"
    assert matrix["context"]["foreign_player_id"] == "player-beta-1"


@pytest.mark.parametrize("method, template, key, expected", MATRIX)
def test_probe_matrix(client, matrix, method, template, key, expected):
    path = template.format(matrix["context"][key]) if key else template
    for role, want in zip(ROLES, expected):
        r = call(client, method, path, matrix["tokens"][role])
        assert r.status_code == want, (role, path, r.json())
        if want == 200:
            assert r.json() == {"authorized": True}
        else:
            assert err(r) == "FORBIDDEN"


def _b64(obj):
    return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()


def test_missing_and_bad_tokens_are_401(client, matrix):
    path = "/audit/v1/rbac/platform/config"
    assert err(call(client, "GET", path)) == "UNAUTHENTICATED"
    assert call(client, "GET", path).status_code == 401
    good = matrix["tokens"]["super_admin"]
    head, payload, sig = good.split(".")
    tampered = f"{head}.{payload}.{sig[:-2]}{'AA' if sig[-2:] != 'AA' else 'BB'}"
    assert call(client, "GET", path, tampered).status_code == 401
    claims = jwt.decode(good, options={"verify_signature": False})
    none_token = f"{_b64({'alg': 'none', 'typ': 'JWT'})}.{_b64(claims)}."
    assert call(client, "GET", path, none_token).status_code == 401
    forged_payload = f"{head}.{_b64({**claims, 'role': 'super_admin', 'tenant_id': None})}.{sig}"
    assert call(client, "GET", path, forged_payload).status_code == 401
    expired = jwt.encode({**claims, "exp": int(time.time()) - 10}, _secret(), algorithm="HS256")
    assert call(client, "GET", path, expired).status_code == 401
    other_key = jwt.encode(claims, "not-the-secret", algorithm="HS256")
    assert call(client, "GET", path, other_key).status_code == 401
    assert call(client, "GET", path, "garbage").status_code == 401


def test_tokens_valid_for_at_least_an_hour(matrix):
    claims = jwt.decode(matrix["tokens"]["viewer"], options={"verify_signature": False})
    assert claims["exp"] - time.time() >= 3600


def test_nonexistent_target_is_404_not_403(client, matrix):
    r = call(client, "GET", "/audit/v1/rbac/clubs/club-ghost", matrix["tokens"]["viewer"])
    assert r.status_code == 404


def test_login_and_wrong_password(client):
    client.post("/audit/v1/reset")
    r = client.post("/api/v1/auth/login", json={"email": "manager@nascon.test", "password": "Nascon@26"})
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["role"] == "club_manager" and body["user"]["club_id"] == "club-alpha-1"
    assert body["tenant"]["tenant_id"] == "tenant-alpha" and "primary_color" in body["tenant"]["branding"]
    assert call(client, "POST", "/audit/v1/rbac/clubs/club-alpha-1/roster", body["token"]).status_code == 200
    bad = client.post("/api/v1/auth/login", json={"email": "manager@nascon.test", "password": "nope"})
    assert bad.status_code == 401 and err(bad) == "UNAUTHENTICATED"


def test_all_demo_accounts_exist_after_reset(client):
    client.post("/audit/v1/reset")
    for email in ("admin", "organizer", "manager", "player", "viewer"):
        r = client.post("/api/v1/auth/login", json={"email": f"{email}@nascon.test", "password": "Nascon@26"})
        assert r.status_code == 200, email


def test_rate_limit_on_api_v1_only(client):
    from app import main
    main._hits.clear()
    codes = [client.get("/api/v1/ping").status_code for _ in range(150)]
    assert codes[0] == 200 and codes.count(429) >= 40
    r = client.get("/api/v1/ping")
    assert r.status_code == 429 and int(r.headers["Retry-After"]) >= 1 and err(r) == "RATE_LIMITED"
    # audit and health are exempt
    assert all(client.get("/health").status_code == 200 for _ in range(150))
    main._hits.clear()
    assert client.get("/api/v1/ping").json() == {"pong": True}
