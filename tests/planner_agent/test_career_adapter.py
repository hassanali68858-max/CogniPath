import json
from datetime import date

import pytest

from agents.planner_agent.adapters.career import from_career_output
from shared.contracts import SourceAgent

from .conftest import FIX

TODAY = date(2026, 11, 2)


def sample():
    return json.loads((FIX / "career_plan_sample.json").read_text())


def test_converts_elhams_prototype_output():
    [p] = from_career_output(sample(), today=TODAY, user_id="student001")
    assert p.source_agent == SourceAgent.CAREER
    assert p.user_id == "student001"
    assert p.title == "Learn Docker"
    assert p.opportunity_ref == "AIInternship001"
    assert p.duration_min == 180
    assert str(p.resource_url) == "https://docs.docker.com/get-started/"
    assert p.window.earliest == TODAY
    assert p.window.deadline == date(2026, 11, 15)  # default: end of a 14-day horizon
    assert p.value.career > p.value.study
    assert "Docker" in p.reason and "AIInternship001" in p.reason


def test_uses_optional_fields_when_present():
    data = sample()
    data["activities"][0].update(
        deadline="2026-11-06", priority="high", value={"career": 1.0}, estimated_duration_minutes=100
    )
    [p] = from_career_output(data, today=TODAY)
    assert p.window.deadline == date(2026, 11, 6)
    assert p.priority.value == "high"
    assert p.value.career == 1.0
    assert p.duration_min == 120  # rounded up to the 30-min grid
    assert p.user_id == "ElhamPournouri"  # falls back to the document's student


def test_duplicate_activities_get_unique_ids():
    data = sample()
    data["activities"] *= 2
    ids = [p.proposal_id for p in from_career_output(data, today=TODAY)]
    assert len(set(ids)) == 2


def test_rejects_other_agents_documents():
    with pytest.raises(ValueError):
        from_career_output({"agent": "EventAgent", "activities": []}, today=TODAY)
