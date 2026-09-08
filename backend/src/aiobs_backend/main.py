"""FastAPI application factory and CLI entry point."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .api import api
from .config import get_settings

logger = logging.getLogger("aiobs_backend")


@asynccontextmanager
async def _lifespan(app: FastAPI):
    from . import db, seed

    db.create_all()
    if get_settings().seed_pricing:
        added = seed.seed_pricing()
        logger.info("seeded %s pricing rows", added)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="AI Observability Platform API",
        version=__version__,
        lifespan=_lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api)

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