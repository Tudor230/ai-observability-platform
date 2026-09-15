"""RBAC identities (F06/F16): user API keys and role-gated reads."""
from __future__ import annotations

from aiobs_backend.config import get_settings

ADMIN = {"x-admin-key": "admin"}


def _enable_read_auth(monkeypatch, key: str = "service-key") -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("AIOBS_READ_API_KEY", key)
    get_settings.cache_clear()


def _disable_read_auth(monkeypatch) -> None:
    monkeypatch.delenv("AIOBS_READ_API_KEY", raising=False)
    get_settings.cache_clear()


def test_users_require_admin(client):
    assert client.post("/api/v1/users", json={"email": "x@y.z"}).status_code == 401


def test_role_gated_reads(client, project, monkeypatch):
    _enable_read_auth(monkeypatch)
    try:
        eng = client.post(
            "/api/v1/users", json={"email": "eng@x", "role": "engineer"}, headers=ADMIN
        ).json()
        fin = client.post(
            "/api/v1/users", json={"email": "fin@x", "role": "finance"}, headers=ADMIN
        ).json()

        assert client.get("/api/v1/executions").status_code == 401
        assert (
            client.get("/api/v1/executions", headers={"x-api-key": "service-key"}).status_code
            == 200
        )
        assert (
            client.get("/api/v1/executions", headers={"x-api-key": eng["api_key"]}).status_code
            == 200
        )
        # Engineer cannot read cost views; finance cannot read trace detail.
        assert (
            client.get("/api/v1/costs", headers={"x-api-key": eng["api_key"]}).status_code
            == 403
        )
        assert (
            client.get("/api/v1/costs", headers={"x-api-key": fin["api_key"]}).status_code
            == 200
        )
        assert (
            client.get("/api/v1/executions", headers={"x-api-key": fin["api_key"]}).status_code
            == 403
        )
        # Shared views accept any authenticated role.
        assert (
            client.get("/api/v1/overview", headers={"x-api-key": eng["api_key"]}).status_code
            == 200
        )

        client.post(f"/api/v1/users/{eng['id']}/disable", headers=ADMIN)
        assert (
            client.get("/api/v1/executions", headers={"x-api-key": eng["api_key"]}).status_code
            == 401
        )

        users = client.get("/api/v1/users", headers=ADMIN).json()
        assert users["total"] == 2
    finally:
        _disable_read_auth(monkeypatch)


def test_reads_stay_open_without_read_auth(client, project):
    assert client.get("/api/v1/executions").status_code == 200
