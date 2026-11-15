"""Tests for planted-case simulation and evaluation (Task 7b-2)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from case_graph.builder import _collect_bank_edges, _collect_cdr_edges
from case_simulation.builder import build_planted_graph, sample_stated_facts
from scripts.eval_planted import _find_best_rank, run_paired_bootstrap


@pytest.fixture
def sample_truth_fixture() -> dict:
    """Hand-made truth fixture with 2 suspects and 1 decoy owner."""
    return {
        "case_id": "TEST_CASE_01",
        "kingpin_ids": ["PER_A_KP_01", "PER_B_KP_01"],
        "people": [
            {
                "person_id": "PER_A_KP_01",
                "name": "Kingpin Alpha",
                "is_decoy": False,
                "phones": [{"phone": "9876543210"}, {"phone": "9876543211"}],
                "accounts": [{"account_number": "ACC1001"}],
            },
            {
                "person_id": "PER_B_KP_01",
                "name": "Kingpin Beta",
                "is_decoy": False,
                "phones": [{"phone": "9876543212"}],
                "accounts": [{"account_number": "ACC1002"}, {"account_number": "ACC1003"}],
            },
            {
                "person_id": "DEC_PIZZA_01",
                "name": "Decoy Pizza Owner",
                "is_decoy": True,
                "phones": [{"phone": "9999999999"}],
                "accounts": [{"account_number": "ACC9999"}],
            },
        ],
    }


def test_coverage_one_and_zero(sample_truth_fixture):
    """coverage 1.0 states every ownership fact, coverage 0.0 states none."""
    rng = np.random.RandomState(42)

    # Coverage 1.0: all facts stated
    stated_1 = sample_stated_facts(sample_truth_fixture, coverage=1.0, rng=rng)
    assert len(stated_1["PER_A_KP_01"]) == 3  # 2 phones + 1 acc
    assert len(stated_1["PER_B_KP_01"]) == 3  # 1 phone + 2 acc
    assert len(stated_1["DEC_PIZZA_01"]) == 2  # 1 phone + 1 acc

    # Coverage 0.0: no facts stated
    stated_0 = sample_stated_facts(sample_truth_fixture, coverage=0.0, rng=rng)
    assert stated_0["PER_A_KP_01"] == []
    assert stated_0["PER_B_KP_01"] == []
    assert stated_0["DEC_PIZZA_01"] == []


def test_fragmented_vs_resolved_node_counts(tmp_path, sample_truth_fixture):
    """fragmented=True mode creates one node per stated fact, fragmented=False one per person."""
    case_dir = tmp_path / "case_test"
    case_dir.mkdir()
    (case_dir / "truth.json").write_text(json.dumps(sample_truth_fixture), encoding="utf-8")
    (case_dir / "cdr.csv").write_text("caller,callee,timestamp,call_duration_seconds,imei\n", encoding="utf-8")
    (case_dir / "bank.csv").write_text("sender_account,receiver_account,timestamp,amount,channel\n", encoding="utf-8")

    rng = np.random.RandomState(123)
    # Mode resolved (fragmented=False)
    graph_resolved = build_planted_graph(case_dir, coverage=1.0, fragmented=False, rng=rng)
    person_nodes_resolved = [n for n in graph_resolved["nodes"] if n["type"] == "PERSON"]
    # Exactly 3 people -> 3 PERSON nodes
    assert len(person_nodes_resolved) == 3
    assert {n["id"] for n in person_nodes_resolved} == {
        "PERSON:PER_A_KP_01",
        "PERSON:PER_B_KP_01",
        "PERSON:DEC_PIZZA_01",
    }

    # Mode fragmented (fragmented=True)
    rng_frag = np.random.RandomState(123)
    graph_frag = build_planted_graph(case_dir, coverage=1.0, fragmented=True, rng=rng_frag)
    person_nodes_frag = [n for n in graph_frag["nodes"] if n["type"] == "PERSON"]
    # PER_A has 3 facts, PER_B has 3 facts, DEC has 2 facts -> 8 PERSON nodes
    assert len(person_nodes_frag) == 8
    assert {n["id"] for n in person_nodes_frag} == {
        "PERSON:PER_A_KP_01:1",
        "PERSON:PER_A_KP_01:2",
        "PERSON:PER_A_KP_01:3",
        "PERSON:PER_B_KP_01:1",
        "PERSON:PER_B_KP_01:2",
        "PERSON:PER_B_KP_01:3",
        "PERSON:DEC_PIZZA_01:1",
        "PERSON:DEC_PIZZA_01:2",
    }


def test_deterministic_reproducibility(tmp_path, sample_truth_fixture):
    """Same seed and coverage index gives identical graph and attributions output."""
    case_dir = tmp_path / "case_det"
    case_dir.mkdir()
    (case_dir / "truth.json").write_text(json.dumps(sample_truth_fixture), encoding="utf-8")
    (case_dir / "cdr.csv").write_text("caller,callee,timestamp,call_duration_seconds,imei\n", encoding="utf-8")
    (case_dir / "bank.csv").write_text("sender_account,receiver_account,timestamp,amount,channel\n", encoding="utf-8")

    g1 = build_planted_graph(case_dir, coverage=0.6, fragmented=False, rng=np.random.RandomState(999))
    g2 = build_planted_graph(case_dir, coverage=0.6, fragmented=False, rng=np.random.RandomState(999))

    assert g1["nodes"] == g2["nodes"]
    assert g1["edges"] == g2["edges"]
    assert g1["attributions"] == g2["attributions"]


def test_decoy_owner_treated_like_any_other_person(sample_truth_fixture):
    """Decoy owner (DEC_PIZZA_01) is treated like any other person at the same coverage."""
    # Run multiple seeds to verify decoy is sampled with the same independent Bernoulli logic
    decoy_fact_counts = []
    for s in range(50):
        rng = np.random.RandomState(s)
        facts = sample_stated_facts(sample_truth_fixture, coverage=0.5, rng=rng)
        decoy_fact_counts.append(len(facts["DEC_PIZZA_01"]))

    # Total possible facts for decoy is 2
    # At coverage 0.5, average across 50 trials should be around 1.0 (between 0.7 and 1.3)
    avg_decoy_facts = sum(decoy_fact_counts) / len(decoy_fact_counts)
    assert 0.7 <= avg_decoy_facts <= 1.3


def test_kingpin_without_stated_fact_gets_rank_none():
    """Kingpin without a stated fact gets rank None (null) and counts as a miss in metrics."""
    # Ranking has only other nodes
    ranking = [
        {"node_id": "PERSON:OTHER_01", "rank": 1, "score": 10.0},
        {"node_id": "PERSON:OTHER_02", "rank": 2, "score": 5.0},
    ]
    # Finding rank for unstated kingpin PER_A_KP_01 returns None
    rank = _find_best_rank(ranking, "PER_A_KP_01")
    assert rank is None

    # In metrics, rank is None -> not present and not in top-3
    assert not (rank is not None and rank <= 3)


def test_bootstrap_reproducibility():
    """Bootstrap function is reproducible with seed 20261113."""
    comp_hits = [2, 1, 0, 2, 1, 1, 0, 2]
    base_hits = [1, 1, 0, 1, 0, 1, 0, 1]

    res1 = run_paired_bootstrap(comp_hits, base_hits, n_resamples=2000, seed=20261113)
    res2 = run_paired_bootstrap(comp_hits, base_hits, n_resamples=2000, seed=20261113)

    assert res1 == res2
    assert "ci_95" in res1
    assert "mean_diff" in res1


def test_paired_difference_identical_hits():
    """Paired difference is 0.0 with CI [0.0, 0.0] when composite and baseline hits are identical."""
    comp_hits = [2, 1, 0, 2, 1]
    base_hits = [2, 1, 0, 2, 1]

    res = run_paired_bootstrap(comp_hits, base_hits, n_resamples=2000, seed=20261113)
    assert res["mean_diff"] == 0.0
    assert res["ci_95"] == [0.0, 0.0]


def test_no_truth_in_case_analytics_and_case_graph():
    """case_analytics/ and case_graph/ source files contain the word 'truth' nowhere."""
    repo_root = Path(__file__).resolve().parents[1]
    for pkg in ("case_analytics", "case_graph"):
        pkg_dir = repo_root / pkg
        for py_path in pkg_dir.rglob("*.py"):
            content = py_path.read_text(encoding="utf-8").lower()
            assert "truth" not in content, f"Word 'truth' found in {py_path}"


def test_csv_edges_match_case_demo_v2_r2():
    """On data/synthetic/out/case_demo_v2, aggregated CSV edges from case_graph.builder match graph.json."""
    repo_root = Path(__file__).resolve().parents[1]
    case_dir = repo_root / "data" / "synthetic" / "out" / "case_demo_v2"
    graph_path = repo_root / "data" / "graph" / "out" / "case_demo_v2_r2" / "graph.json"

    if not (case_dir / "cdr.csv").exists() or not graph_path.exists():
        pytest.skip("case_demo_v2 or graph.json not found")

    nodes: dict = {}
    cdr_edges, _, _ = _collect_cdr_edges(case_dir / "cdr.csv", nodes)
    bank_edges, _ = _collect_bank_edges(case_dir / "bank.csv", nodes)

    with graph_path.open("r", encoding="utf-8") as fh:
        g = json.load(fh)

    g_edges = [e for e in g["edges"] if e.get("source_kind") == "CSV"]

    cdr_tuples = {
        (e["relation"], e["source"], e["target"], e.get("call_count", e.get("sms_count", 0)))
        for e in cdr_edges
    }
    g_cdr_tuples = {
        (e["relation"], e["source"], e["target"], e.get("call_count", e.get("sms_count", 0)))
        for e in g_edges
        if e.get("relation") in ("COMMUNICATED_WITH", "ASSOCIATED_IMEI")
    }
    assert cdr_tuples == g_cdr_tuples

    bank_tuples = {
        (
            e["relation"],
            e["source"],
            e["target"],
            e.get("txn_count", 0),
            e.get("total_amount_paise", 0),
        )
        for e in bank_edges
    }
    g_bank_tuples = {
        (
            e["relation"],
            e["source"],
            e["target"],
            e.get("txn_count", 0),
            e.get("total_amount_paise", 0),
        )
        for e in g_edges
        if e.get("relation") == "TRANSFERRED_FUNDS"
    }
    assert bank_tuples == g_bank_tuples

