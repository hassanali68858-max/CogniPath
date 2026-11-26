"""Shared study data the Tutor Agent reads: degree rules, courses, opportunities, topic graph.

The same catalog serves every student. It comes from ``data/seed/tutor/`` (see ``seed.py``);
``sisu.py`` can replace the course data with live data from JYU Sisu.
"""

from __future__ import annotations

from datetime import date, timedelta
from enum import Enum
from functools import cached_property
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator


class CourseOffering(BaseModel):
    model_config = ConfigDict(extra="forbid")

    period: str  # e.g. "2027-P3"
    start: date
    end: date
    registration_deadline: date

    @model_validator(mode="after")
    def _check_dates(self) -> "CourseOffering":
        if self.end < self.start:
            raise ValueError("offering end must not be before start")
        if self.registration_deadline > self.start:
            raise ValueError("registration_deadline must not be after the offering start")
        return self


class Course(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    name: str
    credits: float = Field(..., gt=0)
    module_id: str
    language: str = "en"
    tags: list[str] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list)  # course codes
    offerings: list[CourseOffering] = Field(default_factory=list)
    sisu_code: Optional[str] = None  # set when the course data comes from Sisu (see sisu.py)

    @field_validator("tags")
    @classmethod
    def _lower(cls, values: list[str]) -> list[str]:
        return [v.lower() for v in values]

    @property
    def label(self) -> str:
        return f"{self.sisu_code or self.code} {self.name}"


class Module(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    min_credits: float = Field(..., gt=0)
    mandatory: list[str] = Field(default_factory=list)  # course codes


class DegreeProgramme(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    total_credits: float = Field(..., gt=0)
    modules: list[Module]


class OpportunityKind(str, Enum):
    SUMMER_SCHOOL = "summer_school"
    WINTER_SCHOOL = "winter_school"
    ERASMUS = "erasmus"
    FORUM = "forum"


class Opportunity(BaseModel):
    """Something outside the Sisu course list. Forums have no dates or credits."""

    model_config = ConfigDict(extra="forbid")

    id: str
    kind: OpportunityKind
    title: str
    provider: str
    url: Optional[HttpUrl] = None
    location: Optional[str] = None
    language: str = "en"
    tags: list[str] = Field(default_factory=list)
    related_courses: list[str] = Field(default_factory=list)
    credits: Optional[float] = Field(None, gt=0)
    credit_module_id: Optional[str] = None  # degree module the credits can count toward
    start: Optional[date] = None
    end: Optional[date] = None
    application_deadline: Optional[date] = None
    min_completed_credits: float = Field(0.0, ge=0)

    @field_validator("tags")
    @classmethod
    def _lower(cls, values: list[str]) -> list[str]:
        return [v.lower() for v in values]

    @model_validator(mode="after")
    def _check_dates(self) -> "Opportunity":
        if self.kind == OpportunityKind.FORUM:
            return self
        if self.start is None or self.end is None or self.application_deadline is None:
            raise ValueError(f"{self.kind.value} needs start, end and application_deadline")
        if self.end < self.start:
            raise ValueError("opportunity end must not be before start")
        return self


class Fact(BaseModel):
    """One term and its definition; the Quiz Agent builds questions from these."""

    model_config = ConfigDict(extra="forbid")

    term: str
    definition: str


class Resource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    url: HttpUrl
    minutes: int = Field(..., gt=0)


class Topic(BaseModel):
    """A node in the course knowledge graph; prerequisites are the edges."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    course_code: str
    prerequisites: list[str] = Field(default_factory=list)  # topic ids
    facts: list[Fact] = Field(..., min_length=1)
    resources: list[Resource] = Field(default_factory=list)


class Catalog(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    programmes: list[DegreeProgramme]
    courses: list[Course]
    opportunities: list[Opportunity] = Field(default_factory=list)
    topics: list[Topic] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_references(self) -> "Catalog":
        codes = {c.code for c in self.courses}
        for course in self.courses:
            missing = set(course.prerequisites) - codes
            if missing:
                raise ValueError(f"{course.code}: unknown prerequisite courses {sorted(missing)}")
        topic_ids = {t.id for t in self.topics}
        for topic in self.topics:
            missing = set(topic.prerequisites) - topic_ids
            if missing:
                raise ValueError(f"topic {topic.id}: unknown prerequisite topics {sorted(missing)}")
        _check_acyclic({t.id: t.prerequisites for t in self.topics})
        return self

    @cached_property
    def courses_by_code(self) -> dict[str, Course]:
        return {c.code: c for c in self.courses}

    @cached_property
    def topics_by_id(self) -> dict[str, Topic]:
        return {t.id: t for t in self.topics}

    def programme(self, programme_id: str) -> DegreeProgramme:
        for p in self.programmes:
            if p.id == programme_id:
                return p
        raise KeyError(f"unknown programme {programme_id!r}")


class TutorContext(BaseModel):
    """Everything besides the student that one Tutor Agent run needs."""

    model_config = ConfigDict(extra="forbid")

    today: date
    horizon_days: int = Field(14, ge=1, le=28)  # the Planner's planning horizon
    lookahead_days: int = Field(60, ge=1)  # propose registrations/applications that close within this
    catalog: Catalog

    @property
    def horizon_end(self) -> date:
        """Last day the Planner can schedule in (inclusive)."""
        return self.today + timedelta(days=self.horizon_days - 1)

    @property
    def lookahead_end(self) -> date:
        return self.today + timedelta(days=self.lookahead_days)


def _check_acyclic(edges: dict[str, list[str]]) -> None:
    done: set[str] = set()
    path: set[str] = set()

    def visit(node: str) -> None:
        if node in done:
            return
        if node in path:
            raise ValueError(f"topic prerequisites form a cycle at {node!r}")
        path.add(node)
        for nxt in edges.get(node, []):
            visit(nxt)
        path.remove(node)
        done.add(node)

    for node in edges:
        visit(node)
