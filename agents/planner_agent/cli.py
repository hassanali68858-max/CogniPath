"""Run the Planner from the command line.

From the repository root:

    python -m agents.planner_agent.cli \
        --proposals tests/planner_agent/fixtures/mock_proposals.json \
        --career tests/planner_agent/fixtures/career_plan_sample.json \
        --profile tests/planner_agent/fixtures/mock_profile.json \
        --start 2026-11-02 --days 14
"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from .io import load_career_output, load_profile, load_proposals, to_ics
from .planner import make_plans
from .solver import MODES


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="CogniPath Planner")
    ap.add_argument("--proposals", type=Path, help="JSON list of ActivityProposal")
    ap.add_argument("--career", type=Path, help="career_plan.json from the Career Agent prototype")
    ap.add_argument("--profile", type=Path, required=True)
    ap.add_argument("--start", type=date.fromisoformat, required=True, help="first day, YYYY-MM-DD")
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--mode", choices=[*MODES, "all"], default="all")
    ap.add_argument("--ics", type=Path, help="write the balanced plan to this .ics file")
    ap.add_argument("--daily-cap", type=int, help="override the profile's daily limit (minutes) to test tight weeks")
    args = ap.parse_args(argv)

    profile = load_profile(args.profile)
    if args.daily_cap:
        profile = profile.model_copy(update={"daily_cap_min": args.daily_cap})
    proposals = load_proposals(args.proposals) if args.proposals else []
    if args.career:
        proposals += load_career_output(args.career, today=args.start, horizon_days=args.days, user_id=profile.user_id)

    modes = list(MODES) if args.mode == "all" else [args.mode]
    plans = make_plans(proposals, profile, args.start, args.days, modes=modes)

    for plan in plans:
        s = plan.scores
        print(f"\n=== {plan.mode.upper()}  ({plan.solver_status}, {plan.solve_seconds}s)")
        print(
            "loss  study {study:.0%}  career {career:.0%}  social {social:.0%}".format(**s.loss)
            + f"   fairness gap {s.fairness_gap:.0%}   evening sessions {s.soft_conflicts}"
            + f"   planned {s.scheduled_minutes / 60:.1f} h"
        )
        rows = sorted(
            [(sess.start, sess.end, item) for item in plan.items for sess in item.sessions],
            key=lambda r: r[:2],
        )
        for start, end, item in rows:
            print(f"  {start:%a %d %b %H:%M}-{end:%H:%M}  [{'+'.join(item.source_agents):>12}]  {item.title}")
        if plan.dropped:
            print("  dropped:")
            for d in plan.dropped:
                print(f"    - {d.title}: {d.explanation}")

    if args.ics:
        balanced = next((p for p in plans if p.mode == "balanced"), plans[0])
        args.ics.write_text(to_ics(balanced), encoding="utf-8")
        print(f"\nwrote {args.ics}")


if __name__ == "__main__":
    main()
