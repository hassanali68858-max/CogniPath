import json
import sys
import re
from difflib import SequenceMatcher
from pathlib import Path

from pypdf import PdfReader
from cv_writer import save_tailored_cv
sys.path.insert(0, str(Path(__file__).resolve().parent))  # src/
from llm import ask_llm
from db import save_cv, latest_cv_skills, cache_get, cache_set

CV_DIR = Path(__file__).resolve().parents[1] / "data" / "cvs"


def read_pdf_text(path):
    """Extract all text from a PDF file."""
    reader = PdfReader(path)
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages).strip()

# Patterns for contact details that must never reach the LLM
EMAIL_RE = re.compile(r"\S+@\S+\.\S+")
PHONE_RE = re.compile(r"\+?\d[\d\s\-()]{7,}\d")
URL_RE = re.compile(r"(https?://\S+|www\.\S+|linkedin\.com/\S+|github\.com/\S+)", re.I)


def strip_contact(cv_text):
    """Remove name line, emails, phone numbers and links before sending to the LLM."""
    lines = cv_text.splitlines()
    # The first non-empty line is usually the person's name
    for i, line in enumerate(lines):
        if line.strip():
            lines[i] = ""
            break
    text = "\n".join(lines)
    text = EMAIL_RE.sub("[email]", text)
    text = PHONE_RE.sub("[phone]", text)
    text = URL_RE.sub("[link]", text)
    return text

def extract_profile(cv_text):
    """Ask the LLM to turn CV text into a structured profile dict."""
    prompt = f"""Read this CV and return ONLY a JSON object with these keys:
"skills": list of short skill names (technical and soft skills, tools, methods).
          Take skills from the WHOLE CV: skills, experience, projects AND certificates
          (e.g. a certificate "PRINCE2 Foundation" gives the skill "PRINCE2"),
"certificates": list of certificates,
"education": list of degrees,
"experience": list of job titles,
"languages": list of spoken languages.
Do not include personal contact details. Return JSON only, nothing else.

CV:
{strip_contact(cv_text)}"""
    answer = ask_llm(prompt)
    # Keep only the part between the first { and the last }
    start, end = answer.find("{"), answer.rfind("}")
    if start == -1 or end == -1:
        return {}
    try:
        return json.loads(answer[start:end + 1])
    except json.JSONDecodeError:
        return {}



def clean_skills(raw_skills):
    """Split long skill lines like 'Languages: C, C#, and Python (basic)' into single skills."""
    skills = []
    for item in raw_skills:
        if ":" in item:
            item = item.split(":", 1)[1]           # drop the category label before ':'
        item = re.sub(r"\(.*?\)", "", item)        # drop notes in parentheses
        for part in item.split(","):
            part = re.sub(r"^\s*and\s+", "", part).strip()  # drop a leading 'and'
            if part and part.lower() not in (s.lower() for s in skills):
                skills.append(part)
    return skills

def fix_skill_name(name):
    """Fix the spelling of one skill name with the LLM (cached in the DB)."""
    key = f"fix:{name.lower()}"
    cached = cache_get(key)
    if cached:
        answer = cached["result"]
    else:
        answer = ask_llm(
            "This is a computer/IT skill from a CV. Fix ONLY spelling mistakes. "
            "Do not change its meaning or add words. If it is already correct, "
            f"return it unchanged. Answer with the skill name only: {name}"
        )
        # Keep only the first line and remove quotes / dots
        answer = answer.strip().splitlines()[0].strip(' "\'.') if answer.strip() else ""
        cache_set(key, {"result": answer})
    # Accept the LLM answer only if it is very similar to the original (a spelling fix)
    similarity = SequenceMatcher(None, name.lower(), answer.lower()).ratio()
    return answer if similarity >= 0.7 else name


def fix_skill_names(skills):
    """Fix every skill name in the list."""
    return [fix_skill_name(s) for s in skills]

# Sections where the LLM may drop items that do not fit the job (matched by keyword).
# All other sections are always copied in full (never trimmed).
SELECTABLE_KEYWORDS = ("skill", "project", "seminar", "presentation", "research",
                       "interest", "merit", "certific", "course", "workshop")

def is_selectable(heading):
    """True if the heading looks like a section the LLM may trim."""
    h = heading.lower()
    return any(k in h for k in SELECTABLE_KEYWORDS)

def is_heading(line):
    """Guess if a line is a section heading: short, alone, starts with a capital,
    no digits, no sentence ending. Works for any CV layout."""
    s = line.strip().rstrip(":").strip()
    if not s or len(s) > 40 or any(ch.isdigit() for ch in s):
        return False
    if s[0] in "-•*–" or s.endswith((".", ",", ";")) or "@" in s:
        return False
    words = s.split()
    if not 1 <= len(words) <= 5:
        return False
    small = {"and", "of", "&", "in", "for", "the", "to"}
    return s.isupper() or all(w[0].isupper() or w.lower() in small for w in words)


# Words that really name a CV section. Used only at the top of the CV,
# so a job title like "Project Coordinator" stays with the contact lines.
SECTION_WORDS = {
    "profile", "summary", "about", "objective", "skills", "competencies",
    "experience", "employment", "education", "qualifications",
    "certificates", "certifications", "languages", "projects",
    "references", "contact", "interests", "hobbies", "publications",
    "awards", "courses", "training", "volunteering",
}


def is_section_word_heading(line):
    """True if the heading line contains a known CV section word."""
    words = line.strip().rstrip(":").lower().split()
    return any(w in SECTION_WORDS for w in words)


def split_sections(text):
    """Split CV text into sections using auto-detected headings."""
    sections = {}
    current = "Contact Information"
    sections[current] = []
    first_line_seen = False

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        # The first non-empty line is usually the candidate's name -> keep it in contact
        if not first_line_seen:
            first_line_seen = True
            sections[current].append(line)
            continue

        # At the top of the CV, only a real section word starts a new section
        top_of_cv = current == "Contact Information"
        if is_heading(line) and (not top_of_cv or is_section_word_heading(line)):
            current = line.title()
            sections.setdefault(current, [])
        else:
            sections[current].append(line)

    # Drop empty sections and join lines
    sections = {h: "\n".join(lines) for h, lines in sections.items() if lines}
    return sections or {"CV": text}

def split_items(body):
    """Split one section into items. Bullet points (•) start a new item.
    A section without bullets stays as one item. Text is kept verbatim."""
    if "•" not in body:
        return [body.strip()] if body.strip() else []
    parts = body.split("•")
    items = []
    # Text before the first bullet (e.g. a table header) is kept as its own item
    if parts[0].strip():
        items.append(parts[0].strip())
    for p in parts[1:]:
        if p.strip():
            items.append("• " + p.strip())
    return items

def select_items(section, items, job_text):
    """Ask the LLM which items of one section fit the job.
    Returns kept indices, most relevant first. The LLM can only drop or
    reorder items: invalid answers fall back to keeping everything."""
    numbered = "\n".join(f"[{i}] {it}" for i, it in enumerate(items))
    prompt = f"""You help tailor a CV to a job posting.
Below are the items of the CV section "{section}".
Return ONLY a JSON list of the item numbers that are relevant to the job,
most relevant first. Leave out items that do not help for this job.
Example answer: [2, 0]

JOB POSTING:
{job_text}

ITEMS:
{numbered}
"""
    answer = ask_llm(prompt)
    match = re.search(r"\[[\d,\s]*\]", answer)
    if not match:
        return list(range(len(items)))  # could not read the answer: keep all
    kept = []
    for n in json.loads(match.group()):
        # Keep only real item numbers, each once
        if 0 <= n < len(items) and n not in kept:
            kept.append(n)
    return kept or list(range(len(items)))  # never return an empty section

def tailor_sections(text, job_text):
    """Tailor the whole CV. Selectable sections keep only the items the LLM
    picked (most relevant first). Other sections are copied in full.
    Returns {heading: {"kept": [...], "removed": [...]}} in CV order."""
    tailored = {}
    for heading, body in split_sections(text).items():
        items = split_items(body)
        if is_selectable(heading) and len(items) > 1:
            kept_idx = select_items(heading, items, job_text)
        else:
            kept_idx = list(range(len(items)))
        tailored[heading] = {
            "kept": [items[i] for i in kept_idx],
            "removed": [items[i] for i in range(len(items)) if i not in kept_idx],
        }
    
    return tailored

def write_profile(tailored, job_text):
    """Write a short profile for the top of the CV from the kept CV items only.
    Contact info and references are never sent to the LLM."""
    parts = []
    for heading, part in tailored.items():
        if any(k in heading.lower() for k in ("contact", "reference")):
            continue
        parts.append(heading + ":\n" + "\n".join(part["kept"]))
    prompt = f"""Write a 3-sentence profile summary for the top of this CV, tailored to the job.
Rules:
- Use ONLY facts from the CV. Do not invent anything.
- Take the field of study, degree and job titles ONLY from the CV.
- Never mix details between different degrees or jobs (each thesis belongs to its own degree).
- A skill level applies only to the skill it is written next to (e.g. "Python (basic level)" means only Python is basic).
- Exactly 3 sentences.
- No names, no contact details, no placeholders like [Your Name].
- Write in third person without a name and without pronouns (no he, she, his, her, they). Start sentences with a noun or verb (e.g. "<degree> student with ...", "Has built ...").
- Do not use these words: {", ".join(OVERCLAIM_WORDS)}. Describe experience plainly.
- Return ONLY the 3 profile sentences. No notes, no explanations, no comments about the match.
JOB POSTING:
{job_text}

CV:
{chr(10).join(parts)}
"""
    return ask_llm(prompt).strip()

OVERCLAIM_WORDS = ["proficient", "expert", "advanced", "skilled", "strong", "extensive", "mastery"]


def check_profile(profile_text, cv_text):
    """Return warnings for claims the CV does not support.
    A word is flagged only if it does not appear in the original CV."""
    warnings = []
    low_profile, low_cv = profile_text.lower(), cv_text.lower()
    for w in OVERCLAIM_WORDS:
        if w in low_profile and w not in low_cv:
            warnings.append(f'"{w}" is not in your CV - please check this claim')
    if re.search(r"\[[^\]]+\]", profile_text):
        warnings.append("Profile contains a placeholder like [Your Name]")
    return warnings

if __name__ == "__main__":
    # Ask for the user; the CV file name is optional
    user_id = input("User ID: ").strip()
    if not user_id:
        sys.exit("User ID is required")
    cv_name = input("CV file name (Enter = newest PDF in cvs): ").strip()
    if cv_name:
        cv_path = CV_DIR / cv_name
    else:
        # Pick the most recently added PDF
        pdfs = sorted(CV_DIR.glob("*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not pdfs:
            sys.exit(f"No PDF CV found in {CV_DIR}")
        cv_path = pdfs[0]
    print("Using CV:", cv_path.name)
    text = read_pdf_text(cv_path)
    profile = extract_profile(text)
    profile["skills"] = clean_skills(profile.get("skills", []))
    profile["skills"] = fix_skill_names(profile["skills"])
    print("Fixed skills:", profile["skills"])
    save_cv(user_id, cv_path, text, profile["skills"])
    print("Skills from DB:", latest_cv_skills(user_id))