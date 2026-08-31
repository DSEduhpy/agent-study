"""Explainable adaptive study recommendations from exercise evidence."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from study_agent.core.models import AdaptiveRecommendation, Difficulty, ExerciseType
from study_agent.memory.repository import LearningRepository


class AdaptiveLearningEngine:
    """Choose the next topic and difficulty without making external AI calls."""

    def __init__(self, repository: LearningRepository, curriculum: Any | None = None, retention: Any | None = None) -> None:
        self.repository = repository
        self.curriculum = curriculum
        self.retention = retention

    def recommend(
        self,
        student_id: str,
        *,
        topic: str | None = None,
        exercise_type: ExerciseType | str = ExerciseType.SHORT_ANSWER,
    ) -> AdaptiveRecommendation:
        attempts = self.repository.list_attempts(student_id)
        due_recommendation = self._due_recommendation(student_id, exercise_type)
        if due_recommendation is not None and topic is None:
            return due_recommendation
        selected_topic = topic.strip() if topic else self._weakest_topic(attempts)
        if not selected_topic:
            raise ValueError("topic is required when the student has no exercise history")

        prerequisite = self._weak_prerequisite(selected_topic, attempts)
        if prerequisite is not None:
            selected_topic, reason = prerequisite
        else:
            reason = ""

        topic_attempts = [row for row in attempts if str(row.get("topic") or "") == selected_topic]
        average = sum(float(row["score"]) for row in topic_attempts) / len(topic_attempts) if topic_attempts else 0.0
        last_attempt = topic_attempts[-1] if topic_attempts else None
        if not topic_attempts:
            difficulty = Difficulty.BEGINNER
            reason = reason or "Start with a foundational exercise because there is no evidence for this topic yet."
            confidence = 0.45
        elif average < 60 or not bool(last_attempt["correct"]):
            difficulty = Difficulty.EASY
            reason = reason or "Recent evidence shows the topic needs reinforcement before increasing complexity."
            confidence = 0.85
        elif average < 80:
            difficulty = Difficulty.MEDIUM
            reason = reason or "Performance is developing; use a moderate challenge to consolidate the concept."
            confidence = 0.75
        else:
            difficulty = Difficulty.HARD
            reason = reason or "Consistent strong performance supports a more demanding application."
            confidence = 0.82

        selected_type = ExerciseType(exercise_type if isinstance(exercise_type, str) else exercise_type.value)
        return AdaptiveRecommendation(selected_topic, difficulty, selected_type, reason, confidence)

    def _due_recommendation(self, student_id: str, exercise_type: ExerciseType | str) -> AdaptiveRecommendation | None:
        if self.retention is None or self.curriculum is None:
            return None
        due = self.retention.due(student_id)
        if not due:
            return None
        item = due[0]
        node = self.curriculum.get_node(item.state.knowledge_node_id)
        selected_type = ExerciseType(exercise_type if isinstance(exercise_type, str) else exercise_type.value)
        status = item.status.value
        return AdaptiveRecommendation(
            node.name,
            Difficulty.EASY,
            selected_type,
            f"Prioritize this {status} review before introducing new material.",
            0.9,
        )

    def recommend_next(self, student_id: str, **kwargs: Any) -> AdaptiveRecommendation:
        """Compatibility alias for callers that describe the next study action."""
        return self.recommend(student_id, **kwargs)

    def _weak_prerequisite(self, topic: str, attempts: list[dict[str, object]]) -> tuple[str, str] | None:
        if self.curriculum is None:
            return None
        try:
            prerequisites = self.curriculum.prerequisites(topic, recursive=True)
        except (KeyError, ValueError):
            return None
        for node in prerequisites:
            evidence = [row for row in attempts if str(row.get("topic") or "").casefold() == node.name.casefold()]
            if evidence and sum(float(row["score"]) for row in evidence) / len(evidence) < 60:
                return node.name, f"Review prerequisite '{node.name}' before continuing with '{topic}'."
        return None

    @staticmethod
    def _weakest_topic(attempts: list[dict[str, object]]) -> str:
        grouped: dict[str, list[float]] = defaultdict(list)
        for row in attempts:
            topic = str(row.get("topic") or "").strip()
            if topic:
                grouped[topic].append(float(row["score"]))
        if not grouped:
            return ""
        return min(grouped, key=lambda item: (sum(grouped[item]) / len(grouped[item]), item))