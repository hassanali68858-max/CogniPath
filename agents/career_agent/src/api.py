import json
import re
import subprocess
import sys
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel

from fastapi.responses import FileResponse
from langgraph.types import Command

from db import save_user_profile, save_cv, load_postings, load_tracker, add_application, update_application
from cv_reader import CV_DIR, read_pdf_text, extract_profile, clean_skills, fix_skill_names
from application_graph import graph as app_graph

SRC_DIR = Path(__file__).resolve().parent
# Plans are written by advisor.py, one file per user
DATA_DIR = SRC_DIR.parent / "data"

app = FastAPI(title="CogniPath Career Agent API")


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
def upload_cv(user_id: str, file: UploadFile = File(...)):
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