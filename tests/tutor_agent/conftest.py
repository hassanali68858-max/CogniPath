from datetime import date

import pytest

from agents.tutor_agent.catalog import TutorContext
from agents.tutor_agent.seed import load_catalog, load_student

TODAY = date(2026, 11, 2)


@pytest.fixture(scope="session")
def catalog():
    return load_catalog()


@pytest.fixture
def student():
    return load_student("student001")


@pytest.fixture
def context(catalog):
    return TutorContext(today=TODAY, horizon_days=14, catalog=catalog)
