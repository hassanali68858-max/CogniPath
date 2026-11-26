"""Taking a quiz: build it, grade the answers, store the result in the quiz history."""

from __future__ import annotations

from datetime import date

from ..catalog import Catalog, Fact
from ..student import QuizAttempt, StudentProfile
from .generator import MAX_OPTIONS, QuestionGenerator
from .models import Quiz

DEFAULT_QUESTION_COUNT = 5


def build_quiz(
    topic_id: str, catalog: Catalog, generator: QuestionGenerator, count: int = DEFAULT_QUESTION_COUNT
) -> Quiz:
    topic = catalog.topics_by_id.get(topic_id)
    if topic is None:
        raise KeyError(f"unknown topic {topic_id!r}")
    questions = generator.generate(topic, _distractors(topic_id, catalog), count)
    if not questions:
        raise ValueError(f"not enough facts to build a quiz on {topic_id!r}")
    return Quiz(topic_id=topic_id, questions=questions)


def grade_quiz(quiz: Quiz, answers: list[int], taken_on: date) -> QuizAttempt:
    if len(answers) != len(quiz.questions):
        raise ValueError(f"expected {len(quiz.questions)} answers, got {len(answers)}")
    correct = sum(a == q.answer_index for q, a in zip(quiz.questions, answers))
    return QuizAttempt(topic_id=quiz.topic_id, correct=correct, total=len(quiz.questions), taken_on=taken_on)


def record_attempt(profile: StudentProfile, attempt: QuizAttempt) -> StudentProfile:
    return profile.model_copy(update={"quiz_history": [*profile.quiz_history, attempt]})


def _distractors(topic_id: str, catalog: Catalog) -> list[Fact]:
    """Facts of the same course's other topics; other courses only if those are too few."""
    topic = catalog.topics_by_id[topic_id]
    others = [t for t in catalog.topics if t.id != topic_id]
    same_course = [f for t in others if t.course_code == topic.course_code for f in t.facts]
    if len(same_course) >= MAX_OPTIONS - 1:
        return same_course
    return same_course + [f for t in others if t.course_code != topic.course_code for f in t.facts]
