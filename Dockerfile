FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-install-project --no-dev

COPY src/ ./src/
COPY config/ ./config/
COPY static/ ./static/

RUN uv sync --frozen --no-dev

EXPOSE 8080

CMD ["uvicorn", "agentic_cart.api:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
