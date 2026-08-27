from pathlib import Path

import pytest

from study_agent.config.settings import load_student_profile
from study_agent.core.exceptions import ConfigurationError


def test_profile_loads() -> None:
    profile = load_student_profile(Path("config/profile.yaml"))
    assert profile.name == "Eduardo"
    assert profile.primary_areas == ("cybersecurity",)
    assert profile.daily_goal == 5


def test_missing_profile_fails_clearly(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="not found"):
        load_student_profile(tmp_path / "missing.yaml")
