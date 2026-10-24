# CogniPath

Your one-stop cognitive companion for study, events and career (TIES4570 Cognitive Service Project).

Three domain agents (Event, Tutor, Career) each propose activities. The Planner Agent
joins them into one balanced plan, and the user approves it.

```
data sources -> Event / Tutor / Career agents -> ActivityProposal -> Planner -> web app -> user approves
```

## Team

| Area | Owner | Folder |
| --- | --- | --- |
| Planner Agent | _add name_ | `agents/planner_agent/` |
| Career Agent | Elham | `agents/career_agent/` |
| Event Agent | _add name_ | `agents/event_agent/` |
| Tutor Agent | _add name_ | `agents/tutor_agent/` |
| Backend / integration | _add name_ | `backend/` |
| Frontend | _add name_ | `frontend/` |

## Repository layout

```
CogniPath/
  shared/contracts/   common data models every agent uses (ActivityProposal, profile, plan)
  agents/
    event_agent/      events from websites, posters, emails
    tutor_agent/      study plan, prerequisites, Erasmus, quizzes
    career_agent/     skill gaps, jobs, CV help (ontology + RDFLib)
    planner_agent/    joins all proposals into one balanced plan
  backend/            FastAPI app, orchestration, database access
  frontend/           web app (plan view, approve / reject)
  infra/              docker-compose, database migrations, deployment
  data/seed/          demo data: events, jobs, courses
  docs/               reports, diagrams, homework slides
  tests/              one folder per agent + integration tests
```

Each agent folder contains its own `README.md`, `requirements.txt`, code and
(if needed) its own data such as an ontology. Tests live in `tests/<agent_name>/`.

## Branch workflow

1. `main` always works. Nobody commits to it directly.
2. Create your branch from the latest `main`:
   ```bash
   git checkout main && git pull
   git checkout -b feature/<agent-or-topic>
   ```
3. Work only inside your own folder. Changes to `shared/contracts/` go in a
   separate, small pull request that everyone reviews.
4. Bring in other people's work at least twice a week:
   ```bash
   git fetch origin && git merge origin/main
   ```
5. Open a pull request into `main`; one teammate reviews; CI must pass.

## Setup (Python 3.11+)

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -r agents/<agent>/requirements.txt
pytest
```
