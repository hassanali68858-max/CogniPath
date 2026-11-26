import pytest
from fastapi.testclient import TestClient

from agents.planner_agent.store import PlannerStore, ProposalStatus
from agents.tutor_agent.quiz import Question
from backend.main import build_app
from backend.tutor import OpenQuizzes, QuizHistory, open_quizzes, question_generator, quiz_history

PARAMS = {"today": "2026-11-02", "days": 14}


@pytest.fixture
def store():
    return PlannerStore("sqlite://")


@pytest.fixture
def client(store):
    app = build_app()
    app.state.store = store
    history, quizzes, generator = QuizHistory(), OpenQuizzes(), KnownAnswerGenerator()
    app.dependency_overrides[quiz_history] = lambda: history
    app.dependency_overrides[open_quizzes] = lambda: quizzes
    app.dependency_overrides[question_generator] = lambda: generator
    with TestClient(app) as c:
        yield c


def _tutor_ids(store, status=ProposalStatus.ACTIVE):
    return {p.proposal_id for p in store.list_proposals("student001", statuses=[status]) if p.source_agent == "tutor"}


def test_report_returns_progress_forums_and_proposals(client):
    r = client.get("/tutor/student001/report", params=PARAMS)
    assert r.status_code == 200
    body = r.json()
    assert body["progress"]["status"] == "at_risk"
    assert body["forums"] and body["proposals"]
    assert _level(body, "sorting") == "weak" and _level(body, "owl") == "untested"


def test_unknown_student_is_404(client):
    assert client.get("/tutor/nobody/report", params=PARAMS).status_code == 404


def test_the_catalog_source_is_the_seed_data_by_default(client):
    r = client.get("/tutor/catalog/source")
    assert r.status_code == 200
    assert r.json() == {"source": "seed", "url": None, "linked": {}, "unavailable": []}


def test_upcoming_courses_list_courses_not_taken_yet(client):
    r = client.get("/tutor/student001/courses", params={"today": PARAMS["today"]})
    assert r.status_code == 200
    codes = [c["code"] for c in r.json()]
    assert codes and "COG1100" not in codes  # completed
    assert all(not c["from_sisu"] for c in r.json())


def test_proposals_are_stored_for_the_planner(client, store):
    r = client.post("/tutor/student001/proposals", params=PARAMS)
    assert r.status_code == 201 and r.json()["stored"] == 19
    assert "tut-quiz-sorting" in _tutor_ids(store)


def test_rerun_withdraws_proposals_the_agent_no_longer_makes(client, store):
    client.post("/tutor/student001/proposals", params=PARAMS)
    # By 20 Dec registrations have closed and the Algorithms exam is over.
    r = client.post("/tutor/student001/proposals", params={"today": "2026-12-20", "days": 14})
    withdrawn = set(r.json()["withdrawn"])
    assert {"tut-register-cog2100", "tut-quiz-sorting"} <= withdrawn
    assert withdrawn == _tutor_ids(store, ProposalStatus.WITHDRAWN)
    assert "tut-quiz-rdf" in _tutor_ids(store)  # TIES4570 has no exam, so its quizzes stay


def test_quiz_hides_the_answers(client):
    quiz = _new_quiz(client, "sorting", questions=3)
    assert len(quiz["questions"]) == 3
    assert set(quiz["questions"][0]) == {"prompt", "options"}


def test_quiz_on_unknown_topic_is_404(client):
    r = client.post("/tutor/student001/quizzes", json={"topic_id": "nothing"})
    assert r.status_code == 404


def test_wrong_number_of_answers_is_422(client):
    quiz = _new_quiz(client, "sorting", questions=3)
    assert _answer(client, quiz, [RIGHT]).status_code == 422


def test_a_quiz_is_graded_once_and_only_for_its_student(client):
    quiz = _new_quiz(client, "sorting")
    other = client.post(f"/tutor/student002/quizzes/{quiz['quiz_id']}/answers", json={"answers": [RIGHT] * 5})
    assert other.status_code == 404
    assert _answer(client, quiz, [RIGHT] * 5).status_code == 200
    assert _answer(client, quiz, [RIGHT] * 5).status_code == 404


def test_a_good_quiz_makes_the_topic_strong_and_schedules_a_refresh(client, store):
    client.post("/tutor/student001/proposals", params=PARAMS)
    quiz = _new_quiz(client, "sorting")

    result = _answer(client, quiz, [RIGHT] * len(quiz["questions"])).json()

    assert result["correct"] == result["total"]
    assert result["mastery_after"] > result["mastery_before"]
    report = client.get("/tutor/student001/report", params=PARAMS).json()
    assert _level(report, "sorting") == "strong"
    refresh = next(p for p in report["proposals"] if p["proposal_id"] == "tut-quiz-sorting")
    assert refresh["window"]["earliest"] == "2026-11-05"  # passed the 29 Oct and today's quiz: a 3-day gap
    withdrawn = client.post("/tutor/student001/proposals", params=PARAMS).json()["withdrawn"]
    assert "tut-review-sorting" in withdrawn


RIGHT = 0  # KnownAnswerGenerator always puts the right answer first


class KnownAnswerGenerator:
    def generate(self, topic, distractors, count):
        return [
            Question(topic_id=topic.id, prompt=f"Question {n}", options=["right", "wrong"], answer_index=RIGHT)
            for n in range(count)
        ]


def _new_quiz(client, topic_id, questions=5):
    r = client.post("/tutor/student001/quizzes", json={"topic_id": topic_id, "questions": questions})
    assert r.status_code == 201
    return r.json()


def _answer(client, quiz, answers):
    url = f"/tutor/student001/quizzes/{quiz['quiz_id']}/answers"
    return client.post(url, params={"today": "2026-11-02"}, json={"answers": answers})


def _level(report, topic_id):
    return next(t["level"] for t in report["topics"] if t["topic_id"] == topic_id)
