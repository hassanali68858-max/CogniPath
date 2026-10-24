"""Adapter: Career Agent prototype output -> ActivityProposal.

Elham's prototype (branch ``career-agent``, career_agent/src/career.py) writes
``career_plan.json`` shaped like::

    {
      "agent": "CareerAgent",
      "student": "ElhamPournouri",
      "goal": "GetAIInternship",
      "activities": [
        {"name": "Learn Docker", "target_opportunity": "AIInternship001",
         "learning_url": "https://docs.docker.com/get-started/",
         "estimated_duration_minutes": 180}
      ]
    }

That output has no deadline, score or id, so this adapter fills safe defaults.
Optional keys are already read if the Career Agent starts sending them:
``deadline`` (YYYY-MM-DD), ``priority`` (low/medium/high), ``value`` (dict),
``reason`` (str), ``missing_skill`` (str).

Delete this adapter once the Career Agent returns ActivityProposal directly.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any, Optional

from shared.contracts import (
    ActivityProposal,
    ActivityType,
    ObjectiveValue,
    Priority,
    SessionSplit,
    SourceAgent,
    TimeWindow,
)

DEFAULT_VALUE = {"study": 0.2, "career": 0.8, "social": 0.0}


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "item"


def _round_up_to_30(minutes: int) -> int:
    return max(30, -(-int(minutes) // 30) * 30)


def from_career_output(
    data: dict[str, Any],
    *,
    today: date,
    horizon_days: int = 14,
    user_id: Optional[str] = None,
) -> list[ActivityProposal]:
    """Convert one career_plan.json document into ActivityProposals."""
    if data.get("agent") not in (None, "CareerAgent", "career"):
        raise ValueError(f"not a Career Agent document: agent={data.get('agent')!r}")

    uid = user_id or data.get("student") or "unknown-user"
    goal = data.get("goal")
    default_deadline = today + timedelta(days=horizon_days - 1)

    proposals: list[ActivityProposal] = []
    seen: dict[str, int] = {}
    for activity in data.get("activities", []):
        name = activity["name"]
        target = activity.get("target_opportunity")
        base_id = f"career-{_slug(name)}-{_slug(target or 'general')}"
        seen[base_id] = seen.get(base_id, 0) + 1
        proposal_id = base_id if seen[base_id] == 1 else f"{base_id}-{seen[base_id]}"

        deadline = date.fromisoformat(activity["deadline"]) if activity.get("deadline") else default_deadline
        skill = activity.get("missing_skill") or name.removeprefix("Learn ").strip()
        reason = activity.get("reason") or (
            f"Missing skill '{skill}' for {target}" + (f" (goal: {goal})" if goal else "")
            if target
            else f"Supports career goal {goal}"
            if goal
            else "Suggested by the Career Agent"
        )

        proposals.append(
            ActivityProposal(
                proposal_id=proposal_id,
                source_agent=SourceAgent.CAREER,
                user_id=uid,
                type=ActivityType.LEARNING,
                title=name,
                opportunity_ref=target,
                resource_url=activity.get("learning_url"),
                duration_min=_round_up_to_30(activity.get("estimated_duration_minutes", 120)),
                window=TimeWindow(earliest=today, deadline=max(today, deadline)),
                split=SessionSplit(min_session_min=60, max_session_min=120),
                value=ObjectiveValue(**(activity.get("value") or DEFAULT_VALUE)),
                priority=Priority(activity.get("priority", "medium")),
                reason=reason,
            )
        )
    return proposals
