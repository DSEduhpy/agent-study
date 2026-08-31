from pathlib import Path

from study_agent.application import StudyAgentApplication
from study_agent.ai.provider import AIProvider
from study_agent.core.models import LessonState


class OfflineProvider(AIProvider):
    def generate(self, prompt: str, *, system: str | None = None) -> str:
        if "Evaluate the student's answer" in prompt:
            return '{"correct": true, "score": 90, "feedback": "Correct", "confidence": 0.9}'
        return "Study content"

    def generate_structured(self, prompt: str, schema: type, *, system: str | None = None):
        return {
            "area": "data_science", "subject": "SQL", "topic": "JOIN", "subtopic": "table relationships",
            "difficulty": "easy", "exercise_type": "short_answer", "question": "What does JOIN do?",
            "options": [], "expected_answer": "combine", "explanation": "JOIN combines related rows.",
            "professional_context": "An analyst combines customer and order tables.",
            "learning_objective": "Combine related tables.",
        }


def test_application_facade_returns_structured_offline_dashboard(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STUDY_AGENT_DATABASE", str(tmp_path / "facade.sqlite3"))
    application = StudyAgentApplication(Path.cwd())
    dashboard = application.handle("dashboard", {})
    assert dashboard["type"] == "dashboard"
    assert dashboard["dailyGoal"]["target"] == 5
    assert dashboard["firstLessonId"]


def test_application_facade_runs_offline_study_to_retention_flow(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STUDY_AGENT_DATABASE", str(tmp_path / "flow.sqlite3"))
    application = StudyAgentApplication(Path.cwd(), OfflineProvider())
    lesson = application.handle("startLesson", {"lessonId": "data_science/sql/joins"})
    assert lesson["sessionId"] and lesson["state"]
    exercise = application.handle("startExercise", {"sessionId": lesson["sessionId"], "topic": ""})
    payload = exercise["exercise"]
    result = application.handle("submitAnswer", {**payload, "answer": "combine"})
    assert result["evaluation"]["correct"] is True
    assert application.handle("dashboard", {})["dailyGoal"]["completed"] == 1
    assert application.handle("concept", {"query": "JOIN"})["retention"]["successfulReviews"] == 1


def test_application_dashboard_resumes_persisted_session(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STUDY_AGENT_DATABASE", str(tmp_path / "resume.sqlite3"))
    application = StudyAgentApplication(Path.cwd(), OfflineProvider())
    lesson = application.handle("startLesson", {"lessonId": "data_science/sql/joins"})
    session = application.repository.get_session(lesson["sessionId"])
    assert session is not None
    resumed = application.handle("startLesson", {"lessonId": "data_science/sql/joins", "sessionId": lesson["sessionId"]})
    assert resumed["sessionId"] == lesson["sessionId"]
    assert resumed["state"] == LessonState.ORIENT.value