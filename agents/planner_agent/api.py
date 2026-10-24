"""FastAPI service for the Planner (in-memory store; swap for PostgreSQL later).

Run from the repository root:

    uvicorn agents.planner_agent.api:app --reload
    # docs at http://127.0.0.1:8000/docs
"""

from __future__ import annotations

from datetime import date

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from shared.contracts import ActivityProposal, ItemDecision, Plan, PlannerProfile, PlanStatus

from .io import to_ics
from .planner import make_plans
from .solver import MODES

app = FastAPI(title="CogniPath Planner", version="0.1.0")

# TODO(db): replace with the activity_proposals / plans tables
PROPOSALS: dict[str, ActivityProposal] = {}
PLANS: dict[str, Plan] = {}


class RunRequest(BaseModel):
    profile: PlannerProfile
    horizon_start: date
    days: int = Field(14, ge=1, le=28)
    modes: list[str] = Field(default_factory=lambda: list(MODES))


class Decision(BaseModel):
    item_id: str
    decision: ItemDecision


@app.post("/proposals", status_code=201)
def add_proposals(proposals: list[ActivityProposal]) -> dict:
    for p in proposals:
        PROPOSALS[p.proposal_id] = p
    return {"stored": len(proposals), "total": len(PROPOSALS)}


@app.get("/proposals")
def list_proposals(user_id: str | None = None) -> list[ActivityProposal]:
    return [p for p in PROPOSALS.values() if user_id is None or p.user_id == user_id]


@app.post("/planner/runs")
def run_planner(req: RunRequest) -> list[Plan]:
    unknown = set(req.modes) - set(MODES)
    if unknown:
        raise HTTPException(422, f"unknown modes: {sorted(unknown)}")
    proposals = [p for p in PROPOSALS.values() if p.user_id == req.profile.user_id]
    plans = make_plans(proposals, req.profile, req.horizon_start, req.days, modes=req.modes)
    for plan in plans:
        PLANS[plan.plan_id] = plan
    return plans


@app.get("/planner/plans/{plan_id}")
def get_plan(plan_id: str) -> Plan:
    if plan_id not in PLANS:
        raise HTTPException(404, "plan not found")
    return PLANS[plan_id]


@app.post("/planner/plans/{plan_id}/decisions")
def decide(plan_id: str, decisions: list[Decision]) -> Plan:
    plan = get_plan(plan_id)
    by_id = {i.item_id: i for i in plan.items}
    for d in decisions:
        if d.item_id not in by_id:
            raise HTTPException(404, f"item {d.item_id} not in plan")
        by_id[d.item_id].decision = d.decision
    states = {i.decision for i in plan.items}
    if states == {ItemDecision.ACCEPTED}:
        plan.status = PlanStatus.APPROVED
    elif ItemDecision.ACCEPTED in states:
        plan.status = PlanStatus.PARTIAL
    return plan


@app.get("/planner/plans/{plan_id}/ics", response_class=PlainTextResponse)
def plan_ics(plan_id: str) -> str:
    return to_ics(get_plan(plan_id))
