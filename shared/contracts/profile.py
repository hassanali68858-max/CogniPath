"""User profile fields the Planner needs (availability and objective weights)."""

from __future__ import annotations

from datetime import datetime, time

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ObjectiveWeights(BaseModel):
    """Relative importance the user gives each goal (any positive scale)."""

    model_config = ConfigDict(extra="forbid")

    study: float = Field(1.0, ge=0.0)
    career: float = Field(1.0, ge=0.0)
    social: float = Field(1.0, ge=0.0)


class BusyBlock(BaseModel):
    """Time already taken: lectures, work shifts, imported calendar events."""

    model_config = ConfigDict(extra="forbid")

    title: str
    start: datetime
    end: datetime

    @model_validator(mode="after")
    def _check_order(self) -> "BusyBlock":
        if self.end <= self.start:
            raise ValueError("busy block end must be after start")
        return self


class PlannerProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str
    weights: ObjectiveWeights = Field(default_factory=ObjectiveWeights)

    day_start: time = time(8, 0)  # nothing is planned before this
    day_end: time = time(22, 0)  # ... or after this
    evening_after: time = time(20, 0)  # sessions ending later get a soft penalty
    daily_cap_min: int = Field(360, ge=30)  # max planned minutes per day (excl. busy blocks)
    free_weekdays: list[int] = Field(default_factory=list)  # 0=Mon ... 6=Sun, keep empty

    busy_blocks: list[BusyBlock] = Field(default_factory=list)

    fairness_weight: float = Field(1.0, ge=0.0)  # mu: "nobody gets ignored"
    conflict_weight: float = Field(0.2, ge=0.0)  # lambda_f: soft-conflict penalty
