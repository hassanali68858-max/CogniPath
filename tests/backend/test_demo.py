import pytest
from fastapi.testclient import TestClient

from agents.planner_agent.store import PlannerStore
from backend.main import build_app


@pytest.fixture
def client():
    app = build_app()
    app.state.store = PlannerStore("sqlite://")
    with TestClient(app) as c:
        yield c


def test_seed_plan_and_reset(client):
    info = client.get("/demo/info").json()
    r = client.post("/demo/seed")
    assert r.status_code == 200 and r.json()["proposals"] == 20

    r = client.post(
        "/planner/runs",
        json={"user_id": info["user_id"], "horizon_start": info["horizon_start"], "modes": ["balanced"]},
    )
    assert r.status_code == 200 and r.json()[0]["items"]

    assert client.post(f"/demo/reset/{info['user_id']}").status_code == 200
    assert client.get(f"/profiles/{info['user_id']}").status_code == 404
    assert client.get("/proposals", params={"user_id": info["user_id"]}).json() == []


def test_cors_allows_the_frontend(client):
    r = client.options("/health", headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"
