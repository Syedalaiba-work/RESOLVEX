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
| FR-3.2 / §5.4 | Stream key generate / rotate / revoke | — | — | Missing |
| FR-3.3 / §5.5 | 4-way co-stream session + host handoff | `db` table `costream_sessions` | — | Scaffold (schema) |
| FR-4.1 / §5.6 | Dynamic QR resolve, exports, `/q/{code}` 302, scan telemetry | `db` tables `qr_codes`, `qr_scans`; seed | — | Scaffold (schema + seed) |
| FR-4.4 / §5.7 | Guest cart merge (idempotent, stock-capped) | `db` tables `guest_tokens`, `carts`; seed | — | Scaffold (schema + seed) |
| FR-5.3 / FR-5.2 / §5.8 | Moderation (leetspeak, flood), kick/mute idempotency, DLQ | `db` tables `moderation_actions`, `notification_dlq` | — | Scaffold (schema) |
| NFR-6 / §5.9 | `GET /metrics` Prometheus text | — | — | Missing |
| NFR-9 / §5.9 | `DELETE /audit/v1/privacy/user/{id}` | — | — | Missing |
| NFR-1 | WS/SSE score broadcast, p95 < 500 ms | — | — | Missing |
| §6 | Selenium Grid (≥3 nodes), Appium deep links, k6 550 VU, GitHub Actions, reports, `COVERAGE_DAY2.json` | `qa/` (Day 2 morning tooling, to move to `tests/`) | `qa/selenium`, `qa/appium`, `qa/k6` | Partial |
| §1.1 / §6.2.2 | Guest Web Player `/web/*` with 9 `data-testid`s, WCAG AA | — | — | Missing |
| §6.3 | Android `nascon://` intent-filter + deep-link screens | — | — | Missing |
