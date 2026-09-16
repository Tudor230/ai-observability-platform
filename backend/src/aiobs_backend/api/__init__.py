"""Platform API package: assemble all routers."""
from __future__ import annotations

from fastapi import APIRouter

from .routes import (
    agents,
    alerts,
    budgets,
    clients,
    costs,
    executions,
    ingest,
    maintenance,
    metrics,
    overview,
    pricing,
    projects,
    users,
    workflows,
)

api = APIRouter(prefix="/api/v1")

for module in (
    agents,
    alerts,
    budgets,
    clients,
    costs,
    executions,
    ingest,
    maintenance,
    metrics,
    overview,
    pricing,
    projects,
    users,
    workflows,
):
    api.include_router(module.router)