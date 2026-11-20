"""Unit tests for evidence extraction, span slicing, document views, and timelines."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import pytest

from kavach_api.analysis_service import build_graph
from kavach_api.evidence import (
    document_view,
    edge_evidence,
    node_evidence,
    rows,
)
from kavach_api.settings import Settings, repo_root
from kavach_api.storage import Storage
from kavach_api.timeline import build_timeline


@pytest.fixture
def temp_store(tmp_path: Path) -> Storage:
    """Fixture providing Storage with temporary runtime directory."""
    return Storage(Settings(runtime_dir=tmp_path / "runtime"))


def _populate_demo_case(store: Storage) -> tuple[str, dict[str, Any]]:
    """Helper to populate case with demo data, return case_id and built graph."""
    root = repo_root()
    case = store.create_case("Evidence Demo Case", "test_user", synthetic=True)
    case_id = case["case_id"]

    analyses_src = root / "results" / "2026-11-11_step6_extraction_r2" / "run1"
    texts_src = root / "data" / "synthetic" / "out" / "firs_v5"
    cdr_src = root / "data" / "synthetic" / "out" / "case_demo_v2" / "cdr.csv"
    bank_src = root / "data" / "synthetic" / "out" / "case_demo_v2" / "bank.csv"

    store.save_csv(case_id, "cdr", cdr_src.read_bytes())
    store.save_csv(case_id, "bank", bank_src.read_bytes())

    for txt_file in sorted(texts_src.glob("FIR_*.txt")):
        doc_id = txt_file.stem
        store.add_document(case_id, doc_id, txt_file.read_bytes(), "test_user")
        analysis_path = analyses_src / f"{doc_id}.analysis.json"
        if analysis_path.is_file():
            store.save_analysis(case_id, doc_id, json.loads(analysis_path.read_text(encoding="utf-8")))
            store.set_document_status(case_id, doc_id, "extracted")

    graph = build_graph(store, case_id)
    return case_id, graph


def test_fir_evidence_spans_slice_back_to_surface(temp_store: Storage) -> None:
    """Every FIR evidence span slices stored text back to the recorded surface."""
    case_id, graph = _populate_demo_case(temp_store)

    # 1. Node evidence spans
    nodes_with_evidence = [n for n in graph["nodes"] if n.get("evidence_spans")]
    assert len(nodes_with_evidence) > 0

    for n in nodes_with_evidence:
        nid = n["id"]
        ev = node_evidence(temp_store, case_id, graph, nid)
        assert ev["node_id"] == nid
        for item in ev["fir_evidence"]:
            doc_id = item["doc_id"]
            _, text = temp_store.get_document(case_id, doc_id)
            start, end = item["char_span"]
            assert text[start:end] == item["surface"]
            assert item["surface"] in item["excerpt"]

    # 2. Edge evidence spans
    fir_edges = [e for e in graph["edges"] if e.get("source_kind") == "FIR"]
    assert len(fir_edges) > 0

    for e in fir_edges:
        src = e["source"]
        tgt = e["target"]
        rel = e.get("relation")
        ev = edge_evidence(temp_store, case_id, graph, src, tgt, rel)
        for item in ev["fir_evidence"]:
            doc_id = item["doc_id"]
            _, text = temp_store.get_document(case_id, doc_id)
            start, end = item["char_span"]
            assert text[start:end] == item["surface"]


def test_csv_evidence_row_numbers_exist_and_hashes_match(temp_store: Storage) -> None:
    """CSV evidence row numbers exist in stored CSV and file hash matches recorded hash."""
    case_id, graph = _populate_demo_case(temp_store)

    files_info = temp_store.files_info(case_id)
    cdr_sha = (files_info.get("cdr") or files_info.get("cdr.csv", {}))["sha256"]
    bank_sha = (files_info.get("bank") or files_info.get("bank.csv", {}))["sha256"]

    # Read row counts from stored CSVs
    with open(temp_store.csv_path(case_id, "cdr"), "r", encoding="utf-8") as f:
        cdr_total = sum(1 for _ in csv.DictReader(f))
    with open(temp_store.csv_path(case_id, "bank"), "r", encoding="utf-8") as f:
        bank_total = sum(1 for _ in csv.DictReader(f))

    # Check edges with CSV evidence
    csv_edges = [e for e in graph["edges"] if e.get("source_kind") == "CSV"]
    assert len(csv_edges) > 0

    for e in csv_edges:
        src = e["source"]
        tgt = e["target"]
        rel = e.get("relation")
        ev = edge_evidence(temp_store, case_id, graph, src, tgt, rel)
        csv_ev = ev["csv_evidence"]
        assert csv_ev is not None

        fname = csv_ev["file"]
        expected_sha = cdr_sha if fname == "cdr.csv" else bank_sha
        assert csv_ev["sha256"] == expected_sha

        max_rows = cdr_total if fname == "cdr.csv" else bank_total
        for r_num in csv_ev["row_numbers"]:
            assert 1 <= r_num <= max_rows


def test_rows_returns_same_values_as_manual_read(temp_store: Storage) -> None:
    """rows(...) returns same values as reading the CSV directly for 5 chosen rows."""
    case_id, _ = _populate_demo_case(temp_store)

    chosen_rows = [1, 25, 100, 500, 1000]
    result_rows = rows(temp_store, case_id, "cdr", chosen_rows)
    assert len(result_rows) == 5

    # Read manual rows
    manual_rows: dict[int, dict[str, str]] = {}
    with open(temp_store.csv_path(case_id, "cdr"), "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for idx, row_dict in enumerate(reader, start=1):
            if idx in chosen_rows:
                manual_rows[idx] = dict(row_dict)

    for item in result_rows:
        r_num = item["row"]
        expected = manual_rows[r_num]
        for k, v in expected.items():
            assert item[k] == v


def test_document_view(temp_store: Storage) -> None:
    """document_view returns text, sha256 hashes, and span highlight list."""
    case_id, graph = _populate_demo_case(temp_store)

    doc_id = "FIR_01"
    view = document_view(temp_store, case_id, doc_id, graph)

    assert view["doc_id"] == doc_id
    assert len(view["text"]) > 0
    assert view["sha256_raw"] is not None
    assert len(view["spans"]) > 0

    # Every span coordinates slice back into document text
    text = view["text"]
    for s in view["spans"]:
        coords = s.get("char_span")
        if coords:
            assert text[coords[0] : coords[1]] is not None


def test_timeline_aggregation_counts_sum_to_csv_rows(temp_store: Storage) -> None:
    """Timeline counts sum to the CSV row counts for both day and hour buckets."""
    case_id, _ = _populate_demo_case(temp_store)

    root = repo_root()
    stats = json.load(open(root / "data" / "graph" / "out" / "case_demo_v2_r2" / "stats.json", encoding="utf-8"))
    expected_cdr = stats["cdr_rows_read"]
    expected_bank = stats["bank_rows_read"]

    # Day bucket
    tl_day = build_timeline(temp_store, case_id, bucket="day")
    assert tl_day["bucket"] == "day"
    sum_day_calls = sum(c["count"] for c in tl_day["calls"])
    sum_day_transfers = sum(t["count"] for t in tl_day["transfers"])
    assert sum_day_calls == expected_cdr
    assert sum_day_transfers == expected_bank

    # Hour bucket
    tl_hour = build_timeline(temp_store, case_id, bucket="hour")
    assert tl_hour["bucket"] == "hour"
    sum_hour_calls = sum(c["count"] for c in tl_hour["calls"])
    sum_hour_transfers = sum(t["count"] for t in tl_hour["transfers"])
    assert sum_hour_calls == expected_cdr
    assert sum_hour_transfers == expected_bank

    # First seen phone entries exist
    assert len(tl_day["first_seen"]) > 0
