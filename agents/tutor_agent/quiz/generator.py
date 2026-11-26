"""Question generators. The rest of the Quiz Agent depends only on ``QuestionGenerator``.

``TemplateQuestionGenerator`` needs no LLM, so tests and demos always work.
``llm.OllamaQuestionGenerator`` implements the same protocol with a local LLM.
"""

from __future__ import annotations

import random
from typing import Optional, Protocol

from ..catalog import Fact, Topic
from .models import Question

MAX_OPTIONS = 4


class QuestionGenerator(Protocol):
    def generate(self, topic: Topic, distractors: list[Fact], count: int) -> list[Question]:
        """Up to ``count`` questions on ``topic``; ``distractors`` are facts from other topics."""
        ...


class TemplateQuestionGenerator:
    """Multiple-choice questions from the topic's facts.

    Questions alternate between "which term matches this definition" and
    "what does this term mean". Wrong options come from the topic's other facts
    first, then from ``distractors``.
    """

    def __init__(self, rng: Optional[random.Random] = None) -> None:
        self._rng = rng or random.Random()

    def generate(self, topic: Topic, distractors: list[Fact], count: int) -> list[Question]:
        facts = self._rng.sample(topic.facts, k=min(count, len(topic.facts)))
        questions = []
        for i, fact in enumerate(facts):
            ask_for_term = i % 2 == 0
            others = [f for f in topic.facts if f != fact]
            pool = self._shuffled(others) + self._shuffled(distractors)
            pick = (lambda f: f.term) if ask_for_term else (lambda f: f.definition)
            correct = pick(fact)
            wrong = _unique([pick(f) for f in pool if pick(f) != correct])[: MAX_OPTIONS - 1]
            if not wrong:
                continue
            options = self._shuffled(wrong + [correct])
            prompt = (
                f"Which term matches this description? {fact.definition}"
                if ask_for_term
                else f"What does '{fact.term}' mean?"
            )
            questions.append(
                Question(topic_id=topic.id, prompt=prompt, options=options, answer_index=options.index(correct))
            )
        return questions

    def _shuffled(self, items: list) -> list:
        return self._rng.sample(items, k=len(items))


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
