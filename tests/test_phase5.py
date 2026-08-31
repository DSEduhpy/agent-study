from pathlib import Path

from study_agent.config.settings import load_student_profile
from study_agent.core.models import DailyGoal, ExerciseAttempt, StudentProfile
from study_agent.database.sqlite import SQLiteDatabase
from study_agent.learning.adaptive_learning import AdaptiveLearningEngine
from study_agent.learning.daily_goal import DailyGoalEngine
from study_agent.memory.repository import LearningRepository


def test_daily_goal_uses_profile_and_persists_progress(tmp_path: Path) -> None:
    profile = load_student_profile(Path("config/profile.yaml"))
    repository = LearningRepository(SQLiteDatabase(tmp_path / "phase5.sqlite3"))
    repository.save_student("student-goal", profile)
    engine = DailyGoalEngine(repository, profile)

    goal = engine.start_day("student-goal", target=3, goal_date="2026-08-28")
    assert isinstance(goal, DailyGoal)
    assert goal.remaining == 3
    updated = engine.record_completion("student-goal", amount=2, goal_date="2026-08-28")
    assert updated.completed == 2
    assert updated.progress == 2 / 3
    assert repository.get_daily_goal("student-goal", "2026-08-28") == updated


def test_daily_goal_caps_completion_at_target(tmp_path: Path) -> None:
    repository = LearningRepository(SQLiteDatabase(tmp_path / "phase5.sqlite3"))
    repository.save_student("student-goal", StudentProfile("Test", 2, ("data_science",)))
    engine = DailyGoalEngine(repository)
    goal = engine.record_completion("student-goal", target=2, amount=5, goal_date="2026-08-28")
    assert goal.completed == 2
    assert goal.is_complete
    assert goal.remaining == 0


def test_adaptive_engine_prioritizes_weak_topic(tmp_path: Path) -> None:
    repository = LearningRepository(SQLiteDatabase(tmp_path / "phase5.sqlite3"))
    repository.save_student("student-adaptive", StudentProfile("Test", 2, ("data_science",)))
    engine = AdaptiveLearningEngine(repository)

    for exercise_id, topic in (("joins-1", "JOIN"), ("where-1", "WHERE")):
        from study_agent.core.models import Exercise
        repository.save_exercise(Exercise(
            exercise_id, "SQL", topic, difficulty="medium", question="Question",
            expected_answer="Answer"))
    repository.save_attempt("student-adaptive", ExerciseAttempt("joins-1", "Wrong", False, 30))
    repository.save_attempt("student-adaptive", ExerciseAttempt("where-1", "Answer", True, 95))

    recommendation = engine.recommend_next("student-adaptive")
    assert recommendation.topic == "JOIN"
    assert recommendation.difficulty.value == "easy"
    assert recommendation.reason