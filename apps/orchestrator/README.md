# Orchestrator

FastAPI service that keeps the `gpthub-prod` runtime path stable:

`Open WebUI -> orchestrator -> LiteLLM -> MWS`

## Local Dev

```bash
uv sync --extra dev
uv run uvicorn gpthub_orchestrator.main:app --host 0.0.0.0 --port 8000 --reload
```

The preserved test suite is intentionally focused on the runtime spine: routing, prompt handling, health, fallback, and mixed-input ingest helpers.

## Tests

```bash
uv run pytest
```
