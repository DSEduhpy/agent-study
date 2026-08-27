"""Provider-independent domain models for learning and progress tracking."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class Difficulty(StrEnum):
    """Difficulty levels shared by lessons and exercises."""

    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class SessionStatus(StrEnum):
    """Lifecycle states for a study session."""

    ACTIVE = "active"
    COMPLETED = "completed"


@dataclass(frozen=True)
class StudentProfile:
    """Learning preferences loaded from the student's profile configuration."""

    name: str
    daily_goal: int
    primary_areas: tuple[str, ...]
    secondary_areas: tuple[str, ...] = ()
    adaptive: bool = True
    prioritize_weak_topics: bool = True
    contextualize_professionally: bool = True
    use_analogies: bool = True
    include_practical_labs: bool = True


@dataclass(frozen=True)
class Lesson:
    """A curriculum lesson whose content is stored independently of Python code."""

    id: str
    title: str
    area: str
    topic: str
    content: str
    source_path: str = ""


@dataclass(frozen=True)
class Exercise:
    """An answerable learning activity associated with a subject and topic."""

    id: str
    subject: str
    topic: str
    difficulty: Difficulty
    question: str
    expected_answer: str
    explanation: str = ""
    professional_context: str = ""
    created_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class ExerciseAttempt:
    """One student's answer and result for an exercise."""

    exercise_id: str
    answer: str
    correct: bool
    score: float
    feedback: str = ""
    timestamp: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if not 0 <= self.score <= 100:
            raise ValueError("score must be between 0 and 100")


@dataclass(frozen=True)
class Evaluation:
    """Structured feedback produced when an answer is evaluated."""

    score: float
    correct: bool
    feedback: str
    next_focus: str = ""

    def __post_init__(self) -> None:
        if not 0 <= self.score <= 100:
            raise ValueError("score must be between 0 and 100")


@dataclass(frozen=True)
class LearningProgress:
    """Aggregated progress for one student and topic."""

    student_id: str
    topic: str
    lessons_completed: int = 0
    exercises_attempted: int = 0
    average_score: float = 0.0
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class StudySession:
    """A bounded period in which a student studies."""

    student_id: str
    started_at: datetime = field(default_factory=utc_now)
    ended_at: datetime | None = None
    lesson_ids: tuple[str, ...] = ()
    notes: str = ""
    session_id: str = ""
    status: SessionStatus = SessionStatus.ACTIVE
    interactions: tuple[str, ...] = ()


@dataclass(frozen=True)
class DatabaseRecord:
    """Small typed boundary object for repository results."""

    values: dict[str, Any]
