"""KPI gate safety guard (F03): never drop a non-disposable database."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "kpi_gate.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("kpi_gate_script", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://postgres:postgres@localhost:5432/aiobs_test",
        "postgresql+psycopg://postgres:postgres@localhost:5432/aiobs_kpi",
    ],
)
def test_guard_allows_disposable_names(monkeypatch, url):
    monkeypatch.delenv("AIOBS_KPI_ALLOW_RESET", raising=False)
    _load_script()._assert_disposable(url)


def test_guard_refuses_live_database(monkeypatch):
    monkeypatch.delenv("AIOBS_KPI_ALLOW_RESET", raising=False)
    with pytest.raises(SystemExit):
        _load_script()._assert_disposable(
            "postgresql+psycopg://postgres:postgres@localhost:5432/aiobs"
        )


def test_guard_allows_explicit_override(monkeypatch):
    monkeypatch.setenv("AIOBS_KPI_ALLOW_RESET", "1")
    _load_script()._assert_disposable(
        "postgresql+psycopg://postgres:postgres@localhost:5432/aiobs"
    )
