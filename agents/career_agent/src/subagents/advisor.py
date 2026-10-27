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
            "why": f"Needed for {match['title']}",      # توضیح: چرا این مهارت را یاد بگیری؟ (اسم آگهی را بیاور)
        })
    acts.append({
        "type": "apply",
        "name": f"Apply: {match['title']}",
        "duration_minutes": 60,
        "scores": {"academic": 0.0, "career": match['score'], "social": 0.0},   # هرچه تطابق بیشتر، ارزش اپلای بیشتر
        "why": f"Match score {match['score']:.0%}",
    })
    return acts


if __name__ == "__main__":
    matches = json.loads((DATA_DIR / "matches.json").read_text(encoding="utf-8"))
    plan = {"agent": "career", "activities": []}
    for match in matches:
        plan["activities"] += make_activities(match)
    for a in plan["activities"]:
        print(a["name"], "|", a["why"])
    (DATA_DIR / "career_plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
    print("Saved career_plan.json")