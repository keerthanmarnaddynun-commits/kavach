"""Follow-up tests for Chunk A review findings (Step C0)."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import threading
import time
from typing import Any
from unittest.mock import patch

from fastapi.testclient import TestClient
import httpx
import pytest

import kavach_api.app
from kavach_api.app import create_app
from kavach_api.settings import Settings, load_settings
from kavach_api.storage import Storage
from scripts.create_user import create_user
from scripts.load_demo_case import DEMO_CASE_NAME, load_demo_case

REPO_ROOT = Path(__file__).resolve().parent.parent


def fake_extractor(text: str, doc_id: str, case_id: str) -> dict[str, Any]:
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
                    "mentions": [{"surface": "Target Person", "char_span": [14, 27], "kind": "NAME"}],
                    "ai_confidence": 0.95,
                }
            ],
            "relations": [],
        },
    }


def _create_test_environment(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    settings = load_settings(
        {
            "KAVACH_RUNTIME_DIR": str(runtime_dir),
            "KAVACH_PBKDF2_ITERATIONS": "1000",
            "KAVACH_CORS_ORIGINS": "http://localhost:5173,http://127.0.0.1:5173",
        }
    )
    create_user(settings, "admin_user", "admin", "AdminStrongPass123!")
    create_user(settings, "analyst_user", "analyst", "AnalystStrongPass123!")
    create_user(settings, "viewer_user", "viewer", "ViewerStrongPass123!")

    app = create_app(settings, extractor=fake_extractor)
    client = TestClient(app)

    r_adm = client.post("/api/auth/login", json={"username": "admin_user", "password": "AdminStrongPass123!"})
    admin_token = r_adm.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    r_ana = client.post("/api/auth/login", json={"username": "analyst_user", "password": "AnalystStrongPass123!"})
    analyst_token = r_ana.json()["access_token"]
    analyst_headers = {"Authorization": f"Bearer {analyst_token}"}

    r_viw = client.post("/api/auth/login", json={"username": "viewer_user", "password": "ViewerStrongPass123!"})
    viewer_token = r_viw.json()["access_token"]
    viewer_headers = {"Authorization": f"Bearer {viewer_token}"}

    return {
        "admin_headers": admin_headers,
        "analyst_headers": analyst_headers,
        "app": app,
        "client": client,
        "runtime_dir": runtime_dir,
        "settings": settings,
        "viewer_headers": viewer_headers,
    }


def test_path_traversal_properly(tmp_path: Path):
    """Hostile ids in case, doc, node positions return 400/404 with error body; >= 8 requests sent."""
    env = _create_test_environment(tmp_path)
    client: TestClient = env["client"]
    v_headers = env["viewer_headers"]
    a_headers = env["analyst_headers"]
    runtime_dir = env["runtime_dir"]

    # Create a valid case with a valid document
    r_case = client.post("/api/cases", json={"name": "ValidCase"}, headers=a_headers)
    assert r_case.status_code in (200, 201)
    valid_cid = r_case.json()["case_id"]

    fir_content = "LANG: english\n[[PERSON:P1:S|Target Person]] made a call.\n"
    r_doc = client.post(
        f"/api/cases/{valid_cid}/documents",
        files={"files": ("FIR_01.txt", fir_content.encode("utf-8"), "text/plain")},
        headers=a_headers,
    )
    assert r_doc.status_code in (200, 201)
    valid_did = r_doc.json()["documents"][0]["doc_id"]

    hostile_ids = [
        "../x",
        "..\\x",
        "%2e%2e",
        "..%2F..%2Fx",
        "%00",
        "/etc/passwd",
        "C:\\Windows\\System32",
        "A" * 500,
        "C-0123456789\n",
    ]

    sent_count = 0
    test_urls = []
    for hid in hostile_ids:
        test_urls.append(f"/api/cases/{hid}")
        test_urls.append(f"/api/cases/{valid_cid}/documents/{hid}")
        test_urls.append(f"/api/cases/{valid_cid}/nodes/{hid}")

    for url in test_urls:
        try:
            resp = client.get(url, headers=v_headers)
        except (httpx.InvalidURL, httpx.UnsupportedProtocol):
            continue

        sent_count += 1
        assert resp.status_code in (400, 404), f"URL '{url}' returned {resp.status_code}"
        data = resp.json()
        assert "error" in data, f"Missing error object in response for {url}"
        assert "code" in data["error"], f"Missing error code in response for {url}"
        assert "message" in data["error"], f"Missing error message in response for {url}"

    assert sent_count >= 8, f"Only sent {sent_count} requests, required at least 8"

    # Check that no file was created outside the temp runtime directory
    parent_files = list(tmp_path.iterdir())
    for p in parent_files:
        assert p == runtime_dir, f"Unexpected file or directory created outside runtime: {p}"


def test_unknown_routes_and_wrong_methods_error_format(tmp_path: Path):
    """Unknown routes (404) and wrong methods (405) return documented error JSON shape."""
    env = _create_test_environment(tmp_path)
    client: TestClient = env["client"]
    v_headers = env["viewer_headers"]

    # 1. Unknown route GET /api/nope -> 404 code not_found
    r1 = client.get("/api/nope", headers=v_headers)
    assert r1.status_code == 404
    data1 = r1.json()
    assert data1["error"]["code"] == "not_found"
    assert data1["error"]["message"] == "Not Found"

    # 2. Wrong method DELETE /api/health -> 405 code method_not_allowed
    r2 = client.delete("/api/health")
    assert r2.status_code == 405
    data2 = r2.json()
    assert data2["error"]["code"] == "method_not_allowed"
    assert data2["error"]["message"] == "Method Not Allowed"


def test_read_only_repository_check(tmp_path: Path):
    """Git status is unchanged before and after executing a realistic workload."""
    if shutil.which("git") is None:
        pytest.skip("git binary not available in environment")

    def get_repo_status() -> list[str]:
        proc = subprocess.run(
            ["git", "status", "--short"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        lines: list[str] = []
        for line in proc.stdout.splitlines():
            stripped = line.strip()
            path = stripped.split()[-1] if stripped.split() else ""
            if any(
                path.startswith(prefix)
                for prefix in (
                    "runbook_logs/",
                    "runbook_state/",
                    "scratch/",
                    "runbook_logs\\",
                    "runbook_state\\",
                    "scratch\\",
                )
            ):
                continue
            lines.append(line)
        return lines

    status_before = get_repo_status()

    # Workload execution
    env = _create_test_environment(tmp_path)
    client: TestClient = env["client"]
    settings = env["settings"]
    v_headers = env["viewer_headers"]
    a_headers = env["analyst_headers"]

    # Load demo case
    demo_res = load_demo_case(settings=settings)
    case_id = demo_res["case_id"]

    # Read graph and leads
    r_graph = client.get(f"/api/cases/{case_id}/graph", headers=v_headers)
    assert r_graph.status_code == 200
    r_leads = client.get(f"/api/cases/{case_id}/leads", headers=v_headers)
    assert r_leads.status_code == 200

    # Upload one document
    doc_text = "LANG: english\n[[PERSON:P10:S|Anand Kumar]] was present.\n"
    r_up = client.post(
        f"/api/cases/{case_id}/documents",
        files={"files": ("FIR_extra.txt", doc_text.encode("utf-8"), "text/plain")},
        headers=a_headers,
    )
    assert r_up.status_code == 200

    status_after = get_repo_status()
    assert status_after == status_before, f"Git status changed after workload:\nBefore: {status_before}\nAfter: {status_after}"


def test_load_demo_case_preflight_validation(tmp_path: Path):
    """Preflight validation in load_demo_case: tampered analysis raises ValueError and leaves zero cases behind."""
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    settings = load_settings({"KAVACH_RUNTIME_DIR": str(runtime_dir)})
    store = Storage(settings)

    # Prepare tampered analysis in a temporary directory
    src_analyses = REPO_ROOT / "results" / "2026-11-11_step6_extraction_r2" / "run1"
    temp_analyses = tmp_path / "tampered_analyses"
    temp_analyses.mkdir(parents=True, exist_ok=True)

    for afile in src_analyses.glob("*.analysis.json"):
        shutil.copy2(afile, temp_analyses / afile.name)

    # Tamper one file's document_hash
    target_analysis = temp_analyses / "FIR_01.analysis.json"
    os.chmod(target_analysis, stat.S_IWRITE | stat.S_IREAD)
    content = json.loads(target_analysis.read_text(encoding="utf-8"))
    content["info"]["document_hash"] = "0000000000000000000000000000000000000000000000000000000000000000"
    target_analysis.write_text(json.dumps(content, indent=2), encoding="utf-8")

    # 1. Attempt load with tampered analysis -> raises ValueError
    with pytest.raises(ValueError) as excinfo:
        load_demo_case(settings=settings, analyses_dir=temp_analyses)
    assert "mismatch" in str(excinfo.value).lower()

    # Verify that NO case was created in runtime
    assert len(store.list_cases()) == 0, "Failed load left a case behind"

    # 2. Second call with real analyses folder succeeds
    result = load_demo_case(settings=settings)
    assert result["name"] == DEMO_CASE_NAME
    assert len(store.list_cases()) == 1


def test_analyze_concurrency_deterministic(tmp_path: Path):
    """Deterministic analyze concurrency test using threading.Event patch on build_graph."""
    env = _create_test_environment(tmp_path)
    client: TestClient = env["client"]
    settings = env["settings"]
    app = env["app"]
    a_headers = env["analyst_headers"]

    # Pre-populate demo case so analysis dependencies are met
    demo_res = load_demo_case(settings=settings)
    case_id = demo_res["case_id"]

    event_entered = threading.Event()
    event_release = threading.Event()
    orig_build_graph = kavach_api.app.build_graph

    def blocking_build_graph(store, cid):
        event_entered.set()
        event_release.wait(timeout=10.0)
        return orig_build_graph(store, cid)

    with patch("kavach_api.app.build_graph", side_effect=blocking_build_graph):
        # 1. First analyze request -> 200
        r1 = client.post(f"/api/cases/{case_id}/analyze", headers=a_headers)
        assert r1.status_code == 200
        job_id_1 = r1.json()["job_id"]

        # Wait for worker thread to enter build_graph
        assert event_entered.wait(timeout=5.0), "Worker did not enter build_graph"

        # 2. Second analyze request while first is running -> 409
        r2 = client.post(f"/api/cases/{case_id}/analyze", headers=a_headers)
        assert r2.status_code == 409

        # Verify exactly one analyze job exists
        jobs = app.state.job_store.list_for_case(case_id)
        analyze_jobs = [j for j in jobs if j.get("kind") == "analyze"]
        assert len(analyze_jobs) == 1, f"Expected 1 analyze job, found {len(analyze_jobs)}"

        # 3. Release worker and wait for completion
        event_release.set()
        for _ in range(100):
            jstate = app.state.job_store.get(job_id_1)
            if jstate and jstate.get("status") == "done":
                break
            time.sleep(0.05)
        else:
            pytest.fail("First analyze job did not complete within timeout")

        # 4. Third analyze request after completion -> 200
        r3 = client.post(f"/api/cases/{case_id}/analyze", headers=a_headers)
        assert r3.status_code == 200
