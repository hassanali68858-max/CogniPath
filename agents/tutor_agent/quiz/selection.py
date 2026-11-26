"""Choose which topics of the student's current courses to quiz next."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Optional

from ..catalog import Course, Topic, TutorContext
from ..student import StudentProfile
from .mastery import WEAK_MASTERY, topic_mastery
from .models import MasteryLevel, TopicStatus
from .spacing import next_review

MAX_QUIZ_TOPICS = 5
# Refresh quizzes have their own limit, so they never push out the weak and untested topics.
MAX_REFRESH_TOPICS = 3


class TargetKind(str, Enum):
    WEAK = "weak"  # quizzed before, mastery below WEAK_MASTERY
    UNTESTED = "untested"  # never quizzed: a short diagnostic quiz
    REFRESH = "refresh"  # strong, and a spaced-repetition quiz is due within the horizon


@dataclass(frozen=True)
class QuizTarget:
    topic: Topic
    kind: TargetKind
    mastery: Optional[float]
    course: Optional[Course]
    exam_date: Optional[date]
    review_due: Optional[date] = None  # REFRESH only


def select_quiz_targets(profile: StudentProfile, context: TutorContext) -> list[QuizTarget]:
    """Weak topics first, then untested ones, then due refreshes; topics with an exam in the horizon go first."""
    exams = _current_course_exams(profile, context)
    targets = [
        target
        for topic in context.catalog.topics
        if topic.course_code in exams
        and (target := _target(topic, exams[topic.course_code], profile, context)) is not None
    ]
    learning = sorted(
        (t for t in targets if t.kind != TargetKind.REFRESH),
        key=lambda t: (not exam_in_horizon(t, context), t.kind != TargetKind.WEAK, t.mastery or 0.0, t.topic.id),
    )
    refresh = sorted(
        (t for t in targets if t.kind == TargetKind.REFRESH),
        key=lambda t: (not exam_in_horizon(t, context), t.review_due, t.topic.id),
    )
    return learning[:MAX_QUIZ_TOPICS] + refresh[:MAX_REFRESH_TOPICS]


def current_topics(profile: StudentProfile, context: TutorContext) -> list[TopicStatus]:
    """Every topic of the courses the student can still be quizzed on, in catalog order."""
    exams = _current_course_exams(profile, context)
    return [_topic_status(topic, profile) for topic in context.catalog.topics if topic.course_code in exams]


def exam_in_horizon(target: QuizTarget, context: TutorContext) -> bool:
    return target.exam_date is not None and context.today < target.exam_date <= context.horizon_end


def _current_course_exams(profile: StudentProfile, context: TutorContext) -> dict[str, Optional[date]]:
    """Enrolled course code -> exam date, without courses whose exam is today or has passed."""
    return {e.code: e.exam_date for e in profile.enrolled if e.exam_date is None or e.exam_date > context.today}


def _target(
    topic: Topic, exam_date: Optional[date], profile: StudentProfile, context: TutorContext
) -> Optional[QuizTarget]:
    """The topic as a quiz target, or None if it is strong and no refresh is due within the horizon."""
    mastery = topic_mastery(profile.quiz_history, topic.id)
    review_due = None
    if mastery is None:
        kind = TargetKind.UNTESTED
    elif mastery < WEAK_MASTERY:
        kind = TargetKind.WEAK
    else:
        review_due = next_review(profile.quiz_history, topic.id)
        if review_due is None or review_due > context.horizon_end:
            return None
        kind = TargetKind.REFRESH
    return QuizTarget(
        topic=topic,
        kind=kind,
        mastery=mastery,
        course=context.catalog.courses_by_code.get(topic.course_code),
        exam_date=exam_date,
        review_due=review_due,
    )


def _topic_status(topic: Topic, profile: StudentProfile) -> TopicStatus:
    mastery = topic_mastery(profile.quiz_history, topic.id)
    next_review_on = None
    if mastery is None:
        level = MasteryLevel.UNTESTED
    elif mastery < WEAK_MASTERY:
        level = MasteryLevel.WEAK
    else:
        level = MasteryLevel.STRONG
        next_review_on = next_review(profile.quiz_history, topic.id)
    return TopicStatus(
        topic_id=topic.id,
        name=topic.name,
        course_code=topic.course_code,
        mastery=mastery,
        level=level,
        next_review=next_review_on,
    )
