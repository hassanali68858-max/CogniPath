"""Live course data from the University of Jyväskylä Sisu, through its public Kori API.

Kori needs no login and holds no personal data. A student's completed courses and study
plan are in Sisu's Ori and Osuva APIs, which need a JYU login or integration credentials
from the university, so students still come from the seed files.

``data/seed/tutor/sisu_courses.json`` links seed courses to real JYU courses. For a linked
course, Sisu supplies the code, name, credits, teaching language and published offerings.
The module, tags and prerequisites stay as in the seed data. A course that Sisu cannot
supply keeps its seed data.

Configuration (environment variables):

- ``TUTOR_CATALOG_SOURCE``: ``seed`` (default) or ``sisu``
- ``TUTOR_SISU_URL``: default ``https://sisu.jyu.fi``
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Literal, Optional

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .catalog import Catalog, Course, CourseOffering
from .seed import DEFAULT_SEED_DIR, load_catalog, load_sisu_links

SOURCE_ENV = "TUTOR_CATALOG_SOURCE"
SISU_URL_ENV = "TUTOR_SISU_URL"
DEFAULT_SISU_URL = "https://sisu.jyu.fi"
JYU_UNIVERSITY_ID = "jyu-university-root-id"
REQUEST_TIMEOUT_S = 20.0
SEARCH_LIMIT = 10
EXAM_TYPE_PREFIX = "urn:code:course-unit-realisation-type:exam"
LANGUAGE_URN_PREFIX = "urn:code:language:"

logger = logging.getLogger(__name__)


class SisuCourse(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    name: str
    credits: float = Field(..., gt=0)
    language: Optional[str] = None
    offerings: list[CourseOffering]


class CatalogSource(BaseModel):
    """The catalog the Tutor Agent uses, and which courses came from Sisu."""

    model_config = ConfigDict(frozen=True)

    source: Literal["seed", "sisu"]
    url: Optional[str] = None
    catalog: Catalog
    linked: dict[str, str] = Field(default_factory=dict)  # seed code -> Sisu code, loaded from Sisu
    unavailable: list[str] = Field(default_factory=list)  # linked seed codes Sisu could not supply


class KoriClient:
    def __init__(self, client: httpx.Client, university_id: str = JYU_UNIVERSITY_ID) -> None:
        self._client = client
        self._university_id = university_id

    def course(self, code: str) -> Optional[SisuCourse]:
        unit = self._course_unit(code)
        if unit is None:
            return None
        realisations = [r for item_id in unit.get("assessmentItemIds", []) for r in self._realisations(item_id)]
        return _sisu_course(unit, realisations)

    def _course_unit(self, code: str) -> Optional[dict]:
        found = self._get(
            "/kori/api/course-unit-search",
            {
                "fullTextQuery": code,
                "limit": SEARCH_LIMIT,
                "start": 0,
                "uiLang": "en",
                "universityOrgId": self._university_id,
                "validity": "ONGOING_AND_FUTURE",
            },
        )
        return next((unit for unit in found["searchResults"] if unit["code"] == code), None)

    def _realisations(self, assessment_item_id: str) -> list[dict]:
        return self._get("/kori/api/course-unit-realisations/published", {"assessmentItemId": assessment_item_id})

    def _get(self, path: str, params: dict) -> dict | list:
        response = self._client.get(path, params=params)
        response.raise_for_status()
        return response.json()


def catalog_from_env(env: Mapping[str, str], seed_dir: Path = DEFAULT_SEED_DIR) -> CatalogSource:
    seed = load_catalog(seed_dir)
    choice = env.get(SOURCE_ENV, "seed")
    if choice == "seed":
        return CatalogSource(source="seed", catalog=seed)
    if choice == "sisu":
        url = env.get(SISU_URL_ENV, DEFAULT_SISU_URL)
        with httpx.Client(base_url=url, timeout=REQUEST_TIMEOUT_S, follow_redirects=True) as client:
            synced = sync_catalog(seed, load_sisu_links(seed_dir), KoriClient(client))
        return synced.model_copy(update={"url": url})
    raise ValueError(f"unknown {SOURCE_ENV} {choice!r}; use 'seed' or 'sisu'")


def sync_catalog(seed: Catalog, links: Mapping[str, str], kori: KoriClient) -> CatalogSource:
    """The seed catalog with each linked course replaced by its live Sisu data."""
    courses: list[Course] = []
    linked: dict[str, str] = {}
    unavailable: list[str] = []
    for course in seed.courses:
        sisu_code = links.get(course.code)
        sisu = _fetch(kori, sisu_code) if sisu_code else None
        if sisu is None:
            courses.append(course)
            if sisu_code:
                unavailable.append(course.code)
            continue
        linked[course.code] = sisu.code
        courses.append(_with_sisu_data(course, sisu))
    catalog = Catalog(
        programmes=seed.programmes, courses=courses, opportunities=seed.opportunities, topics=seed.topics
    )
    return CatalogSource(source="sisu", catalog=catalog, linked=linked, unavailable=unavailable)


def _fetch(kori: KoriClient, code: str) -> Optional[SisuCourse]:
    try:
        course = kori.course(code)
    except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError) as err:
        logger.warning("Could not load %s from Sisu: %s", code, err)
        return None
    if course is None:
        logger.warning("Sisu has no current course %s", code)
    return course


def _with_sisu_data(course: Course, sisu: SisuCourse) -> Course:
    update = {"sisu_code": sisu.code, "name": sisu.name, "credits": sisu.credits, "offerings": sisu.offerings}
    if sisu.language:
        update["language"] = sisu.language
    return course.model_copy(update=update)


def _sisu_course(unit: dict, realisations: list[dict]) -> SisuCourse:
    offerings = sorted(
        (o for o in map(_offering, realisations) if o is not None), key=lambda o: o.start
    )
    teaching = [r for r in realisations if not _is_exam(r)]
    languages = [r["teachingLanguageUrn"] for r in teaching if r.get("teachingLanguageUrn")]
    languages += unit.get("attainmentLanguageUrns") or []
    return SisuCourse(
        code=unit["code"],
        name=unit["name"],  # the search answers in uiLang, so this is a plain string
        credits=unit["credits"]["min"],
        language=languages[0].removeprefix(LANGUAGE_URN_PREFIX) if languages else None,
        offerings=offerings,
    )


def _offering(realisation: dict) -> Optional[CourseOffering]:
    """A teaching realisation as a course offering; ``None`` for exams and unusable dates.

    Sisu date ranges exclude their end. Sisu often allows enrolment after a course has
    started, but the Tutor proposes registering by the start day.
    """
    if _is_exam(realisation):
        return None
    try:
        period = realisation["activityPeriod"]
        start = date.fromisoformat(period["startDate"])
        end = date.fromisoformat(period["endDate"]) - timedelta(days=1)
        enrolment_end = (realisation.get("enrolmentPeriod") or {}).get("endDateTime")
        deadline = (datetime.fromisoformat(enrolment_end) - timedelta(seconds=1)).date() if enrolment_end else start
        return CourseOffering(period=f"{start:%b %Y}", start=start, end=end, registration_deadline=min(deadline, start))
    except (KeyError, TypeError, ValueError, ValidationError):
        return None


def _is_exam(realisation: dict) -> bool:
    return str(realisation.get("courseUnitRealisationTypeUrn", "")).startswith(EXAM_TYPE_PREFIX)
