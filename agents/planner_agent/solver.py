"""CP-SAT model for the Planner.

Minimise  sum_k lambda_k * L_k  +  lambda_f * C  +  mu * max_k L_k  (+ a small per-session penalty)

  L_k  loss of objective k (study, career, social): the share of proposed,
       priority-weighted value that is NOT scheduled (scaled to 0..1000)
  C    soft conflicts: flexible sessions that end after the evening cut-off
  mu   fairness ("nobody gets ignored"): penalises the worst-off objective

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

Time is a grid of 30-minute slots starting at horizon_start 00:00.
"""

from __future__ import annotations

import math
import time as _time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from ortools.sat.python import cp_model

from shared.contracts import ActivityProposal, PlannerProfile

SLOT_MIN = 30
SLOTS_PER_DAY = 24 * 60 // SLOT_MIN
OBJECTIVES = ("study", "career", "social")
LOSS_SCALE = 1000
FRAGMENT_PENALTY = 50  # per session used: prefer fewer, longer sessions; small next to dropping an item

MODES: dict[str, dict[str, float]] = {
    "balanced": {"study": 1.0, "career": 1.0, "social": 1.0},
    "study_first": {"study": 3.0, "career": 1.0, "social": 1.0},
    "career_first": {"study": 1.0, "career": 3.0, "social": 1.0},
}


@dataclass
class Candidate:
    """A proposal after merging, plus planner-side bookkeeping."""

    proposal: ActivityProposal
    source_agents: list[str]


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
    mode: str = "balanced",
    time_limit_s: float = 10.0,
    workers: int = 8,
) -> SolveResult:
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}; choose from {sorted(MODES)}")
    t0 = _time.perf_counter()
    hs = datetime.combine(horizon_start, datetime.min.time())
    n_slots = days * SLOTS_PER_DAY
    day_lo, day_hi = _minute_slot(profile.day_start), _minute_slot(profile.day_end)
    evening_slot = _minute_slot(profile.evening_after)

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

        # ---- fixed-time item
        if p.is_fixed:
            s = _slot_of(hs, p.fixed_time.start)
            e = _slot_of(hs, p.fixed_time.end, ceil=True)
            if s < 0 or e > n_slots:
                result.unschedulable[pid] = "outside_horizon"
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
            st = m.NewIntVar(base + day_lo, base + day_hi - min_len, f"s_{pid}_{d}")
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

    # ---- no overlap, daily cap
    m.AddNoOverlap(intervals)
    cap = profile.daily_cap_min // SLOT_MIN
    for terms in per_day_load.values():
        if terms:
            m.Add(sum(terms) <= cap)

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
                        m.Add(sq.start >= sp.end).OnlyEnforceIf([sq.used, sp.used])
        if q.hard:
            m.Add(x[q.proposal_id] == 1)

    # ---- objective
    mult = MODES[mode]
    weights = profile.weights.model_dump()
    losses = []
    obj_terms = []
    for k in OBJECTIVES:
        total_k = sum(c.proposal.value.as_dict()[k] * c.proposal.priority.weight for c in candidates)
        if total_k <= 0:
            continue
        coeffs = {
            c.proposal.proposal_id: round(
                LOSS_SCALE * c.proposal.value.as_dict()[k] * c.proposal.priority.weight / total_k
            )
            for c in candidates
        }
        loss_k = m.NewIntVar(0, LOSS_SCALE * 2, f"loss_{k}")
        m.Add(loss_k == sum(a * (1 - x[pid]) for pid, a in coeffs.items() if a))
        losses.append(loss_k)
        obj_terms.append(round(10 * weights[k] * mult[k]) * loss_k)

    if losses:
        worst = m.NewIntVar(0, LOSS_SCALE * 2, "worst_loss")
        m.AddMaxEquality(worst, losses)
        obj_terms.append(round(10 * profile.fairness_weight) * worst)
    obj_terms.append(round(LOSS_SCALE * profile.conflict_weight) * sum(evening_flags))
    obj_terms.append(FRAGMENT_PENALTY * sum(session_flags))
    m.Minimize(sum(obj_terms))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.num_workers = workers
    solver.parameters.random_seed = 42
    status = solver.Solve(m)
    result.status = solver.StatusName(status)
    result.seconds = _time.perf_counter() - t0

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return result

    for cand in candidates:
        p = cand.proposal
        pid = p.proposal_id
        if not solver.Value(x[pid]):
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
    return result
