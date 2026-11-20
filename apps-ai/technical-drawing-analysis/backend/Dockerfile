FROM ghcr.io/astral-sh/uv:0.8.22-python3.12-bookworm-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY backend/pyproject.toml ./pyproject.toml
COPY backend/src ./src

RUN uv pip install --system .

CMD ["python", "-m", "uvicorn", "technical_drawing_analysis.app:app", "--host", "0.0.0.0", "--port", "8000"]

