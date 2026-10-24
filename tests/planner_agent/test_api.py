from fastapi.testclient import TestClient

from agents.planner_agent import api

from .conftest import START


def test_end_to_end_flow(proposals, profile):
    api.PROPOSALS.clear()
    api.PLANS.clear()
    client = TestClient(api.app)

    r = client.post("/proposals", json=[p.model_dump(mode="json") for p in proposals])
    assert r.status_code == 201 and r.json()["total"] == len(proposals)

    r = client.post(
        "/planner/runs",
        json={"profile": profile.model_dump(mode="json"), "horizon_start": START.isoformat(), "days": 14},
    )
    assert r.status_code == 200
    plans = r.json()
    assert [p["mode"] for p in plans] == ["balanced", "study_first", "career_first"]

    plan = plans[0]
    first = plan["items"][0]["item_id"]
    r = client.post(f"/planner/plans/{plan['plan_id']}/decisions", json=[{"item_id": first, "decision": "accepted"}])
    assert r.status_code == 200 and r.json()["status"] == "partial"

    r = client.get(f"/planner/plans/{plan['plan_id']}/ics")
    assert r.status_code == 200 and r.text.startswith("BEGIN:VCALENDAR")


def test_unknown_mode_rejected(profile):
    client = TestClient(api.app)
    r = client.post(
        "/planner/runs",
        json={"profile": profile.model_dump(mode="json"), "horizon_start": START.isoformat(), "modes": ["fun_first"]},
    )
    assert r.status_code == 422
