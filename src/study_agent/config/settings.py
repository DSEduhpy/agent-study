"""Centralized environment and profile configuration."""

from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import load_dotenv

from study_agent.core.exceptions import ConfigurationError
from study_agent.core.models import StudentProfile


@dataclass(frozen=True)
class Settings:
    """Runtime settings; secrets are read only from environment variables."""

    project_root: Path
    profile_path: Path
    database_path: Path
    ai_provider: str
    ai_model: str
    ai_api_key: str | None
    ai_timeout_seconds: float


def load_settings(project_root: Path | None = None) -> Settings:
    """Load environment settings without requiring an API key for offline use."""
    root = (project_root or Path.cwd()).resolve()
    load_dotenv(root / ".env")
    profile_path = _resolve_path(root, os.getenv("STUDY_AGENT_PROFILE", "config/profile.yaml"))
    database_path = _resolve_path(root, os.getenv("STUDY_AGENT_DATABASE", "data/study_agent.sqlite3"))
    try:
        timeout = float(os.getenv("AI_TIMEOUT_SECONDS", "30"))
    except ValueError as exc:
        raise ConfigurationError("AI_TIMEOUT_SECONDS must be a positive number") from exc
    if timeout <= 0:
        raise ConfigurationError("AI_TIMEOUT_SECONDS must be a positive number")
    return Settings(
        project_root=root,
        profile_path=profile_path,
        database_path=database_path,
        ai_provider=os.getenv("AI_PROVIDER", "openai"),
        ai_model=os.getenv("AI_MODEL", ""),
        ai_api_key=os.getenv("AI_API_KEY") or None,
        ai_timeout_seconds=timeout,
    )


def load_student_profile(path: Path) -> StudentProfile:
    """Load and validate a student profile from YAML."""
    import yaml

    if not path.is_file():
        raise ConfigurationError(f"Profile file not found: {path}")
    try:
        with path.open("r", encoding="utf-8") as profile_file:
            data = yaml.safe_load(profile_file)
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigurationError(f"Could not load profile: {path}") from exc
    if not isinstance(data, dict):
        raise ConfigurationError("Profile must contain a mapping at its root")
    try:
        student = data["student"]
        study = data["study"]
        learning = data["learning"]
        name = student["name"]
        daily_goal = study["daily_goal"]
        primary = study["primary_area"]
    except (KeyError, TypeError) as exc:
        raise ConfigurationError("Profile requires student.name, study.daily_goal, and study.primary_area") from exc
    if not isinstance(name, str) or not name.strip():
        raise ConfigurationError("student.name must be a non-empty string")
    if not isinstance(daily_goal, int) or daily_goal <= 0:
        raise ConfigurationError("study.daily_goal must be a positive integer")
    if not _valid_area_list(primary):
        raise ConfigurationError("study.primary_area must be a non-empty list of strings")
    secondary = study.get("secondary_area", [])
    if not _valid_area_list(secondary, allow_empty=True):
        raise ConfigurationError("study.secondary_area must be a list of strings")
    flags = {key: _boolean(learning, key) for key in (
        "adaptive", "prioritize_weak_topics", "contextualize_professionally",
        "use_analogies", "include_practical_labs")}
    return StudentProfile(name.strip(), daily_goal, tuple(primary), tuple(secondary), **flags)


def _resolve_path(root: Path, configured: str) -> Path:
    path = Path(configured)
    return path if path.is_absolute() else root / path


def _valid_area_list(value: object, allow_empty: bool = False) -> bool:
    return isinstance(value, list) and (allow_empty or bool(value)) and all(isinstance(item, str) and item.strip() for item in value)


def _boolean(mapping: dict[str, object], key: str) -> bool:
    value = mapping.get(key)
    if not isinstance(value, bool):
        raise ConfigurationError(f"learning.{key} must be a boolean")
    return value
