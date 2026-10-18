# Traceability matrix

Every requirement ID of the Part I specification mapped to implementation and automated tests.
Backend tests are in `tests/` (run with `./run_tests.sh`); mobile tests are in `mobile/test/`.

| ID | Requirement | Implementation | Automated tests |
|---|---|---|---|
| FR-1.1 | Data-driven sports (event / innings / round models), mystery sport via JSON | `backend/app/sports.py` (`validate_sport`, `SEED_SPORTS`), `POST /audit/v1/sports` in `main.py` | `test_health_reset_sports.py` (create, duplicate, field validation, odd best_of), `test_scoring_standings.py::test_mystery_sport_works_without_restart`, `test_api_v1.py::test_match_detail_lists_scoring_events_from_sport_config` (mobile scoring uses config event names, none hard-coded) |
| FR-1.1 | Append-only event-sourced scoring, signed compensating events | `backend/app/scoring.py` (`append_event`, `project`, `score_view`), `core.sign` | `test_scoring_standings.py` (flow, signatures, idempotency, compensation rules, innings/round limits, tie rules) |
| FR-1.2 | League setup scoped to sport (standings registration) | `scoring.register_league`, `POST /audit/v1/leagues` | `test_scoring_standings.py::test_league_registration_and_errors` |
| FR-1.3 | Four fixture formats, custom implementation | `backend/app/fixtures.py` | `test_fixtures.py` (round robin properties for 2–40 teams × 1–2 legs, withdrawals; Swiss exact round 1, brute-force-verified minimum cost, NO_VALID_PAIRING, bye rules; single elim exact seeding/byes/results/third place; double elim counts, routing graph, bracket reset) |
| FR-1.3 | Match status state machine, illegal transitions rejected | `scoring._append` (match_start / match_end rules) | `test_scoring_standings.py::test_state_machine_errors` |
| FR-1.4 | Points tables, configurable points, tie-break order, H2H, differentials, qualification | `backend/app/standings.py` | `test_scoring_standings.py` (table + h2h, 3-way mini-league, draw lots, clinched/eliminated + recompute after compensation, NRR, tiebreak win, undecided) |
| FR-2.1 | Club profiles, tenant isolation | `seed.py` (clubs, tenants, branding), `api_v1.club_detail`, `rbac.POLICY` | `test_api_v1.py::test_clubs_products_and_tenant_isolation`, `test_rbac_security.py` |
| FR-2.2 | Transfers, loans, releases, rules, immutable audit trail | `backend/app/roster.py` | `test_roster_sync.py` (each rule code in order, window boundary, loan + auto-return written once, deferred transfer, idempotency) |
| FR-2.3 | Merchandise store, concurrency-safe checkout, mock gateway, PDF receipt, domain events | `backend/app/store.py`, `pdf.py`, `worker.py` | `test_store.py` (receipt/signature/PDF text, idempotency, discount, out of stock, payment failures release stock, 20 concurrent buyers), `test_worker.py` |
| FR-5.1 | Five-tier RBAC, scoped permissions, negative tests | `backend/app/rbac.py` (`POLICY`, `authenticate`, `probe`) | `test_rbac_security.py::test_probe_matrix` (full spec matrix), `test_api_v1.py` (role checks on mobile routes) |
| NFR-3 | Zero overselling under concurrency | `store.checkout` (atomic conditional UPDATE, CHECK stock >= 0) | `test_store.py::test_twenty_concurrent_buyers_last_unit` |
| NFR-4 | Offline tolerance: queued actions replayed with conflict handling | `backend/app/sync.py`, `api_v1.offline_sync`; mobile local DB + queue in `mobile/lib/` | `test_roster_sync.py` (sync: appended / rebased / duplicate / server_wins / INVALID_BASE_VERSION / NOT_FOUND / resend), `test_api_v1.py::test_sync_applies_role_rules`, mobile tests |
| NFR-5 | Security: token verification, RBAC, rate limiting, input validation, body limit | `rbac.authenticate`, `main.guards`, `core.read_json` / `Checker` | `test_rbac_security.py` (401 cases, rate limit), `test_health_reset_sports.py` (413, malformed JSON, SQL-injection id), `test_store.py::test_hostile_customer_id_is_plain_data` |
| NFR-7 | One-command reproducible stack with seeded baseline | `docker-compose.yml`, `backend/Dockerfile`, `main.lifespan`, `seed.reset` | `test_health_reset_sports.py` (health, reset repeatable); clean-clone `docker compose up -d --build` check (manual, recorded in README) |

## Contract endpoints → code

| Endpoint | Handler | Domain module |
|---|---|---|
| `GET /health` | `main.health` | `seed.is_seeded` |
| `POST /audit/v1/reset` | `main.reset` | `seed.reset`, `demo.seed_demo` |
| `POST /audit/v1/sports` | `main.create_sport` | `sports.create_sport` |
| `POST /audit/v1/fixtures` | `main.generate_fixtures` | `fixtures.generate` |
| `POST /audit/v1/leagues` | `main.register_league` | `scoring.register_league` |
| `POST /audit/v1/events`, `GET /audit/v1/score/{id}` | `main.append_event`, `main.get_score` | `scoring` |
| `GET /audit/v1/standings/{id}` | `main.get_standings` | `standings` |
| `POST /audit/v1/roster/setup`, `/roster/transfer`, `GET /roster/history/{id}` | `main.roster_*` | `roster` |
| `POST /audit/v1/checkout`, `GET /audit/v1/inventory/{id}` | `main.checkout`, `main.get_inventory` | `store` |
| `POST /audit/v1/rbac-matrix`, `/audit/v1/rbac/*` (7 probes) | `main.rbac_matrix`, `main.probe_*` | `rbac` |
| `GET /api/v1/ping` | `main.ping` | rate limiter in `main.guards` |
| `POST /audit/v1/offline-sync` | `main.offline_sync` | `sync` |

## Part II (Day 2) — source: *App Dev Day 2 Problem Statement.pdf*

Status as of the commit that last edited this table. *Done* = code + passing automated test; *Scaffold* = route
or schema exists, business logic still to be written; *Missing* = not started.

| ID | Requirement (Part II section) | Source files | Automated tests | Status |
|---|---|---|---|---|
| P2-SALT | `DAY2_SALT` from env only; `HMAC(DAY2_SALT, entity_id + "\|" + canonical)` (§1.2, §5.3, App. A) | `core.day2_salt`, `core.sign_day2`; `docker-compose.yml`; `.env.example` | `test_day2_foundation.py` (Appendix A vectors 1–2 vs reference, env-driven key, no salt literal in source) | Done |
| P2-RESET | Reset seeds `player-beta-2`, `match-m1` (in_progress 1–0), QR mappings, `guest_anon_tok_7721`, empty cart (§5.2) | `phase2_seed.py`, `seed.PLAYERS`, `db.SCHEMA` (Phase II tables), `main.full_reset` | `test_day2_foundation.py::test_reset_seeds_phase2_baseline`, `::test_reset_is_repeatable_with_phase2_state` | Done |
| FR-4.3 | Guest tokens rejected on every write with 403 `GUEST_WRITE_FORBIDDEN` (§3.2, §5.7 direct check, §7.3) | `main.guards`, `main._guest_token` | `test_day2_guest_guard.py` (chat / checkout / events, PUT/PATCH/DELETE, precedes validation, no side effects, reads allowed, Day 1 unauthenticated writes unchanged) | Done |
| FR-3.2 / §5.4 | Stream key generate / rotate / revoke | `streaming.stream_key` (scaffold, 501) | `test_day2_contracts.py` (XFAIL until implemented) | Scaffold — team implements |
| FR-3.3 / §5.5 | 4-way co-stream session + host handoff | `costream.costream_session` (scaffold, 501), table `costream_sessions` | `test_day2_contracts.py` (incl. hidden scenario 1) | Scaffold — team implements |
| FR-4.1 / §5.6 | Dynamic QR resolve, exports, `/q/{code}` 302, scan telemetry | `qr_guest.qr_resolve`, `qr_export`, `short_link` (scaffold, 501), tables `qr_codes`, `qr_scans`, seed | `test_day2_contracts.py` (incl. hidden scenario 2) | Scaffold — team implements |
| FR-4.4 / §5.7 | Guest cart merge (idempotent, stock-capped) | `qr_guest.guest_cart_merge` (scaffold, 501), tables `guest_tokens`, `carts`, seed | `test_day2_contracts.py` (incl. hidden scenario 4) | Scaffold — team implements |
| FR-5.3 / FR-5.2 / §5.8 | Moderation (leetspeak, flood), kick/mute idempotency, DLQ | `moderation_dlq.moderation_test` (scaffold, 501), tables `moderation_actions`, `notification_dlq` | `test_day2_contracts.py` (incl. hidden scenario 3) | Scaffold — team implements |
| NFR-6 / §5.9 | `GET /metrics` Prometheus text (`text/plain; version=0.0.4`, 5 series) | `observability.metrics_text`, `main.metrics` | `test_day2_observability_privacy.py` (format, series, values follow DB state) | Done (bitrate reported 0 until a media server exists) |
| NFR-9 / §5.9 | `DELETE /audit/v1/privacy/user/{id}`; scan telemetry without PII | `observability.erase_user`, `main.privacy_erase`, `db` table `qr_scans` | `test_day2_observability_privacy.py` (anonymised, tokens wiped, login blocked, idempotent, 404, no PII columns) | Done |
| NFR-1 | SSE score broadcast `GET /api/v1/matches/{id}/stream`, < 500 ms | `web.match_stream` (100 ms poll of the event log) | `tests/selenium` test 3 (score visible < 500 ms after POST /audit/v1/events, Chrome + Firefox) | Partial (no 25-client p95 probe yet; no WebSocket route) |
| §6 | Selenium Grid (≥3 nodes), Appium deep links, k6 550 VU, GitHub Actions, reports, `COVERAGE_DAY2.json` | `qa/selenium/docker-compose.grid.yml` (hub + 2 Chrome + 1 Firefox, 4.24.0), `tests/selenium/`, `tests/reports/`, `tests/conftest.py` | Grid `/status` ready with 3 nodes; `pytest -n 3 tests/selenium/` | Partial (root compose with hub + 3 nodes and media stack, Appium deep-link suite pending) |
| §1.1 / §6.2.2 / NFR-8 / FR-4.2 | Guest Web Player `/web/*` with 9 `data-testid`s, guest session, read-only boundary + progressive modal, keyboard/ARIA/48 px | `web.py`, `web/player.html` | `test_day2_web.py`; `tests/selenium/test_guest_grid.py` (8 passed, 2 XFAIL awaiting `/q/`) | Done (video renders a stream only once a media server exists) |
| §6.3 | Android `nascon://` intent-filter; `nascon://entity/match-m1` and `nascon://stream/cs-session-101` open Match Live / Co-stream directly, no login wall | `AndroidManifest.xml` (VIEW/DEFAULT/BROWSABLE, scheme nascon), `lib/screens/deep_link_screen.dart`, `main.dart onGenerateRoute` | Flutter: 2 deep-link widget tests; `tests/appium/test_mobile_deeplink.py` (2 passed with the exact `adb shell am start -W` commands) | Partial: 2 s budget met warm (Android TotalTime 465-492 ms), missed cold on the emulator (~2.9-3.1 s); cross-surface chat test pending the co-stream/moderation handlers |
| §1.3 CI | `.github/workflows/autograde.yml`: ancestry, stack + /health, backend tests, reset probe, grid ≥3 nodes, Selenium, k6, report artifact | `.github/workflows/autograde.yml` | YAML parsed; not yet run on GitHub (needs repository secrets `DAY1_SALT`, `DAY2_SALT`) | Done (unverified on GitHub) |
| §6.4 NFR-2 | `tests/k6_load.js` exact profile (500 + 50 VUs, 15 s, `rate==0.00`, `p(95)<800`) | `tests/k6_load.js` | `k6 inspect` OK; a full run needs the QR and moderation handlers | Done (file); run pending |
| §7.2 | `COVERAGE_DAY2.json` measured by `backend/tools/coverage_by_area.py --day2` (printed by `run_tests.sh`) | `COVERAGE_DAY2.json` | measured 2026-10-18 on scaffolds — **regenerate after implementing the handlers** | Done (must be re-measured) |
| §1.3 / §5.1 / §6.1 compose | Root stack: Core API 8080, DB, Redis, MinIO, MediaMTX 1935/8888/8889, hub + 3 nodes on 4444; both salts | `docker-compose.yml`; `/health` checks Redis + media (`main._redis_ok`, `main._media_ok`) | `test_day2_health.py`; full root stack under the QA project: `/health` 200, hub ready with 3 nodes | Partial: **MinIO blocked** (image cannot be pulled) |
