import os
from pathlib import Path

import requests
from dotenv import load_dotenv

# Read settings from agents/career_agent/.env
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

# Shared team backend (uvicorn backend.main:app), Planner API is inside it
PLANNER_URL = os.getenv("PLANNER_URL", "http://127.0.0.1:8000")


def send_batch(plan_json):
    """Send one ProposalBatch (as JSON text) to the shared Planner API.

    Returns True if the Planner stored it. If the server is not running,
    we only print a warning: career_plan.json is still saved as a fallback.
    """
    url = f"{PLANNER_URL}/proposals/batch"
    try:
        r = requests.post(url, data=plan_json,
                          headers={"Content-Type": "application/json"}, timeout=15)
    except requests.RequestException as e:
        print(f"Planner API not reachable ({url}): {e}. Kept career_plan.json only.")
        return False
    if r.status_code != 201:
        print(f"Planner API refused the batch ({r.status_code}): {r.text[:500]}")
        return False
    print("Sent to Planner API:", r.json())
    return True