# Study Agent

Study Agent is a personal, extensible AI-assisted learning system. Cybersecurity and white-hat practice are the priority; data science is a secondary area. The current version provides a curriculum-backed tutor flow with local study-session memory.

## Architecture

- `src/study_agent/config`: environment and YAML profile loading.
- `src/study_agent/core`: provider-independent domain models and exceptions.
- `src/study_agent/curriculum`: safe Markdown lesson discovery and loading.
- `src/study_agent/learning`: small learning use cases.
- `src/study_agent/ai`: `AIProvider` interface and optional OpenAI adapter.
- `src/study_agent/database` and `src/study_agent/memory`: idempotent SQLite schema and centralized persistence.
- `src/study_agent/learning/tutor.py`: `TutorEngine` and `TutorContext`, coordinating lessons, prompts, provider calls, and sessions.
- `src/study_agent/curriculum/engine.py`: `CurriculumEngine`, indexing curriculum metadata and graph queries.
- `src/study_agent/curriculum/graph.py`: `KnowledgeGraph`, an in-memory graph with prerequisite cycle protection.

Content is data: lessons live under `curriculum/<area>/<topic>/*.md`, while application logic stays in `src`.

### Architecture

```text
Markdown lessons + knowledge.yaml
		|
	CurriculumLoader
		|
	CurriculumEngine
		|
	KnowledgeGraph <--> SQLite knowledge_nodes / knowledge_relations
		|
	AdaptiveLearningEngine
		|
	PedagogicalEngine -> ExerciseEngine -> LearningRepository
		|
	    TutorEngine
```

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Copy `.env.example` to `.env` when configuring an AI provider. Put real credentials only in `.env`; it is ignored by Git. `AI_MODEL` is intentionally empty until you choose a model available to your account. The API adapter is not needed for offline tests.

## Run

From the project root:

```powershell
$env:PYTHONPATH="src"
python -m study_agent
```

The CLI lists available lessons, starts a session, generates an explanation, accepts follow-up questions, and completes the session when `exit` is entered. Studying requires a configured provider (`AI_API_KEY` and an account-supported `AI_MODEL`). Listing and the core tests remain offline.

The non-interactive startup check is also available with `python -m study_agent.main`.

## Tests

```powershell
$env:PYTHONPATH="src"
pytest
```

The standard suite does not call an external AI API.

## Pedagogical Engine

The pedagogical layer is the teaching strategy runtime. It does not replace the curriculum, the tutor, or the provider boundary; it coordinates how a lesson is taught, in what order, and when the system should slow down, revisit a concept, or advance.

The engine is intentionally generic: the same flow works for SQL, Python, cybersecurity, or statistics because the logic is based on teaching stages and adaptive decisions rather than on a single domain.

### State machine

The teaching flow uses a typed enum and explicit transitions:

- `ORIENT`: explain the target outcome and why it matters.
- `DIAGNOSE`: check prior knowledge with a short, low-friction prompt.
- `INTRODUCE`: present the core concept in plain terms.
- `EXPLAIN`: cover the technical rules and details.
- `MENTAL_MODEL`: connect the idea to a mental model and a concrete interpretation.
- `DEMONSTRATE`: show a worked example with explanation.
- `GUIDED_PRACTICE`: guide the student through a solution path.
- `INDEPENDENT_PRACTICE`: let the student attempt the task with fewer hints.
- `CHECK`: evaluate comprehension beyond memorization.
- `PROFESSIONAL_APPLICATION`: connect the concept to realistic work scenarios.
- `REVIEW`: re-enter an earlier stage when the student struggles.
- `BLOCKED`: indicate a prerequisite gap that needs a foundational concept first.
- `MASTERED`: only reached after evidence supports sustained understanding.

The engine validates transitions instead of allowing an arbitrary jump.

### How a lesson is conducted

A lesson is taught as a progressive sequence rather than as a single AI answer:

1. orient the student to the objective;
2. diagnose the current level;
3. introduce the concept;
4. explain the technical behavior;
5. build a mental model;
6. demonstrate with code or procedure;
7. guide practice;
8. let the student attempt it independently;
9. check understanding;
10. connect it to professional work;
11. advance only when the evidence supports it.

If the learner struggles, the system shifts to `REVIEW` or `BLOCKED` and changes strategy instead of repeating the same text.

### Adaptive decisions

The engine records `KnowledgeCheckResult` and `PedagogicalDecision` objects. It evaluates factors like confidence, correctness, reasoning quality, and misconceptions, then chooses actions such as `ADVANCE`, `REVIEW`, `RETEACH`, `SIMPLIFY`, or `PRACTICE`.

A correct answer does not automatically mean mastery; the system distinguishes between a lucky answer and durable understanding.

### Persistence

The pedagogical state is stored in the same SQLite-backed repository as the rest of the session data. `StudySession` persists:

- current state;
- objective;
- diagnosis;
- knowledge checks;
- misconceptions;
- difficulty level;
- interaction history.

This allows a session to pause and resume without relying only on in-memory state.

### Practical usage

```python
from study_agent.config.settings import load_student_profile
from study_agent.curriculum.loader import CurriculumLoader
from study_agent.database.sqlite import SQLiteDatabase
from study_agent.learning.pedagogy import PedagogicalEngine
from study_agent.learning.tutor import TutorEngine
from study_agent.memory.repository import LearningRepository

profile = load_student_profile(Path("config/profile.yaml"))
loader = CurriculumLoader("curriculum")
repository = LearningRepository(SQLiteDatabase("data/study_agent.sqlite3"))
tutor = TutorEngine(loader, provider, repository, profile, "prompts")
pedagogy = PedagogicalEngine(tutor, loader, repository, profile, "prompts")

session = tutor.start_session("student-1", "data_science/sql/joins")
session = pedagogy.start_session(session)
session = pedagogy.advance_state(session, LessonState.DIAGNOSE)
```

## Tutor flow

`TutorEngine.start_session` loads a safe Markdown lesson, saves the student, lesson, and active session, and returns a typed `StudySession`. `explain` and `ask` build a `TutorContext` containing the profile, current lesson, objective, preferences, and interaction count before calling only the `AIProvider` interface. `ask(..., socratic=True)` requests guided reasoning rather than an immediate solution. `finish_session` marks the session completed and persists its end time and interaction history.

Example programmatic use:

```python
session = tutor.start_session("student-1", "cybersecurity/linux/permissions")
answer = tutor.explain(session)
answer = tutor.ask(session, "I do not understand chmod 755.")
tutor.finish_session(session)
```

## Add a lesson

Create a Markdown file such as `curriculum/cybersecurity/networking/dns.md` with an H1 title. The loader derives the area and topic from its relative path and returns the Markdown as content. Paths are resolved under `curriculum` and traversal or absolute paths are rejected.

## Memory

`SQLiteDatabase` owns schema initialization. `LearningRepository` is the only current SQL boundary and stores students, lessons, exercises, attempts, study sessions, progress, and mistakes. Tables use foreign keys, constraints, timestamps, and indexes where useful.

## Daily Goal and Adaptive Learning

`DailyGoalEngine` stores one exercise target per student and calendar day. It can use `StudentProfile.daily_goal` as the default, reports remaining work and capped progress, and persists updates in the `daily_goals` table. `ExerciseEngine` can update the goal automatically when constructed with a `DailyGoalEngine`.

`AdaptiveLearningEngine` uses the persisted exercise history to recommend the next topic, difficulty, and exercise type. It prioritizes the topic with the lowest average score, lowers difficulty after weak evidence, keeps a moderate challenge while performance develops, and increases difficulty after consistent strong performance. The recommendation is deterministic, explainable, and does not call an external AI provider.

Example:

```python
from study_agent.learning.adaptive_learning import AdaptiveLearningEngine
from study_agent.learning.daily_goal import DailyGoalEngine

daily_goal = DailyGoalEngine(repository, profile)
goal = daily_goal.start_day("student-1")
recommendation = AdaptiveLearningEngine(repository).recommend_next("student-1")
```

## Curriculum Engine and Knowledge Graph

`CurriculumEngine` preserves `CurriculumLoader` for lesson content and adds a structured index in `curriculum/knowledge.yaml`. `KnowledgeNode` distinguishes area, subject, module, topic, concept, and skill through its `type` and metadata fields. Aliases make searches such as `left join`, `LEFT JOIN`, and `left outer join` resolve to the same node.

Prerequisite edges point from a node to what it requires. The graph supports direct and recursive prerequisites, dependents, related nodes, and next concepts. Adding a prerequisite that would create a cycle is rejected. The SQLite representation is an index and persistence boundary, not a separate graph service.

The CLI accepts offline queries at startup: `curriculum`, `subjects`, `topics`, `concept JOIN`, `prerequisites INNER JOIN`, and `recommend`. No external provider is needed for curriculum or graph queries.

## Retention and Spaced Repetition

`RetentionEngine` schedules reviews for `KnowledgeNode` instances, not for individual exercises. A `RetentionState` keeps the approximate stability, retrievability, review counters, and last/next timestamps for one student and concept. `ReviewHistory` is append-only, so each result remains available for later analysis.

`ReviewScheduler` classifies states as `DUE`, `UPCOMING`, `OVERDUE`, or `MASTERED`. `OVERDUE` means that the scheduled timestamp has passed; it does not mean the concept was forgotten. A small `Clock` boundary makes temporal behavior deterministic in tests.

The initial `SimpleRetentionAlgorithm` is deliberately replaceable and deterministic. It increases the interval after success, keeps it stable after a partial result, reduces it after failure, and applies centralized bounds from `config/retention.yaml`. This is a scheduling heuristic, not a scientific measurement of human memory, and the retention score is only an internal estimate.

The responsibilities remain separate:

```text
RetentionEngine       -> when to review
AdaptiveLearningEngine -> what to prioritize
PedagogicalEngine     -> how and when to teach
ExerciseEngine        -> which practice to apply
DailyGoalEngine       -> how much to practice
```

The logical CLI queries `reviews`, `due`, `overdue`, and `retention JOIN` work without an external AI provider. A review can be connected to an exercise submission by passing its explicit `knowledge_node_id` to `ExerciseEngine.submit_answer`.

## Changing AI providers

Code depending on AI should type against `AIProvider`, not `OpenAIProvider`. A future adapter implements `generate` and `generate_structured`; `chat` is available on the interface. OpenAI construction is lazy and requires `AI_API_KEY` and `AI_MODEL` from the environment, so missing credentials never appear in code, YAML, tests, logs, or errors.

## Decisions and next steps

The design favors standard-library dataclasses, `pathlib`, SQLite, and one provider boundary. Telegram, WhatsApp, scheduling, web, RAG, embeddings, authentication, and controlled lab execution remain intentionally deferred.

## VS Code Study Interface

The first VS Code interface lives under `extension/` and uses the official VS Code Extension API with TypeScript. Its Activity Bar view is a presentation layer over the Python core; it does not duplicate pedagogical, adaptive, retention, curriculum, exercise, or persistence logic.

Communication uses a local Python subprocess and JSON Lines over stdio. `CoreClient` adds request IDs and disconnect handling. `StudyAgentApplication` composes the existing engines and returns structured dashboard, curriculum, review, concept, lesson, tutor, exercise, and evaluation payloads. See [extension/README.md](extension/README.md) for setup, commands, security, and troubleshooting.
