from datetime import date

import pytest

from agents.tutor_agent.course_opportunity import match_forums, recommend_opportunities
from agents.tutor_agent.course_opportunity import opportunities as opportunities_module
from agents.tutor_agent.student import CourseAttainment


@pytest.fixture
def no_limit(monkeypatch):
    monkeypatch.setattr(opportunities_module, "MAX_OPPORTUNITIES", 100)


def _ids(proposals):
    return {p.proposal_id for p in proposals}


def test_recommends_matching_schools_and_exchange(student, context):
    proposals = recommend_opportunities(student, context)
    assert _ids(proposals) == {
        "tut-apply-ml-winter-2027",
        "tut-apply-kg-summer-2027",
        "tut-apply-erasmus-autumn-2027-b",
    }
    summer = next(p for p in proposals if p.proposal_id == "tut-apply-kg-summer-2027")
    assert "matches your interest in AI and knowledge graphs" in summer.reason
    assert summer.window.deadline == date(2026, 12, 1)


def test_opportunities_are_never_scored_as_required(student, context, no_limit):
    assert all(p.value.study <= 0.6 for p in recommend_opportunities(student, context))


def test_filters_language_deadline_and_credit_requirements(student, context, no_limit):
    ids = _ids(recommend_opportunities(student, context))
    assert "tut-apply-arch-winter-fi-2027" not in ids  # Finnish only
    assert "tut-apply-ds-summer-closed" not in ids  # deadline passed
    assert "tut-apply-erasmus-autumn-2027-c" not in ids  # needs 60 completed ECTS


def test_exchange_that_blocks_a_needed_course_is_skipped(student, context, no_limit):
    assert "tut-apply-erasmus-spring-2027-a" not in _ids(recommend_opportunities(student, context))

    # Once COG2400 is done and nothing is planned for spring, the exchange fits.
    research_done = CourseAttainment(code="COG2400", credits=5, completed_on=date(2026, 3, 1))
    free_spring = student.model_copy(update={"planned": [], "completed": [*student.completed, research_done]})
    assert "tut-apply-erasmus-spring-2027-a" in _ids(recommend_opportunities(free_spring, context))


def test_forums_are_links_not_proposals(student, context):
    titles = {f.title for f in match_forums(student, context)}
    assert titles == {"AI student community (demo)", "Algorithms course Q&A board (demo)"}
    assert not any("forum" in p.proposal_id for p in recommend_opportunities(student, context))
