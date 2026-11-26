"""Turn quiz targets into Planner proposals: review (if weak) -> quiz; refresh quizzes stand alone."""

from __future__ import annotations

from datetime import date, timedelta

from shared.contracts import ActivityProposal, ActivityType, ObjectiveValue, SourceAgent, TimeWindow

from ..catalog import TutorContext
from ..proposal_helpers import SINGLE_SESSION, round_up_to_slot, window_until
from ..student import StudentProfile
from .selection import QuizTarget, TargetKind, exam_in_horizon

QUIZ_MIN = 30
DEFAULT_REVIEW_MIN = 60
# Shared rubric: practice on a weak topic is "clearly useful"; a first diagnostic quiz and a
# spaced refresh of a strong topic are "nice to have".
# An exam inside the horizon only moves the deadline (a constraint), not the value.
STUDY_VALUE = {TargetKind.WEAK: 0.6, TargetKind.UNTESTED: 0.3, TargetKind.REFRESH: 0.3}


def quiz_proposal_id(topic_id: str) -> str:
    return f"tut-quiz-{topic_id}"


def quiz_proposals(targets: list[QuizTarget], profile: StudentProfile, context: TutorContext) -> list[ActivityProposal]:
    # A known topic's refresh must not hold back practice on the topics that build on it.
    selected = {t.topic.id: t for t in targets if t.kind != TargetKind.REFRESH}
    proposals = []
    for target in targets:
        prereqs = [selected[p] for p in target.topic.prerequisites if p in selected]
        quiz_depends_on = [quiz_proposal_id(p.topic.id) for p in prereqs]
        if target.kind == TargetKind.WEAK:
            review = _review_proposal(target, quiz_depends_on, profile, context)
            proposals.append(review)
            quiz_depends_on = [review.proposal_id]
        proposals.append(_quiz_proposal(target, quiz_depends_on, prereqs, profile, context))
    return proposals


def _quiz_proposal(
    target: QuizTarget,
    depends_on: list[str],
    prereqs: list[QuizTarget],
    profile: StudentProfile,
    context: TutorContext,
) -> ActivityProposal:
    topic = target.topic
    window = _quiz_window(target, context)
    if target.kind == TargetKind.WEAK:
        reason = f"Your mastery of {topic.name} is {target.mastery:.0%}, so a short quiz shows what to practise"
    elif target.kind == TargetKind.REFRESH:
        due = "now" if window.earliest == context.today else f"from {window.earliest:%d %b}"
        reason = f"Your mastery of {topic.name} is {target.mastery:.0%} and a refresh quiz is due {due}, so you keep it"
    else:
        reason = f"You have not done a quiz on {topic.name} yet, so a short quiz shows where you stand"
    if exam_in_horizon(target, context):
        course = target.course.label if target.course else topic.course_code
        reason += f" before the {course} exam on {target.exam_date:%d %b}"
    if prereqs:
        reason += f", after the {' and '.join(p.topic.name for p in prereqs)} quiz that it builds on"
    return ActivityProposal(
        proposal_id=quiz_proposal_id(topic.id),
        source_agent=SourceAgent.TUTOR,
        user_id=profile.user_id,
        type=ActivityType.QUIZ,
        title=f"Quiz: {topic.name}",
        opportunity_ref=f"topic:{topic.id}",
        duration_min=QUIZ_MIN,
        window=window,
        split=SINGLE_SESSION,
        value=ObjectiveValue(study=STUDY_VALUE[target.kind]),
        depends_on=depends_on,
        reason=reason + ".",
    )


def _review_proposal(
    target: QuizTarget, depends_on: list[str], profile: StudentProfile, context: TutorContext
) -> ActivityProposal:
    topic = target.topic
    resource = topic.resources[0] if topic.resources else None
    return ActivityProposal(
        proposal_id=f"tut-review-{topic.id}",
        source_agent=SourceAgent.TUTOR,
        user_id=profile.user_id,
        type=ActivityType.LEARNING,
        title=f"Review {topic.name}: {resource.title}" if resource else f"Review your notes on {topic.name}",
        opportunity_ref=f"topic:{topic.id}",
        resource_url=resource.url if resource else None,
        duration_min=round_up_to_slot(resource.minutes) if resource else DEFAULT_REVIEW_MIN,
        window=window_until(context.today, _deadline(target, context)),
        value=ObjectiveValue(study=STUDY_VALUE[target.kind]),
        depends_on=depends_on,
        reason=f"Your mastery of {topic.name} is {target.mastery:.0%}, so review it before the quiz.",
    )


def _quiz_window(target: QuizTarget, context: TutorContext) -> TimeWindow:
    """A refresh quiz starts on its due day, but never after the deadline (for example an exam)."""
    window = window_until(context.today, _deadline(target, context))
    if target.review_due is None:
        return window
    earliest = min(max(target.review_due, window.earliest), window.deadline)
    return TimeWindow(earliest=earliest, deadline=window.deadline)


def _deadline(target: QuizTarget, context: TutorContext) -> date:
    if exam_in_horizon(target, context):
        assert target.exam_date is not None
        return target.exam_date - timedelta(days=1)
    return context.horizon_end
