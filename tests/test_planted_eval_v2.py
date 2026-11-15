"""Tests for planted-case evaluation v2 (leak-free ranking, projection, composite v2)."""

from __future__ import annotations

import json
import math
from pathlib import Path

import networkx as nx
import numpy as np
import pytest

from case_analytics.baselines import compute_baselines
from case_analytics.projection import (
    build_person_projection,
    compute_pessimistic_ranks,
    compute_projection_scores,
)
from case_simulation.v2 import build_planted_graph_v2
from scripts.eval_planted_v2 import run_paired_bootstrap


def test_pessimistic_rank_ties_and_no_ids():
    """pessimistic rank gives tied persons the worst rank of their group and never uses ids."""
    scores = {"P_ALPHA": 10.0, "P_BETA": 8.0, "P_GAMMA": 8.0, "P_DELTA": 5.0}
    ranks = compute_pessimistic_ranks(scores)

    # P_ALPHA: 0 higher -> rank 1
    # P_BETA and P_GAMMA: both have score 8.0, 2 persons >= 8.0 (ALPHA, GAMMA/BETA) -> both rank 3
    # P_DELTA: 3 persons >= 5.0 -> rank 4
    assert ranks["P_ALPHA"] == 1
    assert ranks["P_BETA"] == 3
    assert ranks["P_GAMMA"] == 3
    assert ranks["P_DELTA"] == 4


def test_permuting_node_ids_leaves_ranks_unchanged():
    """permuting node ids leaves all ranks unchanged."""
    scores_original = {"A": 15.0, "B": 10.0, "C": 10.0, "D": 2.0}
    # Permute keys to Z, Y, X, W
    scores_permuted = {"Z": 15.0, "Y": 10.0, "X": 10.0, "W": 2.0}

    r_orig = compute_pessimistic_ranks(scores_original)
    r_perm = compute_pessimistic_ranks(scores_permuted)

    assert r_orig["A"] == r_perm["Z"] == 1
    assert r_orig["B"] == r_perm["Y"] == 3
    assert r_orig["C"] == r_perm["X"] == 3
    assert r_orig["D"] == r_perm["W"] == 4


def test_no_per_or_dec_in_relabelled_graph(tmp_path):
    """no node id or name in the relabelled graph contains 'PER_' or 'DEC_'."""
    case_dir = tmp_path / "case_leak_test"
    case_dir.mkdir()
    truth = {
        "case_id": "TEST_LEAK",
        "kingpin_ids": ["PER_A_KP_01"],
        "people": [
            {
                "person_id": "PER_A_KP_01",
                "name": "Per A Kingpin",
                "is_decoy": False,
                "phones": [{"phone": "9876543210"}],
                "accounts": [{"account_number": "ACC101"}],
            },
            {
                "person_id": "DEC_PIZZA_01",
                "name": "Decoy Pizza Person",
                "is_decoy": True,
                "phones": [{"phone": "9999999999"}],
                "accounts": [{"account_number": "ACC999"}],
            },
        ],
    }
    (case_dir / "truth.json").write_text(json.dumps(truth), encoding="utf-8")
    (case_dir / "cdr.csv").write_text("caller,callee,timestamp,call_duration_seconds,imei\n", encoding="utf-8")
    (case_dir / "bank.csv").write_text("from_acct,to_acct,timestamp,amount,mode\n", encoding="utf-8")

    graph, truth_map, _ = build_planted_graph_v2(
        case_dir=case_dir, coverage=1.0, seed=151, coverage_index=0
    )

    for node in graph["nodes"]:
        nid = str(node.get("id", ""))
        name = str(node.get("canonical_name", ""))
        assert "PER_" not in nid, f"Found PER_ in node id: {nid}"
        assert "PER_" not in name, f"Found PER_ in node name: {name}"
        assert "DEC_" not in nid, f"Found DEC_ in node id: {nid}"
        assert "DEC_" not in name, f"Found DEC_ in node name: {name}"

    assert "PER_A_KP_01" in truth_map
    assert "DEC_PIZZA_01" in truth_map


def test_projection_phone_calls_edge_weight():
    """projection: two persons whose phones call each other get an edge of weight 1.5*log2(1+calls)."""
    calls = 7
    expected_w = 1.5 * math.log2(1.0 + calls)  # 1.5 * 3.0 = 4.5

    graph = {
        "nodes": [
            {"id": "PERSON:P001", "type": "PERSON"},
            {"id": "PERSON:P002", "type": "PERSON"},
            {"id": "PHONE:PH1", "type": "PHONE"},
            {"id": "PHONE:PH2", "type": "PHONE"},
        ],
        "edges": [
            {"source": "PERSON:P001", "target": "PHONE:PH1", "relation": "OWNS_DEVICE"},
            {"source": "PERSON:P002", "target": "PHONE:PH2", "relation": "OWNS_DEVICE"},
            {
                "source": "PHONE:PH1",
                "target": "PHONE:PH2",
                "relation": "COMMUNICATED_WITH",
                "source_kind": "CSV",
                "call_count": calls,
                "sms_count": 0,
            },
        ],
    }

    G, _, _ = build_person_projection(graph)
    assert G.has_edge("PERSON:P001", "PERSON:P002")
    assert pytest.approx(G["PERSON:P001"]["PERSON:P002"]["weight"], 1e-9) == expected_w
    assert pytest.approx(G["PERSON:P001"]["PERSON:P002"]["distance"], 1e-9) == (1.0 / expected_w)


def test_projection_account_transfers_edge_weight():
    """transfers between controlled accounts give 1.0*log2(1+txns)."""
    txns = 3
    expected_w = 1.0 * math.log2(1.0 + txns)  # 1.0 * 2.0 = 2.0

    graph = {
        "nodes": [
            {"id": "PERSON:P001", "type": "PERSON"},
            {"id": "PERSON:P002", "type": "PERSON"},
            {"id": "ACCOUNT:ACC1", "type": "ACCOUNT"},
            {"id": "ACCOUNT:ACC2", "type": "ACCOUNT"},
        ],
        "edges": [
            {"source": "PERSON:P001", "target": "ACCOUNT:ACC1", "relation": "CONTROLS_ACCOUNT"},
            {"source": "PERSON:P002", "target": "ACCOUNT:ACC2", "relation": "CONTROLS_ACCOUNT"},
            {
                "source": "ACCOUNT:ACC1",
                "target": "ACCOUNT:ACC2",
                "relation": "TRANSFERRED_FUNDS",
                "source_kind": "CSV",
                "txn_count": txns,
                "total_amount_paise": 50000,
            },
        ],
    }

    G, _, _ = build_person_projection(graph)
    assert G.has_edge("PERSON:P001", "PERSON:P002")
    assert pytest.approx(G["PERSON:P001"]["PERSON:P002"]["weight"], 1e-9) == expected_w


def test_projection_shared_controlled_account_and_phone():
    """a shared controlled account gives 3.0 and a shared phone 1.5."""
    graph = {
        "nodes": [
            {"id": "PERSON:P001", "type": "PERSON"},
            {"id": "PERSON:P002", "type": "PERSON"},
            {"id": "PERSON:P003", "type": "PERSON"},
            {"id": "ACCOUNT:ACC_SHARED", "type": "ACCOUNT"},
            {"id": "PHONE:PH_SHARED", "type": "PHONE"},
        ],
        "edges": [
            # P001 and P002 share an account -> 3.0
            {"source": "PERSON:P001", "target": "ACCOUNT:ACC_SHARED", "relation": "CONTROLS_ACCOUNT"},
            {"source": "PERSON:P002", "target": "ACCOUNT:ACC_SHARED", "relation": "CONTROLS_ACCOUNT"},
            # P002 and P003 share a phone -> 1.5
            {"source": "PERSON:P002", "target": "PHONE:PH_SHARED", "relation": "OWNS_DEVICE"},
            {"source": "PERSON:P003", "target": "PHONE:PH_SHARED", "relation": "OWNS_DEVICE"},
        ],
    }

    G, _, _ = build_person_projection(graph)
    assert pytest.approx(G["PERSON:P001"]["PERSON:P002"]["weight"], 1e-9) == 3.0
    assert pytest.approx(G["PERSON:P002"]["PERSON:P003"]["weight"], 1e-9) == 1.5
    assert not G.has_edge("PERSON:P001", "PERSON:P003")


def test_projection_no_self_loops():
    """no self-loops in person-to-person projection."""
    graph = {
        "nodes": [
            {"id": "PERSON:P001", "type": "PERSON"},
            {"id": "ACCOUNT:A1", "type": "ACCOUNT"},
            {"id": "ACCOUNT:A2", "type": "ACCOUNT"},
            {"id": "PHONE:P1", "type": "PHONE"},
            {"id": "PHONE:P2", "type": "PHONE"},
        ],
        "edges": [
            {"source": "PERSON:P001", "target": "ACCOUNT:A1", "relation": "CONTROLS_ACCOUNT"},
            {"source": "PERSON:P001", "target": "ACCOUNT:A2", "relation": "CONTROLS_ACCOUNT"},
            {"source": "PERSON:P001", "target": "PHONE:P1", "relation": "OWNS_DEVICE"},
            {"source": "PERSON:P001", "target": "PHONE:P2", "relation": "OWNS_DEVICE"},
            {
                "source": "ACCOUNT:A1",
                "target": "ACCOUNT:A2",
                "relation": "TRANSFERRED_FUNDS",
                "source_kind": "CSV",
                "txn_count": 5,
                "total_amount_paise": 100000,
            },
            {
                "source": "PHONE:P1",
                "target": "PHONE:P2",
                "relation": "COMMUNICATED_WITH",
                "source_kind": "CSV",
                "call_count": 10,
            },
        ],
    }

    G, _, _ = build_person_projection(graph)
    assert not G.has_edge("PERSON:P001", "PERSON:P001")
    assert nx.number_of_selfloops(G) == 0


def test_financial_control_sent_plus_received_normalised():
    """financial_control equals sent plus received paise on controlled accounts, normalised."""
    graph = {
        "nodes": [
            {"id": "PERSON:P001", "type": "PERSON"},
            {"id": "PERSON:P002", "type": "PERSON"},
            {"id": "ACCOUNT:A1", "type": "ACCOUNT"},
            {"id": "ACCOUNT:A2", "type": "ACCOUNT"},
        ],
        "edges": [
            {"source": "PERSON:P001", "target": "ACCOUNT:A1", "relation": "CONTROLS_ACCOUNT"},
            {"source": "PERSON:P002", "target": "ACCOUNT:A2", "relation": "CONTROLS_ACCOUNT"},
            {
                "source": "ACCOUNT:A1",
                "target": "ACCOUNT:A2",
                "relation": "TRANSFERRED_FUNDS",
                "source_kind": "CSV",
                "total_amount_paise": 300000,
            },
            {
                "source": "ACCOUNT:A2",
                "target": "ACCOUNT:A1",
                "relation": "TRANSFERRED_FUNDS",
                "source_kind": "CSV",
                "total_amount_paise": 100000,
            },
        ],
    }

    _, norm_fin, raw_fin = build_person_projection(graph)
    # P001: sent 300000 + received 100000 = 400000
    # P002: sent 100000 + received 300000 = 400000
    assert raw_fin["PERSON:P001"] == 400000
    assert raw_fin["PERSON:P002"] == 400000
    assert norm_fin["PERSON:P001"] == 1.0
    assert norm_fin["PERSON:P002"] == 1.0


def test_composite_v2_formula_weights():
    """composite_v2 uses exactly 0.70/0.30 and 0.40/0.30/0.30."""
    graph = {
        "nodes": [
            {"id": "PERSON:P001", "type": "PERSON"},
            {"id": "PERSON:P002", "type": "PERSON"},
            {"id": "PERSON:P003", "type": "PERSON"},
            {"id": "PHONE:PH1", "type": "PHONE"},
            {"id": "PHONE:PH2", "type": "PHONE"},
            {"id": "ACCOUNT:AC1", "type": "ACCOUNT"},
        ],
        "edges": [
            {"source": "PERSON:P001", "target": "PHONE:PH1", "relation": "OWNS_DEVICE"},
            {"source": "PERSON:P002", "target": "PHONE:PH2", "relation": "OWNS_DEVICE"},
            {"source": "PERSON:P001", "target": "ACCOUNT:AC1", "relation": "CONTROLS_ACCOUNT"},
            {
                "source": "PHONE:PH1",
                "target": "PHONE:PH2",
                "relation": "COMMUNICATED_WITH",
                "source_kind": "CSV",
                "call_count": 3,
            },
            {
                "source": "ACCOUNT:AC1",
                "target": "ACCOUNT:EXTERNAL",
                "relation": "TRANSFERRED_FUNDS",
                "source_kind": "CSV",
                "total_amount_paise": 100000,
            },
        ],
    }

    res = compute_projection_scores(graph)
    comp = res["components"]
    raw = res["raw_scores"]

    for pid in res["person_ids"]:
        norm_D = comp["degree"][pid]
        norm_B = comp["betweenness"][pid]
        norm_E = comp["eigenvector"][pid]
        F = comp["financial"][pid]

        expected_structural = 0.40 * norm_D + 0.30 * norm_B + 0.30 * norm_E
        expected_v2 = 0.70 * expected_structural + 0.30 * F

        assert pytest.approx(raw["projection_only"][pid], 1e-9) == expected_structural
        assert pytest.approx(raw["financial_only"][pid], 1e-9) == F
        assert pytest.approx(raw["composite_v2"][pid], 1e-9) == expected_v2


def test_financial_only_ranks_equal_transfer_amount_paise():
    """financial_only ranks equal transfer_amount_paise ranks on a tiny example."""
    graph = {
        "nodes": [
            {"id": "PERSON:P001", "type": "PERSON", "roles": ["SUSPECT"]},
            {"id": "PERSON:P002", "type": "PERSON", "roles": ["SUSPECT"]},
            {"id": "PERSON:P003", "type": "PERSON", "roles": ["SUSPECT"]},
            {"id": "ACCOUNT:ACC1", "type": "ACCOUNT"},
            {"id": "ACCOUNT:ACC2", "type": "ACCOUNT"},
            {"id": "ACCOUNT:ACC3", "type": "ACCOUNT"},
        ],
        "edges": [
            {"source": "PERSON:P001", "target": "ACCOUNT:ACC1", "relation": "CONTROLS_ACCOUNT"},
            {"source": "PERSON:P002", "target": "ACCOUNT:ACC2", "relation": "CONTROLS_ACCOUNT"},
            {"source": "PERSON:P003", "target": "ACCOUNT:ACC3", "relation": "CONTROLS_ACCOUNT"},
            {
                "source": "ACCOUNT:ACC1",
                "target": "ACCOUNT:ACC2",
                "relation": "TRANSFERRED_FUNDS",
                "source_kind": "CSV",
                "total_amount_paise": 500000,
            },
            {
                "source": "ACCOUNT:ACC2",
                "target": "ACCOUNT:ACC3",
                "relation": "TRANSFERRED_FUNDS",
                "source_kind": "CSV",
                "total_amount_paise": 200000,
            },
        ],
    }

    proj_res = compute_projection_scores(graph)
    fin_ranks = proj_res["pessimistic_ranks"]["financial_only"]

    baselines_res = compute_baselines(graph, mode="strict")
    tx_ranking = baselines_res["baselines"]["transfer_amount_paise"]
    tx_scores = {row["node_id"]: row["score"] for row in tx_ranking}
    tx_ranks = compute_pessimistic_ranks(tx_scores)

    assert fin_ranks == tx_ranks


def test_same_seed_gives_identical_output(tmp_path):
    """same seed gives identical output."""
    case_dir = tmp_path / "case_det"
    case_dir.mkdir()
    truth = {
        "case_id": "TEST_DET",
        "kingpin_ids": ["PER_A_KP_01"],
        "people": [
            {
                "person_id": "PER_A_KP_01",
                "name": "Kingpin",
                "phones": [{"phone": "1111111111"}],
                "accounts": [{"account_number": "ACC1"}],
            }
        ],
    }
    (case_dir / "truth.json").write_text(json.dumps(truth), encoding="utf-8")
    (case_dir / "cdr.csv").write_text("caller,callee,timestamp,call_duration_seconds,imei\n", encoding="utf-8")
    (case_dir / "bank.csv").write_text("from_acct,to_acct,timestamp,amount,mode\n", encoding="utf-8")

    g1, t1, a1 = build_planted_graph_v2(case_dir, coverage=0.6, seed=151, coverage_index=1)
    g2, t2, a2 = build_planted_graph_v2(case_dir, coverage=0.6, seed=151, coverage_index=1)

    assert g1 == g2
    assert t1 == t2
    assert a1 == a2


def test_bootstrap_reproducible_and_diff_zero():
    """bootstrap reproducible and difference 0 for identical rankers."""
    hits = [2, 1, 0, 1, 2, 0, 1, 1, 2, 0]

    b_zero = run_paired_bootstrap(hits, hits, n_resamples=1000, seed=20261114)
    assert b_zero["mean_diff"] == 0.0
    assert b_zero["ci_95"] == [0.0, 0.0]

    # Reproducibility with different hits
    hits2 = [1, 0, 0, 1, 1, 0, 0, 1, 1, 0]
    b1 = run_paired_bootstrap(hits, hits2, n_resamples=1000, seed=20261114)
    b2 = run_paired_bootstrap(hits, hits2, n_resamples=1000, seed=20261114)

    assert b1 == b2


def test_no_truth_in_case_analytics_and_case_graph():
    """case_analytics and case_graph sources contain 'truth' nowhere (including new projection.py)."""
    repo_root = Path(__file__).resolve().parents[1]
    for pkg in ("case_analytics", "case_graph"):
        pkg_dir = repo_root / pkg
        for py_path in pkg_dir.rglob("*.py"):
            content = py_path.read_text(encoding="utf-8").lower()
            assert "truth" not in content, f"Word 'truth' found in {py_path}"

