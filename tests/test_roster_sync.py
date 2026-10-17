import pytest

from conftest import err


def scenario(client, **league_overrides):
    league = {"league_id": "lg-r1", "tenant_id": "tenant-alpha", "sport_id": "football",
              "transfer_window": {"open": "2026-09-01", "close": "2026-09-30"},
              "max_squad_size": 3, "required_positions": {"gk": 1}, **league_overrides}
    body = {
        "league": league,
        "squads": [{"squad_id": "sq-a", "club_id": "club-a", "tenant_id": "tenant-alpha", "name": "A"},
                   {"squad_id": "sq-b", "club_id": "club-b", "tenant_id": "tenant-alpha", "name": "B"},
                   {"squad_id": "sq-x", "club_id": "club-x", "tenant_id": "tenant-beta", "name": "X"}],
        "players": [{"player_id": "p1", "name": "Ali", "position": "gk", "squad_id": "sq-a", "role": "captain"},
                    {"player_id": "p2", "name": "Bilal", "position": "df", "squad_id": "sq-a", "role": "starter"},
                    {"player_id": "p3", "name": "Chand", "position": "df", "squad_id": "sq-b", "role": "starter"},
                    {"player_id": "p4", "name": "Dawood", "position": "fw", "squad_id": "sq-b", "role": "starter"}],
        "matches_in_progress": [],
    }
    return client.post("/audit/v1/roster/setup", json=body)


def tr(client, rid, player="p2", type_="transfer", frm="sq-a", to="sq-b", eff="2026-09-15", end=None, league="lg-r1"):
    return client.post("/audit/v1/roster/transfer", json={
        "request_id": rid, "league_id": league, "player_id": player, "type": type_, "from_squad_id": frm,
        "to_squad_id": to, "effective_date": eff, "loan_end_date": end, "reason": "Tactical move",
        "requested_by": "user-77"})


def test_setup_counts(fresh):
    r = scenario(fresh)
    assert r.status_code == 201
    assert r.json() == {"league_id": "lg-r1", "status": "configured",
                        "squad_counts": {"sq-a": 2, "sq-b": 2, "sq-x": 0}}


def test_transfer_success_audit_and_idempotency(fresh):
    scenario(fresh)
    r = tr(fresh, "tr-001", eff="2026-09-30")  # last day of window, inclusive
    assert r.status_code == 201
    b = r.json()
    assert b["status"] == "accepted" and b["state"] == "active" and b["blocking_match_id"] is None
    assert b["registration"] == {"player_id": "p2", "league_id": "lg-r1", "squad_id": "sq-b", "parent_squad_id": None,
                                 "registration_type": "transfer", "start_date": "2026-09-30", "loan_end_date": None,
                                 "role": "substitute"}
    a = b["audit_entry"]
    assert a["audit_id"] == "au-0001" and a["action"] == "transfer" and a["who"] == "user-77"
    assert a["why"] == "Tactical move" and a["from_squad_id"] == "sq-a" and a["to_squad_id"] == "sq-b"
    again = tr(fresh, "tr-001", eff="2026-09-30")
    assert again.status_code == 200 and again.json() == b
    h = fresh.get("/audit/v1/roster/history/p2?as_of=2026-10-01").json()
    assert h["current_squad_id"] == "sq-b" and len(h["history"]) == 1


@pytest.mark.parametrize("kwargs, code, status", [
    ({"league": "ghost"}, "LEAGUE_NOT_FOUND", 404),
    ({"player": "ghost"}, "PLAYER_NOT_FOUND", 404),
    ({"to": "sq-ghost"}, "SQUAD_NOT_FOUND", 404),
    ({"to": "sq-x"}, "CROSS_TENANT_TRANSFER", 409),
    ({"frm": "sq-b"}, "NOT_IN_SQUAD", 409),
    ({"eff": "2026-10-01"}, "TRANSFER_WINDOW_CLOSED", 409),
    ({"player": "p2", "to": "sq-b"}, None, 201),
])
def test_rule_failures(fresh, kwargs, code, status):
    scenario(fresh)
    r = tr(fresh, "rq", **kwargs)
    assert r.status_code == status
    if code:
        assert err(r) == code
        # rejected requests write no audit entry
        assert fresh.get("/audit/v1/roster/history/p2").json()["history"] == []


def test_squad_full_and_min_position(fresh):
    scenario(fresh)
    assert tr(fresh, "r1", player="p2", eff="2026-09-10").status_code == 201  # sq-b now 3 (max 3)
    r = tr(fresh, "r2", player="p1", eff="2026-09-11")
    assert err(r) == "SQUAD_FULL"
    scenario(fresh, max_squad_size=10)
    r = tr(fresh, "r3", player="p1", eff="2026-09-11")  # only gk of sq-a
    assert r.status_code == 409 and err(r) == "MIN_POSITION_VIOLATION"


def test_validation_errors(fresh):
    scenario(fresh)
    assert err(tr(fresh, "v1", type_="swap")) == "VALIDATION_ERROR"
    assert err(tr(fresh, "v2", type_="loan", end="2026-09-01")) == "VALIDATION_ERROR"  # end <= effective
    assert err(tr(fresh, "v3", eff="2026-13-45")) == "VALIDATION_ERROR"
    assert err(tr(fresh, "v4", to=None)) == "VALIDATION_ERROR"


def test_release_any_date_and_window_not_needed(fresh):
    scenario(fresh)
    r = tr(fresh, "rel", player="p4", type_="release", frm="sq-b", to=None, eff="2027-01-01")
    assert r.status_code == 201 and r.json()["registration"] is None
    h = fresh.get("/audit/v1/roster/history/p4?as_of=2027-01-02").json()
    assert h["current_squad_id"] is None and h["history"][0]["action"] == "release"
    assert h["history"][0]["to_squad_id"] is None


def test_loan_and_automatic_return_written_once(fresh):
    scenario(fresh, max_squad_size=10)
    r = tr(fresh, "ln", type_="loan", eff="2026-09-05", end="2026-12-31")
    assert r.status_code == 201
    reg = r.json()["registration"]
    assert reg["registration_type"] == "loan" and reg["parent_squad_id"] == "sq-a" and reg["loan_end_date"] == "2026-12-31"
    during = fresh.get("/audit/v1/roster/history/p2?as_of=2026-10-01").json()
    assert during["current_squad_id"] == "sq-b" and during["parent_squad_id"] == "sq-a"
    assert err(tr(fresh, "again", frm="sq-b", to="sq-a", eff="2026-09-20")) == "PLAYER_ON_LOAN"
    after = fresh.get("/audit/v1/roster/history/p2?as_of=2027-01-05").json()
    assert after["current_squad_id"] == "sq-a" and after["parent_squad_id"] is None
    assert [e["action"] for e in after["history"]] == ["loan", "loan_return"]
    ret = after["history"][1]
    assert ret["who"] == "system" and ret["effective_date"] == "2027-01-01" and ret["from_squad_id"] == "sq-b"
    again = fresh.get("/audit/v1/roster/history/p2?as_of=2027-01-06").json()
    assert [e["action"] for e in again["history"]] == ["loan", "loan_return"]  # never duplicated


def test_loaned_player_counts_for_borrower(fresh):
    scenario(fresh)  # max 3, sq-b has 2
    assert tr(fresh, "ln", type_="loan", eff="2026-09-05", end="2026-12-31").status_code == 201  # sq-b -> 3
    assert err(tr(fresh, "full", player="p1", eff="2026-09-06")) == "SQUAD_FULL"


def test_deferred_when_in_progress_match(fresh):
    scenario_body = {
        "league": {"league_id": "lg-r1", "tenant_id": "tenant-alpha", "sport_id": "football",
                   "transfer_window": {"open": "2026-09-01", "close": "2026-09-30"}},
        "squads": [{"squad_id": "sq-a", "club_id": "c1", "tenant_id": "tenant-alpha", "name": "A"},
                   {"squad_id": "sq-b", "club_id": "c2", "tenant_id": "tenant-alpha", "name": "B"}],
        "players": [{"player_id": "p1", "name": "Ali", "position": "gk", "squad_id": "sq-a", "role": "captain"},
                    {"player_id": "p2", "name": "Bilal", "position": "df", "squad_id": "sq-a", "role": "starter"}],
        "matches_in_progress": [{"match_id": "m-live", "home_squad_id": "sq-a", "away_squad_id": "sq-b"}],
    }
    assert fresh.post("/audit/v1/roster/setup", json=scenario_body).status_code == 201
    r = tr(fresh, "late", eff="2026-09-30")
    assert r.status_code == 201
    assert r.json()["state"] == "deferred_until_match_end" and r.json()["blocking_match_id"] == "m-live"
    assert r.json()["audit_entry"]["state"] == "deferred_until_match_end"


def test_history_unknown_player(fresh):
    r = fresh.get("/audit/v1/roster/history/nobody")
    assert r.status_code == 404 and err(r) == "PLAYER_NOT_FOUND"


# --- offline sync -------------------------------------------------------------------------------------

def _match(client):
    client.post("/audit/v1/events", json={"event_id": "i", "match_id": "m1", "type": "match_init",
                                          "payload": {"sport_id": "football", "home_team_id": "t1", "away_team_id": "t2"}})
    client.post("/audit/v1/events", json={"event_id": "s", "match_id": "m1", "type": "match_start", "payload": {}})


def score_action(aid, event_id, base, queued="2026-10-17T11:00:00Z", team="t1"):
    return {"action_id": aid, "type": "score_event", "queued_at": queued, "base_version": base,
            "payload": {"event_id": event_id, "match_id": "m1", "type": "score",
                        "payload": {"team_id": team, "event_type": "goal"}}}


def roster_action(aid, rid, base, queued="2026-10-17T11:01:00Z", **kw):
    body = {"request_id": rid, "league_id": "lg-r1", "player_id": "p2", "type": "transfer",
            "from_squad_id": "sq-a", "to_squad_id": "sq-b", "effective_date": "2026-09-15", "loan_end_date": None,
            "reason": "offline", "requested_by": "manager"}
    body.update(kw)
    return {"action_id": aid, "type": "roster_transfer", "queued_at": queued, "base_version": base, "payload": body}


def test_sync_applied_rebased_rejected_and_order(fresh):
    _match(fresh)
    scenario(fresh)
    actions = [
        score_action("a2", "evt-b", 1, queued="2026-10-17T11:05:00Z"),   # processed second -> stale (rebased)
        score_action("a1", "evt-a", 2, queued="2026-10-17T11:00:00Z"),   # processed first, base == 2
        roster_action("a3", "rq-1", 0),
        roster_action("a4", "rq-2", 0, player_id="p1", from_squad_id="sq-a", to_squad_id="sq-b"),  # SQUAD_FULL
        score_action("a5", "evt-c", 99),                                  # base > current
    ]
    r = fresh.post("/audit/v1/offline-sync", json={"device_id": "dev-1", "actions": actions})
    assert r.status_code == 200
    res = {x["action_id"]: x for x in r.json()["results"]}
    assert [x["action_id"] for x in r.json()["results"]] == ["a2", "a1", "a3", "a4", "a5"]  # request order
    assert res["a1"]["processed_order"] == 1 and res["a1"]["resolution"] == "appended"
    assert res["a1"]["server_version"] == 3 and len(res["a1"]["signature"]) == 64
    assert res["a2"]["status"] == "applied" and res["a2"]["resolution"] == "rebased_append"
    assert res["a2"]["server_version"] == 4
    assert res["a3"]["status"] == "applied" and res["a3"]["server_version"] == 1 and res["a3"]["signature"] is None
    assert res["a4"]["status"] == "rejected" and res["a4"]["error_code"] == "SQUAD_FULL"
    assert res["a4"]["resolution"] == "server_wins"
    # a5 ties with a1 on queued_at, so array order puts it second (match version 3 at that point)
    assert res["a5"]["error_code"] == "INVALID_BASE_VERSION" and res["a5"]["server_version"] == 3
    assert res["a5"]["processed_order"] == 2
    assert r.json()["summary"] == {"applied": 3, "rejected": 2, "duplicate": 0}
    # resend: everything is a duplicate and nothing changes
    r2 = fresh.post("/audit/v1/offline-sync", json={"device_id": "dev-1", "actions": actions}).json()
    assert all(x["status"] == "duplicate" and x["resolution"] == "skipped_duplicate" for x in r2["results"])
    assert r2["summary"] == {"applied": 0, "rejected": 0, "duplicate": 5}
    assert fresh.get("/audit/v1/score/m1").json()["version"] == 4


def test_sync_same_event_from_other_device_is_duplicate(fresh):
    _match(fresh)
    fresh.post("/audit/v1/offline-sync", json={"device_id": "d1", "actions": [score_action("x", "evt-z", 2)]})
    r = fresh.post("/audit/v1/offline-sync", json={"device_id": "d2", "actions": [score_action("y", "evt-z", 2)]}).json()
    assert r["results"][0]["status"] == "duplicate"
    r = fresh.post("/audit/v1/offline-sync",
                   json={"device_id": "d3", "actions": [score_action("w", "evt-z", 3, team="t2")]}).json()
    assert r["results"][0]["error_code"] == "DUPLICATE_EVENT_ID"


def test_sync_unknown_ids_and_rule_errors(fresh):
    a = score_action("u1", "evt-q", 0)
    a["payload"]["match_id"] = "ghost"
    r = fresh.post("/audit/v1/offline-sync", json={"device_id": "d", "actions": [a, roster_action("u2", "rq", 0)]}).json()
    assert r["results"][0]["error_code"] == "MATCH_NOT_FOUND"
    assert r["results"][1]["error_code"] == "LEAGUE_NOT_FOUND"
    _match(fresh)
    fresh.post("/audit/v1/events", json={"event_id": "e", "match_id": "m1", "type": "match_end", "payload": {}})
    r = fresh.post("/audit/v1/offline-sync", json={"device_id": "d", "actions": [score_action("u3", "evt-r", 3)]}).json()
    assert r["results"][0]["error_code"] == "MATCH_NOT_IN_PROGRESS"


@pytest.mark.parametrize("body", [{"device_id": "d", "actions": []}, {"device_id": "d"},
                                  {"device_id": "d", "actions": [{"action_id": "a"}]}])
def test_sync_bad_envelope(fresh, body):
    r = fresh.post("/audit/v1/offline-sync", json=body)
    assert r.status_code == 400 and err(r) == "VALIDATION_ERROR"
