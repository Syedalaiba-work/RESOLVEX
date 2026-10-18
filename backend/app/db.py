"""PostgreSQL access: one connection pool, schema creation, small query helpers."""
import os
import time
from contextlib import contextmanager

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://nascon:nascon@localhost:5432/nascon")

_pool: ConnectionPool | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value JSONB NOT NULL);

CREATE TABLE IF NOT EXISTS tenants (
    tenant_id TEXT PRIMARY KEY, name TEXT NOT NULL, branding JSONB NOT NULL DEFAULT '{}');

CREATE TABLE IF NOT EXISTS sports (
    sport_id TEXT PRIMARY KEY, config JSONB NOT NULL, seeded BOOLEAN NOT NULL DEFAULT FALSE);

-- RBAC scenario / club data (spec 5.5)
CREATE TABLE IF NOT EXISTS leagues (
    league_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, name TEXT NOT NULL, sport_id TEXT);
CREATE TABLE IF NOT EXISTS clubs (
    club_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, name TEXT NOT NULL, profile JSONB NOT NULL DEFAULT '{}');
CREATE TABLE IF NOT EXISTS players (
    player_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, club_id TEXT, name TEXT NOT NULL,
    position TEXT, role TEXT);
CREATE TABLE IF NOT EXISTS users (
    email TEXT PRIMARY KEY, password_hash TEXT NOT NULL, role TEXT NOT NULL, tenant_id TEXT,
    league_id TEXT, club_id TEXT, player_id TEXT, display_name TEXT NOT NULL);

-- Standings leagues registered through /audit/v1/leagues (spec 5.8)
CREATE TABLE IF NOT EXISTS standings_leagues (league_id TEXT PRIMARY KEY, config JSONB NOT NULL);

-- Event-sourced matches (spec 5.9). events is append-only: rows are never updated or deleted
-- except by /reset.
CREATE TABLE IF NOT EXISTS matches (
    match_id TEXT PRIMARY KEY, sport_id TEXT NOT NULL, league_id TEXT,
    home_team_id TEXT NOT NULL, away_team_id TEXT NOT NULL, origin TEXT NOT NULL,
    created_order BIGSERIAL);
CREATE TABLE IF NOT EXISTS events (
    match_id TEXT NOT NULL, sequence INT NOT NULL, event_id TEXT NOT NULL UNIQUE, type TEXT NOT NULL,
    payload JSONB NOT NULL, request JSONB NOT NULL, signature TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), PRIMARY KEY (match_id, sequence));

-- Store (spec 5.12)
CREATE TABLE IF NOT EXISTS products (
    product_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, club_id TEXT, name TEXT NOT NULL,
    category TEXT NOT NULL, description TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS variants (
    variant_id TEXT PRIMARY KEY, product_id TEXT NOT NULL, label TEXT NOT NULL,
    price_minor INT NOT NULL, currency TEXT NOT NULL,
    stock INT NOT NULL CHECK (stock >= 0), reserved INT NOT NULL DEFAULT 0 CHECK (reserved >= 0));
CREATE TABLE IF NOT EXISTS orders (
    order_id TEXT PRIMARY KEY, request JSONB NOT NULL, status_code INT NOT NULL, response JSONB NOT NULL,
    status TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS payments (
    id BIGSERIAL PRIMARY KEY, order_id TEXT NOT NULL, kind TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now());
-- Internal queue (outbox): structured domain events, consumed by the worker.
CREATE TABLE IF NOT EXISTS domain_events (
    id BIGSERIAL PRIMARY KEY, type TEXT NOT NULL, payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), processed_at TIMESTAMPTZ);

-- Roster (spec 5.11). roster_state holds the current registrations of a configured league;
-- roster_audit is the append-only history.
CREATE TABLE IF NOT EXISTS roster_leagues (league_id TEXT PRIMARY KEY, state JSONB NOT NULL);
CREATE TABLE IF NOT EXISTS roster_audit (
    seq BIGSERIAL PRIMARY KEY, audit_id TEXT NOT NULL UNIQUE, player_id TEXT NOT NULL,
    league_id TEXT NOT NULL, entry JSONB NOT NULL);
CREATE TABLE IF NOT EXISTS roster_requests (
    request_id TEXT PRIMARY KEY, request JSONB NOT NULL, status_code INT NOT NULL, response JSONB NOT NULL);

-- Offline sync (spec 5.14)
CREATE TABLE IF NOT EXISTS sync_actions (
    device_id TEXT NOT NULL, action_id TEXT NOT NULL, result JSONB NOT NULL,
    PRIMARY KEY (device_id, action_id));

-- ---- Phase II (Day 2) -------------------------------------------------------------------------
-- Stream keys (Part II 5.4). One active key per player at a time.
CREATE TABLE IF NOT EXISTS stream_keys (
    stream_key TEXT PRIMARY KEY, player_id TEXT NOT NULL, label TEXT NOT NULL, status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), revoked_at TIMESTAMPTZ);
-- Co-stream sessions (5.5): the accepted request and stored response, for idempotent replay.
CREATE TABLE IF NOT EXISTS costream_sessions (
    session_id TEXT PRIMARY KEY, request JSONB NOT NULL, response JSONB NOT NULL);
-- Dynamic QR mappings (5.6). short_code never changes; the target route is computed at scan time.
CREATE TABLE IF NOT EXISTS qr_codes (
    entity_id TEXT PRIMARY KEY, entity_type TEXT NOT NULL, short_code TEXT NOT NULL UNIQUE,
    scan_count INT NOT NULL DEFAULT 0);
-- Privacy-safe scan telemetry (NFR-9): no IP, no User-Agent string, no fingerprint.
CREATE TABLE IF NOT EXISTS qr_scans (
    entity_id TEXT NOT NULL, device_family TEXT NOT NULL, bucket TIMESTAMPTZ NOT NULL);
-- Guest tokens and carts (5.7). merged_* hold the first successful merge for idempotent replay.
CREATE TABLE IF NOT EXISTS guest_tokens (
    guest_token TEXT PRIMARY KEY, status TEXT NOT NULL, user_id TEXT,
    merged_request JSONB, merged_response JSONB);
CREATE TABLE IF NOT EXISTS carts (user_id TEXT PRIMARY KEY, items JSONB NOT NULL);
-- Moderation (5.8): the primary key makes concurrent kick/mute of one user idempotent (edge case 3).
CREATE TABLE IF NOT EXISTS moderation_actions (
    chat_room_id TEXT NOT NULL, user_id TEXT NOT NULL, action TEXT NOT NULL,
    created_order BIGSERIAL, PRIMARY KEY (chat_room_id, user_id, action));
-- Notification dead-letter queue (FR-5.2).
CREATE TABLE IF NOT EXISTS notification_dlq (
    id BIGSERIAL PRIMARY KEY, event JSONB NOT NULL, attempts INT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now());
"""

ALL_TABLES = [
    "meta", "tenants", "sports", "leagues", "clubs", "players", "users", "standings_leagues",
    "matches", "events", "products", "variants", "orders", "payments", "domain_events", "roster_leagues",
    "roster_audit", "roster_requests", "sync_actions",
    "stream_keys", "costream_sessions", "qr_codes", "qr_scans", "guest_tokens", "carts",
    "moderation_actions", "notification_dlq",
]


def pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            DATABASE_URL, min_size=2, max_size=20, kwargs={"row_factory": dict_row, "autocommit": False},
            open=True,
        )
    return _pool


@contextmanager
def tx():
    """One transaction: commits on success, rolls back on any exception."""
    with pool().connection() as conn:
        with conn.transaction():
            yield conn


def wait_for_db(timeout_s: float = 90) -> None:
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            with tx() as conn:
                conn.execute("SELECT 1")
            return
        except Exception:
            if time.monotonic() > deadline:
                raise
            time.sleep(1)


def create_schema() -> None:
    with tx() as conn:
        # Serialize schema creation if several processes start at once.
        conn.execute("SELECT pg_advisory_xact_lock(424242)")
        conn.execute(SCHEMA)


def J(value) -> Jsonb:
    return Jsonb(value)
