# Part II root `docker-compose.yml` — structural plan (team writes the file)

Source: Part II §1.3, §5.2, §6.1, §6.2.1, §7.3 and checklist C. The existing `db`, `api` and `worker` services
stay as they are (both salts are already forwarded). Add the services below to the **root** file: the GitHub
runner brings everything up with one `DAY1_SALT=… DAY2_SALT=… docker compose up -d --build`, and every container
must be healthy with `/health` = 200 within 120 s.

| Service | Image (pre-pulled bundle) | Host ports (exact, §6.1) | Must have | Health intent |
|---|---|---|---|---|
| `redis` | `redis:7-alpine` | none needed | — | `redis-cli ping` |
| `minio` | `minio/minio:RELEASE.2024-09-22T00-33-43Z` (**not on this laptop yet**) | none needed (console optional) | `command: server /data`, root user/password from env, a volume | `mc ready` / HTTP `/minio/health/live` |
| `media` (MediaMTX) | `bluenviron/mediamtx:1.9.1` | `1935` RTMP, `8888` HLS, `8889` WebRTC | publish auth that asks the API whether a stream key is active (revoked → reject, §5.4) | HTTP on the API port of MediaMTX |
| `selenium-hub` | `selenium/hub:4.24.0` (spec example shows 4.25.0; 4.24.0 is what was pre-pulled) | `4444`, `4442`, `4443` | — | `/status` → `ready: true` |
| `node-chrome-1`, `node-chrome-2`, `node-firefox` | `selenium/node-chrome:4.24.0`, `selenium/node-firefox:4.24.0` | none | `shm_size: "1gb"`, `SE_START_VNC=false`, `SE_NODE_MAX_SESSIONS=2`, event-bus env, `extra_hosts: host.docker.internal:host-gateway` (Linux runner) | node registers with hub |

Working reference for the grid part: `qa/selenium/docker-compose.grid.yml` (hub + 3 nodes, verified ready with
3 nodes on 2026-10-18). Differences for the root file: bind the spec's plain host ports, drop the
`qa-target` external network, and either set `SE_NODE_HOST` per node or keep nodes on a single network.

`api` changes to plan:
- `GET /health` must also check Redis and the media server (§5.1) — return 503 until both answer.
- `depends_on` with `condition: service_healthy` for `db`, `redis`, `media`.
- Env for the media server URL and MinIO endpoint/credentials (add every new variable to `.env.example`).

Verification commands (after `docker compose up -d --build`):

```sh
curl -s http://localhost:8080/health                       # {"status":"ok"} within 120 s
curl -s http://localhost:4444/status | python -c "import json,sys; v=json.load(sys.stdin)['value']; print(v['ready'], len(v['nodes']))"   # True 3
docker compose ps                                            # every service healthy
```

Port conflicts on this laptop: 8080 is used by the running submission stack and 8000/8001 by the separate
practice project; stop the submission stack (`docker compose stop`) before testing the new root file locally.
