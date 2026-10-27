import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def make_activities(match):
    acts = []
    for m in match["missing"]:
        acts.append({
            "type": "learn",
            "name": f"Learn {m['skill']}",
            "resource": m["resource"],
            "duration_minutes": 180,
            "scores": {"academic": 0.5, "career": 0.8, "social": 0.0},
            "why": f"Needed for {match['title']}",    
        })
    acts.append({
        "type": "apply",
        "name": f"Apply: {match['title']}",
        "duration_minutes": 60,
        "scores": {"academic": 0.0, "career": match['score'], "social": 0.0},   
        "why": f"Match score {match['score']:.0%}",
    })
    return acts
def score_events(events, companies, missing_skills):
    acts = []
    for e in events:
        meets = [c for c in e["companies"] if c in companies]
        learns = [t for t in e["topics"] if t.replace(" ", "") in missing_skills]
        career = min(1.0, 0.6 * len(meets) + 0.2 * len(learns))
        acts.append({
            "type": "network",
            "name": f"Attend {e['name']}",
            "date": e["date"],
            "duration_minutes": 120,
            "scores": {"academic": 0.0, "career": round(career, 2), "social": 0.8},
            "why": (f"Meet {', '.join(meets)}. " if meets else "") + (f"Learn about {', '.join(learns)}." if learns else "") or "Social only, no career value",
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
    plan["activities"] += score_events(events, companies, missing_skills)

    for a in plan["activities"]:
        print(a["name"], "|", a["why"])
    (DATA_DIR / "career_plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
    print("Saved career_plan.json")