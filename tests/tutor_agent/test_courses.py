from agents.tutor_agent.course_opportunity import recommend_courses
from shared.contracts import ActivityType


def _by_id(proposals):
    return {p.proposal_id: p for p in proposals}


def test_recommends_planned_mandatory_and_prerequisite_courses(student, context):
    proposals = _by_id(recommend_courses(student, context))
    assert set(proposals) == {
        "tut-register-cog2100",  # in the study plan
        "tut-register-cog2400",  # mandatory, not in the plan
        "tut-register-cog2200",  # needed before the planned COG2300
        "tut-register-cog2600",  # fills the electives gap
    }
    assert all(p.type == ActivityType.APPLICATION for p in proposals.values())
    assert "is needed before COG2300 Deep Learning" in proposals["tut-register-cog2200"].reason


def test_skips_ineligible_courses(student, context):
    ids = set(_by_id(recommend_courses(student, context)))
    assert "tut-register-cog2300" not in ids  # prerequisite COG2200 missing
    assert "tut-register-cog2500" not in ids  # taught in Finnish
    assert "tut-register-cog2700" not in ids  # registration closed
    assert "tut-register-cog1010" not in ids  # already enrolled


def test_finnish_speaker_also_gets_finnish_courses(student, context):
    bilingual = student.model_copy(update={"languages": ["en", "fi"]})
    assert "tut-register-cog2500" in _by_id(recommend_courses(bilingual, context))


def test_mandatory_course_keeps_full_value_without_matching_interest(student, context):
    research = _by_id(recommend_courses(student, context))["tut-register-cog2400"]
    assert research.value.study == 0.9


def test_optional_course_scores_lower_than_required_ones(student, context):
    proposals = _by_id(recommend_courses(student, context))
    assert proposals["tut-register-cog2600"].value.study == 0.6  # only fills the electives gap


def test_registration_window_ends_at_the_registration_deadline(student, context):
    kg = _by_id(recommend_courses(student, context))["tut-register-cog2100"]
    assert kg.window.earliest == context.today
    assert kg.window.deadline.isoformat() == "2026-11-20"
