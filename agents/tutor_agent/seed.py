"""Load the demo data in ``data/seed/tutor/``. ``sisu.py`` can replace the course data."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import TypeAdapter

from .catalog import Catalog
from .student import StudentProfile

DEFAULT_SEED_DIR = Path(__file__).resolve().parents[2] / "data" / "seed" / "tutor"
CATALOG_FILES = ("programmes", "courses", "opportunities", "topics")

_students = TypeAdapter(list[StudentProfile])


def load_catalog(seed_dir: Path = DEFAULT_SEED_DIR) -> Catalog:
    return Catalog.model_validate({name: _read(seed_dir / f"{name}.json") for name in CATALOG_FILES})


def load_sisu_links(seed_dir: Path = DEFAULT_SEED_DIR) -> dict[str, str]:
    """Seed course code -> code of the real JYU course in Sisu that stands in for it."""
    return json.loads((seed_dir / "sisu_courses.json").read_text(encoding="utf-8"))


def load_students(seed_dir: Path = DEFAULT_SEED_DIR) -> dict[str, StudentProfile]:
    students = _students.validate_json((seed_dir / "students.json").read_text(encoding="utf-8"))
    return {s.user_id: s for s in students}


def load_student(user_id: str, seed_dir: Path = DEFAULT_SEED_DIR) -> StudentProfile:
    students = load_students(seed_dir)
    if user_id not in students:
        raise KeyError(f"unknown student {user_id!r}; seed students: {sorted(students)}")
    return students[user_id]


def _read(path: Path) -> list:
    return json.loads(path.read_text(encoding="utf-8"))
