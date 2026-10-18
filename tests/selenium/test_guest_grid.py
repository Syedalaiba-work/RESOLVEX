"""Part II §6.2.3 Guest Web Player suite on Selenium Grid 4. Run: pytest -n 3 tests/selenium/

Env: GRID_URL (default http://localhost:4444); APP_URL = backend as seen from the browser nodes
(default http://host.docker.internal:8080, §6.2.1); API_URL = backend as seen from this runner
(default http://localhost:8080). Test 3 posts a score event, so point API_URL at a test stack.
"""
import json
import os
import time
import urllib.request
import uuid

import pytest
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

GRID_URL = os.environ.get("GRID_URL", "http://localhost:4444")
APP_URL = os.environ.get("APP_URL", "http://host.docker.internal:8080").rstrip("/")
API_URL = os.environ.get("API_URL", "http://localhost:8080").rstrip("/")
LIVE = "/web/matches/match-m1/live"


def tid(name):
    return (By.CSS_SELECTOR, f'[data-testid="{name}"]')


@pytest.fixture(params=["chrome", "firefox"])
def driver(request):
    opts = webdriver.ChromeOptions() if request.param == "chrome" else webdriver.FirefoxOptions()
    opts.add_argument("--headless=new" if request.param == "chrome" else "-headless")
    d = webdriver.Remote(command_executor=GRID_URL, options=opts)
    d.set_window_size(390, 844)  # small phone viewport
    yield d
    d.quit()


def api(method, path, body=None):
    req = urllib.request.Request(API_URL + path, method=method, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


def wait_ready(d, timeout=3):
    w = WebDriverWait(d, timeout, poll_frequency=0.05)
    w.until(lambda x: x.find_element(*tid("guest-video-player")).is_displayed())
    w.until(lambda x: x.find_element(*tid("live-score-banner")).text.strip() not in ("", "–"))


def assert_zero_friction(d):
    assert d.find_element(*tid("guest-video-player")).is_displayed()
    assert d.find_element(*tid("live-score-banner")).is_displayed()
    assert not d.find_element(*tid("progressive-auth-modal")).is_displayed()


def test_1_qr_resolution_and_zero_friction_load(driver):
    driver.get(APP_URL + "/q/m1-live")
    if "NOT_IMPLEMENTED" in driver.page_source:
        pytest.xfail("GET /q/{short_code} not implemented yet (scaffold returns 501)")
    assert driver.current_url.endswith(LIVE)
    wait_ready(driver)
    assert_zero_friction(driver)


def test_1b_direct_live_route_zero_friction_load(driver):
    driver.get(APP_URL + LIVE)
    wait_ready(driver)
    assert_zero_friction(driver)


def test_2_guest_write_block_opens_progressive_modal(driver):
    driver.get(APP_URL + LIVE)
    wait_ready(driver)
    before = len(driver.find_elements(By.CSS_SELECTOR, '[data-testid="chat-message-list"] li'))
    driver.find_element(*tid("chat-input-field")).send_keys("Hello from a guest")
    driver.find_element(*tid("chat-send-btn")).click()
    WebDriverWait(driver, 3).until(lambda x: x.find_element(*tid("progressive-auth-modal")).is_displayed())
    assert len(driver.find_elements(By.CSS_SELECTOR, '[data-testid="chat-message-list"] li')) == before


def test_3_guest_cart_staging_and_realtime_score_sync(driver):
    driver.get(APP_URL + LIVE)
    wait_ready(driver)
    count = driver.find_element(*tid("guest-cart-count"))
    assert count.text == "0"
    driver.find_element(*tid("add-to-guest-cart-btn")).click()
    WebDriverWait(driver, 2).until(lambda x: x.find_element(*tid("guest-cart-count")).text == "1")
    home = api("GET", "/audit/v1/score/match-m1")["home"]["team_id"]
    api("POST", "/audit/v1/events", {"event_id": f"sel-{uuid.uuid4().hex[:12]}", "match_id": "match-m1",
                                     "type": "score", "payload": {"team_id": home, "event_type": "goal"}})
    s = api("GET", "/audit/v1/score/match-m1")
    expected = f'{s["home"]["score"]} - {s["away"]["score"]}'
    t0 = time.monotonic()
    WebDriverWait(driver, 0.5, poll_frequency=0.02).until(
        lambda x: x.find_element(*tid("live-score-banner")).text.strip() == expected)
    assert time.monotonic() - t0 < 0.5


def test_nfr8_keyboard_aria_and_touch_targets(driver):
    driver.get(APP_URL + LIVE)
    wait_ready(driver)
    assert driver.find_element(*tid("guest-video-player")).get_attribute("aria-label")
    for name in ("add-to-guest-cart-btn", "chat-send-btn", "chat-input-field"):
        rect = driver.find_element(*tid(name)).rect
        assert rect["height"] >= 48 and rect["width"] >= 48, (name, rect)
    field = driver.find_element(*tid("chat-input-field"))
    field.click()
    field.send_keys("keyboard only", Keys.ENTER)  # Enter submits without a mouse
    WebDriverWait(driver, 3).until(lambda x: x.find_element(*tid("progressive-auth-modal")).is_displayed())
    assert driver.switch_to.active_element.text in ("Sign in or register", "Not now")  # focus moved into dialog
    driver.switch_to.active_element.send_keys(Keys.ESCAPE)
    WebDriverWait(driver, 2).until(lambda x: not x.find_element(*tid("progressive-auth-modal")).is_displayed())
