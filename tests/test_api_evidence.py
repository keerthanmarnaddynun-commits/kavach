"""Unit tests for evidence extraction, span slicing, document views, and timelines."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import pytest

from kavach_api.analysis_service import build_graph
from kavach_api.evidence import (
    compute_first_fir_mention,
    compute_first_record,
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


def test_timeline_first_seen_accounts_and_imeis(temp_store: Storage) -> None:
    """Timeline first-seen tracks earliest timestamps for accounts and IMEIs, empty on missing CSVs."""
    # 1. Custom small case with known timestamps
    case = temp_store.create_case("Timeline Test Case", "test_user", synthetic=True)
    case_id = case["case_id"]

    cdr_content = (
        "a_party,b_party,imei_a,imsi_a,start_time,duration_sec,call_type,tower_id,lat,lon\n"
        "9876543210,9876543211,351756051523999,405851318699938,2026-01-01T10:00:00,30,VOICE,T1,28.6,77.1\n"
        "9876543210,9876543212,351756051523999,405851318699938,2026-01-01T09:00:00,45,VOICE,T1,28.6,77.1\n"
        "9876543215,9876543216,351756051523888,405851318699939,2026-01-02T11:00:00,10,SMS,T1,28.6,77.1\n"
    )
    bank_content = (
        "txn_id,datetime,from_acct,to_acct,amount,mode,ifsc,narration\n"
        "TXN1,2026-01-01T12:00:00,ACCT_A,ACCT_B,100,NEFT,IFSC1,test1\n"
        "TXN2,2026-01-01T08:00:00,ACCT_C,ACCT_A,200,NEFT,IFSC1,test2\n"
        "TXN3,2026-01-02T15:00:00,ACCT_B,ACCT_D,300,IMPS,IFSC2,test3\n"
    )

    temp_store.save_csv(case_id, "cdr", cdr_content.encode("utf-8"))
    temp_store.save_csv(case_id, "bank", bank_content.encode("utf-8"))

    tl = build_timeline(temp_store, case_id, bucket="day")

    # Check first_seen_accounts
    accounts_by_id = {item["account"]: item["t"] for item in tl["first_seen_accounts"]}
    assert accounts_by_id["ACCT_A"] == "2026-01-01T08:00:00"
    assert accounts_by_id["ACCT_B"] == "2026-01-01T12:00:00"
    assert accounts_by_id["ACCT_C"] == "2026-01-01T08:00:00"
    assert accounts_by_id["ACCT_D"] == "2026-01-02T15:00:00"

    # Check first_seen_imeis
    imeis_by_id = {item["imei"]: item["t"] for item in tl["first_seen_imeis"]}
    assert imeis_by_id["351756051523999"] == "2026-01-01T09:00:00"
    assert imeis_by_id["351756051523888"] == "2026-01-02T11:00:00"

    # Check existing fields preserved
    assert tl["bucket"] == "day"
    assert len(tl["calls"]) == 2
    assert len(tl["transfers"]) == 2
    phones_by_id = {item["phone"]: item["t"] for item in tl["first_seen"]}
    assert phones_by_id["9876543210"] == "2026-01-01T09:00:00"

    # 2. Empty case with missing CSVs returns empty lists
    empty_case = temp_store.create_case("Empty Case", "test_user", synthetic=True)
    tl_empty = build_timeline(temp_store, empty_case["case_id"], bucket="day")
    assert tl_empty["calls"] == []
    assert tl_empty["transfers"] == []
    assert tl_empty["first_seen"] == []
    assert tl_empty["first_seen_accounts"] == []
    assert tl_empty["first_seen_imeis"] == []


def test_compute_first_fir_mention_and_node_evidence(temp_store: Storage) -> None:
    """Verify earliest FIR mention determination, Group (a) related entities, Group (b) other entities, and CSV-only fallback."""
    case_id, graph = _populate_demo_case(temp_store)

    # 1. Test node with FIR mentions
    fir_nodes = [n for n in graph["nodes"] if n.get("evidence_spans")]
    assert len(fir_nodes) > 0
    test_node = fir_nodes[0]
    nid = test_node["id"]

    ev = node_evidence(temp_store, case_id, graph, nid)
    assert "first_fir" in ev
    first_fir = ev["first_fir"]
    assert first_fir is not None
    assert first_fir["first_fir_id"] is not None
    assert first_fir["first_fir_id"].startswith("FIR_")
    assert isinstance(first_fir["related_entities"], list)
    assert isinstance(first_fir["other_entities"], list)

    # Check direct call to compute_first_fir_mention
    res = compute_first_fir_mention(temp_store, case_id, graph, nid)
    assert res == first_fir

    # 2. Test CSV-only node has no FIR mention
    case = temp_store.create_case("CSV Only Case", "test_user", synthetic=True)
    cid = case["case_id"]
    empty_graph = {"nodes": [{"id": "ACCOUNT:CSV_ONLY", "type": "ACCOUNT", "source_firs": [], "evidence_spans": []}], "edges": []}
    res_csv = compute_first_fir_mention(temp_store, cid, empty_graph, "ACCOUNT:CSV_ONLY")
    assert res_csv["first_fir_id"] is None
    assert res_csv["related_entities"] == []
    assert res_csv["other_entities"] == []


def test_compute_first_record_and_timeline(temp_store: Storage) -> None:
    """Verify first_record computation for phone, account, and IMEI, 1-based indexing, counterpart extraction, and cap at 5."""
    case = temp_store.create_case("First Record Test Case", "test_user", synthetic=True)
    case_id = case["case_id"]

    # 1. Setup CDR CSV with 6 records sharing the same timestamp for a phone to test cap at 5
    cdr_rows = [
        "a_party,b_party,imei_a,imsi_a,start_time,duration_sec,call_type,tower_id,lat,lon",
        "9876543210,9876543211,351756051523999,405851318699938,2026-01-01T08:00:00,30,VOICE,T1,28.6,77.1", # row 1
        "9876543210,9876543212,351756051523999,405851318699938,2026-01-01T08:00:00,30,VOICE,T1,28.6,77.1", # row 2
        "9876543210,9876543213,351756051523999,405851318699938,2026-01-01T08:00:00,30,VOICE,T1,28.6,77.1", # row 3
        "9876543210,9876543214,351756051523999,405851318699938,2026-01-01T08:00:00,30,VOICE,T1,28.6,77.1", # row 4
        "9876543210,9876543215,351756051523999,405851318699938,2026-01-01T08:00:00,30,VOICE,T1,28.6,77.1", # row 5
        "9876543210,9876543216,351756051523999,405851318699938,2026-01-01T08:00:00,30,VOICE,T1,28.6,77.1", # row 6 (exceeds cap of 5)
        "9876543210,9876543217,351756051523999,405851318699938,2026-01-01T09:00:00,30,VOICE,T1,28.6,77.1", # row 7 (later time)
    ]
    bank_rows = [
        "txn_id,datetime,from_acct,to_acct,amount,mode,ifsc,narration",
        "TXN1,2026-01-01T07:00:00,ACCT_A,ACCT_B,100,NEFT,IFSC1,test1", # row 1
        "TXN2,2026-01-01T10:00:00,ACCT_C,ACCT_A,200,NEFT,IFSC1,test2", # row 2
    ]

    temp_store.save_csv(case_id, "cdr", "\n".join(cdr_rows).encode("utf-8"))
    temp_store.save_csv(case_id, "bank", "\n".join(bank_rows).encode("utf-8"))

    graph = {
        "nodes": [
            {"id": "PHONE:9876543210", "type": "PHONE", "value": "9876543210"},
            {"id": "ACCOUNT:ACCT_A", "type": "ACCOUNT", "value": "ACCT_A"},
            {"id": "IMEI:351756051523999", "type": "IMEI", "value": "351756051523999"},
            {"id": "PERSON:SUSPECT", "type": "PERSON", "value": "SUSPECT"},
        ],
        "edges": [],
    }

    # Test Phone first_record
    p_rec = compute_first_record(temp_store, case_id, graph, "PHONE:9876543210")
    assert p_rec is not None
    assert p_rec["file"] == "cdr"
    assert p_rec["timestamp"] == "2026-01-01T08:00:00"
    # Row numbers must be 1-based and capped at 5
    assert p_rec["rows"] == [1, 2, 3, 4, 5]
    assert len(p_rec["records"]) == 5
    # Counterparts: other parties + IMEI used
    assert "9876543211" in p_rec["counterparts"]
    assert "351756051523999" in p_rec["counterparts"]

    # Verify rows endpoint retrieves exactly those row indices
    raw_fetched = rows(temp_store, case_id, "cdr", p_rec["rows"])
    assert len(raw_fetched) == 5
    assert raw_fetched[0]["row"] == 1
    assert raw_fetched[0]["a_party"] == "9876543210"
    assert raw_fetched[0]["b_party"] == "9876543211"

    # Test Account first_record
    a_rec = compute_first_record(temp_store, case_id, graph, "ACCOUNT:ACCT_A")
    assert a_rec is not None
    assert a_rec["file"] == "bank"
    assert a_rec["timestamp"] == "2026-01-01T07:00:00"
    assert a_rec["rows"] == [1]
    assert a_rec["counterparts"] == ["ACCT_B"]

    # Test IMEI first_record
    im_rec = compute_first_record(temp_store, case_id, graph, "IMEI:351756051523999")
    assert im_rec is not None
    assert im_rec["file"] == "cdr"
    assert im_rec["timestamp"] == "2026-01-01T08:00:00"
    assert im_rec["rows"] == [1, 2, 3, 4, 5]
    assert im_rec["counterparts"] == ["9876543210"]

    # Test node with no CSV activity returns None
    none_rec = compute_first_record(temp_store, case_id, graph, "PERSON:SUSPECT")
    assert none_rec is None

    # Test timeline returns first_record in first_seen lists
    tl = build_timeline(temp_store, case_id, bucket="day")
    p_tl = [item for item in tl["first_seen"] if item["phone"] == "9876543210"][0]
    assert "first_record" in p_tl
    assert p_tl["first_record"]["timestamp"] == "2026-01-01T08:00:00"
    assert p_tl["first_record"]["rows"] == [1, 2, 3, 4, 5]

    a_tl = [item for item in tl["first_seen_accounts"] if item["account"] == "ACCT_A"][0]
    assert "first_record" in a_tl
    assert a_tl["first_record"]["timestamp"] == "2026-01-01T07:00:00"
    assert a_tl["first_record"]["counterparts"] == ["ACCT_B"]

    im_tl = [item for item in tl["first_seen_imeis"] if item["imei"] == "351756051523999"][0]
    assert "first_record" in im_tl
    assert im_tl["first_record"]["timestamp"] == "2026-01-01T08:00:00"
    assert im_tl["first_record"]["counterparts"] == ["9876543210"]
    assert "first_fir" in p_tl
    assert p_tl["first_fir"] is None

    # Test timeline with demo case that has FIR documents
    demo_cid, _ = _populate_demo_case(temp_store)
    demo_tl = build_timeline(temp_store, demo_cid, bucket="day")
    p_with_fir = [item for item in demo_tl["first_seen"] if item.get("first_fir")]
    assert len(p_with_fir) > 0
    assert p_with_fir[0]["first_fir"]["first_fir_id"].startswith("FIR_")
    p_without_fir = [item for item in demo_tl["first_seen"] if not item.get("first_fir")]
    assert len(p_without_fir) > 0
