"""FastAPI service for the Planner, backed by PostgreSQL (or SQLite).

Run from the repository root:

    docker compose -f infra/docker-compose.yml up -d          # PostgreSQL
    export DATABASE_URL=postgresql+psycopg://cognipath:cognipath@localhost:5432/cognipath
    uvicorn agents.planner_agent.api:app --reload
    # docs at http://127.0.0.1:8000/docs

Without DATABASE_URL the API uses a local SQLite file (cognipath_dev.db).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date
from typing import Annotated, Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from shared.contracts import ActivityProposal, ItemDecision, Plan, PlannerProfile, PlanStatus

from .io import to_ics
from .planner import make_plans
from .solver import MODES
from .store import PlannerStore, ProposalStatus


class RunRequest(BaseModel):
    """Start a planning run. Send a profile, or a user_id whose profile is already stored."""

    user_id: Optional[str] = None
    profile: Optional[PlannerProfile] = None
    horizon_start: date
    days: int = Field(14, ge=1, le=28)
    modes: list[str] = Field(default_factory=lambda: list(MODES))


class Decision(BaseModel):
    item_id: str
    decision: ItemDecision


def get_store(request: Request) -> PlannerStore:
    if request.app.state.store is None:
        request.app.state.store = PlannerStore.from_env()
    return request.app.state.store


Store = Annotated[PlannerStore, Depends(get_store)]


def create_app(store: Optional[PlannerStore] = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if getattr(app.state, "store", None) is None:
            app.state.store = PlannerStore.from_env()
        yield

    app = FastAPI(title="CogniPath Planner", version="0.2.0", lifespan=lifespan)
    app.state.store = store

    def load_plan(plan_id: str, store: PlannerStore) -> Plan:
        plan = store.get_plan(plan_id)
        if plan is None:
            raise HTTPException(404, "plan not found")
        return plan

    def check_modes(modes: list[str]) -> None:
        unknown = set(modes) - set(MODES)
        if unknown:
            raise HTTPException(422, f"unknown modes: {sorted(unknown)}")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    # ---- profiles
    @app.put("/profiles/{user_id}")
    def put_profile(user_id: str, profile: PlannerProfile, store: Store) -> PlannerProfile:
        if profile.user_id != user_id:
            raise HTTPException(422, "user_id in the path and body differ")
        store.save_profile(profile)
        return profile

    @app.get("/profiles/{user_id}")
    def get_profile(user_id: str, store: Store) -> PlannerProfile:
        profile = store.get_profile(user_id)
        if profile is None:
            raise HTTPException(404, "profile not found")
        return profile

    # ---- proposals (agents push here)
    @app.post("/proposals", status_code=201)
    def add_proposals(proposals: list[ActivityProposal], store: Store) -> dict:
        return {"stored": store.upsert_proposals(proposals)}

    @app.get("/proposals")
    def list_proposals(
        store: Store,
        user_id: Optional[str] = None,
        status: ProposalStatus = ProposalStatus.ACTIVE,
    ) -> list[ActivityProposal]:
        return store.list_proposals(user_id, statuses=[status])

    @app.post("/proposals/{user_id}/{proposal_id}/withdraw")
    def withdraw_proposal(user_id: str, proposal_id: str, store: Store) -> dict:
        """An agent takes a proposal back (event cancelled, job closed)."""
        if not store.set_proposal_status(user_id, proposal_id, ProposalStatus.WITHDRAWN):
            raise HTTPException(404, "proposal not found")
        return {"proposal_id": proposal_id, "status": ProposalStatus.WITHDRAWN.value}

    # ---- planning
    @app.post("/planner/runs")
    def run_planner(req: RunRequest, store: Store) -> list[Plan]:
        check_modes(req.modes)
        if req.profile is not None:
            store.save_profile(req.profile)
            profile = req.profile
        elif req.user_id is not None:
            profile = store.get_profile(req.user_id)
            if profile is None:
                raise HTTPException(404, "no stored profile for this user; send a profile")
        else:
            raise HTTPException(422, "send a profile or a user_id")
        proposals = store.list_proposals(profile.user_id)
        plans = make_plans(proposals, profile, req.horizon_start, req.days, modes=req.modes)
        store.save_plans(plans)
        return plans

    @app.get("/planner/runs/{run_id}")
    def get_run(run_id: str, store: Store) -> list[Plan]:
        plans = store.plans_in_run(run_id)
        if not plans:
            raise HTTPException(404, "run not found")
        return plans

    @app.get("/planner/plans/{plan_id}")
    def get_plan(plan_id: str, store: Store) -> Plan:
        return load_plan(plan_id, store)

    @app.get("/planner/users/{user_id}/current")
    def current_plan(user_id: str, store: Store) -> Plan:
        plan = store.current_plan(user_id)
        if plan is None:
            raise HTTPException(404, "no plan yet for this user")
        return plan

    @app.post("/planner/plans/{plan_id}/decisions")
    def decide(plan_id: str, decisions: list[Decision], store: Store) -> Plan:
        """Accept / reject items. The first decision on a plan discards the other alternatives of its run."""
        plan = load_plan(plan_id, store)
        if plan.status in (PlanStatus.DISCARDED, PlanStatus.SUPERSEDED):
            raise HTTPException(409, f"plan is {plan.status.value}; use the current plan")
        by_id = {i.item_id: i for i in plan.items}
        for d in decisions:
            if d.item_id not in by_id:
                raise HTTPException(404, f"item {d.item_id} not in plan")
        log = []
        for d in decisions:
            item = by_id[d.item_id]
            item.decision = d.decision
            log.append((item.item_id, item.proposal_id, d.decision))
            # a rejected proposal is never planned again; changing your mind re-activates it
            new_status = ProposalStatus.REJECTED if d.decision == ItemDecision.REJECTED else ProposalStatus.ACTIVE
            if store.proposal_status(plan.user_id, item.proposal_id) in (
                ProposalStatus.ACTIVE,
                ProposalStatus.REJECTED,
            ):
                store.set_proposal_status(plan.user_id, item.proposal_id, new_status)

        states = {i.decision for i in plan.items}
        if states == {ItemDecision.ACCEPTED}:
            plan.status = PlanStatus.APPROVED
        elif ItemDecision.ACCEPTED in states or ItemDecision.REJECTED in states:
            plan.status = PlanStatus.PARTIAL
        store.record_decisions(plan, log)

        siblings = [p for p in store.plans_in_run(plan.run_id or plan.plan_id) if p.plan_id != plan.plan_id]
        for p in siblings:
            if p.status == PlanStatus.DRAFT:
                p.status = PlanStatus.DISCARDED
        store.save_plans(siblings)
        return plan

    @app.get("/planner/plans/{plan_id}/ics", response_class=PlainTextResponse)
    def plan_ics(plan_id: str, store: Store) -> str:
        return to_ics(load_plan(plan_id, store))

    return app


app = create_app()
