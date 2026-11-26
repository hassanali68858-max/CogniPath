import json
import random
import re

import httpx
import pytest

from agents.tutor_agent.quiz import (
    OllamaQuestionGenerator,
    TemplateQuestionGenerator,
    build_quiz,
    generator_from_env,
)

GOOD = {"prompt": "What does RDF describe?", "options": ["Graphs of triples", "Tables", "Images"], "answer_index": 0}
TRUE_OPTIONS = {"Graphs of triples"}


def test_model_questions_are_used_with_shuffled_options(catalog):
    quiz = build_quiz("rdf", catalog, _generator(_model([GOOD])), 1)

    question = quiz.questions[0]
    assert question.prompt == GOOD["prompt"]
    assert question.options[question.answer_index] == "Graphs of triples"
    assert sorted(question.options) == sorted(GOOD["options"])


def test_questions_the_check_answers_differently_are_replaced(catalog):
    wrong_key = {"prompt": "Wrong key", "options": ["Tables", "Graphs of triples"], "answer_index": 0}
    quiz = build_quiz("rdf", catalog, _generator(_model([GOOD, wrong_key])), 2)

    prompts = [q.prompt for q in quiz.questions]
    assert GOOD["prompt"] in prompts
    assert "Wrong key" not in prompts
    assert len(prompts) == 2


def test_invalid_model_questions_are_dropped_and_the_fallback_fills_the_gap(catalog):
    wrong_index = {**GOOD, "prompt": "Bad", "answer_index": 7}
    one_option = {**GOOD, "prompt": "Too few", "options": ["only"], "answer_index": 0}
    quiz = build_quiz("rdf", catalog, _generator(_model([GOOD, GOOD, wrong_index, one_option])), 3)

    prompts = [q.prompt for q in quiz.questions]
    assert len(prompts) == 3
    assert prompts.count(GOOD["prompt"]) == 1
    assert {"Bad", "Too few"}.isdisjoint(prompts)


def test_the_fallback_writes_the_quiz_when_the_model_cannot_be_reached(catalog):
    def refuse(request):
        raise httpx.ConnectError("connection refused", request=request)

    quiz = build_quiz("rdf", catalog, _generator(refuse), 3)
    template = build_quiz("rdf", catalog, TemplateQuestionGenerator(random.Random(0)), 3)

    assert quiz.questions == template.questions


def test_unreadable_model_output_uses_the_fallback(catalog):
    def garbage(request):
        return httpx.Response(200, json={"message": {"content": "not json"}})

    assert len(build_quiz("rdf", catalog, _generator(garbage), 3).questions) == 3


def test_the_generator_is_chosen_from_the_environment():
    assert isinstance(generator_from_env({}, random.Random()), TemplateQuestionGenerator)
    ollama = {"TUTOR_QUESTION_GENERATOR": "ollama"}
    assert isinstance(generator_from_env(ollama, random.Random()), OllamaQuestionGenerator)
    with pytest.raises(ValueError, match="TUTOR_QUESTION_GENERATOR"):
        generator_from_env({"TUTOR_QUESTION_GENERATOR": "gpt"}, random.Random())


def _generator(handler) -> OllamaQuestionGenerator:
    client = httpx.Client(base_url="http://ollama.test", transport=httpx.MockTransport(handler))
    return OllamaQuestionGenerator(client, "test-model", TemplateQuestionGenerator(random.Random(0)))


def _model(questions: list[dict]):
    """A fake Ollama that writes ``questions`` and, when asked to check, picks the options in TRUE_OPTIONS."""

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if "answers" in body["format"]["properties"]:
            reply = {"answers": _true_answers(body["messages"][-1]["content"])}
        else:
            reply = {"questions": questions}
        return httpx.Response(200, json={"message": {"role": "assistant", "content": json.dumps(reply)}})

    return handler


def _true_answers(check_prompt: str) -> list[int]:
    answers = []
    for block in check_prompt.split("Question ")[1:]:
        options = re.findall(r"^  (\d+)\. (.+)$", block, flags=re.MULTILINE)
        answers.append(next((int(i) for i, text in options if text in TRUE_OPTIONS), 0))
    return answers
