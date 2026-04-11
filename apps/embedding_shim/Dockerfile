FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim
WORKDIR /app
COPY apps/embedding_shim/pyproject.toml apps/embedding_shim/uv.lock ./
RUN uv sync --frozen --no-dev
COPY apps/embedding_shim/main.py ./main.py
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
