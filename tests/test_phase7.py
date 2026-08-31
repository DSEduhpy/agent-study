from datetime import datetime, timedelta, timezone
from pathlib import Path

from study_agent.ai.provider import AIProvider
from study_agent.core.models import Exercise, KnowledgeNode, ReviewOutcome, ReviewStatus, StudentProfile
from study_agent.curriculum.engine import CurriculumEngine
from study_agent.database.sqlite import SQLiteDatabase
from study_agent.learning.adaptive_learning import AdaptiveLearningEngine
from study_agent.learning.daily_goal import DailyGoalEngine
from study_agent.learning.exercise_engine import ExerciseEngine, ExerciseEvaluator, ExerciseGenerator, ExerciseSelector
from study_agent.learning.retention import RetentionEngine, ReviewScheduler, SimpleRetentionAlgorithm, load_retention_config
from study_agent.memory.repository import LearningRepository


class FakeClock:
    def __init__(self, current: datetime) -> None:
        self.current = current

    def now(self) -> datetime:
        return self.current


class OfflineProvider(AIProvider):
    def generate(self, prompt: str, *, system: str | None = None) -> str:
        return '{"correct": true, "score": 90, "feedback": "Correct", "confidence": 0.9}'

    def generate_structured(self, prompt: str, schema: type, *, system: str | None = None):
        raise NotImplementedError


def setup_repository(tmp_path: Path) -> LearningRepository:
    repository = LearningRepository(SQLiteDatabase(tmp_path / "retention.sqlite3"))
    repository.save_student("student", StudentProfile("Test", 2, ("data_science",)))
    repository.save_knowledge_node(KnowledgeNode("sql-join", "JOIN", topic="JOIN"))
    return repository


def test_retention_schedules_and_preserves_history(tmp_path: Path) -> None:
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=timezone.utc))
    repository = setup_repository(tmp_path)
    engine = RetentionEngine(repository, clock=clock, config=load_retention_config())

    initial = engine.start_learning("student", "sql-join")
    assert initial.next_review_at == clock.now() + timedelta(days=1)
    clock.current += timedelta(days=1)
    assert engine.due("student")[0].status == ReviewStatus.DUE
    reviewed = engine.review("student", "sql-join", ReviewOutcome.SUCCESS, 90)
    assert reviewed.next_review_at == clock.now() + timedelta(days=2)
    assert len(repository.list_review_history("student", "sql-join")) == 1

    clock.current = reviewed.next_review_at + timedelta(days=1)
    assert engine.due("student")[0].status == ReviewStatus.OVERDUE
    failed = engine.review("student", "sql-join", "failure", 20)
    assert failed.next_review_at == clock.now() + timedelta(days=1)
    assert len(repository.list_review_history("student", "sql-join")) == 2


def test_scheduler_distinguishes_upcoming_and_mastered(tmp_path: Path) -> None:
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=timezone.utc))
    repository = setup_repository(tmp_path)
    engine = RetentionEngine(repository, clock=clock)
    state = engine.start_learning("student", "sql-join")
    assert ReviewScheduler(clock).classify(state).status == ReviewStatus.UPCOMING
    for _ in range(3):
        clock.current = state.next_review_at
        state = engine.review("student", "sql-join", "success", 95)
    assert ReviewScheduler(clock).classify(state).status == ReviewStatus.MASTERED


def test_adaptive_prioritizes_due_retention(tmp_path: Path) -> None:
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=timezone.utc))
    repository = setup_repository(tmp_path)
    curriculum = CurriculumEngine("curriculum", repository)
    retention = RetentionEngine(repository, clock=clock)
    retention.start_learning("student", "sql-join")
    clock.current += timedelta(days=2)
    recommendation = AdaptiveLearningEngine(repository, curriculum, retention).recommend_next("student")
    assert recommendation.topic == "JOIN"
    assert "review" in recommendation.reason


def test_exercise_submission_updates_retention_and_daily_goal(tmp_path: Path) -> None:
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=timezone.utc))
    repository = setup_repository(tmp_path)
    exercise = Exercise("join-exercise", "SQL", "JOIN", difficulty="easy", question="What does JOIN do?", expected_answer="combine")
    repository.save_exercise(exercise)
    retention = RetentionEngine(repository, clock=clock)
    retention.start_learning("student", "sql-join")
    class Pedagogy:
        pass
    engine = ExerciseEngine(
        ExerciseGenerator(OfflineProvider()), ExerciseSelector(repository), ExerciseEvaluator(OfflineProvider()),
        repository, Pedagogy(), DailyGoalEngine(repository, StudentProfile("Test", 1, ("data_science",))), retention,
    )
    evaluation, _ = engine.submit_answer(exercise, "combine", student_id="student", knowledge_node_id="sql-join")
    assert evaluation.correct is True
    assert repository.get_retention_state("student", "sql-join").successful_reviews == 1
    assert repository.get_daily_goal("student").completed == 1