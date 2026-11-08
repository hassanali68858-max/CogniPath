import json
import re
import sys
from pathlib import Path
from rdflib import Graph, Namespace, Literal, RDF, XSD

# Make src/ importable so we can use llm.py from this subfolder
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from llm import ask_llm
from db import ensure_user, save_postings, latest_cv_skills, load_user_profile
DATA_DIR = Path(__file__).resolve().parents[2] / "data"

# Fallback list, used only if the LLM is not available
KNOWN_SKILLS = ["Python", "Docker", "Machine Learning", "LangGraph", "RDF", "SQL", "Git"]


def dedupe(postings):
    seen = set()
    unique = []
    for p in postings:
        key = (p["title"].strip().lower(), p["company"].strip().lower())
        if key in seen:
            continue
        seen.add(key)
        unique.append(p)
    return unique


def extract_skills_regex(text):
    """Old method: find only skills from the fixed KNOWN_SKILLS list."""
    found = []
    for skill in KNOWN_SKILLS:
        if re.search(rf"\b{re.escape(skill)}\b", text, re.IGNORECASE):
            found.append(skill)
    return found


def extract_skills(text):
    """Ask the LLM for the skills in a posting; fall back to regex on failure."""
    prompt = f"""Extract the skills required in this job posting.
Return ONLY a JSON list of short skill names, nothing else.
Example: ["Python", "Docker"]

Posting:
{text}"""
    try:
        answer = ask_llm(prompt)
    except Exception as e:
        print("LLM not available, using regex:", e)
        return extract_skills_regex(text)
    # Keep only the part between the first [ and the last ]
    start = answer.find("[")
    end = answer.rfind("]")
    if start == -1 or end == -1:
        return extract_skills_regex(text)
    try:
        skills = json.loads(answer[start:end + 1])
    except json.JSONDecodeError:
        return extract_skills_regex(text)
    # Keep only non-empty strings
    
    return [s.strip() for s in skills if isinstance(s, str) and s.strip()]


CAREER = Namespace("https://example.org/cognipath/career#")
ONTOLOGY = Path(__file__).resolve().parents[2] / "ontology" / "career.owl"

TYPE_TO_CLASS = {
    "internship": CAREER.Internship,
    "job": CAREER.Job,
    "master_thesis": CAREER.ThesisOpportunity,
}


def slug(text):
    clean = re.sub(r"[^A-Za-z0-9 ]", "", text)
    words = clean.split()
    return "".join(w[:1].upper() + w[1:] for w in words)


def add_to_graph(g, p):
    opp = CAREER[slug(p["company"] + " " + p["title"])]
    g.add((opp, RDF.type, TYPE_TO_CLASS.get(p["type"], CAREER.CareerOpportunity)))
    g.add((opp, CAREER.jobTitle, Literal(p["title"])))
    g.add((opp, CAREER.sourceURL, Literal(p["url"], datatype=XSD.anyURI)))
    for s in p["skills"]:
        skill = CAREER[slug(s)]
        g.add((skill, RDF.type, CAREER.Skill))
        g.add((opp, CAREER.requiresSkill, skill))


def add_student(g, profile):
    """Add the student and their skills to the graph (CV skills first, then profile)."""
    student = CAREER[profile["user_id"]]
    g.add((student, RDF.type, CAREER.Student))
    skills = latest_cv_skills(profile["user_id"])   # skills come only from the CV
    for s in skills:
        skill = CAREER[slug(s)]
        g.add((skill, RDF.type, CAREER.Skill))
        g.add((student, CAREER.hasSkill, skill))


if __name__ == "__main__":
    postings = json.loads((DATA_DIR / "raw_postings.json").read_text(encoding="utf-8"))
    postings = dedupe(postings)
    for p in postings:
        # Skills already saved (e.g. from the database) -> no new LLM call, no cost
        if not p.get("skills"):
            p["skills"] = extract_skills(p["description"])
        print(p["title"], "->", p["skills"])

    g = Graph()
    g.parse(ONTOLOGY)
    print("Before:", len(g))
    # Usage: python subagents\extractor.py <user_id>
    user_id = sys.argv[1] if len(sys.argv) > 1 else input("User ID: ").strip()
    profile = load_user_profile(user_id)
    if profile is None:
        sys.exit(f"No profile for {user_id!r}. Fill in the form first: streamlit run onboarding.py")
    # Save the user and the postings (with LLM skills) to PostgreSQL
    ensure_user(profile["user_id"])
    save_postings(postings)
    print("Saved", len(postings), "postings to the database")
    add_student(g, profile)
    for p in postings:
        add_to_graph(g, p)
    print("After:", len(g))

    out = DATA_DIR / "career_graph.ttl"
    g.serialize(destination=out, format="turtle")
    print("Saved graph to", out.name)