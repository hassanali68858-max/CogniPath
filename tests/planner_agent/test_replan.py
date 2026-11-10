from datetime import datetime, time, timedelta

import pytest
from fastapi.testclient import TestClient

from agents.planner_agent.api import create_app
from agents.planner_agent.planner import make_plan, replan
from shared.contracts import ActivityProposal, BusyBlock, ItemDecision, PlanStatus

from .conftest import DAYS, START

NEW_HACK_NIGHT = {
    "proposal_id": "evt-hack-night",
    "source_agent": "event",
    "user_id": "student001",
    "type": "event",
    "title": "Hack night",
    "fixed_time": {"start": "2026-11-12T17:00", "end": "2026-11-12T19:00"},
    "value": {"social": 0.6, "career": 0.6},
    "reason": "New event matching your interests",
}


def _base(proposals, profile):
    plan = make_plan(proposals, profile, START, DAYS)
    by_pid = {i.proposal_id: i for i in plan.items}
    by_pid["tut-report-draft"].decision = ItemDecision.ACCEPTED
    by_pid["evt-career-fair"].decision = ItemDecision.ACCEPTED
    by_pid["evt-climbing"].decision = ItemDecision.REJECTED
    return plan, by_pid


def test_accepted_items_keep_their_times(proposals, profile):
    base, by_pid = _base(proposals, profile)
    new = replan(base, proposals + [ActivityProposal(**NEW_HACK_NIGHT)], profile)[0]
    items = {i.proposal_id: i for i in new.items}

    for pid in ("tut-report-draft", "evt-career-fair"):
        assert items[pid].sessions == by_pid[pid].sessions
        assert items[pid].decision == ItemDecision.ACCEPTED
    assert new.based_on == base.plan_id and new.status == PlanStatus.PARTIAL
    assert new.changes.added == ["evt-hack-night"]
    assert "evt-climbing" in new.changes.removed  # rejected
    assert "evt-climbing" not in {d.proposal_id for d in new.dropped}


def test_withdrawn_accepted_item_is_reported(proposals, profile):
    base, _ = _base(proposals, profile)
    still_there = [p for p in proposals if p.proposal_id != "evt-career-fair"]
    new = replan(base, still_there, profile)[0]
    assert "evt-career-fair" not in {i.proposal_id for i in new.items}
    assert any("JYU Career Fair" in n and "withdrawn" in n for n in new.changes.notes)


def test_accepted_item_clashing_with_new_busy_block_is_planned_again(proposals, profile):
    base, by_pid = _base(proposals, profile)
    first = by_pid["tut-report-draft"].sessions[0]
    busy = profile.model_copy(
        update={"busy_blocks": profile.busy_blocks + [BusyBlock(title="Dentist", start=first.start, end=first.end)]}
    )
    new = replan(base, proposals, busy)[0]
    report = next(i for i in new.items if i.proposal_id == "tut-report-draft")
    assert report.decision == ItemDecision.PENDING
    assert all(not (s.start < first.end and first.start < s.end) for s in report.sessions)
    assert any("Dentist" in n for n in new.changes.notes)


def test_nothing_new_is_placed_in_the_past(proposals, profile):
    base, by_pid = _base(proposals, profile)
    now = datetime(2026, 11, 9, 12, 0)
    new = replan(base, proposals, profile, not_before=now)[0]
    for item in new.items:
        if item.decision == ItemDecision.ACCEPTED:
            continue
        assert all(s.start >= now for s in item.sessions), item.title
    dropped = {d.proposal_id: d.explanation for d in new.dropped}
    assert "evt-hackathon" in dropped and "past" in dropped["evt-hackathon"]


def test_replan_without_changes_says_so(proposals, profile):
    base = make_plan(proposals, profile, START, DAYS)
    for item in base.items:
        item.decision = ItemDecision.ACCEPTED
    new = replan(base, proposals, profile)[0]
    assert new.changes.summary == "No changes"
    assert new.changes.kept == len(base.items)


def _free_hour(plan, profile):
    """A one-hour slot with room under the daily limit and nothing else planned."""
    taken = [(s.start, s.end) for i in plan.items for s in i.sessions] + [(b.start, b.end) for b in profile.busy_blocks]
    for d in range(DAYS):
        day = START + timedelta(days=d)
        load = sum((e - s).total_seconds() / 60 for s, e in taken if s.date() == day)
        if load + 60 > profile.daily_cap_min:
            continue
        for hour in range(9, 19):
            a, b = datetime.combine(day, time(hour)), datetime.combine(day, time(hour + 1))
            if all(not (s < b and a < e) for s, e in taken):
                return a, b
    raise AssertionError("no free hour in the mock plan")


def test_replan_moves_only_what_it_must(proposals, profile):
    base = make_plan(proposals, profile, START, DAYS)  # nothing accepted yet
    assert replan(base, proposals, profile)[0].changes.summary == "No changes"

    a, b = _free_hour(base, profile)
    event = {**NEW_HACK_NIGHT, "fixed_time": {"start": a.isoformat(), "end": b.isoformat()}}
    new = replan(base, proposals + [ActivityProposal(**event)], profile)[0]
    assert new.changes.added == ["evt-hack-night"]
    assert new.changes.moved == []  # there was room, so nothing else had to move


# ---- API


@pytest.fixture
def client(store):
    with TestClient(create_app(store)) as c:
        yield c


def test_replan_endpoints(client, proposals, profile):
    client.put(f"/profiles/{profile.user_id}", json=profile.model_dump(mode="json"))
    client.post("/proposals", json=[p.model_dump(mode="json") for p in proposals])
    base = client.post(
        "/planner/runs", json={"user_id": "student001", "horizon_start": START.isoformat(), "modes": ["balanced"]}
    ).json()[0]
    fair = next(i for i in base["items"] if i["proposal_id"] == "evt-career-fair")
    client.post(
        f"/planner/plans/{base['plan_id']}/decisions", json=[{"item_id": fair["item_id"], "decision": "accepted"}]
    )

    # a new event arrives, then the user's current plan is re-planned
    client.post("/proposals", json=[NEW_HACK_NIGHT])
    r = client.post("/planner/users/student001/replan", json={"not_before": "2026-11-02T00:00"})
    assert r.status_code == 200, r.text
    new = r.json()[0]
    assert new["based_on"] == base["plan_id"]
    assert "evt-hack-night" in new["changes"]["added"]
    new_fair = next(i for i in new["items"] if i["proposal_id"] == "evt-career-fair")
    assert new_fair["sessions"] == fair["sessions"] and new_fair["decision"] == "accepted"

    assert client.get(f"/planner/plans/{base['plan_id']}").json()["status"] == "superseded"
    assert client.get("/planner/users/student001/current").json()["plan_id"] == new["plan_id"]
    assert client.post(f"/planner/plans/{base['plan_id']}/replan").status_code == 409

    # plan-level endpoint with an explicit mode, no body needed otherwise
    r = client.post(f"/planner/plans/{new['plan_id']}/replan", json={"modes": ["lean_study"]})
    assert r.status_code == 200 and r.json()[0]["mode"] == "lean_study"
