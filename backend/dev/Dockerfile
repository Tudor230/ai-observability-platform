# Build context must be the repo root (contains shared/ + backend/).
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

COPY shared/aiobs_contracts /app/shared/aiobs_contracts
COPY backend/pyproject.toml backend/uv.lock backend/README.md /app/backend/
COPY backend/src /app/backend/src
COPY backend/dev /app/backend/dev
COPY backend/alembic.ini /app/backend/alembic.ini
COPY backend/alembic /app/backend/alembic
RUN cd /app/backend && uv sync --frozen --no-dev

WORKDIR /app/backend
# The image is synced with `--no-dev`; keep `uv run` from re-resolving and
# re-installing the dev group (ruff/mypy/pytest) on every container start.
# Run dev tooling against the host venv, or override with `UV_NO_DEV=0`.
ENV UV_NO_DEV=1
EXPOSE 8000
# Schema is owned by Alembic: migrate before starting the API.
CMD ["sh", "-c", "uv run --frozen alembic upgrade head && uv run --frozen aiobs-backend"]
