"""Provider-independent orchestration for lessons and tutor conversations."""

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from study_agent.ai.provider import AIProvider
from study_agent.core.models import Lesson, SessionStatus, StudentProfile, StudySession
from study_agent.curriculum.loader import CurriculumLoader
from study_agent.memory.repository import LearningRepository


@dataclass(frozen=True)
class TutorContext:
    """Structured dynamic context supplied to a tutor request."""

    student_profile: StudentProfile
    lesson: Lesson
    session: StudySession
    objective: str
    previous_interactions: tuple[str, ...] = ()


class TutorEngine:
    """Coordinate curriculum, pedagogy, provider calls, and session memory."""

    def __init__(self, curriculum: CurriculumLoader, provider: AIProvider,
                 repository: LearningRepository, profile: StudentProfile,
                 prompt_root: Path | str = "prompts") -> None:
        self.curriculum = curriculum
        self.provider = provider
        self.repository = repository
        self.profile = profile
        self.prompt_root = Path(prompt_root)
        self._sessions: dict[str, StudySession] = {}
        self._system_prompt = self._read_prompt("system.md")
        self._lesson_prompt = self._read_prompt("lesson.md")

    def start_session(self, student_id: str, lesson_id: str, *, objective: str | None = None) -> StudySession:
        """Load a lesson and persist a new active study session."""
        lesson = self.curriculum.load(lesson_id)
        lesson_key = Path(lesson.source_path).resolve().relative_to(self.curriculum.root).with_suffix("").as_posix()
        session = StudySession(student_id=student_id, lesson_ids=(lesson_key,), session_id=str(uuid4()))
        self.repository.save_student(student_id, self.profile)
        self.repository.save_lesson(lesson)
        self.repository.save_session(session)
        self._sessions[session.session_id] = session
        return session

    def explain(self, session: StudySession, *, objective: str | None = None) -> str:
        """Generate the initial explanation for the session's current lesson."""
        session = self._current_session(session)
        context = self._context(session, objective)
        prompt = self._lesson_prompt + "\n\n" + self._format_context(context)
        response = self.provider.generate(prompt, system=self._system_prompt)
        self._record_interaction(session, response)
        return response

    def ask(self, session: StudySession, question: str, *, socratic: bool = False) -> str:
        """Answer a question using the active lesson and retained session context."""
        if not question.strip():
            raise ValueError("question cannot be empty")
        session = self._current_session(session)
        context = self._context(session, None)
        mode = "Use Socratic questioning and do not reveal the solution immediately." if socratic else "Answer directly, then check understanding."
        prompt = (f"Current lesson context:\n{self._format_context(context)}\n\n"
                  f"Student question:\n{question.strip()}\n\nInstruction: {mode}")
        response = self.provider.generate(prompt, system=self._system_prompt)
        self._record_interaction(session, response)
        return response

    def finish_session(self, session: StudySession, notes: str = "") -> StudySession:
        """Mark an active session completed and persist its final context."""
        session = self._current_session(session)
        completed = replace(session, ended_at=datetime.now(timezone.utc),
                            status=SessionStatus.COMPLETED, notes=notes or session.notes)
        self.repository.update_session(completed)
        self._sessions[completed.session_id] = completed
        return completed

    def _context(self, session: StudySession, objective: str | None) -> TutorContext:
        lesson = self.curriculum.load(session.lesson_ids[-1])
        return TutorContext(self.profile, lesson, session, objective or f"Understand {lesson.title} and apply it safely.", session.interactions)

    def _record_interaction(self, session: StudySession, response: str) -> None:
        updated = replace(session, interactions=session.interactions + (response,))
        self.repository.update_session(updated)
        self._sessions[updated.session_id] = updated

    def _current_session(self, session: StudySession) -> StudySession:
        return self._sessions.get(session.session_id, session)

    def _read_prompt(self, filename: str) -> str:
        path = self.prompt_root / filename
        return path.read_text(encoding="utf-8") if path.is_file() else ""

    @staticmethod
    def _format_context(context: TutorContext) -> str:
        preferences = ", ".join(name for name, enabled in (
            ("analogies", context.student_profile.use_analogies),
            ("professional context", context.student_profile.contextualize_professionally),
            ("practical application", context.student_profile.include_practical_labs),
        ) if enabled)
        return (f"Student: {context.student_profile.name}\n"
                f"Lesson: {context.lesson.title} ({context.lesson.area}/{context.lesson.topic})\n"
                f"Objective: {context.objective}\n"
                f"Preferences: {preferences}\n"
                f"Lesson content:\n{context.lesson.content}\n"
                f"Previous interactions: {len(context.previous_interactions)}")