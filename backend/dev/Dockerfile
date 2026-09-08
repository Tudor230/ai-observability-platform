FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY src ./src
COPY dev ./dev

EXPOSE 8000
CMD ["uv", "run", "aiobs-backend"]
