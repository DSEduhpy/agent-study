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

Content is data: lessons live under `curriculum/<area>/<topic>/*.md`, while application logic stays in `src`.

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

## Changing AI providers

Code depending on AI should type against `AIProvider`, not `OpenAIProvider`. A future adapter implements `generate` and `generate_structured`; `chat` is available on the interface. OpenAI construction is lazy and requires `AI_API_KEY` and `AI_MODEL` from the environment, so missing credentials never appear in code, YAML, tests, logs, or errors.

## Decisions and next steps

The design favors standard-library dataclasses, `pathlib`, SQLite, and one provider boundary. Telegram, VS Code UI, scheduling, web/WhatsApp, RAG, embeddings, authentication, exercise generation, and controlled lab execution are intentionally deferred. The next recommended step is the Exercise Engine, using the existing `Exercise`, `ExerciseAttempt`, and evaluation contracts without coupling them to the tutor or provider adapter.
