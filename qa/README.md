# QA tooling: Selenium Grid 4, Appium 2, k6

Everything here runs against a **disposable QA copy of the backend** (`nascon-qa` Compose project, own
database volume, dummy salt, API on `127.0.0.1:18080`). The submission stack (`nascon-league`, port 8080)
and its demo data are never used. All services bind to `127.0.0.1` only.

| Tool | Version (pinned) | Where |
|---|---|---|
| Selenium Grid | `selenium/hub:4.24.0` + `selenium/node-chrome:4.24.0` (Chrome 128), Python `selenium==4.24.0` | `qa/selenium/` |
| Appium | `appium@2.19.0` + `uiautomator2@3.10.0`, Python `Appium-Python-Client==4.1.0` | `qa/appium/` |
| k6 | `grafana/k6:0.54.0` (Docker) | `qa/k6/` |
| Test runner / reports | `pytest==8.4.1`, `pytest-html==4.1.1` (HTML reports in `qa/reports/`, not committed) | — |

Images are the ones in the rules booklet's pre-pulled bundle. Hub + node is used instead of standalone mode
because `selenium/standalone-chrome` is not in that bundle (campus Wi-Fi throttles Docker Hub).

Commands below are for Git Bash from the repository root (prefix `MSYS_NO_PATHCONV=1` where shown).

## 0. One-time setup

```sh
python -m venv qa/.venv
qa/.venv/Scripts/python -m pip install selenium==4.24.0 pytest==8.4.1 pytest-html==4.1.1 Appium-Python-Client==4.1.0
(cd qa/appium && npm ci)
export APPIUM_HOME="$PWD/qa/appium/.appium"
(cd qa/appium && npx appium driver install uiautomator2@3.10.0)
```

## 1. Start the QA target (always first)

```sh
DAY1_SALT=qa-only-salt docker compose -p nascon-qa -f docker-compose.yml -f qa/target/compose.qa.yml up -d --build
curl -s http://127.0.0.1:18080/health          # {"status":"ok"}
```

It creates the Docker network `nascon-qa_default`; the Selenium node and k6 join it and reach the API as
`http://api:8080`. The official stack is on a different network, so these tools cannot reach it by that name.
Mutating tests may reset this stack: `curl -X POST http://127.0.0.1:18080/audit/v1/reset`.

## 2. Selenium Grid 4

```sh
docker compose -p nascon-grid -f qa/selenium/docker-compose.grid.yml up -d
curl -s http://127.0.0.1:4444/status            # "ready": true, one chrome node
qa/.venv/Scripts/python -m pytest qa/selenium -v --html=qa/reports/selenium-report.html --self-contained-html
docker logs nascon-grid-chrome-1                 # node log
```

The node runs with `shm_size: 1gb` and `SE_START_VNC=false` (booklet low-RAM settings) and advertises
`SE_NODE_HOST=chrome`; without that it registers its QA-network IP, the hub cannot reach it and the grid
stays "not ready". Scope: the only browser UI in this project is FastAPI's Swagger UI at `/docs` (it loads
its assets from cdn.jsdelivr.net, so the browser container needs internet). Selenium does **not** cover the
native Flutter app; that is the Appium suite.

## 3. Appium 2 (Android, UiAutomator2)

Requirements: `ANDROID_HOME`, `JAVA_HOME` (Android Studio's JBR works), a running emulator or a phone with
USB debugging authorised (`adb devices` must list it as `device`).

```sh
export APPIUM_HOME="$PWD/qa/appium/.appium" ANDROID_HOME="$LOCALAPPDATA/Android/Sdk" JAVA_HOME="C:/Program Files/Android/Android Studio1/jbr"
(cd qa/appium && npx appium driver doctor uiautomator2)        # 0 required fixes expected
(cd qa/appium && npx appium --address 127.0.0.1 --port 4723 --log ../reports/appium-server.log) &
curl -s http://127.0.0.1:4723/status                           # "ready": true
qa/.venv/Scripts/python -m pytest qa/appium -v --html=qa/reports/appium-report.html --self-contained-html
```

The test installs `mobile/release/app-release.apk`, clears the app's local data, points the app at
`QA_SERVER` (default `http://10.0.2.2:18080`, the emulator's view of the QA API), signs in as Organizer and
checks Fixtures, Standings and Match Detail. Teardown clears the app data again, so the device is left on
the default server and the login screen. For a phone set `ANDROID_UDID=<serial>` and
`QA_SERVER=http://<laptop-ip>:18080` (the QA API would then have to be published beyond localhost).

Selectors are Flutter semantics labels (UiAutomator2 `content-desc`). To re-inspect them, dump
`driver.page_source` (recorded trees: `qa/reports/appium-*-source.xml`, not committed).

Troubleshooting:
- `adb devices` shows nothing for a phone: USB debugging is not active on that connection (Windows lists
  the phone only as an MTP device). Re-plug, accept the RSA prompt; restarting adb does not help.
- On-screen keyboard: the system Back key only closes it; the test hides it and uses the app's Back button.
- `NoSuchElementError`: compare the selector with a fresh `page_source`; merged semantics nodes need
  `descriptionContains`.

## 4. k6

```sh
mkdir -p qa/k6/results
MSYS_NO_PATHCONV=1 docker run --rm --network nascon-qa_default \
  -v "$PWD/qa/k6:/scripts:ro" -v "$PWD/qa/k6/results:/results" grafana/k6:0.54.0 run --quiet /scripts/smoke.js
```

- `smoke.js`: read-only, `VUS` (default 3, capped at 5) for `DURATION` (default 30s). Thresholds:
  `http_req_failed < 1%`, `p(95) < 500 ms`, `median < 200 ms`, `checks > 99%`. Writes
  `results/smoke-summary.{txt,json}`.
- `load.js`: **opt-in** (`-e K6_LOAD_OPT_IN=yes`), ramps to 20 VUs over 2 minutes, public read endpoints only.
- Target guard: both refuse any `BASE_URL` other than `http://api:8080` unless `ALLOW_TARGET` repeats the
  same URL. The `/api/v1` rate limit (100 req / 10 s per IP) is part of the contract and will 429 under load.
- A laptop smoke run says nothing about production capacity.

## 5. Cleanup

```sh
docker compose -p nascon-grid -f qa/selenium/docker-compose.grid.yml down
docker compose -p nascon-qa -f docker-compose.yml -f qa/target/compose.qa.yml down -v   # QA data only
# stop the Appium server process (Ctrl+C in its terminal)
```

## Recorded results (2026-10-18)

| Suite | Result |
|---|---|
| Selenium (`qa/selenium`) | 4 passed (grid ready with Chrome 128; `/health` in browser; Swagger UI lists contract routes; "Try it out" GET /health → 200) |
| Appium (`qa/appium`, emulator API 30, APK SHA-256 `a7fbb1aa…a581d`) | 5 passed in 221.7 s |
| k6 smoke (3 VUs, 30 s) | 436 requests, 14.12 req/s, median 10.6 ms, p95 26.8 ms, 0.00 % failed, 435/435 checks, all thresholds OK (`qa/k6/results/smoke-summary.txt`) |
| k6 guards | non-QA target refused (exit 107); load profile without opt-in refused (exit 107) |
