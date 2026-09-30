"""ADR-0008: the key is the ingest identity; project_id is a deprecated routing hint."""

from __future__ import annotations

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

import ai_observability
from ai_observability._config import Config
from ai_observability._tracing import (
    PROJECT_RESOURCE_ATTR,
    build_headers,
    build_resource,
)


def _config(**overrides) -> Config:
    base: dict = {"api_key": "aiobs_secret", "project_id": "proj-1"}
    base.update(overrides)
    return Config(**base)


def test_project_id_sets_header_and_resource_attr():
    config = _config()
    assert build_headers(config) == {
        "authorization": "Bearer aiobs_secret",
        "x-project-name": "proj-1",
    }
    assert build_resource(config).attributes[PROJECT_RESOURCE_ATTR] == "proj-1"


def test_key_only_sends_authorization_only():
    config = _config(project_id=None)
    assert build_headers(config) == {"authorization": "Bearer aiobs_secret"}
    assert PROJECT_RESOURCE_ATTR not in build_resource(config).attributes


def test_init_warns_when_project_id_is_configured(monkeypatch):
    monkeypatch.setattr(ai_observability, "_PROJECT_ID_DEPRECATION_WARNED", False)
    with pytest.warns(DeprecationWarning, match="project_id"):
        ai_observability.init(
            api_key="k", project_id="p1", _final_exporter=InMemorySpanExporter()
        )


def test_init_warns_for_env_project_id(monkeypatch):
    monkeypatch.setenv("AI_OBSERVABILITY_PROJECT_ID", "env-proj")
    monkeypatch.setattr(ai_observability, "_PROJECT_ID_DEPRECATION_WARNED", False)
    with pytest.warns(DeprecationWarning, match="AI_OBSERVABILITY_PROJECT_ID"):
        ai_observability.init(api_key="k", _final_exporter=InMemorySpanExporter())


def test_init_key_only_does_not_warn(monkeypatch, recwarn):
    monkeypatch.delenv("AI_OBSERVABILITY_PROJECT_ID", raising=False)
    monkeypatch.setattr(ai_observability, "_PROJECT_ID_DEPRECATION_WARNED", False)
    ai_observability.init(api_key="k", _final_exporter=InMemorySpanExporter())
    assert not [
        w for w in recwarn if issubclass(w.category, DeprecationWarning)
    ]


def test_key_only_root_has_no_sdk_project_id(monkeypatch):
    monkeypatch.delenv("AI_OBSERVABILITY_PROJECT_ID", raising=False)
    tail = InMemorySpanExporter()
    ai_observability.init(api_key="k", _final_exporter=tail)
    with ai_observability.workflow(name="wf", workflow_id="w-1"):
        pass
    assert ai_observability.flush(timeout_millis=2000) is True
    span = tail.get_finished_spans()[0]
    assert "sdk.project_id" not in (span.attributes or {})
