import pytest
from fastapi.testclient import TestClient

from agents.planner_agent.api import create_app

from .conftest import START


@pytest.fixture
def client(store):
    with TestClient(create_app(store)) as c:
        yield c


def _setup(client, proposals, profile):
    r = client.put(f"/profiles/{profile.user_id}", json=profile.model_dump(mode="json"))
    assert r.status_code == 200
    r = client.post("/proposals", json=[p.model_dump(mode="json") for p in proposals])
    assert r.status_code == 201 and r.json()["stored"] == len(proposals)


def _run(client, user_id="student001", **extra):
    r = client.post("/planner/runs", json={"user_id": user_id, "horizon_start": START.isoformat(), **extra})
    assert r.status_code == 200, r.text
    return r.json()


def test_end_to_end_flow(client, proposals, profile):
    _setup(client, proposals, profile)
    plans = _run(client)
    assert [p["mode"] for p in plans] == ["balanced", "study_first", "career_first"]
    assert len({p["run_id"] for p in plans}) == 1

    plan = plans[0]
    first = plan["items"][0]["item_id"]
    r = client.post(f"/planner/plans/{plan['plan_id']}/decisions", json=[{"item_id": first, "decision": "accepted"}])
    assert r.status_code == 200 and r.json()["status"] == "partial"

    # the other alternatives of the run are now discarded
    run = client.get(f"/planner/runs/{plan['run_id']}").json()
    assert {p["plan_id"]: p["status"] for p in run}[plans[1]["plan_id"]] == "discarded"
    r = client.post(f"/planner/plans/{plans[1]['plan_id']}/decisions", json=[])
    assert r.status_code == 409

    assert client.get("/planner/users/student001/current").json()["plan_id"] == plan["plan_id"]
    r = client.get(f"/planner/plans/{plan['plan_id']}/ics")
    assert r.status_code == 200 and r.text.startswith("BEGIN:VCALENDAR")


def test_rejected_items_are_not_planned_again(client, proposals, profile):
    _setup(client, proposals, profile)
    plan = _run(client, modes=["balanced"])[0]
    item = next(i for i in plan["items"] if i["proposal_id"] == "evt-climbing")
    client.post(
        f"/planner/plans/{plan['plan_id']}/decisions", json=[{"item_id": item["item_id"], "decision": "rejected"}]
    )

    rejected = client.get("/proposals", params={"user_id": "student001", "status": "rejected"}).json()
    assert [p["proposal_id"] for p in rejected] == ["evt-climbing"]
    again = _run(client, modes=["balanced"])[0]
    planned = {i["proposal_id"] for i in again["items"]} | {d["proposal_id"] for d in again["dropped"]}
    assert "evt-climbing" not in planned


def test_withdrawn_proposal_disappears(client, proposals, profile):
    _setup(client, proposals, profile)
    r = client.post("/proposals/student001/evt-ai-meetup/withdraw")
    assert r.status_code == 200
    plan = _run(client, modes=["balanced"])[0]
    assert "evt-ai-meetup" not in {i["proposal_id"] for i in plan["items"]}
    assert client.post("/proposals/student001/nope/withdraw").status_code == 404


def test_run_needs_a_profile(client):
    r = client.post("/planner/runs", json={"user_id": "ghost", "horizon_start": START.isoformat()})
    assert r.status_code == 404
    r = client.post("/planner/runs", json={"horizon_start": START.isoformat()})
    assert r.status_code == 422


def test_run_with_inline_profile_saves_it(client, profile):
    r = client.post(
        "/planner/runs", json={"profile": profile.model_dump(mode="json"), "horizon_start": START.isoformat()}
    )
    assert r.status_code == 200
    assert client.get(f"/profiles/{profile.user_id}").json()["user_id"] == profile.user_id


def test_unknown_mode_rejected(client, profile):
    r = client.post(
        "/planner/runs",
        json={"profile": profile.model_dump(mode="json"), "horizon_start": START.isoformat(), "modes": ["fun_first"]},
    )
    assert r.status_code == 422
