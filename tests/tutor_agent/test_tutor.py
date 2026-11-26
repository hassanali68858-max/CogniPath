"""Checks from the CogniPath Shared Proposal Format checklist, plus a Planner run."""

from pathlib import Path

from agents.planner_agent.io import load_profile, load_proposals
from agents.planner_agent.planner import make_plan
from agents.tutor_agent import cli, propose, run
from shared.contracts import SourceAgent

PLANNER_PROFILE = Path(__file__).parents[1] / "planner_agent" / "fixtures" / "mock_profile.json"


def test_proposals_follow_the_contract(student, context):
    proposals = propose(student, context)
    ids = [p.proposal_id for p in proposals]
    assert len(ids) == len(set(ids))
    assert all(i.startswith("tut-") for i in ids)
    assert all(p.source_agent == SourceAgent.TUTOR and p.user_id == student.user_id for p in proposals)
    assert all(dep in ids for p in proposals for dep in p.depends_on)
    assert not any(p.hard for p in proposals)


def test_reason_is_one_plain_sentence(student, context):
    for p in propose(student, context):
        assert p.reason[0].isupper() and p.reason.endswith("."), p.reason
        assert ";" not in p.reason and p.reason.count(". ") == 0, p.reason


def test_only_required_course_registrations_score_as_directly_required(student, context):
    top = {p.proposal_id for p in propose(student, context) if p.value.study >= 0.9}
    assert top == {"tut-register-cog2100", "tut-register-cog2200", "tut-register-cog2400"}


def test_cli_output_loads_with_the_planner_loader(tmp_path):
    out = tmp_path / "tutor_proposals.json"
    cli.main(["propose", "--student", "student001", "--today", "2026-11-02", "--out", str(out)])
    assert {p.source_agent for p in load_proposals(out)} == {SourceAgent.TUTOR}


def test_run_also_returns_report_and_forums(student, context):
    output = run(student, context)
    assert output.progress.user_id == student.user_id
    assert output.forums


def test_planner_schedules_tutor_proposals_in_dependency_order(student, context):
    profile = load_profile(PLANNER_PROFILE)
    plan = make_plan(propose(student, context), profile, context.today, context.horizon_days)

    assert plan.solver_status in ("OPTIMAL", "FEASIBLE")
    start = {i.proposal_id: i.sessions[0].start for i in plan.items}
    end = {i.proposal_id: i.sessions[-1].end for i in plan.items}
    assert {"tut-review-sorting", "tut-quiz-sorting", "tut-quiz-rdf", "tut-review-sparql"} <= set(start)
    assert end["tut-review-sorting"] <= start["tut-quiz-sorting"]
    assert end["tut-quiz-rdf"] <= start["tut-review-sparql"]
