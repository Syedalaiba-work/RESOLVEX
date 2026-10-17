"""Production routes for the mobile app (docs/MOBILE_API.md). Same domain services as /audit/v1,
behind JWT authentication and the RBAC policy layer."""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app import rbac, roster, scoring, standings, store, sync
from app.core import ApiError, read_json
from app.db import tx

router = APIRouter(prefix="/api/v1")


def _meta(conn, key):
    row = conn.execute("SELECT value FROM meta WHERE key = %s", (key,)).fetchone()
    return row["value"] if row else {}


def _visible_leagues(conn, claims):
    if claims["role"] == "super_admin":
        rows = conn.execute("SELECT * FROM leagues ORDER BY league_id").fetchall()
    else:
        rows = conn.execute("SELECT * FROM leagues WHERE tenant_id = %s ORDER BY league_id",
                            (claims["tenant_id"],)).fetchall()
    return [dict(r) for r in rows]


def _league_target(conn, league_id):
    row = conn.execute("SELECT * FROM leagues WHERE league_id = %s", (league_id,)).fetchone()
    return dict(row) if row else {"league_id": league_id, "tenant_id": None}


@router.get("/me")
def me(request: Request):
    claims = rbac.authenticate(request)
    with tx() as conn:
        return rbac.profile(conn, rbac.user_by_email(conn, claims["sub"]))


@router.get("/leagues")
def leagues(request: Request):
    claims = rbac.authenticate(request)
    with tx() as conn:
        return [{"league_id": r["league_id"], "name": r["name"], "sport_id": r["sport_id"], "tenant_id": r["tenant_id"]}
                for r in _visible_leagues(conn, claims)]


@router.get("/fixtures")
def fixtures(request: Request, league_id: str | None = None):
    claims = rbac.authenticate(request)
    with tx() as conn:
        visible = {r["league_id"] for r in _visible_leagues(conn, claims)}
        if league_id is not None:
            if league_id not in visible:
                raise ApiError(403, "FORBIDDEN", "You cannot view this league.")
            visible = {league_id}
        names, schedule = _meta(conn, "team_names"), _meta(conn, "schedule")
        rows = conn.execute("SELECT * FROM matches WHERE league_id = ANY(%s) ORDER BY created_order",
                            (list(visible),)).fetchall()
        out = []
        for m in rows:
            sport = scoring.get_sport(conn, m["sport_id"])
            state = scoring.project(m, sport, scoring.load_events(conn, m["match_id"]))
            out.append({
                "match_id": m["match_id"], "league_id": m["league_id"], "sport_id": m["sport_id"],
                "home_team_id": m["home_team_id"], "away_team_id": m["away_team_id"],
                "home_name": names.get(m["home_team_id"], m["home_team_id"]),
                "away_name": names.get(m["away_team_id"], m["away_team_id"]),
                "status": state["status"], "scheduled_at": schedule.get(m["match_id"]),
                "home_score": state["side"][m["home_team_id"]]["score"],
                "away_score": state["side"][m["away_team_id"]]["score"],
            })
    out.sort(key=lambda f: (f["scheduled_at"] or "", f["match_id"]))
    return out


def _check_league_visible(conn, claims, league_id):
    target = _league_target(conn, league_id)
    if claims["role"] != "super_admin" and target["tenant_id"] != claims["tenant_id"]:
        raise ApiError(403, "FORBIDDEN", "You cannot view this league.")


@router.get("/matches/{match_id}")
def match_detail(request: Request, match_id: str):
    claims = rbac.authenticate(request)
    view = scoring.score_view(match_id)
    with tx() as conn:
        _check_league_visible(conn, claims, view["league_id"])
        names, schedule, pinned = _meta(conn, "team_names"), _meta(conn, "schedule"), _meta(conn, "pinned")
        product = _products(conn, pinned.get(match_id)) if pinned.get(match_id) else []
    return {**view, "home_name": names.get(view["home"]["team_id"], view["home"]["team_id"]),
            "away_name": names.get(view["away"]["team_id"], view["away"]["team_id"]),
            "scheduled_at": schedule.get(match_id), "pinned_product": product[0] if product else None}


@router.get("/standings/{league_id}")
def league_standings(request: Request, league_id: str):
    claims = rbac.authenticate(request)
    with tx() as conn:
        _check_league_visible(conn, claims, league_id)
        names = _meta(conn, "team_names")
    table = standings.standings(league_id)
    return {**table, "names": {t["team_id"]: names.get(t["team_id"], t["team_id"]) for t in table["table"]}}


@router.get("/clubs")
def clubs(request: Request):
    claims = rbac.authenticate(request)
    with tx() as conn:
        if claims["role"] == "super_admin":
            rows = conn.execute("SELECT club_id, name, tenant_id FROM clubs ORDER BY club_id").fetchall()
        else:
            rows = conn.execute("SELECT club_id, name, tenant_id FROM clubs WHERE tenant_id = %s ORDER BY club_id",
                                (claims["tenant_id"],)).fetchall()
    return [dict(r) for r in rows]


@router.get("/clubs/{club_id}")
def club_detail(request: Request, club_id: str):
    claims = rbac.authenticate(request)
    target = rbac.load_target("club", club_id)
    rbac.authorize("club.read", claims, target)
    with tx() as conn:
        roster_rows = []
        for row in conn.execute("SELECT state FROM roster_leagues").fetchall():
            st = row["state"]
            for pid, reg in st["registrations"].items():
                sq = st["squads"].get(reg["squad_id"])
                if sq and sq["club_id"] == club_id:
                    p = st["players"][pid]
                    roster_rows.append({"player_id": pid, "name": p["name"], "position": p["position"],
                                        "role": reg["role"], "squad_id": reg["squad_id"]})
    profile = target["profile"]
    return {"club_id": club_id, "name": target["name"], "tenant_id": target["tenant_id"],
            "home_venue": profile.get("home_venue"), "social": profile.get("social", {}),
            "staff": profile.get("staff", []), "history": profile.get("history", []),
            "roster": sorted(roster_rows, key=lambda r: r["name"])}


def _products(conn, product_id=None, tenant_id=None):
    sql, args = "SELECT * FROM products", []
    if product_id:
        sql, args = sql + " WHERE product_id = %s", [product_id]
    elif tenant_id:
        sql, args = sql + " WHERE tenant_id = %s", [tenant_id]
    out = []
    for p in conn.execute(sql + " ORDER BY product_id", args).fetchall():
        variants = conn.execute("SELECT variant_id, label, price_minor, currency, stock FROM variants "
                                "WHERE product_id = %s ORDER BY variant_id", (p["product_id"],)).fetchall()
        out.append({"product_id": p["product_id"], "name": p["name"], "category": p["category"],
                    "description": p["description"], "club_id": p["club_id"], "variants": [dict(v) for v in variants]})
    return out


@router.get("/products")
def products(request: Request):
    claims = rbac.authenticate(request)
    with tx() as conn:
        return _products(conn, tenant_id=None if claims["role"] == "super_admin" else claims["tenant_id"])


@router.post("/checkout")
async def checkout(request: Request):
    claims = rbac.authenticate(request)
    body = await read_json(request)
    body["customer_id"] = claims["sub"]
    code, response = await run_in_threadpool(store.checkout, body)
    return JSONResponse(status_code=code, content=response)


def _authorize_event(claims, body):
    with tx() as conn:
        match = conn.execute("SELECT league_id FROM matches WHERE match_id = %s",
                             (body.get("match_id"),)).fetchone()
        league_id = match["league_id"] if match else (body.get("payload") or {}).get("league_id")
        target = _league_target(conn, league_id)
    rbac.authorize("league.events.write", claims, target)


@router.post("/events")
async def events(request: Request):
    claims = rbac.authenticate(request)
    body = await read_json(request)
    _authorize_event(claims, body)
    code, response = await run_in_threadpool(scoring.append_event, body)
    return JSONResponse(status_code=code, content=response)


def _roster_state(conn, league_id):
    row = conn.execute("SELECT state FROM roster_leagues WHERE league_id = %s", (league_id,)).fetchone()
    if row is None:
        raise ApiError(404, "LEAGUE_NOT_FOUND", f"League {league_id} does not exist.", {"league_id": league_id})
    return row["state"]


@router.get("/roster/{league_id}")
def roster_view(request: Request, league_id: str):
    claims = rbac.authenticate(request)
    with tx() as conn:
        state = _roster_state(conn, league_id)
    if claims["role"] not in ("club_manager", "super_admin") or (
            claims["role"] != "super_admin" and state["league"]["tenant_id"] != claims["tenant_id"]):
        raise ApiError(403, "FORBIDDEN", "Only club managers can manage rosters.")
    squads = []
    for sid, sq in state["squads"].items():
        members = [{"player_id": pid, "name": state["players"][pid]["name"],
                    "position": state["players"][pid]["position"], "role": reg["role"],
                    "registration_type": reg["registration_type"]}
                   for pid, reg in state["registrations"].items() if reg["squad_id"] == sid]
        squads.append({"squad_id": sid, "club_id": sq["club_id"], "name": sq["name"],
                       "players": sorted(members, key=lambda m: m["name"])})
    return {"league_id": league_id, "squads": squads, "transfer_window": state["league"]["transfer_window"],
            "max_squad_size": state["league"]["max_squad_size"]}


def _authorize_transfer(claims, body):
    if claims["role"] == "super_admin":
        return
    if claims["role"] != "club_manager":
        raise ApiError(403, "FORBIDDEN", "Only club managers can move players.")
    with tx() as conn:
        row = conn.execute("SELECT state FROM roster_leagues WHERE league_id = %s",
                           (body.get("league_id"),)).fetchone()
    if row is None:
        return  # the domain service reports LEAGUE_NOT_FOUND
    squad = row["state"]["squads"].get(body.get("from_squad_id"))
    if squad and (squad["club_id"] != claims["club_id"] or squad["tenant_id"] != claims["tenant_id"]):
        raise ApiError(403, "FORBIDDEN", "You can only move players out of your own club.")


@router.post("/roster/transfer")
async def roster_transfer(request: Request):
    claims = rbac.authenticate(request)
    body = await read_json(request)
    body["requested_by"] = claims["sub"]
    _authorize_transfer(claims, body)
    code, response = await run_in_threadpool(roster.transfer, body)
    return JSONResponse(status_code=code, content=response)


@router.post("/sync")
async def offline_sync(request: Request):
    claims = rbac.authenticate(request)
    body = await read_json(request)

    def authorizer(action):
        try:
            if action.get("type") == "score_event":
                _authorize_event(claims, action.get("payload") or {})
            elif action.get("type") == "roster_transfer":
                if isinstance(action.get("payload"), dict):
                    action["payload"]["requested_by"] = claims["sub"]
                _authorize_transfer(claims, action.get("payload") or {})
        except ApiError as e:
            return e.code
        return None

    return await run_in_threadpool(sync.sync, body, authorizer)
