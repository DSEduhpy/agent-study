"""Idempotent SQLite schema and connection management."""

from contextlib import contextmanager
from pathlib import Path
import sqlite3
from collections.abc import Iterator

from study_agent.core.exceptions import DatabaseError


SCHEMA = """
CREATE TABLE IF NOT EXISTS students (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS lessons (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    area TEXT NOT NULL,
    topic TEXT NOT NULL,
    content TEXT NOT NULL,
    source_path TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS exercises (
    id TEXT PRIMARY KEY,
    subject TEXT NOT NULL,
    topic TEXT NOT NULL,
    difficulty TEXT NOT NULL,
    question TEXT NOT NULL,
    expected_answer TEXT NOT NULL,
    explanation TEXT NOT NULL,
    professional_context TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS exercise_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exercise_id TEXT NOT NULL REFERENCES exercises(id),
    student_id TEXT NOT NULL REFERENCES students(id),
    answer TEXT NOT NULL,
    correct INTEGER NOT NULL CHECK (correct IN (0, 1)),
    score REAL NOT NULL CHECK (score BETWEEN 0 AND 100),
    feedback TEXT NOT NULL,
    timestamp TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS study_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT UNIQUE,
    student_id TEXT NOT NULL REFERENCES students(id),
    started_at TEXT NOT NULL,
    ended_at TEXT,
    lesson_ids TEXT NOT NULL,
    notes TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    interactions TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS learning_progress (
    student_id TEXT NOT NULL REFERENCES students(id),
    topic TEXT NOT NULL,
    lessons_completed INTEGER NOT NULL DEFAULT 0,
    exercises_attempted INTEGER NOT NULL DEFAULT 0,
    average_score REAL NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (student_id, topic)
);
CREATE TABLE IF NOT EXISTS mistakes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id TEXT NOT NULL REFERENCES students(id),
    topic TEXT NOT NULL,
    description TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_attempts_student ON exercise_attempts(student_id);
CREATE INDEX IF NOT EXISTS idx_progress_student ON learning_progress(student_id);
"""


class SQLiteDatabase:
    """Own the SQLite file and expose short-lived connections."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def initialize(self) -> None:
        """Create the database directory and missing tables without data loss."""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.connection() as connection:
                connection.executescript(SCHEMA)
                self._migrate_sessions(connection)
        except sqlite3.Error as exc:
            raise DatabaseError("Could not initialize database") from exc

    @staticmethod
    def _migrate_sessions(connection: sqlite3.Connection) -> None:
        """Add session lifecycle columns to databases created by version 0.1."""
        columns = {row[1] for row in connection.execute("PRAGMA table_info(study_sessions)")}
        migrations = {
            "session_id": "ALTER TABLE study_sessions ADD COLUMN session_id TEXT",
            "status": "ALTER TABLE study_sessions ADD COLUMN status TEXT NOT NULL DEFAULT 'active'",
            "interactions": "ALTER TABLE study_sessions ADD COLUMN interactions TEXT NOT NULL DEFAULT '[]'",
        }
        for column, statement in migrations.items():
            if column not in columns:
                connection.execute(statement)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """Yield a configured connection and translate SQLite errors."""
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(self.path)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            yield connection
            connection.commit()
        except sqlite3.Error as exc:
            if connection is not None:
                connection.rollback()
            raise DatabaseError("Database operation failed") from exc
        finally:
            if connection is not None:
                connection.close()
