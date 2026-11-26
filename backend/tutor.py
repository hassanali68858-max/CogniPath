"""Tutor Agent routes: run the agent for a student, take quizzes, and hand proposals to the Planner.

Students come from the seed files. Course data comes from the seed files or, with
``TUTOR_CATALOG_SOURCE=sisu``, live from JYU Sisu (see ``agents/tutor_agent/sisu.py``).
Open quizzes (``OpenQuizzes``) and quiz attempts taken in the app (``QuizHistory``)
are kept in memory, so they are lost when the backend restarts.
"""

from __future__ import annotations

import os
import random
import uuid
from collections import OrderedDict, defaultdict
from datetime import date
from functools import lru_cache
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from agents.planner_agent.api import Store
from agents.planner_agent.store import PlannerStore, ProposalStatus
from agents.tutor_agent import TutorContext, TutorOutput, run
from agents.tutor_agent.catalog import Catalog
from agents.tutor_agent.course_opportunity import UpcomingCourse, upcoming_courses
from agents.tutor_agent.quiz import (
    QuestionGenerator,
    Quiz,
    build_quiz,
    generator_from_env,
    grade_quiz,
    topic_mastery,
)
from agents.tutor_agent.seed import load_student
from agents.tutor_agent.sisu import CatalogSource, catalog_from_env
from agents.tutor_agent.student import QuizAttempt, StudentProfile
from shared.contracts import SourceAgent

MAX_QUESTIONS = 10
MAX_OPEN_QUIZZES_PER_STUDENT = 20

router = APIRouter(prefix="/tutor", tags=["tutor"])

Today = Query(None, description="Planning start day; default: today")
Days = Query(14, ge=1, le=28, description="Planner horizon in days")


class QuizHistory:
    """Quiz attempts per student, taken in the app; added to the seed quiz history."""

    def __init__(self) -> None:
        self._attempts: dict[str, list[QuizAttempt]] = defaultdict(list)

    def add(self, user_id: str, attempt: QuizAttempt) -> None:
        self._attempts[user_id].append(attempt)

    def for_user(self, user_id: str) -> list[QuizAttempt]:
        return list(self._attempts.get(user_id, []))


_HISTORY = QuizHistory()


def quiz_history() -> QuizHistory:
    return _HISTORY


History = Annotated[QuizHistory, Depends(quiz_history)]


class OpenQuizzes:
    """Quizzes handed out but not graded yet. The answers stay here, never in the response.

    A generated quiz (for example by an LLM) cannot be rebuilt, so it is kept until the
    student submits it once. Each student keeps at most ``MAX_OPEN_QUIZZES_PER_STUDENT``.
    """

    def __init__(self) -> None:
        self._quizzes: dict[str, OrderedDict[str, Quiz]] = defaultdict(OrderedDict)

    def add(self, user_id: str, quiz: Quiz) -> str:
        quiz_id = uuid.uuid4().hex
        open_quizzes = self._quizzes[user_id]
        open_quizzes[quiz_id] = quiz
        while len(open_quizzes) > MAX_OPEN_QUIZZES_PER_STUDENT:
            open_quizzes.popitem(last=False)
        return quiz_id

    def take(self, user_id: str, quiz_id: str) -> Optional[Quiz]:
        return self._quizzes[user_id].pop(quiz_id, None)


_OPEN_QUIZZES = OpenQuizzes()


def open_quizzes() -> OpenQuizzes:
    return _OPEN_QUIZZES


@lru_cache(maxsize=1)
def question_generator() -> QuestionGenerator:
    return generator_from_env(os.environ, random.Random())


Open = Annotated[OpenQuizzes, Depends(open_quizzes)]
Generator = Annotated[QuestionGenerator, Depends(question_generator)]


class QuizRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic_id: str = Field(..., min_length=1, max_length=100)
    questions: int = Field(5, ge=1, le=MAX_QUESTIONS)


class QuestionView(BaseModel):
    prompt: str
    options: list[str]


class QuizView(BaseModel):
    """A quiz without its answers."""

    quiz_id: str
    topic_id: str
    topic_name: str
    questions: list[QuestionView]


class QuizAnswers(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answers: list[Annotated[int, Field(ge=0)]] = Field(..., min_length=1, max_length=MAX_QUESTIONS)


class QuizResult(BaseModel):
    topic_id: str
    correct: int
    total: int
    answer_indexes: list[int]
    mastery_before: Optional[float]
    mastery_after: float


class CatalogInfo(BaseModel):
    source: str
    url: Optional[str]
    linked: dict[str, str]
    unavailable: list[str]


@router.get("/catalog/source")
def catalog_source() -> CatalogInfo:
    """Where the course data comes from, and which seed courses Sisu replaced."""
    source = _catalog_source()
    return CatalogInfo(source=source.source, url=source.url, linked=source.linked, unavailable=source.unavailable)


@router.get("/{user_id}/courses")
def courses(user_id: str, history: History, today: Optional[date] = Today) -> list[UpcomingCourse]:
    """The next offering of each course the student has not taken yet, soonest first."""
    return upcoming_courses(_student(user_id, history), _catalog(), today or date.today())


@router.get("/{user_id}/report")
def report(user_id: str, history: History, today: Optional[date] = Today, days: int = Days) -> TutorOutput:
    """Progress report, topic mastery, forum links and proposals for the frontend. Stores nothing."""
    return run(_student(user_id, history), _context(today, days))


@router.post("/{user_id}/proposals", status_code=201)
def send_proposals(
    user_id: str, store: Store, history: History, today: Optional[date] = Today, days: int = Days
) -> dict:
    """Store the Tutor Agent's proposals for the Planner.

    Active Tutor proposals that the agent no longer makes (for example a quiz on a
    topic that is now strong) are withdrawn, so the Planner does not keep planning them.
    """
    proposals = run(_student(user_id, history), _context(today, days)).proposals
    stored = store.upsert_proposals(proposals)
    withdrawn = withdraw_stale_tutor_proposals(store, user_id, {p.proposal_id for p in proposals})
    return {"user_id": user_id, "stored": stored, "withdrawn": withdrawn}


@router.post("/{user_id}/quizzes", status_code=201)
def new_quiz(
    user_id: str, body: QuizRequest, history: History, quizzes: Open, generator: Generator
) -> QuizView:
    """Build a quiz on one topic. The answers stay on the server until the quiz is graded."""
    _student(user_id, history)
    quiz = _build_quiz(body.topic_id, generator, body.questions)
    return QuizView(
        quiz_id=quizzes.add(user_id, quiz),
        topic_id=quiz.topic_id,
        topic_name=_catalog().topics_by_id[quiz.topic_id].name,
        questions=[QuestionView(prompt=q.prompt, options=q.options) for q in quiz.questions],
    )


@router.post("/{user_id}/quizzes/{quiz_id}/answers")
def submit_answers(
    user_id: str, quiz_id: str, body: QuizAnswers, history: History, quizzes: Open, today: Optional[date] = Today
) -> QuizResult:
    """Grade the answers once and add the attempt to the student's quiz history."""
    student = _student(user_id, history)
    quiz = quizzes.take(user_id, quiz_id)
    if quiz is None:
        raise HTTPException(404, f"no open quiz {quiz_id!r} for student {user_id!r}")
    try:
        attempt = grade_quiz(quiz, body.answers, today or date.today())
    except ValueError as err:
        raise HTTPException(422, str(err)) from err
    history.add(user_id, attempt)
    topic_id = quiz.topic_id
    return QuizResult(
        topic_id=topic_id,
        correct=attempt.correct,
        total=attempt.total,
        answer_indexes=[q.answer_index for q in quiz.questions],
        mastery_before=topic_mastery(student.quiz_history, topic_id),
        mastery_after=topic_mastery([*student.quiz_history, attempt], topic_id),
    )


def withdraw_stale_tutor_proposals(store: PlannerStore, user_id: str, current_ids: set[str]) -> list[str]:
    stale = [
        p.proposal_id
        for p in store.list_proposals(user_id)
        if p.source_agent == SourceAgent.TUTOR and p.proposal_id not in current_ids
    ]
    for proposal_id in stale:
        store.set_proposal_status(user_id, proposal_id, ProposalStatus.WITHDRAWN)
    return stale


def tutor_context(today: date, days: int) -> TutorContext:
    return TutorContext(today=today, horizon_days=days, catalog=_catalog())


def _context(today: Optional[date], days: int) -> TutorContext:
    return tutor_context(today or date.today(), days)


def _student(user_id: str, history: QuizHistory) -> StudentProfile:
    try:
        profile = load_student(user_id)
    except KeyError as err:
        raise HTTPException(404, f"no Tutor data for student {user_id!r}") from err
    return profile.model_copy(update={"quiz_history": [*profile.quiz_history, *history.for_user(user_id)]})


def _build_quiz(topic_id: str, generator: QuestionGenerator, count: int) -> Quiz:
    try:
        return build_quiz(topic_id, _catalog(), generator, count)
    except KeyError as err:
        raise HTTPException(404, f"unknown topic {topic_id!r}") from err
    except ValueError as err:
        raise HTTPException(422, str(err)) from err


def _catalog() -> Catalog:
    return _catalog_source().catalog


@lru_cache(maxsize=1)
def _catalog_source() -> CatalogSource:
    """Loaded once; with Sisu as the source, restart the backend to load new course data."""
    return catalog_from_env(os.environ)
