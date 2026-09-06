"""SDK configuration: init() argument + environment resolution.

12-factor: explicit ``init()`` arguments override environment variables.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Optional

API_KEY_ENV = "AI_OBSERVABILITY_API_KEY"
ENDPOINT_ENV = "AI_OBSERVABILITY_ENDPOINT"
PROJECT_ID_ENV = "AI_OBSERVABILITY_PROJECT_ID"
DEFAULT_ENDPOINT = "http://localhost:6006"
DEFAULT_SERVICE_NAME = "unknown_service"


@dataclass(frozen=True)
class Config:
    api_key: Optional[str] = None
    endpoint: Optional[str] = None
    project_id: Optional[str] = None
    service_name: str = DEFAULT_SERVICE_NAME
    service_version: Optional[str] = None
    deployment_environment: Optional[str] = None
    capture_prompts: bool = False

    @property
    def capture_enabled(self) -> bool:
        return self.capture_prompts


def _env(name: str) -> Optional[str]:
    value = os.environ.get(name)
    return value if value else None


def resolve_config(kwargs: dict[str, Any]) -> Config:
    """Resolve a Config from explicit init() kwargs over env-var fallbacks."""
    api_key = kwargs.get("api_key") or _env(API_KEY_ENV)
    endpoint = kwargs.get("endpoint") or _env(ENDPOINT_ENV) or DEFAULT_ENDPOINT
    project_id = kwargs.get("project_id") or _env(PROJECT_ID_ENV)
    service_name = (
        kwargs.get("service_name")
        or _env("OTEL_SERVICE_NAME")
        or DEFAULT_SERVICE_NAME
    )
    service_version = kwargs.get("service_version") or _env("OTEL_SERVICE_VERSION")
    deployment_environment = kwargs.get("deployment_environment") or _env(
        "OTEL_DEPLOYMENT_ENVIRONMENT"
    )
    capture_prompts = bool(kwargs.get("capture_prompts", False))
    return Config(
        api_key=api_key,
        endpoint=endpoint,
        project_id=project_id,
        service_name=service_name,
        service_version=service_version,
        deployment_environment=deployment_environment,
        capture_prompts=capture_prompts,
    )