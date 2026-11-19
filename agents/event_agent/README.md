# Event Agent

Event Agent: reads events from websites, posters and emails and ranks them by the user's interests.

Step 1 provides the API, PostgreSQL migration, and per-user preferences.

Run from the repository root with Python 3.11+ and PostgreSQL running.

```powershell
python -m pip install -r agents/event_agent/requirements.txt
Copy-Item agents/event_agent/.env.example agents/event_agent/.env
```

Set `EVENT_DATABASE_URL` in the agent's `.env`. For local development, set
`EVENT_USER_TOKENS` to a JSON object mapping Planner user IDs to distinct,
random bearer tokens. An empty object disables access to all preference routes.
Keep any future vision provider key in `LLM_API_KEY` in the same file.

```powershell
python -m agents.event_agent.db
python -m uvicorn agents.event_agent.api:app --port 8002
```

Open [Swagger UI](http://127.0.0.1:8002/docs), select **Authorize**, and enter
the token for the user ID in the request. Use `PUT /preferences/{user_id}`
to replace that user's preferences and `GET /preferences/{user_id}` to read them.
