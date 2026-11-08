import json
from pathlib import Path

from rdflib import Graph, Namespace
from collections import Counter
import sys
import logging
logging.getLogger("rdflib").setLevel(logging.ERROR)  # hide harmless URI warnings
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # src/, for db.py
from db import save_matches, latest_cv_skills, load_postings, load_user_profile
from esco import skills_to_uris

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
CAREER = Namespace("https://example.org/cognipath/career#")



REQUIRED_SKILLS = """
PREFIX career: <https://example.org/cognipath/career#>
SELECT ?opp ?title ?skill WHERE {
    ?opp career:jobTitle ?title ;
         career:requiresSkill ?skill .
}
"""

RESOURCES = """
PREFIX career: <https://example.org/cognipath/career#>
SELECT ?skill ?res ?url WHERE {
    ?res career:helpsLearnSkill ?skill .
    OPTIONAL { ?res career:resourceURL ?url }
}
"""


def short(iri):
    return str(iri).split("#")[1]


if __name__ == "__main__":
    g = Graph()
    g.parse(DATA_DIR / "career_graph.ttl")
        # Usage: python subagents\matcher.py <user_id>
    user_id = sys.argv[1] if len(sys.argv) > 1 else input("User ID: ").strip()
    profile = load_user_profile(user_id)
    if profile is None:
        sys.exit(f"No profile for {user_id!r}. Fill in the form first: streamlit run onboarding.py")
    user = CAREER[profile["user_id"]]
    have = set(g.objects(user, CAREER.hasSkill))   # skills of the profile's student
    # Use the original CV skill names (readable) for ESCO; fall back to graph names
    cv_skills = latest_cv_skills(profile["user_id"])
    have_uris = skills_to_uris(cv_skills or [short(s) for s in have])
    # Simple names without spaces/case, e.g. "Deep Learning" -> "deeplearning"
    def squash(text):
        return "".join(c for c in text.lower() if c.isalnum())
    have_names = {squash(n) for n in (cv_skills or [short(s) for s in have])}
        # Stems of one-word CV skills, e.g. "Budgeting" -> "budget"
    have_stems = {squash(n)[:6] for n in (cv_skills or [])
                  if " " not in n.strip() and len(squash(n)) >= 6}

    def loose_match(job_skill):
        """Partial match: 'scheduling' ~ 'projectscheduling', 'budgeting' ~ 'budgetmanagement'."""
        j = squash(job_skill)
        if len(j) < 4:
            return False                      # too short, e.g. "R" or "C"
        for h in have_names:
            if len(h) >= 4 and (h in j or j in h):
                return True                   # one name contains the other
        return any(stem in j for stem in have_stems)
    required = {}  
    # title -> set of skills
    for row in g.query(REQUIRED_SKILLS):
        required.setdefault(str(row.title), set()).add(row.skill)
        # Score only the postings the collector kept (filtered by the user's preferences)
    raw_file = DATA_DIR / "raw_postings.json"
    if raw_file.exists():
        postings = json.loads(raw_file.read_text(encoding="utf-8"))
    else:
        # No collector output yet -> fall back to all database postings
        postings = load_postings()
    for p in postings:
        if p.get("skills") and p["title"] not in required:
            required[p["title"]] = {CAREER[s] for s in p["skills"]}
    resources = {row.skill: (str(row.url) if row.url else None) for row in g.query(RESOURCES)}
    results = []
    gap_counter = Counter()

    for title, skills in required.items():
        
        matched = {s for s in skills
                   if s in have
                   or squash(short(s)) in have_names
                   or skills_to_uris([short(s)]) & have_uris
                   or loose_match(short(s))}
        
        missing = skills - matched
        gap_counter.update(short(s) for s in missing)
        score = len(matched) / len(skills)
        print(f"{title}: {score:.0%}  missing: {[short(s) for s in missing]}")
        results.append({
            "title": title,
            "score": round(score, 2),
            "required": sorted(short(s) for s in skills),
            "missing": [{"skill": short(s), "resource": resources.get(s)} for s in missing],
        })
    out = DATA_DIR / "matches.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print("Saved", out.name)
    save_matches(profile["user_id"], results)
    print("Saved matches to the database")
    skill_gaps = {
        "agent": "career",
        "student": profile["user_id"],
        "gaps": [
            {"skill": skill, "needed_by": count, "resource": resources.get(CAREER[skill])}
            for skill, count in gap_counter.most_common()
        ],
    }
    (DATA_DIR / "skill_gaps.json").write_text(json.dumps(skill_gaps, indent=2), encoding="utf-8")
    print("Saved skill_gaps.json")
      