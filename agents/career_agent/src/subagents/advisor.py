import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
ROOT = Path(__file__).resolve().parents[4]          # CogniPath-Team
sys.path.insert(0, str(ROOT))
from shared.contracts import ProposalBatch           # the team contract

TODAY = date.today()
# MAVT weights derived from swing weighting (100, 60, 40)
W1 = 0.5  # Company opportunity relevance
W2 = 0.3  # Skill gap coverage
W3 = 0.2  # Career goal alignment

# Temporary semantic links until we use career.owl
RELATED = {"LangGraph": "AI", "Machine Learning": "AI", "RDF": "AI"}


def c3_goal(topics, goal):
    best = 0.0
    for t in topics:
        if t == goal:
            best = max(best, 1.0)      # direct match
        elif RELATED.get(t) == goal:
            best = max(best, 0.5)      # indirect match
    return best

def make_id(kind, title):
    return "career-" + kind + "-" + re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def window(deadline=None):
    end = deadline or (TODAY + timedelta(days=30)).isoformat()
    return {"earliest": TODAY.isoformat(), "deadline": end}


def make_activities(match):
    acts = []
    for m in match["missing"]:
        title = f"Learn {m['skill']}"
        res = m.get("resource") or ""
        acts.append({
            "proposal_id": make_id("learning", title),
            "type": "learning",
            "title": title,
            "resource_url": res if res.startswith("http") else None,
            "opportunity_ref": None if res.startswith("http") else (res or None),
            "duration_min": 180,
            "window": window(match.get("deadline")),
            "value": {"study": 0.5, "career": 0.8, "social": 0.0},
            "reason": f"Needed for {match['title']}",
        })
    title = f"Apply: {match['title']}"
    acts.append({
        "proposal_id": make_id("application", title),
        "type": "application",
        "title": title,
        "opportunity_ref": match["title"],
        "duration_min": 60,
        "window": window(match.get("deadline")),
        "value": {"study": 0.0, "career": match["score"], "social": 0.0},
        "reason": f"Match score {match['score']:.0%}",
    })
    return acts


def social_score(event_topics, interests):
    if not event_topics:
        return 0.3
    matched = sum(1 for t in event_topics if t.lower() in interests)
    return 0.3 + 0.7 * matched / len(event_topics)


def score_events(events, companies, missing_skills, interests):
    acts = []
    for e in events:
        meets = [c for c in e["companies"] if c in companies]
        learns = [t for t in e["topics"] if t.replace(" ", "") in missing_skills]
        c1 = 1.0 if meets else 0.0                                         # company relevance
        c2 = len(learns) / len(missing_skills) if missing_skills else 0.0  # gap coverage
        c3 = c3_goal(e["topics"], "AI")                                    # goal relevance
        career = round(W1 * c1 + W2 * c2 + W3 * c3, 2)
        social = social_score(e["topics"], interests)
        start = datetime.fromisoformat(e["date"] + "T" + e.get("start", "17:00"))
        title = f"Attend {e['name']}"
        acts.append({
            "proposal_id": make_id("event", title),
            "type": "event",
            "title": title,
            "fixed_time": {"start": start.isoformat(), "end": (start + timedelta(minutes=120)).isoformat()},
            "location": e.get("location"),
            "value": {"study": 0.0, "career": round(career, 2), "social": round(social, 2)},
            "reason": (f"Meet {', '.join(meets)}. " if meets else "") + (f"Learn about {', '.join(learns)}." if learns else "") or "Social only, no career value",
        })
    return acts


if __name__ == "__main__":
    matches = json.loads((DATA_DIR / "matches.json").read_text(encoding="utf-8"))
    raw = json.loads((DATA_DIR / "raw_postings.json").read_text(encoding="utf-8"))
    events = json.loads((DATA_DIR / "events.json").read_text(encoding="utf-8"))
    profile = json.loads((DATA_DIR / "user_profile.json").read_text(encoding="utf-8"))

    user_id = profile.get("user_id", "demo-user")
    interests = [i.lower() for i in profile.get("interests", [])]
    companies = {p["company"] for p in raw}
    missing_skills = {m["skill"] for match in matches for m in match["missing"]}

    acts = []
    for match in matches:
        acts += make_activities(match)
    acts += score_events(events, companies, missing_skills, interests)

    for a in acts:
        a["source_agent"] = "career"
        a["user_id"] = user_id

    batch = ProposalBatch(source_agent="career", user_id=user_id,
                          generated_at=datetime.now(), proposals=acts)   # validates!

    for p in batch.proposals:
        print(p.title, "|", p.value.as_dict(), "|", p.reason)
    (DATA_DIR / "career_plan.json").write_text(batch.model_dump_json(indent=2), encoding="utf-8")
    print("Saved career_plan.json (ProposalBatch)")