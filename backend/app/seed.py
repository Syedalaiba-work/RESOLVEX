"""POST /audit/v1/reset: wipe all state and re-create the exact baseline of spec 5.5."""
import hashlib
import os

from app.core import ApiError, Checker, is_int
from app.db import ALL_TABLES, J, tx
from app.sports import SEED_SPORTS, validate_sport

DEFAULT_SEED = 42
DEFAULT_STOCK = {"var-jersey-001-M": 1, "var-jersey-001-L": 5}
DEMO_PASSWORD = "Nascon@26"

TENANTS = [
    ("tenant-alpha", "Alpha Sports", {"primary_color": "#0B3D91", "accent_color": "#F5A623", "logo_text": "AS"}),
    ("tenant-beta", "Beta Athletics", {"primary_color": "#1B5E20", "accent_color": "#FFC107", "logo_text": "BA"}),
]
LEAGUES = [
    ("league-alpha-1", "tenant-alpha", "Alpha Premier League", "football"),
    ("league-alpha-2", "tenant-alpha", "Alpha Basketball Cup", "basketball"),
    ("league-beta-1", "tenant-beta", "Beta Championship", "football"),
]
CLUBS = [
    ("club-alpha-1", "tenant-alpha", "Alpha United", {
        "home_venue": {"name": "Alpha Arena", "lat": 33.6844, "lng": 73.0479},
        "social": {"x": "@alphautd", "instagram": "alpha.united"},
        "staff": [{"role": "coach", "name": "Kamran Ali"}, {"role": "manager", "name": "Sara Khan"},
                  {"role": "physio", "name": "Hina Raza"}],
        "history": [{"season": "2025", "position": 2, "points": 61}, {"season": "2024", "position": 4, "points": 52}],
    }),
    ("club-alpha-2", "tenant-alpha", "Alpha Rovers", {
        "home_venue": {"name": "Rovers Ground", "lat": 33.7, "lng": 73.06},
        "social": {"x": "@alpharovers"},
        "staff": [{"role": "coach", "name": "Usman Tariq"}],
        "history": [{"season": "2025", "position": 5, "points": 48}],
    }),
    ("club-beta-1", "tenant-beta", "Beta City", {
        "home_venue": {"name": "Beta Stadium", "lat": 31.5204, "lng": 74.3587},
        "social": {"x": "@betacity"},
        "staff": [{"role": "coach", "name": "Ayesha Malik"}],
        "history": [],
    }),
]
PLAYERS = [
    ("player-alpha-1", "tenant-alpha", "club-alpha-1", "Ahmed Raza", "gk", "captain"),
    ("player-alpha-2", "tenant-alpha", "club-alpha-2", "Bilal Shah", "fw", "starter"),
    ("player-beta-1", "tenant-beta", "club-beta-1", "Faisal Noor", "df", "starter"),
    ("player-beta-2", "tenant-beta", "club-beta-1", "Hassan Iqbal", "mf", "starter"),  # Part II 5.2
]
USERS = [
    # email, role, tenant, league, club, player, display name
    ("admin@nascon.test", "super_admin", None, None, None, None, "Platform Admin"),
    ("organizer@nascon.test", "league_organizer", "tenant-alpha", "league-alpha-1", None, None, "League Organizer"),
    ("manager@nascon.test", "club_manager", "tenant-alpha", None, "club-alpha-1", None, "Club Manager"),
    ("player@nascon.test", "player", "tenant-alpha", None, "club-alpha-1", "player-alpha-1", "Ahmed Raza"),
    ("viewer@nascon.test", "viewer", "tenant-alpha", None, None, None, "Viewer"),
]


def hash_password(password: str, salt_bytes: bytes | None = None) -> str:
    salt_bytes = salt_bytes or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt_bytes, 100_000)
    return f"pbkdf2_sha256${salt_bytes.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    return hash_password(password, bytes.fromhex(salt_hex)) == stored


# Hash once per process: PBKDF2 is deliberately slow and reset must stay fast.
_DEMO_HASH = hash_password(DEMO_PASSWORD)


def parse_reset(body: dict) -> tuple[int, dict]:
    c = Checker()
    seed = body.get("seed", DEFAULT_SEED)
    c.check(is_int(seed), "seed")
    stock = body.get("stock", {})
    c.check(isinstance(stock, dict) and all(is_int(v) and v >= 0 for v in stock.values()), "stock")
    c.raise_if_any()
    merged = dict(DEFAULT_STOCK)
    for variant_id, qty in stock.items():
        if variant_id not in DEFAULT_STOCK:
            raise ApiError(404, "VARIANT_NOT_FOUND", f"Variant {variant_id} does not exist.",
                           {"variant_id": variant_id})
        merged[variant_id] = qty
    return seed, merged


def reset(seed: int = DEFAULT_SEED, stock: dict | None = None) -> dict:
    stock = stock or dict(DEFAULT_STOCK)
    with tx() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(777)")
        conn.execute("TRUNCATE " + ", ".join(ALL_TABLES) + " RESTART IDENTITY")
        conn.execute("INSERT INTO meta (key, value) VALUES ('seed', %s)", (J(seed),))
        for tenant_id, name, branding in TENANTS:
            conn.execute("INSERT INTO tenants VALUES (%s, %s, %s)", (tenant_id, name, J(branding)))
        for raw in SEED_SPORTS:
            config = validate_sport(raw)
            conn.execute("INSERT INTO sports VALUES (%s, %s, TRUE)", (config["sport_id"], J(config)))
        for row in LEAGUES:
            conn.execute("INSERT INTO leagues VALUES (%s, %s, %s, %s)", row)
        for club_id, tenant_id, name, profile in CLUBS:
            conn.execute("INSERT INTO clubs VALUES (%s, %s, %s, %s)", (club_id, tenant_id, name, J(profile)))
        for row in PLAYERS:
            conn.execute("INSERT INTO players VALUES (%s, %s, %s, %s, %s, %s)", row)
        for email, role, tenant, league, club, player, display in USERS:
            conn.execute(
                "INSERT INTO users VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (email, _DEMO_HASH, role, tenant, league, club, player, display),
            )
        conn.execute(
            "INSERT INTO products VALUES ('prod-jersey-001', 'tenant-alpha', 'club-alpha-1', "
            "'Alpha United Home Jersey', 'apparel', 'Official 2026 home jersey.')"
        )
        for variant_id, label in (("var-jersey-001-M", "M"), ("var-jersey-001-L", "L")):
            conn.execute(
                "INSERT INTO variants VALUES (%s, 'prod-jersey-001', %s, 450000, 'PKR', %s, 0)",
                (variant_id, label, stock[variant_id]),
            )
        conn.execute("INSERT INTO meta (key, value) VALUES ('seeded', 'true')")
    return {
        "status": "reset_complete",
        "seed": seed,
        "sports": [s["sport_id"] for s in SEED_SPORTS],
        "tenants": [t[0] for t in TENANTS],
        "stock": stock,
    }


def current_seed(conn) -> int:
    row = conn.execute("SELECT value FROM meta WHERE key = 'seed'").fetchone()
    return row["value"] if row else DEFAULT_SEED


def is_seeded(conn) -> bool:
    return conn.execute("SELECT 1 FROM meta WHERE key = 'seeded'").fetchone() is not None
