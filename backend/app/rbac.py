"""Five-tier RBAC with tenant isolation (spec 5.13, FR-5.1).

Authorization is policy-as-code: POLICY maps (action, role) to a rule evaluated against the token's
scope and the target's tenant/ownership. Tokens are HS256 JWTs whose signature, algorithm and expiry
are always verified.
"""
import hashlib
import os
import time

import jwt
from fastapi import Request

from app.core import ApiError, salt
from app.db import tx
from app.seed import verify_password

ROLES = ["super_admin", "league_organizer", "club_manager", "player", "viewer"]
TOKEN_TTL_S = 8 * 3600
DEMO_EMAILS = {
    "super_admin": "admin@nascon.test", "league_organizer": "organizer@nascon.test",
    "club_manager": "manager@nascon.test", "player": "player@nascon.test", "viewer": "viewer@nascon.test",
}


def _secret() -> str:
    explicit = os.environ.get("JWT_SECRET")
    if explicit:
        return explicit
    # Stable across restarts, never committed: derived from the per-team salt.
    return hashlib.sha256(("nascon-jwt|" + salt()).encode("utf-8")).hexdigest()


def issue_token(user: dict) -> str:
    now = int(time.time())
    claims = {"sub": user["email"], "role": user["role"], "tenant_id": user["tenant_id"],
              "league_id": user["league_id"], "club_id": user["club_id"], "player_id": user["player_id"],
              "iat": now, "exp": now + TOKEN_TTL_S}
    return jwt.encode(claims, _secret(), algorithm="HS256")


def unauthenticated(message="Missing or invalid token."):
    return ApiError(401, "UNAUTHENTICATED", message)


def authenticate(request: Request) -> dict:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise unauthenticated("Missing bearer token.")
    token = header[7:].strip()
    try:
        # algorithms is pinned: "none" and any other algorithm are rejected; exp is required.
        claims = jwt.decode(token, _secret(), algorithms=["HS256"], options={"require": ["exp", "sub", "role"]})
    except jwt.PyJWTError:
        raise unauthenticated()
    if claims.get("role") not in ROLES:
        raise unauthenticated()
    return claims


def user_by_email(conn, email):
    return conn.execute("SELECT * FROM users WHERE email = %s", (email,)).fetchone()


def login(email, password) -> dict:
    with tx() as conn:
        user = user_by_email(conn, email) if isinstance(email, str) else None
        if user is None or not isinstance(password, str) or not verify_password(password, user["password_hash"]):
            raise unauthenticated("Email or password is incorrect.")
        return {"token": issue_token(user), **profile(conn, user)}


def profile(conn, user) -> dict:
    tenant = None
    if user["tenant_id"]:
        t = conn.execute("SELECT * FROM tenants WHERE tenant_id = %s", (user["tenant_id"],)).fetchone()
        tenant = {"tenant_id": t["tenant_id"], "name": t["name"], "branding": t["branding"]}
    return {
        "user": {k: user[k] for k in ("email", "role", "display_name", "tenant_id", "league_id", "club_id", "player_id")},
        "tenant": tenant,
    }


def rbac_matrix() -> dict:
    with tx() as conn:
        tokens = {role: issue_token(user_by_email(conn, email)) for role, email in DEMO_EMAILS.items()}
    return {
        "tokens": tokens,
        "context": {
            "tenant_id": "tenant-alpha", "foreign_tenant_id": "tenant-beta",
            "own_league_id": "league-alpha-1", "other_league_id": "league-alpha-2",
            "foreign_league_id": "league-beta-1",
            "own_club_id": "club-alpha-1", "other_club_id": "club-alpha-2", "foreign_club_id": "club-beta-1",
            "own_player_id": "player-alpha-1", "other_player_id": "player-alpha-2",
            "foreign_player_id": "player-beta-1",
        },
    }


# --- policy-as-code ---------------------------------------------------------------------------------
# Each rule gets (claims, target) where target = {"tenant_id", "league_id"/"club_id"/"player_id", ...}.

def _super(c, t):
    return c["role"] == "super_admin"


def _same_tenant(c, t):
    return t is not None and c.get("tenant_id") == t.get("tenant_id")


def _own_league(c, t):
    return _same_tenant(c, t) and c.get("league_id") == t["league_id"]


def _own_club(c, t):
    return _same_tenant(c, t) and c.get("club_id") == t["club_id"]


def _own_clubs_player(c, t):
    return _same_tenant(c, t) and c.get("club_id") is not None and c.get("club_id") == t.get("club_id")


def _self_player(c, t):
    return _same_tenant(c, t) and c.get("player_id") == t["player_id"]


POLICY = {
    "tenants.create": {"super_admin": _super},
    "league.fixtures.write": {"super_admin": _super, "league_organizer": _own_league},
    "club.roster.write": {"super_admin": _super, "club_manager": _own_club},
    "club.products.write": {"super_admin": _super, "club_manager": _own_club},
    "player.update": {"super_admin": _super, "club_manager": _own_clubs_player, "player": _self_player},
    "club.read": {role: (_super if role == "super_admin" else _same_tenant) for role in ROLES},
    "platform.config.read": {"super_admin": _super},
    # production (mobile) routes
    "league.events.write": {"super_admin": _super, "league_organizer": _own_league},
    "tenant.read": {role: (_super if role == "super_admin" else _same_tenant) for role in ROLES},
}


def allowed(action: str, claims: dict, target: dict | None) -> bool:
    rule = POLICY.get(action, {}).get(claims["role"])
    return bool(rule and rule(claims, target))


def authorize(action: str, claims: dict, target: dict | None):
    if not allowed(action, claims, target):
        raise ApiError(403, "FORBIDDEN", "You are not allowed to perform this action.", {"action": action})


def load_target(kind: str, target_id: str) -> dict:
    table, key = {"league": ("leagues", "league_id"), "club": ("clubs", "club_id"),
                  "player": ("players", "player_id")}[kind]
    with tx() as conn:
        row = conn.execute(f"SELECT * FROM {table} WHERE {key} = %s", (target_id,)).fetchone()
    if row is None:
        code = {"league": "LEAGUE_NOT_FOUND", "club": "CLUB_NOT_FOUND", "player": "PLAYER_NOT_FOUND"}[kind]
        raise ApiError(404, code, f"{kind.capitalize()} {target_id} does not exist.", {f"{kind}_id": target_id})
    return dict(row)


def probe(request: Request, action: str, kind: str | None = None, target_id: str | None = None) -> dict:
    claims = authenticate(request)  # 401 first
    target = load_target(kind, target_id) if kind else None
    authorize(action, claims, target)
    return {"authorized": True}
