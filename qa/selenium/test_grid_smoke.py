"""Selenium Grid 4 browser smoke test (read-only) against the QA backend's web pages.

The project's only browser UI is FastAPI's Swagger UI at /docs; the mobile app is native Flutter and is
covered by the Appium suite, not by Selenium. Swagger UI loads its JS/CSS from cdn.jsdelivr.net, so the
/docs tests need internet access from the browser container.

Env: GRID_URL (default http://127.0.0.1:4444), APP_URL as seen from the browser container
(default http://api:8080 = the nascon-qa stack on the nascon-qa_default network).
"""
import json
import os
import pathlib
import urllib.request

import pytest
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

GRID_URL = os.environ.get("GRID_URL", "http://127.0.0.1:4444")
APP_URL = os.environ.get("APP_URL", "http://api:8080").rstrip("/")
REPORTS = pathlib.Path(__file__).resolve().parents[1] / "reports"


@pytest.fixture(scope="module")
def driver():
    opts = webdriver.ChromeOptions()
    opts.add_argument("--headless=new")
    opts.add_argument("--window-size=1280,900")
    d = webdriver.Remote(command_executor=GRID_URL, options=opts)
    d.set_page_load_timeout(30)
    yield d
    d.quit()


def test_grid_is_ready_with_a_chrome_node():
    with urllib.request.urlopen(f"{GRID_URL}/status", timeout=10) as r:
        status = json.load(r)["value"]
    assert status["ready"] is True
    browsers = {s["stereotype"]["browserName"] for n in status["nodes"] for s in n["slots"]}
    assert "chrome" in browsers


def test_health_endpoint_renders_in_browser(driver):
    driver.get(f"{APP_URL}/health")
    assert json.loads(driver.find_element(By.TAG_NAME, "body").text) == {"status": "ok"}


def test_swagger_ui_lists_contract_endpoints(driver):
    driver.get(f"{APP_URL}/docs")
    wait = WebDriverWait(driver, 30)
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".opblock-summary-path")))
    title = driver.find_element(By.CSS_SELECTOR, ".info .title").text
    paths = {e.get_attribute("data-path") for e in driver.find_elements(By.CSS_SELECTOR, ".opblock-summary-path")}
    assert "NaSCon League Platform" in title
    assert {"/health", "/audit/v1/reset", "/audit/v1/checkout", "/audit/v1/offline-sync"} <= paths


def test_try_out_health_operation_shows_200(driver):
    driver.get(f"{APP_URL}/docs")
    wait = WebDriverWait(driver, 30)
    block = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "#operations-default-health_health_get .opblock-summary")))
    block.click()
    wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "#operations-default-health_health_get .try-out__btn"))).click()
    wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "#operations-default-health_health_get .execute"))).click()
    cell = (By.CSS_SELECTOR, "#operations-default-health_health_get .live-responses-table tbody .response-col_status")
    wait.until(lambda d: d.find_element(*cell).text.strip()[:3].isdigit())
    assert driver.find_element(*cell).text.strip().startswith("200")
    REPORTS.mkdir(exist_ok=True)
    driver.save_screenshot(str(REPORTS / "selenium-swagger-health.png"))
