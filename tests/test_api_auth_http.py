"""Authentication and authorization tests for HTTP endpoints."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
import pytest
from starlette.testclient import TestClient

from kavach_api.app import create_app
from kavach_api.security import create_token, hash_password
from kavach_api.settings import Settings


@pytest.fixture
def test_setup(tmp_path: Path):
    """Setup app with fast PBKDF2 iterations and pre-created users."""
    runtime_dir = tmp_path / "runtime"
    settings = Settings(
        runtime_dir=runtime_dir,
        pbkdf2_iterations=1000,
        login_fail_limit=5,
        login_fail_window_seconds=300,
    )
    app = create_app(settings)

    with TestClient(app) as client:
        # Create users for each role directly in store
        user_store = app.state.user_store
        user_store.create_user("admin_user", "AdminSecret123!", "admin")
        user_store.create_user("analyst_user", "AnalystSecret123!", "analyst")
        user_store.create_user("viewer_user", "ViewerSecret123!", "viewer")

        # Create tokens
        secret = app.state.secret
        tokens = {
            "admin": create_token(secret, "admin_user", "admin", 3600),
            "analyst": create_token(secret, "analyst_user", "analyst", 3600),
            "viewer": create_token(secret, "viewer_user", "viewer", 3600),
        }

        yield {
            "app": app,
            "client": client,
            "settings": settings,
            "tokens": tokens,
            "user_store": user_store,
        }


def test_health_public_and_no_paths(test_setup):
    """GET /api/health is public, returns 200, and contains no path-like strings."""
    client: TestClient = test_setup["client"]
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert "queue_length" in data
    assert "model_loaded" in data

    # Check for path-like substrings
    raw_str = resp.text.lower()
    assert "/" not in data.get("version", "")
    assert "\\" not in raw_str
    assert "c:" not in raw_str
    assert "/home" not in raw_str
    assert "/users" not in raw_str


def test_protected_routes_reject_unauthenticated(test_setup):
    """No token returns 401 on every protected route."""
    client: TestClient = test_setup["client"]
    app = test_setup["app"]

    # Iterate over application routes
    for route in app.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", set())
        if not path or not path.startswith("/api"):
            continue
        if path in ("/api/health", "/api/auth/login"):
            continue

        method = next(iter(methods)) if methods else "GET"
        resp = client.request(method, path)
        assert resp.status_code == 401, f"Route {method} {path} did not reject unauthenticated request"
        body = resp.json()
        assert "error" in body
        assert body["error"]["code"] == "unauthorized"


def test_viewer_cannot_call_admin_or_analyst_routes(test_setup):
    """Viewer token returns 403 on admin routes."""
    client: TestClient = test_setup["client"]
    viewer_token = test_setup["tokens"]["viewer"]
    headers = {"Authorization": f"Bearer {viewer_token}"}

    # Admin routes
    resp_create = client.post(
        "/api/admin/users",
        headers=headers,
        json={"username": "newuser", "password": "Password123!", "role": "viewer"},
    )
    assert resp_create.status_code == 403
    assert resp_create.json()["error"]["code"] == "forbidden"

    resp_audit = client.get("/api/admin/audit", headers=headers)
    assert resp_audit.status_code == 403
    assert resp_audit.json()["error"]["code"] == "forbidden"

    resp_verify = client.get("/api/admin/audit/verify", headers=headers)
    assert resp_verify.status_code == 403
    assert resp_verify.json()["error"]["code"] == "forbidden"


def test_login_success_and_failures(test_setup):
    """Login succeeds with correct password, fails on wrong, trips limiter on 6th."""
    client: TestClient = test_setup["client"]

    # 1. Successful login
    resp = client.post(
        "/api/auth/login",
        json={"username": "viewer_user", "password": "ViewerSecret123!"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["role"] == "viewer"
    assert data["username"] == "viewer_user"

    # 2. Wrong passwords (1 to 5)
    for _ in range(5):
        resp_fail = client.post(
            "/api/auth/login",
            json={"username": "viewer_user", "password": "WrongPassword!"},
        )
        assert resp_fail.status_code == 401
        assert resp_fail.json()["error"]["code"] == "unauthorized"

    # 3. 6th failed attempt -> 429 Too Many Requests with Retry-After header
    resp_limit = client.post(
        "/api/auth/login",
        json={"username": "viewer_user", "password": "WrongPassword!"},
    )
    assert resp_limit.status_code == 429
    assert resp_limit.json()["error"]["code"] == "too_many_requests"
    assert "retry-after" in resp_limit.headers


def test_token_for_deleted_user_rejected(test_setup):
    """Token for a deleted user is rejected with 401."""
    client: TestClient = test_setup["client"]
    app = test_setup["app"]
    secret = app.state.secret

    # Create temporary user
    app.state.user_store.create_user("temp_user", "TempPassword123!", "viewer")
    token = create_token(secret, "temp_user", "viewer", 3600)

    # Verify token works
    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200

    # Delete user from store
    users_file = test_setup["settings"].runtime_dir / "users.json"
    users = json.loads(users_file.read_text(encoding="utf-8"))
    del users["temp_user"]
    users_file.write_text(json.dumps(users), encoding="utf-8")

    # Accessing with deleted user token returns 401
    resp_deleted = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp_deleted.status_code == 401
    assert resp_deleted.json()["error"]["code"] == "unauthorized"


def test_admin_create_user_and_audit_verification(test_setup):
    """Admin creates user, audit chain logs entries and verify endpoint returns ok."""
    client: TestClient = test_setup["client"]
    admin_token = test_setup["tokens"]["admin"]
    headers = {"Authorization": f"Bearer {admin_token}"}

    # Admin creates user
    resp_create = client.post(
        "/api/admin/users",
        headers=headers,
        json={"username": "brand_new_analyst", "password": "BrandNewSecret123!", "role": "analyst"},
    )
    assert resp_create.status_code == 201
    assert resp_create.json()["username"] == "brand_new_analyst"

    # Read audit log
    resp_audit = client.get("/api/admin/audit?limit=20", headers=headers)
    assert resp_audit.status_code == 200
    entries = resp_audit.json()
    assert len(entries) > 0
    assert any(e["action"] == "user_created" for e in entries)

    # Verify audit chain
    resp_verify = client.get("/api/admin/audit/verify", headers=headers)
    assert resp_verify.status_code == 200
    v_data = resp_verify.json()
    assert v_data["ok"] is True
    assert v_data["first_bad_index"] is None
    assert v_data["entries"] >= len(entries)
