"""Use-case helpers for loading lessons."""

from study_agent.core.models import Lesson
from study_agent.curriculum.loader import CurriculumLoader


def get_lesson(loader: CurriculumLoader, lesson_id: str) -> Lesson:
    """Load a lesson through the curriculum boundary."""
    return loader.load(lesson_id)
