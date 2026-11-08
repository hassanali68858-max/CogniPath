# Career Agent (CogniPath)

Owner: Elham Pournouri

The Career Agent finds job, internship and thesis opportunities, compares them with the
student's skills, and proposes a career plan (learn / apply / network) with scores for
three objectives (academic, career, social) for the Planner Agent.

The agent only advises and prepares. The student decides and applies.
No scraping and no automatic applications.

## Architecture

- `src/app.py`: Streamlit UI (port 8501)
- `src/api.py`: FastAPI backend (port 8000), docs at http://127.0.0.1:8000/docs
- `src/pipeline.py`: LangGraph pipeline (collector → extractor → matcher → advisor)
- PostgreSQL database (schema in `db/schema.sql`)
- Optional LLM explanations for each match (Anthropic)

## Setup

```
cd agents/career_agent
pip install -r requirements.txt
copy .env.example .env    # then fill in your own values
```



## Run

Terminal 1:
```
cd agents/career_agent/src
uvicorn api:app --reload
```

Terminal 2:
```
cd agents/career_agent/src
python -m streamlit run app.py
```

Pipeline only (test user):
```
python pipeline.py mira
```

## Sub-agents

| Step | File | Role |
|------|------|------|
| 1. Collector | `src/subagents/collector.py` | Loads postings that fit the user profile |
| 2. Extractor | `src/subagents/extractor.py` | Builds the skill graph with `ontology/career.owl` |
| 3. Matcher | `src/subagents/matcher.py` | Scores matches and finds skill gaps (SPARQL) |
| 4. Advisor | `src/subagents/advisor.py` | Builds the career plan and match explanations |

## Features

- Profile and CV upload
- Career plan with match score per opportunity
- Application tracker (same job is not added twice)
- Clear error messages in the UI

## Interfaces with other agents (JSON only)

- **Planner ← career plan**: activities with `type`, `name`, `duration_minutes`,
  `scores {academic, career, social}`, `why`
- **Tutor ← skill gaps**: missing skills with `needed_by` count and learning `resource`
- **Event → events**: `name`, `date`, `companies`, `topics`

`career.owl` is private to the Career Agent.

## Privacy

- Personal CVs, letters, job emails, career plans and `user_profile.json` are not stored in Git.
- Contact information is never sent to the LLM.
- Use only test users (for example `mira`) for demos.

## Ontology

Namespace: `https://example.org/cognipath/career#`
Main classes: Student, Skill, CareerOpportunity (Internship, Job, ThesisOpportunity),
LearningResource, CareerPlan, CareerActivity.
