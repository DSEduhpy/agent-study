"""Provider-independent domain models for learning and progress tracking."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Any


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class Difficulty(StrEnum):
    """Difficulty levels shared by lessons and exercises."""

    BEGINNER = "beginner"
    EASY = "easy"
    INTERMEDIATE = "intermediate"
    MEDIUM = "medium"
    ADVANCED = "advanced"
    HARD = "hard"


class ExerciseType(StrEnum):
    """Supported exercise formats."""

    MULTIPLE_CHOICE = "multiple_choice"
    TRUE_FALSE = "true_false"
    SHORT_ANSWER = "short_answer"
    CODE = "code"
    DEBUGGING = "debugging"
    QUERY = "query"
    COMMAND_LINE = "command_line"
    PRACTICAL_SCENARIO = "practical_scenario"
    ANALYSIS = "analysis"


class ReviewOutcome(StrEnum):
    """Normalized result of a retention review."""

    SUCCESS = "success"
    PARTIAL = "partial"
    FAILURE = "failure"


class ReviewStatus(StrEnum):
    """Logical scheduling state for a retention review."""

    DUE = "due"
    UPCOMING = "upcoming"
    OVERDUE = "overdue"
    MASTERED = "mastered"


@dataclass(frozen=True)
class RetentionConfig:
    """Centralized parameters for the initial retention heuristic."""

    initial_interval_days: float = 1.0
    minimum_interval_days: float = 1.0
    maximum_interval_days: float = 60.0
    success_multiplier: float = 2.0
    partial_multiplier: float = 1.0
    failure_multiplier: float = 0.5

    def __post_init__(self) -> None:
        if self.minimum_interval_days <= 0 or self.maximum_interval_days < self.minimum_interval_days:
            raise ValueError("retention interval bounds are invalid")
        if self.initial_interval_days <= 0:
            raise ValueError("initial retention interval must be positive")
        if min(self.success_multiplier, self.partial_multiplier, self.failure_multiplier) <= 0:
            raise ValueError("retention multipliers must be positive")


@dataclass(frozen=True)
class RetentionState:
    """Approximate memory state for one student and one knowledge node."""

    student_id: str
    knowledge_node_id: str
    stability: float = 0.0
    difficulty: float = 0.5
    retrievability: float = 0.0
    review_count: int = 0
    successful_reviews: int = 0
    failed_reviews: int = 0
    last_review_at: datetime | None = None
    next_review_at: datetime | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if not self.student_id or not self.knowledge_node_id:
            raise ValueError("retention state identifiers cannot be empty")
        if self.stability < 0 or not 0 <= self.difficulty <= 1 or not 0 <= self.retrievability <= 1:
            raise ValueError("retention values are out of range")
        if min(self.review_count, self.successful_reviews, self.failed_reviews) < 0:
            raise ValueError("review counters cannot be negative")

    @property
    def retention_score(self) -> float:
        """A bounded estimate for scheduling, not a literal memory percentage."""
        return min(max(self.retrievability, 0.0), 1.0)


@dataclass(frozen=True)
class ReviewHistory:
    """Immutable record of one review and its scheduling effect."""

    student_id: str
    knowledge_node_id: str
    reviewed_at: datetime
    outcome: ReviewOutcome
    score: float
    previous_interval_days: float
    new_interval_days: float
    previous_retention: float
    new_retention: float

    def __post_init__(self) -> None:
        if not 0 <= self.score <= 100 or not 0 <= self.previous_retention <= 1 or not 0 <= self.new_retention <= 1:
            raise ValueError("review history values are out of range")
        if self.previous_interval_days < 0 or self.new_interval_days <= 0:
            raise ValueError("review intervals are invalid")


@dataclass(frozen=True)
class ReviewItem:
    """A scheduled state paired with its logical review status."""

    state: RetentionState
    status: ReviewStatus
    overdue_duration: timedelta = timedelta(0)


class SessionStatus(StrEnum):
    """Lifecycle states for a study session."""

    ACTIVE = "active"
    COMPLETED = "completed"


class LessonState(StrEnum):
    """Explicit teaching sequence used by the pedagogical engine."""

    ORIENT = "orient"
    DIAGNOSE = "diagnose"
    INTRODUCE = "introduce"
    EXPLAIN = "explain"
    MENTAL_MODEL = "mental_model"
    DEMONSTRATE = "demonstrate"
    GUIDED_PRACTICE = "guided_practice"
    INDEPENDENT_PRACTICE = "independent_practice"
    CHECK = "check"
    PROFESSIONAL_APPLICATION = "professional_application"
    MASTERED = "mastered"
    REVIEW = "review"
    BLOCKED = "blocked"

    def allowed_next(self) -> tuple["LessonState", ...]:
        transitions = {
            LessonState.ORIENT: (LessonState.DIAGNOSE, LessonState.REVIEW),
            LessonState.DIAGNOSE: (LessonState.INTRODUCE, LessonState.BLOCKED, LessonState.REVIEW),
            LessonState.INTRODUCE: (LessonState.EXPLAIN, LessonState.REVIEW),
            LessonState.EXPLAIN: (LessonState.MENTAL_MODEL, LessonState.REVIEW, LessonState.BLOCKED),
            LessonState.MENTAL_MODEL: (LessonState.DEMONSTRATE, LessonState.REVIEW),
            LessonState.DEMONSTRATE: (LessonState.GUIDED_PRACTICE, LessonState.REVIEW),
            LessonState.GUIDED_PRACTICE: (LessonState.INDEPENDENT_PRACTICE, LessonState.REVIEW, LessonState.BLOCKED),
            LessonState.INDEPENDENT_PRACTICE: (LessonState.CHECK, LessonState.REVIEW),
            LessonState.CHECK: (LessonState.PROFESSIONAL_APPLICATION, LessonState.REVIEW, LessonState.BLOCKED),
            LessonState.PROFESSIONAL_APPLICATION: (LessonState.MASTERED, LessonState.REVIEW),
            LessonState.REVIEW: (LessonState.EXPLAIN, LessonState.DEMONSTRATE, LessonState.INTRODUCE, LessonState.GUIDED_PRACTICE, LessonState.CHECK, LessonState.BLOCKED, LessonState.DIAGNOSE),
            LessonState.BLOCKED: (LessonState.DIAGNOSE, LessonState.INTRODUCE, LessonState.EXPLAIN, LessonState.REVIEW),
            LessonState.MASTERED: (LessonState.REVIEW,),
        }
        return transitions.get(self, ())

    def next_state(self, target: "LessonState") -> bool:
        return target in self.allowed_next()


@dataclass(frozen=True)
class StudentProfile:
    """Learning preferences loaded from the student's profile configuration."""

    name: str
    daily_goal: int
    primary_areas: tuple[str, ...]
    secondary_areas: tuple[str, ...] = ()
    adaptive: bool = True
    prioritize_weak_topics: bool = True
    contextualize_professionally: bool = True
    use_analogies: bool = True
    include_practical_labs: bool = True


@dataclass(frozen=True)
class DailyGoal:
    """Daily exercise target and progress for one student."""

    student_id: str
    target: int
    goal_date: str = field(default_factory=lambda: utc_now().date().isoformat())
    completed: int = 0

    def __post_init__(self) -> None:
        if not self.student_id.strip():
            raise ValueError("student_id cannot be empty")
        if self.target < 1:
            raise ValueError("daily goal target must be at least 1")
        if self.completed < 0:
            raise ValueError("completed exercises cannot be negative")

    @property
    def remaining(self) -> int:
        return max(self.target - self.completed, 0)

    @property
    def progress(self) -> float:
        return min(self.completed / self.target, 1.0)

    @property
    def is_complete(self) -> bool:
        return self.completed >= self.target


@dataclass(frozen=True)
class AdaptiveRecommendation:
    """Explainable next-study recommendation derived from learner evidence."""

    topic: str
    difficulty: Difficulty
    exercise_type: ExerciseType = ExerciseType.SHORT_ANSWER
    reason: str = ""
    confidence: float = 0.0

    def __post_init__(self) -> None:
        if not self.topic.strip():
            raise ValueError("recommendation topic cannot be empty")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")


@dataclass(frozen=True)
class KnowledgeNode:
    """A curriculum concept, skill, topic, module, or subject."""

    id: str
    name: str
    description: str = ""
    area: str = ""
    subject: str = ""
    module: str = ""
    topic: str = ""
    type: str = "concept"
    difficulty: Difficulty = Difficulty.BEGINNER
    learning_objectives: tuple[str, ...] = ()
    prerequisites: tuple[str, ...] = ()
    skills: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()

    def matches(self, query: str) -> bool:
        needle = query.strip().casefold()
        return bool(needle) and needle in {self.name.casefold(), *(alias.casefold() for alias in self.aliases)}


@dataclass(frozen=True)
class KnowledgeRelation:
    """A directed semantic relation between two knowledge nodes."""

    source_id: str
    target_id: str
    relation_type: str = "related"

    def __post_init__(self) -> None:
        if not self.source_id or not self.target_id:
            raise ValueError("knowledge relation endpoints cannot be empty")
        if not self.relation_type.strip():
            raise ValueError("knowledge relation type cannot be empty")


@dataclass(frozen=True)
class Lesson:
    """A curriculum lesson whose content is stored independently of Python code."""

    id: str
    title: str
    area: str
    topic: str
    content: str
    source_path: str = ""


class Exercise:
    """A practice activity that may be created in legacy or structured formats."""

    def __init__(
        self,
        id: str,
        subject: str | None = None,
        topic: str | None = None,
        *args: object,
        difficulty: Difficulty | str = Difficulty.BEGINNER,
        question: str = "",
        expected_answer: str = "",
        explanation: str = "",
        professional_context: str = "",
        area: str = "",
        subtopic: str = "",
        exercise_type: ExerciseType | str = ExerciseType.SHORT_ANSWER,
        options: tuple[str, ...] | list[str] | None = None,
        learning_objective: str = "",
        created_at: datetime | None = None,
    ) -> None:
        self.id = id
        self.subject = str(subject or "")
        self.topic = str(topic or "")
        self.difficulty = Difficulty(difficulty if isinstance(
            difficulty, str) else difficulty.value)
        self.question = str(question)
        self.expected_answer = str(expected_answer)
        self.explanation = str(explanation)
        self.professional_context = str(professional_context)
        self.area = str(area or self.subject)
        self.subtopic = str(subtopic)
        self.exercise_type = ExerciseType(exercise_type if isinstance(
            exercise_type, str) else exercise_type.value)
        self.options = tuple(str(item) for item in (options or ()))
        self.learning_objective = str(learning_objective)
        self.created_at = created_at or utc_now()

        if args:
            parsed = self._parse_legacy_arguments(args)
            if parsed is not None:
                (
                    self.area,
                    self.subject,
                    self.topic,
                    self.subtopic,
                    self.difficulty,
                    self.exercise_type,
                    self.question,
                    self.options,
                    self.expected_answer,
                    self.explanation,
                    self.professional_context,
                    self.learning_objective,
                ) = parsed

    @property
    def exercise_id(self) -> str:
        return self.id

    @staticmethod
    def _parse_legacy_arguments(args: tuple[object, ...]) -> tuple[str, str, str, str, Difficulty, ExerciseType, str, tuple[str, ...], str, str, str, str] | None:
        if len(args) >= 5 and isinstance(args[0], (Difficulty, str)):
            difficulty, question, expected_answer, explanation, professional_context = (
                args[0],
                args[1],
                args[2],
                args[3] if len(args) > 3 else "",
                args[4] if len(args) > 4 else "",
            )
            return (
                "",
                "",
                "",
                "",
                Difficulty(str(difficulty).lower()) if not isinstance(
                    difficulty, Difficulty) else difficulty,
                ExerciseType.SHORT_ANSWER,
                str(question),
                tuple(),
                str(expected_answer),
                str(explanation),
                str(professional_context),
                "",
            )

        if len(args) >= 8 and isinstance(args[0], (str, Difficulty)):
            area, subject, topic, difficulty, question, expected_answer, explanation, professional_context = (
                args[0],
                args[1],
                args[2],
                args[3],
                args[4],
                args[5],
                args[6],
                args[7],
            )
            return (
                str(area),
                str(subject),
                str(topic),
                "",
                Difficulty(str(difficulty).lower()) if not isinstance(
                    difficulty, Difficulty) else difficulty,
                ExerciseType.SHORT_ANSWER,
                str(question),
                tuple(),
                str(expected_answer),
                str(explanation),
                str(professional_context),
                "",
            )
        return None


@dataclass(frozen=True)
class ExerciseAttempt:
    """One student's answer and result for an exercise."""

    exercise_id: str
    answer: str
    correct: bool
    score: float
    feedback: str = ""
    timestamp: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if not 0 <= self.score <= 100:
            raise ValueError("score must be between 0 and 100")


@dataclass(frozen=True)
class Evaluation:
    """Structured feedback produced when an answer is evaluated."""

    score: float
    correct: bool
    feedback: str
    next_focus: str = ""
    explanation: str = ""
    misconception: str = ""
    confidence: float = 0.0
    status: str = "correct"

    def __post_init__(self) -> None:
        if not 0 <= self.score <= 100:
            raise ValueError("score must be between 0 and 100")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")


@dataclass(frozen=True)
class LearningProgress:
    """Aggregated progress for one student and topic."""

    student_id: str
    topic: str
    lessons_completed: int = 0
    exercises_attempted: int = 0
    average_score: float = 0.0
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class KnowledgeCheckResult:
    """Structured evidence used to decide whether a concept is understood."""

    score: float
    confidence: float
    correct: bool
    reasoning_quality: float
    misconception: str = ""
    recommendation: str = ""

    def __post_init__(self) -> None:
        if not 0 <= self.score <= 100:
            raise ValueError("score must be between 0 and 100")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if not 0.0 <= self.reasoning_quality <= 1.0:
            raise ValueError("reasoning_quality must be between 0 and 1")


class PedagogicalDecisionAction(StrEnum):
    """Instructional decisions that an engine can make during a teaching flow."""

    ADVANCE = "advance"
    REVIEW = "review"
    RETEACH = "reteach"
    ASK = "ask"
    PRACTICE = "practice"
    SIMPLIFY = "simplify"
    INCREASE_DIFFICULTY = "increase_difficulty"
    DECREASE_DIFFICULTY = "decrease_difficulty"
    END_SESSION = "end_session"


@dataclass(frozen=True)
class PedagogicalDecision:
    """Structured, teachable action chosen after evaluating a response."""

    action: PedagogicalDecisionAction
    next_state: LessonState
    reason: str
    confidence: float
    recommended_difficulty: str = "beginner"

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")


@dataclass(frozen=True)
class StudySession:
    """A bounded period in which a student studies."""

    student_id: str
    started_at: datetime = field(default_factory=utc_now)
    ended_at: datetime | None = None
    lesson_ids: tuple[str, ...] = ()
    notes: str = ""
    session_id: str = ""
    status: SessionStatus = SessionStatus.ACTIVE
    interactions: tuple[str, ...] = ()
    pedagogical_state: LessonState = LessonState.ORIENT
    learning_objective: str = ""
    diagnostic_result: KnowledgeCheckResult | None = None
    knowledge_checks: tuple[KnowledgeCheckResult, ...] = ()
    misconceptions: tuple[str, ...] = ()
    current_difficulty: str = "beginner"


@dataclass(frozen=True)
class DatabaseRecord:
    """Small typed boundary object for repository results."""

    values: dict[str, Any]
