# CogniPath – Planner Agent

The Planner joins the Event, Tutor and Career agents' proposals into one
balanced plan. It minimises

```
study loss + career loss + social loss + soft conflicts + fairness (worst objective)
```

with Google OR-Tools CP-SAT, returns three alternatives (balanced, study first,
career first), explains every kept and dropped item, and waits for the user to
accept or reject items.

## Layout

| Path | What |
| --- | --- |
| `shared/contracts/` | `ActivityProposal` (agent → Planner), `PlannerProfile`, `Plan` + exported JSON Schema |
| `agents/planner_agent/solver.py` | CP-SAT model (30-minute grid) |
| `agents/planner_agent/planner.py` | Pipeline: merge duplicates → solve per mode → explain → `Plan` |
| `agents/planner_agent/explain.py` | Why each item was kept or dropped |
| `agents/planner_agent/adapters/career.py` | Converts the Career Agent prototype's `career_plan.json` |
| `agents/planner_agent/api.py` | FastAPI service |
| `agents/planner_agent/store.py` | Database tables and queries (PostgreSQL or SQLite) |
| `agents/planner_agent/cli.py` | Command-line demo |
| `tests/planner_agent/` | 28 tests + mock data (19 proposals, 1 career file, 1 profile) |

## Setup (Python 3.11+)

From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r agents/planner_agent/requirements.txt
pytest
```

## Run the demo

```bash
python -m agents.planner_agent.cli \
  --proposals tests/planner_agent/fixtures/mock_proposals.json \
  --career tests/planner_agent/fixtures/career_plan_sample.json \
  --profile tests/planner_agent/fixtures/mock_profile.json \
  --start 2026-11-02 --days 14 --ics plan.ics
```

`plan.ics` opens in Outlook, Google Calendar or Apple Calendar.

With the mock profile (3 h of planned time per day) everything except two
clashing social events fits, so the three alternatives are the same. Add
`--daily-cap 120` to simulate a tight fortnight: the balanced, study-first and
career-first plans then drop different items, and each drop is explained.

How flexible work is placed: at most one session per activity per day, each
session between `split.min_session_min` and `split.max_session_min` (default
60-120 min), all sessions summing to `duration_min`.

Losses are normalised per objective, so a goal with few proposals is not
drowned out by a goal with many. Two items serving different goals are
therefore balanced against each other, not compared by raw score.

## Run the API with PostgreSQL

```bash
docker compose -f infra/docker-compose.yml up -d
export DATABASE_URL=postgresql+psycopg://cognipath:cognipath@localhost:5432/cognipath
uvicorn agents.planner_agent.api:app --reload
# open http://127.0.0.1:8000/docs
```

Without `DATABASE_URL` the API uses a local SQLite file (`cognipath_dev.db`), so
you can try it without Docker. Tables are created on first start.

| Method | Path | Purpose |
| --- | --- | --- |
| PUT / GET | `/profiles/{user_id}` | Store or read a student's planner profile |
| POST | `/proposals` | Agents push a list of ActivityProposal (insert or update) |
| GET | `/proposals?user_id=&status=` | List proposals (`active`, `rejected`, `withdrawn`) |
| POST | `/proposals/{user_id}/{proposal_id}/withdraw` | Agent takes a proposal back (event cancelled) |
| POST | `/planner/runs` | Plan with a stored profile (`user_id`) or an inline `profile` → 3 alternatives |
| GET | `/planner/runs/{run_id}` | The alternatives of one run |
| GET | `/planner/plans/{plan_id}` | One plan |
| GET | `/planner/users/{user_id}/current` | The plan the student is working with |
| POST | `/planner/plans/{plan_id}/decisions` | Accept / reject items |
| POST | `/planner/plans/{plan_id}/replan` | Re-plan this plan (see below) |
| POST | `/planner/users/{user_id}/replan` | Re-plan the student's current plan |
| GET | `/planner/plans/{plan_id}/ics` | Calendar export |

Rules the API applies:

- The first decision on a plan marks the other alternatives of that run as `discarded`.
- A rejected item's proposal is marked `rejected` and is not planned again. If the
  agent sends it again, it stays rejected; if the user un-rejects it, it is active again.
- A withdrawn proposal becomes active again if the agent sends it again.

## Re-planning

Call a replan endpoint whenever something changes: an agent pushes new
proposals, withdraws one, or the student's profile gets a new busy block.

- **Accepted** items keep their exact times.
- **Rejected** items are left out.
- **Pending** items and new proposals are planned again around them. Moving a
  pending item costs a little, so a re-plan only moves what it has to.
- With `"not_before": "<now>"` in the body, nothing new is placed in the past;
  events that already started are dropped with an explanation.
- An accepted item whose proposal was withdrawn, or that now clashes with a new
  busy block, is removed or planned again, and the plan's `changes.notes` says so.
- The new plan has `based_on` = the old plan and a `changes` summary
  (added / moved / removed / unchanged). The old plan becomes `superseded`.

Typical flow from the backend:

```text
POST /proposals                         (an agent found a new event)
POST /planner/users/student001/replan   {"not_before": "2026-11-09T12:00"}
→ show changes.summary and changes.notes to the student
```

Tests run on in-memory SQLite. To also run them on PostgreSQL (CI does this):

```bash
TEST_DATABASE_URL=postgresql+psycopg://cognipath:cognipath@localhost:5432/cognipath pytest
```

## For the other agents

Return `list[ActivityProposal]` from `shared.contracts`. Fixed-time things
(events) set `fixed_time`; work that can happen any time before a deadline sets
`duration_min` + `window`. Score `value.study / career / social` on the 0–1
rubric in `activity_proposal.py`, and always fill `reason` – the user sees it.

Non-Python code can validate against `shared/contracts/activity_proposal.schema.json`.
After changing the model, regenerate it: `python -m shared.contracts.export_schema`.

## Next steps

- [ ] Agree the contract with all agent owners (PR review)
- [ ] Career Agent returns `ActivityProposal` directly → delete `adapters/career.py`
- [x] Persist proposals and plans in PostgreSQL
- [x] Re-plan when something changes, keeping accepted items
- [ ] Trigger re-planning automatically from the backend (scheduler / new proposals)
- [ ] LLM layer: rewrite explanations in friendly language; parse requests like "keep Friday evening free"
- [ ] Learn weights from accept/reject decisions
