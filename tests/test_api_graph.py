"""Unit tests for graph building, caching, and Contract 2 rendering."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import pytest

from contracts.v1_1.validate import validate_graph
from kavach_api.analysis_service import (
    NothingToAnalyzeError,
    build_graph,
    compute_case_fingerprint,
)
from kavach_api.render import render_graph
from kavach_api.settings import Settings, repo_root
from kavach_api.storage import Storage


@pytest.fixture
def temp_store(tmp_path: Path) -> Storage:
    """Fixture providing Storage with temporary runtime directory."""
    return Storage(Settings(runtime_dir=tmp_path / "runtime"))


def _setup_demo_case(store: Storage) -> tuple[str, dict[str, Any]]:
    """Helper to populate a temporary case with demo analyses and CSVs."""
    root = repo_root()
    case = store.create_case("Demo Case", "test_user", synthetic=True)
    case_id = case["case_id"]

    analyses_src = root / "results" / "2026-11-11_step6_extraction_r2" / "run1"
    texts_src = root / "data" / "synthetic" / "out" / "firs_v5"
    cdr_src = root / "data" / "synthetic" / "out" / "case_demo_v2" / "cdr.csv"
    bank_src = root / "data" / "synthetic" / "out" / "case_demo_v2" / "bank.csv"

    # Store CSVs
    store.save_csv(case_id, "cdr", cdr_src.read_bytes())
    store.save_csv(case_id, "bank", bank_src.read_bytes())

    # Store documents and analyses
    for txt_file in sorted(texts_src.glob("FIR_*.txt")):
        doc_id = txt_file.stem
        store.add_document(case_id, doc_id, txt_file.read_bytes(), "test_user")
        analysis_path = analyses_src / f"{doc_id}.analysis.json"
        if analysis_path.is_file():
            analysis_data = json.loads(analysis_path.read_text(encoding="utf-8"))
            store.save_analysis(case_id, doc_id, analysis_data)
            store.set_document_status(case_id, doc_id, "extracted")

    committed_graph = json.load(
        open(root / "data" / "graph" / "out" / "case_demo_v2_r2" / "graph.json", encoding="utf-8")
    )
    return case_id, committed_graph


def test_build_graph_matches_committed_case_demo_v2(temp_store: Storage) -> None:
    """Building case graph from demo analyses and CSVs equals committed graph.json."""
    case_id, committed_graph = _setup_demo_case(temp_store)

    built = build_graph(temp_store, case_id)
    # Check loaded dictionary equality on all structural sections
    assert built.get("nodes") == committed_graph.get("nodes")
    assert built.get("edges") == committed_graph.get("edges")
    assert built.get("stats") == committed_graph.get("stats")


def test_render_graph_validates_against_contract2(temp_store: Storage) -> None:
    """Rendered graph validates against Contract 2 schema and semantic rules."""
    case_id, _ = _setup_demo_case(temp_store)
    graph = build_graph(temp_store, case_id)

    rendered = render_graph(graph)
    validate_graph(rendered)

    # All nodes must have isKingpin false
    for node in rendered["elements"]["nodes"]:
        assert node["data"]["isKingpin"] is False

    # Summary requirements
    assert rendered["summary"]["schema_version"] == "1.1"
    assert rendered["summary"]["kingpin_node_id"] is None
    assert rendered["summary"]["total_nodes"] == len(rendered["elements"]["nodes"])
    assert rendered["summary"]["total_edges"] == len(rendered["elements"]["edges"])


def test_ids_stable_across_two_builds(temp_store: Storage) -> None:
    """Node and edge IDs are stable across two independent builds."""
    case_id, _ = _setup_demo_case(temp_store)

    build1 = build_graph(temp_store, case_id)
    rendered1 = render_graph(build1)

    # Invalidate cache by clearing derived directory
    cdir = temp_store.case_dir(case_id)
    derived = cdir / "derived"
    for f in derived.glob("*"):
        f.unlink()

    build2 = build_graph(temp_store, case_id)
    rendered2 = render_graph(build2)

    nodes1 = [n["data"]["id"] for n in rendered1["elements"]["nodes"]]
    nodes2 = [n["data"]["id"] for n in rendered2["elements"]["nodes"]]
    assert nodes1 == nodes2

    edges1 = [e["data"]["id"] for e in rendered1["elements"]["edges"]]
    edges2 = [e["data"]["id"] for e in rendered2["elements"]["edges"]]
    assert edges1 == edges2


def test_cache_used_and_rebuilt_on_document_add(temp_store: Storage) -> None:
    """Graph cache is used when fingerprint is unchanged and rebuilt on document addition."""
    case_id, _ = _setup_demo_case(temp_store)

    build1 = build_graph(temp_store, case_id)
    fp1 = build1["fingerprint"]

    # Read cached graph directly
    cdir = temp_store.case_dir(case_id)
    graph_path = cdir / "derived" / "graph.json"
    assert graph_path.is_file()

    # Second call uses cache
    build2 = build_graph(temp_store, case_id)
    assert build2["fingerprint"] == fp1

    # Add an analysis file to alter fingerprint
    new_doc_id = "FIR_999"
    temp_store.add_document(case_id, new_doc_id, b"Additional FIR text", "test_user")
    temp_store.save_analysis(
        case_id,
        new_doc_id,
        {"aux": {}, "doc": {"source_doc_id": new_doc_id, "entities": []}, "info": {}},
    )

    fp2, _ = compute_case_fingerprint(temp_store, case_id)
    assert fp1 != fp2

    build3 = build_graph(temp_store, case_id)
    assert build3["fingerprint"] == fp2


def test_extra_field_fails_validation(temp_store: Storage) -> None:
    """Deliberately adding an extra field fails Contract 2 validation."""
    case_id, _ = _setup_demo_case(temp_store)
    graph = build_graph(temp_store, case_id)
    rendered = render_graph(graph)

    # Extra field in summary
    broken_summary = copy.deepcopy(rendered)
    broken_summary["summary"]["extra_property"] = "disallowed"
    with pytest.raises(ValueError):
        validate_graph(broken_summary)

    # Extra field in node data
    broken_node = copy.deepcopy(rendered)
    broken_node["elements"]["nodes"][0]["data"]["extra_property"] = 123
    with pytest.raises(ValueError):
        validate_graph(broken_node)


def test_fir_only_case_works(temp_store: Storage) -> None:
    """FIR-only case without CSV uploads builds successfully without error."""
    case = temp_store.create_case("FIR Only Case", "test_user")
    case_id = case["case_id"]

    root = repo_root()
    analysis_data = json.load(
        open(root / "results" / "2026-11-11_step6_extraction_r2" / "run1" / "FIR_01.analysis.json", encoding="utf-8")
    )
    temp_store.add_document(case_id, "FIR_01", b"Sample text", "test_user")
    temp_store.save_analysis(case_id, "FIR_01", analysis_data)

    built = build_graph(temp_store, case_id)
    assert len(built["nodes"]) > 0
    rendered = render_graph(built)
    validate_graph(rendered)


def test_nothing_to_analyze_error(temp_store: Storage) -> None:
    """Empty case raises NothingToAnalyzeError."""
    case = temp_store.create_case("Empty Case", "test_user")
    case_id = case["case_id"]

    with pytest.raises(NothingToAnalyzeError):
        build_graph(temp_store, case_id)
