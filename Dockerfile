# syntax=docker/dockerfile:1

FROM ghcr.io/astral-sh/uv:python3.11-bookworm

WORKDIR /bot
ENV UV_COMPILE_BYTECODE=1
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY data/credentials.json data/postgres.json data/initial_cogs.json ./data/
COPY cogs/ cogs/
COPY bot.py .
CMD ["python", "-u", "bot.py"]
