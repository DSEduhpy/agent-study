import pytest

from study_agent.core.models import Difficulty, Exercise, ExerciseAttempt
from study_agent.learning.exercises import create_exercise


def test_exercise_and_attempt_are_typed() -> None:
    exercise = create_exercise("e1", "cybersecurity", "linux", "Question", "Answer", Difficulty.INTERMEDIATE)
    attempt = ExerciseAttempt(exercise.id, "Answer", True, 95, "Correct")
    assert isinstance(exercise, Exercise)
    assert attempt.correct is True


def test_attempt_score_is_validated() -> None:
    with pytest.raises(ValueError):
        ExerciseAttempt("e1", "Answer", False, 101)
