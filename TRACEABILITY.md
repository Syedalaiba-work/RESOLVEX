# Traceability matrix

Every requirement ID of the Part I specification mapped to implementation and automated tests.
Backend tests are in `tests/` (run with `./run_tests.sh`); mobile tests are in `mobile/test/`.

| ID | Requirement | Implementation | Automated tests |
|---|---|---|---|
| FR-1.1 | Data-driven sports (event / innings / round models), mystery sport via JSON | `backend/app/sports.py` (`validate_sport`, `SEED_SPORTS`), `POST /audit/v1/sports` in `main.py` | `test_health_reset_sports.py` (create, duplicate, field validation, odd best_of), `test_scoring_standings.py::test_mystery_sport_works_without_restart` |
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
