"""Pedagogical state machine and teaching decisions for progressive learning."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from study_agent.core.models import (
    KnowledgeCheckResult,
    LessonState,
    PedagogicalDecision,
    PedagogicalDecisionAction,
    StudentProfile,
    StudySession,
)
from study_agent.curriculum.loader import CurriculumLoader
from study_agent.memory.repository import LearningRepository
from study_agent.learning.tutor import TutorEngine


@dataclass(frozen=True)
class PedagogicalContext:
    """Snapshot used to generate the next teaching step."""

    current_state: LessonState
    learning_objective: str
    previous_interactions: tuple[str, ...]
    diagnostic_result: KnowledgeCheckResult | None
    knowledge_checks: tuple[KnowledgeCheckResult, ...]
    misconceptions: tuple[str, ...]
    current_difficulty: str
    student_profile: StudentProfile
    lesson_title: str
    lesson_area: str
    lesson_topic: str


class PedagogicalEngine:
    """Coordinate teaching strategy, state transitions, and adaptive reinforcement."""

    def __init__(
        self,
        tutor: TutorEngine,
        curriculum: CurriculumLoader,
        repository: LearningRepository,
        profile: StudentProfile,
        prompt_root: Path | str = "prompts",
    ) -> None:
        self.tutor = tutor
        self.curriculum = curriculum
        self.repository = repository
        self.profile = profile
        self.prompt_root = Path(prompt_root)
        self.pedagogical_prompt = self._read_prompt("pedagogical.md")

    def start_session(self, session: StudySession) -> StudySession:
        """Initialize the pedagogical state for an existing study session."""
        lesson = self.curriculum.load(session.lesson_ids[-1])
        objective = session.learning_objective or f"Understand {lesson.title} and apply it safely."
        updated = replace(
            session,
            pedagogical_state=LessonState.ORIENT,
            learning_objective=objective,
            current_difficulty="beginner",
        )
        self.repository.update_session(updated)
        return updated

    def advance_state(self, session: StudySession, next_state: LessonState) -> StudySession:
        """Advance only through explicit, valid transitions."""
        current = session.pedagogical_state
        if current == next_state:
            return session
        valid_transition = next_state in current.allowed_next(
        ) or next_state == LessonState.REVIEW and current in LessonState.__members__.values()
        if not valid_transition:
            raise ValueError(
                f"Invalid transition from {current.value} to {next_state.value}")
        updated = replace(session, pedagogical_state=next_state)
        if next_state == LessonState.REVIEW:
            updated = replace(updated, current_difficulty="beginner")
        self.repository.update_session(updated)
        return updated

    def apply_decision(
        self,
        session: StudySession,
        action: PedagogicalDecisionAction | str,
        reason: str,
        *,
        confidence: float = 0.75,
        next_state: LessonState | None = None,
    ) -> StudySession:
        """Persist a teaching decision and move to the chosen state."""
        if isinstance(action, str):
            action = PedagogicalDecisionAction(action)
        selected_state = next_state or self._decision_to_state(action)
        return self.advance_state(session, selected_state)

    def diagnose(self, session: StudySession, student_answer: str) -> KnowledgeCheckResult:
        """Assess the student's prior knowledge and set a learning baseline."""
        lowered = student_answer.lower()
        if any(token in lowered for token in ("project", "write", "used", "daily", "can use")):
            score = 85.0
            confidence = 0.9
            correct = True
            reasoning_quality = 0.8
            recommendation = "Proceed with a targeted practical review; avoid rehashing the basics."
        elif any(token in lowered for token in ("seen", "simple", "familiar", "some")):
            score = 65.0
            confidence = 0.8
            correct = True
            reasoning_quality = 0.7
            recommendation = "Review the main syntax and patterns before moving into advanced applications."
        else:
            score = 35.0
            confidence = 0.7
            correct = False
            reasoning_quality = 0.5
            recommendation = "Start from the core concept, show the mental model, and verify understanding before practice."

        result = KnowledgeCheckResult(
            score=score,
            confidence=confidence,
            correct=correct,
            reasoning_quality=reasoning_quality,
            recommendation=recommendation,
        )
        updated = replace(
            session,
            diagnostic_result=result,
            knowledge_checks=session.knowledge_checks + (result,),
            current_difficulty="intermediate" if score >= 70 else "beginner",
        )
        self.repository.update_session(updated)
        return result

    def check_knowledge(self, session: StudySession, answer: str) -> KnowledgeCheckResult:
        """Evaluate a concept check while looking for the specific misconception."""
        lowered = answer.lower()
        if "where" in lowered and "filter" in lowered and "column" not in lowered:
            result = KnowledgeCheckResult(
                score=88.0,
                confidence=0.82,
                correct=True,
                reasoning_quality=0.9,
                recommendation="Good; explain how the filter affects rows and then move to a short practice exercise.",
            )
        elif "where" in lowered and "column" in lowered:
            result = KnowledgeCheckResult(
                score=28.0,
                confidence=0.66,
                correct=False,
                reasoning_quality=0.4,
                misconception="Confusion between selecting columns and filtering rows: WHERE filters rows, while SELECT chooses columns.",
                recommendation="Re-explain the difference between selection and filtering before continuing.",
            )
        elif "select" in lowered and "column" in lowered and "filter" not in lowered:
            result = KnowledgeCheckResult(
                score=40.0,
                confidence=0.6,
                correct=False,
                reasoning_quality=0.45,
                misconception="The student is conflating the SELECT clause with filtering logic.",
                recommendation="Return to a concrete example and contrast SELECT and WHERE in the same query.",
            )
        else:
            result = KnowledgeCheckResult(
                score=62.0,
                confidence=0.7,
                correct=True,
                reasoning_quality=0.7,
                recommendation="The answer is partly correct; give a quick example to tighten the interpretation.",
            )

        misconceptions = list(session.misconceptions)
        if result.misconception:
            misconceptions.append(result.misconception)
        updated = replace(
            session,
            knowledge_checks=session.knowledge_checks + (result,),
            misconceptions=tuple(dict.fromkeys(misconceptions)),
            current_difficulty="beginner" if result.correct is False else session.current_difficulty,
        )
        self.repository.update_session(updated)
        return result

    def make_decision(
        self,
        session: StudySession,
        *,
        correct: bool,
        confidence: float,
        misconception: str | None = None,
    ) -> PedagogicalDecision:
        """Translate observed performance into a crisp teaching action."""
        if not correct or confidence < 0.6:
            return PedagogicalDecision(
                action=PedagogicalDecisionAction.REVIEW,
                next_state=LessonState.REVIEW,
                reason=misconception or "The concept is not stable enough to advance safely.",
                confidence=min(max(confidence, 0.0), 1.0),
                recommended_difficulty="beginner",
            )
        if confidence >= 0.85:
            return PedagogicalDecision(
                action=PedagogicalDecisionAction.ADVANCE,
                next_state=LessonState.PROFESSIONAL_APPLICATION,
                reason="Evidence suggests the student can move toward contextual application.",
                confidence=min(max(confidence, 0.0), 1.0),
                recommended_difficulty="intermediate",
            )
        return PedagogicalDecision(
            action=PedagogicalDecisionAction.PRACTICE,
            next_state=LessonState.GUIDED_PRACTICE,
            reason="A quick practice cycle is the safest next move.",
            confidence=min(max(confidence, 0.0), 1.0),
            recommended_difficulty="beginner",
        )

    def build_context(self, session: StudySession, limit: int = 5) -> PedagogicalContext:
        """Create a compact but useful teaching context for the next prompt."""
        lesson = self.curriculum.load(session.lesson_ids[-1])
        previous = session.interactions[-limit:
                                        ] if limit else session.interactions
        return PedagogicalContext(
            current_state=session.pedagogical_state,
            learning_objective=session.learning_objective or f"Understand {lesson.title}",
            previous_interactions=previous,
            diagnostic_result=session.diagnostic_result,
            knowledge_checks=session.knowledge_checks,
            misconceptions=session.misconceptions,
            current_difficulty=session.current_difficulty,
            student_profile=self.profile,
            lesson_title=lesson.title,
            lesson_area=lesson.area,
            lesson_topic=lesson.topic,
        )

    def generate_step_message(self, session: StudySession, user_request: str) -> str:
        """Create a short teaching message using the current pedagogical state."""
        context = self.build_context(session)
        rendered_prompt = self._render_pedagogical_prompt(context)

        return (
            f"Current pedagogical state: {context.current_state.value}\n"
            f"Objective: {context.learning_objective}\n"
            f"Difficulty: {context.current_difficulty}\n"
            f"Lesson: {context.lesson_title} "
            f"({context.lesson_area}/{context.lesson_topic})\n\n"
            f"Teacher guidance: {rendered_prompt}\n\n"
            f"Student request: {user_request.strip()}"
        )

    def _render_pedagogical_prompt(self, context: PedagogicalContext) -> str:
        """Render the pedagogical template using the current learning context."""
        replacements = {
            "{{CURRENT_STATE}}": context.current_state.value,
            "{{STUDENT_PROFILE}}": self._format_student_profile(
                context.student_profile
            ),
            "{{OBJECTIVE}}": context.learning_objective,
            "{{CURRENT_DIFFICULTY}}": context.current_difficulty,
            "{{PREVIOUS_INTERACTIONS}}": self._format_list(
                context.previous_interactions
            ),
            "{{DIAGNOSTIC_RESULT}}": self._format_knowledge_check(
                context.diagnostic_result
            ),
            "{{KNOWLEDGE_CHECKS}}": self._format_knowledge_checks(
                context.knowledge_checks
            ),
            "{{MISCONCEPTIONS}}": self._format_list(
                context.misconceptions
            ),
        }

        rendered = self.pedagogical_prompt
        for placeholder, value in replacements.items():
            rendered = rendered.replace(placeholder, value)

        return rendered

    @staticmethod
    def _format_student_profile(profile: StudentProfile) -> str:
        """Format student preferences as stable, readable prompt data."""
        return (
            f"Name: {profile.name}\n"
            f"Daily goal: {profile.daily_goal}\n"
            f"Primary areas: {', '.join(profile.primary_areas) or 'None'}\n"
            f"Secondary areas: {', '.join(profile.secondary_areas) or 'None'}\n"
            f"Adaptive learning: {profile.adaptive}\n"
            f"Prioritize weak topics: {profile.prioritize_weak_topics}\n"
            f"Professional context: {profile.contextualize_professionally}\n"
            f"Use analogies: {profile.use_analogies}\n"
            f"Practical labs: {profile.include_practical_labs}"
        )

    @staticmethod
    def _format_list(values: tuple[str, ...]) -> str:
        """Format a sequence as stable bullet points for the prompt."""
        if not values:
            return "None"

        return "\n".join(f"- {value}" for value in values)

    @staticmethod
    def _format_knowledge_check(
        result: KnowledgeCheckResult | None,
    ) -> str:
        """Format one knowledge-check result for the prompt."""
        if result is None:
            return "None"

        return (
            f"Score: {result.score}\n"
            f"Confidence: {result.confidence}\n"
            f"Correct: {result.correct}\n"
            f"Reasoning quality: {result.reasoning_quality}\n"
            f"Misconception: {result.misconception or 'None'}\n"
            f"Recommendation: {result.recommendation or 'None'}"
        )

    @classmethod
    def _format_knowledge_checks(
        cls,
        results: tuple[KnowledgeCheckResult, ...],
    ) -> str:
        """Format all knowledge-check results for the prompt."""
        if not results:
            return "None"

        return "\n\n".join(
            f"Check {index}:\n{cls._format_knowledge_check(result)}"
            for index, result in enumerate(results, start=1)
        )

    def record_interaction(self, session: StudySession, interaction: str) -> StudySession:
        """Record a student or tutor message while keeping the lesson state consistent."""
        updated = replace(
            session, interactions=session.interactions + (interaction.strip(),))
        self.repository.update_session(updated)
        return updated

    def _read_prompt(self, filename: str) -> str:
        path = self.prompt_root / filename
        return path.read_text(encoding="utf-8") if path.is_file() else ""

    @staticmethod
    def _decision_to_state(action: PedagogicalDecisionAction) -> LessonState:
        mapping = {
            PedagogicalDecisionAction.ADVANCE: LessonState.PROFESSIONAL_APPLICATION,
            PedagogicalDecisionAction.REVIEW: LessonState.REVIEW,
            PedagogicalDecisionAction.RETEACH: LessonState.EXPLAIN,
            PedagogicalDecisionAction.ASK: LessonState.DIAGNOSE,
            PedagogicalDecisionAction.PRACTICE: LessonState.GUIDED_PRACTICE,
            PedagogicalDecisionAction.SIMPLIFY: LessonState.INTRODUCE,
            PedagogicalDecisionAction.INCREASE_DIFFICULTY: LessonState.DEMONSTRATE,
            PedagogicalDecisionAction.DECREASE_DIFFICULTY: LessonState.EXPLAIN,
            PedagogicalDecisionAction.END_SESSION: LessonState.MASTERED,
        }
        return mapping.get(action, LessonState.REVIEW)
