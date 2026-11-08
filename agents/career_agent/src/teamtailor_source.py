import html
import json
import re
import ssl
import sys
import urllib.request
from pathlib import Path

import certifi

sys.path.insert(0, str(Path(__file__).resolve().parent))  # src/
from db import known_urls, load_postings, save_postings
from subagents.extractor import extract_skills

# Public Teamtailor job feed (JSON Feed 1.1). No API key needed.
FEED_URL = "https://{company}.teamtailor.com/jobs.json"

# List of companies and their ATS (kept as data, not in code)
COMPANIES_FILE = Path(__file__).resolve().parents[1] / "data" / "ats_companies.json"


def fetch_teamtailor(company):
    """Download the job feed of one company and return its job items."""
    url = FEED_URL.format(company=company)
    context = ssl.create_default_context(cafile=certifi.where())
    request = urllib.request.Request(url, headers={"User-Agent": "CogniPath-CareerAgent/0.1"})
    with urllib.request.urlopen(request, context=context, timeout=30) as response:
        feed = json.load(response)
    return feed.get("items", [])


def load_companies():
    """Read the company list from data/ats_companies.json."""
    with open(COMPANIES_FILE, encoding="utf-8") as f:
        return json.load(f)


def html_to_text(raw):
    """Turn the HTML job description into plain text."""
    no_tags = re.sub(r"<[^>]+>", " ", raw or "")
    return re.sub(r"\s+", " ", html.unescape(no_tags)).strip()

# Words in a job title that mean an internship (checked as whole words)
INTERNSHIP_WORDS = re.compile(
    r"\b(intern|internship|trainee|harjoittelija)\b", re.IGNORECASE
)


def guess_type(title):
    """Return 'internship' if the title looks like an internship, else 'job'."""
    return "internship" if INTERNSHIP_WORDS.search(title) else "job"


def to_posting(item, company_name):
    """Convert one feed item into the posting format used by save_postings."""
    description = html_to_text(item.get("content_html"))
    return {
        "title": item["title"],
        "company": company_name,
        "type": guess_type(item["title"]),
        "url": item["url"],
        "description": description,
        "skills": extract_skills(description),  # skills found by the LLM
    }


if __name__ == "__main__":
    seen_urls = known_urls()
    # Same rule as the database: one row per title + company
    seen_keys = {(p["title"], p["company"]) for p in load_postings()}
    new_postings = []
    for company in load_companies():
        if company["ats"] != "teamtailor":
            continue
        items = fetch_teamtailor(company["token"])
        fresh = []
        for item in items:
            key = (item["title"], company["name"])
            if item["url"] in seen_urls or key in seen_keys:
                continue
            seen_keys.add(key)
            fresh.append(to_posting(item, company["name"]))
        print(company["name"], "- jobs found:", len(items), "| new:", len(fresh))
        new_postings.extend(fresh)
    save_postings(new_postings)
    print("Saved to database:", len(new_postings))