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
from datetime import date, datetime
from typing import Annotated, Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from shared.contracts import ActivityProposal, ItemDecision, Plan, PlannerProfile, PlanStatus, Preference, ProposalBatch

from .io import to_ics
from .planner import MODES, PlanningError, make_plans, nimbus, replan
from .store import PlannerStore, ProposalStatus


class RunRequest(BaseModel):
    """Start a planning run. Send a profile, or a user_id whose profile is already stored."""

    user_id: Optional[str] = None
    profile: Optional[PlannerProfile] = None
    horizon_start: date
    days: int = Field(14, ge=1, le=28)
    modes: list[str] = Field(default_factory=lambda: list(MODES))


class ReplanRequest(BaseModel):
    """Re-plan after something changed (new proposals, a withdrawn event, a new busy block)."""

    not_before: Optional[datetime] = Field(None, description="Nothing new is placed before this; usually 'now'")
    modes: Optional[list[str]] = Field(None, description="Default: the mode of the plan being re-planned")


class NimbusRequest(Preference):
    """Classify each goal of the plan: improve, keep, or worsen (optionally not below a limit)."""

    not_before: Optional[datetime] = Field(None, description="Nothing new is placed before this; usually 'now'")


class ScheduledActivity(BaseModel):
    proposal_id: str
    plan_id: str
    title: str
    source_agents: list[str]
    start: datetime
    end: datetime


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

    app = FastAPI(title="CogniPath Planner", version="0.3.0", lifespan=lifespan)
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

    @app.post("/proposals/batch", status_code=201)
    def add_batch(batch: ProposalBatch, store: Store) -> dict:
        """Store one agent run (the shared ProposalBatch format, e.g. the Career Agent's career_plan.json)."""
        wrong = [p.proposal_id for p in batch.proposals if p.user_id != batch.user_id]
        if wrong:
            raise HTTPException(422, f"proposals for another user than the batch: {wrong}")
        return {"stored": store.upsert_proposals(batch.proposals), "source_agent": batch.source_agent.value}

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
            if p.status in (PlanStatus.DRAFT, PlanStatus.PARTIAL):
                p.status = PlanStatus.DISCARDED
        store.save_plans(siblings)
        return plan

    def do_replan(base: Plan, req: ReplanRequest, store: PlannerStore) -> list[Plan]:
        if base.status in (PlanStatus.DISCARDED, PlanStatus.SUPERSEDED):
            raise HTTPException(409, f"plan is {base.status.value}; re-plan the current plan")
        if req.modes:
            check_modes(req.modes)
        profile = store.get_profile(base.user_id)
        if profile is None:
            raise HTTPException(404, "no stored profile for this user")
        try:
            plans = replan(
                base, store.list_proposals(base.user_id), profile, not_before=req.not_before, modes=req.modes
            )
        except PlanningError as e:
            raise HTTPException(422, str(e)) from e
        base.status = PlanStatus.SUPERSEDED
        store.save_plans([base, *plans])
        return plans

    @app.post("/planner/plans/{plan_id}/replan")
    def replan_plan(plan_id: str, store: Store, req: Optional[ReplanRequest] = None) -> list[Plan]:
        """Keep accepted items, drop rejected ones, plan everything else again (incl. new proposals)."""
        return do_replan(load_plan(plan_id, store), req or ReplanRequest(), store)

    @app.post("/planner/users/{user_id}/replan")
    def replan_user(user_id: str, store: Store, req: Optional[ReplanRequest] = None) -> list[Plan]:
        """Same as above, for the user's current plan. Call it after agents push new proposals."""
        base = store.current_plan(user_id)
        if base is None:
            raise HTTPException(404, "no plan yet for this user")
        return do_replan(base, req or ReplanRequest(), store)

    @app.post("/planner/plans/{plan_id}/nimbus")
    def steer_plan(plan_id: str, req: NimbusRequest, store: Store) -> Plan:
        """NIMBUS step: "improve career, keep study, social may get worse" -> a new Pareto-optimal plan.

        The new plan joins the same run as another alternative (with a trade-off against this plan).
        Accepted items stay where they are. 422 with a plain-language reason if it cannot be done.
        """
        base = load_plan(plan_id, store)
        if base.status in (PlanStatus.DISCARDED, PlanStatus.SUPERSEDED):
            raise HTTPException(409, f"plan is {base.status.value}; use the current plan")
        profile = store.get_profile(base.user_id)
        if profile is None:
            raise HTTPException(404, "no stored profile for this user")
        pref = Preference(classes=req.classes, limits=req.limits)
        try:
            plan = nimbus(base, store.list_proposals(base.user_id), profile, pref, not_before=req.not_before)
        except PlanningError as e:
            raise HTTPException(422, str(e)) from e
        store.save_plans([plan])
        return plan

    @app.get("/planner/users/{user_id}/schedule")
    def schedule(user_id: str, store: Store) -> list[ScheduledActivity]:
        """Accepted sessions (planner.scheduled_activities). Other agents can read this to avoid clashes."""
        return [ScheduledActivity(**row) for row in store.scheduled(user_id)]

    @app.get("/planner/plans/{plan_id}/ics", response_class=PlainTextResponse)
    def plan_ics(plan_id: str, store: Store) -> str:
        return to_ics(load_plan(plan_id, store))

    return app


app = create_app()
