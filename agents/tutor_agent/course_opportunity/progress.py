"""Degree progress: credits per module, graduation pace and study-plan warnings."""

from __future__ import annotations

from datetime import date
from typing import Optional

from shared.contracts import ActivityProposal, ActivityType, ObjectiveValue, SourceAgent

from ..catalog import Catalog, DegreeProgramme, TutorContext
from ..proposal_helpers import SINGLE_SESSION, window_until
from ..student import StudentProfile
from .models import (
    CurrentCourse,
    ModuleProgress,
    ProgressReport,
    ProgressStatus,
    ProgressWarning,
    WarningKind,
)

FULL_TIME_CREDITS_PER_YEAR = 60.0  # Finnish full-time study norm: 60 ECTS per academic year
DAYS_PER_YEAR = 365.25
ADVISOR_MEETING_MIN = 30


def build_progress_report(profile: StudentProfile, context: TutorContext) -> ProgressReport:
    catalog = context.catalog
    programme = catalog.programme(profile.programme_id)
    pace = required_pace(profile, programme, context.today)
    status = ProgressStatus.AT_RISK if pace > FULL_TIME_CREDITS_PER_YEAR else ProgressStatus.ON_TRACK

    warnings = _missing_mandatory(profile, programme, catalog) + _missing_prerequisites(profile, catalog)
    if status == ProgressStatus.AT_RISK:
        warnings.append(
            ProgressWarning(
                kind=WarningKind.BEHIND_PACE,
                message=(
                    f"You need {pace:.0f} ECTS per year to graduate by {profile.target_graduation:%b %Y}, "
                    f"but full-time study is {FULL_TIME_CREDITS_PER_YEAR:.0f} ECTS per year."
                ),
            )
        )

    return ProgressReport(
        user_id=profile.user_id,
        programme_name=programme.name,
        completed_credits=profile.completed_credits,
        required_credits=programme.total_credits,
        required_pace=round(pace, 1),
        status=status,
        modules=module_progress(profile, programme, catalog),
        current_courses=_current_courses(profile, catalog),
        warnings=warnings,
    )


def advisor_proposal(
    report: ProgressReport, profile: StudentProfile, context: TutorContext
) -> Optional[ActivityProposal]:
    if report.status != ProgressStatus.AT_RISK:
        return None
    pace_warning = next(w for w in report.warnings if w.kind == WarningKind.BEHIND_PACE)
    return ActivityProposal(
        proposal_id="tut-advisor-meeting",
        source_agent=SourceAgent.TUTOR,
        user_id=profile.user_id,
        type=ActivityType.OTHER,
        title="Book a meeting with your study advisor",
        duration_min=ADVISOR_MEETING_MIN,
        window=window_until(context.today, context.horizon_end),
        split=SINGLE_SESSION,
        value=ObjectiveValue(study=0.6),
        reason=pace_warning.message,
    )


def module_progress(profile: StudentProfile, programme: DegreeProgramme, catalog: Catalog) -> list[ModuleProgress]:
    done: dict[str, float] = {}
    for attainment in profile.completed:
        course = catalog.courses_by_code.get(attainment.code)
        if course is not None:
            done[course.module_id] = done.get(course.module_id, 0.0) + attainment.credits
    return [
        ModuleProgress(
            module_id=m.id,
            name=m.name,
            completed_credits=done.get(m.id, 0.0),
            required_credits=m.min_credits,
        )
        for m in programme.modules
    ]


def needed_courses(profile: StudentProfile, programme: DegreeProgramme) -> set[str]:
    """Planned or mandatory courses that the student has not completed or started."""
    mandatory = {code for m in programme.modules for code in m.mandatory}
    return (set(profile.planned) | mandatory) - profile.completed_codes - profile.enrolled_codes


def required_pace(profile: StudentProfile, programme: DegreeProgramme, today: date) -> float:
    remaining = max(0.0, programme.total_credits - profile.completed_credits)
    if remaining == 0:
        return 0.0
    days_left = max(1, (profile.target_graduation - today).days)
    return remaining / (days_left / DAYS_PER_YEAR)


def _missing_mandatory(profile: StudentProfile, programme: DegreeProgramme, catalog: Catalog) -> list[ProgressWarning]:
    in_plan = profile.completed_codes | profile.enrolled_codes | set(profile.planned)
    warnings = []
    for module in programme.modules:
        for code in module.mandatory:
            if code in in_plan:
                continue
            course = catalog.courses_by_code.get(code)
            warnings.append(
                ProgressWarning(
                    kind=WarningKind.MISSING_MANDATORY,
                    course_code=code,
                    message=f"{course.label if course else code} is mandatory in {module.name} "
                    "but is not in your study plan.",
                )
            )
    return warnings


def _missing_prerequisites(profile: StudentProfile, catalog: Catalog) -> list[ProgressWarning]:
    warnings = []
    taking = [(code, profile.completed_codes) for code in sorted(profile.enrolled_codes)]
    # A planned course may rely on a course that the student takes now.
    taking += [(code, profile.completed_codes | profile.enrolled_codes) for code in profile.planned]
    for code, satisfied in taking:
        course = catalog.courses_by_code.get(code)
        if course is None:
            continue
        for prereq_code in course.prerequisites:
            if prereq_code in satisfied:
                continue
            prereq = catalog.courses_by_code[prereq_code]
            warnings.append(
                ProgressWarning(
                    kind=WarningKind.MISSING_PREREQUISITE,
                    course_code=code,
                    message=f"{course.label} needs {prereq.label} first, which you have not completed.",
                )
            )
    return warnings


def _current_courses(profile: StudentProfile, catalog: Catalog) -> list[CurrentCourse]:
    current = []
    for enrollment in profile.enrolled:
        course = catalog.courses_by_code.get(enrollment.code)
        current.append(
            CurrentCourse(
                code=enrollment.code,
                name=course.name if course else enrollment.code,
                credits=course.credits if course else 0.0,
                exam_date=enrollment.exam_date,
            )
        )
    return current
