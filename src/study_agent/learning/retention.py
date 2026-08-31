"""Deterministic, replaceable spaced-review scheduling for knowledge nodes."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol

import yaml

from study_agent.core.models import (
    KnowledgeNode,
    ReviewHistory,
    ReviewItem,
    ReviewOutcome,
    ReviewStatus,
    RetentionConfig,
    RetentionState,
)
from study_agent.memory.repository import LearningRepository


class Clock(Protocol):
    """Clock boundary used to keep scheduling tests deterministic."""

    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class RetentionAlgorithm(Protocol):
    """Strategy contract for replacing the initial scheduling heuristic."""

    def update(self, state: RetentionState, outcome: ReviewOutcome, score: float, now: datetime) -> tuple[RetentionState, float]: ...


class SimpleRetentionAlgorithm:
    """A transparent heuristic, not a scientific model of human memory."""

    def __init__(self, config: RetentionConfig | None = None) -> None:
        self.config = config or RetentionConfig()

    def update(self, state: RetentionState, outcome: ReviewOutcome, score: float, now: datetime) -> tuple[RetentionState, float]:
        previous_interval = _interval_days(state, now, self.config.initial_interval_days)
        multiplier = {
            ReviewOutcome.SUCCESS: self.config.success_multiplier,
            ReviewOutcome.PARTIAL: self.config.partial_multiplier,
            ReviewOutcome.FAILURE: self.config.failure_multiplier,
        }[outcome]
        interval = min(max(previous_interval * multiplier, self.config.minimum_interval_days), self.config.maximum_interval_days)
        previous_retention = state.retention_score
        retention = {
            ReviewOutcome.SUCCESS: min(1.0, max(previous_retention, 0.45) + 0.2),
            ReviewOutcome.PARTIAL: min(1.0, max(previous_retention, 0.25) + 0.05),
            ReviewOutcome.FAILURE: max(0.0, previous_retention * 0.5),
        }[outcome]
        updated = replace(
            state,
            stability=interval,
            retrievability=retention,
            review_count=state.review_count + 1,
            successful_reviews=state.successful_reviews + (outcome == ReviewOutcome.SUCCESS),
            failed_reviews=state.failed_reviews + (outcome == ReviewOutcome.FAILURE),
            last_review_at=now,
            next_review_at=now + timedelta(days=interval),
            updated_at=now,
        )
        return updated, interval


class ReviewScheduler:
    """Classify persisted retention states relative to an injected clock."""

    def __init__(self, clock: Clock | None = None) -> None:
        self.clock = clock or SystemClock()

    def classify(self, state: RetentionState) -> ReviewItem:
        now = self.clock.now()
        if state.next_review_at is None:
            return ReviewItem(state, ReviewStatus.DUE)
        if state.next_review_at < now:
            return ReviewItem(state, ReviewStatus.OVERDUE, now - state.next_review_at)
        if state.next_review_at == now:
            return ReviewItem(state, ReviewStatus.DUE)
        if state.review_count >= 3 and state.successful_reviews == state.review_count and state.retrievability >= 0.85:
            return ReviewItem(state, ReviewStatus.MASTERED)
        return ReviewItem(state, ReviewStatus.UPCOMING, state.next_review_at - now)

    def due(self, states: list[RetentionState]) -> list[ReviewItem]:
        return [item for item in (self.classify(state) for state in states) if item.status in {ReviewStatus.DUE, ReviewStatus.OVERDUE}]

    def upcoming(self, states: list[RetentionState]) -> list[ReviewItem]:
        return [item for item in (self.classify(state) for state in states) if item.status == ReviewStatus.UPCOMING]


class RetentionEngine:
    """Own retention state transitions while keeping storage in LearningRepository."""

    def __init__(self, repository: LearningRepository, *, algorithm: RetentionAlgorithm | None = None, scheduler: ReviewScheduler | None = None, clock: Clock | None = None, config: RetentionConfig | None = None) -> None:
        self.repository = repository
        self.clock = clock or SystemClock()
        self.algorithm = algorithm or SimpleRetentionAlgorithm(config)
        self.scheduler = scheduler or ReviewScheduler(self.clock)

    def start_learning(self, student_id: str, knowledge_node_id: str) -> RetentionState:
        existing = self.repository.get_retention_state(student_id, knowledge_node_id)
        if existing is not None:
            return existing
        now = self.clock.now()
        config = self.algorithm.config if isinstance(self.algorithm, SimpleRetentionAlgorithm) else RetentionConfig()
        state = RetentionState(
            student_id=student_id,
            knowledge_node_id=knowledge_node_id,
            stability=config.initial_interval_days,
            retrievability=0.35,
            next_review_at=now + timedelta(days=config.initial_interval_days),
            created_at=now,
            updated_at=now,
        )
        self.repository.save_retention_state(state)
        return state

    def review(self, student_id: str, knowledge_node_id: str, outcome: ReviewOutcome | str, score: float) -> RetentionState:
        outcome = ReviewOutcome(outcome)
        if not 0 <= score <= 100:
            raise ValueError("review score must be between 0 and 100")
        state = self.repository.get_retention_state(student_id, knowledge_node_id) or self.start_learning(student_id, knowledge_node_id)
        now = self.clock.now()
        previous_interval = _interval_days(state, now, 0.0)
        previous_retention = state.retention_score
        updated, new_interval = self.algorithm.update(state, outcome, score, now)
        history = ReviewHistory(student_id, knowledge_node_id, now, outcome, score, previous_interval, new_interval, previous_retention, updated.retention_score)
        self.repository.save_retention_state(updated)
        self.repository.save_review_history(history)
        return updated

    def get(self, student_id: str, knowledge_node_id: str) -> RetentionState | None:
        return self.repository.get_retention_state(student_id, knowledge_node_id)

    def reviews(self, student_id: str) -> list[ReviewItem]:
        return sorted((self.scheduler.classify(state) for state in self.repository.list_retention_states(student_id)), key=lambda item: item.overdue_duration, reverse=True)

    def due(self, student_id: str) -> list[ReviewItem]:
        return [item for item in self.reviews(student_id) if item.status in {ReviewStatus.DUE, ReviewStatus.OVERDUE}]

    def retention_for_node(self, student_id: str, node: KnowledgeNode) -> RetentionState | None:
        return self.get(student_id, node.id)


def load_retention_config(path: Path | str = "config/retention.yaml") -> RetentionConfig:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return RetentionConfig(**(data.get("retention") or {}))


def _interval_days(state: RetentionState, now: datetime, default: float) -> float:
    if state.last_review_at and state.next_review_at:
        return max((state.next_review_at - state.last_review_at).total_seconds() / 86400, default)
    return max(state.stability, default)