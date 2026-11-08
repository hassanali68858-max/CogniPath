import html
import re
from email import policy
from email.parser import BytesParser
from pathlib import Path

from db import known_urls, save_postings
from guess_skills import guess_skills
from teamtailor_source import guess_type  # same internship rule as Teamtailor

EMAIL_DIR = Path(__file__).resolve().parents[1] / "data" / "job_emails"

# Lines in a job card that are not title, company or location
FILLER = ("This company is actively hiring", "Apply with resume",
          "Actively recruiting", "Easy Apply", "Promoted")


def read_email(path):
    """Return the subject, sender and plain-text body of one .eml file."""
    with open(path, "rb") as f:
        msg = BytesParser(policy=policy.default).parse(f)
    # Prefer the plain-text part; fall back to HTML
    part = msg.get_body(preferencelist=("plain", "html"))
    body = part.get_content() if part else ""
    return msg["subject"], msg["from"], body


def parse_linkedin(body):
    """Return a list of jobs (title, company, location, url) from a LinkedIn alert."""
    jobs = []
    # Job cards are separated by a line of dashes
    for block in re.split(r"\n-{10,}\n", body):
        match = re.search(r"View job: \S*/jobs/view/(\d+)", block)
        if not match:
            continue
        lines = [l.strip() for l in block[:match.start()].splitlines()]
        lines = [l for l in lines if l and not l.startswith(FILLER)]
        if len(lines) < 3:
            continue
        # The first card also has the alert header, so take the last 3 lines
        title, company, location = lines[-3:]
        jobs.append({"title": title, "company": company, "location": location,
                     "url": f"https://www.linkedin.com/jobs/view/{match.group(1)}/"})
    return jobs


def parse_indeed(body):
    """Return a list of jobs (title, company, location, url) from an Indeed email."""
    jobs = []
    for match in re.finditer(r"View job: (\S+)", body):
        # The 3 non-empty lines before "View job:" are title, company, location
        lines = [l.strip() for l in body[:match.start()].splitlines() if l.strip()]
        if len(lines) < 3:
            continue
        title, company, location = lines[-3:]
        jobs.append({"title": title, "company": company, "location": location,
                     "url": match.group(1)})
    return jobs


def parse_glassdoor(body):
    """Extract jobs from a Glassdoor alert (HTML only)."""
    # Job links appear in the same order as the jobs
    links = re.findall(r'href="(https://www\.glassdoor\.com/partner/jobListing\.htm[^"]+)"', body)
    links = [html.unescape(html.unescape(l)) for l in dict.fromkeys(links)]
    # Turn HTML into clean text lines
    body = re.sub(r"<(style|head)[^>]*>.*?</\1>", "", body, flags=re.S)
    text = html.unescape(re.sub(r"<[^>]+>", "\n", body))
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    start = next(i for i, l in enumerate(lines) if l.startswith("Your job listings")) + 3
    # Split into blocks; a block ends with the job age, like "2d" or "8h"
    blocks, block = [], []
    for line in lines[start:]:
        if re.fullmatch(r"\d+[hd]\+?", line):
            blocks.append(block)
            block = []
            continue
        # Skip rating, salary and "Easy Apply" lines
        if "★" in line or "(Employer est.)" in line or line == "Easy Apply":
            continue
        block.append(line)
    blocks.append(block)
    jobs = []
    for block, url in zip(blocks, links):
        if len(block) >= 3:
            company, title, location = block[:3]
            jobs.append({"title": title, "company": company,
                         "location": location, "url": url})
    return jobs


if __name__ == "__main__":
    seen = known_urls()
    for path in EMAIL_DIR.glob("*.eml"):
        subject, sender, body = read_email(path)
        print("File:", path.name, "| Subject:", subject)

        body = html.unescape(body)
        # Pick the parser by the sender's address
        if "linkedin" in sender.lower():
            parsed = parse_linkedin(body)
        elif "indeed" in sender.lower():
            parsed = parse_indeed(body)
        elif "glassdoor" in sender.lower():
            parsed = parse_glassdoor(body)
        else:
            parsed = []
        # Skip jobs we already saved, so skills are not guessed again
        jobs = [j for j in parsed if j["url"] not in seen]
        for job in jobs:
            job["type"] = guess_type(job["title"])
            location = job.pop("location")
            skills = guess_skills(job["title"])
            print("Skills for", job["title"], "->", skills)
            job["skills"] = skills
            # Guessed skills go into description so the matcher can use them
            job["description"] = f"Location: {location}\nGuessed skills: {', '.join(skills)}"
            seen.add(job["url"])
        save_postings(jobs)
        print("Saved", len(jobs), "new jobs from", path.name)