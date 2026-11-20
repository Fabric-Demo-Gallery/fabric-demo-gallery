FROM ghcr.io/astral-sh/uv:0.8.22-python3.12-bookworm-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src
ENV AGENT_INSTRUCTIONS_DIR=/app/agent-instructions

WORKDIR /app

COPY backend/pyproject.toml backend/uv.lock ./
COPY backend/src ./src
COPY agent-instructions ./agent-instructions

RUN uv pip install --system .

EXPOSE 8138
CMD ["python", "-m", "uvicorn", "demand_portfolio_planning.app:app", "--host", "0.0.0.0", "--port", "8138"]
