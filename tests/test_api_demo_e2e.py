"""End-to-end tests for reference demo case loader, OpenAPI export, and API queries."""
from __future__ import annotations

import json
from pathlib import Path
import time
from typing import Any

from fastapi.testclient import TestClient
import pytest

from contracts.v1_1.validate import validate_graph
from kavach_api.app import create_app
from kavach_api.security import create_token
from kavach_api.settings import Settings
from scripts.export_openapi import export_openapi
from scripts.load_demo_case import DEMO_CASE_NAME, load_demo_case

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def demo_e2e_setup(tmp_path: Path):
    """Fixture initializing temporary runtime and loading the reference demo case."""
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)

    settings = Settings(
        runtime_dir=runtime_dir,
        pbkdf2_iterations=1000,
        jwt_ttl_minutes=60,
    )

    # Load demo case using script loader
    demo_info = load_demo_case(settings)

    # Initialize app and users
    app = create_app(settings=settings)
    user_store = app.state.user_store
    user_store.create_user("viewer_user", "ViewerSecret123!", "viewer")

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
        "settings": settings,
        "demo_info": demo_info,
        "viewer_headers": {"Authorization": f"Bearer {viewer_token}"},
        "runtime_dir": runtime_dir,
    }

    app.state.job_runner.shutdown()


def test_demo_case_loader_and_duplicate_prevention(demo_e2e_setup):
    """Demo loader populates case records and refuses duplicate loading attempts."""
    settings = demo_e2e_setup["settings"]
    demo_info = demo_e2e_setup["demo_info"]

    assert demo_info["name"] == DEMO_CASE_NAME
    assert demo_info["documents"] == 100
    assert demo_info["cdr_rows"] > 0
    assert demo_info["bank_rows"] > 0

    # Attempting to load demo case again in same runtime directory must raise RuntimeError
    with pytest.raises(RuntimeError) as exc_info:
        load_demo_case(settings)
    assert "already exists" in str(exc_info.value)


def test_query_loaded_demo_case_via_api(demo_e2e_setup):
    """Loaded demo case is fully queryable across read endpoints."""
    client: TestClient = demo_e2e_setup["client"]
    headers = demo_e2e_setup["viewer_headers"]
    case_id = demo_e2e_setup["demo_info"]["case_id"]

    # 1. GET /api/cases
    r_cases = client.get("/api/cases", headers=headers)
    assert r_cases.status_code == 200
    cases_list = r_cases.json()
    demo_entry = next((c for c in cases_list if c["case_id"] == case_id), None)
    assert demo_entry is not None
    assert demo_entry["analyzed"] is True
    assert demo_entry["counts"]["documents"] == 100

    # 2. GET /api/cases/{id}
    r_detail = client.get(f"/api/cases/{case_id}", headers=headers)
    assert r_detail.status_code == 200
    d_body = r_detail.json()
    assert d_body["case"]["name"] == DEMO_CASE_NAME
    assert len(d_body["documents"]) == 100
    assert d_body["files"]["cdr"] is not None
    assert d_body["files"]["bank"] is not None

    # 3. GET /api/cases/{id}/graph validates against Cytoscape Contract 2 schema
    r_graph = client.get(f"/api/cases/{case_id}/graph", headers=headers)
    assert r_graph.status_code == 200
    graph_data = r_graph.json()
    validate_graph(graph_data)
    assert graph_data["summary"]["total_nodes"] > 0
    assert graph_data["summary"]["total_edges"] > 0

    # 4. GET /api/cases/{id}/leads
    r_leads = client.get(f"/api/cases/{case_id}/leads", headers=headers)
    assert r_leads.status_code == 200
    leads_data = r_leads.json()
    assert len(leads_data["money_flow"]) > 0
    assert len(leads_data["mule_accounts"]) > 0
    assert len(leads_data["burner_phones"]) > 0
    assert len(leads_data["role_chips"]) > 0

    # 5. GET /api/cases/{id}/people
    r_people = client.get(f"/api/cases/{case_id}/people", headers=headers)
    assert r_people.status_code == 200
    people = r_people.json()
    assert len(people) > 0
    first_person = people[0]
    assert "person_id" in first_person
    assert "owned_phones" in first_person
    assert "controlled_accounts" in first_person

    # 6. GET /api/cases/{id}/timeline
    r_timeline = client.get(f"/api/cases/{case_id}/timeline?bucket=day", headers=headers)
    assert r_timeline.status_code == 200
    tl = r_timeline.json()
    assert "calls" in tl
    assert "transfers" in tl

    # 7. Audit log contains demo_loaded entry
    audit = demo_e2e_setup["app"].state.audit_log
    entries = audit.read(limit=50, offset=0)
    assert any(e["action"] == "demo_loaded" for e in entries)


def test_export_openapi_script(tmp_path: Path):
    """export_openapi exports sorted-key valid JSON containing API endpoints."""
    out_file = tmp_path / "openapi_test.json"
    export_openapi(out_file)

    assert out_file.is_file()
    assert out_file.stat().st_size >= 2000

    content = out_file.read_text(encoding="utf-8")
    parsed = json.loads(content)
    assert "openapi" in parsed
    assert "paths" in parsed
    assert "/api/health" in parsed["paths"]
    assert "/api/cases" in parsed["paths"]
    assert "/api/cases/{case_id}/leads" in parsed["paths"]
