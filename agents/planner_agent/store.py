"""Database storage for the Planner (PostgreSQL in Docker, SQLite for quick local runs and tests).

Tables (all prefixed ``planner_`` so they can share one database with the backend):

  planner_profiles    one row per user: PlannerProfile as JSON
  planner_proposals   one row per (user, proposal_id): ActivityProposal as JSON + status
  planner_plans       one row per plan alternative: Plan as JSON + run_id, mode, status
  planner_decisions   audit log of every accept / reject the user makes

Whole Pydantic models are stored as JSON, with the columns we filter on copied
next to them. This keeps the schema small while the contracts are still changing.

Choose the database with the DATABASE_URL environment variable:

  postgresql+psycopg://cognipath:cognipath@localhost:5432/cognipath   (docker compose)
  sqlite:///cognipath_dev.db                                           (default, no setup)
"""

from __future__ import annotations

import os
from datetime import datetime
from enum import Enum
from typing import Iterable, Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, create_engine, delete, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool

from shared.contracts import ActivityProposal, ItemDecision, Plan, PlannerProfile, PlanStatus

DEFAULT_DATABASE_URL = "sqlite:///cognipath_dev.db"


class ProposalStatus(str, Enum):
    ACTIVE = "active"  # can be planned
    REJECTED = "rejected"  # the user said no; never planned again unless the agent changes it
    WITHDRAWN = "withdrawn"  # the agent took it back (event cancelled, job closed)


class Base(DeclarativeBase):
    pass


def _now() -> datetime:
    return datetime.now()


class ProfileRow(Base):
    __tablename__ = "planner_profiles"

    user_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    data: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class ProposalRow(Base):
    __tablename__ = "planner_proposals"

    user_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    proposal_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    source_agent: Mapped[str] = mapped_column(String(20), index=True)
    status: Mapped[str] = mapped_column(String(20), default=ProposalStatus.ACTIVE.value, index=True)
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class PlanRow(Base):
    __tablename__ = "planner_plans"

    plan_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(200), index=True)
    user_id: Mapped[str] = mapped_column(String(100), index=True)
    mode: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), index=True)
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class DecisionRow(Base):
    __tablename__ = "planner_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[str] = mapped_column(ForeignKey("planner_plans.plan_id"), index=True)
    item_id: Mapped[str] = mapped_column(String(250))
    proposal_id: Mapped[str] = mapped_column(String(200))
    decision: Mapped[str] = mapped_column(String(20))
    decided_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


# plans the user can still act on, newest first
_LIVE = (PlanStatus.DRAFT.value, PlanStatus.PARTIAL.value, PlanStatus.APPROVED.value)


class PlannerStore:
    def __init__(self, url: str = DEFAULT_DATABASE_URL):
        kwargs: dict = {}
        if url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False}
            if ":memory:" in url or url in ("sqlite://", "sqlite+pysqlite://"):
                kwargs["poolclass"] = StaticPool  # one shared in-memory database
        self.engine = create_engine(url, **kwargs)
        self._session = sessionmaker(self.engine, expire_on_commit=False)
        Base.metadata.create_all(self.engine)

    @classmethod
    def from_env(cls) -> "PlannerStore":
        return cls(os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL))

    def drop_all(self) -> None:
        """Delete every planner table (tests only)."""
        Base.metadata.drop_all(self.engine)

    # ---- profiles
    def save_profile(self, profile: PlannerProfile) -> None:
        with self._session.begin() as s:
            s.merge(ProfileRow(user_id=profile.user_id, data=profile.model_dump(mode="json")))

    def get_profile(self, user_id: str) -> Optional[PlannerProfile]:
        with self._session() as s:
            row = s.get(ProfileRow, user_id)
            return PlannerProfile.model_validate(row.data) if row else None

    # ---- proposals
    def upsert_proposals(self, proposals: Iterable[ActivityProposal]) -> int:
        """Insert new proposals or update existing ones.

        A withdrawn proposal sent again becomes active; a proposal the user
        rejected stays rejected.
        """
        n = 0
        with self._session.begin() as s:
            for p in proposals:
                row = s.get(ProposalRow, (p.user_id, p.proposal_id))
                data = p.model_dump(mode="json")
                if row is None:
                    s.add(
                        ProposalRow(
                            user_id=p.user_id, proposal_id=p.proposal_id, source_agent=p.source_agent.value, data=data
                        )
                    )
                else:
                    row.data = data
                    row.source_agent = p.source_agent.value
                    if row.status == ProposalStatus.WITHDRAWN.value:
                        row.status = ProposalStatus.ACTIVE.value
                n += 1
        return n

    def list_proposals(
        self, user_id: Optional[str] = None, statuses: Iterable[ProposalStatus] = (ProposalStatus.ACTIVE,)
    ) -> list[ActivityProposal]:
        wanted = [st.value for st in statuses]
        with self._session() as s:
            q = select(ProposalRow).where(ProposalRow.status.in_(wanted))
            if user_id is not None:
                q = q.where(ProposalRow.user_id == user_id)
            rows = s.scalars(q.order_by(ProposalRow.created_at, ProposalRow.proposal_id)).all()
            return [ActivityProposal.model_validate(r.data) for r in rows]

    def proposal_status(self, user_id: str, proposal_id: str) -> Optional[ProposalStatus]:
        with self._session() as s:
            row = s.get(ProposalRow, (user_id, proposal_id))
            return ProposalStatus(row.status) if row else None

    def set_proposal_status(self, user_id: str, proposal_id: str, status: ProposalStatus) -> bool:
        with self._session.begin() as s:
            row = s.get(ProposalRow, (user_id, proposal_id))
            if row is None:
                return False
            row.status = status.value
            return True

    # ---- plans
    def save_plans(self, plans: Iterable[Plan]) -> None:
        with self._session.begin() as s:
            for plan in plans:
                s.merge(
                    PlanRow(
                        plan_id=plan.plan_id,
                        run_id=plan.run_id or plan.plan_id,
                        user_id=plan.user_id,
                        mode=plan.mode,
                        status=plan.status.value,
                        data=plan.model_dump(mode="json"),
                    )
                )

    def get_plan(self, plan_id: str) -> Optional[Plan]:
        with self._session() as s:
            row = s.get(PlanRow, plan_id)
            return Plan.model_validate(row.data) if row else None

    def plans_in_run(self, run_id: str) -> list[Plan]:
        with self._session() as s:
            rows = s.scalars(select(PlanRow).where(PlanRow.run_id == run_id).order_by(PlanRow.plan_id)).all()
            return [Plan.model_validate(r.data) for r in rows]

    def current_plan(self, user_id: str) -> Optional[Plan]:
        """The plan the user is working with: newest plan with accepted items, else newest draft."""
        with self._session() as s:
            q = select(PlanRow).where(PlanRow.user_id == user_id, PlanRow.status.in_(_LIVE))
            rows = s.scalars(q.order_by(PlanRow.created_at.desc())).all()
            chosen = [r for r in rows if r.status != PlanStatus.DRAFT.value]
            row = (chosen or rows or [None])[0]
            return Plan.model_validate(row.data) if row else None

    def record_decisions(self, plan: Plan, decisions: Iterable[tuple[str, str, ItemDecision]]) -> None:
        """Save the updated plan and log (item_id, proposal_id, decision) rows."""
        self.save_plans([plan])
        with self._session.begin() as s:
            for item_id, proposal_id, decision in decisions:
                s.add(
                    DecisionRow(plan_id=plan.plan_id, item_id=item_id, proposal_id=proposal_id, decision=decision.value)
                )

    def delete_user(self, user_id: str) -> None:
        """Remove everything stored for one user (demo reset)."""
        with self._session.begin() as s:
            plan_ids = s.scalars(select(PlanRow.plan_id).where(PlanRow.user_id == user_id)).all()
            if plan_ids:
                s.execute(delete(DecisionRow).where(DecisionRow.plan_id.in_(plan_ids)))
            s.execute(delete(PlanRow).where(PlanRow.user_id == user_id))
            s.execute(delete(ProposalRow).where(ProposalRow.user_id == user_id))
            s.execute(delete(ProfileRow).where(ProfileRow.user_id == user_id))

    def decision_log(self, plan_id: str) -> list[tuple[str, str]]:
        with self._session() as s:
            rows = s.scalars(select(DecisionRow).where(DecisionRow.plan_id == plan_id).order_by(DecisionRow.id)).all()
            return [(r.item_id, r.decision) for r in rows]
