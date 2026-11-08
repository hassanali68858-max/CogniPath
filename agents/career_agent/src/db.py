import json
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Load DATABASE_URL from agents/career_agent/.env
load_dotenv(Path(__file__).resolve().parents[1] / ".env")
engine = create_engine(os.environ["DATABASE_URL"])


def ensure_user(user_id, name=None, email=None):
    """Add the user to shared.users if they are not there yet."""
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO shared.users (user_id, name, email) "
            "VALUES (:uid, :name, :email) ON CONFLICT (user_id) DO NOTHING"
        ), {"uid": user_id, "name": name, "email": email})


def save_postings(postings):
    """Insert or update job postings (one row per title + company)."""
    with engine.begin() as conn:
        for p in postings:
            conn.execute(text(
                "INSERT INTO career.job_postings "
                "(title, company, type, url, description, skills) "
                "VALUES (:title, :company, :type, :url, :description, CAST(:skills AS JSONB)) "
                "ON CONFLICT (title, company) DO UPDATE SET "
                "type = EXCLUDED.type, url = EXCLUDED.url, "
                "description = EXCLUDED.description, skills = EXCLUDED.skills"
            ), {
                "title": p["title"], "company": p["company"], "type": p.get("type"),
                "url": p.get("url"), "description": p.get("description"),
                "skills": json.dumps(p.get("skills", [])),
            })


def load_postings():
    """Return all job postings as a list of dicts."""
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT * FROM career.job_postings ORDER BY job_posting_id"))
        return [dict(r._mapping) for r in rows]

def known_urls():
    """Return the set of job URLs already in the database."""
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT url FROM career.job_postings WHERE url IS NOT NULL"
        ))
        return {r.url for r in rows}

def save_matches(user_id, matches):
    """Save match results (score + missing skills) for one user."""
    with engine.begin() as conn:
        for m in matches:
            # Find the posting id by its title
            posting_id = conn.execute(text(
                "SELECT job_posting_id FROM career.job_postings WHERE title = :title"
            ), {"title": m["title"]}).scalar()
            if posting_id is None:
                continue  # posting not in the database yet
            conn.execute(text(
                "INSERT INTO career.matches (user_id, job_posting_id, score, missing_skills) "
                "VALUES (:uid, :pid, :score, CAST(:missing AS JSONB)) "
                "ON CONFLICT (user_id, job_posting_id) DO UPDATE SET "
                "score = EXCLUDED.score, missing_skills = EXCLUDED.missing_skills"
            ), {"uid": user_id, "pid": posting_id, "score": m["score"],
                "missing": json.dumps([x["skill"] for x in m["missing"]])})
def cache_get(key):
    """Return cached JSON data for a key, or None if not cached."""
    with engine.connect() as conn:
        return conn.execute(text(
            "SELECT data FROM career.esco_cache WHERE key = :key"
        ), {"key": key}).scalar()


def cache_set(key, data):
    """Store JSON data for a key (insert or replace)."""
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO career.esco_cache (key, data) VALUES (:key, CAST(:data AS JSONB)) "
            "ON CONFLICT (key) DO UPDATE SET data = EXCLUDED.data"
        ), {"key": key, "data": json.dumps(data)})

def save_cv(user_id, file_path, cv_text, skills):
    """Store a CV (path, extracted text and skills) for a user."""
    ensure_user(user_id)
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO career.cvs (user_id, file_path, extracted_text, skills) "
            "VALUES (:uid, :path, :text, CAST(:skills AS JSONB))"
        ), {"uid": user_id, "path": str(file_path), "text": cv_text,
            "skills": json.dumps(skills)})


def latest_cv_skills(user_id):
    """Return the skills from the user's most recent CV, or [] if none."""
    with engine.connect() as conn:
        skills = conn.execute(text(
            "SELECT skills FROM career.cvs WHERE user_id = :uid "
            "ORDER BY uploaded_at DESC LIMIT 1"
        ), {"uid": user_id}).scalar()
    return skills or []
def save_cover_letter(user_id, job_posting_id, letter):
    """Save an approved cover letter; create the application if needed. Returns (application_id, version)."""
    ensure_user(user_id)
    params = {"uid": user_id, "jid": job_posting_id}
    with engine.begin() as conn:
        app_id = conn.execute(text(
            "SELECT application_id FROM career.applications "
            "WHERE user_id = :uid AND job_posting_id = :jid"
        ), params).scalar()
        if app_id is None:
            # 'planned' = the student plans to apply; nothing is sent automatically
            app_id = conn.execute(text(
                "INSERT INTO career.applications (user_id, job_posting_id) "
                "VALUES (:uid, :jid) RETURNING application_id"
            ), params).scalar()
        version = conn.execute(text(
            "SELECT COALESCE(MAX(version), 0) + 1 FROM career.cover_letters "
            "WHERE application_id = :aid"
        ), {"aid": app_id}).scalar()
        conn.execute(text(
            "INSERT INTO career.cover_letters (application_id, text, version, approved) "
            "VALUES (:aid, :letter, :v, TRUE)"
        ), {"aid": app_id, "letter": letter, "v": version})
    return app_id, version

def load_tracker(user_id):
    """Return the user's applications with job, match and interview info (newest first)."""
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT a.application_id, j.title, j.company, m.score AS match, "
            # The application's own deadline wins; otherwise use the posting's
            "COALESCE(a.deadline, j.deadline) AS deadline, a.status, "
            "a.interview_invited, a.accepted, a.interview_date "
            "FROM career.applications a "
            "JOIN career.job_postings j ON j.job_posting_id = a.job_posting_id "
            "LEFT JOIN career.matches m "
            "ON m.user_id = a.user_id AND m.job_posting_id = a.job_posting_id "
            "WHERE a.user_id = :uid ORDER BY a.application_id DESC"
        ), {"uid": user_id})
        return [dict(r._mapping) for r in rows]

def add_application(user_id, job_posting_id, status="planned"):
    """Add a recommended job to the tracker. Returns the application_id."""
    with engine.begin() as conn:
        # Do not add the same job twice for the same user
        row = conn.execute(text(
            "SELECT application_id FROM career.applications "
            "WHERE user_id = :uid AND job_posting_id = :jid"
        ), {"uid": user_id, "jid": job_posting_id}).first()
        if row:
            return row[0]
        new_id = conn.execute(text(
            "INSERT INTO career.applications (user_id, job_posting_id, status) "
            "VALUES (:uid, :jid, :st) RETURNING application_id"
        ), {"uid": user_id, "jid": job_posting_id, "st": status}).scalar()
        return new_id
    
def load_recommendations(user_id):
    """Return scored jobs, adjusted by feedback, best first; hide disliked."""
    weights = feedback_skill_weights(user_id)
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT j.job_posting_id, j.title, j.company, m.score, "
            "m.missing_skills, j.url, j.skills, f.liked "
            "FROM career.matches m "
            "JOIN career.job_postings j ON j.job_posting_id = m.job_posting_id "
            "LEFT JOIN career.feedback f "
            "  ON f.job_posting_id = m.job_posting_id AND f.user_id = m.user_id "
            "WHERE m.user_id = :uid AND f.liked IS NOT FALSE"
        ), {"uid": user_id})
        jobs = [dict(r._mapping) for r in rows]
    for job in jobs:
        job["base"] = job["score"]  # Keep the original match score                
        bonus = 0.02 * sum(weights.get(s, 0) for s in (job["skills"] or []))
        bonus = max(-0.10, min(0.10, bonus))  # Likes can move the score by at most 10%
        job["score"] = min(1.0, max(0.0, job["score"] + bonus))
    jobs.sort(key=lambda j: (j["liked"] is True, j["score"]), reverse=True)
    return jobs

# Only these columns may be changed from the tracker
TRACKER_FIELDS = {"status", "deadline", "applied_at",
                  "interview_invited", "accepted", "interview_date"}


def update_application(application_id, **fields):
    """Update tracker fields of one application, e.g. status='applied'."""
    bad = set(fields) - TRACKER_FIELDS
    if bad:
        raise ValueError(f"Not a tracker field: {bad}")
    if not fields:
        return
    # Column names come only from TRACKER_FIELDS, values are bound safely
    sets = ", ".join(f"{name} = :{name}" for name in fields)
    with engine.begin() as conn:
        conn.execute(text(
            f"UPDATE career.applications SET {sets} WHERE application_id = :aid"
        ), {**fields, "aid": application_id})

def save_feedback(user_id, job_posting_id, liked, reason=None):
    """Store a like/dislike for a job. A new vote replaces the old one."""
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO career.feedback (user_id, job_posting_id, liked, reason) "
            "VALUES (:uid, :jid, :liked, :reason) "
            "ON CONFLICT (user_id, job_posting_id) "
            "DO UPDATE SET liked = EXCLUDED.liked, reason = EXCLUDED.reason, "
            "created_at = now()"
        ), {"uid": user_id, "jid": job_posting_id, "liked": liked, "reason": reason})

def feedback_skill_weights(user_id):
    """Count skills in liked (+1) and disliked (-1) jobs."""
    weights = {}
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT j.skills, f.liked FROM career.feedback f "
            "JOIN career.job_postings j ON j.job_posting_id = f.job_posting_id "
            "WHERE f.user_id = :uid AND j.skills IS NOT NULL"
        ), {"uid": user_id})
        for skills, liked in rows:
            for s in skills:
                weights[s] = weights.get(s, 0) + (1 if liked else -1)
    return weights

def save_user_profile(user_id, countries, job_types, work_mode, target_title, interests):
    """Insert or update one user's job preferences in career.user_profiles."""
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO career.user_profiles
                (user_id, countries, job_types, work_mode, target_title, interests, updated_at)
            VALUES (:user_id, :countries, :job_types, :work_mode, :target_title, :interests, now())
            ON CONFLICT (user_id) DO UPDATE SET
                countries = EXCLUDED.countries,
                job_types = EXCLUDED.job_types,
                work_mode = EXCLUDED.work_mode,
                target_title = EXCLUDED.target_title,
                interests = EXCLUDED.interests,
                updated_at = now()
        """), {
            "user_id": user_id, "countries": countries, "job_types": job_types,
            "work_mode": work_mode, "target_title": target_title, "interests": interests,
        })

def load_user_profile(user_id):
    """Return one user's job preferences as a dict, or None if not saved yet."""
    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT * FROM career.user_profiles WHERE user_id = :user_id"
        ), {"user_id": user_id}).mappings().first()
    return dict(row) if row else None

if __name__ == "__main__":
    for p in load_postings():
        print(p["job_posting_id"], p["title"], "-", p["company"], p["skills"])
    with engine.connect() as conn:
        for row in conn.execute(text("SELECT * FROM career.matches")):
            print("match:", dict(row._mapping))