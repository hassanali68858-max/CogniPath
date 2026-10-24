import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from shared.contracts import ActivityProposal

SCHEMA = Path(__file__).resolve().parents[2] / "shared" / "contracts" / "activity_proposal.schema.json"

BASE = {
    "proposal_id": "t-1",
    "source_agent": "tutor",
    "user_id": "student001",
    "type": "learning",
    "title": "Read chapter 1",
    "value": {"study": 0.6},
    "reason": "Course prerequisite",
}


def test_fixtures_are_valid(proposals):
    assert len(proposals) == 20
    assert {p.source_agent.value for p in proposals} == {"event", "tutor", "career"}


def test_flexible_needs_duration_and_window():
    with pytest.raises(ValidationError, match="duration_min and window"):
        ActivityProposal(**BASE, duration_min=60)


def test_fixed_must_not_have_duration():
    with pytest.raises(ValidationError, match="must not set duration_min"):
        ActivityProposal(
            **BASE,
            fixed_time={"start": "2026-11-02T10:00", "end": "2026-11-02T11:00"},
            duration_min=60,
        )


def test_fixed_time_order():
    with pytest.raises(ValidationError, match="after"):
        ActivityProposal(**BASE, fixed_time={"start": "2026-11-02T11:00", "end": "2026-11-02T10:00"})


def test_values_are_bounded():
    bad = {**BASE, "value": {"study": 1.5}}
    with pytest.raises(ValidationError):
        ActivityProposal(**bad, duration_min=60, window={"earliest": "2026-11-02", "deadline": "2026-11-03"})


def test_unknown_fields_rejected():
    with pytest.raises(ValidationError):
        ActivityProposal(
            **BASE, duration_min=60, window={"earliest": "2026-11-02", "deadline": "2026-11-03"}, colour="red"
        )


def test_self_dependency_rejected():
    with pytest.raises(ValidationError, match="itself"):
        ActivityProposal(
            **BASE,
            duration_min=60,
            window={"earliest": "2026-11-02", "deadline": "2026-11-03"},
            depends_on=["t-1"],
        )


def test_committed_json_schema_is_up_to_date():
    """Other agents (any language) validate against the JSON Schema file.

    Regenerate with:  python -m shared.contracts.export_schema
    """
    assert json.loads(SCHEMA.read_text()) == ActivityProposal.model_json_schema()
