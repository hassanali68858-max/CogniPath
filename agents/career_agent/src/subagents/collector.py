import json
from pathlib import Path
from datetime import datetime, timedelta, timezone
import re
DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def load_postings(path):
    text = Path(path).read_text(encoding="utf-8")
    postings = json.loads(text)          
    return postings

def filter_recent(postings, now, hours=24):
    recent = []
    for p in postings:
        posted = datetime.fromisoformat(p["posted_at"].replace("Z", "+00:00"))
        if now - posted < timedelta(hours=hours):               
            recent.append(p)
    return recent

def filter_title(postings, wanted):
    if wanted == "any":
        return postings
    pattern = re.compile(rf"\b{re.escape(wanted)}\b", re.IGNORECASE)
    return [p for p in postings if pattern.search(p["title"])]    
def matches_any(value, wanted):
    return wanted == "any" or value in wanted


def filter_location(postings, profile):
    result = []
    for p in postings:
        if not matches_any(p["work_mode"], profile["work_mode"]):
            continue
        if p["work_mode"] == "remote":
            result.append(p)
            continue
        if not matches_any(p["country"], profile["countries"]):
            continue
        if profile["city"] and p["city"].lower() != profile["city"].lower():
            continue
        result.append(p)
    return result
def filter_opportunity_type(postings, profile):
    result = []
    for p in postings:
        if not matches_any(p["type"], profile["opportunity_type"]):
            continue
        result.append(p)
    return result
if __name__ == "__main__":
    postings = load_postings(DATA_DIR / "sample_postings.json")
    now = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)
    postings = filter_recent(postings, now)
    profile = json.loads((DATA_DIR / "user_profile.json").read_text(encoding="utf-8"))
    postings = filter_title(postings, profile["title"])
    postings = filter_location(postings, profile)
    postings = filter_opportunity_type(postings, profile)
    for p in postings:
        print(f"{p['title']} - {p['company']}")
    out = DATA_DIR / "raw_postings.json"
    out.write_text(json.dumps(postings, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved {len(postings)} postings to {out.name}")