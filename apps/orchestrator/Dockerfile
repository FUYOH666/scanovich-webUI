FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

COPY apps/orchestrator/pyproject.toml apps/orchestrator/uv.lock apps/orchestrator/README.md ./
COPY apps/orchestrator/gpthub_orchestrator ./gpthub_orchestrator

RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

CMD ["uvicorn", "gpthub_orchestrator.main:app", "--host", "0.0.0.0", "--port", "8000"]
