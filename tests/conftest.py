import importlib.util
import os

import pytest

# One tests/ tree serves three environments: the backend suite (inside the API container), the Selenium
# Grid suite and the Appium suite (on a QA runner). Each part loads only where its dependencies exist,
# so `pytest`, `pytest -n 3 tests/selenium/` and `pytest tests/appium/` all work from the repo root.
def _installed(module: str) -> bool:
    # Probe a submodule: the folders tests/selenium and tests/appium would otherwise satisfy
    # find_spec("selenium") / find_spec("appium") as namespace packages when tests/ is on sys.path.
    try:
        return importlib.util.find_spec(module) is not None
    except ModuleNotFoundError:
        return False


collect_ignore = [d for d, module in (("selenium", "selenium.webdriver"), ("appium", "appium.webdriver"))
                  if not _installed(module)]
BACKEND = importlib.util.find_spec("psycopg") is not None and importlib.util.find_spec("fastapi") is not None


def err(response):
    return response.json()["error"]["code"]


if BACKEND:
    import psycopg
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

    from fastapi.testclient import TestClient

    from app.main import app

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
else:
    collect_ignore_glob = ["test_*.py"]  # backend tests need the API container (psycopg + FastAPI)
