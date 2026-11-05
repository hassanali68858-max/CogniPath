"""Planner pipeline (multi-objective, no priorities).

    validate -> merge duplicates -> payoff table (ideal / nadir)
             -> ASF balanced plan + Pareto "leaning" alternatives -> explain trade-offs
             -> the student picks, or steers with NIMBUS (improve / keep / may worsen)

The three goals (study, career, social) are never added up with fixed weights.
Each plan is Pareto-optimal: no goal can get better without another getting worse.

Usage::

    from agents.planner_agent.planner import make_plans, nimbus
    plans = make_plans(proposals, profile, horizon_start=date(2026, 11, 2), days=14)
    better = nimbus(plans[0], proposals, profile, Preference(classes={"career": "improve", "social": "worsen"}))
"""

from __future__ import annotations

import logging
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterable, Optional

from shared.contracts import (
    ActivityProposal,
    BusyBlock,
    DroppedItem,
    ItemDecision,
    ObjectiveClass,
    Plan,
    PlanChanges,
    PlanItem,
    PlannerProfile,
    PlanScores,
    PlanStatus,
    Preference,
    Session,
    TradeOff,
)

from .explain import explain_dropped, explain_scheduled
from .solver import OBJECTIVES, SCALE, Candidate, SolveResult, Target, gain_coefficients, solve

log = logging.getLogger(__name__)

# Alternatives shown to the student. Each one is an ASF solve with a different reference point.
MODES: dict[str, str] = {
    "balanced": "Balanced",
    "lean_study": "More study",
    "lean_career": "More career",
    "lean_social": "More social",
}
LEAN_SHARE = 0.25  # a leaning plan asks the other goals for a quarter of their reachable range
GOAL_NAMES = {"study": "Study", "career": "Career", "social": "Social"}

Sessions = dict[str, list[tuple[datetime, datetime]]]


# Independent solves (one per goal, one per alternative) run in parallel threads;
# CP-SAT releases the GIL while it solves. Each solve stays single-threaded, so plans are reproducible.
PARALLEL = max(1, min(4, os.cpu_count() or 1))


def _parallel(fn, args: list) -> list:
    if PARALLEL == 1 or len(args) < 2:
        return [fn(a) for a in args]
    with ThreadPoolExecutor(max_workers=PARALLEL) as pool:
        return list(pool.map(fn, args))


class PlanningError(ValueError):
    """A request the Planner cannot satisfy; the message is meant for the student."""


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
        cand.proposal = base.model_copy(
            update={
                "value": base.value.model_copy(update=merged_value),
                "hard": base.hard or p.hard,
                "reason": f"{base.reason}; {p.reason}",
            }
        )
        if p.source_agent.value not in cand.source_agents:
            cand.source_agents.append(p.source_agent.value)
    return out


@dataclass
class Frontier:
    """Payoff table summary, in permille: best and worst reachable share per goal."""

    ideal: dict[str, int]
    nadir: dict[str, int]

    @property
    def ranges(self) -> dict[str, int]:
        return {k: max(1, self.ideal[k] - self.nadir[k]) for k in self.ideal}


def payoff_table(
    candidates: list[Candidate], profile: PlannerProfile, horizon_start: date, days: int, **kw
) -> Frontier:
    """For each goal: its best share alone, then the best other goals with that share fixed.

    ideal_k = best G_k;  nadir_k = worst G_k across those rows (the usual payoff-table estimate).
    """

    def row(k: str) -> dict[str, int]:
        best = solve(candidates, profile, horizon_start, days, target=Target(kind="max", objective=k), **kw)
        if best.status not in ("OPTIMAL", "FEASIBLE"):
            raise PlanningError("No feasible plan: check hard items, accepted items and busy blocks.")
        full = solve(
            candidates, profile, horizon_start, days, target=Target(kind="sum", lower={k: best.gains[k]}), **kw
        )
        return full.gains if full.status in ("OPTIMAL", "FEASIBLE") else best.gains

    goals = list(gain_coefficients(candidates))
    rows = dict(zip(goals, _parallel(row, goals), strict=True))
    ideal = {k: r[k] for k, r in rows.items()}
    nadir = {k: min(r.get(k, 0) for r in rows.values()) for k in rows}
    return Frontier(ideal=ideal, nadir=nadir)


def reference_point(mode: str, frontier: Frontier) -> dict[str, int]:
    """Balanced: aim at the ideal for every goal. Leaning to k: ideal for k, half-way for the rest."""
    if mode == "balanced":
        return dict(frontier.ideal)
    lean = mode.removeprefix("lean_")
    return {
        k: frontier.ideal[k]
        if k == lean
        else frontier.nadir[k] + round(LEAN_SHARE * (frontier.ideal[k] - frontier.nadir[k]))
        for k in frontier.ideal
    }


def _achieved(candidates: list[Candidate], scheduled: set[str]) -> dict[str, float]:
    out = {}
    for k in OBJECTIVES:
        total = sum(c.proposal.value.as_dict()[k] for c in candidates)
        if total > 0:
            got = sum(c.proposal.value.as_dict()[k] for c in candidates if c.proposal.proposal_id in scheduled)
            out[k] = round(got / total, 3)
    return out


def _scores(
    candidates: list[Candidate], scheduled: set[str], evening: int, minutes: int, frontier: Optional[Frontier]
) -> PlanScores:
    achieved = _achieved(candidates, scheduled)
    loss = {k: round(1 - achieved.get(k, 1.0), 3) for k in OBJECTIVES}
    active = [1 - v for v in achieved.values()]
    gap = round(max(active) - min(active), 3) if active else 0.0
    return PlanScores(
        achieved=achieved,
        ideal={k: min(1.0, v / SCALE) for k, v in frontier.ideal.items()} if frontier else {},
        nadir={k: min(1.0, v / SCALE) for k, v in frontier.nadir.items()} if frontier else {},
        loss=loss,
        fairness_gap=gap,
        soft_conflicts=evening,
        scheduled_minutes=minutes,
    )


def _to_plan(
    res: SolveResult,
    candidates: list[Candidate],
    profile: PlannerProfile,
    horizon_start: date,
    days: int,
    *,
    mode: str,
    label: str,
    plan_id: str,
    run_id: str,
    locked: Sessions,
    frontier: Optional[Frontier],
) -> Plan:
    by_id = {c.proposal.proposal_id: c for c in candidates}
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
                    item_id=f"{pid}@{plan_id.rsplit('-', 1)[-1] if mode == 'nimbus' else mode}",
                    proposal_id=pid,
                    source_agents=c.source_agents,
                    title=c.proposal.title,
                    sessions=[Session(start=s, end=e) for s, e in sess],
                    value=c.proposal.value.as_dict(),
                    explanation=(
                        "You accepted this; it stays at the same time." if pid in locked else explain_scheduled(c, sess)
                    ),
                    decision=ItemDecision.ACCEPTED if pid in locked else ItemDecision.PENDING,
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
    plan = Plan(
        plan_id=plan_id,
        run_id=run_id,
        user_id=profile.user_id,
        mode=mode,
        label=label,
        horizon_start=hs,
        horizon_end=hs + timedelta(days=days),
        items=items,
        dropped=dropped,
        scores=_scores(candidates, set(res.scheduled), res.evening_sessions, minutes, frontier),
        solver_status=res.status,
        solve_seconds=round(res.seconds, 3),
    )
    if locked and any(i.decision == ItemDecision.ACCEPTED for i in items):
        plan.status = PlanStatus.PARTIAL
    return plan


def _candidates(proposals: Iterable[ActivityProposal], user_id: str) -> list[Candidate]:
    return merge_duplicates(p for p in proposals if p.user_id == user_id)


def make_plan(
    proposals: list[ActivityProposal],
    profile: PlannerProfile,
    horizon_start: date,
    days: int = 14,
    mode: str = "balanced",
    plan_id: Optional[str] = None,
    run_id: Optional[str] = None,
    locked: Optional[Sessions] = None,
    not_before: Optional[datetime] = None,
    previous: Optional[Sessions] = None,
    frontier: Optional[Frontier] = None,
) -> Plan:
    """Plan one alternative (an ASF solve towards the mode's reference point)."""
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}; choose from {sorted(MODES)}")
    run_id = run_id or new_run_id(profile.user_id)
    locked = locked or {}
    candidates = _candidates(proposals, profile.user_id)
    kw = dict(locked=locked, not_before=not_before, previous=previous)
    try:
        frontier = frontier or payoff_table(candidates, profile, horizon_start, days, **kw)
        target = Target(kind="asf", reference=reference_point(mode, frontier), ranges=frontier.ranges)
    except PlanningError:
        frontier, target = None, Target()
    res = solve(candidates, profile, horizon_start, days, target=target, **kw)
    return _to_plan(
        res,
        candidates,
        profile,
        horizon_start,
        days,
        mode=mode,
        label=MODES[mode],
        plan_id=plan_id or f"{run_id}-{mode}",
        run_id=run_id,
        locked=locked,
        frontier=frontier,
    )


def make_plans(
    proposals: list[ActivityProposal],
    profile: PlannerProfile,
    horizon_start: date,
    days: int = 14,
    modes: Iterable[str] = tuple(MODES),
    *,
    locked: Optional[Sessions] = None,
    not_before: Optional[datetime] = None,
    previous: Optional[Sessions] = None,
    run_id: Optional[str] = None,
) -> list[Plan]:
    """The balanced plan plus Pareto-optimal alternatives that lean towards one goal.

    Alternatives that end up identical to an earlier one, or are dominated by
    another (worse or equal on every goal), are left out. Each alternative
    carries a TradeOff against the balanced plan.
    """
    modes = list(modes)
    for m in modes:
        if m not in MODES:
            raise ValueError(f"unknown mode {m!r}; choose from {sorted(MODES)}")
    run_id = run_id or new_run_id(profile.user_id)
    candidates = _candidates(proposals, profile.user_id)
    kw = dict(locked=locked, not_before=not_before, previous=previous)
    try:
        frontier: Optional[Frontier] = payoff_table(candidates, profile, horizon_start, days, **kw)
    except PlanningError:
        frontier = None

    if frontier is not None and frontier.ideal == frontier.nadir and "balanced" in modes:
        modes = ["balanced"]  # the goals do not compete: every alternative would be this same plan
    solved = _parallel(
        lambda m: make_plan(proposals, profile, horizon_start, days, mode=m, run_id=run_id, frontier=frontier, **kw),
        modes,
    )
    plans: list[Plan] = []
    for plan in solved:
        same = next((p for p in plans if _item_set(p) == _item_set(plan)), None)
        if same is not None:
            log.info("%s gives the same activities as %s; not shown", plan.mode, same.mode)
            continue
        plans.append(plan)
    plans = pareto_filter(plans)
    ref = next((p for p in plans if p.mode == "balanced"), None)
    if ref is not None:
        for p in plans:
            if p is not ref:
                p.tradeoff = trade_off(p, ref)
    return plans


def _item_set(plan: Plan) -> frozenset[str]:
    return frozenset(i.proposal_id for i in plan.items)


def dominates(a: Plan, b: Plan) -> bool:
    """a is at least as good as b on every goal and better on one."""
    ka, kb = a.scores.achieved, b.scores.achieved
    keys = set(ka) | set(kb)
    ge = all(ka.get(k, 0) >= kb.get(k, 0) - 1e-9 for k in keys)
    gt = any(ka.get(k, 0) > kb.get(k, 0) + 1e-9 for k in keys)
    return ge and gt


def pareto_filter(plans: list[Plan]) -> list[Plan]:
    return [p for p in plans if not any(dominates(q, p) for q in plans if q is not p)]


def trade_off(plan: Plan, ref: Plan) -> TradeOff:
    """Plain-language comparison of plan against ref (per goal, and which activities differ)."""
    a, b = plan.scores.achieved, ref.scores.achieved
    deltas = {k: round(a.get(k, 0) - b.get(k, 0), 3) for k in sorted(set(a) | set(b), key=OBJECTIVES.index)}
    mine = {i.proposal_id: i.title for i in plan.items}
    theirs = {i.proposal_id: i.title for i in ref.items}
    gained = [t for pid, t in mine.items() if pid not in theirs]
    given_up = [t for pid, t in theirs.items() if pid not in mine]
    moves = [f"{GOAL_NAMES[k]} {d * 100:+.0f} pts" for k, d in deltas.items() if abs(d) >= 0.005]
    parts = [", ".join(moves) + f" compared with {ref.label or ref.mode}." if moves else "Same goal scores."]
    if gained:
        parts.append("Adds " + ", ".join(gained) + ".")
    if given_up:
        parts.append("Gives up " + ", ".join(given_up) + ".")
    return TradeOff(compared_to=ref.plan_id, deltas=deltas, gained=gained, given_up=given_up, summary=" ".join(parts))


def new_run_id(user_id: str) -> str:
    """Unique id for one planning run, e.g. student001-20261102T091500-3f2a."""
    return f"{user_id}-{datetime.now():%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:4]}"


def approved_as_busy(plan: Plan) -> list[BusyBlock]:
    """Accepted items become fixed busy time for the next (re)planning run."""
    return [
        BusyBlock(title=f"[approved] {item.title}", start=s.start, end=s.end)
        for item in plan.items
        if item.decision == ItemDecision.ACCEPTED
        for s in item.sessions
    ]


def _carry_over(base: Plan, proposals: list[ActivityProposal], profile: PlannerProfile):
    """Accepted items stay (unless withdrawn or now clashing); rejected ones are left out."""
    rejected = {i.proposal_id for i in base.items if i.decision == ItemDecision.REJECTED}
    available = {p.proposal_id: p for p in proposals if p.user_id == base.user_id and p.proposal_id not in rejected}
    notes: list[str] = []
    locked: Sessions = {}
    for item in base.items:
        if item.decision != ItemDecision.ACCEPTED:
            continue
        if item.proposal_id not in available:
            notes.append(f"'{item.title}' was withdrawn by the {'/'.join(item.source_agents)} agent.")
            continue
        sessions = [(s.start, s.end) for s in item.sessions]
        clash = next(
            (b for b in profile.busy_blocks for a, e in sessions if b.start < e and a < b.end),
            None,
        )
        if clash is not None:
            notes.append(f"'{item.title}' now clashes with '{clash.title}', so it was planned again.")
            continue
        locked[item.proposal_id] = sessions
    previous = {
        i.proposal_id: [(s.start, s.end) for s in i.sessions]
        for i in base.items
        if i.decision == ItemDecision.PENDING and i.proposal_id not in locked
    }
    return list(available.values()), locked, previous, notes


def replan(
    base: Plan,
    proposals: list[ActivityProposal],
    profile: PlannerProfile,
    *,
    not_before: Optional[datetime] = None,
    modes: Optional[Iterable[str]] = None,
) -> list[Plan]:
    """Plan again after something changed, keeping what the user already accepted.

    - accepted items keep their exact times (unless their proposal was withdrawn,
      or a new busy block now clashes with them; then they are planned again)
    - rejected items are left out
    - pending items and new proposals are planned freely, not before ``not_before``
    - same horizon as ``base``; default: one plan with the base plan's mode
      (a NIMBUS plan is re-planned as balanced)
    """
    available, locked, previous, notes = _carry_over(base, proposals, profile)
    horizon_start = base.horizon_start.date()
    days = (base.horizon_end - base.horizon_start).days
    modes = list(modes or [base.mode if base.mode in MODES else "balanced"])
    plans = make_plans(
        available, profile, horizon_start, days, modes, locked=locked, not_before=not_before, previous=previous
    )
    for plan in plans:
        plan.based_on = base.plan_id
        plan.changes = compare_plans(base, plan, notes)
    return plans


def nimbus(
    base: Plan,
    proposals: list[ActivityProposal],
    profile: PlannerProfile,
    preference: Preference,
    *,
    not_before: Optional[datetime] = None,
    plan_id: Optional[str] = None,
) -> Plan:
    """NIMBUS-style step: the student classifies each goal of ``base`` and gets a new Pareto-optimal plan.

    improve  pushed towards its ideal (the ASF looks only at these goals)
    keep     must not get worse than in ``base``
    worsen   may get worse, down to ``preference.limits[goal]`` if given

    Goals that are not classified count as "worsen" without a limit.
    Accepted items stay fixed; the new plan joins the base plan's run as another alternative.
    Raises PlanningError (with a sentence for the student) when the request cannot be met.
    """
    classes = {k: ObjectiveClass(v) for k, v in preference.classes.items()}
    unknown = set(classes) - set(OBJECTIVES)
    if unknown:
        raise PlanningError(f"Unknown goals: {sorted(unknown)}. Use study, career, social.")
    improve = [k for k, c in classes.items() if c == ObjectiveClass.IMPROVE]
    if not improve:
        raise PlanningError("Choose at least one goal to improve.")
    if all(classes.get(k) in (ObjectiveClass.IMPROVE, ObjectiveClass.KEEP) for k in OBJECTIVES):
        raise PlanningError(
            "Every plan shown is already the best possible balance, so to improve one goal "
            "at least one other goal has to be allowed to get worse."
        )

    available, locked, previous, notes = _carry_over(base, proposals, profile)
    candidates = _candidates(available, base.user_id)
    horizon_start = base.horizon_start.date()
    days = (base.horizon_end - base.horizon_start).days
    kw = dict(locked=locked, not_before=not_before, previous=previous)
    frontier = payoff_table(candidates, profile, horizon_start, days, **kw)

    coeffs = gain_coefficients(candidates)
    in_base = {i.proposal_id for i in base.items if i.proposal_id in {c.proposal.proposal_id for c in candidates}}
    current = {k: sum(a for pid, a in ck.items() if pid in in_base) for k, ck in coeffs.items()}
    lower: dict[str, int] = {}
    for k in coeffs:
        c = classes.get(k, ObjectiveClass.WORSEN)
        if c in (ObjectiveClass.IMPROVE, ObjectiveClass.KEEP):
            lower[k] = current[k]
        elif k in preference.limits:  # a limit above today's value would forbid the current plan itself
            lower[k] = min(current[k], round(SCALE * preference.limits[k]))
    active = {k for k in improve if k in coeffs}
    if not active:
        raise PlanningError("Nothing was proposed for the goal(s) you want to improve.")

    target = Target(kind="asf", reference=dict(frontier.ideal), ranges=frontier.ranges, active=active, lower=lower)
    res = solve(candidates, profile, horizon_start, days, target=target, **kw)
    if res.status not in ("OPTIMAL", "FEASIBLE"):
        raise PlanningError(
            "No plan can keep the goals you marked 'keep' and respect your limits. Allow more to get worse."
        )

    names = " and ".join(GOAL_NAMES[k].lower() for k in improve)
    if all(current[k] >= frontier.ideal[k] for k in active):
        raise PlanningError(f"{names.capitalize()} is already as high as any plan can make it with these suggestions.")
    if all(res.gains.get(k, 0) <= current.get(k, 0) for k in active):
        raise PlanningError(
            f"No plan gives more {names} without breaking your 'keep' choices or limits. "
            "Allow another goal to give a little more."
        )

    run_id = base.run_id or base.plan_id
    pid = plan_id or f"{run_id}-nimbus-{uuid.uuid4().hex[:4]}"
    plan = _to_plan(
        res,
        candidates,
        profile,
        horizon_start,
        days,
        mode="nimbus",
        label=f"Your choice: more {names}",
        plan_id=pid,
        run_id=run_id,
        locked=locked,
        frontier=frontier,
    )
    plan.based_on = base.plan_id
    plan.preference = preference
    plan.tradeoff = trade_off(plan, base)  # the trade-off replaces a "what changed" list here
    if notes:
        plan.message = " ".join(notes)
    return plan


def compare_plans(old: Plan, new: Plan, notes: Optional[list[str]] = None) -> PlanChanges:
    """What changed from ``old`` to ``new``, by proposal."""
    before = {i.proposal_id: [(s.start, s.end) for s in i.sessions] for i in old.items}
    after = {i.proposal_id: [(s.start, s.end) for s in i.sessions] for i in new.items}
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    moved = sorted(pid for pid in set(before) & set(after) if before[pid] != after[pid])
    kept = len(set(before) & set(after)) - len(moved)
    parts = [f"{n} {word}" for n, word in ((len(added), "added"), (len(moved), "moved"), (len(removed), "removed"))]
    summary = ", ".join(parts) + f", {kept} unchanged" if (added or moved or removed) else "No changes"
    return PlanChanges(added=added, removed=removed, moved=moved, kept=kept, notes=list(notes or []), summary=summary)
