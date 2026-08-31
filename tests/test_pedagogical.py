from pathlib import Path

import pytest

from study_agent.ai.provider import AIProvider
from study_agent.config.settings import load_student_profile
from study_agent.core.models import StudySession
from study_agent.curriculum.loader import CurriculumLoader
from study_agent.database.sqlite import SQLiteDatabase
from study_agent.learning.pedagogy import (
    LessonState,
    PedagogicalDecision,
    PedagogicalDecisionAction,
    PedagogicalEngine,
)
from study_agent.learning.tutor import TutorEngine
from study_agent.memory.repository import LearningRepository


class FakeAIProvider(AIProvider):
    def generate(self, prompt: str, *, system: str | None = None) -> str:
        return "fake educational response"

    def generate_structured(self, prompt: str, schema: type, *, system: str | None = None):
        raise NotImplementedError


@pytest.fixture
def pedagogical_engine(tmp_path: Path) -> PedagogicalEngine:
    profile = load_student_profile(Path("config/profile.yaml"))
    curriculum = CurriculumLoader(Path("curriculum"))
    repository = LearningRepository(
        SQLiteDatabase(tmp_path / "pedagogy.sqlite3"))
    tutor = TutorEngine(curriculum, FakeAIProvider(),
                        repository, profile, Path("prompts"))
    return PedagogicalEngine(tutor, curriculum, repository, profile, Path("prompts"))


def test_lesson_state_machine_transitions(pedagogical_engine: PedagogicalEngine) -> None:
    tutor = pedagogical_engine.tutor
    session = tutor.start_session("student-pedagogy", "data_science/sql/joins")
    state = pedagogical_engine.start_session(session)
    assert state.pedagogical_state == LessonState.ORIENT
    assert LessonState.ORIENT.next_state(LessonState.DIAGNOSE)
    assert pedagogical_engine.advance_state(
        state, LessonState.DIAGNOSE).pedagogical_state == LessonState.DIAGNOSE
    review = pedagogical_engine.apply_decision(
        state, PedagogicalDecisionAction.REVIEW, "Need more explanation")
    assert review.pedagogical_state == LessonState.REVIEW


def test_diagnosis_levels(pedagogical_engine: PedagogicalEngine) -> None:
    session = pedagogical_engine.tutor.start_session(
        "student-diagnosis", "cybersecurity/linux/permissions")
    result = pedagogical_engine.diagnose(
        session, "I have used JOINs in projects and I can write simple queries.")
    assert result.correct is True
    assert result.score >= 70
    assert result.recommendation


def test_knowledge_check_handles_misconception(pedagogical_engine: PedagogicalEngine) -> None:
    session = pedagogical_engine.tutor.start_session(
        "student-misconception", "data_science/sql/joins")
    result = pedagogical_engine.check_knowledge(
        session, "WHERE selects columns instead of filtering rows.")
    assert result.correct is False
    assert result.misconception
    assert "column" in result.misconception.lower(
    ) or "filter" in result.misconception.lower()


def test_decision_for_review_and_advance(pedagogical_engine: PedagogicalEngine) -> None:
    session = pedagogical_engine.tutor.start_session(
        "student-decision", "data_science/sql/joins")
    decision = pedagogical_engine.make_decision(
        session, correct=False, confidence=0.45, misconception="Confusion between WHERE and SELECT")
    assert decision.action == PedagogicalDecisionAction.REVIEW
    assert decision.next_state == LessonState.REVIEW

    advance = pedagogical_engine.make_decision(
        session, correct=True, confidence=0.9)
    assert advance.action == PedagogicalDecisionAction.ADVANCE
    assert advance.next_state == LessonState.PROFESSIONAL_APPLICATION


def test_context_limits_history_and_includes_pedagogy(pedagogical_engine: PedagogicalEngine) -> None:
    session = pedagogical_engine.tutor.start_session(
        "student-context", "data_science/sql/joins")
    session = pedagogical_engine.start_session(session)
    for index in range(10):
        session = pedagogical_engine.record_interaction(
            session, f"interaction {index}")
    context = pedagogical_engine.build_context(session, limit=4)
    assert context.current_state == LessonState.ORIENT
    assert len(context.previous_interactions) <= 4
    assert context.learning_objective
    assert context.current_difficulty == "beginner"


def test_tutor_integration_keeps_state(pedagogical_engine: PedagogicalEngine) -> None:
    session = pedagogical_engine.tutor.start_session(
        "student-integration", "data_science/sql/joins")
    session = pedagogical_engine.start_session(session)
    message = pedagogical_engine.generate_step_message(
        session, "Explain the purpose of WHERE")
    assert "WHERE" in message or "lesson" in message.lower()
    session = pedagogical_engine.advance_state(session, LessonState.DIAGNOSE)
    persisted = pedagogical_engine.repository.get_session(session.session_id)
    assert persisted is not None
    assert persisted.pedagogical_state == LessonState.DIAGNOSE


def test_session_resume_round_trip(pedagogical_engine: PedagogicalEngine) -> None:
    session = pedagogical_engine.tutor.start_session(
        "student-resume", "cybersecurity/linux/permissions")
    session = pedagogical_engine.start_session(session)
    session = pedagogical_engine.advance_state(session, LessonState.DIAGNOSE)
    resumed = pedagogical_engine.repository.get_session(session.session_id)
    assert resumed is not None and resumed.pedagogical_state == LessonState.DIAGNOSE


def test_invalid_transition_rejected(pedagogical_engine: PedagogicalEngine) -> None:
    state = pedagogical_engine.start_session(pedagogical_engine.tutor.start_session(
        "student-invalid", "data_science/sql/joins"))
    with pytest.raises(ValueError, match="invalid|transition"):
        pedagogical_engine.advance_state(state, LessonState.MASTERED)
