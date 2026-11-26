"""Opportunities beyond Sisu: summer/winter schools, Erasmus exchanges and forums."""

from __future__ import annotations

from datetime import date

from shared.contracts import ActivityProposal, ActivityType, ObjectiveValue, SessionSplit, SourceAgent

from ..catalog import Catalog, Opportunity, OpportunityKind, TutorContext
from ..proposal_helpers import window_until
from ..student import StudentProfile
from .models import ForumLink
from .progress import module_progress, needed_courses
from .scoring import (
    MIN_RECOMMENDATION_SCORE,
    STRONG_MATCH,
    as_sentence,
    interest_fit,
    interest_reason,
    join_clauses,
)

INTEREST_WEIGHT = 0.5
DEGREE_WEIGHT = 0.5
VALUE_FILLS_MODULE = 0.8
VALUE_OTHER_CREDITS = 0.3
MAX_OPPORTUNITIES = 3
# Opportunities are optional, so never "directly required" (0.9) on the shared rubric.
STUDY_VALUE_STRONG_MATCH = 0.6
STUDY_VALUE_OTHER = 0.3
APPLICATION_MIN = {
    OpportunityKind.SUMMER_SCHOOL: 60,
    OpportunityKind.WINTER_SCHOOL: 60,
    OpportunityKind.ERASMUS: 120,
}
APPLICATION_SPLIT = SessionSplit(min_session_min=60, max_session_min=120)


def recommend_opportunities(profile: StudentProfile, context: TutorContext) -> list[ActivityProposal]:
    catalog = context.catalog
    programme = catalog.programme(profile.programme_id)
    gaps = {m.module_id: m for m in module_progress(profile, programme, catalog) if m.missing_credits > 0}
    needed = needed_courses(profile, programme)

    scored = []
    for opp in catalog.opportunities:
        if opp.kind == OpportunityKind.FORUM or not _is_feasible(opp, profile, context, needed):
            continue
        fit, matched = interest_fit(opp.tags, profile.interests)
        reasons = [interest_reason(matched)] if matched else []
        degree = 0.0
        if opp.credits and opp.credit_module_id in gaps:
            gap = gaps[opp.credit_module_id]
            degree = VALUE_FILLS_MODULE
            reasons.append(
                f"gives {opp.credits:.0f} ECTS that can count toward {gap.name} "
                f"({gap.missing_credits:.0f} ECTS missing)"
            )
        elif opp.credits:
            degree = VALUE_OTHER_CREDITS
            reasons.append(f"gives {opp.credits:.0f} ECTS")
        score = INTEREST_WEIGHT * fit + DEGREE_WEIGHT * degree
        if score >= MIN_RECOMMENDATION_SCORE:
            scored.append((score, opp, reasons))

    scored.sort(key=lambda s: (-s[0], s[1].application_deadline))
    return [
        _application_proposal(opp, score, reasons, profile, context)
        for score, opp, reasons in scored[:MAX_OPPORTUNITIES]
    ]


def match_forums(profile: StudentProfile, context: TutorContext) -> list[ForumLink]:
    courses = profile.enrolled_codes | set(profile.planned)
    links = []
    for opp in context.catalog.opportunities:
        if opp.kind != OpportunityKind.FORUM:
            continue
        _, matched = interest_fit(opp.tags, profile.interests)
        related = sorted(set(opp.related_courses) & courses)
        reasons = ([interest_reason(matched)] if matched else []) + (
            [f"discusses your course {join_clauses(related)}"] if related else []
        )
        if reasons:
            links.append(ForumLink(title=opp.title, url=opp.url, reason=as_sentence(reasons)))
    return links


def _is_feasible(opp: Opportunity, profile: StudentProfile, context: TutorContext, needed: set[str]) -> bool:
    assert opp.application_deadline is not None
    return (
        context.today <= opp.application_deadline <= context.lookahead_end
        and opp.language in profile.languages
        and profile.completed_credits >= opp.min_completed_credits
        and not (opp.kind == OpportunityKind.ERASMUS and _blocks_needed_course(opp, needed, context.catalog))
    )


def _blocks_needed_course(opp: Opportunity, needed: set[str], catalog: Catalog) -> bool:
    """True if a needed course is only offered while the student is away on exchange."""
    assert opp.start is not None and opp.end is not None
    for code in needed:
        course = catalog.courses_by_code.get(code)
        offerings = course.offerings if course else []
        if offerings and all(_overlaps(o.start, o.end, opp.start, opp.end) for o in offerings):
            return True
    return False


def _overlaps(a_start: date, a_end: date, b_start: date, b_end: date) -> bool:
    return a_start <= b_end and b_start <= a_end


def _application_proposal(
    opp: Opportunity, score: float, reasons: list[str], profile: StudentProfile, context: TutorContext
) -> ActivityProposal:
    assert opp.application_deadline is not None and opp.start is not None
    deadline = opp.application_deadline
    strong = score >= STRONG_MATCH
    return ActivityProposal(
        proposal_id=f"tut-apply-{opp.id}",
        source_agent=SourceAgent.TUTOR,
        user_id=profile.user_id,
        type=ActivityType.APPLICATION,
        title=f"Apply: {opp.title}",
        opportunity_ref=f"opportunity:{opp.id}",
        resource_url=opp.url,
        duration_min=APPLICATION_MIN[opp.kind],
        window=window_until(context.today, deadline),
        split=APPLICATION_SPLIT,
        value=ObjectiveValue(study=STUDY_VALUE_STRONG_MATCH if strong else STUDY_VALUE_OTHER),
        location=opp.location,
        reason=f"Apply by {deadline:%d %b}: it {join_clauses(reasons + [f'starts {opp.start:%d %b %Y}'])}.",
    )
