import pytest
from pydantic import ValidationError

from agents.tutor_agent.catalog import Catalog
from agents.tutor_agent.seed import load_student, load_students


def test_seed_catalog_loads(catalog):
    assert catalog.programme("msc-cognitive-computing-demo").total_credits == 120
    assert "COG2100" in catalog.courses_by_code
    assert "rdf" in catalog.topics_by_id


def test_seed_students_load():
    assert "student001" in load_students()
    with pytest.raises(KeyError):
        load_student("nobody")


def _catalog(courses=(), topics=()):
    module = {"id": "m", "name": "M", "min_credits": 10}
    return {
        "programmes": [{"id": "p", "name": "P", "total_credits": 120, "modules": [module]}],
        "courses": list(courses),
        "topics": list(topics),
    }


def test_unknown_course_prerequisite_is_rejected():
    course = {"code": "A", "name": "A", "credits": 5, "module_id": "m", "prerequisites": ["MISSING"]}
    with pytest.raises(ValidationError, match="unknown prerequisite courses"):
        Catalog.model_validate(_catalog(courses=[course]))


def test_topic_prerequisite_cycle_is_rejected():
    fact = [{"term": "t", "definition": "d"}]
    topics = [
        {"id": "a", "name": "A", "course_code": "X", "prerequisites": ["b"], "facts": fact},
        {"id": "b", "name": "B", "course_code": "X", "prerequisites": ["a"], "facts": fact},
    ]
    with pytest.raises(ValidationError, match="cycle"):
        Catalog.model_validate(_catalog(topics=topics))
