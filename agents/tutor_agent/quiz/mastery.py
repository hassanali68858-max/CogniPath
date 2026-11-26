"""Mastery per topic, estimated from the student's quiz history."""

from __future__ import annotations

from typing import Optional

from ..student import QuizAttempt

NEWEST_ATTEMPT_WEIGHT = 0.5  # exponential smoothing: recent quizzes count more
WEAK_MASTERY = 0.6


def topic_mastery(history: list[QuizAttempt], topic_id: str) -> Optional[float]:
    """0-1 mastery, or None if the student has never done a quiz on the topic."""
    attempts = sorted((a for a in history if a.topic_id == topic_id), key=lambda a: a.taken_on)
    if not attempts:
        return None
    mastery = attempts[0].score
    for attempt in attempts[1:]:
        mastery = NEWEST_ATTEMPT_WEIGHT * attempt.score + (1 - NEWEST_ATTEMPT_WEIGHT) * mastery
    return mastery
