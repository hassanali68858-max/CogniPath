"""ActivityProposal: the one contract between the domain agents and the Planner.

Every agent (Event, Tutor, Career) returns a list of ActivityProposal objects.
The Planner consumes only this model, so agents can change internally without
breaking the Planner.

Two kinds of proposal:
- Fixed:    an event with a known start/end (set ``fixed_time``).
- Flexible: work that needs ``duration_min`` minutes somewhere inside ``window``
            (a course chapter, "Learn Docker"); the Planner chooses when.

Times are naive local datetimes (Europe/Helsinki) for now.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class SourceAgent(str, Enum):
    EVENT = "event"
    TUTOR = "tutor"
    CAREER = "career"
    USER = "user"  # items the user adds by hand


class ActivityType(str, Enum):
    EVENT = "event"  # attend something at a fixed time
    LEARNING = "learning"  # study a skill / resource
    COURSE_WORK = "course_work"
    APPLICATION = "application"  # write CV, apply for a job, Erasmus form
    QUIZ = "quiz"
    SOCIAL = "social"
    OTHER = "other"


class Priority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

    @property
    def weight(self) -> int:
        return {"low": 1, "medium": 2, "high": 3}[self.value]


class ObjectiveValue(BaseModel):
    """How much the activity serves each objective, on a fixed 0-1 rubric.

    Rubric (agree on it as a team so scores are comparable across agents):
      0.0 no contribution, 0.3 nice to have, 0.6 clearly useful,
      0.9 directly required for a stated goal or course.
    """

    model_config = ConfigDict(extra="forbid")

    study: float = Field(0.0, ge=0.0, le=1.0)
    career: float = Field(0.0, ge=0.0, le=1.0)
    social: float = Field(0.0, ge=0.0, le=1.0)

    def as_dict(self) -> dict[str, float]:
        return {"study": self.study, "career": self.career, "social": self.social}


class FixedTime(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: datetime
    end: datetime

    @model_validator(mode="after")
    def _check_order(self) -> "FixedTime":
        if self.end <= self.start:
            raise ValueError("fixed_time.end must be after fixed_time.start")
        return self


class TimeWindow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    earliest: date
    deadline: date  # inclusive: the work must be finished by the end of this day

    @model_validator(mode="after")
    def _check_order(self) -> "TimeWindow":
        if self.deadline < self.earliest:
            raise ValueError("window.deadline must not be before window.earliest")
        return self


class SessionSplit(BaseModel):
    """How a flexible activity may be cut into sessions."""

    model_config = ConfigDict(extra="forbid")

    min_session_min: int = Field(60, ge=30)
    max_session_min: int = Field(120, ge=30)

    @model_validator(mode="after")
    def _check_order(self) -> "SessionSplit":
        if self.max_session_min < self.min_session_min:
            raise ValueError("max_session_min must be >= min_session_min")
        return self


class ActivityProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_id: str = Field(..., min_length=1)
    source_agent: SourceAgent
    user_id: str
    type: ActivityType
    title: str = Field(..., min_length=1)

    # Where it came from (job id, event id, course code, ontology URI ...)
    opportunity_ref: Optional[str] = None
    resource_url: Optional[HttpUrl] = None

    # Either fixed_time, or duration_min + window
    fixed_time: Optional[FixedTime] = None
    duration_min: Optional[int] = Field(None, ge=30)
    window: Optional[TimeWindow] = None
    split: SessionSplit = Field(default_factory=SessionSplit)

    value: ObjectiveValue
    priority: Priority = Priority.MEDIUM
    hard: bool = False  # True = must be scheduled (exam, mandatory lecture)
    depends_on: list[str] = Field(default_factory=list)  # proposal_ids that must come first

    location: Optional[str] = None
    reason: str = Field(..., min_length=1, description="Why the agent proposes this; shown to the user")

    @model_validator(mode="after")
    def _check_kind(self) -> "ActivityProposal":
        if self.fixed_time is None:
            if self.duration_min is None or self.window is None:
                raise ValueError("a flexible proposal needs duration_min and window (or set fixed_time)")
        else:
            if self.duration_min is not None or self.window is not None:
                raise ValueError("a fixed proposal must not set duration_min or window")
        if self.proposal_id in self.depends_on:
            raise ValueError("a proposal cannot depend on itself")
        return self

    @property
    def is_fixed(self) -> bool:
        return self.fixed_time is not None

    @property
    def total_minutes(self) -> int:
        if self.fixed_time is not None:
            return int((self.fixed_time.end - self.fixed_time.start).total_seconds() // 60)
        assert self.duration_min is not None
        return self.duration_min


class ProposalBatch(BaseModel):
    """What an agent returns for one run."""

    model_config = ConfigDict(extra="forbid")

    source_agent: SourceAgent
    user_id: str
    generated_at: datetime
    proposals: list[ActivityProposal]
