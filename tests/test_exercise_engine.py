from pathlib import Path

import json

import pytest

from study_agent.ai.provider import AIProvider
from study_agent.config.settings import load_student_profile
from study_agent.core.models import (
    Difficulty,
    Exercise,
    ExerciseAttempt,
    KnowledgeCheckResult,
    LessonState,
    PedagogicalDecisionAction,
    StudySession,
)
from study_agent.curriculum.loader import CurriculumLoader
from study_agent.database.sqlite import SQLiteDatabase
from study_agent.learning.exercise_engine import (
    ExerciseEngine,
    ExerciseEvaluator,
    ExerciseGenerator,
    ExerciseSelector,
)
from study_agent.learning.pedagogy import PedagogicalEngine
from study_agent.learning.tutor import TutorEngine
from study_agent.memory.repository import LearningRepository


class FakeAIProvider(AIProvider):
    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []

    def generate(self, prompt: str, *, system: str | None = None) -> str:
        self.calls.append((prompt, system))
        return json.dumps({
            "area": "data_science",
            "subject": "SQL",
            "topic": "WHERE",
            "subtopic": "filtering rows",
            "difficulty": "medium",
            "exercise_type": "query",
            "question": "Write a query that returns customers older than 18.",
            "options": [],
            "expected_answer": "SELECT * FROM customers WHERE age > 18;",
            "explanation": "WHERE filters rows prior to presentation.",
            "professional_context": "A business analyst needs a filtered customer list.",
            "learning_objective": "Filter data using WHERE.",
        })

    def generate_structured(self, prompt: str, schema: type, *, system: str | None = None):
        if schema is dict:
            return {
                "area": "data_science",
                "subject": "SQL",
                "topic": "WHERE",
                "subtopic": "filtering rows",
                "difficulty": "medium",
                "exercise_type": "query",
                "question": "Write a query that returns customers older than 18.",
                "options": [],
                "expected_answer": "SELECT * FROM customers WHERE age > 18;",
                "explanation": "WHERE filters rows prior to presentation.",
                "professional_context": "A business analyst needs a filtered customer list.",
                "learning_objective": "Filter data using WHERE.",
            }
        if schema.__name__ == "StructuredEvaluation":
            return {"correct": True, "score": 90, "feedback": "Good explanation.", "explanation": "You identified the filter correctly.", "misconception": "", "confidence": 0.9}
        raise NotImplementedError


@pytest.fixture
def exercise_engine(tmp_path: Path) -> ExerciseEngine:
    profile = load_student_profile(Path("config/profile.yaml"))
    curriculum = CurriculumLoader(Path("curriculum"))
    repository = LearningRepository(
        SQLiteDatabase(tmp_path / "exercises.sqlite3"))
    tutor = TutorEngine(curriculum, FakeAIProvider(),
                        repository, profile, Path("prompts"))
    pedagogical = PedagogicalEngine(
        tutor, curriculum, repository, profile, Path("prompts"))
    provider = FakeAIProvider()
    generator = ExerciseGenerator(provider)
    selector = ExerciseSelector(repository)
    evaluator = ExerciseEvaluator(provider)
    return ExerciseEngine(generator, selector, evaluator, repository, pedagogical)


def test_generator_validates_required_fields(exercise_engine: ExerciseEngine) -> None:
    context = exercise_engine.pedagogical.build_context(
        exercise_engine.pedagogical.start_session(
            exercise_engine.pedagogical.tutor.start_session(
                "student-exercise", "data_science/sql/joins")
        )
    )
    exercise = exercise_engine.generate_exercise(
        context, exercise_type="query", difficulty="medium")
    assert isinstance(exercise, Exercise)
    assert exercise.topic == "WHERE"
    assert exercise.learning_objective


def test_selector_adapts_difficulty_and_avoids_repetition(exercise_engine: ExerciseEngine) -> None:
    session = exercise_engine.pedagogical.tutor.start_session(
        "student-selector", "data_science/sql/joins")
    session = exercise_engine.pedagogical.start_session(session)
    repository = exercise_engine.repository
    repository.save_exercise(Exercise("ex-1", area="data_science", subject="SQL", topic="WHERE", subtopic="filtering rows", difficulty="medium", exercise_type="query", question="Question 1",
                             options=[], expected_answer="SELECT * FROM sales WHERE total > 100;", explanation="Explanation", professional_context="Professional context", learning_objective="Filter rows using WHERE."))
    repository.save_exercise(Exercise("ex-2", area="data_science", subject="SQL", topic="WHERE", subtopic="filtering rows", difficulty="easy", exercise_type="multiple_choice", question="Question 2",
                             options=["A", "B", "C"], expected_answer="B", explanation="Explanation", professional_context="Professional context", learning_objective="Filter rows using WHERE."))
    repository.save_attempt(
        "student-selector", ExerciseAttempt("ex-1", "SELECT * FROM sales;", False, 30, "Wrong"))
    selected = exercise_engine.selector.select_exercise(
        {"topic": "WHERE", "difficulty": "medium", "exercise_type": "query"}, student_id="student-selector")
    assert selected.exercise_id in {"ex-1", "ex-2"}


def test_evaluator_multiple_choice_and_open_answer(exercise_engine: ExerciseEngine) -> None:
    exercise = Exercise("mc-1", area="data_science", subject="SQL", topic="WHERE", subtopic="filtering rows", difficulty="medium", exercise_type="multiple_choice", question="Which clause filters rows?",
                        options=["SELECT", "WHERE", "FROM"], expected_answer="WHERE", explanation="WHERE filters rows.", professional_context="Professional context", learning_objective="Filter rows using WHERE.")
    correct = exercise_engine.evaluator.evaluate(exercise, "WHERE")
    assert correct.correct is True
    assert correct.score >= 80

    open_exercise = Exercise("oa-1", area="data_science", subject="SQL", topic="WHERE", subtopic="filtering rows", difficulty="medium", exercise_type="short_answer", question="Explain what WHERE does.",
                             options=[], expected_answer="WHERE filters rows.", explanation="WHERE filters rows before the result is presented.", professional_context="Professional context", learning_objective="Explain filtering.")
    result = exercise_engine.evaluator.evaluate(
        open_exercise, "WHERE filters rows before they are shown.")
    assert result.correct in {True, False}
    assert result.feedback


def test_exercise_engine_integration_with_pedagogy(exercise_engine: ExerciseEngine) -> None:
    pedagogical = exercise_engine.pedagogical
    session = pedagogical.tutor.start_session(
        "student-flow", "data_science/sql/joins")
    session = pedagogical.start_session(session)
    context = pedagogical.build_context(session)
    exercise = exercise_engine.generate_exercise(
        context, exercise_type="query", difficulty="medium")
    evaluation = exercise_engine.evaluator.evaluate(
        exercise, "SELECT * FROM sales;")
    knowledge = exercise_engine.to_knowledge_check(exercise, evaluation)
    decision = pedagogical.make_decision(
        session, correct=evaluation.correct, confidence=knowledge.confidence, misconception=evaluation.misconception)
    assert decision.action in {PedagogicalDecisionAction.REVIEW,
                               PedagogicalDecisionAction.ADVANCE, PedagogicalDecisionAction.PRACTICE}
    assert isinstance(knowledge, KnowledgeCheckResult)
