from datetime import date
from pathlib import Path

import pytest

from agents.planner_agent.io import load_career_output, load_profile, load_proposals

FIX = Path(__file__).parent / "fixtures"
START = date(2026, 11, 2)
DAYS = 14


@pytest.fixture
def profile():
    return load_profile(FIX / "mock_profile.json")


@pytest.fixture
def proposals(profile):
    props = load_proposals(FIX / "mock_proposals.json")
    props += load_career_output(
        FIX / "career_plan_sample.json", today=START, horizon_days=DAYS, user_id=profile.user_id
    )
    return props
