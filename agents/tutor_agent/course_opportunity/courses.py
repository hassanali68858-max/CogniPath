"""Next-period course recommendations, proposed as "register for course X" items."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from shared.contracts import ActivityProposal, ActivityType, ObjectiveValue, SourceAgent

from ..catalog import Catalog, Course, CourseOffering, TutorContext
from ..proposal_helpers import SINGLE_SESSION, window_until
from ..student import StudentProfile
from .models import ModuleProgress, UpcomingCourse
from .progress import module_progress, needed_courses
from .scoring import MIN_RECOMMENDATION_SCORE, interest_fit, interest_reason, join_clauses, study_value

DEGREE_WEIGHT = 0.6
INTEREST_WEIGHT = 0.4
VALUE_IN_PLAN = 0.9
VALUE_MANDATORY = 0.9
VALUE_PREREQUISITE = 0.8
VALUE_MODULE_GAP = 0.6
MAX_COURSE_RECOMMENDATIONS = 4
REGISTRATION_MIN = 30


@dataclass(frozen=True)
class _Candidate:
    course: Course
    offering: CourseOffering
    score: float
    reasons: list[str]


def recommend_courses(profile: StudentProfile, context: TutorContext) -> list[ActivityProposal]:
    catalog = context.catalog
    programme = catalog.programme(profile.programme_id)
    gaps = {m.module_id: m for m in module_progress(profile, programme, catalog) if m.missing_credits > 0}
    mandatory = {code: m.name for m in programme.modules for code in m.mandatory}
    needed_before = _needed_before(needed_courses(profile, programme), profile, catalog)
    taken = profile.completed_codes | profile.enrolled_codes

    candidates = []
    for course in catalog.courses:
        offering = _next_offering(course, context)
        if course.code in taken or offering is None or not _is_eligible(course, profile):
            continue
        degree, reasons = _degree_value(course, profile, mandatory, needed_before, gaps)
        fit, matched = interest_fit(course.tags, profile.interests)
        if matched:
            reasons.append(interest_reason(matched))
        # Interest can raise a course but not push a degree requirement below its own value.
        score = max(degree, DEGREE_WEIGHT * degree + INTEREST_WEIGHT * fit)
        if score >= MIN_RECOMMENDATION_SCORE:
            candidates.append(_Candidate(course, offering, score, reasons))

    candidates.sort(key=lambda c: (-c.score, c.course.code))
    return [_registration_proposal(c, profile, context) for c in candidates[:MAX_COURSE_RECOMMENDATIONS]]


def upcoming_courses(profile: StudentProfile, catalog: Catalog, today: date) -> list[UpcomingCourse]:
    """Courses not taken yet that start on or after ``today``, soonest first."""
    taken = profile.completed_codes | profile.enrolled_codes
    upcoming = []
    for course in catalog.courses:
        offering = min((o for o in course.offerings if o.start >= today), key=lambda o: o.start, default=None)
        if course.code in taken or offering is None:
            continue
        upcoming.append(
            UpcomingCourse(
                code=course.sisu_code or course.code,
                name=course.name,
                credits=course.credits,
                language=course.language,
                start=offering.start,
                end=offering.end,
                registration_deadline=offering.registration_deadline,
                from_sisu=course.sisu_code is not None,
            )
        )
    return sorted(upcoming, key=lambda c: (c.start, c.code))


def _needed_before(needed: set[str], profile: StudentProfile, catalog: Catalog) -> dict[str, list[str]]:
    """Missing prerequisite code -> labels of the needed courses that wait for it."""
    out: dict[str, list[str]] = {}
    for code in sorted(needed):
        course = catalog.courses_by_code.get(code)
        for prereq in course.prerequisites if course else []:
            if prereq not in profile.completed_codes:
                out.setdefault(prereq, []).append(course.label)
    return out


def _next_offering(course: Course, context: TutorContext) -> Optional[CourseOffering]:
    open_offerings = [
        o for o in course.offerings if context.today <= o.registration_deadline <= context.lookahead_end
    ]
    return min(open_offerings, key=lambda o: o.registration_deadline, default=None)


def _is_eligible(course: Course, profile: StudentProfile) -> bool:
    if course.language not in profile.languages:
        return False
    done_or_ongoing = profile.completed_codes | profile.enrolled_codes
    return set(course.prerequisites) <= done_or_ongoing


def _degree_value(
    course: Course,
    profile: StudentProfile,
    mandatory: dict[str, str],
    needed_before: dict[str, list[str]],
    gaps: dict[str, ModuleProgress],
) -> tuple[float, list[str]]:
    parts: list[tuple[float, str]] = []
    if course.code in profile.planned:
        parts.append((VALUE_IN_PLAN, "is in your study plan"))
    if course.code in mandatory:
        parts.append((VALUE_MANDATORY, f"is mandatory in {mandatory[course.code]}"))
    if course.code in needed_before:
        parts.append((VALUE_PREREQUISITE, "is needed before " + join_clauses(needed_before[course.code])))
    gap = gaps.get(course.module_id)
    if gap is not None:
        parts.append((VALUE_MODULE_GAP, f"counts toward {gap.name} ({gap.missing_credits:.0f} ECTS missing)"))
    return max((value for value, _ in parts), default=0.0), [reason for _, reason in parts]


def _registration_proposal(candidate: _Candidate, profile: StudentProfile, context: TutorContext) -> ActivityProposal:
    course, offering = candidate.course, candidate.offering
    deadline = offering.registration_deadline
    return ActivityProposal(
        proposal_id=f"tut-register-{course.code.lower()}",
        source_agent=SourceAgent.TUTOR,
        user_id=profile.user_id,
        type=ActivityType.APPLICATION,
        title=f"Register for {course.label} ({offering.period})",
        opportunity_ref=f"course:{course.code}:{offering.period}",
        duration_min=REGISTRATION_MIN,
        window=window_until(context.today, deadline),
        split=SINGLE_SESSION,
        value=ObjectiveValue(study=study_value(candidate.score)),
        reason=f"Register by {deadline:%d %b}: this course {join_clauses(candidate.reasons)}.",
    )
