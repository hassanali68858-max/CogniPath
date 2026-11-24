import json
import re
import subprocess
import sys
from pathlib import Path

from application_graph import graph as app_graph
from cv_reader import CV_DIR, clean_skills, extract_profile, fix_skill_names, read_pdf_text
from db import add_application, load_postings, load_tracker, save_cv, save_user_profile, update_application
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from langgraph.types import Command
from pydantic import BaseModel

SRC_DIR = Path(__file__).resolve().parent
# Plans are written by advisor.py, one file per user
DATA_DIR = SRC_DIR.parent / "data"


app = FastAPI(title="CogniPath Career Agent API")

# Allow the team's Next.js frontend (port 3000) to call this API from the browser
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class Profile(BaseModel):
    """Job preferences a CV cannot tell us."""
    countries: list[str]
    job_types: list[str]
    work_mode: str = "any"
    target_title: str = ""
    interests: list[str] = []


def safe_name(user_id: str) -> str:
    """Keep only letters, digits, - and _ so a user id can never change the folder."""
    return re.sub(r"[^A-Za-z0-9_-]", "", user_id)


@app.get("/")
def home():
    """Simple check that the API is running."""
    return {"status": "ok"}


@app.post("/profile/{user_id}")
def save_profile(user_id: str, profile: Profile):
    """Save job preferences of this user in the database."""
    if not profile.countries or not profile.job_types:
        raise HTTPException(status_code=400, detail="Country and job type are required.")
    save_user_profile(user_id, profile.countries, profile.job_types,
                      profile.work_mode, profile.target_title, profile.interests)
    return {"status": "saved", "user_id": user_id}


@app.post("/cv/{user_id}")
def upload_cv(user_id: str, file: UploadFile = File(...)):  # noqa: B008 (normal FastAPI style)
    """Save the uploaded PDF CV, read its skills and store them in the database."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Please upload a PDF file.")
    name = safe_name(user_id)
    if not name:
        raise HTTPException(status_code=400, detail="Invalid user id.")

    # Same steps as running cv_reader.py, but the file comes from the browser
    CV_DIR.mkdir(parents=True, exist_ok=True)
    cv_path = CV_DIR / f"{name}-cv.pdf"
    cv_path.write_bytes(file.file.read())

    text = read_pdf_text(cv_path)
    if not text:
        raise HTTPException(status_code=400, detail="Could not read any text from this PDF.")
    skills = clean_skills(extract_profile(text).get("skills", []))
    skills = fix_skill_names(skills)
    save_cv(user_id, cv_path, text, skills)
    return {"status": "saved", "user_id": user_id, "skills": skills}


@app.get("/plan/{user_id}")
def get_plan(user_id: str):
    """Return the career plan of this user (data/career_plan_<user_id>.json)."""
    plan_file = DATA_DIR / f"career_plan_{user_id}.json"
    if not plan_file.exists():
        raise HTTPException(status_code=404, detail=f"No plan for user '{user_id}'. Run the pipeline first.")
    return json.loads(plan_file.read_text(encoding="utf-8"))


@app.post("/run/{user_id}")
def run_pipeline(user_id: str):
    """Run the whole pipeline for this user (same as: python pipeline.py <user_id>)."""
    result = subprocess.run(
        [sys.executable, str(SRC_DIR / "pipeline.py"), user_id],
        cwd=SRC_DIR, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if result.returncode != 0:
        # Send the last part of the output so the user can see what failed
        raise HTTPException(status_code=500, detail=result.stdout[-1500:] + result.stderr[-1500:])
    return {"status": "done", "user_id": user_id}

# ---------- Prepare application (cover letter + tailored CV) ----------

class StartApply(BaseModel):
    title: str          # job title from the Apply card


class Answer(BaseModel):
    answer: str         # user's reply to the current pause (yes / feedback / download ...)


def app_config(user_id, job_id):
    # One graph thread per user and job, so pauses are remembered
    return {"configurable": {"thread_id": f"{user_id}-{job_id}"}}


def app_reply(job_id, result):
    """Return either the current pause (question for the user) or the finished files."""
    if "__interrupt__" in result:
        return {"status": "waiting", "job_id": job_id,
                "step": result["__interrupt__"][0].value}
    return {"status": "done", "job_id": job_id,
            "has_letter": bool(result.get("docx_path")),
            "has_cv": bool(result.get("cv_path"))}


@app.post("/apply/{user_id}/start")
def apply_start(user_id: str, body: StartApply):
    # Find the job id from the title shown on the Apply card
    job = next((p for p in load_postings() if p["title"] == body.title), None)
    if job is None:
        raise HTTPException(404, f"Job '{body.title}' not found")
    job_id = job["job_posting_id"]
    result = app_graph.invoke({"user_id": user_id, "job_posting_id": job_id},
                              app_config(user_id, job_id))
    return app_reply(job_id, result)


@app.post("/apply/{user_id}/{job_id}/answer")
def apply_answer(user_id: str, job_id: int, body: Answer):
    # Resume the paused graph with the user's answer
    result = app_graph.invoke(Command(resume=body.answer), app_config(user_id, job_id))
    return app_reply(job_id, result)


@app.get("/apply/{user_id}/{job_id}/file/{kind}")
def apply_file(user_id: str, job_id: int, kind: str):
    # Paths come from the graph state, never from the URL (safer)
    values = app_graph.get_state(app_config(user_id, job_id)).values
    key = {"letter": "docx_path", "cv": "cv_path"}.get(kind)
    if key is None or not values.get(key):
        raise HTTPException(404, "File not ready")
    path = values[key]
    return FileResponse(path, filename=Path(path).name)

# ---------- Application tracker (the user applies, we only record it) ----------

TRACK_STATUSES = ["planned", "applied", "interview", "rejected", "offer"]


class AddToTracker(BaseModel):
    title: str              # job title from the Apply card
    applied: bool = False   # True = user already applied


class TrackerUpdate(BaseModel):
    status: str
    interview_date: str | None = None   # YYYY-MM-DD, optional


@app.get("/tracker/{user_id}")
def get_tracker(user_id: str):
    """Return all applications of this user."""
    return load_tracker(user_id)


@app.post("/tracker/{user_id}")
def tracker_add(user_id: str, body: AddToTracker):
    """Add a job from the plan to the tracker."""
    # Do not add the same job twice: return the existing row instead
    for row in load_tracker(user_id):
        if row["title"] == body.title:
            return {"status": "exists", "application_id": row["application_id"]}
    from datetime import date
    job = next((p for p in load_postings() if p["title"] == body.title), None)
    if job is None:
        raise HTTPException(404, f"Job '{body.title}' not found")
    app_id = add_application(user_id, job["job_posting_id"])
    if body.applied:
        update_application(app_id, status="applied", applied_at=date.today())
    return {"status": "added", "application_id": app_id}


@app.patch("/tracker/{user_id}/{app_id}")
def tracker_update(user_id: str, app_id: int, body: TrackerUpdate):
    """Change the status of one application (same rules as the terminal tracker)."""
    from datetime import date
    # Only allow changing this user's own applications
    if not any(r["application_id"] == app_id for r in load_tracker(user_id)):
        raise HTTPException(404, "Application not found for this user")
    if body.status not in TRACK_STATUSES:
        raise HTTPException(400, f"Status must be one of {TRACK_STATUSES}")
    fields = {"status": body.status}
    if body.status == "applied":
        fields["applied_at"] = date.today()
    if body.status == "interview":
        fields["interview_invited"] = True
        if body.interview_date:
            fields["interview_date"] = body.interview_date
    if body.status == "offer":
        fields["accepted"] = "yes"
    if body.status == "rejected":
        fields["accepted"] = "no"
    update_application(app_id, **fields)
    return {"status": "updated", "application_id": app_id}

@app.get("/matches/{user_id}")
def get_matches(user_id: str, limit: int = 3):
    """Return the best job matches in the shape the team frontend card expects."""
    from db import load_recommendations

    def squash(name):
        # "Quality Control" and "QualityControl" both become "qualitycontrol"
        return re.sub(r"[^a-z0-9]", "", name.lower())

    # Deadline of each posting, and the user's tracker status for each job title
    deadlines = {p["job_posting_id"]: p["deadline"] for p in load_postings()}
    tracked = {r["title"]: r for r in load_tracker(user_id)}

    result = []
    for job in load_recommendations(user_id)[:limit]:
        skills = job["skills"] or []
        missing_keys = {squash(s) for s in (job["missing_skills"] or [])}
        # Readable names (with spaces) come from the job's skill list
        matched = [s for s in skills if squash(s) not in missing_keys]
        missing = [s for s in skills if squash(s) in missing_keys]
        deadline = deadlines.get(job["job_posting_id"])
        row = tracked.get(job["title"])
        result.append({
            "id": str(job["job_posting_id"]),
            "org": job["company"],
            "title": job["title"],
            "deadline": deadline.isoformat() if deadline else "not given",
            "match": round(job["score"] * 100),
            "matchedSkills": matched,
            "missingSkills": missing,
            "coverLetter": "",
            "status": row["status"] if row else None,
        })
    return result


# ---------- More endpoints for the team frontend (Career Agent page) ----------

@app.get("/profile/{user_id}")
def get_profile(user_id: str):
    """Return the saved job preferences of this user (empty values if none yet)."""
    from db import load_user_profile
    p = load_user_profile(user_id)
    if p is None:
        return {"countries": [], "job_types": [], "work_mode": "any",
                "target_title": "", "interests": [], "saved": False}
    return {"countries": p["countries"] or [], "job_types": p["job_types"] or [],
            "work_mode": p["work_mode"] or "any", "target_title": p["target_title"] or "",
            "interests": p["interests"] or [], "saved": True}


@app.get("/jobs/{user_id}")
def search_jobs(user_id: str, q: str = "", limit: int = 50):
    """Search the jobs the Career Agent found for this user (the ones with a match score),
    plus jobs the user already tracks. A new user sees nothing until the agent has run."""
    from db import load_recommendations
    scores = {j["job_posting_id"]: j["score"] for j in load_recommendations(user_id)}
    tracked = {r["title"]: r for r in load_tracker(user_id)}
    words = q.lower().split()
    jobs = []
    for p in load_postings():
        # Search in title, company, description and skills; every word must appear
        text = " ".join([p["title"], p["company"], p.get("description") or "",
                         " ".join(p["skills"] or [])]).lower()
        if not all(w in text for w in words):
            continue
        score = scores.get(p["job_posting_id"])
        row = tracked.get(p["title"])
        if score is None and row is None:
            continue  # collected for another user: not shown here
        jobs.append({
            "id": p["job_posting_id"],
            "title": p["title"],
            "company": p["company"],
            "summary": p.get("summary"),  # one sentence written by the enricher
            "url": p.get("url"),
            "deadline": p["deadline"].isoformat() if p.get("deadline") else None,
            "match": round(score * 100) if score is not None else None,
            "status": row["status"] if row else None,
            "application_id": row["application_id"] if row else None,
        })
    # Best matches first; jobs without a score at the end
    jobs.sort(key=lambda j: j["match"] if j["match"] is not None else -1, reverse=True)
    return jobs[:limit]


def ics_file(events, filename):
    """Wrap calendar events into one downloadable .ics file."""
    from fastapi.responses import Response
    body = ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//CogniPath//Career Agent//EN\r\n"
            + "".join(events) + "END:VCALENDAR\r\n")
    return Response(body, media_type="text/calendar",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@app.get("/calendar/{user_id}")
def get_calendar(user_id: str):
    """Download apply deadlines and interview dates as an .ics file (Outlook, Google Calendar).
    Includes tracked applications AND the jobs the agent found for the user."""
    from datetime import date

    from calendar_export import ics_event
    from db import load_recommendations
    events = []
    tracked_titles = set()
    for r in load_tracker(user_id):
        tracked_titles.add(r["title"])
        name = f"{r['title']} @ {r['company']}"
        if r["deadline"] and r["status"] == "planned":
            events.append(ics_event(f"deadline-{r['application_id']}", r["deadline"], f"Apply deadline: {name}"))
        if r["interview_date"]:
            events.append(ics_event(f"interview-{r['application_id']}", r["interview_date"], f"Interview: {name}"))
    # Found jobs that are not tracked yet but have a deadline in the ad
    deadlines = {p["job_posting_id"]: p["deadline"] for p in load_postings()}
    for j in load_recommendations(user_id):
        day = deadlines.get(j["job_posting_id"])
        if day and day >= date.today() and j["title"] not in tracked_titles:
            label = f"Apply deadline: {j['title']} @ {j['company']} ({round(j['score'] * 100)}% match)"
            events.append(ics_event(f"job-{j['job_posting_id']}-{safe_name(user_id)}", day, label))
    return ics_file(events, f"career_{safe_name(user_id)}.ics")


@app.get("/calendar/{user_id}/job/{job_id}")
def get_job_calendar(user_id: str, job_id: int):
    """Download the apply deadline of ONE job as an .ics file (the calendar button on a job card)."""
    from calendar_export import ics_event
    job = next((p for p in load_postings() if p["job_posting_id"] == job_id), None)
    if job is None or not job.get("deadline"):
        raise HTTPException(404, "This job has no deadline in the ad")
    event = ics_event(f"job-{job_id}-{safe_name(user_id)}", job["deadline"],
                      f"Apply deadline: {job['title']} @ {job['company']}")
    return ics_file([event], f"deadline_{job_id}.ics")
