"""Multi-objective planning: payoff table, ASF compromise, Pareto alternatives, NIMBUS steering."""

import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

from agents.planner_agent.api import create_app
from agents.planner_agent.io import load_proposals
from agents.planner_agent.planner import PlanningError, dominates, make_plans, nimbus
from shared.contracts import ItemDecision, PlannerProfile, Preference

from .conftest import DAYS, FIX, START


@pytest.fixture
def tight(profile):
    return profile.model_copy(update={"daily_cap_min": 120})


@pytest.fixture
def plans(proposals, tight):
    return make_plans(proposals, tight, START, DAYS)


def test_achieved_never_beats_ideal_and_never_drops_below_nadir_on_balanced(plans):
    bal = plans[0]
    assert bal.mode == "balanced"
    for k, v in bal.scores.achieved.items():
        assert bal.scores.nadir[k] - 1e-3 <= v <= bal.scores.ideal[k] + 1e-3


def test_alternatives_are_pareto_optimal_and_distinct(plans):
    assert len(plans) >= 2
    for a in plans:
        assert not any(dominates(b, a) for b in plans if b is not a)
    item_sets = [frozenset(i.proposal_id for i in p.items) for p in plans]
    assert len(set(item_sets)) == len(item_sets)


def test_alternatives_explain_their_trade_off(plans):
    bal, *others = plans
    assert bal.tradeoff is None
    for p in others:
        t = p.tradeoff
        assert t.compared_to == bal.plan_id
        assert any(d > 0 for d in t.deltas.values()) and any(d < 0 for d in t.deltas.values())
        assert "compared with Balanced" in t.summary
        assert t.gained or t.given_up


def test_no_priority_label_can_hide_a_valuable_item():
    """Two identical events except their value: the more valuable one wins, whatever any label said."""
    from .test_planner import _fixed

    a = _fixed("career-talk", 10, 12, {"career": 0.9})
    b = _fixed("study-group", 11, 13, {"study": 0.3})
    plan = make_plans([a, b], PlannerProfile(user_id="u"), date(2026, 11, 2), 1)[0]
    # the balanced compromise must pick one; the dropped one is still offered as an alternative
    shown = [
        {i.proposal_id for i in p.items} for p in make_plans([a, b], PlannerProfile(user_id="u"), date(2026, 11, 2), 1)
    ]
    assert {"career-talk"} in shown and {"study-group"} in shown
    assert plan.scores.achieved.keys() == {"study", "career"}


def test_nimbus_improves_career_by_letting_study_worsen(proposals, tight, plans):
    bal = plans[0]
    new = nimbus(bal, proposals, tight, Preference(classes={"career": "improve", "study": "worsen", "social": "keep"}))
    assert new.mode == "nimbus" and new.run_id == bal.run_id and new.based_on == bal.plan_id
    assert new.scores.achieved["career"] > bal.scores.achieved["career"]
    assert new.scores.achieved["social"] >= bal.scores.achieved["social"]
    assert new.message is None and new.label == "Your choice: more career"
    assert "Career +" in new.tradeoff.summary


def test_nimbus_says_so_when_the_rules_leave_no_better_plan(proposals, tight, plans):
    bal = plans[0]
    with pytest.raises(PlanningError, match="No plan gives more career"):
        nimbus(
            bal,
            proposals,
            tight,
            Preference(
                classes={"career": "improve", "study": "worsen", "social": "keep"},
                limits={"study": bal.scores.achieved["study"]},  # study may not actually drop
            ),
        )


def test_nimbus_says_so_when_a_goal_is_already_at_its_best(proposals, tight, plans):
    top = next(p for p in plans if p.mode == "lean_career")
    if top.scores.achieved["career"] < top.scores.ideal["career"] - 1e-3:
        pytest.skip("career-leaning plan is not at the career ideal for this data")
    with pytest.raises(PlanningError, match="already as high"):
        nimbus(top, proposals, tight, Preference(classes={"career": "improve", "study": "worsen"}))


def test_nimbus_needs_something_to_give(proposals, tight, plans):
    with pytest.raises(PlanningError, match="at least one other goal"):
        nimbus(plans[0], proposals, tight, Preference(classes={"career": "improve", "study": "keep", "social": "keep"}))
    with pytest.raises(PlanningError, match="at least one goal to improve"):
        nimbus(plans[0], proposals, tight, Preference(classes={"career": "worsen"}))


def test_nimbus_keeps_accepted_items(proposals, tight, plans):
    bal = plans[0]
    keep = bal.items[0]
    keep.decision = ItemDecision.ACCEPTED
    new = nimbus(bal, proposals, tight, Preference(classes={"career": "improve", "study": "worsen"}))
    same = next(i for i in new.items if i.proposal_id == keep.proposal_id)
    assert same.sessions == keep.sessions and same.decision == ItemDecision.ACCEPTED


def test_career_agent_batch_is_planned():
    """Elham's real Career Agent output (a ProposalBatch written by advisor.py) plans without changes."""
    batch = load_proposals(FIX / "career_batch_sample.json")
    assert batch and all(p.source_agent.value == "career" for p in batch)
    profile = PlannerProfile(user_id=batch[0].user_id)
    plans = make_plans(batch, profile, date(2026, 11, 5), 14)
    assert plans[0].solver_status == "OPTIMAL" and plans[0].items


@pytest.fixture
def client(store):
    with TestClient(create_app(store)) as c:
        yield c


def test_batch_nimbus_and_schedule_endpoints(client, proposals, tight):
    client.put(f"/profiles/{tight.user_id}", json=tight.model_dump(mode="json"))
    raw = json.loads((FIX / "career_batch_sample.json").read_text(encoding="utf-8"))
    r = client.post("/proposals/batch", json=raw)
    assert r.status_code == 201 and r.json() == {"stored": len(raw["proposals"]), "source_agent": "career"}
    client.post("/proposals", json=[p.model_dump(mode="json") for p in proposals])

    bal = client.post("/planner/runs", json={"user_id": tight.user_id, "horizon_start": START.isoformat()}).json()[0]
    r = client.post(
        f"/planner/plans/{bal['plan_id']}/nimbus",
        json={"classes": {"career": "improve", "study": "worsen", "social": "keep"}},
    )
    assert r.status_code == 200, r.text
    new = r.json()
    assert new["mode"] == "nimbus" and new["run_id"] == bal["run_id"]
    assert new["scores"]["achieved"]["career"] > bal["scores"]["achieved"]["career"]

    r = client.post(
        f"/planner/plans/{bal['plan_id']}/nimbus",
        json={"classes": {"career": "improve", "study": "keep", "social": "keep"}},
    )
    assert r.status_code == 422 and "worse" in r.json()["detail"]

    # accepting items on the NIMBUS plan discards the balanced one and fills planner.scheduled_activities
    first = new["items"][0]
    client.post(
        f"/planner/plans/{new['plan_id']}/decisions", json=[{"item_id": first["item_id"], "decision": "accepted"}]
    )
    assert client.get(f"/planner/plans/{bal['plan_id']}").json()["status"] == "discarded"
    sched = client.get(f"/planner/users/{tight.user_id}/schedule").json()
    assert [s["proposal_id"] for s in sched] == [first["proposal_id"]] * len(first["sessions"])


def test_batch_rejects_proposals_for_another_user(client):
    raw = json.loads((FIX / "career_batch_sample.json").read_text(encoding="utf-8"))
    raw["proposals"][0]["user_id"] = "someone-else"
    assert client.post("/proposals/batch", json=raw).status_code == 422


def test_users_are_registered_in_shared_users(store, profile):
    store.save_profile(profile)
    store.save_profile(profile)
    assert store.users().count(profile.user_id) == 1  # added once, never duplicated


def test_nimbus_limit_rounded_above_current_value_is_not_infeasible(proposals, tight, plans):
    """The UI shows whole percentages; a limit a hair above today's value must not forbid today's plan.

    The answer must be "no better plan" (a trade-off message), not "no feasible plan".
    """
    bal = plans[0]
    limit = round(bal.scores.achieved["career"] + 0.004, 2)
    with pytest.raises(PlanningError, match="No plan gives more study"):
        nimbus(
            bal,
            proposals,
            tight,
            Preference(classes={"study": "improve", "career": "worsen", "social": "keep"}, limits={"career": limit}),
        )
