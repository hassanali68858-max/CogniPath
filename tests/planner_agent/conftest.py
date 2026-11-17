import os
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


# Storage tests run on in-memory SQLite, and also on PostgreSQL when
# TEST_DATABASE_URL is set (CI sets it; locally see infra/README.md), e.g.
#   TEST_DATABASE_URL=postgresql+psycopg://cognipath:cognipath@localhost:5432/cognipath pytest
_DB_URLS = ["sqlite://"] + ([os.environ["TEST_DATABASE_URL"]] if os.environ.get("TEST_DATABASE_URL") else [])


@pytest.fixture(params=_DB_URLS, ids=lambda u: u.split(":")[0].split("+")[0])
def store(request):
    from agents.planner_agent.store import PlannerStore

    s = PlannerStore(request.param)
    s.drop_all()  # start every test from empty tables
    s = PlannerStore(request.param)
    yield s
    s.drop_all()
    s.engine.dispose()
