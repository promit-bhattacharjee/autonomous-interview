# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:0.6.5-python3.12-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Copy dependency definition
COPY pyproject.toml /app/

# Install dependencies
RUN --mount=type=cache,target=/root/.cache/uv \
    uv venv && \
    uv pip install --no-cache-dir -r pyproject.toml

# Copy project code
COPY . /app/

# Minimal runtime stage
FROM python:3.12-slim-bookworm

WORKDIR /app

# Copy installed venv and application
COPY --from=builder /app /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

CMD ["python", "-m", "src.agent.worker", "start"]
