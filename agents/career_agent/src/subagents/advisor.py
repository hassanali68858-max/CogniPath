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
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # src/, for esco.py
from esco import map_to_esco, get_occupation, esco_relevance
from db import load_user_profile
TODAY = date.today()

# Event career weights (swing weighting: 100, 60, 40)
W1 = 0.5  # Company opportunity relevance
W2 = 0.3  # Skill gap coverage
W3 = 0.2  # Career goal alignment

# Learning activity weights (swing weighting: goal 100, gap closure 60)
WL1 = 0.375  # Gap closure for the opportunity
WL2 = 0.625  # Career goal relevance
# Apply only when enough required skills match
MIN_APPLY = 0.40     # at least 40% skill match
KEEP_AT_LEAST = 3    # if no job reaches 40%, still show the best 3

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


_goal_occ = {}


def goal_occupation(goal):
    """Map the career goal text to an ESCO occupation once and keep it."""
    if goal not in _goal_occ:
        found = map_to_esco(goal, kind="occupation")
        _goal_occ[goal] = get_occupation(found[1]) if found else None
    return _goal_occ[goal]


def relevance(skill, goal):
    """ESCO relevance of a skill for the career goal: 1.0 / 0.6 / 0.3 / 0."""
    occ = goal_occupation(goal)
    # Graph names like "MachineLearning" -> "Machine Learning" for the ESCO search
    name = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", skill)
    found = map_to_esco(name)
    if occ is None or found is None:
        return 0.0
    return esco_relevance(found[1], occ)


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

def apply_career(match, goal):
    a1 = match["score"]                                                  # readiness (skill match)
    a2 = max((relevance(s, goal) for s in match.get("required", [])), default=0.0)  # goal fit
    # Multiply by readiness: a job you have no skills for gets no career value
    return round(a1 * (WL1 + WL2 * a2), 2)

def apply_reason(match, goal, interests):
    """Rule-based trade-off: what you have, what is missing, why still apply."""
    missing = [m["skill"] for m in match["missing"]]
    shared = [s for s in match.get("required", []) if s not in missing]
    parts = [f"Match {match['score']:.0%}."]
    parts.append("You have: " + (", ".join(shared) if shared else "none") + ".")
    if missing:
        parts.append("Missing: " + ", ".join(missing) + ".")
    # Reasons to apply anyway
    why = []
    if apply_career(match, goal) > 0.7 * match["score"] > 0:
        why.append(f"fits your goal '{goal}'")
    if any(i in match["title"].lower() for i in interests):
        why.append("matches your interests")
    if 0 < len(missing) <= 2:
        why.append("only a few skills to learn")
    if why:
        parts.append("Worth applying: " + ", ".join(why) + ".")
    return " ".join(parts)



def llm_reason(match, goal, rule_text):
    """Ask the LLM for a short, friendly explanation of one top job.
    The score is decided by code; the LLM only explains it.
    Only job title, company, score and skill names are sent (no CV, no contact info).
    Falls back to the rule-based text if anything goes wrong."""
    try:
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # src/
        from llm import ask_llm

        missing = [m["skill"] for m in match["missing"]]
        shared = [s for s in match.get("required", []) if s not in missing]
        prompt = f"""Explain in 2-3 short, friendly sentences why this job could fit a job seeker.
Use ONLY the facts below. Do not invent skills, numbers or company details.
Do not change the match score. Mention one or two skills to learn if some are missing.
Write in plain English, second person ("you"). No lists, no headings.

Job title: {match["title"]}
Company: {match.get("company", "unknown")}
Match score: {match["score"]:.0%}
Skills you already have: {", ".join(shared) or "none"}
Skills missing: {", ".join(missing) or "none"}
Career goal: {goal or "not given"}
"""
        answer = ask_llm(prompt).strip()
        if not answer:
            return rule_text
        # Code adds the real score, so the UI never depends on the LLM writing it
        return f"Match {match['score']:.0%}. {answer}"
    except Exception:
        return rule_text  # LLM down or error: keep the rule-based text
    
def make_activities(match, profile, goal, use_llm=False):
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
    interests = [i.lower() for i in profile.get("interests") or []]
    # Rule-based explanation: always computed, used as fallback
    rule_text = apply_reason(match, goal, interests)
    acts.append({
        "proposal_id": make_id("application", title),
        "type": "application",
        "title": title,
        "opportunity_ref": match["title"],
        "duration_min": 60,
        "window": window(match.get("deadline")),
        "value": {"study": 0.0, "career": apply_career(match, goal), "social": 0.0},
        # Top jobs get a friendly LLM explanation; score stays from code
        "reason": llm_reason(match, goal, rule_text) if use_llm else rule_text,
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
     # Usage: python subagents\advisor.py <user_id>
    user_id = sys.argv[1] if len(sys.argv) > 1 else input("User ID: ").strip()
    profile = load_user_profile(user_id)
    if profile is None:
        sys.exit(f"No profile for {user_id!r}. Fill in the form first: streamlit run onboarding.py")
    interests = [i.lower() for i in profile.get("interests") or []]
    goal = profile.get("target_title") or ""  # no goal given: do not guess one
    companies = {p["company"] for p in raw}
    missing_skills = {m["skill"] for match in matches for m in match["missing"]}

    acts = []
    # Best matches first
    matches.sort(key=lambda m: m["score"], reverse=True)
    # Keep jobs with enough match; if none, keep the best few so the plan is not empty
    good = [m for m in matches if m["score"] >= MIN_APPLY] or matches[:KEEP_AT_LEAST]
    skipped = len(matches) - len(good)
    goal_words = set(goal.lower().split()) | set(interests)
    llm_used = 0  # how many top jobs got an LLM explanation
    for match in good:
        missing = {m["skill"] for m in match["missing"]}
        shared = [s for s in match.get("required", []) if s not in missing]
        # Whole words only, so "ai" does not match "maintenance"
        title_words = set(re.findall(r"[a-z]+", match["title"].lower()))
        # Skip jobs with no shared skill and no link to goal/interests
        if not shared and not (title_words & goal_words):
            skipped += 1
            continue
        # Only the top 3 kept jobs (good is sorted by score) use the LLM
        use_llm = llm_used < 3
        acts += make_activities(match, profile, goal, use_llm=use_llm)
        if use_llm:
            llm_used += 1
    print(f"Skipped jobs (below {MIN_APPLY:.0%} or unrelated):", skipped)
    acts += score_events(events, companies, missing_skills, interests, goal)
        
    for a in acts:
        a["source_agent"] = "career"
        a["user_id"] = user_id
    print("Activities built:", len(acts))

    batch = ProposalBatch(source_agent="career", user_id=user_id,
                          generated_at=datetime.now(), proposals=acts)   # validates!
    print("Activities in batch:", len(batch.proposals))

    for p in batch.proposals:
        print(p.title, "|", p.value.as_dict(), "|", p.reason)
    plan_json = batch.model_dump_json(indent=2)
    # Shared file: the team's Planner agent reads this one, keep the name
    (DATA_DIR / "career_plan.json").write_text(plan_json, encoding="utf-8")
    # Per-user file: so plans of different users do not overwrite each other
    (DATA_DIR / f"career_plan_{user_id}.json").write_text(plan_json, encoding="utf-8")
    print(f"Saved career_plan.json and career_plan_{user_id}.json (ProposalBatch)")