# Day 1 Audit — Gap Report and Traceability Matrix

Audit date: 2026-10-18 (before Sprint 2). Audited commit: `f6d03c3470c7f497474a89500a3e4f6882025c53`
(the locked Day 1 SHA; local HEAD = `origin/main`, clean tree).

**Sources (authoritative, nothing else assumed):**
- **[P1]** *NaSCon ’26 App Dev Part I Specification* (`NaSCon 26 App Dev Part 1-1.pdf`, 22 pages). Page numbers are the PDF's.
- **[RB]** *Official Rules, Environment Readiness & Compliance Booklet* (`Official_Participant_Rules_Booklet.pdf`, 4 pages).
- The Part II brief is not yet available (released 10:15 PKT Day 2 per [RB] p1); nothing below depends on it.

**Status legend:** *Implemented* = code present **and** verified by an automated test or a recorded probe; *Partial* =
some required behaviour missing; *Missing* = no implementation; *Unverified* = implemented but no evidence recorded.

## 1. Baseline evidence (recorded 2026-10-18, no data mutated)

| Check | Result |
|---|---|
| Backend pytest (`nascon_test` DB, inside `api` container) | **241 passed**, 0 failed (45.5 s) |
| Per-area line coverage vs `COVERAGE.json` | fixtures 96.7, scoring 98.9, standings 99.2, store 96.8, roster 96.1, rbac 97.6 — **identical** |
| `flutter analyze` / `flutter test` | No issues / **17 passed** |
| `GET /health` | 200 `{"status":"ok"}` |
| Release APK `mobile/release/app-release.apk` | At audit start: 54,816,237 bytes, SHA-256 `a7fbb1aa69f865fc0368b24a8fbf71712d79243970c6dd3daa6f7691a05a581d` (= committed in `f6d03c3`). Replaced on 2026-10-18 by `ee64c73e01e5b9843c1619f118849a9ab8fcad4ef0887928257cb3bce6a0f012` (D5/D6 fixes) after `flutter analyze` clean, 18/18 Flutter tests, Appium 5/5 on the installed candidate, apksigner verify. |
| Demo DB | Left as found: 1 order, jersey L stock 3, M 1, `la1-m5` 0–0 v3 (viva activity after the Day 1 reset) |

Evidence carried over from Day 1 (2026-10-17, recorded in the session, not re-run today):
- Fresh anonymous clone of `4c0b63e`, `--no-cache` build: `/health` 200 after 32 s; 241 tests passed.
- Independent black-box probe written from [P1] (120 checks): 116 passed; the 4 failures were traced to probe errors
  (wrong expected version count, mis-applied qualification rule, arithmetic, header-case check). Covered Appendix A
  vectors 1–2, all four fixture formats, scoring models, compensation, standings 3-way H2H, roster rule order and
  loan return, 20-buyer checkout burst, PDF text, full RBAC matrix, alg:none/tampered JWT, rate limit, 413, offline sync.
- Live smoke through `/api/v1` (34/34) and emulator desk check (offline queue → force-close → auto-sync) for
  Organizer scoring and Manager transfer.

## 2. Gap and defect report (prioritised)

| # | Finding | Source | Severity | Fixable without history rewrite? | Recommended action |
|---|---|---|---|---|---|
| G1 | First commit `9ee39a4` ("Initial commit", README) is dated **2026-10-16 17:50 +0500**; the repo had to be empty at 10:40 Day 1 with all code committed after 10:45. | [RB] p3 §4.1 | High (compliance) | No — Day 2 history must continue from the locked SHA ([RB] p4 §4.4) | Obtain/keep the organisers' written ruling; do not rewrite history. |
| G2 | [RB] requires a **private** repo with `nascon-eval-26` invited; [P1] p2 §1.3 requires it **public** (grader clones without credentials). Repo is public; invite not verified. | [RB] p3 §4.1 vs [P1] p2 | High (compliance, conflicting sources) | Yes (GitHub settings) | Confirm with organisers which rule applies; check Settings → Collaborators for `nascon-eval-26`. |
| G3 | Hourly push rule: first push at 12:47:33 PKT; windows 10:45–11:45 and 11:45–12:45 had no push. | [P1] p2 §1.3, p21 §9.4; [RB] p3 §4.2 | High (−4, historical) | No | Push at least hourly throughout Sprint 2 (first push after 10:15). |
| G4 | **No pushes allowed 15:05 Day 1 → 10:15 Day 2.** | [RB] p4 §4.4 | Critical (process) | n/a | All Day 2 work stays uncommitted/unpushed until 10:15; then continue from `f6d03c3`. |
| G5 | Roster management screen must support **add** / transfer / loan / release; only transfer/loan/release exist (API `roster.TYPES`, app action sheet). | [P1] p19 §8.2; p3 FR-2.2 | Medium (required workflow) | Yes | Add an "add/register player" action (API + screen) with rule checks and an audit entry; regression tests. Needs a contract decision (no `/audit/v1` shape is defined for "add"). |
| G6 | No realtime WebSocket/SSE layer; match screen polls every 3 s; status changes and product pinning are not pushed. | [P1] p1 §1, p3 FR-1.3, p4 FR-2.3, p19 §8.2 | Medium | Yes | SSE endpoint for match/status/pin events; app subscribes with polling fallback. |
| G7 | Rescheduling with conflict detection (venue double-booking, team/player overlap, rest period, venue windows) and statuses Postponed/Abandoned/Cancelled are missing; only upcoming → in_progress → completed exist. | [P1] p3 FR-1.3 | Medium | Yes | Implement if Part II asks for it; it has no Part I grader endpoint. |
| G8 | League setup: multi-division, promotion/relegation, knockout tournaments, hybrid group+knockout, season scoping are missing (only `POST /audit/v1/leagues` registration). | [P1] p3 FR-1.2 | Medium | Yes | Defer to Part II scope. |
| G9 | Store: order states Packed/Shipped/Delivered/Cancelled/Refunded, scheduled price changes and refund simulation are missing (orders reach `paid`, or fail with 402). | [P1] p4 FR-2.3 | Medium | Yes | State machine + domain event per transition; regression tests on `nascon_test`. |
| G10 | Compose brings up API, PostgreSQL, worker; **no cache or object store** service. Queue is a Postgres outbox. | [P1] p2 §1.3 table | Low–Medium | Yes | Add only if a feature needs them (Redis/MinIO are in the pre-pulled bundle). |
| G11 | Day 2 QA tooling required by the booklet: Appium 2 + UiAutomator2, Selenium WebDriver bindings, Allure **or** HTML reports, k6 **or** Locust. | [RB] p2 §2.1(2) | High for Day 2 | Yes | **Done 2026-10-18** — `qa/` (Selenium 4 passed, Appium 5 passed, k6 smoke thresholds OK); see `qa/README.md`. |
| D1 | `/api/v1` rate limiter keys on client IP; behind Docker Desktop every LAN client appears as the bridge gateway (`172.22.0.1` in logs), so all phones/emulators share one 100 req/10 s bucket. | [P1] p6, p17 §5.13 | Low (dev-host only; Linux runners keep source IPs) | Yes | Document; optionally honour a trusted proxy header. Not changed. |
| D2 | ~~413 bypass with a chunked body~~ **Not reproduced (2026-10-18):** a 1.2 MB chunked body with no `Content-Length` still returns 413 `PAYLOAD_TOO_LARGE`, because `core.read_json` re-checks the size after reading. Residual: such a body is buffered before rejection. | [P1] p6, p18 §5.13 | Low (hardening only) | Yes | No contract change needed; optional streaming cap later. |
| D5 | Fixture cards are not actionable by screen readers: `FixtureCard` wraps its `InkWell` in `Semantics(button: true, excludeSemantics: true)`, which drops the tap action; UiAutomator2 reports the cards as `clickable=false` (finger taps work). | [P1] p20 §8.6 (accessibility) | Low–Medium (a11y) | Yes | **Fixed 2026-10-18.** Same defect also found in the standings row and the connection-status chip. Each `Semantics` wrapper now carries the same `onTap`. Regression: Flutter test `screen readers can activate fixture cards, standings rows and the status chip` (failed before the fix, passes after; activates the card through `SemanticsAction.tap`) and Appium `test_03` asserts `clickable=true` on the device (failed on the old APK `a7fbb1aa…`, passes on `ee64c73e…`). |
| D6 | Match screen status row (LIVE pill + "Updates every 3 s") is a non-flexible `Row`; at 360 dp it overflowed by 13 px in the widget test, and would overflow on a real 360 dp phone with enlarged system text. Introduced by the hero margin in `f6d03c3`. | [P1] p20 §8.6 (no overflow on 360×640) | Low (UI) | Yes | **Fixed 2026-10-18:** `Row` → `Wrap` (the hint moves to a second line). Regression: the D5 Flutter test opens the match screen at 360×640 and asserts no exception. |
| D3 | App shows "Offline" for ~5 s after a cold start when the first ping times out (emulator); recovers on the next check. | [P1] p19 §8.2 (sync status) | Low (UI) | Yes | Treat the first timeout as "checking". |
| D4 | Standings for `league-alpha-2` (RBAC-only seed league) shows "That league was not found." | [P1] p19 §8.2 | Low (UI) | Yes | Show the empty state for a league without a table. |

## 3. Traceability matrix

Day 1 evidence = the commit that introduced the code (all pushed on 2026-10-17 between 12:47 and 13:46 PKT, final `f6d03c3`).
"Tests" refers to `tests/` (backend) and `mobile/test/` (Flutter).

| ID | Requirement (source) | Source files / endpoints | Implementation evidence | Automated test evidence | Status | Severity / correction | Day 1 / Day 2 evidence |
|---|---|---|---|---|---|---|---|
| FR-1.1a | Arbitrary sports as JSON config; seed four sports; mystery sport via `POST /audit/v1/sports` ([P1] p3, p7–9 §5.6) | `sports.py` (`validate_sport`, `SEED_SPORTS`), `main.py` | Kabaddi + innings + round mystery sports used in events/leagues without restart (Day 1 probe) | `test_health_reset_sports.py`, `test_scoring_standings.py::test_mystery_sport_works_without_restart`, `test_api_v1.py::test_match_detail_lists_scoring_events_from_sport_config` | Implemented | — | `90f7823`, `4c0b63e` |
| FR-1.1b | Append-only event log, compensating signed events, score rebuilt on read ([P1] p3, p11–13 §5.9) | `scoring.py`, `core.sign`; `POST /audit/v1/events`, `GET /audit/v1/score/{id}` | Appendix A vector 1 signature exact; compensation neutral, originals retained | `test_scoring_standings.py` (flow, signatures, idempotency, compensation, innings/round limits, tie rules) | Implemented | — | `b4cf21a` |
| FR-1.1c | No hard-coded sport/event logic (−8 penalty) ([P1] p21 §9.4) | backend domain + `mobile/lib/screens/scoring_screen.dart` | Code scan: names only in seed data; mobile table removed | `test_api_v1.py::test_match_detail_lists_scoring_events_from_sport_config` | Implemented | — | `4c0b63e` |
| FR-1.2 | Single-stage, multi-division with promotion/relegation, knockout, hybrid, seasons ([P1] p3) | `scoring.register_league` | Only league registration for standings | Standings tests only | Partial | G8 | `b4cf21a` (partial) |
| FR-1.3a | Fixtures: round robin (circle, byes, withdrawals), Swiss (backtracking, Buchholz, NO_VALID_PAIRING), single and double elimination (byes, reset) ([P1] p3, p9–11 §5.7) | `fixtures.py`; `POST /audit/v1/fixtures` | Exact single-elim n=6, Swiss round 1/2 example, double-elim graph and GF2 reset (Day 1 probe) | `test_fixtures.py` | Implemented | — | `840f101` |
| FR-1.3b | Match status state machine incl. Postponed/Abandoned/Cancelled; illegal transitions rejected ([P1] p3) | `scoring._append` | upcoming → in_progress → completed with ILLEGAL_TRANSITION | `test_scoring_standings.py` | Partial | G7 | `b4cf21a` |
| FR-1.3c | Rescheduling + structured conflict detection ([P1] p3) | — | none | none | Missing | G7 | — |
| FR-1.3d | Status changes broadcast in real time ([P1] p3) | — (app polls) | 3 s polling in `match_screen.dart` | none | Missing | G6 | — |
| FR-1.4 | Points tables, configurable tie-breaks incl. 3-way mini-league, H2H matrix, differentials, clinched/eliminated, recompute from scratch ([P1] p3, p13–14 §5.10) | `standings.py`; `GET /audit/v1/standings/{id}` | Appendix A vector 2 exact; 3-way H2H; compensation recompute | `test_scoring_standings.py` | Implemented | — | `b4cf21a` |
| FR-2.1 | Club portal (venue coords, socials, history, roster, staff), white-label tenant, strict isolation ([P1] p3) | `seed.py`, `api_v1.club_detail`, `rbac.POLICY`; `GET /api/v1/clubs/{id}` | Live smoke: club detail with roster/staff/venue; foreign-tenant club 403 | `test_api_v1.py::test_clubs_products_and_tenant_isolation`, `test_rbac_security.py` | Implemented | — | `9328c22` |
| FR-2.2a | Transfer, loan (auto-return), release; window, squad size, one registration, positions; ordered rule checks ([P1] p3, p14–15 §5.11) | `roster.py`; `/audit/v1/roster/*`, `POST /api/v1/roster/transfer` | Rule order, deferred last-day transfer, loan_return written once | `test_roster_sync.py` | Implemented | — | `d0c19e0` |
| FR-2.2b | **Add** player to squad; role assignments Captain/Vice/Starter/Substitute ([P1] p3, p19 §8.2) | roles set only via `roster/setup` | No add or role-change workflow | none | Partial | G5 | — |
| FR-2.2c | Immutable audit trail who/when/why ([P1] p3) | `roster.py` audit entries; `GET /audit/v1/roster/history/{id}` | Live smoke: entry with who = manager email, why | `test_roster_sync.py` | Implemented | — | `d0c19e0` |
| FR-2.3a | Catalogue with variants, discount codes; checkout; PDF receipt ([P1] p4, p15–16 §5.12) | `store.py`, `pdf.py`; `/audit/v1/checkout`, `/audit/v1/inventory/{id}` | WELCOME10, PDF text "PKR 4500.00", signature verified | `test_store.py` | Implemented | — | `64459ec` |
| FR-2.3b | Order states Pending→Refunded with a domain event per transition; scheduled price changes; refund simulation ([P1] p4) | `store.py` (`order.status_changed`, `order.payment_failed` events) | Only paid / payment failure | `test_store.py`, `test_worker.py` | Partial | G9 | `64459ec`, `ac03ef3` |
| FR-2.3c | Product showcase on match pages; pinning updates clients in real time ([P1] p4) | `api_v1.match_detail.pinned_product` | Pinned product shown; no live push | `test_api_v1.py` | Partial | G6 | `9328c22` |
| FR-5.1 | Five-tier RBAC, scoped permissions, policy-as-code, negative tests per boundary ([P1] p4, p16–17 §5.13) | `rbac.py` | Every cell of the [P1] p17 matrix passed (probe); 401 for missing/tampered/alg:none | `test_rbac_security.py::test_probe_matrix`, `test_api_v1.py` | Implemented | — | `43a2a74` |
| NFR-3 | Last unit, 20 concurrent buyers → exactly one 201, stock 0, reserved 0 ([P1] p4, p15 §5.12) | `store.checkout` (conditional UPDATE, CHECK ≥ 0) | Burst probe: 1×201, 19×409 in < 10 s | `test_store.py::test_twenty_concurrent…` | Implemented | — | `64459ec` |
| NFR-4 | Offline cache (SQLite) + persistent queue in §5.14 format + conflict sync ([P1] p4, p17–18 §5.14, p19 §8.4) | `sync.py`, `api_v1.sync`; `mobile/lib/services/{local_store,sync_service}.dart` | Emulator desk check passed (Organizer + Manager); real phone not verified | `test_roster_sync.py` (all resolutions), `mobile/test/widget_test.dart` offline flows | Implemented (device: emulator only) | Real-phone check pending | `d0c19e0`, `cf78240` |
| NFR-5 | OWASP basics, secure token storage, rate limiting, input validation ([P1] p4, p18 §5.13) | `rbac.authenticate`, `main.guards`, `core.read_json`; `token_store.dart` (`FlutterSecureStorage`) | Rate limit ≥ 40×429 + Retry-After + recovery; SQLi id → 400; 413 | `test_rbac_security.py`, `test_health_reset_sports.py` | Implemented | D1, D2 (low) | `43a2a74`, `cf78240` |
| NFR-7 | `docker compose up -d --build` on a clean machine, seeded, `/health` 200 ≤ 120 s ([P1] p4–5 §5.2) | `docker-compose.yml`, `backend/Dockerfile`, `seed.py` | Fresh clone, `--no-cache`: 200 after 32 s; LF line endings; `run_tests.sh` 100755 | `test_health_reset_sports.py` | Implemented | — | `90f7823`, `4c0b63e` |
| §1.3-compose | Compose brings up API, DB, **cache, queue, object store**, workers; forwards `DAY1_SALT` ([P1] p2) | `docker-compose.yml` | db, api, worker; outbox queue; salt forwarded | — | Partial | G10 | `90f7823` |
| §1.2 | Salt from env only, never committed ([P1] p2, p5) | `core.sign`, `.gitignore` | Real salt in no tracked file or git history (scan) | — | Implemented | — | all |
| §5.4–5.5 | Health semantics; reset repeatable with exact baseline ids ([P1] p7) | `main.health`, `seed.reset`, `demo.seed_demo` | Exact reset body; post-reset baseline verified 2026-10-17 | `test_health_reset_sports.py` | Implemented | — | `90f7823`, `9328c22` |
| §8.1 | Android APK at `mobile/release/app-release.apk`, API ≥ 29; server address changeable; Keystore storage ([P1] p19) | `mobile/`, `settings_screen.dart` | apksigner v2 verifies; minSdk 24; installs/runs on API 30 emulator | `flutter test` | Implemented (real phone pending) | — | `cf78240`, `f6d03c3` |
| §8.2 Login | Email + password; role-aware home ([P1] p19) | `login_screen.dart`, `home_shell.dart` | Emulator: 5 roles; tabs differ by role | `widget_test.dart` | Implemented | — | `cf78240` |
| §8.2 Fixtures | Matches with status/time; tap to open ([P1] p19) | `fixtures_screen.dart` | Emulator screenshot | `widget_test.dart` | Implemented | — | `cf78240` |
| §8.2 Match detail | Live score (**real time**), timeline, pinned product ([P1] p19) | `match_screen.dart` | Emulator: score, timeline, featured product | `widget_test.dart` | Partial (polling) | G6 | `cf78240` |
| §8.2 Standings | Points table with qualification status ([P1] p19) | `standings_screen.dart` | Emulator screenshot | `widget_test.dart` | Implemented | D4 | `cf78240` |
| §8.2 Club profile | Club info, roster, staff, venue ([P1] p19) | `club_screen.dart` | API smoke; screen not visually re-checked after theme change | `widget_test.dart` | Unverified (visual) | — | `cf78240` |
| §8.2 Store | Catalogue, variant picker, cart, mock checkout, receipt view/download ([P1] p19) | `store_screen.dart`, `checkout_screen.dart` | Emulator: cart, confirm, receipt, PDF buttons | `widget_test.dart` | Implemented | — | `cf78240` |
| §8.2 Roster mgmt | Club Manager add / transfer / loan / release ([P1] p19) | `roster_screen.dart` | Transfer/loan/release; no add | `widget_test.dart` (offline transfer) | Partial | G5 | `cf78240` |
| §8.2 Scoring entry | Organizer appends score + compensating event ([P1] p19) | `scoring_screen.dart` | Emulator: score offline → sync | `widget_test.dart` | Implemented | — | `cf78240`, `4c0b63e` |
| §8.2 Sync status | Always-visible online/offline/syncing + pending queue ([P1] p19) | `widgets/common.dart` (`SyncStatusChip`), `sync_screen.dart` | Emulator | `widget_test.dart` | Implemented | D3 | `cf78240` |
| §8.3 | Five demo accounts after startup and reset ([P1] p19) | `seed.py` | 5 logins with correct roles | `test_api_v1.py`, `test_rbac_security.py` | Implemented | — | `43a2a74` |
| §9.3 | `COVERAGE.json` within 2 points of measured ([P1] p20–21) | `COVERAGE.json`, `backend/tools/coverage_by_area.py` | Measured = declared (2026-10-18) | `run_tests.sh` | Implemented | — | `ac03ef3` |
| §1.3 docs | README (run + 5 accounts), TRACEABILITY.md, `.env.example`, `tests/`, `run_tests.sh` ([P1] p2) | repo root | Present at `f6d03c3` (GitHub tree) | — | Implemented | — | `ac03ef3`, `c4e0f13` |
| RB-4.5 | Eight short ADRs in `ADR.md`; traceability matrix in `TRACEABILITY.md` ([RB] p4) | `ADR.md`, `TRACEABILITY.md` | 8 ADR headings | — | Implemented | Keep TRACEABILITY in sync with this audit | `ac03ef3` |
| RB-2.1 | Appium 2 + UiAutomator2; Selenium bindings + pytest; Allure or HTML reports; k6 or Locust ([RB] p2) | `qa/` (see `qa/README.md`) | Appium 2.19.0 + uiautomator2 3.10.0 (doctor: 0 required fixes); Selenium Grid 4.24.0 hub + Chrome node; pytest-html reports; k6 0.54.0 | `qa/selenium` 4 passed; `qa/appium` 5 passed on the release APK; k6 smoke all thresholds OK | Implemented (Day 2) | Physical-phone run pending (phone not visible to ADB) | Day 2 (2026-10-18) |
| RB-4.1 | Empty repo at 10:40, code after 10:45; private repo, invite `nascon-eval-26` ([RB] p3) | — | Oct 16 commit; repo public | — | Partial / Unverified | G1, G2 | — |
| RB-4.2 | Push at least once per hour during sprints ([RB] p3) | — | 2 Day 1 windows missed | — | Partial | G3 | — |
