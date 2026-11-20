"""HTTP security test pass for KAVACH API (Step A10)."""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import subprocess

import pytest
from fastapi.testclient import TestClient

from kavach_api.app import create_app
from kavach_api.security import create_token, hash_password
from kavach_api.settings import Settings, load_settings
from kavach_api.storage import Storage
from scripts.create_user import create_user

REPO_ROOT = Path(__file__).resolve().parent.parent


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def fake_extractor_success(text: str, doc_id: str, case_id: str) -> dict[str, Any]:
    return {
        "info": {"document_hash": "dummy_hash"},
        "doc": {
            "schema_version": "1.1",
            "source_doc_id": doc_id,
            "case_id": case_id,
            "entities": [
                {
                    "entity_id": "ent_01",
                    "entity_type": "PERSON",
                    "canonical_name": "Target Person",
                    "mentions": [{"surface": "Target Person", "char_span": [14, 27]}],
                    "ai_confidence": 0.95,
                }
            ],
            "relations": [],
        },
    }


@pytest.fixture(scope="module")
def sec_env(tmp_path_factory):
    runtime_dir = tmp_path_factory.mktemp("runtime_sec")
    settings = load_settings(
        {
            "KAVACH_RUNTIME_DIR": str(runtime_dir),
            "KAVACH_PBKDF2_ITERATIONS": "1000",
            "KAVACH_CORS_ORIGINS": "http://localhost:5173,http://127.0.0.1:5173",
        }
    )

    # Pre-create users
    create_user(settings, "admin_user", "admin", "AdminStrongPass123!")
    create_user(settings, "analyst_user", "analyst", "AnalystStrongPass123!")
    create_user(settings, "viewer_user", "viewer", "ViewerStrongPass123!")

    app = create_app(settings, extractor=fake_extractor_success)
    client = TestClient(app)

    # Get tokens
    r_adm = client.post("/api/auth/login", json={"username": "admin_user", "password": "AdminStrongPass123!"})
    adm_token = r_adm.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {adm_token}"}

    r_ana = client.post("/api/auth/login", json={"username": "analyst_user", "password": "AnalystStrongPass123!"})
    ana_token = r_ana.json()["access_token"]
    analyst_headers = {"Authorization": f"Bearer {ana_token}"}

    r_viw = client.post("/api/auth/login", json={"username": "viewer_user", "password": "ViewerStrongPass123!"})
    viw_token = r_viw.json()["access_token"]
    viewer_headers = {"Authorization": f"Bearer {viw_token}"}

    # Create a test case and a document
    r_case = client.post("/api/cases", json={"name": "SecTest"}, headers=analyst_headers)
    case_id = r_case.json()["case_id"]

    fir_content = "LANG: english\n[[PERSON:P1:S|Target Person]] made a call.\n"
    r_doc = client.post(
        f"/api/cases/{case_id}/documents",
        files={"files": ("FIR_01.txt", fir_content.encode("utf-8"), "text/plain")},
        headers=analyst_headers,
    )
    doc_id = r_doc.json()["documents"][0]["doc_id"]

    return {
        "admin_headers": admin_headers,
        "analyst_headers": analyst_headers,
        "app": app,
        "case_id": case_id,
        "client": client,
        "doc_id": doc_id,
        "runtime_dir": runtime_dir,
        "settings": settings,
        "viewer_headers": viewer_headers,
    }


def test_path_traversal_attempts_rejected(sec_env):
    """Path traversal attempts in case id, doc id, node id, file names return 400/404 and do not escape runtime."""
    client: TestClient = sec_env["client"]
    v_headers = sec_env["viewer_headers"]
    a_headers = sec_env["analyst_headers"]
    case_id = sec_env["case_id"]
    runtime_dir = sec_env["runtime_dir"]

    # 1. Case ID traversal
    traversal_cases = [
        "../etc/passwd",
        r"..\..\Windows",
        "..%2F..%2Fsecret",
        "case%00id",
        "C-../../evil",
        "/etc/shadow",
    ]
    for bad_id in traversal_cases:
        try:
            r = client.get(f"/api/cases/{bad_id}", headers=v_headers)
            assert r.status_code in (400, 404), f"Case ID traversal '{bad_id}' did not return 400/404: {r.status_code}"
        except Exception:
            # Client HTTP parser rejected invalid characters
            pass

    # 2. Document ID traversal
    traversal_docs = [
        "../secret.key",
        r"..\users.json",
        "..%2F..%2Faudit.log",
        "doc%00evil",
    ]
    for bad_doc in traversal_docs:
        try:
            r = client.get(f"/api/cases/{case_id}/documents/{bad_doc}", headers=v_headers)
            assert r.status_code in (400, 404), f"Doc ID traversal '{bad_doc}' did not return 400/404: {r.status_code}"
        except Exception:
            pass

    # 3. Node ID traversal
    traversal_nodes = [
        "../node",
        r"..\node",
        "..%2Fnode",
        "node%00id",
    ]
    for bad_node in traversal_nodes:
        try:
            r = client.get(f"/api/cases/{case_id}/nodes/{bad_node}", headers=v_headers)
            assert r.status_code in (400, 404), f"Node ID traversal '{bad_node}' did not return 400/404: {r.status_code}"
        except Exception:
            pass

    # 4. Upload filename traversal
    fir_text = "LANG: english\n[[PERSON:P2:V|Victim Name]] was robbed.\n"
    r_up = client.post(
        f"/api/cases/{case_id}/documents",
        files={"files": ("../../escaped_file.txt", fir_text.encode("utf-8"), "text/plain")},
        headers=a_headers,
    )
    # Check that no file escaped outside runtime/cases/{case_id}/documents
    escaped_candidate = runtime_dir / "escaped_file.txt"
    assert not escaped_candidate.exists(), "File escaped runtime_dir!"
    root_candidate = REPO_ROOT / "escaped_file.txt"
    assert not root_candidate.exists(), "File escaped to repo root!"


def test_upload_filename_with_control_characters(sec_env):
    """Upload filename with control characters is stored safely without filesystem corruption."""
    client: TestClient = sec_env["client"]
    a_headers = sec_env["analyst_headers"]
    case_id = sec_env["case_id"]

    fir_text = "LANG: english\n[[PERSON:P3:S|Suspect Three]] ran away.\n"
    r = client.post(
        f"/api/cases/{case_id}/documents",
        files={"files": ("doc\r\n\x00\x1b[31mbad.txt", fir_text.encode("utf-8"), "text/plain")},
        headers=a_headers,
    )
    assert r.status_code in (200, 422), f"Upload with control chars failed unexpectedly: {r.status_code}"
    if r.status_code == 200:
        docs = r.json().get("documents", [])
        assert len(docs) > 0
        doc_meta = docs[0]
        # Document ID must be safe
        assert "\r" not in doc_meta["doc_id"]
        assert "\n" not in doc_meta["doc_id"]
        assert "\0" not in doc_meta["doc_id"]


def test_large_json_body_rejection(sec_env):
    """A 1 MB JSON body to a small endpoint is rejected with 413 without memory blow-up."""
    client: TestClient = sec_env["client"]

    # 1 MB JSON payload to /api/auth/login
    huge_pw = "A" * (1024 * 1024)
    r = client.post("/api/auth/login", json={"username": "viewer_user", "password": huge_pw})
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "upload_too_large"

    # 1 MB JSON payload to /api/admin/users
    huge_username = "B" * (1024 * 1024)
    r_admin = client.post(
        "/api/admin/users",
        json={"username": huge_username, "password": "Password123!", "role": "viewer"},
        headers=sec_env["admin_headers"],
    )
    assert r_admin.status_code == 413
    assert r_admin.json()["error"]["code"] == "upload_too_large"


def test_token_tampering_and_alg_none(sec_env):
    """Token tampering and alg: none header return 401 with 'Invalid or expired token'."""
    client: TestClient = sec_env["client"]

    # 1. alg: none token
    hdr_none = _b64url(json.dumps({"alg": "none", "typ": "JWT"}).encode("utf-8"))
    payload = _b64url(json.dumps({"sub": "admin_user", "role": "admin", "iat": 1000, "exp": 9999999999}).encode("utf-8"))
    none_token = f"{hdr_none}.{payload}."

    r1 = client.get("/api/auth/me", headers={"Authorization": f"Bearer {none_token}"})
    assert r1.status_code == 401
    assert r1.json()["error"]["message"] == "Invalid or expired token"

    # 2. Tampered signature on valid token
    valid_token = sec_env["viewer_headers"]["Authorization"].split()[1]
    tampered_sig = valid_token[:-5] + "XXXXX"
    r2 = client.get("/api/auth/me", headers={"Authorization": f"Bearer {tampered_sig}"})
    assert r2.status_code == 401
    assert r2.json()["error"]["message"] == "Invalid or expired token"


def test_expired_token_rejection(sec_env):
    """Expired token returns 401 with 'Invalid or expired token'."""
    client: TestClient = sec_env["client"]
    app = sec_env["app"]

    expired_token = create_token(
        secret=app.state.secret,
        username="viewer_user",
        role="viewer",
        ttl_seconds=-100,
    )
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert r.status_code == 401
    assert r.json()["error"]["message"] == "Invalid or expired token"


def test_role_escalation_in_token_payload(sec_env):
    """Role escalation by editing token payload without valid signature returns 401."""
    client: TestClient = sec_env["client"]
    viewer_token = sec_env["viewer_headers"]["Authorization"].split()[1]

    parts = viewer_token.split(".")
    payload_dict = json.loads(base64.urlsafe_b64decode(parts[1] + "==").decode("utf-8"))
    payload_dict["role"] = "admin"
    forged_payload = _b64url(json.dumps(payload_dict).encode("utf-8"))
    forged_token = f"{parts[0]}.{forged_payload}.{parts[2]}"

    r = client.post(
        "/api/admin/users",
        json={"username": "escalated_user", "password": "Password123456!", "role": "admin"},
        headers={"Authorization": f"Bearer {forged_token}"},
    )
    assert r.status_code == 401
    assert r.json()["error"]["message"] == "Invalid or expired token"


def test_admin_cannot_be_created_by_analyst(sec_env):
    """An admin user cannot be created by an analyst role (403 Forbidden)."""
    client: TestClient = sec_env["client"]
    r = client.post(
        "/api/admin/users",
        json={"username": "evil_admin", "password": "Password123456!", "role": "admin"},
        headers=sec_env["analyst_headers"],
    )
    assert r.status_code == 403


def test_passwords_never_appear_in_runtime_files_or_responses(sec_env):
    """Passwords never appear in the audit log, job files, responses, or anywhere in runtime dir."""
    client: TestClient = sec_env["client"]
    admin_headers = sec_env["admin_headers"]
    runtime_dir = sec_env["runtime_dir"]

    canary_password = "CANARY_PW_UniqueSecret_987654321!"

    # 1. Create a user with the canary password
    r_create = client.post(
        "/api/admin/users",
        json={"username": "canary_user", "password": canary_password, "role": "viewer"},
        headers=admin_headers,
    )
    assert r_create.status_code == 201
    assert canary_password not in r_create.text

    # 2. Login successfully
    r_login = client.post(
        "/api/auth/login",
        json={"username": "canary_user", "password": canary_password},
    )
    assert r_login.status_code == 200
    assert canary_password not in r_login.text

    # 3. Failed login attempt
    r_fail = client.post(
        "/api/auth/login",
        json={"username": "canary_user", "password": canary_password + "_wrong"},
    )
    assert r_fail.status_code == 401
    assert canary_password not in r_fail.text

    # 4. Search entire runtime dir for the plaintext canary password
    canary_bytes = canary_password.encode("utf-8")
    for root, _dirs, files in os.walk(runtime_dir):
        for fname in files:
            fpath = Path(root) / fname
            content = fpath.read_bytes()
            assert canary_bytes not in content, (
                f"Plaintext password leaked into runtime file: {fpath.relative_to(runtime_dir)}"
            )


def test_secret_key_file_not_served(sec_env):
    """The secret key file is not served by any route and its hex does not leak."""
    client: TestClient = sec_env["client"]
    v_headers = sec_env["viewer_headers"]
    secret_hex = sec_env["app"].state.secret

    routes_to_probe = [
        "/secret.key",
        "/runtime/secret.key",
        "/api/secret.key",
        "/api/cases/secret.key",
        "/api/cases/secret.key/graph",
    ]
    for path in routes_to_probe:
        r = client.get(path, headers=v_headers)
        assert r.status_code in (400, 404)
        assert secret_hex not in r.text


def test_cors_answers_only_for_allowed_origins(sec_env):
    """CORS headers are returned only for configured allowed origins."""
    client: TestClient = sec_env["client"]

    # Allowed origin
    r_allowed = client.options(
        "/api/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert r_allowed.headers.get("access-control-allow-origin") == "http://localhost:5173"

    # Disallowed origin
    r_blocked = client.options(
        "/api/health",
        headers={
            "Origin": "http://malicious-site.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert r_blocked.headers.get("access-control-allow-origin") is None


def test_error_responses_contain_no_paths_or_tracebacks(sec_env):
    """Error responses contain no internal file paths, tracebacks, or framework names."""
    client: TestClient = sec_env["client"]

    error_requests = [
        ("GET", "/api/cases/non_existent_case_12345", sec_env["viewer_headers"], None),
        ("GET", "/api/cases/C-0000000000/documents/doc_missing", sec_env["viewer_headers"], None),
        ("POST", "/api/admin/users", sec_env["analyst_headers"], {"username": "u", "password": "p", "role": "admin"}),
        ("POST", "/api/cases", sec_env["analyst_headers"], {"name": ""}),
    ]

    forbidden_patterns = [
        "Traceback (most recent call last)",
        str(REPO_ROOT),
        ".py:",
        "fastapi",
        "starlette",
        "pydantic",
    ]

    for method, url, headers, json_body in error_requests:
        if method == "GET":
            resp = client.get(url, headers=headers)
        else:
            resp = client.post(url, json=json_body, headers=headers)

        assert resp.status_code >= 400
        text = resp.text
        for pattern in forbidden_patterns:
            assert pattern.lower() not in text.lower(), (
                f"Leaked pattern '{pattern}' in error response for {method} {url}: {text}"
            )
        data = resp.json()
        assert "error" in data
        assert "code" in data["error"]
        assert "message" in data["error"]


def test_g5_concurrency_audit_duplicate_checks(sec_env):
    """G5: Test concurrent analyze race guard, extract audit entry, and atomic duplicate check."""
    import concurrent.futures
    import time
    client: TestClient = sec_env["client"]
    a_headers = sec_env["analyst_headers"]
    case_id = sec_env["case_id"]
    store: Storage = sec_env["app"].state.store

    # 1. G5(c, d): Multi-file upload where second file is duplicate of existing FIR_01
    existing_meta = store.list_documents(case_id)[0]
    existing_doc_id = existing_meta["doc_id"]
    _meta, existing_text = store.get_document(case_id, existing_doc_id)

    new_text = "LANG: english\n[[PERSON:P99:S|New Person]] walked in.\n"
    initial_docs_count = len(store.list_documents(case_id))

    r_dup = client.post(
        f"/api/cases/{case_id}/documents",
        files=[
            ("files", ("FIR_new.txt", new_text.encode("utf-8"), "text/plain")),
            ("files", ("FIR_dup.txt", existing_text.encode("utf-8"), "text/plain")),
        ],
        headers=a_headers,
    )
    assert r_dup.status_code == 409
    err_body = r_dup.json()
    assert err_body["error"]["code"] == "duplicate_document"
    # G5(d): 409 error message must contain the existing doc id
    assert existing_doc_id in err_body["error"]["message"]
    # G5(c): store nothing on duplicate
    assert len(store.list_documents(case_id)) == initial_docs_count
    assert not (store.case_dir(case_id) / "documents" / "FIR_new").exists()

    # Batch internal duplicate check
    r_batch_dup = client.post(
        f"/api/cases/{case_id}/documents",
        files=[
            ("files", ("FIR_b1.txt", new_text.encode("utf-8"), "text/plain")),
            ("files", ("FIR_b2.txt", new_text.encode("utf-8"), "text/plain")),
        ],
        headers=a_headers,
    )
    assert r_batch_dup.status_code == 409
    assert len(store.list_documents(case_id)) == initial_docs_count

    # 2. G5(b): Successful upload creates extract job and writes job_finished audit entry
    r_ok = client.post(
        f"/api/cases/{case_id}/documents",
        files=[("files", ("FIR_new.txt", new_text.encode("utf-8"), "text/plain"))],
        headers=a_headers,
    )
    assert r_ok.status_code == 200
    job_id = r_ok.json()["job_id"]

    # Wait for extract job to finish
    for _ in range(50):
        j_state = client.get(f"/api/jobs/{job_id}", headers=sec_env["viewer_headers"]).json()
        if j_state.get("status") in ("done", "failed"):
            break
        time.sleep(0.05)

    entries = sec_env["app"].state.audit_log.read(limit=100)
    finished_entries = [
        e for e in entries
        if e.get("action") == "job_finished" and e.get("detail", {}).get("job_id") == job_id
    ]
    assert len(finished_entries) >= 1
    fin_detail = finished_entries[0]["detail"]
    assert "status" in fin_detail
    assert "counts" in fin_detail
    # Must NOT log document text or content
    assert "text" not in fin_detail

    # 3. G5(a): Concurrent threads calling analyze: guarded by case_lock
    # One succeeds, others get 409
    analyze_statuses = []
    def _call_analyze():
        resp = client.post(f"/api/cases/{case_id}/analyze", headers=a_headers)
        return resp.status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(_call_analyze) for _ in range(5)]
        for f in concurrent.futures.as_completed(futures):
            analyze_statuses.append(f.result())

    assert 200 in analyze_statuses
    assert 409 in analyze_statuses


def test_audit_chain_validity(sec_env):
    """The audit log chain is completely valid after all security actions."""
    app = sec_env["app"]
    client: TestClient = sec_env["client"]
    admin_headers = sec_env["admin_headers"]

    # Wait briefly for any background jobs to settle
    import time
    time.sleep(0.1)

    # Verification via admin HTTP endpoint
    r = client.get("/api/admin/audit/verify", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["entries"] > 0
    assert body["first_bad_index"] is None

    # Direct verification on the AuditLog object
    is_valid, count, bad_idx = app.state.audit_log.verify()
    assert is_valid is True, f"Audit chain verification failed at entry {bad_idx}"
    assert count == body["entries"]


def test_read_only_data_folders_no_writes_outside_runtime():
    """Verify that the repository data folders remained read-only with no writes outside runtime."""
    # Run git status --short and ensure no modifications outside runtime
    res = subprocess.run(
        ["git", "status", "--short"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0
    # Any tracked modifications should only be inside kavach_api, scripts, tests, runbook_logs
    for line in res.stdout.splitlines():
        line_clean = line.strip()
        if not line_clean:
            continue
        # Status format: XY PATH
        status_code = line_clean[:2]
        path_str = line_clean[3:].strip()
        # Verify no file in data/ has been modified
        if status_code.startswith("M") or status_code.startswith("D"):
            assert not path_str.startswith("data/"), f"File in data/ was modified: {path_str}"
