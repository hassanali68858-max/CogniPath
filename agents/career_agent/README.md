# Career Agent (CogniPath)

Owner: Elham Pournouri

The Career Agent finds job, internship and thesis opportunities, compares them with the
student's skills, and proposes a career plan (learn / apply / network) with scores for
three objectives (academic, career, social) for the Planner Agent.

## Run

```
pip install rdflib
python agents/career_agent/src/pipeline.py
```

## Sub-agents

| Step | File | Input | Output |
|------|------|-------|--------|
| 1. Collector | `src/subagents/collector.py` | `data/user_profile.json`, `data/sample_postings.json` | `data/raw_postings.json` |
| 2. Extractor | `src/subagents/extractor.py` | `raw_postings.json`, `ontology/career.owl` | `data/career_graph.ttl` |
| 3. Matcher | `src/subagents/matcher.py` | `career_graph.ttl` (SPARQL) | `data/matches.json`, `data/skill_gaps.json` |
| 4. Advisor | `src/subagents/advisor.py` | `matches.json`, `events.json` | `data/career_plan.json` |

## User profile (`data/user_profile.json`)

- `title`: keyword or `"any"`
- `countries`: list of ISO codes, e.g. `["FI"]`
- `city`: city name or `null`
- `work_mode`: `onsite` / `remote` / `hybrid` (list) or `"any"`
- `opportunity_type`: `job` / `internship` / `master_thesis` (list) or `"any"`

Remote postings match any location.

## Interfaces with other agents (JSON only)

- **Planner ← `career_plan.json`**: list of activities, each with
  `type`, `name`, `duration_minutes`, `scores {academic, career, social}`, `why`
- **Tutor ← `skill_gaps.json`**: missing skills with `needed_by` count and learning `resource`
- **Event → `events.json`**: `name`, `date`, `companies`, `topics`

`career.owl` is private to the Career Agent.

## Ontology

Namespace: `https://example.org/cognipath/career#`
Main classes: Student, Skill, CareerOpportunity (Internship, Job, ThesisOpportunity),
LearningResource, CareerPlan, CareerActivity.