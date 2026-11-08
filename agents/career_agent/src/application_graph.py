import re
import sys
from pathlib import Path
from typing import TypedDict
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt, Command

sys.path.insert(0, str(Path(__file__).resolve().parent))  # src/
from db import latest_cv_skills, load_postings, save_cover_letter
from esco import skills_to_uris
from llm import ask_llm
from cv_reader import read_pdf_text, split_sections, tailor_sections, write_profile, check_profile, CV_DIR
from cv_writer import save_tailored_cv
from docx import Document
# Delivery methods the user can choose from
DELIVERY_OPTIONS = ("download", "email", "drive")

# Folder for the exported Word files (must stay out of git)
LETTER_DIR = Path(__file__).resolve().parents[1] / "data" / "letters"

class AppState(TypedDict, total=False):
    """Data that is passed between the steps of the graph."""
    job_posting_id: int
    job_title: str
    company: str
    job_skills: list
    skills: list
    have_skills: list
    missing_skills: list
    letter: str
    feedback: str
    approved: bool
    docx_path: str
    delivery: str
    ordered_skills: list
    cv_summary: str
    cv_feedback: str
    cv_approved: bool
    cv_path: str
    cv_text: str
    tailored: dict
    user_id: str
    go_on: bool

def find_cv(user_id):
    """Find the user's CV in CV_DIR: name starting with user_id, else newest PDF."""
    pdfs = sorted(CV_DIR.glob("*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not pdfs:
        raise FileNotFoundError(f"No PDF CV found in {CV_DIR}")
    for p in pdfs:
        if p.stem.lower().startswith(user_id.lower()):
            return p
    return pdfs[0]

def split_skills(job_skills, cv_skills):
    """Split the job's skills into the ones the student has and the ones missing."""
    cv_lower = {s.lower() for s in cv_skills}
    cv_uris = skills_to_uris(cv_skills)
    have, missing = [], []
    for s in job_skills:
        if s.lower() in cv_lower or skills_to_uris([s]) & cv_uris:
            have.append(s)
        else:
            missing.append(s)
    return have, missing


def load_data(state):
    """Step 1: load the job posting and the CV skills, and compare them in code."""
    job = next(p for p in load_postings() if p["job_posting_id"] == state["job_posting_id"])
    cv_skills = latest_cv_skills(state["user_id"])
    have, missing = split_skills(job["skills"] or [], cv_skills)
    return {"job_title": job["title"], "company": job["company"],
            "job_skills": job["skills"] or [], "skills": cv_skills,
            "have_skills": have, "missing_skills": missing}

MATCH_THRESHOLD = 0.25  # below this share of job skills, warn the user


def check_match(state: AppState):
    # Warn the user before writing a letter if the CV matches the job weakly
    job = state["job_skills"]
    have = state["have_skills"]
    ratio = len(have) / len(job) if job else 0
    if ratio >= MATCH_THRESHOLD:
        return {"go_on": True}
    answer = interrupt({
        "match": f"Weak match: your CV has {len(have)} of {len(job)} required skills for this job ({ratio:.0%}).",
        "missing": state["missing_skills"],
    })
    return {"go_on": str(answer).strip().lower() in ("yes", "y")}


def after_match(state: AppState):
    # Route to letter writing only if the match is fine or the user said yes
    return "write_letter" if state["go_on"] else END

def cv_summary_for_llm(state):
    """Return the CV text without contact info and references, for LLM prompts."""
    text = state.get("cv_text") or read_pdf_text(find_cv(state["user_id"]))
    parts = []
    for heading, body in split_sections(text).items():
        if any(k in heading.lower() for k in ("contact", "reference")):
            continue  # never send personal details to the LLM
        parts.append(f"{heading}:\n{body}")
    return "\n\n".join(parts)


def write_letter(state):
    """Step 2: ask the LLM to write a short, honest cover letter; use feedback if any."""
    prompt = (
        f"Write a short cover letter (max 180 words) for the job '{state['job_title']}' "
        f"at {state['company']}.\n\n"
        "Use ONLY facts from the CV below. Mention 1-2 concrete projects or experiences "
        "from the CV that fit the job best.\n"
        f"Job skills the applicant has: {', '.join(state['have_skills']) or 'none'}.\n"
        f"Job skills that look missing: {', '.join(state['missing_skills']) or 'none'}.\n"
        "If the CV shows any experience with a 'missing' skill (e.g. in Projects), "
        "you may mention that real experience. Never claim more than the CV shows.\n"
        "Do not list everything the applicant lacks; at most say in one sentence "
        "that the applicant is eager to learn the most important missing skills.\n"
        "Avoid words like strong, expert, proficient, extensive.\n"
        "Do not write any name, address, phone or email. "
        "End with 'Sincerely,' and nothing after it. Return only the letter.\n\n"
        f"CV:\n{cv_summary_for_llm(state)}"
    )
    if state.get("feedback"):
        prompt += (f"\n\nHere is the previous letter:\n{state['letter']}\n"
                   f"Rewrite it with this change: {state['feedback']}")
    return {"letter": ask_llm(prompt)}


def check_letter(letter, missing_skills, cv_text=""):
    """Warn only when a missing skill is mentioned as experience.
    Skip skills that appear in the CV text, and sentences about learning."""
    warnings = []
    cv_low = cv_text.lower()
    sentences = re.split(r"(?<=[.!?])\s+", letter)
    for s in missing_skills:
        if s.lower() in cv_low:
            continue  # the CV really mentions it (e.g. in Projects)
        for sent in sentences:
            low = sent.lower()
            if s.lower() in low and "learn" not in low:
                warnings.append(f"The letter mentions '{s}', which is not in your CV. "
                                "Check it is not claimed as experience.")
                break
    return warnings


def human_review(state):
    """Step 3: pause the graph and wait for the human's decision."""
    cv_text = read_pdf_text(find_cv(state["user_id"]))
    warnings = (check_letter(state["letter"], state["missing_skills"], cv_text)
                + check_profile(state["letter"], cv_text))
    answer = interrupt({"letter": state["letter"], "warnings": warnings})
    if answer.strip().lower() in ("yes", "y", "ok"):
        return {"approved": True}
    if answer.strip().lower().startswith("edit:"):
        # The user writes the letter directly; no LLM involved
        return {"approved": True, "letter": answer.strip()[5:].strip()}
    return {"approved": False, "feedback": answer}

def export_docx(letter, app_id, version):
    """Write the letter to an editable Word (.docx) file and return its path."""
    LETTER_DIR.mkdir(parents=True, exist_ok=True)
    doc = Document()
    for paragraph in letter.split("\n\n"):  # one Word paragraph per text paragraph
        doc.add_paragraph(paragraph.strip())
    path = LETTER_DIR / f"cover_letter_app{app_id}_v{version}.docx"
    doc.save(path)
    return path

def save(state):
    """Step 4: save the approved letter in the database and export it to Word."""
    app_id, version = save_cover_letter(state["user_id"], state["job_posting_id"], state["letter"])
    print(f"Saved cover letter version {version} for application {app_id}")
    path = export_docx(state["letter"], app_id, version)  # keep the path for delivery
    print("Word file:", path)
    return {"docx_path": str(path)}

def choose_delivery(state: AppState):
    # Pause and let the USER pick how to receive the file
    answer = interrupt({
        "question": "How do you want to receive your cover letter and CV?",
        "options": list(DELIVERY_OPTIONS),
    })
    return {"delivery": answer.strip().lower()}

def deliver_download(state: AppState):
    # For now "download" means: show where the files are (Streamlit button later)
    print("Cover letter:", state["docx_path"])
    print("Tailored CV:", state["cv_path"])
    return {}

def deliver_later(state: AppState):
    # Email / Drive need OAuth and user approval; built at the end
    print(f"'{state['delivery']}' is not available yet. Files saved at:")
    print(" ", state["docx_path"])
    print(" ", state["cv_path"])
    return {}

def after_choice(state: AppState):
    # Route to the node for the chosen method
    if state["delivery"] == "download":
        return "deliver_download"
    return "deliver_later"


def after_review(state):
    """Decide where to go after the review."""
    return "save" if state["approved"] else "write_letter"

def order_skills(cv_skills, have_skills):
    """Put the CV skills the job asks for first (same name OR same ESCO link).
    Never add or remove a skill."""
    have_lower = {s.lower() for s in have_skills}
    have_uris = skills_to_uris(have_skills)
    first, rest = [], []
    for s in cv_skills:
        if s.lower() in have_lower or skills_to_uris([s]) & have_uris:
            first.append(s)
        else:
            rest.append(s)
    return first + rest

def job_text(state):
    """Build a short job description for the LLM prompts."""
    return (f"{state['job_title']} at {state['company']}. "
            f"Required skills: {', '.join(state['job_skills']) or 'none'}.")


def tailor_cv(state):
    """Tailor the full CV: keep relevant items and write a new profile.
    On the first visit the sections are selected; on feedback only the profile is rewritten."""
    if state.get("cv_feedback"):
        prompt = (f"Here is a CV profile:\n{state['cv_summary']}\n"
                  f"Rewrite it with this change: {state['cv_feedback']}\n"
                  "Use only facts from the CV. No names or contact details. "
                  "Return only the profile.")
        return {"cv_summary": ask_llm(prompt)}
    text = read_pdf_text(find_cv(state["user_id"]))
    tailored = tailor_sections(text, job_text(state))
    profile = write_profile(tailored, job_text(state))
    ordered = order_skills(state["skills"], state["have_skills"])  # still used by cv_review for now
    return {"cv_text": text, "tailored": tailored,
            "cv_summary": profile, "ordered_skills": ordered}


def check_summary(summary, missing_skills, cv_text=""):
    """Warn only for missing skills that the summary mentions
    and that do not appear anywhere in the CV text."""
    cv_low = cv_text.lower()
    return [f"The summary mentions '{s}', which is not in your CV."
            for s in missing_skills
            if s.lower() in summary.lower() and s.lower() not in cv_low]

def removed_list(tailored):
    """All removed items as (heading, item) pairs, numbered in CV order."""
    return [(h, it) for h, part in tailored.items() for it in part["removed"]]


def cv_review(state):
    """Pause and let the human approve the profile, restore removed items, or give feedback."""
    warnings = (check_profile(state["cv_summary"], state["cv_text"])
                + check_summary(state["cv_summary"], state["missing_skills"], state["cv_text"]))
    removed = removed_list(state["tailored"])
    answer = interrupt({"summary": state["cv_summary"],
                        "removed": [f"{h}: {it}" for h, it in removed],
                        "warnings": warnings})
    a = answer.strip()
    if a.lower() in ("yes", "y", "ok"):
        return {"cv_action": "approve", "cv_approved": True}
    if a.lower().startswith("edit:"):
        # The user writes the profile directly; no LLM involved
        return {"cv_action": "restore", "cv_summary": a[5:].strip()}
    if a.lower().startswith("restore"):
        nums = {int(n) for n in re.findall(r"\d+", a) if int(n) < len(removed)}
        # Copy the lists so the old state is not changed in place
        tailored = {h: {"kept": list(p["kept"]), "removed": list(p["removed"])}
                    for h, p in state["tailored"].items()}
        for n in nums:
            h, item = removed[n]
            tailored[h]["kept"].append(item)
            tailored[h]["removed"].remove(item)
        return {"cv_action": "restore", "tailored": tailored}
    return {"cv_action": "feedback", "cv_feedback": a}


def save_cv_doc(state):
    """Export the approved tailored CV (full CV, original order) to Word.
    Each run gets a new version number, so old files are never overwritten."""
    LETTER_DIR.mkdir(parents=True, exist_ok=True)
    version = 1
    while (LETTER_DIR / f"tailored_cv_job{state['job_posting_id']}_v{version}.docx").exists():
        version += 1
    path = LETTER_DIR / f"tailored_cv_job{state['job_posting_id']}_v{version}.docx"
    save_tailored_cv(state["tailored"], state["cv_summary"], path)
    print("Tailored CV file:", path)
    return {"cv_path": str(path)}


def after_cv_review(state):
    """Approve -> save, restore -> review again, feedback -> rewrite the profile."""
    if state["cv_action"] == "approve":
        return "save_cv_doc"
    if state["cv_action"] == "restore":
        return "cv_review"
    return "tailor_cv"

builder = StateGraph(AppState)
builder.add_node("load_data", load_data)
builder.add_node("write_letter", write_letter)
builder.add_node("human_review", human_review)
builder.add_node("save", save)
builder.add_node("tailor_cv", tailor_cv)
builder.add_node("cv_review", cv_review)
builder.add_node("save_cv_doc", save_cv_doc)
builder.add_node("choose_delivery", choose_delivery)
builder.add_node("deliver_download", deliver_download)
builder.add_node("deliver_later", deliver_later)
builder.add_node("check_match", check_match)

builder.add_edge(START, "load_data")
builder.add_edge("load_data", "check_match")
builder.add_conditional_edges("check_match", after_match, ["write_letter", END])
builder.add_edge("write_letter", "human_review")
builder.add_conditional_edges("human_review", after_review, ["save", "write_letter"])
builder.add_edge("save", "tailor_cv")
builder.add_edge("tailor_cv", "cv_review")
builder.add_conditional_edges("cv_review", after_cv_review, ["save_cv_doc", "tailor_cv", "cv_review"])
builder.add_edge("save_cv_doc", "choose_delivery")
builder.add_conditional_edges("choose_delivery", after_choice, ["deliver_download", "deliver_later"])
builder.add_edge("deliver_download", END)
builder.add_edge("deliver_later", END)
# The checkpointer remembers the state while the graph is paused
graph = builder.compile(checkpointer=MemorySaver())


if __name__ == "__main__":
        # Ask which user and which job posting
    user_id = input("User ID: ").strip()
    job_id = input("Job ID: ").strip()
    config = {"configurable": {"thread_id": f"{user_id}-{job_id}"}}
    result = graph.invoke({"user_id": user_id, "job_posting_id": int(job_id)}, config)
    while "__interrupt__" in result:
        info = result["__interrupt__"][0].value
        if "question" in info:
            # Delivery question: user picks download / email / drive
            print("\n" + info["question"], info["options"])
            answer = input("> ").strip().lower()
            while answer not in DELIVERY_OPTIONS:  # accept only a valid option
                answer = input("Please type one of " + str(info["options"]) + ": ").strip().lower()
        elif "match" in info:
            # Weak match warning before writing the letter
            print("\n" + info["match"])
            print("Missing skills:", ", ".join(info["missing"]))
            answer = input("Write a letter anyway? (yes/no): ")        
        elif "summary" in info:
            # Tailored CV review
            print("\nCV profile:", info["summary"])
            print("Removed items (type 'restore' + numbers to bring them back):")
            for i, item in enumerate(info["removed"]):
                print(f"  [{i}] {item[:70]}")
            for w in info["warnings"]:
                print("WARNING:", w)
            answer = input("Approve CV? Type yes, restore 0 2, or write what to change: ")
            while not answer.strip():  # do not accept an empty answer
                answer = input("Please type yes, restore ..., or write what to change: ")
        else:
            # Letter review
            print("\nLetter:", info["letter"])
            for w in info["warnings"]:
                print("WARNING:", w)
            answer = input("Approve? Type yes, or write what to change: ")
            while not answer.strip():  # do not accept an empty answer
                answer = input("Please type yes, or write what to change: ")
        result = graph.invoke(Command(resume=answer), config)
    print("Done. Delivery:", result.get("delivery"))
