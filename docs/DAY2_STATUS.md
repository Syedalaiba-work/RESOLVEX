# Part II status — factual checklist (2026-10-18, before Window 4)

Source of truth: *App Dev Day 2 Problem Statement.pdf*. "Passed" = ran and passed; nothing is claimed from inspection.

## Evidence

| Check | Where it ran | Result |
|---|---|---|
| Phase I ancestry `git merge-base --is-ancestor f6d03c3 HEAD` | local + GitHub Actions | passed |
| `docker compose up -d --build` (root file) + `/health` 200 ≤ 120 s | GitHub Actions run 39109040728 (`10b5ef6`, clean ubuntu-latest) | passed |
| Root stack under the QA project: `/health` with Redis + MediaMTX probes; hub ready with 3 nodes | local | passed |
| Backend suite (Phase I regression + Part II) | isolated QA stack | **274 passed, 41 xfailed** (the 41 = contracts for the five team-implemented handlers) |
| Backend suite | GitHub Actions (`10b5ef6`) | passed |
| Selenium Grid 4 status ≥ 3 nodes | GitHub Actions + local | passed |
| `pytest -n 3 tests/selenium/` (Chrome + Firefox) | local QA grid; GitHub Actions | 8 passed, 2 xfailed (test 1 waits for `GET /q/{code}`) |
| `tests/appium/test_mobile_deeplink.py` (exact `adb shell am start -W` commands) | emulator API 30 | 2 passed; launch-time and cross-surface cases xfail (below) |
| Appium regression smoke (`qa/appium`) on the release APK | emulator | 5 passed |
| Flutter `analyze` / tests | local | clean / 20 passed |
| NFR-1 25-client WebSocket probe (`qa/probes/nfr1_ws_probe.py`) | QA stack over the network | p95 122–142 ms (3 runs), gauge 25 during / 0 after |
| k6 read-only smoke (`qa/k6/smoke.js`) | QA stack | 435/435 checks, 0 % failed, p95 15.6 ms |
| `tests/k6_load.js` (NFR-2, 550 VUs) | GitHub Actions | **failed** — its two endpoints are still 501 scaffolds |

## Coverage (`COVERAGE_DAY2.json`, measured 12:53 PKT)

`streaming 100.0, costream 100.0, qr_guest 79.2, moderation_dlq 100.0, observability 100.0` — the three 100.0
values are scaffold stubs and must be re-measured (`run_tests.sh`) after the handlers are implemented.

## Not met / not verified

| Item | Status |
|---|---|
| §5.4 stream key, §5.5 co-stream, §5.6 QR + exports + `/q/`, §5.7 cart merge, §5.8 moderation/DLQ | **Not implemented** (team-implemented per the assessment rules; contract tests ready) |
| `DAY2_SALT` in `.env` | **Missing** — must be added from the venue slip |
| GitHub Actions secrets `DAY1_SALT`, `DAY2_SALT` | Not verifiable from here |
| MinIO, stream recording, VOD indexing | **Blocked** — image cannot be pulled (Docker Hub denied, quay.io 401); no recording/VOD support claimed |
| Stream-key revocation severing live ingest within 2 s (MediaMTX auth hook) | Not implemented (depends on §5.4) |
| Deep-link cold start ≤ 2 s | Missed on the emulator (~2.9–3.1 s); warm 465–492 ms |
| Cross-surface mobile + browser chat sync (§6.3) | Not implemented (depends on §5.5/§5.8) |
| FR-3.1 athlete profile + follow graph; FR-3.2 overlays over live video | Not implemented |
| Physical phone | Not visible to ADB (USB debugging not active) |
| Repository visibility rule (booklet: private + invite vs spec: public) | Organiser decision |
