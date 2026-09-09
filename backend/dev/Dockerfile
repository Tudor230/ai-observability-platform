# Build context must be the repo root (contains shared/ + backend/).
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

COPY shared/aiobs_contracts /app/shared/aiobs_contracts
COPY backend/pyproject.toml backend/uv.lock backend/README.md /app/backend/
COPY backend/src /app/backend/src
COPY backend/dev /app/backend/dev
RUN cd /app/backend && uv sync --frozen --no-dev

WORKDIR /app/backend
EXPOSE 8000
CMD ["uv", "run", "aiobs-backend"]