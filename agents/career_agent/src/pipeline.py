import subprocess
import sys
from pathlib import Path

SUBAGENTS_DIR = Path(__file__).resolve().parent / "subagents"
STEPS = ["collector.py", "extractor.py", "matcher.py", "advisor.py"]


def run_step(name):
    print(f"\n=== {name} ===")
    result = subprocess.run([sys.executable, str(SUBAGENTS_DIR / name)])
    if result.returncode != 0:
        print(f"{name} failed, stopping.")
        sys.exit(1)


if __name__ == "__main__":
    for step in STEPS:
        run_step(step)
    print("\nCareer Agent finished. Output: data/career_plan.json")