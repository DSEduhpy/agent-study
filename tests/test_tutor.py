from pathlib import Path

import pytest

from study_agent.ai.provider import AIProvider
from study_agent.config.settings import load_student_profile
from study_agent.core.models import StudySession
from study_agent.curriculum.loader import CurriculumLoader
from study_agent.database.sqlite import SQLiteDatabase
from study_agent.learning.tutor import TutorContext, TutorEngine
from study_agent.memory.repository import LearningRepository


class FakeAIProvider(AIProvider):
    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []

    def generate(self, prompt: str, *, system: str | None = None) -> str:
        self.calls.append((prompt, system))
        return f"fake response {len(self.calls)}"

    def generate_structured(self, prompt: str, schema: type) -> object:
        raise NotImplementedError


@pytest.fixture
def engine(tmp_path: Path) -> tuple[TutorEngine, FakeAIProvider]:
    provider = FakeAIProvider()
    profile = load_student_profile(Path("config/profile.yaml"))
    tutor = TutorEngine(
        CurriculumLoader("curriculum"), provider,
        LearningRepository(SQLiteDatabase(
            tmp_path / "study.sqlite3")), profile, "prompts",
    )
    return tutor, provider


def test_context_and_session_lifecycle(engine: tuple[TutorEngine, FakeAIProvider]) -> None:
    tutor, _ = engine
    session = tutor.start_session(
        "student-1", "cybersecurity/linux/permissions")
    context = tutor._context(session, "Understand chmod")
    assert isinstance(context, TutorContext)
    assert context.lesson.title == "Linux File Permissions"
    completed = tutor.finish_session(session)
    assert completed.ended_at is not None
    assert completed.status.value == "completed"
    with tutor.repository.database.connection() as connection:
        row = connection.execute(
            "SELECT status, ended_at FROM study_sessions WHERE session_id = ?",
            (session.session_id,),
        ).fetchone()
    assert row["status"] == "completed"
    assert row["ended_at"] is not None


def test_explanation_and_repeated_question_keep_context(engine: tuple[TutorEngine, FakeAIProvider]) -> None:
    tutor, provider = engine
    session = tutor.start_session("student-1", "data_science/sql/joins")
    assert tutor.explain(session)
    assert tutor.ask(session, "I do not understand LEFT JOIN")
    assert len(provider.calls) == 2
    assert "Student question:" in provider.calls[1][0]
    assert "Lesson content:" in provider.calls[1][0]
    assert "Previous interactions: 1" in provider.calls[1][0]


def test_socratic_mode_is_explicit(engine: tuple[TutorEngine, FakeAIProvider]) -> None:
    tutor, provider = engine
    session = tutor.start_session("student-1", "data_science/sql/joins")
    tutor.ask(session, "Which join should I use?", socratic=True)
    assert "Socratic" in provider.calls[0][0]


def test_empty_question_is_rejected(engine: tuple[TutorEngine, FakeAIProvider]) -> None:
    tutor, _ = engine
    session = tutor.start_session("student-1", "data_science/sql/joins")
    with pytest.raises(ValueError, match="empty"):
        tutor.ask(session, " ")
