# Backend

Development backend for CogniPath. Today it serves:

- the Planner API (`agents/planner_agent/api.py`): profiles, proposals, planning, decisions, re-planning
- Tutor Agent routes (`backend/tutor.py`): `GET /tutor/{user_id}/report` returns the progress report,
  topic mastery, forum links and proposals; `POST /tutor/{user_id}/proposals` stores the proposals for
  the Planner and withdraws Tutor proposals the agent no longer makes; `POST /tutor/{user_id}/quizzes`
  returns a new quiz with a `quiz_id` and without answers, and `POST /tutor/{user_id}/quizzes/{quiz_id}/answers`
  grades it once and adds it to the quiz history (open quizzes and the history are kept in memory until the
  backend restarts). `GET /tutor/{user_id}/courses` lists the next offering of each course not taken yet,
  and `GET /tutor/catalog/source` tells whether the course data is seed data or live from JYU Sisu.
  Environment variables set the question generator and the course data source (see the
  [Tutor Agent README](../agents/tutor_agent/README.md#llm-questions) and
  [Sisu course data](../agents/tutor_agent/README.md#sisu-course-data))
- demo helpers (`backend/demo.py`): `POST /demo/seed` loads the demo student (mock Event proposals,
  real Tutor and Career proposals), `POST /demo/reset/{user_id}` wipes it
- CORS for the Next.js frontend on `http://localhost:3000`

## Run

```bash
pip install -r requirements.txt -r agents/planner_agent/requirements.txt
docker compose -f infra/docker-compose.yml up -d                       # optional: PostgreSQL
export DATABASE_URL=postgresql+psycopg://cognipath:cognipath@localhost:5432/cognipath
uvicorn backend.main:app --reload                                       # http://127.0.0.1:8000/docs
```

Without `DATABASE_URL` it uses a local SQLite file. Allowed frontend origins can
be changed with `FRONTEND_ORIGINS` (comma-separated).

When the Event, Tutor and Career agents are ready, their routes and the
"plan my week" orchestration belong here too.
