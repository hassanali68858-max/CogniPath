# CogniPath – Planner Agent

The Planner joins the Event, Tutor and Career agents' proposals into a plan
the student approves. It follows the approach agreed with the team (after the
professor's feedback):

- **No priorities.** No agent or label outranks another. Importance comes only
  from each proposal's `value` (study / career / social, 0–1). Deadlines, fixed
  times and `hard` are constraints, not rankings.
- **Three separate objectives.** For each goal, `G_k` = the share of all
  proposed value for that goal that is in the plan. They are never added up
  with fixed weights.
- **CP-SAT for the constraints**: no overlaps, busy time, day hours, daily
  limit, windows/deadlines, dependencies, accepted items stay.
- **Payoff table**: best reachable share per goal (ideal) and the worst among
  those single-goal plans (nadir), used to put the goals on one scale.
- **Reference-point ASF** (achievement scalarizing function) picks the
  **balanced** plan: as close as possible to the ideal on the worst-off goal.
- **Pareto alternatives**: "more study", "more career" and "more social"
  versions (ASF with a reference point leaning to that goal). Duplicates and
  dominated versions are dropped; each one says what it gains and gives up.
- **NIMBUS-style steering**: the student marks each goal *improve*, *keep* or
  *can give* (optionally "not below X %") and gets a new Pareto-optimal plan,
  or a plain sentence saying why that is not possible.

The system advises; the student decides.

## Layout

| Path | What |
| --- | --- |
| `shared/contracts/` | `ActivityProposal` (agent → Planner), `PlannerProfile`, `Plan` + exported JSON Schema |
| `agents/planner_agent/solver.py` | CP-SAT model (30-minute grid): constraints + one target per solve (max, sum, ASF) |
| `agents/planner_agent/planner.py` | Pipeline: merge → payoff table → ASF / Pareto alternatives → trade-offs; `nimbus()`; `replan()` |
| `agents/planner_agent/explain.py` | Why each item was kept or dropped |
| `agents/planner_agent/adapters/career.py` | Only for the first Career prototype; the Career Agent now writes a `ProposalBatch` |
| `agents/planner_agent/api.py` | FastAPI service |
| `agents/planner_agent/store.py` | Database tables and queries (PostgreSQL or SQLite) |
| `agents/planner_agent/cli.py` | Command-line demo |
| `tests/planner_agent/` | Tests + mock data (19 proposals, the real Career Agent batch, 1 profile) |

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
  --profile tests/planner_agent/fixtures/mock_profile.json \
  --start 2026-11-02 --days 14 --daily-cap 120 --ics plan.ics
```

`plan.ics` opens in Outlook, Google Calendar or Apple Calendar.

With the mock profile (3 h of planned time per day) everything except two
clashing social events fits, so the goals do not compete and you get one plan.
With `--daily-cap 120` (a tight fortnight) you get the balanced plan plus
leaning versions, each with its trade-off ("Study +7 pts, Career -6 pts
compared with Balanced. Adds ... Gives up ...").

How flexible work is placed: at most one session per activity per day, each
session between `split.min_session_min` and `split.max_session_min` (default
60-120 min), all sessions summing to `duration_min`.

Shares are computed per goal, so a goal with few proposals is not drowned out
by a goal with many. Independent solves (payoff rows, alternatives) run in
parallel threads; each solve is single-threaded, so results are reproducible.

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
| POST | `/proposals/batch` | Agents push one `ProposalBatch` (e.g. the Career Agent's `career_plan.json`) |
| POST | `/proposals` | Agents push a plain list of ActivityProposal (insert or update) |
| GET | `/proposals?user_id=&status=` | List proposals (`active`, `rejected`, `withdrawn`) |
| POST | `/proposals/{user_id}/{proposal_id}/withdraw` | Agent takes a proposal back (event cancelled) |
| POST | `/planner/runs` | Plan with a stored profile (`user_id`) or an inline `profile` → balanced + Pareto alternatives |
| GET | `/planner/runs/{run_id}` | The alternatives of one run |
| GET | `/planner/plans/{plan_id}` | One plan |
| GET | `/planner/users/{user_id}/current` | The plan the student is working with |
| POST | `/planner/plans/{plan_id}/decisions` | Accept / reject items |
| POST | `/planner/plans/{plan_id}/nimbus` | Steer: `{"classes": {"career": "improve", "study": "keep", "social": "worsen"}, "limits": {"social": 0.3}}` |
| GET | `/planner/users/{user_id}/schedule` | Accepted sessions (`planner.scheduled_activities`), e.g. for other agents |
| POST | `/planner/plans/{plan_id}/replan` | Re-plan this plan (see below) |
| POST | `/planner/users/{user_id}/replan` | Re-plan the student's current plan |
| GET | `/planner/plans/{plan_id}/ics` | Calendar export |

Rules the API applies:

- The first decision on a plan marks the other alternatives of that run as `discarded`.
- A NIMBUS plan joins the same run as another alternative, with `tradeoff` against the plan it came from.
  If the request cannot be met (nothing to give, or no better plan under the limits) the API answers 422
  with a sentence for the student.
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

## Database

One PostgreSQL database `cognipath`, one schema per agent. The Planner owns schema `planner`
(`profiles`, `proposals`, `plans`, `decisions`, `scheduled_activities`) and only adds missing
user ids to the common `shared.users`. It never touches another agent's schema; agents talk to
it through the API. On SQLite the same tables are created without schemas.

Tests run on in-memory SQLite. To also run them on PostgreSQL (CI does this):

```bash
TEST_DATABASE_URL=postgresql+psycopg://cognipath:cognipath@localhost:5432/cognipath pytest
```

## For the other agents

Send a `ProposalBatch` from `shared.contracts` (validate it with Pydantic before sending).
Fixed-time things (events) set `fixed_time`; work that can happen any time before a deadline
sets `duration_min` + `window`. Score `value.study / career / social` on the shared 0–1 rubric
(anchors 0 / 0.3 / 0.6 / 0.9) and always fill `reason` – the student sees it. There is no
`priority` field any more (old outputs that still send it are accepted; it is ignored).

Non-Python code can validate against `shared/contracts/activity_proposal.schema.json`.
After changing the model, regenerate it: `python -m shared.contracts.export_schema`.

## Next steps

- [ ] Agree the contract and the shared scoring rules with all agent owners (PR review)
- [x] Career Agent returns a `ProposalBatch` directly (old adapter kept only for the first prototype)
- [x] No priorities: Pareto alternatives, ASF balanced plan, NIMBUS steering
- [x] Planner tables in the `planner` schema, users in `shared.users`
- [x] Persist proposals and plans in PostgreSQL
- [x] Re-plan when something changes, keeping accepted items
- [ ] Trigger re-planning automatically from the backend (scheduler / new proposals)
- [ ] LLM layer: rewrite explanations in friendly language; parse requests like "keep Friday evening free"
- [ ] Parallel agent fan-out ("plan my week" asks all agents at once, with timeouts)
