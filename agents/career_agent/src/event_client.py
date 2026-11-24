"""Read events from the Event Agent's API (the team's shared way for agents to talk).

If the Event Agent is not running or not configured, fall back to data/events.json,
so the Career Agent always works.
"""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

# Read settings from agents/career_agent/.env
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

# Event Agent API (python -m uvicorn agents.event_agent.api:app --port 8002)
EVENT_AGENT_URL = os.getenv("EVENT_AGENT_URL", "http://127.0.0.1:8002")
# A user or operator token from the Event Agent's EVENT_USER_TOKENS / EVENT_OPERATOR_TOKEN
EVENT_AGENT_TOKEN = os.getenv("EVENT_AGENT_TOKEN", "")
# Only events in the next DAYS_AHEAD days are useful for the plan
DAYS_AHEAD = 60
PAGE_SIZE = 200  # the largest page the Event Agent allows
EVENTS_FILE = Path(__file__).resolve().parents[1] / "data" / "events.json"


def from_event_agent(item):
    """Convert one Event Agent catalog entry into the format advisor.py uses."""
    e = item["event"]
    return {
        "id": item["id"],                       # Event Agent's own id: used as opportunity_ref
        "name": e["title"],
        "start": e.get("start"),                # ISO date and time with time zone
        "end": e.get("end"),
        "companies": [e["organizer"]] if e.get("organizer") else [],
        "topics": e.get("topics") or [],
        "url": e.get("url"),
        "location": ", ".join(x for x in (e.get("venue"), e.get("city")) if x) or None,
        "online": e.get("online"),
    }


def fetch_event_agent():
    """All upcoming events from GET /events, or None if the Event Agent cannot be used."""
    if not EVENT_AGENT_TOKEN:
        print("EVENT_AGENT_TOKEN is not set in .env: using data/events.json.")
        return None
    headers = {"Authorization": f"Bearer {EVENT_AGENT_TOKEN}"}
    now = datetime.now(timezone.utc)
    last = now + timedelta(days=DAYS_AHEAD)
    events, offset = [], 0
    try:
        while True:
            r = requests.get(f"{EVENT_AGENT_URL}/events", headers=headers,
                             params={"limit": PAGE_SIZE, "offset": offset}, timeout=15)
            r.raise_for_status()
            page = r.json()
            for item in page["events"]:
                e = item["event"]
                if e.get("cancelled") or not e.get("start"):
                    continue  # no time = cannot be put in a plan
                start = datetime.fromisoformat(e["start"].replace("Z", "+00:00"))
                if now <= start <= last:
                    events.append(from_event_agent(item))
            offset += page["limit"]
            if offset >= page["total"]:
                break
    except (requests.RequestException, KeyError, ValueError) as err:
        print(f"Event Agent not reachable ({EVENT_AGENT_URL}): {err}. Using data/events.json.")
        return None
    print(f"Events from the Event Agent: {len(events)} in the next {DAYS_AHEAD} days")
    return events


def load_events():
    """Events for the advisor: from the Event Agent if possible, else the sample file."""
    events = fetch_event_agent()
    if events is not None:
        return events
    return json.loads(EVENTS_FILE.read_text(encoding="utf-8"))
