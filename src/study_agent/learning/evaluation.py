"""Deterministic evaluation boundary ready for an AI-backed evaluator."""

from study_agent.core.models import Evaluation


def evaluate_answer(correct: bool, feedback: str, score: float, next_focus: str = "") -> Evaluation:
    """Create validated evaluation data; scoring policy can evolve independently."""
    return Evaluation(score=score, correct=correct, feedback=feedback, next_focus=next_focus)
