"""FastAPI application factory and CLI entry point."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import __version__
from .api import api
from .config import get_settings
from .security import SESSION_COOKIE

logger = logging.getLogger("aiobs_backend")

CSRF_HEADER = "x-requested-with"
CSRF_VALUE = "aiobs"
_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
# Login has no session yet; SDK ingest authenticates with per-project keys.
_CSRF_EXEMPT_PATHS = {"/api/v1/auth/login", "/api/v1/traces"}


async def _background_loop() -> None:
    """Periodically recompute analytics and evaluate alerts (plans §9-10)."""
    from .alerts import evaluate_alerts
    from .analytics import rollup_recent
    from .db import session_scope

    interval = max(1, get_settings().alert_interval_s)
    while True:
        try:
            with session_scope() as session:
                rollup_recent(session)
                created = evaluate_alerts(session)
                if created:
                    logger.info("background: %s alert(s) created", len(created))
        except Exception:  # never let the background loop die
            logger.exception("background rollup/alerts failed")
        await asyncio.sleep(interval)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    from . import db, seed

    db.create_all()
    if get_settings().seed_pricing:
        added = seed.seed_pricing()
        logger.info("seeded %s pricing rows", added)
    settings = get_settings()
    if settings.admin_email and settings.admin_password:
        seed.seed_admin(settings.admin_email, settings.admin_password)
    task = asyncio.create_task(_background_loop())
    yield
    task.cancel()


def create_app() -> FastAPI:
    app = FastAPI(
        title="AI Observability Platform API",
        version=__version__,
        lifespan=_lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def csrf_guard(request: Request, call_next):
        """Cookie-authenticated mutations must carry the custom CSRF header."""
        if (
            request.method in _MUTATING_METHODS
            and request.url.path.startswith("/api/v1")
            and request.url.path not in _CSRF_EXEMPT_PATHS
            and request.cookies.get(SESSION_COOKIE)
            and not request.headers.get("x-admin-key")
            and not request.headers.get("x-api-key")
            and request.headers.get(CSRF_HEADER) != CSRF_VALUE
        ):
            return JSONResponse(
                {"detail": "missing CSRF header"}, status_code=403
            )
        return await call_next(request)

    app.include_router(api)
    # Standard OTLP HTTP path for SDK exporters: POST /v1/traces
    from .api.routes.ingest import otlp_router

    app.include_router(otlp_router)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "version": __version__}

    return app


app = create_app()


def run() -> None:
    uvicorn.run(
        "aiobs_backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )


if __name__ == "__main__":
    run()