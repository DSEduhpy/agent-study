# Study Agent VS Code Extension

This extension provides a compact Study Agent sidebar while keeping all learning decisions in the Python core.

## Setup

From the repository root:

```powershell
Set-Location extension
npm install
npm run typecheck
npm run compile
```

Open the repository in VS Code, press `F5`, and choose the Extension Development Host. Configure `studyAgent.pythonPath` when `python` is not the desired interpreter.

## Architecture

```text
VS Code Activity Bar / Webview
              |
        CoreClient (TypeScript)
              |
       JSON Lines over stdio
              |
       study_agent.application
              |
   Existing Python learning engines
              |
           SQLite
```

The client sends requests such as `{ "operation": "dashboard", "payload": {} }`. Responses contain `ok`, `requestId`, and either structured `data` or a sanitized `error` with a stable code. The Python process starts lazily and pending requests receive a disconnect error if it exits.

## Commands

- `Study Agent: Open Dashboard`
- `Study Agent: Start Study`
- `Study Agent: Ask Tutor`
- `Study Agent: Show Reviews`
- `Study Agent: Open Curriculum`

## Security

The extension never reads or stores API keys. Credentials remain in the Python environment and `.env` handling. The Webview uses a restrictive Content Security Policy with a nonce, has no remote scripts, and exchanges structured messages only. It does not execute shell commands or arbitrary code.

## Troubleshooting

- If the sidebar reports a disconnected core, check `studyAgent.pythonPath` and the `Study Agent` output channel.
- If AI-backed actions fail, configure the Python provider through the existing `.env` settings; dashboard and curriculum queries remain offline.
- Reopening VS Code reloads state from SQLite through the facade rather than from Webview memory.