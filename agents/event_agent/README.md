# Event Agent

Event Agent: reads events from websites, posters and emails and ranks them by the user's interests.

The Event Agent collects and ranks events, analyzes board photos, and sends
eligible recommendations to the Planner.

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

## Collect events

Set `EVENT_OPERATOR_TOKEN` in the agent's `.env` to a separate random token,
then run the database migration again. It registers Keski-Suomi Events as
the first source. Sources are configured in the `event.sources` table.
Keep one module per input source in `collectors/`. Keski-Suomi Events uses
`collectors/scrape_keski_suomi.py`. Add future Gmail and poster collectors
there too. Each collector extracts source-specific data and constructs validated
`EventCandidate` objects. To add a scheduled website, register its collector
in `sources.py` and add the source to `event.sources`.

Start the worker in a second terminal from the repository root.

```powershell
python -m agents.event_agent.worker
```

Authorize with the operator token in Swagger. Call `POST /ingestion/runs`
to queue a refresh of all enabled sources, or send
`{"source_keys":["keski-suomi"]}` to select that source. Poll
`GET /ingestion/runs/{run_id}` for the result. Counts refer to source records.
The worker reads all pages before saving changes from a source, so a failed
page leaves that source's existing catalog intact.

Keski-Suomi requests up to 500 records per page. Its `start` query date is
calculated each run from the Helsinki date 48 hours ahead. Only listings that
start at least 48 hours after the run begins are imported from this source.

For a test import, send `{"limit":5}` to `POST /ingestion/runs`. The worker
stops after five valid listings across the selected sources. Existing
listings count toward the limit. Omit `limit` for a full import.

Use `GET /events?limit=100&offset=0` to browse the shared catalog with a user
or operator token. The response includes the total and a page of event records.
Increase `offset` to see more. The catalog includes imported listings and
consented poster events. Private poster matches are available through the
owner's recommendations endpoint.

To clear all Event Agent data, authorize with the operator token and call
`POST /admin/reset` with `{"confirm":"RESET_EVENT_DATA"}`. This clears events,
run history, uploads, recommendations, user preferences, and custom sources.
It restores the default sources and keeps the schema and migration history.
Planner data is stored separately and is outside this reset.

## Match and publish events

Run the database migration again and set `EVENT_PLANNER_URL` if the Planner
runs on a different address. Save the user's preferences first.

- `POST /recommendations/{user_id}/refresh` scores upcoming events against the
  latest saved preferences. It saves up to 20 matches in the next 28 days and
  automatically attempts delivery when `auto_publish` is enabled.
- `GET /recommendations/{user_id}` returns the saved shortlist with reasons
  and delivery status.
- `POST /recommendations/{user_id}/publish` sends all current recommendations
  with confirmed times. Use `{"recommendation_ids":["<id>"]}` to choose specific
  recommendations. A subsequent publish can retry failed deliveries.

The collection model extracts evidence-backed event relationships. The
recommendation model evaluates interest, language, attendance, and travel.
The Event Agent applies ELECTRE TRI-B concordance profiles and requirement
vetoes to decide whether to recommend, consider, or skip an event. Preferences
support `require_language` (default true when languages are listed) and
`require_attendance` (default false). Location preferences are flexible.
Shared catalog decisions are stored with explanations, criteria, and evidence.
The recommendations endpoint shows the shortlist of recommended and consider
events. Planner delivery requires a recommended decision and confirmed times.
Confirmed cancellations are withdrawn on the next publish. Generate or replan
in the Planner to update the calendar.

## Analyze a board photo

Apply the migration with `python -m agents.event_agent.db`. Configure the
poster, collection, and recommendation models in the agent's local `.env`.

In Swagger, call `POST /poster-analysis/{user_id}` with a signed-in user's token,
an `image` file, and optional `share_events` set to `true` or `false`.
Accepted images are JPEG, PNG, or WebP, up to 10 MB and 30 megapixels.
The request waits for analysis and returns the uploader's ranked matches.

- With sharing enabled, all validated events go into the shared catalog.
  Other users can match against eligible events on their next refresh.
- With sharing off, only the uploader's matches are saved, as private
  recommendations. Unmatched events are discarded.
- The service records consent and sends the image to the vision provider for
  analysis. It does not save the image in CogniPath or include it in the catalog.
  Missing or unclear times stay in recommendations for review. Only events with
  confirmed start and end times can be delivered to the Planner.

## Model configuration

Set the three model and key pairs independently in `agents/event_agent/.env`.

| Settings | Used for |
| --- | --- |
| `COLLECTION_AGENT_MODEL`, `COLLECTION_AGENT_KEY` | Extract and cache event relationships and infer missing languages from clear title or description text. Website fetching itself reads the public feed directly. |
| `RECOMMEND_AGENT_MODEL`, `RECOMMEND_AGENT_KEY` | Assess event relevance and practical fit, and write a user-facing explanation. |
| `POSTER_AGENT_MODEL`, `POSTER_AGENT_KEY` | Extract event details from board photos. |

All models must support structured JSON over the OpenAI-compatible Responses
API. The poster model also needs image input. For a compatible alternative
provider set the corresponding `COLLECTION_AGENT_BASE_URL`,
`RECOMMEND_AGENT_BASE_URL`, or `POSTER_AGENT_BASE_URL`. Each defaults to
`https://api.openai.com/v1`. Model settings are reloaded on each analysis,
refresh, and nightly matching run. Older `LLM_API_KEY` and
`EVENT_VISION_MODEL` settings remain fallback settings for the poster model.

When the collection model infers a missing language, the catalog and
recommendations show it in `languages` with `language_inferred: true`.
Explicit language metadata takes precedence. Inference runs after import and
can also be refreshed when matching saved events.

Website imports save listings and AI enrichment in the same transaction per
source. If the model fails or is rate-limited, the source's changes roll back
and the run reports the error. Website listings without a confirmed start at
least 24 hours away are skipped. Keski-Suomi applies its stricter 48-hour limit.

## Run the nightly workflow

Apply the latest migration and keep the worker running. It queues one nightly
run per Helsinki calendar date at 02:00 by default. Set `EVENT_NIGHTLY_HOUR` and
`EVENT_NIGHTLY_MINUTE` to change the time. Starting the worker after today's
scheduled time queues today's run if it has not already been queued.

The worker refreshes the enabled sources once, then reads the saved
preferences of users with `nightly_matching: true`. Each user is matched
against the full eligible shared catalog, including consented poster events.
Matching still runs against the stored catalog if a source fails. Users with
`auto_publish: true` have eligible matches sent to the Planner. If delivery
fails, the recommendations remain available for another attempt.

Use the operator token with `GET /ingestion/runs` to find recent manual and
nightly runs. The nightly status shows per-source counts and a separate
matching summary. Manual ingestion refreshes only the catalog.

Open [CogniPath Events](http://127.0.0.1:8002/) to upload a board photo, choose
whether to share its event details, and view or refresh saved recommendations.
Save the user's preferences through Swagger first and use the same user ID
in the Planner. With the Planner backend and frontend running, open
[Planner Suggestions](http://localhost:3000/suggestions) to see published
proposals and generate a plan from the Planner.
