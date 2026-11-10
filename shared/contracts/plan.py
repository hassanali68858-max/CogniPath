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
    """How well the plan serves each objective (study, career, social), each 0-1.

    achieved  share of all proposed value for that goal that is in the plan
    ideal     best share reachable for that goal alone (other goals ignored)
    nadir     worst share among the single-goal best plans (payoff table)
    loss      1 - achieved
    """

    achieved: dict[str, float] = Field(default_factory=dict)
    ideal: dict[str, float] = Field(default_factory=dict)
    nadir: dict[str, float] = Field(default_factory=dict)
    loss: dict[str, float]
    fairness_gap: float = Field(description="max loss - min loss across objectives")
    soft_conflicts: int
    scheduled_minutes: int


class ObjectiveClass(str, Enum):
    """NIMBUS classification: what the student wants for one objective."""

    IMPROVE = "improve"  # make this better
    KEEP = "keep"  # do not let this get worse
    WORSEN = "worsen"  # this may get worse (optionally down to a limit) to pay for the improvement


class Preference(BaseModel):
    """The student's answer to "what should change in this plan?"."""

    classes: dict[str, ObjectiveClass] = Field(
        description="study / career / social -> improve, keep or worsen",
        examples=[{"career": "improve", "study": "keep", "social": "worsen"}],
    )
    limits: dict[str, float] = Field(
        default_factory=dict, description="For 'worsen' goals: lowest acceptable achieved share, 0-1 (optional)"
    )


class TradeOff(BaseModel):
    """What this plan gains and gives up compared with another plan (usually the balanced one)."""

    compared_to: str = Field(description="plan_id of the reference plan")
    deltas: dict[str, float] = Field(description="achieved share difference per objective, -1..1")
    gained: list[str] = Field(default_factory=list, description="titles in this plan but not in the reference")
    given_up: list[str] = Field(default_factory=list, description="titles in the reference but not in this plan")
    summary: str = ""


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
    mode: str = Field(description="balanced, lean_study, lean_career, lean_social or nimbus")
    label: str = ""
    horizon_start: datetime
    horizon_end: datetime
    status: PlanStatus = PlanStatus.DRAFT
    items: list[PlanItem]
    dropped: list[DroppedItem]
    scores: PlanScores
    solver_status: str
    solve_seconds: float
    changes: Optional[PlanChanges] = None
    tradeoff: Optional[TradeOff] = None
    preference: Optional[Preference] = Field(None, description="NIMBUS classification that produced this plan")
    message: Optional[str] = Field(None, description="Plain-language note, e.g. why a request could not be met")
