"""User profile fields the Planner needs (availability and limits).

There are no objective weights: the student steers the trade-off between
study, career and social interactively (NIMBUS-style), not with fixed numbers.
"""

from __future__ import annotations

from datetime import datetime, time

from pydantic import BaseModel, ConfigDict, Field, model_validator

_LEGACY_FIELDS = ("weights", "fairness_weight")  # removed in Nov 2026; ignored when read


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

    day_start: time = time(8, 0)  # nothing is planned before this
    day_end: time = time(22, 0)  # ... or after this
    evening_after: time = time(20, 0)  # sessions ending later get a soft penalty
    daily_cap_min: int = Field(360, ge=30)  # max planned minutes per day (excl. busy blocks)
    free_weekdays: list[int] = Field(default_factory=list)  # 0=Mon ... 6=Sun, keep empty

    busy_blocks: list[BusyBlock] = Field(default_factory=list)

    # Among plans that are equally good for every goal, prefer fewer late-evening sessions.
    conflict_weight: float = Field(0.2, ge=0.0)

    @model_validator(mode="before")
    @classmethod
    def _drop_legacy(cls, data):
        if isinstance(data, dict):
            data = {k: v for k, v in data.items() if k not in _LEGACY_FIELDS}
        return data
