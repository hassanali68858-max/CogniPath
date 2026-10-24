from datetime import date, datetime, time, timedelta

from agents.planner_agent.planner import approved_as_busy, make_plan, make_plans, merge_duplicates
from shared.contracts import ActivityProposal, BusyBlock, ItemDecision, PlannerProfile

from .conftest import DAYS, START


def _all_sessions(plan):
    return [(s.start, s.end, i) for i in plan.items for s in i.sessions]


def test_mock_week_solves_fast_and_optimal(proposals, profile):
    plan = make_plan(proposals, profile, START, DAYS)
    assert plan.solver_status == "OPTIMAL"
    assert plan.solve_seconds < 2


def test_no_overlaps_with_each_other_or_busy_blocks(proposals, profile):
    plan = make_plan(proposals, profile, START, DAYS)
    spans = [(s, e) for s, e, _ in _all_sessions(plan)] + [(b.start, b.end) for b in profile.busy_blocks]
    spans.sort()
    for (s1, e1), (s2, e2) in zip(spans, spans[1:]):
        assert e1 <= s2, f"overlap {s1}-{e1} and {s2}-{e2}"


def test_flexible_sessions_respect_window_day_hours_and_cap(proposals, profile):
    plan = make_plan(proposals, profile, START, DAYS)
    by_id = {p.proposal_id: p for p in proposals}
    per_day: dict[date, int] = {}
    for s, e, item in _all_sessions(plan):
        per_day[s.date()] = per_day.get(s.date(), 0) + int((e - s).total_seconds() // 60)
        p = by_id[item.proposal_id]
        if p.is_fixed:
            continue
        assert p.window.earliest <= s.date() <= p.window.deadline
        assert s.time() >= profile.day_start and e.time() <= profile.day_end and e.date() == s.date()
    assert max(per_day.values()) <= profile.daily_cap_min + 30  # +30: fixed events are rounded to the grid


def test_hard_item_and_dependencies(proposals, profile):
    plan = make_plan(proposals, profile, START, DAYS)
    items = {i.proposal_id: i for i in plan.items}
    assert "tut-exam-review" in items  # hard
    for after, before in [("tut-quiz-kg", "tut-read-rdf"), ("car-apply-trainee", "car-update-cv")]:
        if after in items:
            assert before in items
            assert items[after].sessions[0].start >= items[before].sessions[-1].end


def test_career_fair_from_two_agents_is_merged(proposals, profile):
    cands = merge_duplicates(proposals)
    fair = [c for c in cands if c.proposal.opportunity_ref == "event:jyu-career-fair-2026"]
    assert len(fair) == 1
    assert fair[0].source_agents == ["event", "career"]
    assert fair[0].proposal.value.career == 0.9 and fair[0].proposal.value.social == 0.5


def test_dropped_items_are_explained(proposals, profile):
    plan = make_plan(proposals, profile, START, DAYS)
    dropped = {d.proposal_id: d.explanation for d in plan.dropped}
    assert "Work shift" in dropped["evt-boardgames"]
    assert "Algorithms exam review" in dropped["evt-sauna"]
    assert all(dropped.values())


def test_roomy_week_fits_all_study_and_career_work(proposals, profile):
    plan = make_plan(proposals, profile, START, DAYS)
    assert plan.scores.loss["study"] == 0 and plan.scores.loss["career"] == 0
    assert {d.proposal_id for d in plan.dropped} == {"evt-boardgames", "evt-sauna"}


def test_tight_week_modes_trade_objectives(proposals, profile):
    tight = profile.model_copy(update={"daily_cap_min": 120})
    plans = {p.mode: p for p in make_plans(proposals, tight, START, DAYS)}
    assert all(p.solver_status == "OPTIMAL" for p in plans.values())
    assert plans["study_first"].scores.loss["study"] < plans["balanced"].scores.loss["study"]
    assert plans["study_first"].scores.loss["career"] > plans["balanced"].scores.loss["career"]
    assert plans["career_first"].scores.loss["career"] <= plans["balanced"].scores.loss["career"]


def test_flexible_work_is_split_one_session_per_day(proposals, profile):
    plan = make_plan(proposals, profile, START, DAYS)
    by_id = {p.proposal_id: p for p in proposals}
    for item in plan.items:
        p = by_id[item.proposal_id]
        if p.is_fixed:
            continue
        days = [s.start.date() for s in item.sessions]
        assert len(days) == len(set(days))
        lengths = [int((s.end - s.start).total_seconds() // 60) for s in item.sessions]
        assert sum(lengths) == p.duration_min
        assert all(p.split.min_session_min <= m <= p.split.max_session_min for m in lengths)


def test_event_longer_than_daily_limit_is_explained(proposals, profile):
    tight = profile.model_copy(update={"daily_cap_min": 150})
    plan = make_plan(proposals, tight, START, DAYS)
    dropped = {d.proposal_id: d.explanation for d in plan.dropped}
    assert "more than your daily limit" in dropped["evt-hackathon"]


def _fixed(pid, start_h, end_h, value, **kw):
    d = date(2026, 11, 2)
    return ActivityProposal(
        proposal_id=pid,
        source_agent="event",
        user_id="u",
        type="event",
        title=pid,
        fixed_time={"start": datetime.combine(d, time(start_h)), "end": datetime.combine(d, time(end_h))},
        value=value,
        reason="test",
        **kw,
    )


def test_overlap_keeps_higher_value():
    profile = PlannerProfile(user_id="u")
    plan = make_plan(
        [_fixed("low", 10, 12, {"study": 0.3}), _fixed("high", 11, 13, {"study": 0.9})],
        profile,
        date(2026, 11, 2),
        1,
    )
    assert [i.proposal_id for i in plan.items] == ["high"]
    assert "Overlaps with 'high'" in plan.dropped[0].explanation


def test_hard_item_clashing_with_busy_is_infeasible():
    d = date(2026, 11, 2)
    profile = PlannerProfile(
        user_id="u",
        busy_blocks=[BusyBlock(title="Lecture", start=datetime(2026, 11, 2, 10), end=datetime(2026, 11, 2, 12))],
    )
    plan = make_plan([_fixed("exam", 11, 12, {"study": 1.0}, hard=True)], profile, d, 1)
    assert plan.solver_status == "INFEASIBLE"
    assert plan.dropped and "hard items" in plan.dropped[0].explanation


def test_window_only_on_free_weekday_is_unschedulable():
    sunday = date(2026, 11, 8)
    profile = PlannerProfile(user_id="u", free_weekdays=[6])
    p = ActivityProposal(
        proposal_id="sun",
        source_agent="tutor",
        user_id="u",
        type="learning",
        title="Sunday reading",
        duration_min=60,
        window={"earliest": sunday, "deadline": sunday},
        value={"study": 0.5},
        reason="test",
    )
    plan = make_plan([p], profile, sunday - timedelta(days=6), 7)
    assert plan.items == []
    assert "no free slot" in plan.dropped[0].explanation


def test_approved_items_become_busy_blocks(proposals, profile):
    plan = make_plan(proposals, profile, START, DAYS)
    plan.items[0].decision = ItemDecision.ACCEPTED
    busy = approved_as_busy(plan)
    assert len(busy) == len(plan.items[0].sessions)
    assert busy[0].title.startswith("[approved]")
