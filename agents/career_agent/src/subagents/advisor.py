import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def make_activities(match):
    acts = []
    for m in match["missing"]:
        acts.append({
            "type": "learning",
            "title": f"Learn {m['skill']}",
            "resource": m["resource"],
            "duration_min": 180,
            "value": {"study": 0.5, "career": 0.8, "social": 0.0},
            "reason": f"Needed for {match['title']}",
        })
    acts.append({
        "type": "application",
        "title": f"Apply: {match['title']}",
        "duration_min": 60,
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
        career = min(1.0, 0.6 * len(meets) + 0.2 * len(learns))
        social = social_score(e["topics"], interests)
        acts.append({
            "type": "event",
            "title": f"Attend {e['name']}",
            "date": e["date"],
            "duration_min": 120,
            "value": {"study": 0.0, "career": round(career, 2), "social": round(social, 2)},
            "reason": (f"Meet {', '.join(meets)}. " if meets else "") + (f"Learn about {', '.join(learns)}." if learns else "") or "Social only, no career value",
        })
    return acts


if __name__ == "__main__":
    matches = json.loads((DATA_DIR / "matches.json").read_text(encoding="utf-8"))
    plan = {"agent": "career", "activities": []}
    for match in matches:
        plan["activities"] += make_activities(match)

    raw = json.loads((DATA_DIR / "raw_postings.json").read_text(encoding="utf-8"))
    companies = {p["company"] for p in raw}
    missing_skills = {m["skill"] for match in matches for m in match["missing"]}
    events = json.loads((DATA_DIR / "events.json").read_text(encoding="utf-8"))
    profile = json.loads((DATA_DIR / "user_profile.json").read_text(encoding="utf-8"))
    interests = [i.lower() for i in profile.get("interests", [])]
    plan["activities"] += score_events(events, companies, missing_skills, interests)

    for a in plan["activities"]:
        print(a["title"], "|", a["value"], "|", a["reason"])
    (DATA_DIR / "career_plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
    print("Saved career_plan.json")