"""Daily study target management backed by the learning repository."""

from __future__ import annotations

from datetime import date
from collections.abc import Iterable

from study_agent.core.models import DailyGoal, StudentProfile
from study_agent.memory.repository import LearningRepository


class DailyGoalEngine:
    """Create and update one exercise target per student and calendar day."""

    def __init__(self, repository: LearningRepository, profile: StudentProfile | None = None) -> None:
        self.repository = repository
        self.profile = profile

    def get_goal(self, student_id: str, *, goal_date: str | date | None = None) -> DailyGoal | None:
        return self.repository.get_daily_goal(student_id, _date_value(goal_date))

    def start_day(
        self,
        student_id: str,
        *,
        target: int | None = None,
        goal_date: str | date | None = None,
    ) -> DailyGoal:
        """Return today's existing goal or create it from the profile default."""
        day = _date_value(goal_date)
        existing = self.repository.get_daily_goal(student_id, day)
        if existing is not None:
            return existing
        selected_target = target if target is not None else self.profile.daily_goal if self.profile else None
        if selected_target is None:
            raise ValueError("target is required when no student profile is configured")
        goal = DailyGoal(student_id=student_id, target=selected_target, goal_date=day)
        self.repository.save_daily_goal(goal)
        return goal

    def record_completion(
        self,
        student_id: str,
        *,
        amount: int = 1,
        target: int | None = None,
        goal_date: str | date | None = None,
    ) -> DailyGoal:
        """Count completed exercises, capped at the target."""
        if amount < 1:
            raise ValueError("completion amount must be at least 1")
        goal = self.start_day(student_id, target=target, goal_date=goal_date)
        updated = DailyGoal(
            student_id=goal.student_id,
            target=goal.target,
            goal_date=goal.goal_date,
            completed=min(goal.completed + amount, goal.target),
        )
        self.repository.save_daily_goal(updated)
        return updated

    def status(self, student_id: str, *, goal_date: str | date | None = None) -> DailyGoal:
        goal = self.get_goal(student_id, goal_date=goal_date)
        if goal is None:
            return self.start_day(student_id, goal_date=goal_date)
        return goal

    @staticmethod
    def prioritize_for_goal(goal: DailyGoal, recommendations: Iterable[object]) -> tuple[object, ...]:
        """Fit externally produced study recommendations into remaining capacity."""
        return tuple(recommendations)[:goal.remaining]


def _date_value(value: str | date | None) -> str:
    if value is None:
        return date.today().isoformat()
    return value.isoformat() if isinstance(value, date) else value