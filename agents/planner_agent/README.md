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
| `agents/planner_agent/api.py` | FastAPI service (in-memory store for now) |
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

## Run the API

```bash
uvicorn agents.planner_agent.api:app --reload
# open http://127.0.0.1:8000/docs
```

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/proposals` | Agents push a list of ActivityProposal |
| POST | `/planner/runs` | Profile + horizon → 3 alternative plans |
| GET | `/planner/plans/{plan_id}` | One plan |
| POST | `/planner/plans/{plan_id}/decisions` | Accept / reject items |
| GET | `/planner/plans/{plan_id}/ics` | Calendar export |

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
- [ ] Persist proposals and plans in PostgreSQL instead of the in-memory dicts
- [ ] Re-plan when a new high-priority proposal arrives (keep accepted items via `approved_as_busy`)
- [ ] LLM layer: rewrite explanations in friendly language; parse requests like "keep Friday evening free"
- [ ] Learn weights from accept/reject decisions
