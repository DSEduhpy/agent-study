"""Small startup entry point for validating local Study Agent configuration."""

from study_agent.config.settings import load_settings, load_student_profile
from study_agent.curriculum.loader import CurriculumLoader
from study_agent.database.sqlite import SQLiteDatabase


def initialize() -> None:
    """Load the profile and initialize local persistence."""
    settings = load_settings()
    load_student_profile(settings.profile_path)
    SQLiteDatabase(settings.database_path).initialize()


def run_cli() -> None:
    """Run a small interactive CLI using the configured provider."""
    from study_agent.ai.client import OpenAIProvider
    from study_agent.learning.tutor import TutorEngine
    from study_agent.memory.repository import LearningRepository

    settings = load_settings()
    profile = load_student_profile(settings.profile_path)
    loader = CurriculumLoader(settings.project_root / "curriculum")
    print("Study Agent\n")
    for index, lesson in enumerate(loader.list_lessons(), 1):
        print(f"{index}. {lesson}")
    lesson_id = input("\nLesson id (blank to exit): ").strip()
    if not lesson_id:
        return
    engine = TutorEngine(loader, OpenAIProvider(settings), LearningRepository(SQLiteDatabase(settings.database_path)), profile,
                         settings.project_root / "prompts")
    session = engine.start_session("default", lesson_id)
    print("\n" + engine.explain(session))
    while True:
        question = input("\nQuestion (or 'exit'): ").strip()
        if question.lower() == "exit":
            engine.finish_session(session)
            print("Session completed.")
            return
        print("\n" + engine.ask(session, question))


if __name__ == "__main__":
    initialize()
    print("Study Agent initialized")
