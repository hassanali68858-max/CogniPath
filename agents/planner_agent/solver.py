"""CP-SAT model for the Planner: constraints + one multi-objective target per solve.

Objectives (kept separate, never added with fixed weights or priorities)
  G_k  for k in study, career, social: the share of all proposed value for goal k
       that the plan contains, in permille (0..1000). Bigger is better.

A solve optimises one Target:
  max k   best G_k alone (payoff table, step 1)
  sum     best G_1 + G_2 + G_3 (payoff table, step 2: with G_k fixed at its best, so the
          row is not weakly dominated; together they give the ideal and nadir points)
  asf     reference-point Achievement Scalarizing Function (Wierzbicki):
              minimise  max_{k in active} w_k (ref_k - G_k)  +  rho * sum_k w_k (ref_k - G_k)
          with w_k = 1 / (ideal_k - nadir_k). The result is Pareto-optimal and lies
          as close to the reference point as possible. ref = ideal gives the balanced plan.
  lower   optional bounds G_k >= lower_k (NIMBUS "keep" and "worsen down to a limit")

Tie-breakers, far smaller than any change in a goal: fewer late-evening sessions,
fewer separate sessions, and (when re-planning) moving fewer sessions.

Hard constraints
  - nothing overlaps (scheduled items + busy blocks)
  - fixed events keep their time
  - flexible work is split into at most one session per day, each between
    min_session and max_session long, inside the user's day hours and the
    proposal's window, never on a free weekday; sessions sum to duration_min
  - planned minutes per day <= daily_cap_min
  - dependencies: q only if p is scheduled, and every q session starts after
    every p session ends
  - hard proposals are always scheduled (the model is INFEASIBLE otherwise)
  - locked items (accepted by the user, when re-planning) keep their exact sessions
  - with not_before, nothing new is placed before that moment (re-planning mid-week)

Time is a grid of 30-minute slots starting at horizon_start 00:00.
"""

from __future__ import annotations

import math
import time as _time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Literal, Optional

from ortools.sat.python import cp_model

from shared.contracts import ActivityProposal, PlannerProfile

SLOT_MIN = 30
SLOTS_PER_DAY = 24 * 60 // SLOT_MIN
OBJECTIVES = ("study", "career", "social")
SCALE = 1000  # goal shares in permille
FRAGMENT_PENALTY = 50  # per session used: prefer fewer, longer sessions
MOVE_PENALTY = 100  # per session moved away from the previous plan when re-planning
_ASF_W = 100_000  # w_k = _ASF_W / range_k (integer)
_ASF_RHO = 100  # augmentation rho = 1 / _ASF_RHO


@dataclass
class Candidate:
    """A proposal after merging, plus planner-side bookkeeping."""

    proposal: ActivityProposal
    source_agents: list[str]


@dataclass
class Target:
    """What one solve optimises; see the module docstring."""

    kind: Literal["max", "sum", "asf"] = "asf"
    objective: Optional[str] = None  # for kind="max"
    reference: dict[str, int] = field(default_factory=dict)  # permille; default: 1000 (everything)
    ranges: dict[str, int] = field(default_factory=dict)  # ideal - nadir, permille; default: 1000
    active: Optional[set[str]] = None  # objectives inside the max term; default: all with value
    lower: dict[str, int] = field(default_factory=dict)  # G_k >= lower_k


def gain_coefficients(candidates: list["Candidate"]) -> dict[str, dict[str, int]]:
    """objective -> proposal_id -> its share of that goal's proposed value, in permille.

    Objectives nobody proposed anything for are left out.
    """
    out: dict[str, dict[str, int]] = {}
    for k in OBJECTIVES:
        total = sum(c.proposal.value.as_dict()[k] for c in candidates)
        if total <= 0:
            continue
        out[k] = {
            c.proposal.proposal_id: round(SCALE * c.proposal.value.as_dict()[k] / total)
            for c in candidates
            if c.proposal.value.as_dict()[k] > 0
        }
    return out


@dataclass
class SolvedItem:
    proposal_id: str
    sessions: list[tuple[datetime, datetime]]


@dataclass
class SolveResult:
    status: str
    scheduled: dict[str, SolvedItem] = field(default_factory=dict)
    unschedulable: dict[str, str] = field(default_factory=dict)  # proposal_id -> reason code
    evening_sessions: int = 0
    seconds: float = 0.0
    gains: dict[str, int] = field(default_factory=dict)  # G_k in permille


@dataclass
class _Session:
    day: int
    start: cp_model.IntVar | int
    end: cp_model.IntVar | int
    used: cp_model.IntVar  # presence literal


def _slot_of(horizon_start: datetime, t: datetime, *, ceil: bool = False) -> int:
    minutes = (t - horizon_start).total_seconds() / 60
    return math.ceil(minutes / SLOT_MIN) if ceil else math.floor(minutes / SLOT_MIN)


def _time_of(horizon_start: datetime, slot: int) -> datetime:
    return horizon_start + timedelta(minutes=slot * SLOT_MIN)


def _minute_slot(t) -> int:
    return (t.hour * 60 + t.minute) // SLOT_MIN


def solve(
    candidates: list[Candidate],
    profile: PlannerProfile,
    horizon_start: date,
    days: int,
    target: Optional[Target] = None,
    time_limit_s: float = 10.0,
    workers: int = 1,  # 1 = same plan every run (good for demos); raise for big problems
    locked: Optional[dict[str, list[tuple[datetime, datetime]]]] = None,
    not_before: Optional[datetime] = None,
    previous: Optional[dict[str, list[tuple[datetime, datetime]]]] = None,
) -> SolveResult:
    """Solve one planning problem.

    locked:     proposal_id -> sessions the user already accepted; kept exactly as they are
    not_before: nothing that is not locked may start before this moment
    previous:   proposal_id -> sessions in the plan being replaced; moving them costs a little,
                so a re-plan changes only what it has to
    """
    target = target or Target()
    if target.kind == "max" and target.objective not in OBJECTIVES:
        raise ValueError(f"kind='max' needs objective in {OBJECTIVES}")
    t0 = _time.perf_counter()
    hs = datetime.combine(horizon_start, datetime.min.time())
    n_slots = days * SLOTS_PER_DAY
    day_lo, day_hi = _minute_slot(profile.day_start), _minute_slot(profile.day_end)
    evening_slot = _minute_slot(profile.evening_after)
    locked = locked or {}
    previous = previous or {}
    stay_flags: list = []
    nb = max(0, _slot_of(hs, not_before, ceil=True)) if not_before else 0
    locked_load: dict[int, int] = {d: 0 for d in range(days)}

    m = cp_model.CpModel()
    result = SolveResult(status="UNKNOWN")

    x: dict[str, cp_model.IntVar] = {}
    sessions: dict[str, list[_Session]] = {}
    intervals: list = []
    per_day_load: dict[int, list] = {d: [] for d in range(days)}
    evening_flags: list = []
    session_flags: list = []

    # ---- busy blocks: fixed, always present
    for b in profile.busy_blocks:
        s = max(0, _slot_of(hs, b.start))
        e = min(n_slots, _slot_of(hs, b.end, ceil=True))
        if e > s:
            intervals.append(m.NewFixedSizeIntervalVar(s, e - s, f"busy_{s}_{e}"))

    for cand in candidates:
        p = cand.proposal
        pid = p.proposal_id
        xp = m.NewBoolVar(f"x_{pid}")
        x[pid] = xp
        sessions[pid] = []

        # ---- locked item: accepted earlier, keep its sessions exactly
        if pid in locked:
            m.Add(xp == 1)
            for a, b in locked[pid]:
                s = max(0, _slot_of(hs, a))
                e = min(n_slots, _slot_of(hs, b, ceil=True))
                if e <= s:
                    continue  # outside this horizon
                intervals.append(m.NewFixedSizeIntervalVar(s, e - s, f"lock_{pid}_{s}"))
                d = s // SLOTS_PER_DAY
                per_day_load[d].append(e - s)
                locked_load[d] += e - s
                sessions[pid].append(_Session(d, s, e, xp))
            continue

        # ---- fixed-time item
        if p.is_fixed:
            s = _slot_of(hs, p.fixed_time.start)
            e = _slot_of(hs, p.fixed_time.end, ceil=True)
            if s < 0 or e > n_slots:
                result.unschedulable[pid] = "outside_horizon"
                m.Add(xp == 0)
                continue
            if s < nb:
                result.unschedulable[pid] = "already_started"
                m.Add(xp == 0)
                continue
            intervals.append(m.NewOptionalFixedSizeIntervalVar(s, e - s, xp, f"iv_{pid}"))
            per_day_load[s // SLOTS_PER_DAY].append((e - s) * xp)
            sessions[pid].append(_Session(s // SLOTS_PER_DAY, s, e, xp))
            continue

        # ---- flexible item: at most one session per eligible day
        total = math.ceil(p.duration_min / SLOT_MIN)
        max_len = max(1, p.split.max_session_min // SLOT_MIN)
        min_len = min(total, max(1, math.ceil(p.split.min_session_min / SLOT_MIN)), max_len)
        first_day = max(0, (p.window.earliest - horizon_start).days)
        last_day = min(days - 1, (p.window.deadline - horizon_start).days)
        eligible = [
            d
            for d in range(first_day, last_day + 1)
            if (horizon_start + timedelta(days=d)).weekday() not in profile.free_weekdays
            and d * SLOTS_PER_DAY + day_hi - min_len >= nb  # still time left that day
        ]
        if not eligible or day_hi - day_lo < min_len or len(eligible) * min(max_len, day_hi - day_lo) < total:
            result.unschedulable[pid] = "no_free_time_in_window"
            m.Add(xp == 0)
            continue

        lengths = []
        for d in eligible:
            base = d * SLOTS_PER_DAY
            used = m.NewBoolVar(f"u_{pid}_{d}")
            m.AddImplication(used, xp)
            ln = m.NewIntVar(0, max_len, f"len_{pid}_{d}")
            m.Add(ln >= min_len).OnlyEnforceIf(used)
            m.Add(ln == 0).OnlyEnforceIf(used.Not())
            st = m.NewIntVar(max(base + day_lo, nb), base + day_hi - min_len, f"s_{pid}_{d}")
            en = m.NewIntVar(base + day_lo, base + day_hi, f"e_{pid}_{d}")
            m.Add(en == st + ln)
            intervals.append(m.NewOptionalIntervalVar(st, ln, en, used, f"iv_{pid}_{d}"))
            per_day_load[d].append(ln)
            lengths.append(ln)

            late = m.NewBoolVar(f"late_{pid}_{d}")
            m.Add(en <= base + evening_slot).OnlyEnforceIf(late.Not())
            m.AddImplication(late, used)
            evening_flags.append(late)
            session_flags.append(used)
            sessions[pid].append(_Session(d, st, en, used))
        m.Add(sum(lengths) == total * xp)

        # re-planning: reward keeping each previous session where it was
        by_day = {sess.day: sess for sess in sessions[pid]}
        for a, b in previous.get(pid, []):
            s0, e0 = _slot_of(hs, a), _slot_of(hs, b, ceil=True)
            sess = by_day.get(s0 // SLOTS_PER_DAY) if 0 <= s0 < n_slots else None
            if sess is None:
                continue
            stay = m.NewBoolVar(f"stay_{pid}_{s0}")
            m.Add(sess.start == s0).OnlyEnforceIf(stay)
            m.Add(sess.end == e0).OnlyEnforceIf(stay)
            m.AddImplication(stay, sess.used)
            stay_flags.append(stay)

    # ---- no overlap, daily cap
    m.AddNoOverlap(intervals)
    cap = profile.daily_cap_min // SLOT_MIN
    for d, terms in per_day_load.items():
        if terms:  # accepted items may already exceed a lowered cap; never make that infeasible
            m.Add(sum(terms) <= max(cap, locked_load[d]))

    # ---- dependencies and hard proposals
    for cand in candidates:
        q = cand.proposal
        for dep in q.depends_on:
            if dep not in x:
                continue  # prerequisite not proposed: assume it is already done
            m.AddImplication(x[q.proposal_id], x[dep])
            for sq in sessions[q.proposal_id]:
                for sp in sessions[dep]:
                    if sp.day > sq.day:  # prerequisite later than the dependent: not both
                        m.AddBoolOr([sq.used.Not(), sp.used.Not()])
                    elif sp.day == sq.day:
                        if isinstance(sq.start, int) and isinstance(sp.end, int):
                            if sq.start < sp.end:  # both fixed and in the wrong order
                                m.AddBoolOr([sq.used.Not(), sp.used.Not()])
                        else:
                            m.Add(sq.start >= sp.end).OnlyEnforceIf([sq.used, sp.used])
        if q.hard:
            m.Add(x[q.proposal_id] == 1)

    # ---- goals
    coeffs = gain_coefficients(candidates)
    gains: dict[str, cp_model.IntVar] = {}
    for k, ck in coeffs.items():
        g = m.NewIntVar(0, 2 * SCALE, f"gain_{k}")
        m.Add(g == sum(a * x[pid] for pid, a in ck.items() if pid in x))
        gains[k] = g
    for k, lo in target.lower.items():
        if k in gains and lo > 0:
            m.Add(gains[k] >= lo)

    tiebreak = (
        round(SCALE * profile.conflict_weight) * sum(evening_flags)
        + FRAGMENT_PENALTY * sum(session_flags)
        + MOVE_PENALTY * (len(stay_flags) - sum(stay_flags))
    )
    value = None  # goal part of the objective (minimised first)
    if target.kind == "max":  # payoff table only: no tie-breakers, the plan is never shown
        m.Maximize(gains.get(target.objective, 0))
    elif target.kind == "sum":
        m.Maximize(sum(gains.values()))
    elif gains:
        active = [k for k in (target.active or gains) if k in gains] or list(gains)
        terms = {}
        for k, g in gains.items():
            w = max(1, round(_ASF_W / max(1, target.ranges.get(k, SCALE))))
            terms[k] = w * (target.reference.get(k, SCALE) - g)
        bound = max(abs(_ASF_W) * 2 * SCALE, 1)
        worst = m.NewIntVar(-bound, bound, "asf_worst")
        for k in active:
            m.Add(worst >= terms[k])
        value = _ASF_RHO * worst + sum(terms.values())
        m.Minimize(value)
    else:
        m.Minimize(tiebreak)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.num_workers = workers
    solver.parameters.random_seed = 42
    status = solver.Solve(m)

    # Stage 2 (lexicographic): keep the goals exactly as good, then place sessions nicely
    # (fewer evenings, fewer pieces, fewer moves). Two short solves beat one big weighted one.
    if value is not None and status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        best = round(solver.ObjectiveValue())
        m.Add(value <= best)
        m.ClearHints()
        for i in range(len(m.Proto().variables)):
            m.AddHint(m.GetIntVarFromProtoIndex(i), solver.Value(m.GetIntVarFromProtoIndex(i)))
        m.Minimize(tiebreak)
        first = solver
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = max(1.0, time_limit_s / 2)
        solver.parameters.num_workers = workers
        solver.parameters.random_seed = 42
        status2 = solver.Solve(m)
        if status2 not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            solver = first  # cannot happen in theory; fall back to the stage-1 plan
        else:
            status = status2 if status2 == cp_model.FEASIBLE and status == cp_model.OPTIMAL else status
    result.status = solver.StatusName(status)
    result.seconds = _time.perf_counter() - t0

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return result

    for cand in candidates:
        p = cand.proposal
        pid = p.proposal_id
        if not solver.Value(x[pid]):
            continue
        if pid in locked:
            result.scheduled[pid] = SolvedItem(pid, sorted(locked[pid]))
            continue
        if p.is_fixed:  # report the real times, not the 30-minute grid
            result.scheduled[pid] = SolvedItem(pid, [(p.fixed_time.start, p.fixed_time.end)])
            continue
        out = [
            (_time_of(hs, solver.Value(s.start)), _time_of(hs, solver.Value(s.end)))
            for s in sessions[pid]
            if solver.Value(s.used)
        ]
        result.scheduled[pid] = SolvedItem(pid, sorted(out))
    result.evening_sessions = sum(solver.Value(f) for f in evening_flags)
    result.gains = {k: solver.Value(g) for k, g in gains.items()}
    return result
