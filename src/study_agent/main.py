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
    from study_agent.core.models import LessonState
    from study_agent.learning.pedagogy import PedagogicalEngine
    from study_agent.learning.adaptive_learning import AdaptiveLearningEngine
    from study_agent.curriculum.engine import CurriculumEngine
    from study_agent.learning.retention import RetentionEngine, load_retention_config
    from study_agent.learning.tutor import TutorEngine
    from study_agent.memory.repository import LearningRepository

    settings = load_settings()
    profile = load_student_profile(settings.profile_path)
    loader = CurriculumLoader(settings.project_root / "curriculum")
    repository = LearningRepository(SQLiteDatabase(settings.database_path))
    curriculum = CurriculumEngine(settings.project_root / "curriculum", repository)
    retention = RetentionEngine(repository, config=load_retention_config(settings.project_root / "config" / "retention.yaml"))
    adaptive = AdaptiveLearningEngine(repository, curriculum, retention)
    print("Study Agent\n")
    for index, lesson in enumerate(loader.list_lessons(), 1):
        print(f"{index}. {lesson}")
    lesson_id = input("\nLesson id or command (blank to exit): ").strip()
    if not lesson_id:
        return

    command, _, argument = lesson_id.partition(" ")
    if command.lower() in {"curriculum", "subjects", "topics", "concept", "prerequisites", "recommend", "reviews", "due", "overdue", "retention"}:
        _run_curriculum_command(command.lower(), argument.strip(), curriculum, adaptive, retention)
        return

    tutor = TutorEngine(loader, OpenAIProvider(settings), repository, profile,
                        settings.project_root / "prompts")
    pedagogical = PedagogicalEngine(tutor, loader, repository, profile,
                                    settings.project_root / "prompts")
    session = pedagogical.start_session(
        tutor.start_session("default", lesson_id))

    print("\nIniciando aula...")
    print(
        f"Tema: {lesson_id}\nEtapa: {session.pedagogical_state.value.upper()}\n")
    print(pedagogical.generate_step_message(session, "Objetivo da aula"))

    while True:
        question = input(
            "\nMensagem, resposta ou comando ('exit', 'diagnose', 'advance', 'summary'): ").strip()
        if not question:
            continue
        normalized = question.lower()
        if normalized == "exit":
            tutor.finish_session(session)
            print("Session completed.")
            return
        if normalized == "diagnose":
            answer = input("Diagnóstico: ").strip()
            if answer:
                result = pedagogical.diagnose(session, answer)
                print(
                    f"\nDiagnóstico: score={result.score} / confidence={result.confidence} / recommendation={result.recommendation}")
            continue
        if normalized == "advance":
            try:
                session = pedagogical.advance_state(
                    session, LessonState.DIAGNOSE)
                print(
                    f"\nEtapa atual: {session.pedagogical_state.value.upper()}")
            except ValueError as exc:
                print(f"\n{exc}")
            continue
        if normalized in {"summary", "resumo"}:
            print("\n" + pedagogical.generate_step_message(session, "Resumo da sessão"))
            continue
        session = pedagogical.record_interaction(session, question)
        print("\n" + pedagogical.generate_step_message(session, question))


def _run_curriculum_command(command: str, argument: str, curriculum: object, adaptive: object, retention: object) -> None:
    """Run one offline curriculum query from the startup prompt."""
    from study_agent.curriculum.engine import CurriculumEngine
    from study_agent.learning.adaptive_learning import AdaptiveLearningEngine
    from study_agent.learning.retention import RetentionEngine

    if not isinstance(curriculum, CurriculumEngine) or not isinstance(adaptive, AdaptiveLearningEngine) or not isinstance(retention, RetentionEngine):
        return
    if command == "curriculum":
        print("\nLessons:")
        print("\n".join(curriculum.loader.list_lessons()))
        print("\nConcepts:")
        print("\n".join(node.name for node in curriculum.graph.nodes.values()))
    elif command == "subjects":
        print("\n".join(curriculum.list_subjects()))
    elif command == "topics":
        print("\n".join(curriculum.list_topics(argument or None)))
    elif command == "concept" and argument:
        node = curriculum.get_node(argument)
        print(f"\n{node.name}\nArea: {node.area}\nSubject: {node.subject}\nTopic: {node.topic}")
        prerequisites = ", ".join(item.name for item in curriculum.prerequisites(node.id))
        print("Prerequisites: " + (prerequisites or "none"))
    elif command == "prerequisites" and argument:
        print("\n".join(item.name for item in curriculum.prerequisites(argument, recursive=True)))
    elif command == "recommend":
        try:
            recommendation = adaptive.recommend_next("default", topic=argument or None)
            print(f"{recommendation.topic}: {recommendation.difficulty.value} - {recommendation.reason}")
        except ValueError as exc:
            print(str(exc))
    elif command in {"reviews", "due", "overdue"}:
        items = retention.reviews("default")
        if command == "due":
            items = [item for item in items if item.status.value in {"due", "overdue"}]
        elif command == "overdue":
            items = [item for item in items if item.status.value == "overdue"]
        for item in items:
            node = curriculum.get_node(item.state.knowledge_node_id)
            print(f"{node.name}: {item.status.value} ({item.overdue_duration})")
    elif command == "retention" and argument:
        node = curriculum.get_node(argument)
        state = retention.get("default", node.id)
        if state is None:
            print(f"{node.name}: no retention state")
            return
        item = retention.scheduler.classify(state)
        print(f"{node.name}\nReviews: {state.review_count}\nSuccesses: {state.successful_reviews}\nFailures: {state.failed_reviews}\nNext review: {state.next_review_at}\nState: {item.status.value}\nEstimated retention: {state.retention_score:.2f}")


if __name__ == "__main__":
    initialize()
    print("Study Agent initialized")
