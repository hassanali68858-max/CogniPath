"""Spaced repetition: when a topic the student knows is due for a refresh quiz."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from ..student import QuizAttempt
from .mastery import WEAK_MASTERY

# Days until the next refresh after 1, 2, 3, ... passed quizzes in a row; the last gap repeats.
REVIEW_INTERVALS_DAYS = (1, 3, 7, 14, 30)


def next_review(history: list[QuizAttempt], topic_id: str) -> Optional[date]:
    """The day a refresh quiz on the topic is due, or None if it was never quizzed."""
    attempts = sorted((a for a in history if a.topic_id == topic_id), key=lambda a: a.taken_on)
    if not attempts:
        return None
    step = min(max(_passed_in_a_row(attempts), 1), len(REVIEW_INTERVALS_DAYS))
    return attempts[-1].taken_on + timedelta(days=REVIEW_INTERVALS_DAYS[step - 1])


def _passed_in_a_row(attempts: list[QuizAttempt]) -> int:
    streak = 0
    for attempt in reversed(attempts):
        if attempt.score < WEAK_MASTERY:
            break
        streak += 1
    return streak
