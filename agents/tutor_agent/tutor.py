"""Tutor Agent entry point: runs both sub-agents and returns one result.

``propose`` is the Planner-facing contract (see agents/README.md).
``run`` also returns the progress report and forum links for the frontend.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from shared.contracts import ActivityProposal

from .catalog import TutorContext
from .course_opportunity import (
    ForumLink,
    ProgressReport,
    advisor_proposal,
    build_progress_report,
    match_forums,
    recommend_courses,
    recommend_opportunities,
)
from .quiz import TopicStatus, current_topics, quiz_proposals, select_quiz_targets
from .student import StudentProfile


class TutorOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposals: list[ActivityProposal]
    progress: ProgressReport
    forums: list[ForumLink]
    topics: list[TopicStatus]


def run(profile: StudentProfile, context: TutorContext) -> TutorOutput:
    progress = build_progress_report(profile, context)
    advisor = advisor_proposal(progress, profile, context)
    proposals = [
        *recommend_courses(profile, context),
        *recommend_opportunities(profile, context),
        *quiz_proposals(select_quiz_targets(profile, context), profile, context),
        *([advisor] if advisor else []),
    ]
    return TutorOutput(
        proposals=proposals,
        progress=progress,
        forums=match_forums(profile, context),
        topics=current_topics(profile, context),
    )


def propose(profile: StudentProfile, context: TutorContext) -> list[ActivityProposal]:
    return run(profile, context).proposals
