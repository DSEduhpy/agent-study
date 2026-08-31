"""Centralized persistence operations for learning records."""

import json
from datetime import date, datetime

from study_agent.core.models import (
    Exercise,
    ExerciseAttempt,
    DailyGoal,
    Difficulty,
    KnowledgeNode,
    KnowledgeRelation,
    ReviewHistory,
    ReviewOutcome,
    RetentionState,
    KnowledgeCheckResult,
    Lesson,
    LessonState,
    LearningProgress,
    StudentProfile,
    StudySession,
)
from study_agent.database.sqlite import SQLiteDatabase


class LearningRepository:
    """Persist domain entities without leaking SQL into learning services."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database
        self.database.initialize()

    def save_student(self, student_id: str, profile: StudentProfile) -> None:
        with self.database.connection() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO students (id, name, created_at) VALUES (?, ?, ?)",
                (student_id, profile.name, _now()),
            )

    def get_student(self, student_id: str) -> dict[str, object] | None:
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
        return dict(row) if row else None

    def save_lesson(self, lesson: Lesson) -> None:
        with self.database.connection() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO lessons VALUES (?, ?, ?, ?, ?, ?)",
                (lesson.id, lesson.title, lesson.area,
                 lesson.topic, lesson.content, lesson.source_path),
            )

    def save_exercise(self, exercise: Exercise) -> None:
        with self.database.connection() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO exercises (id, subject, topic, difficulty, question, expected_answer, explanation, professional_context, created_at, area, subtopic, exercise_type, options, learning_objective) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    exercise.id,
                    exercise.subject,
                    exercise.topic,
                    exercise.difficulty.value,
                    exercise.question,
                    exercise.expected_answer,
                    exercise.explanation,
                    exercise.professional_context,
                    exercise.created_at.isoformat(),
                    exercise.area,
                    exercise.subtopic,
                    exercise.exercise_type.value,
                    json.dumps(list(exercise.options)),
                    exercise.learning_objective,
                ),
            )

    def save_attempt(self, student_id: str, attempt: ExerciseAttempt) -> None:
        with self.database.connection() as connection:
            connection.execute(
                "INSERT INTO exercise_attempts (exercise_id, student_id, answer, correct, score, feedback, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (attempt.exercise_id, student_id, attempt.answer, int(attempt.correct),
                 attempt.score, attempt.feedback, attempt.timestamp.isoformat()),
            )

    def save_session(self, session: StudySession) -> None:
        with self.database.connection() as connection:
            connection.execute(
                "INSERT INTO study_sessions (session_id, student_id, started_at, ended_at, lesson_ids, notes, status, interactions, pedagogical_state, learning_objective, diagnostic_result, knowledge_checks, misconceptions, current_difficulty) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    session.session_id,
                    session.student_id,
                    session.started_at.isoformat(),
                    session.ended_at.isoformat() if session.ended_at else None,
                    json.dumps(session.lesson_ids),
                    session.notes,
                    session.status.value,
                    json.dumps(session.interactions),
                    session.pedagogical_state.value,
                    session.learning_objective,
                    json.dumps(_to_json(session.diagnostic_result)),
                    json.dumps([_to_json(item)
                               for item in session.knowledge_checks]),
                    json.dumps(list(session.misconceptions)),
                    session.current_difficulty,
                ),
            )

    def update_session(self, session: StudySession) -> None:
        """Persist the latest state of an existing session."""
        with self.database.connection() as connection:
            connection.execute(
                "UPDATE study_sessions SET ended_at = ?, notes = ?, status = ?, interactions = ?, pedagogical_state = ?, learning_objective = ?, diagnostic_result = ?, knowledge_checks = ?, misconceptions = ?, current_difficulty = ? WHERE session_id = ?",
                (
                    session.ended_at.isoformat() if session.ended_at else None,
                    session.notes,
                    session.status.value,
                    json.dumps(session.interactions),
                    session.pedagogical_state.value,
                    session.learning_objective,
                    json.dumps(_to_json(session.diagnostic_result)),
                    json.dumps([_to_json(item)
                               for item in session.knowledge_checks]),
                    json.dumps(list(session.misconceptions)),
                    session.current_difficulty,
                    session.session_id,
                ),
            )

    def get_session(self, session_id: str) -> StudySession | None:
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT * FROM study_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        return _session_from_row(dict(row))

    def get_latest_session(self, student_id: str) -> StudySession | None:
        """Return the most recently started persisted session for a student."""
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT * FROM study_sessions WHERE student_id = ? ORDER BY started_at DESC, id DESC LIMIT 1",
                (student_id,),
            ).fetchone()
        return _session_from_row(dict(row)) if row else None

    def save_progress(self, progress: LearningProgress) -> None:
        with self.database.connection() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO learning_progress VALUES (?, ?, ?, ?, ?, ?)",
                (progress.student_id, progress.topic, progress.lessons_completed, progress.exercises_attempted,
                 progress.average_score, progress.updated_at.isoformat()),
            )

    def list_attempts(self, student_id: str) -> list[dict[str, object]]:
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT exercise_attempts.*, exercises.topic, exercises.exercise_type, exercises.difficulty "
                "FROM exercise_attempts LEFT JOIN exercises ON exercises.id = exercise_attempts.exercise_id "
                "WHERE exercise_attempts.student_id = ? ORDER BY exercise_attempts.timestamp", (
                    student_id,)
            ).fetchall()
        return [dict(row) for row in rows]

    def save_daily_goal(self, goal: DailyGoal) -> None:
        with self.database.connection() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO daily_goals (student_id, goal_date, target, completed) VALUES (?, ?, ?, ?)",
                (goal.student_id, goal.goal_date, goal.target, goal.completed),
            )

    def get_daily_goal(self, student_id: str, goal_date: str | None = None) -> DailyGoal | None:
        goal_date = goal_date or date.today().isoformat()
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT student_id, goal_date, target, completed FROM daily_goals WHERE student_id = ? AND goal_date = ?",
                (student_id, goal_date),
            ).fetchone()
        if row is None:
            return None
        return DailyGoal(
            student_id=str(row["student_id"]),
            goal_date=str(row["goal_date"]),
            target=int(row["target"]),
            completed=int(row["completed"]),
        )

    def save_knowledge_node(self, node: KnowledgeNode) -> None:
        with self.database.connection() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO knowledge_nodes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (node.id, node.name, node.description, node.area, node.subject,
                 node.module, node.topic, node.type, node.difficulty.value,
                 json.dumps(list(node.learning_objectives)), json.dumps(list(node.prerequisites)),
                 json.dumps(list(node.skills)), json.dumps(list(node.aliases)), json.dumps(list(node.tags))),
            )

    def get_knowledge_node(self, node_id: str) -> KnowledgeNode | None:
        with self.database.connection() as connection:
            row = connection.execute("SELECT * FROM knowledge_nodes WHERE id = ?", (node_id,)).fetchone()
        return _knowledge_node_from_row(row) if row else None

    def list_knowledge_nodes(self) -> list[KnowledgeNode]:
        with self.database.connection() as connection:
            rows = connection.execute("SELECT * FROM knowledge_nodes ORDER BY name").fetchall()
        return [_knowledge_node_from_row(row) for row in rows]

    def save_knowledge_relation(self, relation: KnowledgeRelation) -> None:
        with self.database.connection() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO knowledge_relations (source_id, target_id, relation_type) VALUES (?, ?, ?)",
                (relation.source_id, relation.target_id, relation.relation_type),
            )

    def list_knowledge_relations(self, *, relation_type: str | None = None) -> list[KnowledgeRelation]:
        query = "SELECT source_id, target_id, relation_type FROM knowledge_relations"
        parameters: tuple[str, ...] = ()
        if relation_type:
            query += " WHERE relation_type = ?"
            parameters = (relation_type,)
        query += " ORDER BY source_id, target_id"
        with self.database.connection() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [KnowledgeRelation(str(row["source_id"]), str(row["target_id"]), str(row["relation_type"])) for row in rows]

    def save_retention_state(self, state: RetentionState) -> None:
        with self.database.connection() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO retention_states (student_id, knowledge_node_id, stability, difficulty, retrievability, review_count, successful_reviews, failed_reviews, last_review_at, next_review_at, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (state.student_id, state.knowledge_node_id, state.stability, state.difficulty,
                 state.retrievability, state.review_count, state.successful_reviews,
                 state.failed_reviews, _iso(state.last_review_at), _iso(state.next_review_at),
                 state.created_at.isoformat(), state.updated_at.isoformat()),
            )

    def get_retention_state(self, student_id: str, knowledge_node_id: str) -> RetentionState | None:
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT * FROM retention_states WHERE student_id = ? AND knowledge_node_id = ?",
                (student_id, knowledge_node_id),
            ).fetchone()
        return _retention_state_from_row(row) if row else None

    def list_retention_states(self, student_id: str) -> list[RetentionState]:
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM retention_states WHERE student_id = ? ORDER BY next_review_at",
                (student_id,),
            ).fetchall()
        return [_retention_state_from_row(row) for row in rows]

    def save_review_history(self, history: ReviewHistory) -> None:
        with self.database.connection() as connection:
            connection.execute(
                "INSERT INTO review_history (student_id, knowledge_node_id, reviewed_at, outcome, score, previous_interval_days, new_interval_days, previous_retention, new_retention) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (history.student_id, history.knowledge_node_id, history.reviewed_at.isoformat(),
                 history.outcome.value, history.score, history.previous_interval_days,
                 history.new_interval_days, history.previous_retention, history.new_retention),
            )

    def list_review_history(self, student_id: str, knowledge_node_id: str | None = None) -> list[ReviewHistory]:
        query = "SELECT * FROM review_history WHERE student_id = ?"
        parameters: tuple[str, ...] = (student_id,)
        if knowledge_node_id:
            query += " AND knowledge_node_id = ?"
            parameters += (knowledge_node_id,)
        query += " ORDER BY reviewed_at, id"
        with self.database.connection() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [_review_history_from_row(row) for row in rows]


def _to_json(value: object) -> dict[str, object] | None:
    if value is None:
        return None
    if isinstance(value, KnowledgeCheckResult):
        return {
            "score": value.score,
            "confidence": value.confidence,
            "correct": value.correct,
            "reasoning_quality": value.reasoning_quality,
            "misconception": value.misconception,
            "recommendation": value.recommendation,
        }
    return value


def _knowledge_node_from_row(row: object) -> KnowledgeNode:
    def values(name: str) -> tuple[str, ...]:
        raw = row[name] or "[]"
        return tuple(str(item) for item in json.loads(raw))

    return KnowledgeNode(
        id=str(row["id"]), name=str(row["name"]), description=str(row["description"] or ""),
        area=str(row["area"] or ""), subject=str(row["subject"] or ""), module=str(row["module"] or ""),
        topic=str(row["topic"] or ""), type=str(row["node_type"] or "concept"),
        difficulty=Difficulty(str(row["difficulty"] or Difficulty.BEGINNER.value)),
        learning_objectives=values("learning_objectives"), prerequisites=values("prerequisites"),
        skills=values("skills"), aliases=values("aliases"), tags=values("tags"),
    )


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _retention_state_from_row(row: object) -> RetentionState:
    return RetentionState(
        student_id=str(row["student_id"]), knowledge_node_id=str(row["knowledge_node_id"]),
        stability=float(row["stability"]), difficulty=float(row["difficulty"]),
        retrievability=float(row["retrievability"]), review_count=int(row["review_count"]),
        successful_reviews=int(row["successful_reviews"]), failed_reviews=int(row["failed_reviews"]),
        last_review_at=datetime.fromisoformat(row["last_review_at"]) if row["last_review_at"] else None,
        next_review_at=datetime.fromisoformat(row["next_review_at"]) if row["next_review_at"] else None,
        created_at=datetime.fromisoformat(row["created_at"]), updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def _review_history_from_row(row: object) -> ReviewHistory:
    return ReviewHistory(
        student_id=str(row["student_id"]), knowledge_node_id=str(row["knowledge_node_id"]),
        reviewed_at=datetime.fromisoformat(row["reviewed_at"]), outcome=ReviewOutcome(str(row["outcome"])),
        score=float(row["score"]), previous_interval_days=float(row["previous_interval_days"]),
        new_interval_days=float(row["new_interval_days"]), previous_retention=float(row["previous_retention"]),
        new_retention=float(row["new_retention"]),
    )


def _session_from_row(row: dict[str, object]) -> StudySession:
    definition = row.get("diagnostic_result")
    diagnostic_result = None
    if definition not in (None, "", "null"):
        parsed = json.loads(definition)
        diagnostic_result = KnowledgeCheckResult(**parsed) if parsed else None

    checks = row.get("knowledge_checks") or "[]"
    knowledge_checks = ()
    if checks not in (None, "", "[]", "null"):
        knowledge_checks = tuple(
            KnowledgeCheckResult(**item) for item in json.loads(checks)
        )

    misconceptions_raw = row.get("misconceptions") or "[]"
    misconceptions = tuple(json.loads(misconceptions_raw)) if misconceptions_raw not in (
        None, "", "[]", "null") else ()
    return StudySession(
        student_id=str(row["student_id"]),
        started_at=datetime.fromisoformat(str(row["started_at"])),
        ended_at=datetime.fromisoformat(
            str(row["ended_at"])) if row.get("ended_at") else None,
        lesson_ids=tuple(json.loads(row.get("lesson_ids") or "[]")),
        notes=str(row.get("notes") or ""),
        session_id=str(row["session_id"]),
        status=row["status"],
        interactions=tuple(json.loads(row.get("interactions") or "[]")),
        pedagogical_state=LessonState(
            str(row.get("pedagogical_state") or LessonState.ORIENT.value)),
        learning_objective=str(row.get("learning_objective") or ""),
        diagnostic_result=diagnostic_result,
        knowledge_checks=knowledge_checks,
        misconceptions=misconceptions,
        current_difficulty=str(row.get("current_difficulty") or "beginner"),
    )


def _now() -> str:
    return datetime.now().astimezone().isoformat()
