"""Config resolution: explicit args override env vars (12-factor)."""

from __future__ import annotations

import pytest

from ai_observability._config import resolve_config

ENVS = [
    "AI_OBSERVABILITY_API_KEY",
    "AI_OBSERVABILITY_ENDPOINT",
    "AI_OBSERVABILITY_PROJECT_ID",
    "OTEL_SERVICE_NAME",
    "OTEL_SERVICE_VERSION",
    "OTEL_DEPLOYMENT_ENVIRONMENT",
]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in ENVS:
        monkeypatch.delenv(name, raising=False)


def test_defaults():
    config = resolve_config({})
    assert config.api_key is None
    assert config.endpoint == "http://localhost:6006"
    assert config.project_id is None
    assert config.service_name == "unknown_service"
    assert config.capture_prompts is False


def test_env_fallbacks(monkeypatch):
    monkeypatch.setenv("AI_OBSERVABILITY_API_KEY", "env-key")
    monkeypatch.setenv("AI_OBSERVABILITY_ENDPOINT", "http://env:6006")
    monkeypatch.setenv("AI_OBSERVABILITY_PROJECT_ID", "proj-env")
    monkeypatch.setenv("OTEL_SERVICE_NAME", "env-service")
    monkeypatch.setenv("OTEL_SERVICE_VERSION", "1.2.3")
    monkeypatch.setenv("OTEL_DEPLOYMENT_ENVIRONMENT", "staging")
    config = resolve_config({})
    assert config.api_key == "env-key"
    assert config.endpoint == "http://env:6006"
    assert config.project_id == "proj-env"
    assert config.service_name == "env-service"
    assert config.service_version == "1.2.3"
    assert config.deployment_environment == "staging"


def test_explicit_args_override_env(monkeypatch):
    monkeypatch.setenv("AI_OBSERVABILITY_API_KEY", "env-key")
    monkeypatch.setenv("AI_OBSERVABILITY_PROJECT_ID", "proj-env")
    config = resolve_config(
        {"api_key": "explicit-key", "project_id": "proj-explicit", "capture_prompts": True}
    )
    assert config.api_key == "explicit-key"
    assert config.project_id == "proj-explicit"
    assert config.capture_prompts is True


def test_empty_env_is_treated_as_unset(monkeypatch):
    monkeypatch.setenv("AI_OBSERVABILITY_API_KEY", "")
    monkeypatch.setenv("AI_OBSERVABILITY_ENDPOINT", "")
    config = resolve_config({})
    assert config.api_key is None
    assert config.endpoint == "http://localhost:6006"