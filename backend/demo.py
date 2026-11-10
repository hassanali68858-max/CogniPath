"""Demo helpers: load the mock student and proposals, or wipe a user's data.

These exist so the frontend can be tried without the real agents.
Remove or protect them before any real deployment.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi import APIRouter, HTTPException

from agents.planner_agent.api import Store
from agents.planner_agent.io import load_profile, load_proposals

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "planner_agent" / "fixtures"
DEMO_USER = "student001"
DEMO_START = date(2026, 11, 2)
DEMO_DAYS = 14
DEMO_DAILY_CAP = 120  # a tight fortnight, so the goals compete and trade-offs show up

router = APIRouter(prefix="/demo", tags=["demo"])


@router.get("/info")
def demo_info() -> dict:
    """What the demo data covers, so the frontend can prefill its forms."""
    return {"user_id": DEMO_USER, "horizon_start": DEMO_START.isoformat(), "days": DEMO_DAYS}


@router.post("/seed")
def seed(store: Store) -> dict:
    """Store the mock profile and proposals for student001.

    Event and Tutor proposals are mock data; the Career proposals are the real ProposalBatch
    written by the Career Agent (advisor.py), assigned to the demo student.
    """
    if not FIXTURES.exists():
        raise HTTPException(500, f"fixtures folder not found: {FIXTURES}")
    profile = load_profile(FIXTURES / "mock_profile.json").model_copy(update={"daily_cap_min": DEMO_DAILY_CAP})
    proposals = load_proposals(FIXTURES / "mock_proposals.json")
    proposals += [
        p.model_copy(update={"user_id": DEMO_USER}) for p in load_proposals(FIXTURES / "career_batch_sample.json")
    ]
    store.save_profile(profile)
    stored = store.upsert_proposals(proposals)
    return {"user_id": profile.user_id, "profile": "saved", "proposals": stored}


@router.post("/reset/{user_id}")
def reset(user_id: str, store: Store) -> dict:
    """Delete the user's profile, proposals, plans and decisions."""
    store.delete_user(user_id)
    return {"user_id": user_id, "deleted": True}
