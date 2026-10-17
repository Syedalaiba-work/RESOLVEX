# Mobile API (`/api/v1/*`)

Production routes used by the Flutter app. All bodies JSON. Errors use the contract shape
`{"error": {"code", "message", "details"}}`. Rate limit: 100 requests / rolling 10 s per IP (429 `RATE_LIMITED`,
`Retry-After` header). Auth: `Authorization: Bearer <jwt>` on everything except login and ping.
Money is integer minor units (paisa), currency `PKR`. Timestamps `YYYY-MM-DDTHH:MM:SSZ`.

| Method & path | Who | Body / query | Response 200/201 |
|---|---|---|---|
| `GET /api/v1/ping` | anyone | – | `{"pong": true}` |
| `POST /api/v1/auth/login` | anyone | `{email, password}` | `{token, user, tenant}` (below); 401 `UNAUTHENTICATED` on bad credentials |
| `GET /api/v1/me` | any role | – | `{user, tenant}` |
| `GET /api/v1/leagues` | any role | – | `[{league_id, name, sport_id, tenant_id}]` (super admin: all tenants) |
| `GET /api/v1/fixtures` | any role | `?league_id=` optional | `[{match_id, league_id, sport_id, home_team_id, away_team_id, home_name, away_name, status, scheduled_at, home_score, away_score}]` |
| `GET /api/v1/matches/{match_id}` | any role | – | same body as `GET /audit/v1/score/{id}` plus `home_name`, `away_name`, `scheduled_at`, `pinned_product` (product object or null), `scoring_events` (sorted event names from the sport's config) |
| `GET /api/v1/standings/{league_id}` | any role | – | same body as `GET /audit/v1/standings/{id}` plus `names: {team_id: name}` |
| `GET /api/v1/clubs` | any role | – | `[{club_id, name, tenant_id}]` |
| `GET /api/v1/clubs/{club_id}` | any role in tenant | – | `{club_id, name, tenant_id, home_venue, social, staff, history, roster: [{player_id, name, position, role, squad_id}]}` |
| `GET /api/v1/products` | any role | – | `[{product_id, name, category, description, club_id, variants: [{variant_id, label, price_minor, currency, stock}]}]` |
| `POST /api/v1/checkout` | any role | same body as `/audit/v1/checkout` (customer_id is forced to the user) | same response as `/audit/v1/checkout` |
| `POST /api/v1/events` | league_organizer (own league), super_admin | same body as `/audit/v1/events` | same response |
| `GET /api/v1/roster/{league_id}` | club_manager, super_admin | – | `{league_id, squads: [{squad_id, club_id, name, players: [{player_id, name, position, role}]}], transfer_window}` |
| `POST /api/v1/roster/transfer` | club_manager (own club squads), super_admin | same body as `/audit/v1/roster/transfer` (`requested_by` forced to the user) | same response |
| `POST /api/v1/sync` | any role | same body as `/audit/v1/offline-sync` | same response |

`user` = `{email, role, display_name, tenant_id, league_id, club_id, player_id}`;
`role` is one of `super_admin`, `league_organizer`, `club_manager`, `player`, `viewer`.
`tenant` = `{tenant_id, name, branding: {primary_color, accent_color, logo_text}}` (null for super admin).

Demo data after every reset: league `league-alpha-1` (tenant-alpha, football) with six fixtures between
`club-alpha-1`, `club-alpha-2`, `alpha-falcons`, `alpha-tigers` (some completed, one in progress, one upcoming);
roster league `league-alpha-1` with squads `sq-alpha-1` (club-alpha-1) and `sq-alpha-2` (club-alpha-2), transfer window
covering the current date (±30 days). The organizer owns `league-alpha-1`.

## Offline queue action format (spec 5.14) — the app must store exactly this

```json
{ "action_id": "a1", "type": "score_event", "queued_at": "2026-10-17T11:00:00Z", "base_version": 3,
  "payload": { "event_id": "evt-9", "match_id": "m1", "type": "score",
               "payload": { "team_id": "t1", "event_type": "goal" } } }
{ "action_id": "a2", "type": "roster_transfer", "queued_at": "...", "base_version": 1,
  "payload": { ...same body as POST /api/v1/roster/transfer... } }
```
Sync request: `{"device_id": "...", "actions": [ ... ]}` → per-action results
`{action_id, status: applied|rejected|duplicate, resolution, error_code, processed_order, server_version, signature}`.
