# Backend

Development backend for CogniPath. Today it serves:

- the Planner API (`agents/planner_agent/api.py`): profiles, proposals, planning, decisions, re-planning
- demo helpers (`backend/demo.py`): `POST /demo/seed` loads the mock student, `POST /demo/reset/{user_id}` wipes it
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
