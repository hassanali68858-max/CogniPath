import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # src/, for db.py
from db import latest_cv_skills, load_user_profile
from db import load_postings as load_db_postings  # postings saved in PostgreSQL

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def filter_recent(postings, now, hours=24):
    recent = []
    for p in postings:
        # Unknown date -> keep the posting (unknown is not "too old")
        if not p.get("posted_at"):
            recent.append(p)
            continue
        posted = datetime.fromisoformat(p["posted_at"].replace("Z", "+00:00"))
        if now - posted < timedelta(hours=hours):
            recent.append(p)
    return recent


def filter_title(postings, wanted):
    if wanted == "any":
        return postings
    # Match if any word of the target title appears in the posting title
    words = [re.escape(w) for w in wanted.split()]
    pattern = re.compile(rf"\b({'|'.join(words)})\b", re.IGNORECASE)
    return [p for p in postings if pattern.search(p["title"])]

def squash(text):
    """Simple name without spaces/case, e.g. 'Deep Learning' -> 'deeplearning'."""
    return "".join(c for c in str(text).lower() if c.isalnum())


def filter_title_or_skills(postings, title, user_skills):
    """Keep a posting if its title matches OR it shares a skill with the user."""
    by_title = filter_title(postings, title)
    have = {squash(s) for s in user_skills}
    result = []
    for p in postings:
        shared = have & {squash(s) for s in (p.get("skills") or [])}
        if p in by_title or shared:
            result.append(p)
    return result


def matches_any(value, wanted):
    # Unknown value -> keep the posting
    return wanted == "any" or value is None or value in wanted


def filter_location(postings, profile):
    result = []
    for p in postings:
        work_mode = p.get("work_mode")
        if not matches_any(work_mode, profile["work_mode"]):
            continue
        if work_mode == "remote":
            result.append(p)
            continue
        if not matches_any(p.get("country"), profile["countries"]):
            continue
        city = p.get("city")
        if profile["city"] and city and city.lower() != profile["city"].lower():
            continue
        result.append(p)
    return result


# Internship-like choices; everything else counts as a normal job
INTERN_TYPES = {"internship", "thesis"}


def filter_opportunity_type(postings, profile):
    wanted = profile["opportunity_type"]
    # Filter only if the user chose ONLY internship/thesis; otherwise keep all
    if wanted == "any" or not set(wanted) <= INTERN_TYPES:
        return postings
    return [p for p in postings if p.get("type") in (None, "internship")]


if __name__ == "__main__":
    # Usage: python subagents\collector.py <user_id>
    user_id = sys.argv[1] if len(sys.argv) > 1 else input("User ID: ").strip()
    row = load_user_profile(user_id)
    if row is None:
        sys.exit(f"No profile for {user_id!r}. Fill in the form first: streamlit run onboarding.py")

    # Map table columns to the keys the filters expect
    profile = {
        "title": row.get("target_title") or "any",
        "work_mode": row.get("work_mode") or "any",
        "countries": row.get("countries") or "any",
        "city": row.get("city"),  # not in the table yet -> None
        "opportunity_type": row.get("job_types") or "any",
    }

    # All postings from the database (Teamtailor, emails, ...)
    postings = load_db_postings()
    now = datetime.now(timezone.utc)

    print(f"Found {len(postings)} postings in the database (no date limit)")
     # Close matches count too: title match OR at least one shared skill
    user_skills = latest_cv_skills(user_id) or []
    postings = filter_title_or_skills(postings, profile["title"], user_skills)
    print(f"Found {len(postings)} postings for title '{profile['title']}' or your skills")
    postings = filter_location(postings, profile)
    print(f"Found {len(postings)} postings after filtering by location and work mode")
    postings = filter_opportunity_type(postings, profile)
    print(f"Found {len(postings)} postings after filtering by opportunity type")

    for p in postings:
        print(f"{p['title']} - {p['company']}")

    out = DATA_DIR / "raw_postings.json"
    out.write_text(json.dumps(postings, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"Saved {len(postings)} postings to {out.name}")