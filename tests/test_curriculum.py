from pathlib import Path

import pytest

from study_agent.core.exceptions import CurriculumError
from study_agent.curriculum.loader import CurriculumLoader


def test_lesson_loads_and_is_listed() -> None:
    loader = CurriculumLoader(Path("curriculum"))
    assert "cybersecurity/linux/permissions" in loader.list_lessons()
    lesson = loader.load("cybersecurity/linux/permissions")
    assert lesson.title == "Linux File Permissions"
    assert lesson.area == "cybersecurity"
    assert "## Conceito" in lesson.content


def test_missing_and_unsafe_lessons_fail() -> None:
    loader = CurriculumLoader("curriculum")
    with pytest.raises(CurriculumError, match="not found"):
        loader.load("cybersecurity/linux/missing")
    with pytest.raises(CurriculumError, match="escapes|Invalid"):
        loader.load("../requirements")
