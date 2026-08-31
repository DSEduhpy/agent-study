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
    created_at TEXT NOT NULL,
    area TEXT DEFAULT '',
    subtopic TEXT DEFAULT '',
    exercise_type TEXT DEFAULT 'short_answer',
    options TEXT DEFAULT '[]',
    learning_objective TEXT DEFAULT ''
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
    interactions TEXT NOT NULL DEFAULT '[]',
    pedagogical_state TEXT NOT NULL DEFAULT 'orient',
    learning_objective TEXT NOT NULL DEFAULT '',
    diagnostic_result TEXT NOT NULL DEFAULT '{}',
    knowledge_checks TEXT NOT NULL DEFAULT '[]',
    misconceptions TEXT NOT NULL DEFAULT '[]',
    current_difficulty TEXT NOT NULL DEFAULT 'beginner'
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
CREATE TABLE IF NOT EXISTS daily_goals (
    student_id TEXT NOT NULL REFERENCES students(id),
    goal_date TEXT NOT NULL,
    target INTEGER NOT NULL CHECK (target > 0),
    completed INTEGER NOT NULL DEFAULT 0 CHECK (completed >= 0),
    PRIMARY KEY (student_id, goal_date)
);
CREATE TABLE IF NOT EXISTS knowledge_nodes (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    area TEXT NOT NULL DEFAULT '',
    subject TEXT NOT NULL DEFAULT '',
    module TEXT NOT NULL DEFAULT '',
    topic TEXT NOT NULL DEFAULT '',
    node_type TEXT NOT NULL DEFAULT 'concept',
    difficulty TEXT NOT NULL DEFAULT 'beginner',
    learning_objectives TEXT NOT NULL DEFAULT '[]',
    prerequisites TEXT NOT NULL DEFAULT '[]',
    skills TEXT NOT NULL DEFAULT '[]',
    aliases TEXT NOT NULL DEFAULT '[]',
    tags TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS knowledge_relations (
    source_id TEXT NOT NULL REFERENCES knowledge_nodes(id),
    target_id TEXT NOT NULL REFERENCES knowledge_nodes(id),
    relation_type TEXT NOT NULL,
    PRIMARY KEY (source_id, target_id, relation_type)
);
CREATE TABLE IF NOT EXISTS retention_states (
    student_id TEXT NOT NULL REFERENCES students(id),
    knowledge_node_id TEXT NOT NULL REFERENCES knowledge_nodes(id),
    stability REAL NOT NULL DEFAULT 0 CHECK (stability >= 0),
    difficulty REAL NOT NULL DEFAULT 0.5 CHECK (difficulty BETWEEN 0 AND 1),
    retrievability REAL NOT NULL DEFAULT 0 CHECK (retrievability BETWEEN 0 AND 1),
    review_count INTEGER NOT NULL DEFAULT 0 CHECK (review_count >= 0),
    successful_reviews INTEGER NOT NULL DEFAULT 0 CHECK (successful_reviews >= 0),
    failed_reviews INTEGER NOT NULL DEFAULT 0 CHECK (failed_reviews >= 0),
    last_review_at TEXT,
    next_review_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (student_id, knowledge_node_id)
);
CREATE TABLE IF NOT EXISTS review_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id TEXT NOT NULL REFERENCES students(id),
    knowledge_node_id TEXT NOT NULL REFERENCES knowledge_nodes(id),
    reviewed_at TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK (outcome IN ('success', 'partial', 'failure')),
    score REAL NOT NULL CHECK (score BETWEEN 0 AND 100),
    previous_interval_days REAL NOT NULL CHECK (previous_interval_days >= 0),
    new_interval_days REAL NOT NULL CHECK (new_interval_days > 0),
    previous_retention REAL NOT NULL CHECK (previous_retention BETWEEN 0 AND 1),
    new_retention REAL NOT NULL CHECK (new_retention BETWEEN 0 AND 1)
);
CREATE INDEX IF NOT EXISTS idx_attempts_student ON exercise_attempts(student_id);
CREATE INDEX IF NOT EXISTS idx_progress_student ON learning_progress(student_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_relations_target ON knowledge_relations(target_id, relation_type);
CREATE INDEX IF NOT EXISTS idx_retention_due ON retention_states(student_id, next_review_at);
CREATE INDEX IF NOT EXISTS idx_review_history_node ON review_history(student_id, knowledge_node_id, reviewed_at);
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
        study_columns = {row[1] for row in connection.execute(
            "PRAGMA table_info(study_sessions)")}
        exercise_columns = {row[1] for row in connection.execute(
            "PRAGMA table_info(exercises)")}

        session_migrations = {
            "session_id": "ALTER TABLE study_sessions ADD COLUMN session_id TEXT",
            "status": "ALTER TABLE study_sessions ADD COLUMN status TEXT NOT NULL DEFAULT 'active'",
            "interactions": "ALTER TABLE study_sessions ADD COLUMN interactions TEXT NOT NULL DEFAULT '[]'",
            "pedagogical_state": "ALTER TABLE study_sessions ADD COLUMN pedagogical_state TEXT NOT NULL DEFAULT 'orient'",
            "learning_objective": "ALTER TABLE study_sessions ADD COLUMN learning_objective TEXT NOT NULL DEFAULT ''",
            "diagnostic_result": "ALTER TABLE study_sessions ADD COLUMN diagnostic_result TEXT NOT NULL DEFAULT '{}'",
            "knowledge_checks": "ALTER TABLE study_sessions ADD COLUMN knowledge_checks TEXT NOT NULL DEFAULT '[]'",
            "misconceptions": "ALTER TABLE study_sessions ADD COLUMN misconceptions TEXT NOT NULL DEFAULT '[]'",
            "current_difficulty": "ALTER TABLE study_sessions ADD COLUMN current_difficulty TEXT NOT NULL DEFAULT 'beginner'",
        }
        exercise_migrations = {
            "area": "ALTER TABLE exercises ADD COLUMN area TEXT NOT NULL DEFAULT ''",
            "subtopic": "ALTER TABLE exercises ADD COLUMN subtopic TEXT NOT NULL DEFAULT ''",
            "exercise_type": "ALTER TABLE exercises ADD COLUMN exercise_type TEXT NOT NULL DEFAULT 'short_answer'",
            "options": "ALTER TABLE exercises ADD COLUMN options TEXT NOT NULL DEFAULT '[]'",
            "learning_objective": "ALTER TABLE exercises ADD COLUMN learning_objective TEXT NOT NULL DEFAULT ''",
        }

        for column, statement in session_migrations.items():
            if column not in study_columns:
                connection.execute(statement)

        for column, statement in exercise_migrations.items():
            if column not in exercise_columns:
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
