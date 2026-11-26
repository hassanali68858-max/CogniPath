"""Small builders shared by both sub-agents."""

from __future__ import annotations

import math
from datetime import date

from shared.contracts import SessionSplit, TimeWindow

PLANNER_SLOT_MIN = 30
SINGLE_SESSION = SessionSplit(min_session_min=30, max_session_min=30)


def window_until(today: date, deadline: date) -> TimeWindow:
    return TimeWindow(earliest=today, deadline=max(today, deadline))


def round_up_to_slot(minutes: int) -> int:
    return max(PLANNER_SLOT_MIN, math.ceil(minutes / PLANNER_SLOT_MIN) * PLANNER_SLOT_MIN)
