"""Appium 2 + UiAutomator2 smoke test of the real release APK on an Android emulator or phone.

The app is pointed at the disposable QA backend (default http://10.0.2.2:18080, the emulator's view of
127.0.0.1:18080) so the demo/judging data is never touched; every step is read-only apart from login.
Selectors are Flutter semantics labels (exposed to UiAutomator2 as content-desc), taken from the
recorded accessibility trees in qa/reports/appium-*-source.xml.

Env: APPIUM_URL (default http://127.0.0.1:4723), ANDROID_UDID (default emulator-5554),
APK (default mobile/release/app-release.apk), QA_SERVER (default http://10.0.2.2:18080).
"""
import os
import pathlib

import pytest
from appium import webdriver
from appium.options.android import UiAutomator2Options
from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

ROOT = pathlib.Path(__file__).resolve().parents[2]
REPORTS = ROOT / "qa" / "reports"
APPIUM_URL = os.environ.get("APPIUM_URL", "http://127.0.0.1:4723")
UDID = os.environ.get("ANDROID_UDID", "emulator-5554")
APK = os.environ.get("APK", str(ROOT / "mobile" / "release" / "app-release.apk"))
QA_SERVER = os.environ.get("QA_SERVER", "http://10.0.2.2:18080")
PACKAGE = "com.nascon.nascon_league"


def desc(text):
    return (AppiumBy.ACCESSIBILITY_ID, text)


def ui(selector):
    return (AppiumBy.ANDROID_UIAUTOMATOR, f"new UiSelector().{selector}")


@pytest.fixture(scope="module")
def driver():
    o = UiAutomator2Options()
    o.platform_name = "Android"
    o.automation_name = "UiAutomator2"
    o.udid = UDID
    o.app = APK
    o.app_package = PACKAGE
    o.app_activity = ".MainActivity"
    o.no_reset = False  # clean app data: login screen, default server
    o.new_command_timeout = 180
    d = webdriver.Remote(APPIUM_URL, options=o)
    REPORTS.mkdir(exist_ok=True)
    yield d
    d.execute_script("mobile: clearApp", {"appId": PACKAGE})  # leave the device on the default server
    d.quit()


def wait(d, locator, timeout=25):
    return WebDriverWait(d, timeout).until(EC.presence_of_element_located(locator))


def shot(d, name):
    d.save_screenshot(str(REPORTS / f"appium-{name}.png"))


def test_01_login_screen_shows_demo_accounts(driver):
    wait(driver, ui('description("Sign in").clickable(true)'))
    for role in ("Organizer", "Manager", "Player", "Viewer", "Admin"):
        assert driver.find_element(*desc(role)).is_displayed()
    shot(driver, "01-login")


def test_02_server_address_is_changeable(driver):
    driver.find_element(*desc("Server settings")).click()
    field = wait(driver, (AppiumBy.CLASS_NAME, "android.widget.EditText"))
    field.click()
    field.clear()
    field.send_keys(QA_SERVER)
    if driver.is_keyboard_shown():
        driver.hide_keyboard()  # the system Back key would only close the keyboard
    driver.find_element(*desc("Save and test connection")).click()
    back = driver.find_elements(*desc("Back"))
    if back:  # still on the settings screen: use the app's own back button
        back[0].click()
    wait(driver, desc(f"Server: {QA_SERVER}"))
    shot(driver, "02-server-set")


def test_03_organizer_signs_in_and_sees_fixtures(driver):
    driver.find_element(*desc("Organizer")).click()
    driver.find_element(*ui('description("Sign in").clickable(true)')).click()
    card = wait(driver, ui('descriptionContains("Alpha United versus Alpha Tigers")'), timeout=40)
    assert "LIVE" in card.get_attribute("content-desc")
    wait(driver, ui('descriptionContains("Connection status: Online")'), timeout=20)
    shot(driver, "03-fixtures")


def test_04_standings_tab_shows_table(driver):
    driver.find_element(*ui('descriptionStartsWith("Standings")')).click()
    wait(driver, ui('descriptionContains("Alpha United")'))
    wait(driver, ui('descriptionContains("Alpha Tigers")'))
    shot(driver, "04-standings")


def test_05_match_detail_shows_live_score(driver):
    driver.find_element(*ui('descriptionStartsWith("Fixtures")')).click()
    wait(driver, ui('descriptionContains("Alpha United versus Alpha Tigers")')).click()
    # The score header merges its children into one semantics node ("LIVE\n...\nScore: A 1, B 0\n...").
    score = wait(driver, ui('descriptionContains("Score: Alpha United")'))
    assert "Alpha Tigers" in score.get_attribute("content-desc")
    assert driver.find_elements(*desc("Match timeline"))
    shot(driver, "05-match")
