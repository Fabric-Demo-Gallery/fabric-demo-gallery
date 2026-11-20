FROM ghcr.io/astral-sh/uv:0.8.22-python3.12-bookworm-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/src ./src
RUN uv sync --frozen --no-dev --no-editable

CMD ["/app/.venv/bin/python", "-m", "uvicorn", "delivery_note_extraction.app:app", "--host", "0.0.0.0", "--port", "8000"]
