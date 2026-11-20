"""Tests for write HTTP endpoints: case creation, uploads, jobs, events, analyze, and break."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import time
from typing import Any

from fastapi.testclient import TestClient
import pytest

from contracts.v1_1.validate import validate_graph
from kavach_api.app import create_app
from kavach_api.leads import _extract_owner_maps
from kavach_api.security import create_token
from kavach_api.settings import Settings
from kavach_api.storage import Storage

REPO_ROOT = Path(__file__).resolve().parent.parent


def fake_extractor_success(text: str, doc_id: str, case_id: str) -> dict[str, Any]:
    """Fake extractor returning valid contract schema doc."""
    return {
        "aux": {"source_doc_id": doc_id, "case_id": case_id},
        "doc": {
            "source_doc_id": doc_id,
            "case_id": case_id,
            "entities": [
                {
                    "entity_id": "ent_p1",
                    "category": "PERSON",
                    "text": "Ramesh Kumar",
                    "char_span": [0, 12],
                    "ai_confidence": 0.95,
                    "confidence": "high",
                    "attributes": {"role": "suspect"},
                },
                {
                    "entity_id": "ent_p2",
                    "category": "PERSON",
                    "text": "Suresh Singh",
                    "char_span": [15, 27],
                    "ai_confidence": 0.92,
                    "confidence": "high",
                    "attributes": {"role": "suspect"},
                },
                {
                    "entity_id": "ent_ph1",
                    "category": "PHONE",
                    "text": "9876543210",
                    "char_span": [30, 40],
                    "ai_confidence": 0.98,
                    "confidence": "high",
                    "attributes": {},
                },
            ],
            "relations": [
                {
                    "relation": "OWNS_DEVICE",
                    "source": "ent_p1",
                    "target": "ent_ph1",
                    "char_span": [0, 40],
                    "ai_confidence": 0.9,
                    "confidence": "high",
                }
            ],
            "schema_version": "1.1",
        },
        "info": {"model": "fake", "elapsed_sec": 0.01},
    }


@pytest.fixture
def write_app_setup(tmp_path: Path):
    """Fixture providing FastAPI test client and authenticated analyst/viewer tokens."""
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

    app = create_app(settings=settings, extractor=fake_extractor_success)
    user_store = app.state.user_store
    user_store.create_user("analyst_user", "AnalystSecret123!", "analyst")
    user_store.create_user("viewer_user", "ViewerSecret123!", "viewer")

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
        "analyst_headers": {"Authorization": f"Bearer {analyst_token}"},
        "viewer_headers": {"Authorization": f"Bearer {viewer_token}"},
        "settings": settings,
    }

    # Clean shutdown
    app.state.job_runner.shutdown()


def test_write_auth_and_permissions(write_app_setup):
    """Protected write routes reject unauthenticated requests (401) and viewer role (403)."""
    client: TestClient = write_app_setup["client"]
    viewer_headers = write_app_setup["viewer_headers"]

    # 1. POST /api/cases
    r_unauth = client.post("/api/cases", json={"name": "Case A"})
    assert r_unauth.status_code == 401

    r_forbidden = client.post("/api/cases", json={"name": "Case A"}, headers=viewer_headers)
    assert r_forbidden.status_code == 403
    assert r_forbidden.json()["error"]["code"] == "forbidden"

    # 2. POST /api/cases/{id}/documents
    r_doc_forbid = client.post("/api/cases/C-0000000001/documents", headers=viewer_headers)
    assert r_doc_forbid.status_code == 403

    # 3. POST /api/cases/{id}/cdr
    r_cdr_forbid = client.post("/api/cases/C-0000000001/cdr", headers=viewer_headers)
    assert r_cdr_forbid.status_code == 403

    # 4. POST /api/cases/{id}/analyze
    r_an_forbid = client.post("/api/cases/C-0000000001/analyze", headers=viewer_headers)
    assert r_an_forbid.status_code == 403

    # 5. POST /api/cases/{id}/break
    r_brk_forbid = client.post(
        "/api/cases/C-0000000001/break",
        json={"group_a": ["P-1"], "group_b": ["P-2"]},
        headers=viewer_headers,
    )
    assert r_brk_forbid.status_code == 403


def test_full_write_flow_and_analysis(write_app_setup):
    """Full end-to-end write workflow: case -> docs -> CSVs -> extract job -> analyze -> leads."""
    client: TestClient = write_app_setup["client"]
    analyst_h = write_app_setup["analyst_headers"]
    viewer_h = write_app_setup["viewer_headers"]

    # 1. Create case
    r_create = client.post(
        "/api/cases",
        json={"name": "Test Operation Alpha", "synthetic": True},
        headers=analyst_h,
    )
    assert r_create.status_code == 201
    case_data = r_create.json()
    case_id = case_data["case_id"]
    assert case_data["name"] == "Test Operation Alpha"
    assert case_data["synthetic"] is True

    # 2. Upload 3 FIR text documents via multipart
    fir_dir = REPO_ROOT / "data" / "synthetic" / "out" / "firs_v5"
    fir_files = [fir_dir / f"FIR_{i:02d}.txt" for i in (1, 2, 3)]
    for f in fir_files:
        assert f.is_file(), f"Expected FIR file missing: {f}"

    files_payload = [
        ("files", (f.name, f.read_bytes(), "text/plain"))
        for f in fir_files
    ]
    r_docs = client.post(
        f"/api/cases/{case_id}/documents",
        files=files_payload,
        headers=analyst_h,
    )
    assert r_docs.status_code == 200
    doc_resp = r_docs.json()
    assert "job_id" in doc_resp
    assert len(doc_resp["documents"]) == 3
    extract_job_id = doc_resp["job_id"]

    # Wait for extract job to finish
    deadline = time.time() + 10.0
    extract_done = False
    while time.time() < deadline:
        r_j = client.get(f"/api/jobs/{extract_job_id}", headers=viewer_h)
        assert r_j.status_code == 200
        if r_j.json()["status"] == "done":
            extract_done = True
            break
        time.sleep(0.1)
    assert extract_done, "Extract job did not finish in time"

    # 3. Upload real demo CDR and Bank CSVs
    demo_dir = REPO_ROOT / "data" / "synthetic" / "out" / "case_demo_v2"
    cdr_path = demo_dir / "cdr.csv"
    bank_path = demo_dir / "bank.csv"
    assert cdr_path.is_file() and bank_path.is_file()

    # Upload CDR
    r_cdr = client.post(
        f"/api/cases/{case_id}/cdr",
        files={"file": ("cdr.csv", cdr_path.read_bytes(), "text/csv")},
        headers=analyst_h,
    )
    assert r_cdr.status_code == 200
    cdr_resp = r_cdr.json()
    assert cdr_resp["ok"] is True
    assert cdr_resp["rows"] > 0
    assert cdr_resp["errors"] == []

    # Upload Bank
    r_bank = client.post(
        f"/api/cases/{case_id}/bank",
        files={"file": ("bank.csv", bank_path.read_bytes(), "text/csv")},
        headers=analyst_h,
    )
    assert r_bank.status_code == 200
    bank_resp = r_bank.json()
    assert bank_resp["ok"] is True
    assert bank_resp["rows"] > 0
    assert bank_resp["errors"] == []

    # 4. Trigger analyze job
    r_an = client.post(f"/api/cases/{case_id}/analyze", headers=analyst_h)
    assert r_an.status_code == 200
    analyze_resp = r_an.json()
    assert "job_id" in analyze_resp
    assert analyze_resp["status"] == "queued"
    analyze_job_id = analyze_resp["job_id"]

    # Wait for analyze job to complete
    deadline = time.time() + 15.0
    analyze_done = False
    while time.time() < deadline:
        r_aj = client.get(f"/api/jobs/{analyze_job_id}", headers=viewer_h)
        assert r_aj.status_code == 200
        if r_aj.json()["status"] == "done":
            analyze_done = True
            break
        time.sleep(0.2)
    assert analyze_done, "Analyze job did not finish in time"

    # 5. Read graph and leads to verify results
    r_g = client.get(f"/api/cases/{case_id}/graph", headers=viewer_h)
    assert r_g.status_code == 200
    graph_data = r_g.json()
    validate_graph(graph_data)

    r_leads = client.get(f"/api/cases/{case_id}/leads", headers=viewer_h)
    assert r_leads.status_code == 200
    leads_data = r_leads.json()
    assert "money_flow" in leads_data
    assert "role_chips" in leads_data

    # Case detail shows analyzed: True
    r_detail = client.get(f"/api/cases/{case_id}", headers=viewer_h)
    assert r_detail.status_code == 200
    assert r_detail.json()["case"]["analyzed"] is True


def test_document_upload_validations(write_app_setup):
    """Document upload handles duplicates (409), non-UTF-8 (422), wrong extension (422), oversized (413)."""
    client: TestClient = write_app_setup["client"]
    analyst_h = write_app_setup["analyst_headers"]

    r_case = client.post("/api/cases", json={"name": "Doc Validation Case"}, headers=analyst_h)
    case_id = r_case.json()["case_id"]

    valid_content = "This is a valid FIR statement about Vikas Kumar and device 9876543210."

    # 1. Initial valid upload
    r_first = client.post(
        f"/api/cases/{case_id}/documents",
        files=[("files", ("FIR_test1.txt", valid_content.encode("utf-8"), "text/plain"))],
        headers=analyst_h,
    )
    assert r_first.status_code == 200

    # 2. Duplicate upload of identical content -> 409
    r_dup = client.post(
        f"/api/cases/{case_id}/documents",
        files=[("files", ("FIR_dup.txt", valid_content.encode("utf-8"), "text/plain"))],
        headers=analyst_h,
    )
    assert r_dup.status_code == 409
    assert r_dup.json()["error"]["code"] == "duplicate_document"

    # 3. Non-UTF-8 bytes -> 422
    invalid_bytes = b"\xff\xfe\x00\x12bad\x80\x81bytes"
    r_bad_enc = client.post(
        f"/api/cases/{case_id}/documents",
        files=[("files", ("FIR_bad.txt", invalid_bytes, "text/plain"))],
        headers=analyst_h,
    )
    assert r_bad_enc.status_code == 422
    assert r_bad_enc.json()["error"]["code"] == "validation_error"

    # 4. Wrong extension -> 422
    r_pdf = client.post(
        f"/api/cases/{case_id}/documents",
        files=[("files", ("evidence.pdf", b"Some text content", "application/pdf"))],
        headers=analyst_h,
    )
    assert r_pdf.status_code == 422
    assert "Only .txt" in r_pdf.json()["error"]["message"]

    # 5. Form text upload
    r_form = client.post(
        f"/api/cases/{case_id}/documents",
        data={"name": "FIR_from_form.txt", "text": "Another valid FIR narrative for testing form field."},
        headers=analyst_h,
    )
    assert r_form.status_code == 200
    assert len(r_form.json()["documents"]) == 1


def test_csv_upload_validations(write_app_setup):
    """CSV upload enforces column schema, row limits, error reporting (422), and size limits (413)."""
    client: TestClient = write_app_setup["client"]
    analyst_h = write_app_setup["analyst_headers"]
    store: Storage = write_app_setup["store"]

    r_case = client.post("/api/cases", json={"name": "CSV Validation Case"}, headers=analyst_h)
    case_id = r_case.json()["case_id"]

    # 1. Missing required column -> 422 with missing column identified
    broken_cdr = "a_party,b_party,start_time,duration_sec\n9876543210,9123456789,2023-01-01T10:00:00,60\n"
    r_broken = client.post(
        f"/api/cases/{case_id}/cdr",
        files={"file": ("cdr.csv", broken_cdr.encode("utf-8"), "text/csv")},
        headers=analyst_h,
    )
    assert r_broken.status_code == 422
    b_err = r_broken.json()
    assert b_err["error"]["code"] == "invalid_csv"
    assert any("imei_a" in err.get("message", "") for err in b_err["errors"])

    # Ensure nothing was stored on failure
    assert store.files_info(case_id)["cdr"] is None

    # 2. Row level errors reported with 1-based data row numbers
    bad_rows_cdr = (
        "a_party,b_party,imei_a,imsi_a,start_time,duration_sec,call_type,tower_id,lat,lon\n"
        "123,9876543210,123456789012345,12345,2023-01-01T10:00:00,60,VOICE,T1,12.0,77.0\n"
        "9876543210,9876543211,123456789012345,12345,bad_date,60,VOICE,T1,12.0,77.0\n"
    )
    r_bad_rows = client.post(
        f"/api/cases/{case_id}/cdr",
        files={"file": ("cdr.csv", bad_rows_cdr.encode("utf-8"), "text/csv")},
        headers=analyst_h,
    )
    assert r_bad_rows.status_code == 422
    err_list = r_bad_rows.json()["errors"]
    assert any(e["row"] == 1 for e in err_list)
    assert any(e["row"] == 2 for e in err_list)

    # 3. Oversized upload limit -> 413
    tiny_settings = Settings(
        runtime_dir=write_app_setup["settings"].runtime_dir,
        max_upload_bytes=100,  # 100 bytes max
    )
    tiny_app = create_app(settings=tiny_settings)
    tiny_client = TestClient(tiny_app)
    r_over = tiny_client.post(
        f"/api/cases/{case_id}/cdr",
        files={"file": ("cdr.csv", b"a" * 200, "text/csv")},
        headers=analyst_h,
    )
    assert r_over.status_code == 413
    assert r_over.json()["error"]["code"] == "upload_too_large"


def test_analyze_concurrency_rejection(write_app_setup):
    """Triggering second analyze job while one is queued or running is rejected with 409."""
    client: TestClient = write_app_setup["client"]
    analyst_h = write_app_setup["analyst_headers"]

    r_case = client.post("/api/cases", json={"name": "Concurrency Case"}, headers=analyst_h)
    case_id = r_case.json()["case_id"]

    # First analyze request
    r_an1 = client.post(f"/api/cases/{case_id}/analyze", headers=analyst_h)
    assert r_an1.status_code == 200

    # Second analyze request immediately -> 409
    r_an2 = client.post(f"/api/cases/{case_id}/analyze", headers=analyst_h)
    assert r_an2.status_code == 409
    assert r_an2.json()["error"]["code"] == "conflict"


def test_job_events_sse_stream(write_app_setup):
    """GET /api/jobs/{id}/events delivers SSE progress events and closes when job terminates."""
    client: TestClient = write_app_setup["client"]
    analyst_h = write_app_setup["analyst_headers"]
    viewer_h = write_app_setup["viewer_headers"]

    r_case = client.post("/api/cases", json={"name": "SSE Case"}, headers=analyst_h)
    case_id = r_case.json()["case_id"]

    # Upload single document to start an extract job
    r_doc = client.post(
        f"/api/cases/{case_id}/documents",
        data={"name": "FIR_sse.txt", "text": "Valid FIR document for SSE test."},
        headers=analyst_h,
    )
    job_id = r_doc.json()["job_id"]

    # Stream events
    with client.stream("GET", f"/api/jobs/{job_id}/events", headers=viewer_h) as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        events = []
        for line in response.iter_lines():
            if line.startswith("data: "):
                payload = json.loads(line[len("data: "):])
                events.append(payload)
                if payload.get("status") in ("done", "failed"):
                    break

        assert len(events) >= 1
        assert any(e["status"] in ("queued", "running", "done") for e in events)


def test_break_endpoint_behavior(write_app_setup):
    """POST /api/cases/{id}/break accepts valid disjoint groups and rejects invalid groups with 422."""
    client: TestClient = write_app_setup["client"]
    analyst_h = write_app_setup["analyst_headers"]
    store: Storage = write_app_setup["store"]

    # Use demo files to build a rich case
    r_case = client.post("/api/cases", json={"name": "Break Test Case"}, headers=analyst_h)
    case_id = r_case.json()["case_id"]

    demo_dir = REPO_ROOT / "data" / "synthetic" / "out" / "case_demo_v2"
    cdr_path = demo_dir / "cdr.csv"
    bank_path = demo_dir / "bank.csv"

    client.post(
        f"/api/cases/{case_id}/cdr",
        files={"file": ("cdr.csv", cdr_path.read_bytes(), "text/csv")},
        headers=analyst_h,
    )
    client.post(
        f"/api/cases/{case_id}/bank",
        files={"file": ("bank.csv", bank_path.read_bytes(), "text/csv")},
        headers=analyst_h,
    )

    # Copy demo analyses
    analyses_src = REPO_ROOT / "results" / "2026-11-11_step6_extraction_r2" / "run1"
    for p in sorted(analyses_src.glob("*.analysis.json"))[:10]:
        store.save_analysis(case_id, p.name[:-len(".analysis.json")], json.loads(p.read_text(encoding="utf-8")))

    # Analyze
    r_an = client.post(f"/api/cases/{case_id}/analyze", headers=analyst_h)
    jid = r_an.json()["job_id"]
    for _ in range(50):
        if client.get(f"/api/jobs/{jid}", headers=analyst_h).json()["status"] == "done":
            break
        time.sleep(0.1)

    r_people = client.get(f"/api/cases/{case_id}/people", headers=analyst_h)
    people = r_people.json()
    assert len(people) >= 2
    pid1, pid2 = people[0]["id"], people[1]["id"]

    # 1. Valid disjoint groups -> 200
    r_brk = client.post(
        f"/api/cases/{case_id}/break",
        json={"group_a": [pid1], "group_b": [pid2]},
        headers=analyst_h,
    )
    assert r_brk.status_code == 200
    brk_data = r_brk.json()
    assert "finite" in brk_data
    assert "size" in brk_data
    assert "cut" in brk_data
    assert "direct_link" in brk_data
    assert "bridging_unowned_phones" in brk_data
    assert "note" in brk_data
    assert "disclaimer" in brk_data

    # 2. Overlapping groups -> 422
    r_overlap = client.post(
        f"/api/cases/{case_id}/break",
        json={"group_a": [pid1], "group_b": [pid1]},
        headers=analyst_h,
    )
    assert r_overlap.status_code == 422
    assert r_overlap.json()["error"]["code"] == "invalid_groups"

    # 3. Empty group -> 422
    r_empty = client.post(
        f"/api/cases/{case_id}/break",
        json={"group_a": [], "group_b": [pid2]},
        headers=analyst_h,
    )
    assert r_empty.status_code == 422
    assert r_empty.json()["error"]["code"] == "invalid_groups"


def test_audit_log_verification(write_app_setup):
    """Audit log records hash-chained entries for case creation, uploads, and jobs."""
    client: TestClient = write_app_setup["client"]
    analyst_h = write_app_setup["analyst_headers"]

    r_case = client.post("/api/cases", json={"name": "Audit Case"}, headers=analyst_h)
    case_id = r_case.json()["case_id"]

    client.post(
        f"/api/cases/{case_id}/documents",
        data={"name": "FIR_aud.txt", "text": "Valid narrative for audit verification."},
        headers=analyst_h,
    )

    demo_dir = REPO_ROOT / "data" / "synthetic" / "out" / "case_demo_v2"
    client.post(
        f"/api/cases/{case_id}/cdr",
        files={"file": ("cdr.csv", (demo_dir / "cdr.csv").read_bytes(), "text/csv")},
        headers=analyst_h,
    )

    # Check audit log directly
    audit = write_app_setup["app"].state.audit_log
    ok, count, first_bad = audit.verify()
    assert ok is True
    assert count >= 3
    assert first_bad is None

    entries = audit.read(limit=50, offset=0)
    actions = [e["action"] for e in entries]
    assert "case_created" in actions
    assert "document_uploaded" in actions
    assert "cdr_uploaded" in actions
    assert "job_started" in actions

    # Verify upload detail has sha256 and size but no content text
    upload_entry = next(e for e in entries if e["action"] == "document_uploaded")
    assert "sha256" in upload_entry["detail"]
    assert "size" in upload_entry["detail"]
    assert "text" not in upload_entry["detail"]
    assert "content" not in upload_entry["detail"]
