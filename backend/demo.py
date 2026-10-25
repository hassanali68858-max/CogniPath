"""Demo helpers: load the mock student and proposals, or wipe a user's data.

These exist so the frontend can be tried without the real agents.
Remove or protect them before any real deployment.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi import APIRouter, HTTPException

from agents.planner_agent.api import Store
from agents.planner_agent.io import load_career_output, load_profile, load_proposals

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "planner_agent" / "fixtures"
DEMO_USER = "student001"
DEMO_START = date(2026, 11, 2)
DEMO_DAYS = 14

router = APIRouter(prefix="/demo", tags=["demo"])


@router.get("/info")
def demo_info() -> dict:
    """What the demo data covers, so the frontend can prefill its forms."""
    return {"user_id": DEMO_USER, "horizon_start": DEMO_START.isoformat(), "days": DEMO_DAYS}


@router.post("/seed")
def seed(store: Store) -> dict:
    """Store the mock profile and proposals (Event, Tutor, Career incl. Elham's sample) for student001."""
    if not FIXTURES.exists():
        raise HTTPException(500, f"fixtures folder not found: {FIXTURES}")
    profile = load_profile(FIXTURES / "mock_profile.json")
    proposals = load_proposals(FIXTURES / "mock_proposals.json")
    proposals += load_career_output(
        FIXTURES / "career_plan_sample.json", today=DEMO_START, horizon_days=DEMO_DAYS, user_id=DEMO_USER
    )
    store.save_profile(profile)
    stored = store.upsert_proposals(proposals)
    return {"user_id": profile.user_id, "profile": "saved", "proposals": stored}


@router.post("/reset/{user_id}")
def reset(user_id: str, store: Store) -> dict:
    """Delete the user's profile, proposals, plans and decisions."""
    store.delete_user(user_id)
    return {"user_id": user_id, "deleted": True}
