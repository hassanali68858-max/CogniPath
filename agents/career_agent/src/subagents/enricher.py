"""Enricher: for the jobs matched to a user, find the apply deadline in the ad text
and write a one-sentence summary of the ad. Both are saved on the job posting."""
import json
import re
import ssl
import sys
import urllib.request
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse

import certifi

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # src/
from sqlalchemy import text
from db import engine
from llm import ask_llm
from teamtailor_source import html_to_text

TODAY = date.today()
RECHECK_DAYS = 7

# Dates written as numbers: 5.12.2026, 05/12/2026, 2026-12-05
# (the ISO form may be followed by a time, e.g. 2026-12-05T23:59:00)
NUMERIC_DATE = re.compile(r"\b(\d{1,2})[./](\d{1,2})[./](\d{4})\b|\b(\d{4})-(\d{2})-(\d{2})(?!\d)")
# Dates with an English month name: "5 December 2026", "December 5, 2026", "Dec 5"
MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
WORD_DATE = re.compile(
    r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})\.?,?\s*(\d{4})?\b"
    r"|\b([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s*(\d{4})?\b")


def ensure_columns():
    """Add the summary column the first time (deadline already exists in schema.sql)."""
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE career.job_postings ADD COLUMN IF NOT EXISTS summary TEXT"))
        # When the deadline was last searched; a job is searched again only after RECHECK_DAYS
        conn.execute(text("ALTER TABLE career.job_postings ADD COLUMN IF NOT EXISTS deadline_checked_at TIMESTAMP"))


def make_date(year, month, day):
    """A real date, or None if the numbers are not a valid date."""
    try:
        return date(int(year), int(month), int(day))
    except (TypeError, ValueError):
        return None


def candidate_dates(ad):
    """All future dates written in the ad (general date patterns, no keyword list)."""
    found = set()
    for m in NUMERIC_DATE.finditer(ad):
        if m.group(1):
            d = make_date(m.group(3), m.group(2), m.group(1))  # day.month.year (Finnish/European)
        else:
            d = make_date(m.group(4), m.group(5), m.group(6))  # year-month-day
        if d:
            found.add(d)
    for m in WORD_DATE.finditer(ad):
        day, name, year = (m.group(1), m.group(2), m.group(3)) if m.group(1) else (m.group(5), m.group(4), m.group(6))
        name = name[:3].lower()
        if name not in MONTHS:
            continue
        d = make_date(year or TODAY.year, MONTHS.index(name) + 1, day)
        if d and not year and d < TODAY:
            d = make_date(TODAY.year + 1, d.month, d.day)  # "Dec 5" without a year = next one
        if d:
            found.add(d)
    # A deadline that has already passed is not useful; far future dates are start dates
    return sorted(d for d in found if TODAY <= d <= date(TODAY.year + 2, 12, 31))


def find_deadline(ad):
    """The apply deadline in the ad, or None.
    One future date: use it. Several dates: the LLM picks the deadline (ads also
    contain start dates). No date: None, the ad does not say."""
    dates = candidate_dates(ad)
    if not dates:
        return None
    if len(dates) == 1:
        return dates[0]
    options = ", ".join(d.isoformat() for d in dates)
    prompt = (f"Job ad:\n{ad[:3000]}\n\nThese dates appear in the ad: {options}. "
              "Which one is the last day to apply? Answer with the date (YYYY-MM-DD) only, "
              "or 'none' if no date is the application deadline.")
    try:
        answer = ask_llm(prompt)
    except Exception as e:
        print("LLM not available for the deadline:", e)
        return None
    m = re.search(r"\d{4}-\d{2}-\d{2}", answer)
    if not m:
        return None
    picked = datetime.strptime(m.group(0), "%Y-%m-%d").date()
    return picked if picked in dates else None  # only accept a date that is really in the ad


# Sites we do not open: LinkedIn does not allow automatic reading of its pages,
# Jooble links only redirect to other sites
NO_FETCH_SITES = ("linkedin.com", "jooble.org")


def open_page(url, show_errors=True):
    """Download the public job ad page once and return its HTML ('' if not possible)."""
    if not url or not url.startswith("http"):
        return ""
    host = urlparse(url).netloc.lower()
    if any(host == s or host.endswith("." + s) for s in NO_FETCH_SITES):
        return ""
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "CogniPath-CareerAgent/0.1"})
        context = ssl.create_default_context(cafile=certifi.where())
        with urllib.request.urlopen(request, context=context, timeout=20) as response:
            return response.read().decode("utf-8", errors="ignore")
    except Exception as e:  # page gone (410), blocked (403), no network: deadline stays unknown
        if show_errors:
            print(f"   could not open the page: {e}")
        return ""


def structured_deadline(page):
    """Most job sites put a hidden JobPosting block in the page for search engines.
    Its 'validThrough' field is the last day of the ad. Returns a date or None."""
    blocks = re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', page, re.S | re.I)
    for block in blocks:
        try:
            data = json.loads(block.strip())
        except json.JSONDecodeError:
            continue
        items = data if isinstance(data, list) else data.get("@graph", [data])
        for item in items:
            if isinstance(item, dict) and item.get("validThrough"):
                d = make_date(*str(item["validThrough"])[:10].split("-"))
                if d and d >= TODAY:
                    return d
    return None


def visible_text(page):
    """Page text without scripts and styles (they contain many unrelated dates)."""
    no_code = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", page, flags=re.S | re.I)
    return html_to_text(no_code)


def summarize(title, company, ad):
    """One short sentence about the job, in English (asked from the LLM)."""
    if not ad.strip():
        return None
    prompt = (f"Job ad for '{title}' at {company}:\n{ad[:3000]}\n\n"
              "Summarize in ONE short English sentence (max 25 words) what this job is "
              "and what the person will do. Answer with the sentence only.")
    try:
        answer = ask_llm(prompt).strip()
    except Exception as e:
        print("LLM not available for the summary:", e)
        return None
    sentence = answer.splitlines()[0].strip().strip('"') if answer else ""
    return sentence[:300] or None


def check_page(url):
    """Diagnostic: show what one job page contains (python subagents\\enricher.py --check <url>)."""
    page = open_page(url)
    if not page:
        return
    blocks = re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', page, re.S | re.I)
    print(f"Page size: {len(page)} characters, JobPosting data blocks: {len(blocks)}")
    for block in blocks:
        for field in ("datePosted", "validThrough"):
            m = re.search(rf'"{field}"\s*:\s*"([^"]+)"', block)
            print(f"   {field}: {m.group(1) if m else 'not given'}")
    full = visible_text(page)
    print("Future dates in the visible text:", [d.isoformat() for d in candidate_dates(full)] or "none")
    print("Deadline the enricher would save:", structured_deadline(page) or find_deadline(full) or "none")


if __name__ == "__main__":
    # Usage: python subagents\enricher.py <user_id>
    #        python subagents\enricher.py --check <job page url>
    if len(sys.argv) > 2 and sys.argv[1] == "--check":
        check_page(sys.argv[2])
        sys.exit(0)
    user_id = sys.argv[1] if len(sys.argv) > 1 else input("User ID: ").strip()
    ensure_columns()
    with engine.connect() as conn:
        # Only this user's matched jobs that still need work (keeps LLM calls and page loads few):
        # no summary yet, or no deadline and not searched in the last RECHECK_DAYS days
        rows = conn.execute(text(
            "SELECT j.job_posting_id, j.title, j.company, j.url, j.description, j.deadline, j.summary "
            "FROM career.job_postings j JOIN career.matches m ON m.job_posting_id = j.job_posting_id "
            "WHERE m.user_id = :uid AND (j.summary IS NULL OR (j.deadline IS NULL AND "
            "(j.deadline_checked_at IS NULL OR j.deadline_checked_at < NOW() - make_interval(days => :days))))"
        ), {"uid": user_id, "days": RECHECK_DAYS}).mappings().all()
    print(f"Jobs to enrich for {user_id}: {len(rows)} (jobs checked in the last {RECHECK_DAYS} days are skipped)")
    found = 0
    for r in rows:
        ad = r["description"] or ""
        deadline = r["deadline"] or find_deadline(ad)
        source = "ad text" if deadline else None
        if deadline is None:
            # The saved text has no deadline: look at the full ad page (e.g. Teamtailor)
            page = open_page(r["url"])
            if page:
                full = visible_text(page)
                deadline = structured_deadline(page)
                source = "page data (validThrough)" if deadline else None
                if deadline is None:
                    deadline = find_deadline(full)
                    source = "page text" if deadline else None
                if len(ad.strip()) < 200:
                    ad = full[:3000]  # email alerts have almost no text: summarize the page instead
        summary = r["summary"] or summarize(r["title"], r["company"], ad)
        with engine.begin() as conn:
            conn.execute(text(
                "UPDATE career.job_postings SET deadline = :d, summary = :s, deadline_checked_at = NOW() "
                "WHERE job_posting_id = :id"
            ), {"d": deadline, "s": summary, "id": r["job_posting_id"]})
        found += deadline is not None
        print(f"{r['title']} - {r['company']}: deadline {deadline or 'not given'}"
              + (f" (from {source})" if source else ""))
    print(f"Done: {found} of {len(rows)} jobs have a deadline.")
