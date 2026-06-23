FROM python:3.12-slim AS base

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=UTC

COPY pyproject.toml uv.lock ./

# ── production ────────────────────────────────────────────────────────────────
FROM base AS production

RUN uv sync --frozen --no-dev

COPY src/ ./src/
COPY config.yaml ./

CMD ["python", "src/main.py"]

# ── test ──────────────────────────────────────────────────────────────────────
FROM base AS test

RUN uv sync --frozen

COPY src/ ./src/
COPY tests/ ./tests/

CMD ["pytest", "-v"]
