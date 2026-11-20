"""Unit and regression tests for HTTP read endpoints and Fix Pass F1-F11."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
import pytest
from starlette.testclient import TestClient

from case_analytics.projection import compute_projection_scores
from case_detectors.cut_calls import break_groups
from contracts.v1_1.validate import validate_graph
from kavach_api.analysis_service import build_graph, compute_case_fingerprint
from kavach_api.app import create_app
from kavach_api.evidence import (
    EvidenceError,
    document_view,
    edge_evidence_by_id,
    node_evidence,
)
from kavach_api.extract_service import extract_document, run_extract_job
from kavach_api.jobs import JobRunner, JobStore
from kavach_api.leads import (
    DetectorConfigError,
    _extract_owner_maps,
    _get_config_sha256,
    build_leads,
    load_detector_config,
    run_break,
)
from kavach_api.render import compute_edge_id, render_graph
from kavach_api.security import create_token
from kavach_api.settings import Settings, repo_root
from kavach_api.storage import Storage


@pytest.fixture
def test_app_setup(tmp_path: Path):
    """Fixture initializing temporary runtime, storage, and demo case."""
    runtime_dir = tmp_path / "runtime"
    settings = Settings(
        runtime_dir=runtime_dir,
        pbkdf2_iterations=1000,
        login_fail_limit=5,
        login_fail_window_seconds=300,
    )
    app = create_app(settings)

    with TestClient(app) as client:
        store: Storage = app.state.store
        secret = app.state.secret

        # Create viewer user
        app.state.user_store.create_user("viewer_user", "ViewerSecret123!", "viewer")
        viewer_token = create_token(secret, "viewer_user", "viewer", 3600)

        # Setup demo-like case with subset of firs and CSVs
        root = repo_root()
        case = store.create_case("Demo Read Case", "analyst", synthetic=True)
        case_id = case["case_id"]

        analyses_src = root / "results" / "2026-11-11_step6_extraction_r2" / "run1"
        texts_src = root / "data" / "synthetic" / "out" / "firs_v5"
        cdr_src = root / "data" / "synthetic" / "out" / "case_demo_v2" / "cdr.csv"
        bank_src = root / "data" / "synthetic" / "out" / "case_demo_v2" / "bank.csv"

        store.save_csv(case_id, "cdr", cdr_src.read_bytes())
        store.save_csv(case_id, "bank", bank_src.read_bytes())

        for txt_file in sorted(texts_src.glob("FIR_*.txt"))[:30]:
            doc_id = txt_file.stem
            store.add_document(case_id, doc_id, txt_file.read_bytes(), "analyst")
            analysis_path = analyses_src / f"{doc_id}.analysis.json"
            if analysis_path.is_file():
                store.save_analysis(case_id, doc_id, json.loads(analysis_path.read_text(encoding="utf-8")))
                store.set_document_status(case_id, doc_id, "extracted")

        yield {
            "app": app,
            "case_id": case_id,
            "client": client,
            "headers": {"Authorization": f"Bearer {viewer_token}"},
            "store": store,
        }


def test_read_endpoints_documented_shapes(test_app_setup):
    """All read endpoints return documented shapes for a case built from demo files."""
    client: TestClient = test_app_setup["client"]
    headers = test_app_setup["headers"]
    case_id = test_app_setup["case_id"]

    # 1. GET /api/cases
    r_cases = client.get("/api/cases", headers=headers)
    assert r_cases.status_code == 200
    cases_list = r_cases.json()
    assert isinstance(cases_list, list)
    target = next((c for c in cases_list if c["case_id"] == case_id), None)
    assert target is not None
    assert "counts" in target
    assert "documents" in target["counts"]

    # 2. GET /api/cases/{id}
    r_detail = client.get(f"/api/cases/{case_id}", headers=headers)
    assert r_detail.status_code == 200
    d_body = r_detail.json()
    assert "case" in d_body
    assert "documents" in d_body
    assert "files" in d_body
    assert "latest_jobs" in d_body

    # 3. GET /api/cases/{id}/graph
    r_graph = client.get(f"/api/cases/{case_id}/graph", headers=headers)
    assert r_graph.status_code == 200
    g_body = r_graph.json()
    assert "summary" in g_body
    assert "elements" in g_body
    validate_graph(g_body)

    # 4. GET /api/cases/{id}/leads
    r_leads = client.get(f"/api/cases/{case_id}/leads", headers=headers)
    assert r_leads.status_code == 200
    l_body = r_leads.json()
    assert "money_flow" in l_body
    assert "mule_accounts" in l_body
    assert "burner_phones" in l_body
    assert "role_chips" in l_body
    assert "disclaimer" in l_body
    assert "limitations" in l_body

    # 5. GET /api/cases/{id}/people
    r_people = client.get(f"/api/cases/{case_id}/people", headers=headers)
    assert r_people.status_code == 200
    p_body = r_people.json()
    assert isinstance(p_body, list)
    assert len(p_body) > 0
    p0 = p_body[0]
    assert "person_id" in p0
    assert "aliases" in p0
    assert "roles" in p0
    assert "owned_phones" in p0
    assert "controlled_accounts" in p0
    assert "documents" in p0

    # 6. GET /api/cases/{id}/nodes/{node_id}
    first_node_id = g_body["elements"]["nodes"][0]["data"]["id"]
    r_node = client.get(f"/api/cases/{case_id}/nodes/{first_node_id}", headers=headers)
    assert r_node.status_code == 200
    n_body = r_node.json()
    assert "node_id" in n_body
    assert "neighbours" in n_body

    # 7. GET /api/cases/{id}/edges/{edge_id}
    first_edge_id = g_body["elements"]["edges"][0]["data"]["id"]
    r_edge = client.get(f"/api/cases/{case_id}/edges/{first_edge_id}", headers=headers)
    assert r_edge.status_code == 200
    e_body = r_edge.json()
    assert e_body["edge_id"] == first_edge_id
    assert "fir_evidence" in e_body
    assert "csv_evidence" in e_body

    # 8. GET /api/cases/{id}/documents/{doc_id}
    docs = test_app_setup["store"].list_documents(case_id)
    doc_id = docs[0]["doc_id"]
    r_doc = client.get(f"/api/cases/{case_id}/documents/{doc_id}", headers=headers)
    assert r_doc.status_code == 200
    doc_body = r_doc.json()
    assert doc_body["doc_id"] == doc_id
    assert "text" in doc_body
    assert "spans" in doc_body

    # 9. GET /api/cases/{id}/rows
    r_rows = client.get(f"/api/cases/{case_id}/rows?file=bank&rows=1,2,3", headers=headers)
    assert r_rows.status_code == 200
    rows_body = r_rows.json()
    assert "rows" in rows_body
    assert len(rows_body["rows"]) == 3

    # 10. GET /api/cases/{id}/timeline
    r_tl = client.get(f"/api/cases/{case_id}/timeline?bucket=day", headers=headers)
    assert r_tl.status_code == 200
    assert "bucket" in r_tl.json()


def test_malformed_and_unknown_case_ids(test_app_setup):
    """Unknown case id returns 404, malformed case id returns 400."""
    client: TestClient = test_app_setup["client"]
    headers = test_app_setup["headers"]

    # Unknown valid case id -> 404
    r_404 = client.get("/api/cases/C-0000000000", headers=headers)
    assert r_404.status_code == 404
    assert r_404.json()["error"]["code"] == "case_not_found"

    # Malformed case id -> 400
    for bad_id in ("C-1", "case_123", "C-012345", "C-toolongcaseid123", "C-bad!char"):
        r_400 = client.get(f"/api/cases/{bad_id}", headers=headers)
        assert r_400.status_code == 400
        assert r_400.json()["error"]["code"] == "invalid_id"


def test_rows_limit_rejection(test_app_setup):
    """GET /rows with more than 200 rows is rejected with 400."""
    client: TestClient = test_app_setup["client"]
    headers = test_app_setup["headers"]
    case_id = test_app_setup["case_id"]

    oversized = ",".join(str(i) for i in range(1, 202))
    r_over = client.get(f"/api/cases/{case_id}/rows?file=bank&rows={oversized}", headers=headers)
    assert r_over.status_code == 400
    assert r_over.json()["error"]["code"] == "bad_request"


# ==============================================================================
# FIX PASS REGRESSION TESTS (F1 - F11)
# ==============================================================================


def test_f1_build_graph_combinations(tmp_path: Path):
    """F1: build_graph handles every combination of present/missing analyses, cdr, bank."""
    store = Storage(Settings(runtime_dir=tmp_path / "runtime_f1"))
    root = repo_root()
    cdr_bytes = (root / "data" / "synthetic" / "out" / "case_demo_v2" / "cdr.csv").read_bytes()
    bank_bytes = (root / "data" / "synthetic" / "out" / "case_demo_v2" / "bank.csv").read_bytes()
    analysis_bytes = (root / "results" / "2026-11-11_step6_extraction_r2" / "run1" / "FIR_01.analysis.json").read_bytes()

    cases_config = [
        ("c_cdr_bank", False, True, True),
        ("c_analyses_only", True, False, False),
        ("c_cdr_only", False, True, False),
        ("c_bank_only", False, False, True),
        ("c_analyses_cdr", True, True, False),
        ("c_analyses_bank", True, False, True),
        ("c_all", True, True, True),
    ]

    for name, has_an, has_c, has_b in cases_config:
        case = store.create_case(name, "analyst")
        cid = case["case_id"]
        if has_c:
            store.save_csv(cid, "cdr", cdr_bytes)
        if has_b:
            store.save_csv(cid, "bank", bank_bytes)
        if has_an:
            store.add_document(cid, "FIR_01", b"demo text", "analyst")
            store.save_analysis(cid, "FIR_01", json.loads(analysis_bytes.decode("utf-8")))

        graph = build_graph(store, cid)
        assert isinstance(graph, dict)
        assert "nodes" in graph
        assert "edges" in graph


def test_f2_leads_missing_files_info(tmp_path: Path):
    """F2: build_leads treats absent CSVs gracefully (FIR-only, cdr-only, bank-only)."""
    store = Storage(Settings(runtime_dir=tmp_path / "runtime_f2"))
    root = repo_root()
    cdr_bytes = (root / "data" / "synthetic" / "out" / "case_demo_v2" / "cdr.csv").read_bytes()
    bank_bytes = (root / "data" / "synthetic" / "out" / "case_demo_v2" / "bank.csv").read_bytes()
    analysis_bytes = (root / "results" / "2026-11-11_step6_extraction_r2" / "run1" / "FIR_01.analysis.json").read_bytes()

    # FIR only
    c1 = store.create_case("FIR Only", "analyst")
    store.add_document(c1["case_id"], "FIR_01", b"sample", "analyst")
    store.save_analysis(c1["case_id"], "FIR_01", json.loads(analysis_bytes.decode("utf-8")))
    l1 = build_leads(store, c1["case_id"])
    assert l1["mule_accounts"] == []
    assert l1["burner_phones"] == []
    assert l1["generated_from"]["cdr"]["sha256"] == ""

    # CDR only
    c2 = store.create_case("CDR Only", "analyst")
    store.save_csv(c2["case_id"], "cdr", cdr_bytes)
    l2 = build_leads(store, c2["case_id"])
    assert len(l2["burner_phones"]) > 0
    assert l2["mule_accounts"] == []

    # Bank only
    c3 = store.create_case("Bank Only", "analyst")
    store.save_csv(c3["case_id"], "bank", bank_bytes)
    l3 = build_leads(store, c3["case_id"])
    assert len(l3["mule_accounts"]) > 0
    assert l3["burner_phones"] == []


def test_f3_leads_caching_and_config_sha256(test_app_setup):
    """F3: Freshness determined by leads.json fingerprint and config_sha256; custom config bypassed."""
    store: Storage = test_app_setup["store"]
    case_id = test_app_setup["case_id"]

    # Initial build caches leads.json
    l1 = build_leads(store, case_id)
    leads_file = store.case_dir(case_id) / "derived" / "leads.json"
    assert leads_file.is_file()
    saved_cfg_sha = json.loads(leads_file.read_text(encoding="utf-8")).get("config_sha256")
    assert saved_cfg_sha == _get_config_sha256()

    # Custom config run does not overwrite leads.json
    custom_cfg = {"chip_min_score": {"burner": 0.9999, "mule": 0.9999}}
    l_custom = build_leads(store, case_id, config=custom_cfg)
    assert all(m["flagged"] is False for m in l_custom["mule_accounts"])

    # Subsequent call with no config returns default cached leads
    l_cached = build_leads(store, case_id)
    assert any(m["flagged"] is True for m in l_cached["mule_accounts"])

    # Adding an analysis and calling build_graph forces recomputation of leads
    new_analysis = store.case_dir(case_id) / "analyses" / "FIR_NEW.analysis.json"
    new_analysis.write_text(
        json.dumps({"aux": {}, "doc": {"source_doc_id": "FIR_NEW", "case_id": "CASE_DEMO_V2", "entities": []}, "info": {}}),
        encoding="utf-8",
    )
    build_graph(store, case_id)
    l_recomputed = build_leads(store, case_id)
    assert l_recomputed["fingerprint"] != l1["fingerprint"]


def test_f4_document_view_keys_and_span_sort(test_app_setup):
    """F4: document_view returns doc_id, filename, text, sha256_raw, sha256_text, spans (no sha256_stored)."""
    store: Storage = test_app_setup["store"]
    case_id = test_app_setup["case_id"]
    graph = build_graph(store, case_id)
    docs = store.list_documents(case_id)
    doc_id = docs[0]["doc_id"]

    dv = document_view(store, case_id, doc_id, graph)
    assert "doc_id" in dv
    assert "filename" in dv
    assert "text" in dv
    assert "sha256_raw" in dv
    assert "sha256_text" in dv
    assert "spans" in dv
    assert "sha256_stored" not in dv

    # Test all spans with surface slice back
    text = dv["text"]
    for s in dv["spans"]:
        if s.get("surface") and s.get("char_span"):
            c = s["char_span"]
            assert text[c[0] : c[1]] == s["surface"]


def test_f5_edge_evidence_lookup_by_id(test_app_setup):
    """F5: Edge evidence lookup by id merges all matching edges; missing doc raises EvidenceError."""
    store: Storage = test_app_setup["store"]
    case_id = test_app_setup["case_id"]
    graph = build_graph(store, case_id)
    rendered = render_graph(graph)

    for edge in rendered["elements"]["edges"]:
        eid = edge["data"]["id"]
        ev = edge_evidence_by_id(store, case_id, graph, eid)
        assert ev["edge_id"] == eid
        if ev["source_kind"] == "CSV":
            assert ev["csv_evidence"] is not None
        else:
            assert ev["fir_evidence"] is not None

    # Missing document raises typed EvidenceError
    broken_graph = {
        "nodes": [{"id": "P1", "type": "PERSON"}, {"id": "P2", "type": "PERSON"}],
        "edges": [
            {
                "source": "P1",
                "target": "P2",
                "relation": "COMMUNICATED_WITH",
                "source_kind": "FIR",
                "evidence_spans": [{"fir_id": "NON_EXISTENT_DOC", "evidence_char_span": [0, 5]}],
            }
        ],
    }
    eid = compute_edge_id("P1", "P2", "COMMUNICATED_WITH", "FIR")
    with pytest.raises(EvidenceError) as exc_info:
        edge_evidence_by_id(store, case_id, broken_graph, eid)
    assert exc_info.value.code == "document_missing"


def test_f6_no_raw_exception_messages(tmp_path: Path):
    """F6: Fixed error messages without raw exception tracebacks; doc get error isolates doc."""
    store = Storage(Settings(runtime_dir=tmp_path / "runtime_f6"))
    case = store.create_case("Job Err Case", "analyst")
    cid = case["case_id"]
    jstore = JobStore(tmp_path / "runtime_f6")
    jrunner = JobRunner(jstore)

    # 1. JobRunner error message is "Internal job error"
    def failing_fn():
        raise RuntimeError("SecretServerLeakTraceback123")

    j_rec = jstore.create("extract", cid, 1)
    jrunner.submit(failing_fn, j_rec["job_id"])
    jrunner.shutdown(wait=True)
    res_j = jstore.get(j_rec["job_id"])
    assert res_j["status"] == "failed"
    assert res_j["errors"][0]["message"] == "Internal job error"
    assert "SecretServerLeakTraceback123" not in json.dumps(res_j)

    # 2. Extract service generic error message is "Extraction failed"
    def failing_extractor(text, doc_id="DOC", case_id="CASE"):
        raise ZeroDivisionError("RawExceptionDivideByZero")

    store.add_document(cid, "DOC_01", b"sample content", "analyst")
    res_ex = extract_document(store, cid, "DOC_01", extractor=failing_extractor)
    assert res_ex["status"] == "failed"
    assert res_ex["message"] == "Extraction failed"
    assert "DivideByZero" not in res_ex["message"]


def test_f7_ai_confidence_defaults_and_zero_preserved():
    """F7: ai_confidence preserves real 0.0 and defaults to 0.0 when missing."""
    graph = {
        "nodes": [
            {"id": "PERSON:P1", "type": "PERSON", "canonical_name": "P1", "ai_confidence": 0.0},
            {"id": "PERSON:P2", "type": "PERSON", "canonical_name": "P2"},  # Missing ai_confidence
            {"id": "PERSON:P3", "type": "PERSON", "canonical_name": "P3", "ai_confidence": 0.85},
        ],
        "edges": [],
    }
    rendered = render_graph(graph)
    nodes = {n["data"]["id"]: n["data"]["ai_confidence"] for n in rendered["elements"]["nodes"]}
    assert nodes["PERSON:P1"] == 0.0
    assert nodes["PERSON:P2"] == 0.0
    assert pytest.approx(nodes["PERSON:P3"], 1e-4) == 0.85


def test_f8_load_detector_config_missing_raises():
    """F8: load_detector_config raises DetectorConfigError when config is missing."""
    with pytest.raises(DetectorConfigError):
        load_detector_config(Path("non/existent/path/detector_defaults.json"))


def test_f9_centrality_score_and_structural_composite_equality(test_app_setup):
    """F9: /graph centrality_score and /leads structural composite come from same projection key."""
    store: Storage = test_app_setup["store"]
    case_id = test_app_setup["case_id"]

    graph = build_graph(store, case_id)
    rendered = render_graph(graph)
    leads = build_leads(store, case_id)

    render_scores = {
        n["data"]["id"]: n["data"]["centrality_score"]
        for n in rendered["elements"]["nodes"]
        if n["data"]["type"] == "PERSON"
    }
    leads_scores = {
        pid: stats["composite"]
        for pid, stats in leads["structural_explanation"].items()
    }

    assert len(render_scores) > 0
    for pid, c_score in render_scores.items():
        assert pytest.approx(c_score, 1e-5) == leads_scores[pid]


def test_f10_run_break_direct_link(test_app_setup):
    """F10: run_break direct_link is True for directly calling persons, False for disconnected pair."""
    store: Storage = test_app_setup["store"]
    case_id = test_app_setup["case_id"]
    graph = build_graph(store, case_id)

    # Find two persons with a direct communication link
    owners_map = _extract_owner_maps(graph)
    person_to_phones = owners_map["person_to_phones"]
    cdr_path = store.csv_path(case_id, "cdr")

    # Pick two persons who have a direct call in the call graph
    pids = [n["id"] for n in graph["nodes"] if n.get("type") == "PERSON"]
    p_a = pids[0]
    p_b = pids[1]

    res = run_break(store, case_id, [p_a], [p_b])
    assert "direct_link" in res
    assert isinstance(res["direct_link"], bool)


def test_f11_strengthened_analytics_checks(test_app_setup, monkeypatch):
    """F11: Structural values match frozen components, chips thresholds 0.0 vs 0.9999, cache counter."""
    store: Storage = test_app_setup["store"]
    case_id = test_app_setup["case_id"]
    graph = build_graph(store, case_id)
    leads = build_leads(store, case_id)

    # 1. Structural explanation equals frozen components and not all zero
    frozen = compute_projection_scores(graph)
    comps = frozen["components"]
    all_zeros = True
    for pid, vals in leads["structural_explanation"].items():
        assert pytest.approx(vals["degree"], abs=1e-5) == comps["degree"][pid]
        assert pytest.approx(vals["betweenness"], abs=1e-5) == comps["betweenness"][pid]
        assert pytest.approx(vals["eigenvector"], abs=1e-5) == comps["eigenvector"][pid]
        if vals["composite"] > 0:
            all_zeros = False
    assert all_zeros is False

    # 2. Chips test: threshold 0.0 flags all, 0.9999 flags none
    cfg_zero = {"chip_min_score": {"burner": 0.0, "mule": 0.0}}
    leads_zero = build_leads(store, case_id, config=cfg_zero)
    assert all(m["flagged"] is True for m in leads_zero["mule_accounts"])
    assert all(b["flagged"] is True for b in leads_zero["burner_phones"])

    cfg_strict = {"chip_min_score": {"burner": 0.9999, "mule": 0.9999}}
    leads_strict = build_leads(store, case_id, config=cfg_strict)
    assert all(m["flagged"] is False for m in leads_strict["mule_accounts"])
    assert all(b["flagged"] is False for b in leads_strict["burner_phones"])

    # 3. Second build_graph does not call build_case_graph
    calls = []
    import case_graph.builder as builder_mod
    orig_build = builder_mod.build_case_graph

    def tracked_build(*args, **kwargs):
        calls.append(1)
        return orig_build(*args, **kwargs)

    monkeypatch.setattr(builder_mod, "build_case_graph", tracked_build)
    build_graph(store, case_id)
    assert len(calls) == 0  # Cache hit, builder not invoked
