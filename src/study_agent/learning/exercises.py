"""Use-case helpers for creating exercises."""

from study_agent.core.models import Difficulty, Exercise


def create_exercise(exercise_id: str, subject: str, topic: str, question: str, expected_answer: str,
                    difficulty: Difficulty = Difficulty.BEGINNER, explanation: str = "",
                    professional_context: str = "") -> Exercise:
    """Build a validated exercise entity."""
    if not all(value.strip() for value in (exercise_id, subject, topic, question, expected_answer)):
        raise ValueError("exercise identity and answer fields cannot be empty")
    return Exercise(exercise_id, subject, topic, difficulty, question, expected_answer, explanation, professional_context)
