"""Structured application boundary for the VS Code Study Agent client."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from study_agent.ai.client import OpenAIProvider
from study_agent.ai.ollama import OllamaProvider
from study_agent.ai.provider import AIProvider
from study_agent.config.settings import load_settings, load_student_profile
from study_agent.core.models import Exercise, ExerciseType, KnowledgeNode
from study_agent.curriculum.engine import CurriculumEngine
from study_agent.curriculum.loader import CurriculumLoader
from study_agent.database.sqlite import SQLiteDatabase
from study_agent.learning.adaptive_learning import AdaptiveLearningEngine
from study_agent.learning.daily_goal import DailyGoalEngine
from study_agent.learning.exercise_engine import ExerciseEngine, ExerciseEvaluator, ExerciseGenerator, ExerciseSelector
from study_agent.learning.pedagogy import PedagogicalEngine
from study_agent.learning.retention import RetentionEngine, load_retention_config
from study_agent.learning.tutor import TutorEngine
from study_agent.memory.repository import LearningRepository


class StudyAgentApplication:
    """Facade consumed by the extension; it never exposes SQL or provider details."""

    def __init__(self, project_root: Path | str | None = None, provider: AIProvider | None = None) -> None:
        self.root = Path(project_root or Path.cwd()).resolve()
        self.settings = load_settings(self.root)
        self.profile = load_student_profile(self.settings.profile_path)
        self.loader = CurriculumLoader(self.root / "curriculum")
        self.repository = LearningRepository(SQLiteDatabase(self.settings.database_path))
        self.repository.save_student("default", self.profile)
        self._provider = provider
        self.curriculum = CurriculumEngine(self.loader.root, self.repository)
        self.retention = RetentionEngine(
            self.repository,
            config=load_retention_config(self.root / "config" / "retention.yaml"),
        )
        self.daily_goal = DailyGoalEngine(self.repository, self.profile)
        self._tutor: TutorEngine | None = None
        self._pedagogy: PedagogicalEngine | None = None
        self._exercise: ExerciseEngine | None = None

    def handle(self, operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        if operation == "dashboard":
            return self.get_dashboard()
        if operation == "curriculum":
            return self.get_curriculum()
        if operation == "reviews":
            return self.get_reviews()
        if operation == "concept":
            return self.get_concept(str(payload.get("query", "")))
        if operation == "startLesson":
            return self.start_lesson(str(payload.get("lessonId", "")), payload.get("sessionId"))
        if operation == "askTutor":
            return self.ask_tutor(str(payload.get("sessionId", "")), str(payload.get("question", "")))
        if operation == "startExercise":
            return self.start_exercise(str(payload.get("topic", "")), str(payload.get("sessionId", "")))
        if operation == "submitAnswer":
            return self.submit_answer(payload)
        raise ValueError("unsupported operation")

    def get_dashboard(self) -> dict[str, Any]:
        goal = self.daily_goal.status("default")
        reviews = self.retention.due("default")
        latest_session = self.repository.get_latest_session("default")
        recommendation = None
        try:
            recommendation = AdaptiveLearningEngine(self.repository, self.curriculum, self.retention).recommend_next("default")
        except ValueError:
            pass
        return {
            "type": "dashboard",
            "firstLessonId": self.loader.list_lessons()[0] if self.loader.list_lessons() else None,
            "resumeSessionId": latest_session.session_id if latest_session else None,
            "resumeLessonId": latest_session.lesson_ids[-1] if latest_session and latest_session.lesson_ids else None,
            "resumeState": latest_session.pedagogical_state.value if latest_session else None,
            "dailyGoal": {"target": goal.target, "completed": goal.completed, "remaining": goal.remaining},
            "reviewCount": len(reviews),
            "reviews": [self._review_item(item) for item in reviews[:5]],
            "recommendation": self._recommendation(recommendation),
        }

    def get_curriculum(self) -> dict[str, Any]:
        return {
            "type": "curriculum",
            "subjects": self.curriculum.list_subjects(),
            "topics": self.curriculum.list_topics(),
            "concepts": [self._node(node) for node in sorted(self.curriculum.graph.nodes.values(), key=lambda item: item.name)],
        }

    def get_reviews(self) -> dict[str, Any]:
        return {"type": "reviews", "items": [self._review_item(item) for item in self.retention.reviews("default")]}

    def get_concept(self, query: str) -> dict[str, Any]:
        node = self.curriculum.get_node(query)
        state = self.retention.get("default", node.id)
        return {"type": "concept", "concept": self._node(node), "prerequisites": [self._node(item) for item in self.curriculum.prerequisites(node.id)], "retention": self._state(state)}

    def start_lesson(self, lesson_id: str, session_id: str | None = None) -> dict[str, Any]:
        self._ensure_learning_services()
        session = self.repository.get_session(session_id) if session_id else None
        if session is None:
            session = self._pedagogy.start_session(self._tutor.start_session("default", lesson_id))
        return {"type": "lesson", "sessionId": session.session_id, "state": session.pedagogical_state.value, "content": self._pedagogy.generate_step_message(session, "Lesson objective")}

    def ask_tutor(self, session_id: str, question: str) -> dict[str, Any]:
        if not question.strip():
            raise ValueError("question cannot be empty")
        self._ensure_learning_services()
        session = self.repository.get_session(session_id)
        if session is None:
            raise ValueError("study session not found")
        return {"type": "tutor", "answer": self._tutor.ask(session, question)}

    def start_exercise(self, topic: str, session_id: str) -> dict[str, Any]:
        self._ensure_learning_services()
        session = self.repository.get_session(session_id)
        if session is None:
            raise ValueError("study session not found")
        context = self._pedagogy.build_context(session)
        exercise = self._exercise.select_and_generate(context, student_id="default") if not topic else self._exercise.generate_exercise(context, exercise_type=ExerciseType.SHORT_ANSWER)
        node_id = None
        matches = self.curriculum.find(exercise.topic)
        if matches:
            node_id = matches[0].id
        return {"type": "exercise", "exercise": self._exercise_data(exercise, node_id), "sessionId": session_id}

    def submit_answer(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._ensure_learning_services()
        exercise = Exercise(
            str(payload.get("exerciseId", "exercise")),
            subject=str(payload.get("subject", "")), topic=str(payload.get("topic", "")),
            question=str(payload.get("question", "")), expected_answer=str(payload.get("expectedAnswer", "")),
            explanation=str(payload.get("explanation", "")), exercise_type=str(payload.get("exerciseType", "short_answer")),
        )
        self.repository.save_exercise(exercise)
        evaluation, _ = self._exercise.submit_answer(exercise, str(payload.get("answer", "")), student_id="default", knowledge_node_id=payload.get("knowledgeNodeId"))
        return {"type": "evaluation", "evaluation": {"score": evaluation.score, "correct": evaluation.correct, "status": evaluation.status, "feedback": evaluation.feedback, "explanation": evaluation.explanation, "misconception": evaluation.misconception}}

    def _ensure_learning_services(self) -> None:
        if self._tutor is not None:
            return
        if self._provider is not None:
            provider = self._provider
        elif self.settings.ai_provider.lower() == "ollama":
            provider = OllamaProvider(self.settings)
        elif self.settings.ai_provider.lower() == "openai":
            provider = OpenAIProvider(self.settings)
        else:
            raise ValueError(
                f"Unsupported AI provider: {self.settings.ai_provider}"
            )
        self._tutor = TutorEngine(self.loader, provider, self.repository, self.profile, self.root / "prompts")
        self._pedagogy = PedagogicalEngine(self._tutor, self.loader, self.repository, self.profile, self.root / "prompts")
        self._exercise = ExerciseEngine(ExerciseGenerator(provider), ExerciseSelector(self.repository), ExerciseEvaluator(provider), self.repository, self._pedagogy, self.daily_goal, self.retention)

    @staticmethod
    def _node(node: KnowledgeNode) -> dict[str, Any]:
        return {"id": node.id, "name": node.name, "area": node.area, "subject": node.subject, "module": node.module, "topic": node.topic, "type": node.type, "aliases": list(node.aliases), "skills": list(node.skills)}

    def _review_item(self, item: Any) -> dict[str, Any]:
        node = self.curriculum.get_node(item.state.knowledge_node_id)
        return {"concept": node.name, "nodeId": node.id, "status": item.status.value, "overdueSeconds": int(item.overdue_duration.total_seconds())}

    @staticmethod
    def _state(state: Any) -> dict[str, Any] | None:
        if state is None:
            return None
        return {"reviewCount": state.review_count, "successfulReviews": state.successful_reviews, "failedReviews": state.failed_reviews, "lastReviewAt": state.last_review_at.isoformat() if state.last_review_at else None, "nextReviewAt": state.next_review_at.isoformat() if state.next_review_at else None, "status": state.retention_score}

    @staticmethod
    def _recommendation(value: Any) -> dict[str, Any] | None:
        if value is None:
            return None
        return {"topic": value.topic, "difficulty": value.difficulty.value, "reason": value.reason}

    @staticmethod
    def _exercise_data(exercise: Exercise, node_id: str | None = None) -> dict[str, Any]:
        return {"id": exercise.id, "area": exercise.area, "subject": exercise.subject, "topic": exercise.topic, "subtopic": exercise.subtopic, "question": exercise.question, "expectedAnswer": exercise.expected_answer, "explanation": exercise.explanation, "professionalContext": exercise.professional_context, "learningObjective": exercise.learning_objective, "exerciseType": exercise.exercise_type.value, "difficulty": exercise.difficulty.value, "options": list(exercise.options), "knowledgeNodeId": node_id}


def serve() -> None:
    """Serve one structured response per JSON request on stdin."""
    app = StudyAgentApplication()
    for line in sys.stdin:
        try:
            request = json.loads(line)
            result = app.handle(str(request.get("operation", "")), request.get("payload") or {})
            response = {"ok": True, "requestId": request.get("requestId"), "data": result}
        except Exception as exc:
            response = {"ok": False, "requestId": request.get("requestId") if "request" in locals() else None, "error": {"type": "error", "code": _error_code(exc), "message": str(exc)}}
        print(json.dumps(response, ensure_ascii=True), flush=True)


def _error_code(error: Exception) -> str:
    name = type(error).__name__.upper()
    return "AI_PROVIDER_UNAVAILABLE" if "PROVIDER" in name else "INVALID_REQUEST" if isinstance(error, (ValueError, KeyError)) else "APPLICATION_ERROR"


if __name__ == "__main__":
    serve()