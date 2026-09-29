"""Email/password sessions (ADR-0006): login, cookies, CSRF, revocation."""
from __future__ import annotations

from helpers import seed_user

CSRF = {"x-requested-with": "aiobs"}


def _login(client, email="u@x", password="hunter2"):
    return client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )


def test_login_me_logout(anon, session_factory):
    with session_factory() as session:
        seed_user(session, "u@x", password="hunter2")
        session.commit()

    resp = _login(anon)
    assert resp.status_code == 200
    assert resp.json()["user"]["email"] == "u@x"
    assert anon.cookies.get("aiobs_session")

    me = anon.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["roles"] == []
    # Sliding TTL: /me re-issues the cookie.
    assert "set-cookie" in {k.lower(): v for k, v in me.headers.items()}

    logout = anon.post("/api/v1/auth/logout", headers=CSRF)
    assert logout.status_code == 200
    assert anon.get("/api/v1/auth/me").status_code == 401


def test_login_rejects_bad_credentials(anon, session_factory):
    with session_factory() as session:
        seed_user(session, "u@x", password="hunter2")
        session.commit()
    assert _login(anon, password="wrong").status_code == 401
    assert _login(anon, email="nobody@x").status_code == 401


def test_cookie_flags_and_csrf_header(anon, session_factory):
    with session_factory() as session:
        seed_user(session, "u@x", password="hunter2")
        session.commit()
    resp = _login(anon)
    cookie_header = resp.headers["set-cookie"].lower()
    assert "httponly" in cookie_header
    assert "samesite=lax" in cookie_header
    # Cookie-authenticated mutations require the custom CSRF header.
    assert anon.post("/api/v1/auth/logout").status_code == 403
    assert anon.post("/api/v1/auth/logout", headers=CSRF).status_code == 200


def test_disable_revokes_session(anon, client, session_factory):
    with session_factory() as session:
        user, _ = seed_user(session, "u@x", password="hunter2")
        session.commit()
        user_id = user.id

    assert _login(anon).status_code == 200
    assert anon.get("/api/v1/auth/me").status_code == 200

    client.post(f"/api/v1/users/{user_id}/disable")
    assert anon.get("/api/v1/auth/me").status_code == 401

    client.post(f"/api/v1/users/{user_id}/enable")
    # Old cookie is stale even after re-enabling: token_version moved on.
    assert anon.get("/api/v1/auth/me").status_code == 401
    assert _login(anon).status_code == 200
