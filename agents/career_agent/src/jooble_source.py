import json
import os
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

import certifi
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))  # src/
from db import known_urls, latest_cv_skills, load_postings, load_user_profile, save_postings
from llm import ask_llm
from subagents.extractor import extract_skills
from teamtailor_source import guess_type, html_to_text

load_dotenv()

# Jooble REST API (official, free key from the Jooble API form). Keys are per country:
# a key from fi.jooble.org searches Finnish jobs.
API_KEY = os.getenv("JOOBLE_API_KEY", "")
# Each country has its own Jooble host: fi.jooble.org = Finland, jooble.org = USA
API_HOST = os.getenv("JOOBLE_HOST", "https://fi.jooble.org").rstrip("/")
# The country the key belongs to; used as the search location
LOCATION = os.getenv("JOOBLE_LOCATION", "Finland")
# Free plan: 100 requests per day. One run makes up to 5 searches x PAGES requests
PAGES = int(os.getenv("JOOBLE_PAGES", "1"))
PER_PAGE = 20


def search_jooble(keywords, page, location=LOCATION):
    """Ask the Jooble API for one page of jobs that match the keywords."""
    body = json.dumps({"keywords": keywords, "location": location, "page": page, "ResultOnPage": PER_PAGE}).encode("utf-8")
    request = urllib.request.Request(
        f"{API_HOST}/api/{API_KEY}", data=body,
        headers={"Content-Type": "application/json", "User-Agent": "CogniPath-CareerAgent/0.1"},
    )
    context = ssl.create_default_context(cafile=certifi.where())
    with urllib.request.urlopen(request, context=context, timeout=30) as response:
        return json.load(response)


def local_title(title):
    """The job title in the main language of job ads in LOCATION (asked from the LLM).
    Example: 'Architect' in Finland -> 'Arkkitehti'. Returns None if not different."""
    try:
        # Two small questions work better with a small local model than one long one
        language = ask_llm(f"What is the main official language of {LOCATION}? Answer with one word.")
        language = language.strip().split()[0].strip(".,") if language.strip() else ""
        if not language or language.lower() == "english":
            return None
        answer = ask_llm(f"Translate the job title '{title}' into {language}, "
                         f"as it is written in {language} job ads. Answer with the job title only.")
    except Exception as e:  # the LLM is optional here
        print(f"No translation for '{title}': {e}")
        return None
    lines = answer.strip().splitlines()
    word = lines[0].strip().strip('"\'.') if lines else ""
    if not word or word.lower() == title.lower() or len(word) > 60:
        return None
    return word


def search_words(user_id):
    """Searches for this user: the target title, the same title in the local language,
    and the first CV skills. Each one is a separate search, because Jooble needs ALL
    words of one search to match, and several skills together find almost nothing."""
    profile = load_user_profile(user_id) or {}
    searches = []
    title = (profile.get("target_title") or "").strip()
    if title:
        searches.append(title)
        translated = local_title(title)
        if translated:
            searches.append(translated)
    for skill in latest_cv_skills(user_id)[:3]:
        if skill.lower() not in {s.lower() for s in searches}:
            searches.append(skill)
    return searches


def to_posting(job):
    """Convert one Jooble result into the posting format used by save_postings."""
    description = html_to_text(job.get("snippet"))
    return {
        "title": job["title"].strip(),
        "company": (job.get("company") or "Unknown company").strip(),
        "type": guess_type(job["title"]),
        "url": job.get("link"),
        "description": description,
        "skills": extract_skills(f"{job['title']}. {description}"),  # skills found by the LLM
    }


if __name__ == "__main__":
    # Usage: python jooble_source.py <user_id>
    user_id = sys.argv[1] if len(sys.argv) > 1 else input("User ID: ").strip()
    if not API_KEY:
        print("JOOBLE_API_KEY is not set in .env, skipping Jooble.")
        sys.exit(0)
    searches = search_words(user_id)
    if not searches:
        print("No target title or CV skills for this user, skipping Jooble.")
        sys.exit(0)

    seen_urls = known_urls()
    # Same rule as the database: one row per title + company
    seen_keys = {(p["title"], p["company"]) for p in load_postings()}
    new_postings = []
    for keywords in searches:
        for page in range(1, PAGES + 1):
            try:
                answer = search_jooble(keywords, page)
            except urllib.error.HTTPError as e:
                # 403 = the key does not belong to this host's country, 429 = daily limit reached
                print(f"Jooble answered HTTP {e.code} for '{keywords}', stopping.")
                if e.code == 403:
                    print(f"The key does not work on {API_HOST}. Get a key on that site's /api/about page.")
                break
            jobs = answer.get("jobs", [])
            print(f"'{keywords}' page {page}: total in Jooble {answer.get('totalCount', 0)}, received {len(jobs)}")
            if not jobs and page == 1 and LOCATION:
                # Check: does the same search find jobs without a location?
                # If yes, the key belongs to another country, or the location name is not known.
                other = search_jooble(keywords, 1, location="")
                print(f"   same search without location: total {other.get('totalCount', 0)}"
                      + (f", first: {other['jobs'][0].get('title')} ({other['jobs'][0].get('location')})" if other.get("jobs") else ""))
            if not jobs:
                break
            for job in jobs:
                posting = to_posting(job)
                key = (posting["title"], posting["company"])
                if posting["url"] in seen_urls or key in seen_keys:
                    continue
                seen_keys.add(key)
                new_postings.append(posting)
    save_postings(new_postings)
    print(f"Jooble ({API_HOST}, {LOCATION}). Saved to database:", len(new_postings))
