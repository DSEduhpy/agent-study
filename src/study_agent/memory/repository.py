"""Centralized persistence operations for learning records."""

import json
from datetime import datetime

from study_agent.core.models import Exercise, ExerciseAttempt, Lesson, LearningProgress, StudentProfile, StudySession
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
                "INSERT OR REPLACE INTO exercises VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (exercise.id, exercise.subject, exercise.topic, exercise.difficulty.value,
                 exercise.question, exercise.expected_answer, exercise.explanation,
                 exercise.professional_context, exercise.created_at.isoformat()),
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
                "INSERT INTO study_sessions (session_id, student_id, started_at, ended_at, lesson_ids, notes, status, interactions) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (session.session_id, session.student_id, session.started_at.isoformat(), session.ended_at.isoformat() if session.ended_at else None,
                 json.dumps(session.lesson_ids), session.notes, session.status.value, json.dumps(session.interactions)),
            )

    def update_session(self, session: StudySession) -> None:
        """Persist the latest state of an existing session."""
        with self.database.connection() as connection:
            connection.execute(
                "UPDATE study_sessions SET ended_at = ?, notes = ?, status = ?, interactions = ? WHERE session_id = ?",
                (session.ended_at.isoformat() if session.ended_at else None, session.notes,
                 session.status.value, json.dumps(session.interactions), session.session_id),
            )

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
                "SELECT * FROM exercise_attempts WHERE student_id = ? ORDER BY timestamp", (
                    student_id,)
            ).fetchall()
        return [dict(row) for row in rows]


def _now() -> str:
    return datetime.now().astimezone().isoformat()
