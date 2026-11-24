# Career Agent (CogniPath)

Owner: Elham Pournouri

The Career Agent finds job, internship and thesis opportunities, compares them with the
student's CV skills, and proposes career activities (learn / apply / attend) with values
for three objectives (study, career, social). It sends them to the Planner through the
team's shared API as a `ProposalBatch`.

The agent only advises and prepares. The student decides and applies.
No scraping and no automatic applications.

## Architecture

- `src/pipeline.py`: runs intake, then the 4 sub-agents (collector → extractor → matcher → advisor)
- `src/planner_client.py`: sends the `ProposalBatch` to the shared Planner API (`POST /proposals/batch`)
- `src/event_client.py`: reads upcoming events from the Event Agent API (`GET /events`, port 8002); falls back to `data/events.json` when it is not running
- `src/api.py`: Career Agent FastAPI (port **8001**), docs at http://127.0.0.1:8001/docs
- `src/app.py`: Streamlit UI (port 8501), calls the Career API
- `src/application_graph.py`: LangGraph flow that prepares a cover letter and tailored CV (with user approval)
- PostgreSQL database (schemas `shared` and `career`, see `db/schema.sql`)
- `ontology/career.owl` + `ontology/skill_hierarchy.ttl` + ESCO for skills (private to the Career Agent)
- Optional LLM explanations for the top matches (`LLM_PROVIDER` = `claude` or `ollama`)

## Algorithm (9 steps)

1. **Job collection**: job alert emails (Gmail) and public Teamtailor feeds (`data/ats_companies.json`)
2. **Job extraction**: title, company, location and required skills from each posting
3. **Database storage**: postings saved in PostgreSQL
4. **Skill extraction**: skills mapped to ESCO and the career ontology
5. **CV matching**: required skills compared with the skills read from the user's CV
6. **Scoring and ranking**: `match = matched required skills / all required skills`
7. **Recommendation**: activities with study / career / social values and skill gaps
8. **Application tracking**: planned, applied, interview, rejected, offer
9. **Planner integration**: one `ProposalBatch` (shared contract) sent to the Planner API

### Scoring (advisor)

All values are between 0 and 1.

| Activity | Career value | Study value | Social value |
|----------|--------------|-------------|--------------|
| Apply for a job | `A1 × (0.375 + 0.625 × A2)` | 0 | 0 |
| Learn a missing skill | `0.375 × L1 + 0.625 × L2` | 0.9 / 0.6 / 0.3 | 0 |
| Attend an event | `0.5 × C1 + 0.3 × C2 + 0.2 × C3` | 0 | `0.3 + 0.7 × matched topics / all topics` |

- `A1` = skill match of the job, `A2` = best ESCO relevance of its skills to the career goal
- `L1` = share of the job's skill gap this skill closes, `L2` = ESCO relevance of the skill to the goal
- `C1` = a target company attends, `C2` = share of missing skills the event covers, `C3` = topic relevance to the goal
- Study value: 0.9 = the thesis concept itself, 0.6 = one step from the thesis or a course, 0.3 = general skill
- Weights come from swing weighting (goal 100, gap 60; company 100, gaps 60, goal 40)
- Jobs below 40 % match are skipped (`MIN_APPLY = 0.40`), but the best 3 are always kept (`KEEP_AT_LEAST = 3`)

## Setup

~~~
cd agents/career_agent
pip install -r requirements.txt
copy .env.example .env    # then fill in your own values
~~~

For the shared team backend (from the repository root):
~~~
pip install -r agents/planner_agent/requirements.txt
~~~

## Run

Terminal 1, shared team backend with the Planner API (repository root, port 8000):
~~~
uvicorn backend.main:app --reload
~~~

Terminal 2, Career Agent API (port 8001):
~~~
cd agents/career_agent/src
uvicorn api:app --reload --port 8001
~~~

Terminal 3, team frontend (Next.js, port 3000, needs Node.js 20.19 or newer):
~~~
cd frontend
npm install
npm run dev
~~~
Open http://localhost:3000/career (menu item **Career Agent**) for preferences, CV upload,
job search, applications and the calendar. The **Internship matches** card on
http://localhost:3000/cognipath also reads from the Career API (matches and cover letter).
Choose the student in the left menu (field **Student**). The frontend calls the Career API at
`NEXT_PUBLIC_CAREER_URL` (default `http://127.0.0.1:8001`).

Optional, the older Streamlit UI (port 8501):
~~~
cd agents/career_agent/src
python -m streamlit run app.py
~~~

Pipeline only (test user):
~~~
cd agents/career_agent/src
python pipeline.py mira
~~~
At the end it prints `Sent to Planner API: {'stored': N, 'source_agent': 'career'}`.
Check the result at http://127.0.0.1:8000/docs → `GET /proposals` with `user_id=mira`.

## Sub-agents

| Step | File | Role |
|------|------|------|
| Intake | `src/gmail_fetch.py`, `src/job_emails.py` | Reads job alert emails into the database |
| Intake (per user) | `src/jooble_source.py` | Searches the Jooble API with the target title (or CV skills); needs `JOOBLE_API_KEY` |
| 1. Collector | `src/subagents/collector.py` | Loads postings that fit the user profile |
| 2. Extractor | `src/subagents/extractor.py` | Builds the skill graph with the ontology and ESCO |
| 3. Matcher | `src/subagents/matcher.py` | Scores matches and finds skill gaps (SPARQL) |
| 4. Advisor | `src/subagents/advisor.py` | Builds the `ProposalBatch` and sends it to the Planner |

## Interfaces with other agents

- **Planner ← Career (API)**: `POST {PLANNER_URL}/proposals/batch` with a `ProposalBatch`
  (`shared/contracts/activity_proposal.py`). `PLANNER_URL` is set in `.env`
  (default `http://127.0.0.1:8000`). If the server is not running, the advisor prints a
  warning and the pipeline continues.
- **Fallback file**: the same batch is also saved to `data/career_plan.json` until the
  Planner reads only from the API.
- **Tutor ← skill gaps**: `data/skill_gaps.json` (missing skills and learning resources)
- **Event → events**: `data/events.json` (`name`, `date`, `companies`, `topics`)

## Career Agent API (port 8001)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/profile/{user_id}` | Save job preferences |
| POST | `/cv/{user_id}` | Upload a PDF CV and read its skills |
| POST | `/run/{user_id}` | Run the whole pipeline |
| GET | `/plan/{user_id}` | The user's latest career plan |
| POST | `/apply/{user_id}/start` | Start preparing a cover letter and CV |
| GET | `/profile/{user_id}` | Read saved job preferences |
| GET | `/matches/{user_id}` | Best matches with skill gaps, deadline and tracker status |
| GET | `/jobs/{user_id}?q=` | Search all postings (match score and tracker status per job) |
| POST | `/apply/{user_id}/{job_id}/answer` | Answer the current pause (yes, changes, download) |
| GET | `/apply/{user_id}/{job_id}/file/{kind}` | Download the cover letter or tailored CV (.docx) |
| GET / POST / PATCH | `/tracker/{user_id}` | Application tracker |
| GET | `/calendar/{user_id}` | Apply deadlines and interviews as an .ics file |

## Privacy

- Personal CVs, letters, job emails, career plans and `user_profile.json` are not stored in Git.
- Contact information is never sent to the LLM.
- Use only test users (for example `mira`) for demos.

## Ontology

Namespace: `https://example.org/cognipath/career#`
Main classes: Student, Skill, CareerOpportunity (Internship, Job, ThesisOpportunity),
LearningResource, CareerPlan, CareerActivity.
