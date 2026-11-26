"""Outputs of the Course and Opportunity sub-agent that are not Planner proposals.

These go to the frontend only, so they live here and not in shared/contracts/.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, HttpUrl


class ProgressStatus(str, Enum):
    ON_TRACK = "on_track"
    AT_RISK = "at_risk"


class WarningKind(str, Enum):
    MISSING_MANDATORY = "missing_mandatory"
    MISSING_PREREQUISITE = "missing_prerequisite"
    BEHIND_PACE = "behind_pace"


class ProgressWarning(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: WarningKind
    message: str
    course_code: Optional[str] = None


class ModuleProgress(BaseModel):
    model_config = ConfigDict(extra="forbid")

    module_id: str
    name: str
    completed_credits: float
    required_credits: float

    @property
    def missing_credits(self) -> float:
        return max(0.0, self.required_credits - self.completed_credits)


class CurrentCourse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    name: str
    credits: float
    exam_date: Optional[date] = None


class ProgressReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str
    programme_name: str
    completed_credits: float
    required_credits: float
    required_pace: float  # credits per year needed to graduate on the target date
    status: ProgressStatus
    modules: list[ModuleProgress]
    current_courses: list[CurrentCourse]
    warnings: list[ProgressWarning]


class UpcomingCourse(BaseModel):
    """The next offering of a course the student has not taken yet."""

    model_config = ConfigDict(extra="forbid")

    code: str  # the Sisu code when the course data comes from Sisu
    name: str
    credits: float
    language: str
    start: date
    end: date
    registration_deadline: date
    from_sisu: bool


class ForumLink(BaseModel):
    """A forum or community to show as a link; not scheduled by the Planner."""

    model_config = ConfigDict(extra="forbid")

    title: str
    url: Optional[HttpUrl] = None
    reason: str
