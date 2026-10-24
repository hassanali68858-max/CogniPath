"""Loading helpers shared by the CLI, the API and the tests."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Optional

from pydantic import TypeAdapter

from shared.contracts import ActivityProposal, Plan, PlannerProfile

from .adapters.career import from_career_output

_proposals = TypeAdapter(list[ActivityProposal])


def load_proposals(path: str | Path) -> list[ActivityProposal]:
    return _proposals.validate_json(Path(path).read_text(encoding="utf-8"))


def load_profile(path: str | Path) -> PlannerProfile:
    return PlannerProfile.model_validate_json(Path(path).read_text(encoding="utf-8"))


def load_career_output(
    path: str | Path, *, today: date, horizon_days: int, user_id: Optional[str] = None
) -> list[ActivityProposal]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return from_career_output(data, today=today, horizon_days=horizon_days, user_id=user_id)


def to_ics(plan: Plan) -> str:
    """Minimal iCalendar export of a plan (import into Outlook / Google Calendar)."""
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//CogniPath//Planner//EN"]
    for item in plan.items:
        for i, s in enumerate(item.sessions):
            lines += [
                "BEGIN:VEVENT",
                f"UID:{item.item_id}-{i}@cognipath",
                f"DTSTART:{s.start:%Y%m%dT%H%M%S}",
                f"DTEND:{s.end:%Y%m%dT%H%M%S}",
                f"SUMMARY:{item.title}",
                "DESCRIPTION:" + item.explanation.replace(",", "\\,").replace(";", "\\;"),
                "END:VEVENT",
            ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
