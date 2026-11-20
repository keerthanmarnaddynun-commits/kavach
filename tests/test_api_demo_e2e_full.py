"""Comprehensive End-to-End tests for KAVACH API using the full demo case."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from case_detectors.cut_calls import call_layer_graph
from contracts.v1_1.validate import validate_graph
import kavach_api.analysis_service
from kavach_api.analysis_service import build_graph
from kavach_api.app import create_app
from kavach_api.leads import _extract_owner_maps, run_break
from kavach_api.settings import Settings, load_settings
from kavach_api.storage import Storage
from scripts.create_user import create_user
from scripts.load_demo_case import DEMO_CASE_NAME, load_demo_case

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def demo_full_env(tmp_path_factory):
    runtime_dir = tmp_path_factory.mktemp("runtime_demo_full")
    settings = load_settings(
        {
            "KAVACH_RUNTIME_DIR": str(runtime_dir),
            "KAVACH_PBKDF2_ITERATIONS": "1000",
        }
    )

    # 1. Create users via create_user function (G1)
    create_user(settings, "admin_user", "admin", "AdminStrongPass123!")
    create_user(settings, "analyst_user", "analyst", "AnalystStrongPass123!")
    create_user(settings, "viewer_user", "viewer", "ViewerStrongPass123!")

    # 2. Load demo case via load_demo_case (G7)
    demo_info = load_demo_case(settings)

    # 3. Create app and test client
    app = create_app(settings)
    client = TestClient(app)

    # 4. Login via HTTP with user created by create_user (G8)
    resp_login = client.post(
        "/api/auth/login",
        json={"username": "viewer_user", "password": "ViewerStrongPass123!"},
    )
    assert resp_login.status_code == 200, f"Login failed: {resp_login.text}"
    token = resp_login.json()["access_token"]
    viewer_headers = {"Authorization": f"Bearer {token}"}

    return {
        "app": app,
        "client": client,
        "demo_info": demo_info,
        "settings": settings,
        "store": app.state.store,
        "viewer_headers": viewer_headers,
    }


def test_login_and_case_list_row_counts(demo_full_env):
    """Test HTTP login and verify list cases reports cdr_rows and bank_rows matching files.json."""
    client: TestClient = demo_full_env["client"]
    headers = demo_full_env["viewer_headers"]
    case_id = demo_full_env["demo_info"]["case_id"]

    resp = client.get("/api/cases", headers=headers)
    assert resp.status_code == 200
    cases = resp.json()
    demo_case = next((c for c in cases if c["case_id"] == case_id), None)
    assert demo_case is not None
    assert demo_case["analyzed"] is True

    # Read files.json directly to verify exact match (7483 CDR rows, 1489 Bank rows)
    store: Storage = demo_full_env["store"]
    finfo = store.files_info(case_id)
    expected_cdr = finfo["cdr"]["rows"]
    expected_bank = finfo["bank"]["rows"]
    assert expected_cdr == 7483
    assert expected_bank == 1489

    assert demo_case["counts"]["cdr_rows"] == expected_cdr
    assert demo_case["counts"]["bank_rows"] == expected_bank
    assert demo_case["counts"]["documents"] == 100


def test_graph_validation_and_node_counts(demo_full_env):
    """Verify Cytoscape Contract 2 graph validates and node counts per type match stats.json."""
    client: TestClient = demo_full_env["client"]
    headers = demo_full_env["viewer_headers"]
    case_id = demo_full_env["demo_info"]["case_id"]

    resp = client.get(f"/api/cases/{case_id}/graph", headers=headers)
    assert resp.status_code == 200
    graph_data = resp.json()

    # Validate against Contract 2 schema
    validate_graph(graph_data)

    # Read committed stats.json
    stats_file = REPO_ROOT / "data" / "graph" / "out" / "case_demo_v2_r2" / "stats.json"
    assert stats_file.is_file(), f"Stats file missing: {stats_file}"
    stats = json.loads(stats_file.read_text(encoding="utf-8"))
    expected_counts = stats["node_counts_by_type"]
    assert expected_counts == {
        "ACCOUNT": 71,
        "IMEI": 49,
        "PERSON": 155,
        "PHONE": 50,
        "VEHICLE": 100,
    }

    # Count nodes per type from graph elements
    actual_counts: dict[str, int] = {}
    for elem in graph_data.get("elements", {}).get("nodes", []):
        ntype = elem.get("data", {}).get("type")
        actual_counts[ntype] = actual_counts.get(ntype, 0) + 1

    assert actual_counts == expected_counts


def test_leads_presence(demo_full_env):
    """Verify leads endpoint returns non-empty leads data."""
    client: TestClient = demo_full_env["client"]
    headers = demo_full_env["viewer_headers"]
    case_id = demo_full_env["demo_info"]["case_id"]

    resp = client.get(f"/api/cases/{case_id}/leads", headers=headers)
    assert resp.status_code == 200
    leads = resp.json()

    assert "money_flow" in leads
    assert len(leads["money_flow"]) > 0
    assert len(leads["mule_accounts"]) > 0
    assert len(leads["burner_phones"]) > 0
    assert len(leads["role_chips"]) > 0
    assert "disclaimer" in leads


def test_evidence_spans_slice_back_to_text(demo_full_env):
    """Verify at least 10 nodes and 10 edges have FIR spans that slice back exactly to surface text."""
    client: TestClient = demo_full_env["client"]
    headers = demo_full_env["viewer_headers"]
    case_id = demo_full_env["demo_info"]["case_id"]
    store: Storage = demo_full_env["store"]

    # 1. Test 10+ nodes
    graph = build_graph(store, case_id)
    verified_nodes = 0

    for node in graph.get("nodes", []):
        nid = node["id"]
        r_node = client.get(f"/api/cases/{case_id}/nodes/{nid}", headers=headers)
        if r_node.status_code != 200:
            continue
        ndata = r_node.json()
        fir_evidence = ndata.get("fir_evidence", [])
        if not fir_evidence:
            continue

        for span in fir_evidence:
            doc_id = span.get("doc_id")
            char_span = span.get("char_span")
            expected_text = span.get("surface")
            if not doc_id or not char_span or expected_text is None:
                continue

            start, end = char_span[0], char_span[1]
            _meta, doc_text = store.get_document(case_id, doc_id)
            assert doc_text[start:end] == expected_text, (
                f"Node {nid} span slice mismatch in {doc_id}: "
                f"{doc_text[start:end]!r} != {expected_text!r}"
            )
        verified_nodes += 1
        if verified_nodes >= 10:
            break

    assert verified_nodes >= 10, f"Verified only {verified_nodes} nodes with FIR spans"

    # 2. Test 10+ edges
    r_graph = client.get(f"/api/cases/{case_id}/graph", headers=headers)
    assert r_graph.status_code == 200
    cyto_edges = r_graph.json().get("elements", {}).get("edges", [])

    verified_edges = 0
    for edge_elem in cyto_edges:
        edata_inner = edge_elem.get("data", {})
        eid = edata_inner.get("id")
        if not eid:
            continue
        r_edge = client.get(f"/api/cases/{case_id}/edges/{eid}", headers=headers)
        if r_edge.status_code != 200:
            continue
        edata = r_edge.json()
        fir_evidence = edata.get("fir_evidence", [])
        if not fir_evidence:
            continue

        for span in fir_evidence:
            doc_id = span.get("doc_id")
            char_span = span.get("char_span")
            expected_text = span.get("surface")
            if not doc_id or not char_span or expected_text is None:
                continue

            start, end = char_span[0], char_span[1]
            _meta, doc_text = store.get_document(case_id, doc_id)
            assert doc_text[start:end] == expected_text, (
                f"Edge {eid} span slice mismatch in {doc_id}: "
                f"{doc_text[start:end]!r} != {expected_text!r}"
            )
        verified_edges += 1
        if verified_edges >= 10:
            break

    assert verified_edges >= 10, f"Verified only {verified_edges} edges with FIR spans"


def test_timeline_sums_equal_csv_rows(demo_full_env):
    """Verify timeline sums equal CSV rows for day and hour buckets."""
    client: TestClient = demo_full_env["client"]
    headers = demo_full_env["viewer_headers"]
    case_id = demo_full_env["demo_info"]["case_id"]

    for bucket in ("day", "hour"):
        resp = client.get(f"/api/cases/{case_id}/timeline?bucket={bucket}", headers=headers)
        assert resp.status_code == 200
        tl = resp.json()

        total_calls = sum(b.get("count", 0) for b in tl.get("calls", []))
        total_transfers = sum(b.get("count", 0) for b in tl.get("transfers", []))

        assert total_calls == 7483, f"Calls sum in {bucket} timeline ({total_calls}) != 7483"
        assert total_transfers == 1489, f"Transfers sum in {bucket} timeline ({total_transfers}) != 1489"


def test_openapi_surface_matches_a2(demo_full_env):
    """Verify OpenAPI contains every method and path in A.2."""
    app = demo_full_env["app"]
    schema = app.openapi()
    paths = schema.get("paths", {})

    expected_endpoints = [
        ("GET", "/api/health"),
        ("POST", "/api/auth/login"),
        ("GET", "/api/auth/me"),
        ("POST", "/api/admin/users"),
        ("GET", "/api/admin/audit"),
        ("GET", "/api/admin/audit/verify"),
        ("GET", "/api/cases"),
        ("POST", "/api/cases"),
        ("GET", "/api/cases/{case_id}"),
        ("POST", "/api/cases/{case_id}/documents"),
        ("POST", "/api/cases/{case_id}/cdr"),
        ("POST", "/api/cases/{case_id}/bank"),
        ("POST", "/api/cases/{case_id}/analyze"),
        ("GET", "/api/jobs/{job_id}"),
        ("GET", "/api/jobs/{job_id}/events"),
        ("GET", "/api/cases/{case_id}/graph"),
        ("GET", "/api/cases/{case_id}/leads"),
        ("GET", "/api/cases/{case_id}/people"),
        ("GET", "/api/cases/{case_id}/nodes/{node_id}"),
        ("GET", "/api/cases/{case_id}/edges/{edge_id}"),
        ("GET", "/api/cases/{case_id}/documents/{doc_id}"),
        ("GET", "/api/cases/{case_id}/rows"),
        ("GET", "/api/cases/{case_id}/timeline"),
        ("POST", "/api/cases/{case_id}/break"),
    ]

    for method, path in expected_endpoints:
        assert path in paths, f"Path {path} missing from OpenAPI"
        assert method.lower() in paths[path], f"Method {method} for {path} missing from OpenAPI"


def test_direct_link_evaluation(demo_full_env):
    """Verify direct_link is True for 2 persons with direct call in demo CDR, False for 2 with none."""
    store: Storage = demo_full_env["store"]
    case_id = demo_full_env["demo_info"]["case_id"]
    graph = build_graph(store, case_id)

    owners = _extract_owner_maps(graph)["phone_to_persons"]
    cdr_rows = []
    with open(store.csv_path(case_id, "cdr"), "r", encoding="utf-8", newline="") as f:
        import csv
        reader = csv.DictReader(f)
        for r in reader:
            cdr_rows.append(r)

    call_graph = call_layer_graph(cdr_rows, owners)

    # 1. Find a connected pair with direct edge in call graph
    connected_pair = None
    for e in call_graph.get("edges", []):
        u = e.get("source")
        v = e.get("target")
        if u and v and u != v:
            connected_pair = (u, v)
            break

    assert connected_pair is not None, "Could not find a connected person pair in demo call graph"
    res_direct = run_break(store, case_id, [connected_pair[0]], [connected_pair[1]])
    assert res_direct["direct_link"] is True, f"Expected direct_link True for {connected_pair}"

    # 2. Find a disconnected pair with no edge between them
    connected_pairs_set = {
        (e["source"], e["target"]) for e in call_graph.get("edges", [])
    } | {
        (e["target"], e["source"]) for e in call_graph.get("edges", [])
    }
    all_persons = [n["id"] for n in graph.get("nodes", []) if n.get("type") == "PERSON"]
    disconnected_pair = None
    for u in all_persons:
        for v in all_persons:
            if u != v and (u, v) not in connected_pairs_set:
                disconnected_pair = (u, v)
                break
        if disconnected_pair:
            break

    assert disconnected_pair is not None, "Could not find a disconnected person pair in demo graph"
    res_no_direct = run_break(store, case_id, [disconnected_pair[0]], [disconnected_pair[1]])
    assert res_no_direct["direct_link"] is False, f"Expected direct_link False for {disconnected_pair}"


def test_graph_caching_and_invalidation(tmp_path):
    """Verify build_case_graph: 0 calls on second build_graph, 1 call after document added."""
    runtime_dir = tmp_path / "runtime_cache"
    settings = load_settings(
        {
            "KAVACH_RUNTIME_DIR": str(runtime_dir),
            "KAVACH_PBKDF2_ITERATIONS": "1000",
        }
    )
    demo_info = load_demo_case(settings)
    store = Storage(settings)
    case_id = demo_info["case_id"]

    # At this point, demo case is analyzed and graph is cached.
    with patch("kavach_api.analysis_service.build_case_graph", wraps=kavach_api.analysis_service.build_case_graph) as mock_builder:
        # Second build_graph call -> cache hit -> 0 calls to builder
        g1 = build_graph(store, case_id)
        assert mock_builder.call_count == 0

        # Now add a document to the case, changing the case fingerprint
        new_text = "LANG: english\n[[PERSON:P999:S|Random Person]] made a call.\n"
        store.add_document(
            case_id=case_id,
            filename="FIR_999.txt",
            raw_bytes=new_text.encode("utf-8"),
            uploaded_by="analyst",
        )
        store.save_analysis(
            case_id,
            "FIR_999",
            {
                "info": {"document_hash": "dummy"},
                "doc": {"source_doc_id": "FIR_999", "entities": [], "relations": []},
            },
        )

        # Third build_graph call -> cache invalidation -> 1 call to builder
        g2 = build_graph(store, case_id)
        assert mock_builder.call_count == 1


def test_load_demo_case_tampered_analysis_raises(tmp_path):
    """Verify load_demo_case refuses with ValueError when an analysis document_hash mismatches."""
    runtime_dir = tmp_path / "runtime_tamper"
    settings = load_settings(
        {
            "KAVACH_RUNTIME_DIR": str(runtime_dir),
            "KAVACH_PBKDF2_ITERATIONS": "1000",
        }
    )

    # Prepare tampered analyses folder
    tamper_analyses_dir = tmp_path / "tampered_analyses"
    tamper_analyses_dir.mkdir(parents=True)
    real_analyses_dir = REPO_ROOT / "results" / "2026-11-11_step6_extraction_r2" / "run1"

    # Copy files and tamper one file
    for apath in real_analyses_dir.glob("*.analysis.json"):
        content = json.loads(apath.read_text(encoding="utf-8"))
        if apath.name == "FIR_01.analysis.json":
            content.setdefault("info", {})["document_hash"] = "0" * 64
        (tamper_analyses_dir / apath.name).write_text(
            json.dumps(content),
            encoding="utf-8",
        )

    with pytest.raises(ValueError, match="Analysis text hash mismatch"):
        load_demo_case(
            settings=settings,
            analyses_dir=tamper_analyses_dir,
        )
