import json
import re
from pathlib import Path
from rdflib import Graph, Namespace, Literal, RDF, XSD

DATA_DIR = Path(__file__).resolve().parents[2] / "data"

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


def extract_skills(text):
    found = []
    for skill in KNOWN_SKILLS:
        if re.search(rf"\b{re.escape(skill)}\b", text, re.IGNORECASE):
            found.append(skill)
    return found

CAREER = Namespace("https://example.org/cognipath/career#")
ONTOLOGY = Path(__file__).resolve().parents[2] / "ontology" / "career.owl"

TYPE_TO_CLASS = {
    "internship": CAREER.Internship,
    "job": CAREER.Job,
    "master_thesis": CAREER.ThesisOpportunity,
}


def slug(text):
    return re.sub(r"[^A-Za-z0-9]", "", text.title())   # "Machine Learning" -> "MachineLearning"


def add_to_graph(g, p):
    opp = CAREER[slug(p["company"] + " " + p["title"])]
    g.add((opp, RDF.type, TYPE_TO_CLASS.get(p["type"], CAREER.CareerOpportunity)))
    g.add((opp, CAREER.jobTitle, Literal(p["title"])))
    g.add((opp, CAREER.sourceURL, Literal(p["url"], datatype=XSD.anyURI)))
    for s in p["skills"]:
        skill = CAREER[slug(s)]
        g.add((skill, RDF.type, CAREER.Skill))
        g.add((opp, CAREER.requiresSkill, skill))

if __name__ == "__main__":
    postings = json.loads((DATA_DIR / "raw_postings.json").read_text(encoding="utf-8"))
    postings = dedupe(postings)
    for p in postings:
        p["skills"] = extract_skills(p["description"])
        print(p["title"], "->", p["skills"])

    g = Graph()
    g.parse(ONTOLOGY)
    print("Before:", len(g))
    for p in postings:
        add_to_graph(g, p)
    print("After:", len(g)) 
    
    out = DATA_DIR / "career_graph.ttl"
    g.serialize(destination=out, format="turtle")
    print("Saved graph to", out.name)
