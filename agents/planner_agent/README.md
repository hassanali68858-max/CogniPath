# Planner Agent (CogniPath)

Owner: Muhammad Hassan Ali

The Planner Agent collects the activities proposed by the Event, Tutor and Career agents and
turns them into a plan that fits the student's free time. It keeps three goals (study, career,
social) separate, shows a few versions of the plan with what each one gains and gives up, and
lets the student steer the balance.

The agent only advises. The student decides and accepts or rejects every item. There are no
priorities: no agent and no label outranks another.

## Architecture

- `api.py`: FastAPI service, docs at http://127.0.0.1:8000/docs
- `planner.py`: planning pipeline (merge → versions → trade-offs → steering → re-planning)
- `solver.py`: constraint model (Google OR-Tools)
- `explain.py`: plain-language reason for every planned and left-out item
- `store.py`: PostgreSQL database (schema `planner`), SQLite for quick local runs
- `backend/main.py` + `frontend/`: development server and Next.js test UI (port 3000)

## Setup

From the repository root:

```
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r agents/planner_agent/requirements.txt
cp .env.example .env               # Windows: copy .env.example .env
docker compose -f infra/docker-compose.yml up -d     # PostgreSQL (optional)
```

Without Docker, leave `DATABASE_URL` unset and a local SQLite file is used.

## Run

Terminal 1:

```
uvicorn backend.main:app --reload
```

Terminal 2:

```
cd frontend
npm install
npm run dev
```

Open http://localhost:3000 and click **Try it with the demo student**.

Command line only (demo data, tight fortnight):

```
python -m agents.planner_agent.cli --proposals tests/planner_agent/fixtures/mock_proposals.json --profile tests/planner_agent/fixtures/mock_profile.json --start 2026-11-02 --daily-cap 120
```

Tests: `pytest`

## Steps

| Step | File | Role |
| --- | --- | --- |
| 1. Collect | `api.py`, `store.py` | Stores the activities the agents send, and the student's profile |
| 2. Merge | `planner.py` | Joins the same event proposed by two agents |
| 3. Check | `solver.py` | Finds what fits: free time, deadlines, daily limit, order of tasks |
| 4. Compare | `planner.py` | Best reachable score per goal; balanced plan and goal-leaning versions |
| 5. Explain | `explain.py`, `planner.py` | Why each item is in or out; what each version gains and gives up |
| 6. Steer | `planner.py` | Student says improve / keep / can give per goal; a new version is made |
| 7. Re-plan | `planner.py` | New or withdrawn activities: accepted items stay, the rest adapts |

## Features

- Plans only inside the student's day hours, around lectures and work shifts, within a daily limit
- Long tasks split into sessions (at most one per day) and finished before their deadline
- Importance comes only from each activity's study / career / social score
- A balanced plan plus "more study", "more career" and "more social" versions when goals compete
- Steering: improve this goal, keep that one, this one can give (optionally "not below X %")
- A reason for every planned and left-out item
- Accept / reject per item; rejected items are not suggested again
- Re-planning keeps accepted items and shows what was added, moved or removed
- Calendar export (`.ics`) for Outlook, Google or Apple Calendar

## Interfaces with other agents (JSON only)

- **Planner ← all agents**: `ProposalBatch` from `shared/contracts`, sent to `POST /proposals/batch`.
  Each activity has `fixed_time` (events) or `duration_min` + `window` (tasks with a deadline),
  `value {study, career, social}` on 0–1 (anchors 0 / 0.3 / 0.6 / 0.9), `reason`, optional `hard`
  and `depends_on`. No `priority` field.
- **Planner → other agents**: accepted sessions at `GET /planner/users/{user_id}/schedule`
  (to avoid suggesting things that clash).
- **Planner → student**: plan versions with goal scores, trade-offs and reasons.

JSON Schema for non-Python agents: `shared/contracts/activity_proposal.schema.json`.

## Database

PostgreSQL database `cognipath`, schema `planner`: `profiles`, `proposals`, `plans`,
`decisions`, `scheduled_activities`. The Planner only adds missing user ids to the common
`shared.users` and never writes another agent's tables.

## Privacy

- Stores only what planning needs: day hours, busy times, proposals, plans and decisions.
- No CVs, letters or contact details. Nothing is sent to an LLM.
- Local databases (`*.db`) and `.env` are not stored in Git.
- Use only test users (for example `student001`) for demos.

## Methods (tested)

Checked with 61 automated tests and the demo data (Event and Tutor mock data plus the real
Career Agent output). The versions differ in the expected direction, and impossible requests
get a clear answer.

- Constraints: Google OR-Tools CP-SAT
- Versions: Pareto-optimal plans (no version is better on every goal)
- Balanced plan: reference-point method (achievement scalarizing function)
- Steering: NIMBUS-style improve / keep / can give

If results with the real Event and Tutor data are not good, these can be replaced without
changing the API or the shared format.

## Next steps

- [ ] Agree one scoring formula with all agent owners
- [ ] Connect the Event and Tutor agents through `ProposalBatch`
- [ ] Ask all agents in parallel and re-plan automatically when new activities arrive
- [ ] Optional LLM layer for friendlier explanations and requests like "keep Friday evening free"
