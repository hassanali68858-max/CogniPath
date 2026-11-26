from datetime import date

from agents.tutor_agent.course_opportunity import (
    ProgressStatus,
    WarningKind,
    advisor_proposal,
    build_progress_report,
)


def test_credits_per_module(student, context):
    report = build_progress_report(student, context)
    credits = {m.module_id: (m.completed_credits, m.required_credits) for m in report.modules}
    assert credits == {"core": (20, 40), "advanced": (5, 30), "electives": (10, 20), "thesis": (0, 30)}
    assert report.completed_credits == 35
    assert [c.code for c in report.current_courses] == ["COG1010", "TIES4570"]


def test_behind_pace_is_at_risk_and_proposes_an_advisor_meeting(student, context):
    report = build_progress_report(student, context)
    assert report.status == ProgressStatus.AT_RISK
    assert report.required_pace > 60
    assert any(w.kind == WarningKind.BEHIND_PACE for w in report.warnings)

    advisor = advisor_proposal(report, student, context)
    assert advisor is not None
    assert advisor.window.deadline == context.horizon_end


def test_enough_time_left_is_on_track(student, context):
    relaxed = student.model_copy(update={"target_graduation": date(2029, 6, 30)})
    report = build_progress_report(relaxed, context)
    assert report.status == ProgressStatus.ON_TRACK
    assert advisor_proposal(report, relaxed, context) is None


def test_warns_about_mandatory_courses_missing_from_the_plan(student, context):
    report = build_progress_report(student, context)
    missing = {w.course_code for w in report.warnings if w.kind == WarningKind.MISSING_MANDATORY}
    # TIES4570 and COG1010 are mandatory too, but the student takes them now.
    assert missing == {"COG2400", "COG9000"}


def test_warns_when_a_planned_course_lacks_its_prerequisite(student, context):
    report = build_progress_report(student, context)
    prereq = [w for w in report.warnings if w.kind == WarningKind.MISSING_PREREQUISITE]
    assert [w.course_code for w in prereq] == ["COG2300"]
    assert "COG2200 Machine Learning" in prereq[0].message
