"""Tests for case deletion endpoint DELETE /cases/{case_id}."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
import pytest

from kavach_api.app import create_app
from kavach_api.security import create_token
from kavach_api.settings import Settings
from kavach_api.storage import CaseNotFoundError


@pytest.fixture
def delete_app_setup(tmp_path: Path):
    """Fixture providing FastAPI test client and authenticated admin/analyst/viewer tokens."""
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)

    settings = Settings(
        runtime_dir=runtime_dir,
        pbkdf2_iterations=1000,
        jwt_ttl_minutes=60,
        max_upload_bytes=10 * 1024 * 1024,
        max_fir_chars=5000,
        max_csv_rows=50000,
        login_fail_limit=5,
        login_fail_window_seconds=300,
    )

    app = create_app(settings=settings)
    user_store = app.state.user_store
    user_store.create_user("admin_user", "AdminSecret123!", "admin")
    user_store.create_user("analyst_user", "AnalystSecret123!", "analyst")
    user_store.create_user("viewer_user", "ViewerSecret123!", "viewer")

    admin_token = create_token(
        secret=app.state.secret,
        username="admin_user",
        role="admin",
        ttl_seconds=3600,
    )
    analyst_token = create_token(
        secret=app.state.secret,
        username="analyst_user",
        role="analyst",
        ttl_seconds=3600,
    )
    viewer_token = create_token(
        secret=app.state.secret,
        username="viewer_user",
        role="viewer",
        ttl_seconds=3600,
    )

    client = TestClient(app)

    yield {
        "app": app,
        "client": client,
        "store": app.state.store,
        "job_store": app.state.job_store,
        "audit_log": app.state.audit_log,
        "admin_headers": {"Authorization": f"Bearer {admin_token}"},
        "analyst_headers": {"Authorization": f"Bearer {analyst_token}"},
        "viewer_headers": {"Authorization": f"Bearer {viewer_token}"},
        "settings": settings,
    }


def test_delete_case_admin_allowed_and_files_gone(delete_app_setup):
    """Admin is permitted to delete a case; case files and directory are removed."""
    client: TestClient = delete_app_setup["client"]
    store = delete_app_setup["store"]
    headers = delete_app_setup["admin_headers"]

    # Create case
    case = store.create_case("Case Alpha", "analyst_user")
    cid = case["case_id"]
    cdir = store.case_dir(cid)
    assert cdir.is_dir()
    assert (cdir / "case.json").is_file()

    # Admin deletes case
    resp = client.delete(f"/api/cases/{cid}", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["deleted"] is True
    assert data["case_id"] == cid
    assert data["name"] == "Case Alpha"

    # Verify files are completely gone
    assert not cdir.exists()

    # Store get_case raises CaseNotFoundError
    with pytest.raises(CaseNotFoundError):
        store.get_case(cid)

    # Listing cases does not include deleted case
    cases_resp = client.get("/api/cases", headers=headers)
    assert cases_resp.status_code == 200
    listed_ids = [c["case_id"] for c in cases_resp.json()]
    assert cid not in listed_ids


def test_delete_case_non_admin_refused(delete_app_setup):
    """Analyst, viewer, and unauthenticated requests are refused with 403 / 401."""
    client: TestClient = delete_app_setup["client"]
    store = delete_app_setup["store"]
    analyst_headers = delete_app_setup["analyst_headers"]
    viewer_headers = delete_app_setup["viewer_headers"]

    case = store.create_case("Case Protected", "analyst_user")
    cid = case["case_id"]
    cdir = store.case_dir(cid)

    # Analyst refused (403)
    resp_analyst = client.delete(f"/api/cases/{cid}", headers=analyst_headers)
    assert resp_analyst.status_code == 403

    # Viewer refused (403)
    resp_viewer = client.delete(f"/api/cases/{cid}", headers=viewer_headers)
    assert resp_viewer.status_code == 403

    # Unauthenticated refused (401)
    resp_unauth = client.delete(f"/api/cases/{cid}")
    assert resp_unauth.status_code == 401

    # Verify case directory and files remain untouched
    assert cdir.is_dir()
    assert (cdir / "case.json").is_file()


def test_delete_case_job_running_refused(delete_app_setup):
    """Deletion is refused with 409 if a job for the case is queued or running."""
    client: TestClient = delete_app_setup["client"]
    store = delete_app_setup["store"]
    job_store = delete_app_setup["job_store"]
    headers = delete_app_setup["admin_headers"]

    case = store.create_case("Case With Job", "analyst_user")
    cid = case["case_id"]
    cdir = store.case_dir(cid)

    # 1. Job is queued
    job = job_store.create(kind="extract", case_id=cid, total=5)
    jid = job["job_id"]

    resp_queued = client.delete(f"/api/cases/{cid}", headers=headers)
    assert resp_queued.status_code == 409
    assert "active" in resp_queued.json()["error"]["message"].lower() or "job" in resp_queued.json()["error"]["message"].lower()
    assert cdir.is_dir()

    # 2. Job is running
    job_store.update(jid, status="running")
    resp_running = client.delete(f"/api/cases/{cid}", headers=headers)
    assert resp_running.status_code == 409
    assert cdir.is_dir()

    # 3. Job is done -> now deletion succeeds
    job_store.update(jid, status="done")
    resp_done = client.delete(f"/api/cases/{cid}", headers=headers)
    assert resp_done.status_code == 200
    assert not cdir.exists()


def test_delete_case_audit_entry_and_chain_verifies(delete_app_setup):
    """Case deletion appends an audit entry and preserves hash chain integrity."""
    client: TestClient = delete_app_setup["client"]
    store = delete_app_setup["store"]
    audit_log = delete_app_setup["audit_log"]
    headers = delete_app_setup["admin_headers"]

    case = store.create_case("Case Audit Verify", "analyst_user")
    cid = case["case_id"]

    resp = client.delete(f"/api/cases/{cid}", headers=headers)
    assert resp.status_code == 200

    # Verify chain integrity
    is_valid, count, first_bad = audit_log.verify()
    assert is_valid is True
    assert first_bad is None
    assert count >= 1

    # Check last audit entry content
    entries = audit_log.read(limit=100)
    last_entry = entries[-1]
    assert last_entry["action"] == "case_deleted"
    assert last_entry["actor"] == "admin_user"
    assert last_entry["role"] == "admin"
    assert last_entry["case_id"] == cid
    assert last_entry["detail"]["name"] == "Case Audit Verify"
    assert "ts" in last_entry
    assert "hash" in last_entry
    assert "prev_hash" in last_entry


def test_delete_case_unknown_404(delete_app_setup):
    """Deleting an unknown case ID returns 404."""
    client: TestClient = delete_app_setup["client"]
    headers = delete_app_setup["admin_headers"]

    resp = client.delete("/api/cases/C-0000000000", headers=headers)
    assert resp.status_code == 404
    data = resp.json()
    assert data["error"]["code"] == "case_not_found"


def test_delete_case_path_safety(delete_app_setup):
    """Path traversal attempts are rejected and cannot escape cases directory."""
    client: TestClient = delete_app_setup["client"]
    headers = delete_app_setup["admin_headers"]

    # Traversal strings
    traversal_ids = [
        "..",
        "../../etc",
        "../cases",
        "C-1234567890/../other",
        "invalid_format",
        "C-123",
    ]

    for bad_id in traversal_ids:
        resp = client.delete(f"/api/cases/{bad_id}", headers=headers)
        assert resp.status_code in (400, 404, 405), f"Traversal '{bad_id}' returned {resp.status_code}"
        assert "error" in resp.json()


def test_delete_case_without_api_prefix(delete_app_setup):
    """DELETE /cases/{case_id} works directly without /api prefix."""
    client: TestClient = delete_app_setup["client"]
    store = delete_app_setup["store"]
    headers = delete_app_setup["admin_headers"]

    case = store.create_case("Case No Prefix", "analyst_user")
    cid = case["case_id"]

    resp = client.delete(f"/cases/{cid}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True
    assert not store.case_dir(cid).exists()
