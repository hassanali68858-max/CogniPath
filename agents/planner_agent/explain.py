"""Template explanations for plan items (no LLM needed).

An LLM can later rewrite these into friendlier text, but the facts (what was
dropped and what it lost to) always come from here, so they stay correct.
"""

from __future__ import annotations

from datetime import datetime

from shared.contracts import PlannerProfile

from .solver import Candidate, SolveResult


def _fmt(t: datetime) -> str:
    return t.strftime("%a %d %b %H:%M")


def _weighted(c: Candidate) -> float:
    return sum(c.proposal.value.as_dict().values()) * c.proposal.priority.weight


def explain_scheduled(c: Candidate, sessions: list[tuple[datetime, datetime]]) -> str:
    p = c.proposal
    minutes = sum(int((e - s).total_seconds() // 60) for s, e in sessions)
    if p.is_fixed:
        when = f"fixed time {_fmt(sessions[0][0])}"
    else:
        when = f"{len(sessions)} session(s), {minutes} min, done before {p.window.deadline:%a %d %b}"
    by = " + ".join(c.source_agents)
    return f"{p.reason}. Proposed by {by}; {when}."


def explain_dropped(
    c: Candidate,
    result: SolveResult,
    by_id: dict[str, Candidate],
    profile: PlannerProfile,
) -> str:
    p = c.proposal
    code = result.unschedulable.get(p.proposal_id)
    if code == "outside_horizon":
        return "Falls outside the planning period."
    if code == "no_free_time_in_window":
        return "There is no free slot inside its time window and your day hours."

    missing = [d for d in p.depends_on if d in by_id and d not in result.scheduled]
    if missing:
        names = ", ".join(by_id[d].proposal.title for d in missing)
        return f"Needs '{names}' first, which is not in this plan."

    if p.is_fixed:
        s, e = p.fixed_time.start, p.fixed_time.end
        for b in profile.busy_blocks:
            if b.start < e and s < b.end:
                return f"Clashes with your fixed commitment '{b.title}'."
        if p.total_minutes > profile.daily_cap_min:
            return f"Takes {p.total_minutes / 60:g} h, more than your daily limit of {profile.daily_cap_min / 60:g} h."
        # only other fixed events are real rivals: flexible work could have moved
        rivals = [
            by_id[pid]
            for pid, item in result.scheduled.items()
            if by_id[pid].proposal.is_fixed and any(a < e and s < b for a, b in item.sessions)
        ]
        if rivals:
            best = max(rivals, key=_weighted)
            return (
                f"Overlaps with '{best.proposal.title}' ({_fmt(s)}), which scores higher on your current goal weights."
            )
        same_day = [
            (by_id[pid], sum(int((b - a).total_seconds() // 60) for a, b in item.sessions if a.date() == s.date()))
            for pid, item in result.scheduled.items()
        ]
        same_day = [(c, mins) for c, mins in same_day if mins]
        used = sum(mins for _, mins in same_day)
        if used + p.total_minutes > profile.daily_cap_min:
            same_day.sort(key=lambda cm: _weighted(cm[0]), reverse=True)
            names = ", ".join(f"'{c.proposal.title}'" for c, _ in same_day[:2])
            return (
                f"{s:%a %d %b} would exceed your daily limit of {profile.daily_cap_min / 60:g} h; "
                f"that day's time went to higher-value items such as {names}."
            )
        return "Left out to balance your goals across the period."

    # flexible: who used the window?
    lo = datetime.combine(p.window.earliest, datetime.min.time())
    hi = datetime.combine(p.window.deadline, datetime.max.time())
    rivals = [by_id[pid] for pid, item in result.scheduled.items() if any(a < hi and lo < b for a, b in item.sessions)]
    rivals.sort(key=_weighted, reverse=True)
    if rivals:
        names = ", ".join(f"'{r.proposal.title}'" for r in rivals[:2])
        return (
            f"Not enough free time before {p.window.deadline:%a %d %b}; "
            f"that time went to higher-value items such as {names}."
        )
    return "Left out to balance your goals within your daily limit."
