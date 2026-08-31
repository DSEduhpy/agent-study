from pathlib import Path

import pytest

from study_agent.core.models import Exercise, ExerciseAttempt, KnowledgeNode, KnowledgeRelation, StudentProfile
from study_agent.curriculum.engine import CurriculumEngine
from study_agent.curriculum.graph import KnowledgeGraph
from study_agent.database.sqlite import SQLiteDatabase
from study_agent.learning.adaptive_learning import AdaptiveLearningEngine
from study_agent.learning.daily_goal import DailyGoalEngine
from study_agent.memory.repository import LearningRepository
from study_agent.learning.exercise_engine import ExerciseEngine, ExerciseEvaluator, ExerciseGenerator, ExerciseSelector
from study_agent.learning.pedagogy import PedagogicalEngine
from study_agent.learning.tutor import TutorEngine
from study_agent.ai.provider import AIProvider


class OfflineProvider(AIProvider):
    def generate(self, prompt: str, *, system: str | None = None) -> str:
        return '{"correct": true, "score": 90, "feedback": "Good", "confidence": 0.9}'

    def generate_structured(self, prompt: str, schema: type, *, system: str | None = None):
        raise NotImplementedError


def test_curriculum_engine_finds_aliases_and_prerequisites(tmp_path: Path) -> None:
    repository = LearningRepository(SQLiteDatabase(tmp_path / "curriculum.sqlite3"))
    engine = CurriculumEngine("curriculum", repository)

    matches = engine.find("left join")
    assert matches and matches[0].name == "JOIN"
    assert engine.find("chmod")[0].name == "File Permissions"
    prerequisites = {node.name for node in engine.prerequisites("Random Forest")}
    assert {"Decision Trees", "Overfitting", "Classification"} <= prerequisites
    assert repository.get_knowledge_node("random-forest") is not None


def test_graph_rejects_prerequisite_cycles() -> None:
    graph = KnowledgeGraph()
    graph.add_node(KnowledgeNode("a", "A"))
    graph.add_node(KnowledgeNode("b", "B"))
    graph.add_relation(KnowledgeRelation("b", "a", "prerequisite"))
    with pytest.raises(ValueError, match="cycle"):
        graph.add_relation(KnowledgeRelation("a", "b", "prerequisite"))


def test_adaptive_learning_prioritizes_weak_prerequisite(tmp_path: Path) -> None:
    repository = LearningRepository(SQLiteDatabase(tmp_path / "adaptive.sqlite3"))
    repository.save_student("student", StudentProfile("Test", 2, ("data_science",)))
    for exercise_id, topic in (("rf", "Random Forest"), ("overfit", "Overfitting"), ("trees", "Decision Trees")):
        repository.save_exercise(Exercise(exercise_id, "Data Science", topic, difficulty="medium", question="Q", expected_answer="A"))
    repository.save_attempt("student", ExerciseAttempt("rf", "A", True, 85))
    repository.save_attempt("student", ExerciseAttempt("overfit", "A", False, 43))
    repository.save_attempt("student", ExerciseAttempt("trees", "A", True, 85))

    curriculum = CurriculumEngine("curriculum", repository)
    recommendation = AdaptiveLearningEngine(repository, curriculum).recommend_next("student", topic="Random Forest")
    assert recommendation.topic == "Overfitting"
    assert "prerequisite" in recommendation.reason


def test_phase6_learning_flow_is_offline_and_persistent(tmp_path: Path) -> None:
    provider = OfflineProvider()
    profile = StudentProfile("Test", 1, ("data_science",))
    repository = LearningRepository(SQLiteDatabase(tmp_path / "flow.sqlite3"))
    repository.save_student("student", profile)
    curriculum = CurriculumEngine("curriculum", repository)
    adaptive = AdaptiveLearningEngine(repository, curriculum)
    exercise = Exercise("overfit-exercise", "Data Science", "Overfitting", difficulty="easy", question="What is overfitting?", expected_answer="Overfitting", explanation="", professional_context="")
    repository.save_exercise(exercise)
    repository.save_attempt("student", ExerciseAttempt("overfit-exercise", "Wrong", False, 43))
    recommendation = adaptive.recommend_next("student", topic="Random Forest")

    tutor = TutorEngine(curriculum.loader, provider, repository, profile, "prompts")
    pedagogy = PedagogicalEngine(tutor, curriculum.loader, repository, profile, "prompts")
    session = pedagogy.start_session(tutor.start_session("student", "data_science/sql/joins"))
    decision = pedagogy.make_decision(session, correct=False, confidence=0.4, misconception=recommendation.reason)
    exercise_engine = ExerciseEngine(ExerciseGenerator(provider), ExerciseSelector(repository), ExerciseEvaluator(provider), repository, pedagogy, DailyGoalEngine(repository, profile))
    evaluation, _ = exercise_engine.submit_answer(exercise, "Overfitting", student_id="student")

    assert recommendation.topic == "Overfitting"
    assert decision.action.value == "review"
    assert evaluation.correct is True
    assert repository.get_daily_goal("student") is not None
    assert repository.list_attempts("student")[-1]["correct"] == 1