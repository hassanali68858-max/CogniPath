from agents.planner_agent.planner import make_plans
from agents.planner_agent.store import ProposalStatus
from shared.contracts import ItemDecision, PlanStatus

from .conftest import DAYS, START


def test_profile_round_trip(store, profile):
    assert store.get_profile(profile.user_id) is None
    store.save_profile(profile)
    assert store.get_profile(profile.user_id) == profile

    changed = profile.model_copy(update={"daily_cap_min": 120})
    store.save_profile(changed)
    assert store.get_profile(profile.user_id).daily_cap_min == 120


def test_proposals_upsert_and_status_rules(store, proposals):
    assert store.upsert_proposals(proposals) == len(proposals)
    assert len(store.list_proposals("student001")) == len(proposals)
    assert store.list_proposals("someone-else") == []

    store.set_proposal_status("student001", "evt-sauna", ProposalStatus.REJECTED)
    store.set_proposal_status("student001", "evt-climbing", ProposalStatus.WITHDRAWN)
    active = {p.proposal_id for p in store.list_proposals("student001")}
    assert "evt-sauna" not in active and "evt-climbing" not in active

    # agent sends both again: rejected stays rejected, withdrawn comes back
    again = [p for p in proposals if p.proposal_id in ("evt-sauna", "evt-climbing")]
    store.upsert_proposals(again)
    assert store.proposal_status("student001", "evt-sauna") == ProposalStatus.REJECTED
    assert store.proposal_status("student001", "evt-climbing") == ProposalStatus.ACTIVE


def test_upsert_updates_content(store, proposals):
    store.upsert_proposals(proposals)
    cv = next(p for p in proposals if p.proposal_id == "car-update-cv")
    store.upsert_proposals([cv.model_copy(update={"duration_min": 180})])
    stored = next(p for p in store.list_proposals("student001") if p.proposal_id == "car-update-cv")
    assert stored.duration_min == 180


def test_plans_round_trip_and_current_plan(store, proposals, profile):
    plans = make_plans(proposals, profile, START, DAYS)
    store.save_plans(plans)
    run_id = plans[0].run_id
    assert [p.mode for p in store.plans_in_run(run_id)] == sorted(p.mode for p in plans)
    assert store.get_plan(plans[1].plan_id) == plans[1]

    # nothing decided yet: current = a draft from the newest run
    assert store.current_plan(profile.user_id).status == PlanStatus.DRAFT

    chosen = plans[2]
    chosen.items[0].decision = ItemDecision.ACCEPTED
    chosen.status = PlanStatus.PARTIAL
    store.record_decisions(chosen, [(chosen.items[0].item_id, chosen.items[0].proposal_id, ItemDecision.ACCEPTED)])
    assert store.current_plan(profile.user_id).plan_id == chosen.plan_id
    assert store.decision_log(chosen.plan_id) == [(chosen.items[0].item_id, "accepted")]
