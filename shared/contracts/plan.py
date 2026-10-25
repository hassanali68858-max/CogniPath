"""Planner output: a draft plan the user approves item by item."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class PlanStatus(str, Enum):
    DRAFT = "draft"  # waiting for the user
    PARTIAL = "partial"  # some items accepted
    APPROVED = "approved"  # every item accepted
    DISCARDED = "discarded"  # another alternative from the same run was chosen
    SUPERSEDED = "superseded"  # replaced by a re-planned version


class ItemDecision(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class Session(BaseModel):
    start: datetime
    end: datetime


class PlanItem(BaseModel):
    item_id: str
    proposal_id: str
    source_agents: list[str]
    title: str
    sessions: list[Session]
    value: dict[str, float]
    explanation: str
    decision: ItemDecision = ItemDecision.PENDING


class DroppedItem(BaseModel):
    proposal_id: str
    source_agents: list[str]
    title: str
    explanation: str


class PlanScores(BaseModel):
    """Loss per objective = share of proposed (weighted) value left out, 0-1."""

    loss: dict[str, float]
    fairness_gap: float = Field(description="max loss - min loss across objectives")
    soft_conflicts: int
    scheduled_minutes: int


class PlanChanges(BaseModel):
    """What a re-planned version changed compared with the plan it replaces."""

    added: list[str] = Field(default_factory=list, description="proposal_ids new in this plan")
    removed: list[str] = Field(default_factory=list, description="proposal_ids no longer in the plan")
    moved: list[str] = Field(default_factory=list, description="proposal_ids at a different time")
    kept: int = 0
    notes: list[str] = Field(default_factory=list, description="Things the user should know, in plain words")
    summary: str = ""


class Plan(BaseModel):
    plan_id: str
    run_id: Optional[str] = Field(None, description="Alternatives from one planning run share a run_id")
    based_on: Optional[str] = Field(None, description="plan_id this plan re-plans, if any")
    user_id: str
    mode: str
    horizon_start: datetime
    horizon_end: datetime
    status: PlanStatus = PlanStatus.DRAFT
    items: list[PlanItem]
    dropped: list[DroppedItem]
    scores: PlanScores
    solver_status: str
    solve_seconds: float
    changes: Optional[PlanChanges] = None
