"""Run the Tutor Agent from the command line.

From the repository root:

    python -m agents.tutor_agent.cli propose --student student001 --today 2026-11-02 --out tutor_proposals.json
    python -m agents.tutor_agent.cli quiz --student student001 --topic rdf

Set TUTOR_QUESTION_GENERATOR=ollama to let a local Ollama model write the quiz (see quiz/llm.py).
Set TUTOR_CATALOG_SOURCE=sisu to use live course data from JYU Sisu (see sisu.py).
"""

from __future__ import annotations

import argparse
import json
import os
import random
from datetime import date

from .catalog import TutorContext
from .quiz import build_quiz, generator_from_env, grade_quiz, record_attempt, topic_mastery
from .seed import load_student
from .sisu import catalog_from_env
from .tutor import run


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="CogniPath Tutor Agent")
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("propose", help="progress report, recommendations and quiz proposals")
    p.add_argument("--student", required=True)
    p.add_argument("--today", type=date.fromisoformat, default=date.today(), help="YYYY-MM-DD")
    p.add_argument("--days", type=int, default=14, help="Planner horizon in days")
    p.add_argument("--out", help="write the proposals as JSON (input for the Planner CLI --proposals)")

    q = sub.add_parser("quiz", help="take a quiz on one topic in the terminal")
    q.add_argument("--student", required=True)
    q.add_argument("--topic", required=True, help="topic id, e.g. rdf")
    q.add_argument("--questions", type=int, default=5)
    q.add_argument("--seed", type=int, help="random seed for a repeatable template quiz")

    args = ap.parse_args(argv)
    if args.command == "propose":
        _propose(args)
    else:
        _quiz(args)


def _propose(args: argparse.Namespace) -> None:
    context = TutorContext(today=args.today, horizon_days=args.days, catalog=catalog_from_env(os.environ).catalog)
    output = run(load_student(args.student), context)
    report = output.progress

    credits = f"{report.completed_credits:.0f}/{report.required_credits:.0f} ECTS"
    print(f"=== {report.programme_name}: {credits}, {report.status.value} (needs {report.required_pace:.0f} ECTS/year)")
    for m in report.modules:
        print(f"  {m.name:<20} {m.completed_credits:>4.0f}/{m.required_credits:.0f} ECTS")
    for w in report.warnings:
        print(f"  ! {w.message}")

    print(f"\n=== {len(output.proposals)} proposals for the Planner")
    for prop in output.proposals:
        when = f"by {prop.window.deadline:%d %b}" if prop.window else f"{prop.fixed_time.start:%d %b %H:%M}"
        print(f"  [study {prop.value.study:.1f}] {prop.title} ({when})")
        print(f"           {prop.reason}")
        if prop.depends_on:
            print(f"           after: {', '.join(prop.depends_on)}")

    if output.forums:
        print("\n=== Forums")
        for f in output.forums:
            print(f"  {f.title} - {f.url or 'no link'}\n           {f.reason}")

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump([p.model_dump(mode="json", exclude_none=True) for p in output.proposals], fh, indent=2)
        print(f"\nwrote {args.out}")


def _quiz(args: argparse.Namespace) -> None:
    catalog = catalog_from_env(os.environ).catalog
    student = load_student(args.student)
    generator = generator_from_env(os.environ, random.Random(args.seed))
    quiz = build_quiz(args.topic, catalog, generator, count=args.questions)

    answers = []
    for n, question in enumerate(quiz.questions, start=1):
        print(f"\n{n}. {question.prompt}")
        for i, option in enumerate(question.options, start=1):
            print(f"   {i}) {option}")
        answers.append(_ask_option(len(question.options)) - 1)

    attempt = grade_quiz(quiz, answers, taken_on=date.today())
    before = topic_mastery(student.quiz_history, args.topic)
    after = topic_mastery(record_attempt(student, attempt).quiz_history, args.topic)
    before_text = "untested" if before is None else f"{before:.0%}"
    print(f"\nScore {attempt.correct}/{attempt.total}. Mastery of {args.topic}: {before_text} -> {after:.0%}")
    print("(The demo does not save the result to the seed data.)")


def _ask_option(count: int) -> int:
    while True:
        raw = input(f"   answer 1-{count}: ").strip()
        if raw.isdigit() and 1 <= int(raw) <= count:
            return int(raw)


if __name__ == "__main__":
    main()
