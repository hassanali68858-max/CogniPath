# CogniPath – Tutor Agent

The Tutor Agent helps students only. It has two sub-agents:

- **Course and Opportunity** (`course_opportunity/`) – follows the Sisu study plan and
  degree progress, recommends next-period courses, and finds summer schools, winter
  schools, Erasmus exchanges and forums that fit this student.
- **Quiz** (`quiz/`) – finds the student's weak topics in the current courses and builds
  personalised quizzes from the course topic graph.

`propose(profile, context)` returns `list[ActivityProposal]` for the Planner (see
[`agents/README.md`](../README.md)). `run(profile, context)` also returns the progress
report, the mastery of each current topic and the forum links for the frontend.

## Layout

| Path | What |
| --- | --- |
| `student.py` | `StudentProfile`; each field is marked "Sisu", "student" or "CogniPath" |
| `catalog.py` | Degree rules, courses, opportunities, topic graph, `TutorContext` |
| `seed.py` | Loads [`data/seed/tutor/`](../../data/seed/tutor/) |
| `sisu.py` | Live course data from JYU Sisu (public Kori API) for the linked seed courses |
| `tutor.py` | `run` and `propose`: calls both sub-agents |
| `course_opportunity/progress.py` | Credits per module, graduation pace, warnings, advisor meeting |
| `course_opportunity/courses.py` | "Register for course X" proposals |
| `course_opportunity/opportunities.py` | School and Erasmus application proposals, forum links |
| `course_opportunity/scoring.py` | Shared scoring rules and the 0–1 value rubric |
| `quiz/mastery.py` | Mastery per topic from the quiz history |
| `quiz/selection.py` | Which topics to quiz next |
| `quiz/spacing.py` | When a strong topic is due for a refresh quiz (spaced repetition) |
| `quiz/proposals.py` | Review and quiz proposals, with `depends_on` |
| `quiz/generator.py` | `QuestionGenerator` protocol and the template generator (no LLM) |
| `quiz/llm.py` | Ollama (local LLM) question generator, with the template generator as fallback |
| `quiz/attempt.py` | Build a quiz, grade it, record the result |
| `cli.py` | Command-line demo |
| `backend/tutor.py` | HTTP routes: report, quizzes, and send proposals to the Planner (see [backend README](../../backend/README.md)) |
| `frontend/app/tutor/` | The Tutor tab: progress, topics and quizzes, suggestions, communities |
| `tests/tutor_agent/` | Tests, including a run through the Planner |

## How it decides

The proposals follow the team's *CogniPath Shared Proposal Format* document:

- `value.study` uses the shared 0–1 rubric. Only courses that the degree requires get
  0.9: planned courses, mandatory courses, and prerequisites of needed courses.
  Opportunities are optional, so they get 0.6 at most. Quizzes get 0.6 for a weak topic
  and 0.3 for a first diagnostic quiz or a refresh quiz.
- There is no `priority`: `value` is the only measure of importance (see
  `shared/contracts/activity_proposal.py`). Deadlines are constraints.
- `reason` is one plain sentence.

Course and Opportunity:

- A course or opportunity is a candidate only if it is feasible. The language must
  match, the prerequisites must be done or in progress, and the deadline must fall
  within `lookahead_days`. An Erasmus semester must also not cover the only offering
  of a planned or mandatory course.
- The score combines degree value with interest fit. Degree value comes from the study
  plan, mandatory courses, missing prerequisites, and modules with missing credits.
  Interest fit counts the tags that the course shares with the student's interests.
  Each proposal's `reason` lists the rules that matched.
- The status is "at risk" if the student needs more than 60 ECTS per year to graduate
  on the target date. Then the agent proposes an advisor meeting.

Quiz:

- Mastery is an exponentially smoothed quiz score. A topic is weak below 60 %.
  The agent selects weak topics and topics without a quiz yet. Topics that have an
  exam in the planning horizon go first.
- A weak topic gets a review item and then a quiz. If a prerequisite topic is also
  selected, that topic is quizzed first. An exam inside the horizon sets the deadline
  to the day before the exam. Courses whose exam has passed are not quizzed.
- Spaced repetition (`quiz/spacing.py`): a strong topic gets a refresh quiz when it is due
  within the horizon. The gap grows with each quiz passed in a row (1, 3, 7, 14, then
  30 days); a failed quiz starts the run again. A refresh quiz has no review item, starts
  on its due day, and is worth 0.3. Refreshes have their own limit, so they never take
  the place of weak or untested topics, and topics that build on them do not wait for them.

The constants at the top of each module set these limits.

## Run the demo

From the repository root, after the setup in the [root README](../../README.md):

```bash
python -m agents.tutor_agent.cli propose --student student001 --today 2026-11-02 --out tutor_proposals.json
python -m agents.planner_agent.cli --proposals tutor_proposals.json \
  --profile tests/planner_agent/fixtures/mock_profile.json --start 2026-11-02 --days 14
python -m agents.tutor_agent.cli quiz --student student001 --topic rdf
```

In the app, open the **Tutor** tab (see the [frontend README](../../frontend/README.md)).
It uses the Planner demo dates. A quiz taken there changes the topic mastery and the
suggestions. **Send suggestions to the Planner** stores them for planning.

## LLM questions

By default, quizzes come from the template generator. To let a local
[Ollama](https://ollama.com) model write them (free, no API key):

```bash
brew install ollama
ollama serve &
ollama pull llama3.2
export TUTOR_QUESTION_GENERATOR=ollama
```

Then start the backend or the CLI in the same shell. The settings and their defaults are in
the docstring of [`quiz/llm.py`](quiz/llm.py). The model only sees the topic name and facts.
Questions that fail validation are dropped. A second call answers each question again,
and questions where the two answers differ are dropped. If Ollama is down or too few
questions pass, the template generator fills the quiz. With `llama3.2` (3B), some wrong
answer keys still pass the check, so the template generator stays the default.

## Sisu course data

The Tutor can take course data live from the University of Jyväskylä Sisu:

```bash
export TUTOR_CATALOG_SOURCE=sisu
```

Then start the backend or the CLI in the same shell. The backend loads the data once, so
restart it to get new data. [`data/seed/tutor/sisu_courses.json`](../../data/seed/tutor/sisu_courses.json)
links seed courses to real JYU courses. What Sisu replaces, and what happens when it cannot
answer, is in the docstring of [`sisu.py`](sisu.py). Sisu replaces the seed offerings
completely, so a course without published teaching in Sisu gets no registration proposal.

Only Sisu's public course API (Kori) is used. It needs no login and holds no personal data.
A student's completed courses, enrolments and study plan are in Sisu's Ori and Osuva APIs,
which answer `401` without a JYU login. Reading them needs integration credentials from JYU,
so students still come from the seed files.

## Next steps

- [ ] Ask JYU for Sisu integration credentials, then load the `StudentProfile` fields marked "Sisu" from Ori and Osuva
- [ ] Store quiz results in a database (the backend keeps them in memory until it restarts; the CLI does not save them)
- [ ] Quizzes from the student's own notes and slides
- [ ] Real opportunity sources (Erasmus partner lists, summer school listings, forums)
- [ ] Wrap `propose` as a node when the team adds orchestration (LangGraph)
