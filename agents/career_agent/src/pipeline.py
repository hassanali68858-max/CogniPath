import subprocess
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent
SUBAGENTS_DIR = SRC_DIR / "subagents"

# Intake: bring new postings into the database first (same for every user)
INTAKE = ["gmail_fetch.py", "job_emails.py"]
# Per-user steps
STEPS = ["collector.py", "extractor.py", "matcher.py", "advisor.py"]


def run_intake(name):
    print(f"\n=== {name} ===")
    result = subprocess.run([sys.executable, str(SRC_DIR / name)])
    # Intake errors (e.g. no internet) should not stop the plan;
    # the database still has the older postings
    if result.returncode != 0:
        print(f"{name} failed, continuing with existing postings.")


def run_step(name, user_id):
    print(f"\n=== {name} ===")
    # Pass the user id to every subagent
    result = subprocess.run([sys.executable, str(SUBAGENTS_DIR / name), user_id])
    if result.returncode != 0:
        print(f"{name} failed, stopping.")
        sys.exit(1)


if __name__ == "__main__":
    # Usage: python pipeline.py <user_id>
    user_id = sys.argv[1] if len(sys.argv) > 1 else input("User ID: ").strip()
    for name in INTAKE:
        run_intake(name)
    for step in STEPS:
        run_step(step, user_id)
    print(f"\nCareer Agent finished for {user_id}. Output: data/career_plan.json")