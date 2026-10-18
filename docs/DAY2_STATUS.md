# Part II status — factual checklist (2026-10-18, 13:37 PKT, before Window 4)

Source of truth: *App Dev Day 2 Problem Statement.pdf*. "Passed" = ran and passed; nothing is claimed from inspection.

## Evidence

| Check | Where it ran | Result |
|---|---|---|
| Phase I ancestry `git merge-base --is-ancestor f6d03c3 HEAD` | local + GitHub Actions | passed |
| `docker compose up -d --build` (root file) + `/health` 200 ≤ 120 s | GitHub Actions run 39109040728 (`10b5ef6`, clean ubuntu-latest) | passed |
| Root stack under the QA project: `/health` with Redis + MediaMTX probes; hub ready with 3 nodes | local | passed |
| Backend suite (Phase I regression + Part II, incl. all §5.4–5.8 contract tests) | isolated QA stack | **315 passed, 0 xfailed, 0 failed** |
| Backend suite | GitHub Actions (`10b5ef6`) | passed |
| Selenium Grid 4 status ≥ 3 nodes | GitHub Actions + local | passed |
| `pytest -n 3 tests/selenium/` (Chrome + Firefox) | local QA grid | **10 passed** (incl. test 1, the real `/q/m1-live` redirect) |
| `tests/appium/test_mobile_deeplink.py` (exact `adb shell am start -W` commands) | emulator API 30 | 2 passed; launch-time and cross-surface cases xfail (below) |
| Appium regression smoke (`qa/appium`) on the release APK | emulator | 5 passed |
| Flutter `analyze` / tests | local | clean / 20 passed |
| NFR-1 25-client WebSocket probe (`qa/probes/nfr1_ws_probe.py`) | QA stack over the network | p95 122–142 ms (3 runs), gauge 25 during / 0 after |
| k6 read-only smoke (`qa/k6/smoke.js`) | QA stack | 435/435 checks, 0 % failed, p95 15.6 ms |
| `tests/k6_load.js` (NFR-2, 500 + 50 VUs, 15 s) | QA stack on this laptop | **0.00 % failed**, 12310/12310 checks; **p95 1.49 s — 800 ms threshold not met locally** (single uvicorn worker, shared laptop); not yet seen on GitHub Actions |

## Coverage (`COVERAGE_DAY2.json`, measured 13:35 PKT from the 315-test run)

`streaming 93.5, costream 95.1, qr_guest 84.8, moderation_dlq 92.9, observability 100.0` (all handlers implemented).

## Not met / not verified

| Item | Status |
|---|---|
| §5.4–5.8 handlers | **Implemented** — every contract test passes (stream key 6, co-stream 8, QR 10, cart merge 8, moderation 9) |
| NFR-2 p95 < 800 ms under 550 VUs | Not met on this laptop (p95 1.49 s, 0 % errors) |
| Chat rate limit (> 3 messages / 2 s per sender) | Not implemented |
| `DAY2_SALT` in `.env` | **Missing** — must be added from the venue slip |
| GitHub Actions secrets `DAY1_SALT`, `DAY2_SALT` | Not verifiable from here |
| MinIO, stream recording, VOD indexing | **Blocked** — image cannot be pulled (Docker Hub denied, quay.io 401); no recording/VOD support claimed |
| Stream-key revocation severing live ingest within 2 s (MediaMTX auth hook) | Not implemented (depends on §5.4) |
| Deep-link cold start ≤ 2 s | Missed on the emulator (~2.9–3.1 s); warm 465–492 ms |
| Cross-surface mobile + browser chat sync (§6.3) | Not implemented (depends on §5.5/§5.8) |
| FR-3.1 athlete profile + follow graph; FR-3.2 overlays over live video | Not implemented |
| Physical phone | Not visible to ADB (USB debugging not active) |
| Repository visibility rule (booklet: private + invite vs spec: public) | Organiser decision |
