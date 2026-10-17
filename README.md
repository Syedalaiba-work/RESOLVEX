# RESOLVEX

NaSCon '26 App Dev — Part I: **Multi-Sport League & Club Operations Platform**.
Self-hosted backend (FastAPI + PostgreSQL 16, Docker Compose) and an Android app (Flutter) in `mobile/`.

## Run the backend

Only Docker is required.

```sh
DAY1_SALT=<your-team-salt> docker compose up -d --build
curl http://localhost:8080/health          # {"status":"ok"} once the database is ready and seeded
```

- API on host port **8080**. The salt is read only from the `DAY1_SALT` environment variable (forwarded by
  `docker-compose.yml`); it is never stored in the repository. For local runs you can copy `.env.example` to `.env`.
- Startup creates the schema and seeds the baseline automatically; `POST /audit/v1/reset` restores it at any time.
- Services: `api` (FastAPI, port 8080), `db` (PostgreSQL 16, internal only, persistent volume `db_data`),
  `worker` (internal queue consumer for order domain events).

## Demo accounts (exist after every startup and every reset)

| Role | Email | Password | Scope |
|---|---|---|---|
| Platform Super-Admin | admin@nascon.test | Nascon@26 | all tenants |
| League Organizer | organizer@nascon.test | Nascon@26 | owns `league-alpha-1` (tenant-alpha) |
| Club Manager | manager@nascon.test | Nascon@26 | owns `club-alpha-1` |
| Player | player@nascon.test | Nascon@26 | `player-alpha-1` |
| General Viewer | viewer@nascon.test | Nascon@26 | read-only in tenant-alpha |

Demo data for the app (rebuilt on every reset): league `league-alpha-1` with six fixtures (completed, live,
upcoming), roster squads `sq-alpha-1` / `sq-alpha-2` with an open transfer window, jersey product
`prod-jersey-001` (variants `var-jersey-001-M`, `var-jersey-001-L`).

## Tests and coverage

```sh
./run_tests.sh
```

Runs the pytest suite inside the API container (against a separate `nascon_test` database) and prints the
per-area line coverage in the `COVERAGE.json` format. Tests live in `tests/`.

## Mobile app

Source in `mobile/`, installable build at `mobile/release/app-release.apk` (Android 10+). The server address is
changeable in the app's Settings (emulator `http://10.0.2.2:8080`, phone: `http://<laptop-LAN-IP>:8080`).
See `mobile/README.md`.

## Layout

| Path | Contents |
|---|---|
| `backend/app/main.py` | HTTP layer for `/health`, `/audit/v1/*`, error handling, body limit, rate limit |
| `backend/app/fixtures.py` | Round robin, Swiss, single and double elimination |
| `backend/app/sports.py`, `scoring.py` | Data-driven sports, event-sourced scoring, leagues |
| `backend/app/standings.py` | Tables, tie-breaks, H2H, qualification |
| `backend/app/store.py`, `pdf.py` | Checkout, mock gateway, PDF receipts |
| `backend/app/roster.py` | Roster scenarios, transfers, loans, history |
| `backend/app/rbac.py` | JWT, five-role policy layer, probes, login |
| `backend/app/sync.py` | Offline action replay |
| `backend/app/api_v1.py`, `demo.py` | Mobile API and demo data |
| `backend/app/worker.py` | Internal queue consumer |
| `docs/MOBILE_API.md` | Mobile API contract |

## Troubleshooting

- `docker compose logs api` / `docker compose logs db` show startup errors.
- Port 8080 already in use → stop the other service; the grader expects 8080.
- Health returns 503 until the database is reachable and seeded (normally a few seconds).
- Data is kept in the `db_data` volume; `docker compose down -v` deletes it (startup re-seeds).
