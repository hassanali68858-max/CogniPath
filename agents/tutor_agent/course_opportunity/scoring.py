"""Rule-based scoring shared by course and opportunity recommendations.

score = weighted sum of interest fit and degree value, both 0-1.
Feasibility (language, prerequisites, dates) is a filter, not part of the score.
"""

from __future__ import annotations

MIN_RECOMMENDATION_SCORE = 0.3
STRONG_MATCH = 0.8

# The shared 0-1 value rubric (CogniPath Shared Proposal Format)
_RUBRIC = ((0.8, 0.9), (0.5, 0.6), (0.0, 0.3))


def interest_fit(tags: list[str], interests: list[str]) -> tuple[float, list[str]]:
    """1.0 for two or more shared tags, 0.6 for one, 0.0 for none."""
    matched = sorted(set(tags) & set(interests))
    return {0: 0.0, 1: 0.6}.get(len(matched), 1.0), matched


def study_value(score: float) -> float:
    return next(value for threshold, value in _RUBRIC if score >= threshold)


def interest_reason(matched: list[str]) -> str:
    return "matches your interest in " + join_clauses([_tag_label(t) for t in matched])


def join_clauses(parts: list[str]) -> str:
    """'a', 'a and b', 'a, b and c'."""
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


def as_sentence(parts: list[str]) -> str:
    text = join_clauses(parts)
    return text[:1].upper() + text[1:] + "."


def _tag_label(tag: str) -> str:
    """'knowledge-graphs' -> 'knowledge graphs', 'ai' -> 'AI'."""
    return " ".join(word.upper() if len(word) <= 2 else word for word in tag.split("-"))
