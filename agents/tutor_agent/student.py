"""What the Tutor Agent knows about one student.

Field origin (check again when the Sisu connection is built):
- "Sisu": expected to be importable from the student's Sisu study plan.
- "student": the student enters it in CogniPath.
- "CogniPath": CogniPath records it itself (quiz results).
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CourseAttainment(BaseModel):
    """A completed course (Sisu)."""

    model_config = ConfigDict(extra="forbid")

    code: str
    credits: float = Field(..., gt=0)
    grade: Optional[int] = Field(None, ge=0, le=5)  # None = pass/fail
    completed_on: date


class Enrollment(BaseModel):
    """A course the student takes in the current period (Sisu)."""

    model_config = ConfigDict(extra="forbid")

    code: str
    exam_date: Optional[date] = None


class QuizAttempt(BaseModel):
    """One finished quiz on one topic (CogniPath)."""

    model_config = ConfigDict(extra="forbid")

    topic_id: str
    correct: int = Field(..., ge=0)
    total: int = Field(..., gt=0)
    taken_on: date

    @model_validator(mode="after")
    def _check_counts(self) -> "QuizAttempt":
        if self.correct > self.total:
            raise ValueError("correct must not be greater than total")
        return self

    @property
    def score(self) -> float:
        return self.correct / self.total


class StudentProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str
    programme_id: str  # Sisu
    study_start: date  # Sisu
    target_graduation: date  # student
    completed: list[CourseAttainment] = Field(default_factory=list)  # Sisu
    enrolled: list[Enrollment] = Field(default_factory=list)  # Sisu
    planned: list[str] = Field(default_factory=list)  # Sisu: course codes in the study plan, not yet taken
    interests: list[str] = Field(default_factory=list)  # student: lower-case tags, e.g. "knowledge-graphs"
    languages: list[str] = Field(default_factory=lambda: ["en"])  # student: ISO 639-1 codes
    quiz_history: list[QuizAttempt] = Field(default_factory=list)  # CogniPath

    @field_validator("interests", "languages")
    @classmethod
    def _lower(cls, values: list[str]) -> list[str]:
        return [v.lower() for v in values]

    @model_validator(mode="after")
    def _check_dates(self) -> "StudentProfile":
        if self.target_graduation <= self.study_start:
            raise ValueError("target_graduation must be after study_start")
        return self

    @property
    def completed_codes(self) -> set[str]:
        return {c.code for c in self.completed}

    @property
    def enrolled_codes(self) -> set[str]:
        return {e.code for e in self.enrolled}

    @property
    def completed_credits(self) -> float:
        return sum(c.credits for c in self.completed)
