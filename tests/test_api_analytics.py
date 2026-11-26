"""Unit tests for analytics service: money-flow leads, role chips, detectors, break."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
import pytest

from case_analytics.projection import (
    compute_pessimistic_ranks,
    compute_projection_scores,
)
from case_detectors.burner import detect_burners
from case_detectors.mule import detect_mules
from kavach_api.analysis_service import build_graph, compute_case_fingerprint
from kavach_api.leads import (
    BREAK_NOTE,
    LIMITATIONS,
    InvalidGroupError,
    build_leads,
    load_detector_config,
    run_break,
)
from kavach_api.settings import DISCLAIMER, Settings, repo_root
from kavach_api.storage import Storage


@pytest.fixture
def temp_store(tmp_path: Path) -> Storage:
    """Fixture providing Storage with temporary runtime directory."""
    return Storage(Settings(runtime_dir=tmp_path / "runtime"))


def _setup_demo_case(store: Storage) -> str:
    """Helper to populate a temporary case with demo analyses and CSVs."""
    root = repo_root()
    case = store.create_case("Demo Analytics Case", "test_analyst", synthetic=True)
    case_id = case["case_id"]

    analyses_src = root / "results" / "2026-11-11_step6_extraction_r2" / "run1"
    texts_src = root / "data" / "synthetic" / "out" / "firs_v5"
    cdr_src = root / "data" / "synthetic" / "out" / "case_demo_v2" / "cdr.csv"
    bank_src = root / "data" / "synthetic" / "out" / "case_demo_v2" / "bank.csv"

    store.save_csv(case_id, "cdr", cdr_src.read_bytes())
    store.save_csv(case_id, "bank", bank_src.read_bytes())

    for txt_file in sorted(texts_src.glob("FIR_*.txt")):
        doc_id = txt_file.stem
        store.add_document(case_id, doc_id, txt_file.read_bytes(), "test_analyst")
        analysis_path = analyses_src / f"{doc_id}.analysis.json"
        if analysis_path.is_file():
            analysis_data = json.loads(analysis_path.read_text(encoding="utf-8"))
            store.save_analysis(case_id, doc_id, analysis_data)
            store.set_document_status(case_id, doc_id, "extracted")

    return case_id


def test_money_flow_and_structural_explanation_on_demo_case(temp_store: Storage) -> None:
    """Money flow list is non-empty, sorted, ranks and scores match frozen functions."""
    case_id = _setup_demo_case(temp_store)
    leads = build_leads(temp_store, case_id)

    # 1. Money flow structure & sorting
    mf = leads["money_flow"]
    assert len(mf) > 0
    assert len(mf) <= 25

    graph = build_graph(temp_store, case_id)
    frozen_scores = compute_projection_scores(graph)
    expected_fin_scores = frozen_scores["raw_scores"]["financial_only"]
    expected_fin_ranks = frozen_scores["pessimistic_ranks"]["financial_only"]

    for idx, item in enumerate(mf):
        pid = item["person_id"]
        assert item["rank"] == expected_fin_ranks[pid]
        assert pytest.approx(item["score"], 1e-5) == expected_fin_scores[pid]
        assert "rank" in item
        assert "tied" in item
        assert "name" in item
        assert "accounts" in item
        assert "reasons" in item
        assert "evidence" in item
        assert isinstance(item["reasons"], list)
        assert len(item["reasons"]) > 0

        if idx > 0:
            prev = mf[idx - 1]
            assert (prev["rank"], -prev["score"]) <= (item["rank"], -item["score"])

    # 2. Structural explanation
    se = leads["structural_explanation"]
    assert isinstance(se, dict)
    person_nodes = [n["id"] for n in graph["nodes"] if n.get("type") == "PERSON"]
    for pid in person_nodes:
        assert pid in se
        stats = se[pid]
        assert "degree" in stats
        assert "betweenness" in stats
        assert "eigenvector" in stats
        assert "composite" in stats


def test_detectors_top_items_match_frozen_detectors(temp_store: Storage) -> None:
    """Detectors' top items in leads equal direct calls of frozen detectors."""
    case_id = _setup_demo_case(temp_store)
    leads = build_leads(temp_store, case_id)

    config = load_detector_config()
    bank_path = temp_store.csv_path(case_id, "bank")
    cdr_path = temp_store.csv_path(case_id, "cdr")

    direct_mules = detect_mules(bank_path, config)
    direct_burners = detect_burners(cdr_path, config)

    mule_leads = leads["mule_accounts"]
    burner_leads = leads["burner_phones"]

    assert len(mule_leads) == min(25, len(direct_mules))
    assert len(burner_leads) == min(25, len(direct_burners))

    for m_lead, m_direct in zip(mule_leads, direct_mules[: len(mule_leads)]):
        assert m_lead["id"] == m_direct["id"]
        assert pytest.approx(m_lead["score"], 1e-5) == m_direct["score"]
        assert m_lead["evidence_rows"]["file"] == "bank.csv"
        assert len(m_lead["evidence_rows"]["sha256"]) == 64
        expected_flag = m_direct["score"] >= config["chip_min_score"]["mule"]
        assert m_lead["flagged"] == expected_flag

    for b_lead, b_direct in zip(burner_leads, direct_burners[: len(burner_leads)]):
        assert b_lead["id"] == b_direct["id"]
        assert pytest.approx(b_lead["score"], 1e-5) == b_direct["score"]
        assert b_lead["evidence_rows"]["file"] == "cdr.csv"
        assert len(b_lead["evidence_rows"]["sha256"]) == 64
        expected_flag = b_direct["score"] >= config["chip_min_score"]["burner"]
        assert b_lead["flagged"] == expected_flag


def test_chips_follow_configured_threshold(temp_store: Storage) -> None:
    """Role chips change when threshold in config is modified."""
    case_id = _setup_demo_case(temp_store)

    default_leads = build_leads(temp_store, case_id)
    default_chips = default_leads["role_chips"]

    # Re-run with custom config having high thresholds (e.g. 0.9999)
    strict_config = {
        "chip_min_score": {
            "burner": 0.9999,
            "mule": 0.9999,
        }
    }
    strict_leads = build_leads(temp_store, case_id, config=strict_config)
    strict_chips = strict_leads["role_chips"]

    # In strict mode, no MULE_OWNER or BURNER_USER chip should be assigned
    for pid, chips in strict_chips.items():
        assert not any(c["chip"] == "MULE_OWNER" for c in chips)
        assert not any(c["chip"] == "BURNER_USER" for c in chips)

    # In strict leads list, flagged must be False for all accounts and burners below 0.9999
    for m in strict_leads["mule_accounts"]:
        assert m["flagged"] is False
    for b in strict_leads["burner_phones"]:
        assert b["flagged"] is False


def test_run_break_with_disjoint_groups(temp_store: Storage) -> None:
    """run_break returns a result and never includes a terminal in the cut."""
    case_id = _setup_demo_case(temp_store)
    graph = build_graph(temp_store, case_id)
    person_nodes = [n["id"] for n in graph["nodes"] if n.get("type") == "PERSON"]
    assert len(person_nodes) >= 4

    group_a = person_nodes[:2]
    group_b = person_nodes[2:4]

    result = run_break(temp_store, case_id, group_a, group_b)

    assert "finite" in result
    assert "size" in result
    assert "cut" in result
    assert "direct_link" in result
    assert "bridging_unowned_phones" in result
    assert result["note"] == BREAK_NOTE
    assert result["disclaimer"] == DISCLAIMER

    # Terminals must never be in the cut
    terminals = set(group_a) | set(group_b)
    cut_ids = {c["person_id"] for c in result["cut"]}
    assert cut_ids & terminals == set()

    for item in result["cut"]:
        assert "person_id" in item
        assert "name" in item


def test_run_break_with_members_absent_from_call_graph(temp_store: Storage) -> None:
    """run_break succeeds and returns valid result when group members are absent from the call graph."""
    case_id = _setup_demo_case(temp_store)
    graph = build_graph(temp_store, case_id)
    person_nodes = [n["id"] for n in graph["nodes"] if n.get("type") == "PERSON"]
    assert len(person_nodes) >= 4

    # 1. Partial absent: group members from demo case
    group_a = person_nodes[:2]
    group_b = person_nodes[2:4]
    res1 = run_break(temp_store, case_id, group_a, group_b)
    assert "cut" in res1
    assert "cut_details" in res1
    assert isinstance(res1["cut_details"], dict)

    # 2. All members absent from call graph: people without phones
    owns_device_people = {
        e["source"] for e in graph.get("edges", []) if e.get("label") == "OWNS_DEVICE"
    } | {
        e["target"] for e in graph.get("edges", []) if e.get("label") == "OWNS_DEVICE"
    }
    non_call_persons = [p for p in person_nodes if p not in owns_device_people]
    if len(non_call_persons) >= 4:
        g_absent_a = non_call_persons[:2]
        g_absent_b = non_call_persons[2:4]
    else:
        g_absent_a = person_nodes[:2]
        g_absent_b = person_nodes[2:4]

    res2 = run_break(temp_store, case_id, g_absent_a, g_absent_b)
    assert "cut" in res2
    assert "cut_details" in res2
    assert isinstance(res2["cut_details"], dict)
    assert "finite" in res2
    assert "size" in res2


def test_run_break_rejects_invalid_groups(temp_store: Storage) -> None:
    """Empty, overlapping, unknown and oversized groups are rejected with typed errors."""
    case_id = _setup_demo_case(temp_store)
    graph = build_graph(temp_store, case_id)
    person_nodes = [n["id"] for n in graph["nodes"] if n.get("type") == "PERSON"]
    p1 = person_nodes[0]
    p2 = person_nodes[1]

    # Empty group
    with pytest.raises(InvalidGroupError):
        run_break(temp_store, case_id, [], [p2])
    with pytest.raises(InvalidGroupError):
        run_break(temp_store, case_id, [p1], [])

    # Overlapping groups
    with pytest.raises(InvalidGroupError):
        run_break(temp_store, case_id, [p1], [p1, p2])

    # Unknown person ID
    with pytest.raises(InvalidGroupError):
        run_break(temp_store, case_id, ["PERSON:UNKNOWN:999"], [p2])

    # Oversized group (> 200)
    oversized = [f"PERSON:DUMMY:{i}" for i in range(201)]
    with pytest.raises(InvalidGroupError):
        run_break(temp_store, case_id, oversized, [p2])


def test_leads_cached_and_reused(temp_store: Storage) -> None:
    """leads.json is reused when fingerprint is unchanged."""
    case_id = _setup_demo_case(temp_store)

    first = build_leads(temp_store, case_id)
    leads_file = temp_store.case_dir(case_id) / "derived" / "leads.json"
    assert leads_file.is_file()

    mtime_before = leads_file.stat().st_mtime_ns

    # Second call should return cached dict without rewriting file
    second = build_leads(temp_store, case_id)
    mtime_after = leads_file.stat().st_mtime_ns

    assert mtime_before == mtime_after
    assert first["fingerprint"] == second["fingerprint"]
    assert first["money_flow"] == second["money_flow"]


def test_disclaimer_and_limitations_always_present(temp_store: Storage) -> None:
    """Note, disclaimer, and 5 limitations are present."""
    case_id = _setup_demo_case(temp_store)
    leads = build_leads(temp_store, case_id)

    assert leads["disclaimer"] == DISCLAIMER
    assert leads["limitations"] == LIMITATIONS
    assert len(leads["limitations"]) == 5

    res = run_break(
        temp_store,
        case_id,
        [leads["money_flow"][0]["person_id"]],
        [leads["money_flow"][-1]["person_id"]],
    )
    assert res["disclaimer"] == DISCLAIMER
    assert res["note"] == BREAK_NOTE
