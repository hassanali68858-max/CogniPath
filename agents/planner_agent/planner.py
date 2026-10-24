"""Planner pipeline: validate -> merge duplicates -> solve (3 modes) -> explain -> Plan.

Usage::

    from agents.planner_agent.planner import make_plans
    plans = make_plans(proposals, profile, horizon_start=date(2026, 11, 2), days=14)
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Iterable, Optional

from shared.contracts import (
    ActivityProposal,
    BusyBlock,
    DroppedItem,
    ItemDecision,
    Plan,
    PlanItem,
    PlannerProfile,
    PlanScores,
    Priority,
    Session,
)

from .explain import explain_dropped, explain_scheduled
from .solver import MODES, OBJECTIVES, Candidate, solve

log = logging.getLogger(__name__)
_PRIORITY_ORDER = [Priority.LOW, Priority.MEDIUM, Priority.HIGH]


def merge_duplicates(proposals: Iterable[ActivityProposal]) -> list[Candidate]:
    """Merge the same fixed-time opportunity proposed by several agents.

    Example: a career fair proposed by both the Event and the Career agent
    becomes one candidate with the larger value per objective.
    """
    out: list[Candidate] = []
    index: dict[tuple, Candidate] = {}
    seen_ids: set[str] = set()
    for p in proposals:
        if p.proposal_id in seen_ids:
            log.warning("duplicate proposal_id %s ignored", p.proposal_id)
            continue
        seen_ids.add(p.proposal_id)

        key = (p.opportunity_ref, p.fixed_time.start, p.fixed_time.end) if (p.is_fixed and p.opportunity_ref) else None
        if key is None or key not in index:
            cand = Candidate(proposal=p, source_agents=[p.source_agent.value])
            out.append(cand)
            if key is not None:
                index[key] = cand
            continue

        cand = index[key]
        base = cand.proposal
        merged_value = {k: max(base.value.as_dict()[k], p.value.as_dict()[k]) for k in OBJECTIVES}
        merged_priority = max(base.priority, p.priority, key=_PRIORITY_ORDER.index)
        cand.proposal = base.model_copy(
            update={
                "value": base.value.model_copy(update=merged_value),
                "priority": merged_priority,
                "hard": base.hard or p.hard,
                "reason": f"{base.reason}; {p.reason}",
            }
        )
        if p.source_agent.value not in cand.source_agents:
            cand.source_agents.append(p.source_agent.value)
    return out


def _scores(candidates: list[Candidate], scheduled: set[str], evening: int, minutes: int) -> PlanScores:
    loss = {}
    for k in OBJECTIVES:
        total = sum(c.proposal.value.as_dict()[k] * c.proposal.priority.weight for c in candidates)
        lost = sum(
            c.proposal.value.as_dict()[k] * c.proposal.priority.weight
            for c in candidates
            if c.proposal.proposal_id not in scheduled
        )
        loss[k] = round(lost / total, 3) if total else 0.0
    active = [v for k, v in loss.items() if any(c.proposal.value.as_dict()[k] for c in candidates)]
    gap = round(max(active) - min(active), 3) if active else 0.0
    return PlanScores(loss=loss, fairness_gap=gap, soft_conflicts=evening, scheduled_minutes=minutes)


def make_plan(
    proposals: list[ActivityProposal],
    profile: PlannerProfile,
    horizon_start: date,
    days: int = 14,
    mode: str = "balanced",
    plan_id: Optional[str] = None,
) -> Plan:
    candidates = merge_duplicates(p for p in proposals if p.user_id == profile.user_id)
    by_id = {c.proposal.proposal_id: c for c in candidates}
    res = solve(candidates, profile, horizon_start, days, mode=mode)

    items: list[PlanItem] = []
    dropped: list[DroppedItem] = []
    minutes = 0
    for c in candidates:
        pid = c.proposal.proposal_id
        if pid in res.scheduled:
            sess = res.scheduled[pid].sessions
            minutes += sum(int((e - s).total_seconds() // 60) for s, e in sess)
            items.append(
                PlanItem(
                    item_id=f"{pid}@{mode}",
                    proposal_id=pid,
                    source_agents=c.source_agents,
                    title=c.proposal.title,
                    sessions=[Session(start=s, end=e) for s, e in sess],
                    value=c.proposal.value.as_dict(),
                    explanation=explain_scheduled(c, sess),
                )
            )
        else:
            dropped.append(
                DroppedItem(
                    proposal_id=pid,
                    source_agents=c.source_agents,
                    title=c.proposal.title,
                    explanation=(
                        "No feasible plan: check hard items and busy blocks."
                        if res.status not in ("OPTIMAL", "FEASIBLE")
                        else explain_dropped(c, res, by_id, profile)
                    ),
                )
            )
    items.sort(key=lambda i: i.sessions[0].start)

    hs = datetime.combine(horizon_start, datetime.min.time())
    return Plan(
        plan_id=plan_id or f"{profile.user_id}-{horizon_start.isoformat()}-{mode}",
        user_id=profile.user_id,
        mode=mode,
        horizon_start=hs,
        horizon_end=hs + timedelta(days=days),
        items=items,
        dropped=dropped,
        scores=_scores(candidates, set(res.scheduled), res.evening_sessions, minutes),
        solver_status=res.status,
        solve_seconds=round(res.seconds, 3),
    )


def make_plans(
    proposals: list[ActivityProposal],
    profile: PlannerProfile,
    horizon_start: date,
    days: int = 14,
    modes: Iterable[str] = tuple(MODES),
) -> list[Plan]:
    """One plan per mode (balanced, study_first, career_first) for the user to pick from."""
    return [make_plan(proposals, profile, horizon_start, days, mode=m) for m in modes]


def approved_as_busy(plan: Plan) -> list[BusyBlock]:
    """Accepted items become fixed busy time for the next (re)planning run."""
    return [
        BusyBlock(title=f"[approved] {item.title}", start=s.start, end=s.end)
        for item in plan.items
        if item.decision == ItemDecision.ACCEPTED
        for s in item.sessions
    ]
