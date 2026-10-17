import os

import psycopg
import pytest
from psycopg import sql

# Tests use their own database so they never touch the running API's data.
BASE_URL = os.environ.get("DATABASE_URL", "postgresql://nascon:nascon_local_dev@db:5432/nascon")
TEST_DB = "nascon_test"
TEST_URL = BASE_URL.rsplit("/", 1)[0] + "/" + TEST_DB
os.environ["DATABASE_URL"] = TEST_URL
os.environ.setdefault("DAY1_SALT", "test-salt")


def _ensure_test_db():
    with psycopg.connect(BASE_URL, autocommit=True) as conn:
        if not conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DB,)).fetchone():
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(TEST_DB)))


_ensure_test_db()

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def fresh(client):
    """Reset to the baseline before a test."""
    r = client.post("/audit/v1/reset", json={})
    assert r.status_code == 200
    return client


def err(response):
    return response.json()["error"]["code"]
