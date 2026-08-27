from pathlib import Path

from study_agent.core.models import ExerciseAttempt, StudentProfile
from study_agent.database.sqlite import SQLiteDatabase
from study_agent.learning.exercises import create_exercise
from study_agent.memory.repository import LearningRepository


def test_database_schema_is_idempotent_and_persists(tmp_path: Path) -> None:
    database = SQLiteDatabase(tmp_path / "study.sqlite3")
    repository = LearningRepository(database)
    database.initialize()
    repository.save_student("student-1", StudentProfile("Test", 1, ("cybersecurity",)))
    repository.save_exercise(create_exercise("exercise-1", "cybersecurity", "linux", "Question", "Answer"))
    repository.save_attempt("student-1", ExerciseAttempt("exercise-1", "Answer", True, 100, "Good"))
    assert repository.get_student("student-1")["name"] == "Test"
    assert len(repository.list_attempts("student-1")) == 1
