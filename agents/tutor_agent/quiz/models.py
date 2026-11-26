from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Question(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic_id: str
    prompt: str = Field(..., min_length=1)
    options: list[str] = Field(..., min_length=2)
    answer_index: int = Field(..., ge=0)

    @model_validator(mode="after")
    def _check_options(self) -> "Question":
        if self.answer_index >= len(self.options):
            raise ValueError("answer_index is outside the options")
        if len(set(self.options)) != len(self.options):
            raise ValueError("options must be unique")
        return self


class Quiz(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic_id: str
    questions: list[Question] = Field(..., min_length=1)


class MasteryLevel(str, Enum):
    STRONG = "strong"
    WEAK = "weak"
    UNTESTED = "untested"


class TopicStatus(BaseModel):
    """How well the student knows one topic of a current course; for the frontend."""

    model_config = ConfigDict(extra="forbid")

    topic_id: str
    name: str
    course_code: str
    mastery: Optional[float] = None
    level: MasteryLevel
    next_review: Optional[date] = None  # strong topics only: when a refresh quiz is due
