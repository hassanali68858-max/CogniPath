import random
from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from agents.tutor_agent.quiz import (
    MasteryLevel,
    Question,
    TargetKind,
    TemplateQuestionGenerator,
    build_quiz,
    current_topics,
    grade_quiz,
    next_review,
    quiz_proposals,
    record_attempt,
    select_quiz_targets,
    topic_mastery,
)
from agents.tutor_agent.student import QuizAttempt
from shared.contracts import ActivityType

# MARK: - Mastery and topic selection


def test_mastery_weights_recent_attempts(student):
    assert topic_mastery(student.quiz_history, "sorting") == pytest.approx(0.5)  # 0.4 then 0.6
    assert topic_mastery(student.quiz_history, "complexity") == pytest.approx(0.6)
    assert topic_mastery(student.quiz_history, "owl") is None


def test_selects_weak_and_untested_topics_exam_first(student, context):
    targets = select_quiz_targets(student, context)
    assert [(t.topic.id, t.kind) for t in targets] == [
        ("sorting", TargetKind.WEAK),  # exam on 12 Nov
        ("dynamic-programming", TargetKind.UNTESTED),
        ("graph-search", TargetKind.UNTESTED),
        ("sparql", TargetKind.WEAK),  # no exam: weakest first
        ("rdf", TargetKind.WEAK),
        ("complexity", TargetKind.REFRESH),  # strong topics with a refresh due, exam first
        ("kg-basics", TargetKind.REFRESH),
        ("multi-agent", TargetKind.REFRESH),
    ]


def test_refresh_gap_grows_with_each_passed_quiz_in_a_row():
    def history(*scores):
        return [QuizAttempt(topic_id="t", correct=s, total=5, taken_on=date(2026, 11, 1)) for s in scores]

    assert next_review(history(), "t") is None
    assert next_review(history(4), "t") == date(2026, 11, 2)  # 1 day
    assert next_review(history(4, 5), "t") == date(2026, 11, 4)  # 3 days
    assert next_review(history(1, 5, 5, 5), "t") == date(2026, 11, 8)  # a fail resets the run: 7 days
    assert next_review(history(*[5] * 9), "t") == date(2026, 12, 1)  # the last gap repeats: 30 days


def test_strong_topic_is_not_quizzed_until_its_refresh_is_due(student, context):
    passed = [
        QuizAttempt(topic_id="owl", correct=5, total=5, taken_on=context.today - timedelta(days=days_ago))
        for days_ago in (80, 60, 40, 20, 2)
    ]
    student = student.model_copy(update={"quiz_history": passed})
    status = next(t for t in current_topics(student, context) if t.topic_id == "owl")
    assert status.next_review == context.today + timedelta(days=28)  # 5 passed in a row: 30 days
    assert "owl" not in {t.topic.id for t in select_quiz_targets(student, context)}  # after the 14-day horizon


def test_only_topics_of_current_courses_are_selected(student, context):
    no_courses = student.model_copy(update={"enrolled": []})
    assert select_quiz_targets(no_courses, context) == []


def test_current_topics_show_the_mastery_level_of_every_current_topic(student, context):
    levels = {t.topic_id: t.level for t in current_topics(student, context)}
    assert levels["kg-basics"] == MasteryLevel.STRONG
    assert levels["sorting"] == MasteryLevel.WEAK
    assert levels["owl"] == MasteryLevel.UNTESTED
    assert len(levels) == len(context.catalog.topics)


def test_courses_whose_exam_has_passed_are_not_quizzed(student, context):
    after_exam = context.model_copy(update={"today": date(2026, 11, 13)})
    courses = {t.topic.course_code for t in select_quiz_targets(student, after_exam)}
    assert courses == {"TIES4570"}


# MARK: - Planner proposals


def _proposals(student, context):
    return {p.proposal_id: p for p in quiz_proposals(select_quiz_targets(student, context), student, context)}


def test_weak_topic_gets_a_review_before_its_quiz(student, context):
    proposals = _proposals(student, context)
    review = proposals["tut-review-sorting"]
    assert review.type == ActivityType.LEARNING
    assert str(review.resource_url).startswith("https://en.wikipedia.org/")
    assert proposals["tut-quiz-sorting"].depends_on == ["tut-review-sorting"]
    assert "tut-review-graph-search" not in proposals  # untested: diagnostic quiz only


def test_prerequisite_topic_is_quizzed_first(student, context):
    proposals = _proposals(student, context)
    assert proposals["tut-review-sparql"].depends_on == ["tut-quiz-rdf"]
    assert "RDF" in proposals["tut-quiz-sparql"].reason


def test_exam_sets_the_deadline_but_not_the_value(student, context):
    proposals = _proposals(student, context)
    sorting, rdf = proposals["tut-quiz-sorting"], proposals["tut-quiz-rdf"]
    assert sorting.window.deadline == date(2026, 11, 11)  # day before the exam
    assert rdf.window.deadline == context.horizon_end
    assert sorting.value.study == rdf.value.study == 0.6
    assert proposals["tut-quiz-graph-search"].value.study == 0.3  # diagnostic


def test_refresh_quiz_stands_alone_and_starts_on_its_due_day(student, context):
    proposals = _proposals(student, context)
    refresh = proposals["tut-quiz-kg-basics"]
    assert "tut-review-kg-basics" not in proposals
    assert refresh.value.study == 0.3
    assert refresh.window.earliest == context.today  # due on 27 Oct: overdue, so now
    assert "refresh" in refresh.reason
    assert proposals["tut-review-rdf"].depends_on == []  # its prerequisite kg-basics is only a refresh


# MARK: - Building and grading a quiz


def test_template_quiz_is_repeatable_and_correct(catalog):
    quiz = build_quiz("rdf", catalog, TemplateQuestionGenerator(random.Random(1)), count=5)
    again = build_quiz("rdf", catalog, TemplateQuestionGenerator(random.Random(1)), count=5)
    assert quiz == again

    facts = {f.term: f.definition for f in catalog.topics_by_id["rdf"].facts}
    for question in quiz.questions:
        answer = question.options[question.answer_index]
        assert answer in facts or answer in facts.values()
        assert 2 <= len(question.options) <= 4


def test_question_count_is_limited_by_the_facts(catalog):
    quiz = build_quiz("kg-basics", catalog, TemplateQuestionGenerator(random.Random(0)), count=20)
    assert len(quiz.questions) == len(catalog.topics_by_id["kg-basics"].facts)


def test_unknown_topic_is_rejected(catalog):
    with pytest.raises(KeyError):
        build_quiz("nope", catalog, TemplateQuestionGenerator())


def test_grading_updates_mastery(student, catalog):
    quiz = build_quiz("owl", catalog, TemplateQuestionGenerator(random.Random(3)), count=4)
    attempt = grade_quiz(quiz, [q.answer_index for q in quiz.questions], taken_on=date(2026, 11, 3))
    assert (attempt.correct, attempt.total) == (4, 4)

    updated = record_attempt(student, attempt)
    assert topic_mastery(updated.quiz_history, "owl") == 1.0
    assert topic_mastery(student.quiz_history, "owl") is None  # original unchanged


def test_grading_needs_one_answer_per_question(catalog):
    quiz = build_quiz("owl", catalog, TemplateQuestionGenerator(random.Random(3)), count=2)
    with pytest.raises(ValueError):
        grade_quiz(quiz, [0], taken_on=date(2026, 11, 3))


def test_question_answer_must_be_an_option():
    with pytest.raises(ValidationError):
        Question(topic_id="t", prompt="?", options=["a", "b"], answer_index=2)
