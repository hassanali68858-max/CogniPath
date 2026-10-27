import json
from pathlib import Path

from rdflib import Graph, Namespace

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
CAREER = Namespace("https://example.org/cognipath/career#")

STUDENT_SKILLS = """
PREFIX career: <https://example.org/cognipath/career#>
SELECT ?skill WHERE { career:ElhamPournouri career:hasSkill ?skill . }
"""

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

    have = {row.skill for row in g.query(STUDENT_SKILLS)}

    required = {}                      # title -> set of skills
    for row in g.query(REQUIRED_SKILLS):
        required.setdefault(str(row.title), set()).add(row.skill)

    resources = {row.skill: (str(row.url) if row.url else None) for row in g.query(RESOURCES)}
    results = []

    for title, skills in required.items():
        matched = have & skills
        missing = skills - have
        score = len(matched) / len(skills)
        print(f"{title}: {score:.0%}  missing: {[short(s) for s in missing]}")
        results.append({
            "title": title,
            "score": round(score, 2),
            "missing": [{"skill": short(s), "resource": resources.get(s)} for s in missing],
        })

    out = DATA_DIR / "matches.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print("Saved", out.name)