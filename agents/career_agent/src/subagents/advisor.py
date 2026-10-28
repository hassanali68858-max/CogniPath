import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from rdflib import Graph, Namespace
from rdflib.namespace import SKOS

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
ROOT = Path(__file__).resolve().parents[4]          # CogniPath-Team
sys.path.insert(0, str(ROOT))
from shared.contracts import ProposalBatch           # the team contract

TODAY = date.today()

# Event career weights (swing weighting: 100, 60, 40)
W1 = 0.5  # Company opportunity relevance
W2 = 0.3  # Skill gap coverage
W3 = 0.2  # Career goal alignment

# Learning activity weights (swing weighting: goal 100, gap closure 60)
WL1 = 0.375  # Gap closure for the opportunity
WL2 = 0.625  # Career goal relevance

CAREER = Namespace("https://example.org/cognipath/career#")
ONTO_DIR = Path(__file__).resolve().parents[2] / "ontology"
HIER = Graph().parse(ONTO_DIR / "skill_hierarchy.ttl")


def distance(skill, target):
    """Number of skos:broader steps from skill up to target, or None."""
    start, goal = CAREER[skill.replace(" ", "")], CAREER[target]
    level, seen, step = [start], {start}, 0
    while level:
        if goal in level:
            return step
        nxt = []
        for node in level:
            for parent in HIER.objects(node, SKOS.broader):
                if parent not in seen:
                    seen.add(parent)
                    nxt.append(parent)
        level, step = nxt, step + 1
    return None


def relevance(skill, target):
    """Turn graph distance into a 0-1 score (closer = more relevant)."""
    d = distance(skill, target)
    if d is None:
        return 0.0
    return {0: 1.0, 1: 0.6}.get(d, 0.3)


def c3_goal(topics, goal):
    return max((relevance(t, goal) for t in topics), default=0.0)


def make_id(kind, title):
    return "career-" + kind + "-" + re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def window(deadline=None):
    end = deadline or (TODAY + timedelta(days=30)).isoformat()
    return {"earliest": TODAY.isoformat(), "deadline": end}


def norm(text):
    return text.lower().replace(" ", "")


def study_score(skill, profile):
    s = norm(skill)
    concepts = profile.get("thesis_concepts", [])
    d = min((x for x in (distance(skill, c) for c in concepts) if x is not None), default=None)
    if s in norm(profile.get("thesis_topic", "")) or d == 0:
        return 0.9                                   # the thesis concept itself
    if d == 1 or any(s == norm(c) for c in profile.get("courses", [])):
        return 0.6                                   # one step from the thesis, or a course
    return 0.3                                       # general skill


def learn_career(skill, match, goal):
    l1 = 1 / len(match["missing"])        # share of the skill gap this closes
    l2 = relevance(skill, goal)           # ontology distance to the career goal
    return round(WL1 * l1 + WL2 * l2, 2)


def make_activities(match, profile, goal):
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
            "value": {"study": study_score(m["skill"], profile),
                      "career": learn_career(m["skill"], match, goal),
                      "social": 0.0},
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


def score_events(events, companies, missing_skills, interests, goal):
    acts = []
    for e in events:
        meets = [c for c in e["companies"] if c in companies]
        learns = [t for t in e["topics"] if t.replace(" ", "") in missing_skills]
        c1 = 1.0 if meets else 0.0                                         # company relevance
        c2 = len(learns) / len(missing_skills) if missing_skills else 0.0  # gap coverage
        c3 = c3_goal(e["topics"], goal)                                    # goal relevance
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
            "value": {"study": 0.0, "career": career, "social": round(social, 2)},
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
    goal = profile.get("career_goal", "AI")
    companies = {p["company"] for p in raw}
    missing_skills = {m["skill"] for match in matches for m in match["missing"]}

    acts = []
    for match in matches:
        acts += make_activities(match, profile, goal)
    acts += score_events(events, companies, missing_skills, interests, goal)

    for a in acts:
        a["source_agent"] = "career"
        a["user_id"] = user_id

    batch = ProposalBatch(source_agent="career", user_id=user_id,
                          generated_at=datetime.now(), proposals=acts)   # validates!

    for p in batch.proposals:
        print(p.title, "|", p.value.as_dict(), "|", p.reason)
    (DATA_DIR / "career_plan.json").write_text(batch.model_dump_json(indent=2), encoding="utf-8")
    print("Saved career_plan.json (ProposalBatch)")