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
"""

ALL_TABLES = [
    "meta", "tenants", "sports", "leagues", "clubs", "players", "users", "standings_leagues",
    "matches", "events", "products", "variants", "orders", "domain_events", "roster_leagues",
    "roster_audit", "roster_requests", "sync_actions",
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
