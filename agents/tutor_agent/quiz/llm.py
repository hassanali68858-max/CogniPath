"""LLM question generator: a local Ollama model writes the questions from the topic's facts.

Every question the model returns is checked against ``Question``. Small models often mark
the wrong option as correct, so a second call answers the questions again (options
reshuffled, temperature 0) and only questions where both answers agree are kept.
If the model cannot be reached, or too few questions pass, the fallback generator
fills the gap, so a quiz is always complete.

Configuration (environment variables):

- ``TUTOR_QUESTION_GENERATOR``: ``template`` (default) or ``ollama``
- ``TUTOR_OLLAMA_URL``: default ``http://localhost:11434``
- ``TUTOR_OLLAMA_MODEL``: default ``llama3.2``
"""

from __future__ import annotations

import json
import logging
import random
from collections.abc import Mapping

import httpx
from pydantic import ValidationError

from ..catalog import Fact, Topic
from .generator import MAX_OPTIONS, QuestionGenerator, TemplateQuestionGenerator
from .models import Question

GENERATOR_ENV = "TUTOR_QUESTION_GENERATOR"
OLLAMA_URL_ENV = "TUTOR_OLLAMA_URL"
OLLAMA_MODEL_ENV = "TUTOR_OLLAMA_MODEL"
DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "llama3.2"
REQUEST_TIMEOUT_S = 60.0
TEMPERATURE = 0.7  # some variety between quizzes on the same topic
CHECK_TEMPERATURE = 0.0

SYSTEM_PROMPT = (
    "You write multiple-choice quiz questions for university students. "
    "Use only the facts you are given. Each question has exactly one correct option "
    f"and at most {MAX_OPTIONS} options in total. Wrong options must be plausible. "
    "Test understanding, not only definitions. Reply with JSON only."
)

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string"},
                    "options": {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": MAX_OPTIONS},
                    "answer_index": {"type": "integer"},
                },
                "required": ["prompt", "options", "answer_index"],
            },
        }
    },
    "required": ["questions"],
}

CHECK_PROMPT = (
    "Answer each multiple-choice question using only the facts you are given. "
    "Reply with JSON only: the 0-based index of the correct option for each question, in order."
)

CHECK_SCHEMA = {
    "type": "object",
    "properties": {"answers": {"type": "array", "items": {"type": "integer"}}},
    "required": ["answers"],
}

logger = logging.getLogger(__name__)


class OllamaQuestionGenerator:
    def __init__(self, client: httpx.Client, model: str, fallback: QuestionGenerator) -> None:
        self._client = client
        self._model = model
        self._fallback = fallback
        self._rng = random.Random()

    def generate(self, topic: Topic, distractors: list[Fact], count: int) -> list[Question]:
        try:
            questions = self._ask_model(topic, count)
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as err:
            logger.warning("Ollama question generation failed for %s: %s", topic.id, err)
            questions = []
        if len(questions) < count:
            questions += _new_prompts(self._fallback.generate(topic, distractors, count), questions)
        return questions[:count]

    def _ask_model(self, topic: Topic, count: int) -> list[Question]:
        raw = self._chat(SYSTEM_PROMPT, _user_prompt(topic, count), RESPONSE_SCHEMA, TEMPERATURE)["questions"]
        questions = [self._shuffled(q) for q in _valid_questions(topic.id, raw)]
        return self._confirmed(topic, questions) if questions else []

    def _confirmed(self, topic: Topic, questions: list[Question]) -> list[Question]:
        """The questions the model answers the same way a second time."""
        answers = self._chat(CHECK_PROMPT, _check_prompt(topic, questions), CHECK_SCHEMA, CHECK_TEMPERATURE)["answers"]
        if len(answers) != len(questions):
            raise ValueError(f"check returned {len(answers)} answers for {len(questions)} questions")
        confirmed = [q for q, answer in zip(questions, answers) if answer == q.answer_index]
        if len(confirmed) < len(questions):
            logger.info("Dropped %d unconfirmed questions on %s", len(questions) - len(confirmed), topic.id)
        return confirmed

    def _chat(self, system: str, user: str, schema: dict, temperature: float) -> dict:
        response = self._client.post(
            "/api/chat",
            json={
                "model": self._model,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "format": schema,
                "stream": False,
                "options": {"temperature": temperature},
            },
        )
        response.raise_for_status()
        return json.loads(response.json()["message"]["content"])

    def _shuffled(self, question: Question) -> Question:
        """Models tend to put the right answer first; shuffle so its position says nothing."""
        correct = question.options[question.answer_index]
        options = self._rng.sample(question.options, k=len(question.options))
        return question.model_copy(update={"options": options, "answer_index": options.index(correct)})


def generator_from_env(env: Mapping[str, str], rng: random.Random) -> QuestionGenerator:
    template = TemplateQuestionGenerator(rng)
    choice = env.get(GENERATOR_ENV, "template")
    if choice == "template":
        return template
    if choice == "ollama":
        client = httpx.Client(base_url=env.get(OLLAMA_URL_ENV, DEFAULT_OLLAMA_URL), timeout=REQUEST_TIMEOUT_S)
        return OllamaQuestionGenerator(client, env.get(OLLAMA_MODEL_ENV, DEFAULT_OLLAMA_MODEL), template)
    raise ValueError(f"unknown {GENERATOR_ENV} {choice!r}; use 'template' or 'ollama'")


def _user_prompt(topic: Topic, count: int) -> str:
    return f"{_facts(topic)}\n\nWrite {count} different questions about this topic."


def _check_prompt(topic: Topic, questions: list[Question]) -> str:
    numbered = "\n\n".join(
        f"Question {n}: {q.prompt}\n" + "\n".join(f"  {i}. {option}" for i, option in enumerate(q.options))
        for n, q in enumerate(questions, start=1)
    )
    return f"{_facts(topic)}\n\n{numbered}"


def _facts(topic: Topic) -> str:
    facts = "\n".join(f"- {f.term}: {f.definition}" for f in topic.facts)
    return f"Topic: {topic.name}\nFacts:\n{facts}"


def _valid_questions(topic_id: str, raw: object) -> list[Question]:
    """The well-formed questions with unique prompts; the rest of the model output is dropped."""
    questions: list[Question] = []
    for item in raw if isinstance(raw, list) else []:
        try:
            question = Question(topic_id=topic_id, **item)
        except (ValidationError, TypeError):
            continue
        if len(question.options) <= MAX_OPTIONS:
            questions.append(question)
    return _new_prompts(questions, [])


def _new_prompts(candidates: list[Question], existing: list[Question]) -> list[Question]:
    seen = {q.prompt for q in existing}
    unique = []
    for question in candidates:
        if question.prompt not in seen:
            seen.add(question.prompt)
            unique.append(question)
    return unique
