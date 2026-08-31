"""Practice runtime responsible for generating, selecting, and evaluating exercises."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from study_agent.ai.provider import AIProvider
from study_agent.core.exceptions import AIProviderError, StudyAgentError
from study_agent.core.models import (
    Difficulty,
    Evaluation,
    Exercise,
    ExerciseAttempt,
    ExerciseType,
    KnowledgeCheckResult,
    LessonState,
    PedagogicalDecisionAction,
)
from study_agent.learning.pedagogy import PedagogicalContext
from study_agent.learning.daily_goal import DailyGoalEngine
from study_agent.learning.retention import RetentionEngine
from study_agent.memory.repository import LearningRepository


class ExerciseGenerator:
    """Turn a pedagogical context into a structured practice opportunity."""

    def __init__(self, provider: AIProvider) -> None:
        self.provider = provider

    def generate(
        self,
        context: PedagogicalContext,
        *,
        exercise_type: str | ExerciseType = ExerciseType.QUERY,
        difficulty: str | Difficulty = Difficulty.MEDIUM,
        quantity: int = 1,
    ) -> Exercise:
        """Generate a single exercise aligned to the current pedagogical objective."""
        if quantity < 1:
            raise ValueError("quantity must be at least 1")
        if not context.learning_objective:
            raise StudyAgentError(
                "Learning objective is required for exercise generation")
        selected_type = ExerciseType(exercise_type if isinstance(
            exercise_type, str) else exercise_type.value)
        selected_difficulty = Difficulty(
            difficulty if isinstance(difficulty, str) else difficulty.value)
        prompt = (
            "Generate a single exercise in JSON with the following required fields: "
            "area, subject, topic, subtopic, difficulty, exercise_type, question, options, "
            "expected_answer, explanation, professional_context, learning_objective.\n"
            f"Context: area={context.lesson_area}, topic={context.lesson_topic}, objective={context.learning_objective}, "
            f"state={context.current_state.value}, difficulty={selected_difficulty.value}, type={selected_type.value}.\n"
            "Return only valid JSON without markdown fences."
        )
        try:
            payload = self.provider.generate_structured(prompt, dict)
        except (AttributeError, NotImplementedError, TypeError):
            raw = self.provider.generate(prompt)
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise StudyAgentError(
                    "Exercise generator returned invalid JSON") from exc

        required = {
            "area", "subject", "topic", "difficulty", "exercise_type", "question",
            "expected_answer", "explanation", "professional_context", "learning_objective",
        }
        missing = sorted(required - set(payload))
        if missing:
            raise StudyAgentError(
                f"Exercise payload missing required fields: {', '.join(missing)}")

        normalized = {
            "id": f"exercise-{context.lesson_topic.lower().replace(' ', '-')}-{uuid4().hex[:8]}",
            "area": str(payload["area"]).strip(),
            "subject": str(payload["subject"]).strip(),
            "topic": str(payload["topic"]).strip(),
            "subtopic": str(payload.get("subtopic", "")).strip(),
            "difficulty": Difficulty(str(payload["difficulty"]).lower()),
            "exercise_type": ExerciseType(str(payload["exercise_type"]).lower()),
            "question": str(payload["question"]).strip(),
            "expected_answer": str(payload["expected_answer"]).strip(),
            "explanation": str(payload["explanation"]).strip(),
            "professional_context": str(payload["professional_context"]).strip(),
            "learning_objective": str(payload["learning_objective"]).strip(),
            "options": tuple(str(item) for item in payload.get("options", [])),
        }
        if not normalized["question"] or not normalized["expected_answer"]:
            raise StudyAgentError(
                "Exercise question and expected answer cannot be empty")
        if normalized["difficulty"] not in {Difficulty.EASY, Difficulty.MEDIUM, Difficulty.HARD}:
            raise StudyAgentError(
                "Exercise difficulty must be one of easy, medium, or hard")
        if normalized["exercise_type"] not in set(ExerciseType):
            raise StudyAgentError("Exercise type is invalid")
        return Exercise(
            id=normalized["id"],
            area=normalized["area"],
            subject=normalized["subject"],
            topic=normalized["topic"],
            subtopic=normalized["subtopic"],
            difficulty=normalized["difficulty"],
            exercise_type=normalized["exercise_type"],
            question=normalized["question"],
            expected_answer=normalized["expected_answer"],
            explanation=normalized["explanation"],
            professional_context=normalized["professional_context"],
            learning_objective=normalized["learning_objective"],
            options=normalized["options"],
        )


class ExerciseSelector:
    """Choose the next practice item using basic, explainable heuristics."""

    def __init__(self, repository: LearningRepository) -> None:
        self.repository = repository

    def select_exercise(
        self,
        criteria: dict[str, Any],
        *,
        student_id: str,
    ) -> Exercise:
        """Return a single exercise that matches context without repeating too soon."""
        topic = str(criteria.get("topic") or "").strip()
        difficulty = str(criteria.get("difficulty")
                         or "medium").strip().lower()
        exercise_type = str(criteria.get("exercise_type")
                            or "query").strip().lower()
        attempts = self.repository.list_attempts(student_id)
        seen = {row["exercise_id"]
                for row in attempts if row.get("exercise_id")}
        candidates = []
        with self.repository.database.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM exercises WHERE topic = ? AND difficulty = ? AND exercise_type = ? ORDER BY created_at DESC",
                (topic, difficulty, exercise_type),
            ).fetchall()
        for row in rows:
            candidate = self._row_to_exercise(row)
            if candidate.id not in seen:
                candidates.append(candidate)
        if candidates:
            return candidates[0]
        with self.repository.database.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM exercises WHERE topic = ? ORDER BY created_at DESC LIMIT 5",
                (topic,),
            ).fetchall()
        for row in rows:
            candidate = self._row_to_exercise(row)
            if candidate.id not in seen:
                return candidate
        raise StudyAgentError(
            "No suitable exercise available for the requested topic")

    @staticmethod
    def _row_to_exercise(row: Any) -> Exercise:
        return Exercise(
            id=str(row["id"]),
            area=str(row["subject"]),
            subject=str(row["subject"]),
            topic=str(row["topic"]),
            subtopic=str(row["topic"]),
            difficulty=Difficulty(str(row["difficulty"]).lower()),
            exercise_type=ExerciseType(str(row["exercise_type"]).lower()),
            question=str(row["question"]),
            expected_answer=str(row["expected_answer"]),
            explanation=str(row["explanation"]),
            professional_context=str(row["professional_context"]),
            learning_objective=str(
                row["learning_objective"] if "learning_objective" in row.keys() else row["question"]),
            options=tuple(json.loads(row["options"])
                          if row["options"] else ()),
        )


class ExerciseEvaluator:
    """Evaluate a submitted answer against the exercise objective and expected result."""

    def __init__(self, provider: AIProvider) -> None:
        self.provider = provider

    def evaluate(self, exercise: Exercise, student_answer: str) -> Evaluation:
        """Return a structured evaluation using deterministic checks where possible."""
        normalized = (student_answer or "").strip()
        if not normalized:
            raise ValueError("student answer cannot be empty")

        if exercise.exercise_type in {ExerciseType.MULTIPLE_CHOICE, ExerciseType.TRUE_FALSE}:
            answer = normalized.lower()
            expected = exercise.expected_answer.lower()
            correct = answer == expected.lower()
            return Evaluation(
                score=100.0 if correct else 0.0,
                correct=correct,
                feedback="Correct answer." if correct else "Not quite; the expected answer was different.",
                next_focus="Review the concept and the specific option before trying again.",
                explanation=exercise.explanation,
                misconception="" if correct else "The student selected an option inconsistent with the concept being tested.",
                confidence=0.95 if correct else 0.4,
                status="correct" if correct else "incorrect",
            )

        if exercise.exercise_type == ExerciseType.QUERY:
            expected = exercise.expected_answer.lower()
            actual = normalized.lower()
            correct = expected in actual or actual == expected
            status = "correct" if correct else "partial" if len(
                actual) > 10 else "incorrect"
            return Evaluation(
                score=100.0 if correct else 50.0,
                correct=correct,
                feedback="Your query matches the expected logic." if correct else "Your query is close, but it is not filtering the data as intended.",
                next_focus="Check the filtering clause and compare it with the target condition.",
                explanation=exercise.explanation,
                misconception="" if correct else "A common issue is confusing SELECT and filter logic in the query.",
                confidence=0.85 if correct else 0.6,
                status=status,
            )

        raw = self.provider.generate(
            "Evaluate the student's answer to the exercise. Return JSON with keys: correct, score, feedback, explanation, misconception, confidence. "
            f"Exercise: {json.dumps({'question': exercise.question, 'expected_answer': exercise.expected_answer, 'explanation': exercise.explanation, 'learning_objective': exercise.learning_objective}, ensure_ascii=False)}\n"
            f"Student answer: {normalized}"
        )
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AIProviderError(
                "AI evaluation returned invalid JSON") from exc

        return Evaluation(
            score=float(payload.get("score", 0)),
            correct=bool(payload.get("correct", False)),
            feedback=str(payload.get("feedback", "Evaluation not available.")),
            next_focus="Review the concept and re-attempt with a more precise explanation.",
            explanation=str(payload.get("explanation", exercise.explanation)),
            misconception=str(payload.get("misconception", "")),
            confidence=float(payload.get("confidence", 0.5)),
            status="partial" if not bool(payload.get("correct", False)) and float(payload.get(
                "score", 0)) > 0 else ("correct" if bool(payload.get("correct", False)) else "incorrect"),
        )


@dataclass
class ExerciseSession:
    """An in-progress collection of exercises for a single practice session."""

    goal: str
    requested_quantity: int
    completed: int = 0
    remaining: int = 0
    exercises: list[Exercise] = field(default_factory=list)
    attempts: list[ExerciseAttempt] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.requested_quantity < 1:
            raise ValueError("requested quantity must be at least 1")
        self.remaining = max(self.requested_quantity - self.completed, 0)


class ExerciseEngine:
    """Practical runtime that sits between pedagogical decisions and actual answer evaluation."""

    def __init__(
        self,
        generator: ExerciseGenerator,
        selector: ExerciseSelector,
        evaluator: ExerciseEvaluator,
        repository: LearningRepository,
        pedagogical: Any,
        daily_goal: DailyGoalEngine | None = None,
        retention: RetentionEngine | None = None,
    ) -> None:
        self.generator = generator
        self.selector = selector
        self.evaluator = evaluator
        self.repository = repository
        self.pedagogical = pedagogical
        self.daily_goal = daily_goal
        self.retention = retention

    def generate_exercise(
        self,
        context: PedagogicalContext,
        *,
        exercise_type: str | ExerciseType = ExerciseType.QUERY,
        difficulty: str | Difficulty = Difficulty.MEDIUM,
        quantity: int = 1,
    ) -> Exercise:
        """Generate and persist a practice item aligned to the current teaching state."""
        exercise = self.generator.generate(
            context, exercise_type=exercise_type, difficulty=difficulty, quantity=quantity)
        self.repository.save_exercise(exercise)
        return exercise

    def select_and_generate(self, context: PedagogicalContext, *, student_id: str, exercise_type: str | ExerciseType = ExerciseType.QUERY, difficulty: str | Difficulty = Difficulty.MEDIUM) -> Exercise:
        """Select a suitable exercise from the repository or generate it if no match exists."""
        criteria = {
            "topic": context.lesson_topic,
            "difficulty": Difficulty(difficulty if isinstance(difficulty, str) else difficulty.value).value,
            "exercise_type": ExerciseType(exercise_type if isinstance(exercise_type, str) else exercise_type.value).value,
        }
        try:
            return self.selector.select_exercise(criteria, student_id=student_id)
        except StudyAgentError:
            return self.generate_exercise(context, exercise_type=exercise_type, difficulty=difficulty)

    def submit_answer(self, exercise: Exercise, student_answer: str, *, student_id: str, knowledge_node_id: str | None = None) -> tuple[Evaluation, ExerciseAttempt]:
        """Evaluate a student's submission and persist the attempt as a historical record."""
        evaluation = self.evaluator.evaluate(exercise, student_answer)
        attempt = ExerciseAttempt(
            exercise_id=exercise.id,
            answer=student_answer,
            correct=evaluation.correct,
            score=evaluation.score,
            feedback=evaluation.feedback,
        )
        self.repository.save_attempt(student_id, attempt)
        if self.daily_goal is not None:
            self.daily_goal.record_completion(student_id)
        if self.retention is not None and knowledge_node_id is not None:
            outcome = "success" if evaluation.correct and evaluation.score >= 80 else "partial" if evaluation.score > 0 else "failure"
            self.retention.review(student_id, knowledge_node_id, outcome, evaluation.score)
        return evaluation, attempt

    def to_knowledge_check(self, exercise: Exercise, evaluation: Evaluation) -> KnowledgeCheckResult:
        """Convert an exercise evaluation into a pedagogical knowledge check."""
        misconception = evaluation.misconception or ""
        return KnowledgeCheckResult(
            score=evaluation.score,
            confidence=evaluation.confidence,
            correct=evaluation.correct,
            reasoning_quality=max(0.0, min(1.0, evaluation.confidence)),
            misconception=misconception,
            recommendation=(
                "The answer is correct; reinforce with application." if evaluation.correct else "Revisit the concept with a simpler explanation and a new example."),
        )
