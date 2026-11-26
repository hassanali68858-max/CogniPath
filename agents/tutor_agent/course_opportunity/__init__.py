"""Course and Opportunity sub-agent: Sisu study plan, degree progress, opportunities beyond Sisu."""

from .courses import recommend_courses, upcoming_courses
from .models import ForumLink, ProgressReport, ProgressStatus, ProgressWarning, UpcomingCourse, WarningKind
from .opportunities import match_forums, recommend_opportunities
from .progress import advisor_proposal, build_progress_report

__all__ = [
    "ForumLink",
    "ProgressReport",
    "ProgressStatus",
    "ProgressWarning",
    "UpcomingCourse",
    "WarningKind",
    "advisor_proposal",
    "build_progress_report",
    "match_forums",
    "recommend_courses",
    "recommend_opportunities",
    "upcoming_courses",
]
