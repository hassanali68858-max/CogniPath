from datetime import date

import httpx
import pytest

from agents.tutor_agent.course_opportunity import upcoming_courses
from agents.tutor_agent.sisu import KoriClient, catalog_from_env, sync_catalog

LINKS = {"COG2500": "ITKA2004", "COG2300": "TIES4910"}
DATABASES = {
    "code": "ITKA2004",
    "name": "Databases and data management",
    "credits": {"min": 5, "max": 5},
    "assessmentItemIds": ["item-db"],
    "attainmentLanguageUrns": ["urn:code:language:fi"],
}
LECTURES = {
    "courseUnitRealisationTypeUrn": "urn:code:course-unit-realisation-type:teaching-participation-lectures",
    "activityPeriod": {"startDate": "2027-01-11", "endDate": "2027-03-20"},
    "enrolmentPeriod": {"startDateTime": "2026-12-01T00:00:00", "endDateTime": "2027-01-23T23:59:00"},
    "teachingLanguageUrn": "urn:code:language:fi",
}
EXAM = {
    **LECTURES,
    "courseUnitRealisationTypeUrn": "urn:code:course-unit-realisation-type:exam-exam",
    "activityPeriod": {"startDate": "2027-03-25", "endDate": "2027-03-26"},
}


def test_a_linked_course_takes_its_code_name_credits_language_and_offerings_from_sisu(catalog):
    synced = sync_catalog(catalog, LINKS, _kori(_fake_kori()))
    course = synced.catalog.courses_by_code["COG2500"]

    assert course.label == "ITKA2004 Databases and data management"
    assert (course.credits, course.language) == (5, "fi")
    assert course.module_id == catalog.courses_by_code["COG2500"].module_id
    [offering] = course.offerings
    assert (offering.start, offering.end) == (date(2027, 1, 11), date(2027, 3, 19))


def test_registration_closes_by_the_start_day_even_when_sisu_allows_late_enrolment(catalog):
    synced = sync_catalog(catalog, LINKS, _kori(_fake_kori()))

    [offering] = synced.catalog.courses_by_code["COG2500"].offerings
    assert offering.registration_deadline == date(2027, 1, 11)


def test_a_course_sisu_does_not_have_keeps_its_seed_data(catalog):
    synced = sync_catalog(catalog, LINKS, _kori(_fake_kori()))

    assert synced.linked == {"COG2500": "ITKA2004"}
    assert synced.unavailable == ["COG2300"]
    assert synced.catalog.courses_by_code["COG2300"] == catalog.courses_by_code["COG2300"]


def test_the_seed_catalog_is_kept_when_sisu_cannot_be_reached(catalog):
    def refuse(request):
        raise httpx.ConnectError("connection refused", request=request)

    synced = sync_catalog(catalog, LINKS, _kori(refuse))

    assert synced.catalog.courses == catalog.courses
    assert sorted(synced.unavailable) == sorted(LINKS)


def test_the_seed_catalog_is_the_default_source(catalog):
    source = catalog_from_env({})

    assert source.source == "seed" and source.catalog.courses == catalog.courses


def test_an_unknown_catalog_source_is_an_error():
    with pytest.raises(ValueError, match="TUTOR_CATALOG_SOURCE"):
        catalog_from_env({"TUTOR_CATALOG_SOURCE": "moodle"})


def test_upcoming_courses_skip_taken_courses_and_come_soonest_first(catalog, student):
    synced = sync_catalog(catalog, LINKS, _kori(_fake_kori()))

    upcoming = upcoming_courses(student, synced.catalog, date(2026, 11, 2))

    taken = student.completed_codes | student.enrolled_codes
    assert not {c.code for c in upcoming} & taken
    assert [c.start for c in upcoming] == sorted(c.start for c in upcoming)
    databases = next(c for c in upcoming if c.code == "ITKA2004")
    assert databases.from_sisu and databases.registration_deadline == date(2027, 1, 11)


def _kori(handler) -> KoriClient:
    return KoriClient(httpx.Client(base_url="https://sisu.example", transport=httpx.MockTransport(handler)))


def _fake_kori():
    """Kori with one course, ITKA2004, that has a lecture course and an exam."""

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/kori/api/course-unit-search":
            query = request.url.params["fullTextQuery"]
            return httpx.Response(200, json={"searchResults": [DATABASES] if query == "ITKA2004" else []})
        if request.url.path == "/kori/api/course-unit-realisations/published":
            return httpx.Response(200, json=[LECTURES, EXAM])
        return httpx.Response(404)

    return handle
