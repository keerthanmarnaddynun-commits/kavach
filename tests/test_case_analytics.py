"""Tests for case_analytics kingpin scoring, baselines, and robustness."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from case_analytics.baselines import compute_baselines
from case_analytics.scores import (
    COMPOSITE_WEIGHTS,
    DEFAULT_BASE_WEIGHTS,
    build_analytics_graph,
    compute_kingpin_scores,
    compute_robustness,
)
from scripts.run_kingpin_scores import main as run_cli_main

REPO_ROOT = Path(__file__).resolve().parents[1]


def _suspect(nid: str, name: str) -> dict:
    return {
        "id": nid,
        "type": "PERSON",
        "roles": ["SUSPECT"],
        "canonical_name": name,
        "names": [name],
    }


def _node(nid: str, ntype: str, **extra) -> dict:
    out = {"id": nid, "type": ntype}
    out.update(extra)
    return out


def test_star_centre_ranks_first_and_normalisation_bounds() -> None:
    graph_data = {
        "nodes": [
            _suspect("PERSON:P1", "Centre Kingpin"),
            _suspect("PERSON:P2", "Spoke A"),
            _suspect("PERSON:P3", "Spoke B"),
            _suspect("PERSON:P4", "Spoke C"),
            _node("ACCOUNT:1", "ACCOUNT"),
            _node("ACCOUNT:2", "ACCOUNT"),
            _node("ACCOUNT:3", "ACCOUNT"),
        ],
        "edges": [
            {"source": "PERSON:P1", "target": "ACCOUNT:1", "relation": "CONTROLS_ACCOUNT", "source_kind": "FIR"},
            {"source": "PERSON:P1", "target": "ACCOUNT:2", "relation": "CONTROLS_ACCOUNT", "source_kind": "FIR"},
            {"source": "PERSON:P1", "target": "ACCOUNT:3", "relation": "CONTROLS_ACCOUNT", "source_kind": "FIR"},
            {"source": "PERSON:P2", "target": "ACCOUNT:1", "relation": "CONTROLS_ACCOUNT", "source_kind": "FIR"},
            {"source": "PERSON:P3", "target": "ACCOUNT:2", "relation": "CONTROLS_ACCOUNT", "source_kind": "FIR"},
            {"source": "PERSON:P4", "target": "ACCOUNT:3", "relation": "CONTROLS_ACCOUNT", "source_kind": "FIR"},
        ],
    }

    assert math.isclose(sum(COMPOSITE_WEIGHTS.values()), 1.0, rel_tol=1e-9)

    res = compute_kingpin_scores(graph_data, mode="strict")
    ranking = res["ranking"]
    assert ranking[0]["node_id"] == "PERSON:P1"
    assert ranking[0]["components"] == {"betweenness": 1.0, "degree": 1.0, "eigenvector": 1.0}
    assert ranking[0]["composite"] == 1.0

    for row in ranking:
        for comp_val in row["components"].values():
            assert 0.0 <= comp_val <= 1.0


def test_vehicle_and_non_suspect_persons_excluded() -> None:
    graph_data = {
        "nodes": [
            _suspect("PERSON:S1", "Suspect One"),
            _node("PERSON:OFF1", "PERSON", roles=["OFFICER"], canonical_name="Officer One"),
            _node("PERSON:WIT1", "PERSON", roles=["WITNESS"], canonical_name="Witness One"),
            _node("PHONE:100", "PHONE"),
            _node("PHONE:200", "PHONE"),
            _node("VEHICLE:DL1C0001", "VEHICLE"),
        ],
        "edges": [
            {"source": "PERSON:S1", "target": "PHONE:100", "relation": "OWNS_DEVICE", "source_kind": "FIR"},
            {"source": "PERSON:OFF1", "target": "PHONE:200", "relation": "OWNS_DEVICE", "source_kind": "FIR"},
            {"source": "PHONE:100", "target": "PHONE:200", "relation": "COMMUNICATED_WITH", "source_kind": "FIR"},
        ],
    }

    G, _ = build_analytics_graph(graph_data, mode="strict")
    assert "PERSON:S1" in G
    assert "PERSON:OFF1" not in G
    assert "PERSON:WIT1" not in G
    assert "VEHICLE:DL1C0001" not in G

    res = compute_kingpin_scores(graph_data, mode="strict")
    assert [r["node_id"] for r in res["ranking"]] == ["PERSON:S1"]


def test_strict_ignores_candidate_and_resolved_collapses_with_edge_union() -> None:
    graph_data = {
        "nodes": [
            _suspect("PERSON:FIR_01:ent_01", "Rajesh Kumar"),
            _suspect("PERSON:FIR_02:ent_01", "Rajesh Kumar"),
            _node("PHONE:111", "PHONE"),
            _node("ACCOUNT:222", "ACCOUNT"),
        ],
        "edges": [
            {
                "source": "PERSON:FIR_02:ent_01",
                "target": "PERSON:FIR_01:ent_01",
                "relation": "SAME_AS_CANDIDATE",
                "source_kind": "RULE",
                "reasons": ["same_name"],
            },
            {
                "source": "PERSON:FIR_01:ent_01",
                "target": "PHONE:111",
                "relation": "OWNS_DEVICE",
                "source_kind": "FIR",
            },
            {
                "source": "PERSON:FIR_02:ent_01",
                "target": "ACCOUNT:222",
                "relation": "CONTROLS_ACCOUNT",
                "source_kind": "FIR",
            },
        ],
    }

    strict_res = compute_kingpin_scores(graph_data, mode="strict")
    assert [r["node_id"] for r in strict_res["ranking"]] == [
        "PERSON:FIR_02:ent_01",
        "PERSON:FIR_01:ent_01",
    ]
    assert strict_res["person_nodes_ranked"] == 2

    resolved_res = compute_kingpin_scores(graph_data, mode="resolved")
    assert resolved_res["person_nodes_ranked"] == 1
    collapsed = resolved_res["ranking"][0]
    assert collapsed["node_id"] == "PERSON:FIR_01:ent_01"
    assert set(collapsed["collapsed_node_ids"]) == {
        "PERSON:FIR_01:ent_01",
        "PERSON:FIR_02:ent_01",
    }
    assert collapsed["linked"]["phones"] == 1
    assert collapsed["linked"]["accounts"] == 1


def test_parallel_edges_sum_weights() -> None:
    graph_data = {
        "nodes": [
            _suspect("PERSON:A", "Alpha"),
            _node("PHONE:1", "PHONE"),
        ],
        "edges": [
            {
                "source": "PERSON:A",
                "target": "PHONE:1",
                "relation": "OWNS_DEVICE",
                "source_kind": "FIR",
            },
            {
                "source": "PERSON:A",
                "target": "PHONE:1",
                "relation": "OWNS_DEVICE",
                "source_kind": "FIR",
            },
        ],
    }

    G, _ = build_analytics_graph(graph_data, mode="strict")
    expected_w = 2.0 * DEFAULT_BASE_WEIGHTS["OWNS_DEVICE"] * math.log2(1 + 1)
    assert math.isclose(G["PERSON:A"]["PHONE:1"]["weight"], expected_w, rel_tol=1e-9)
    assert math.isclose(G["PERSON:A"]["PHONE:1"]["distance"], 1.0 / expected_w, rel_tol=1e-9)


def test_betweenness_uses_inverse_weight_distance() -> None:
    # A --(weak=1.5)-- B
    # A --(strong)-- MID --(strong)-- B
    # Inverse distance along A-MID-B is smaller than direct A-B edge,
    # so shortest path between A and B passes through MID, giving MID > 0 betweenness.
    graph_data = {
        "nodes": [
            _suspect("PERSON:A", "Alpha"),
            _suspect("PERSON:B", "Beta"),
            _suspect("PERSON:MID", "Middleman"),
            _node("ACCOUNT:X", "ACCOUNT"),
        ],
        "edges": [
            # Direct weak edge A-B via ACCOUNT:X? No, direct between A and B:
            {
                "source": "PERSON:A",
                "target": "PERSON:B",
                "relation": "TRANSFERRED_FUNDS",
                "source_kind": "CSV",
                "txn_count": 1,  # weight = 1.0 * log2(2) = 1.0 -> distance = 1.0
                "total_amount_paise": 100,
            },
            {
                "source": "PERSON:A",
                "target": "PERSON:MID",
                "relation": "TRANSFERRED_FUNDS",
                "source_kind": "CSV",
                "txn_count": 1023,  # weight = 10.0 -> distance = 0.1
                "total_amount_paise": 100,
            },
            {
                "source": "PERSON:MID",
                "target": "PERSON:B",
                "relation": "TRANSFERRED_FUNDS",
                "source_kind": "CSV",
                "txn_count": 1023,  # weight = 10.0 -> distance = 0.1
                "total_amount_paise": 100,
            },
        ],
    }

    res = compute_kingpin_scores(graph_data, mode="strict")
    by_id = {r["node_id"]: r for r in res["ranking"]}
    # Total inverse-weight distance via MID = 0.2 < 1.0 direct, so MID captures betweenness!
    assert by_id["PERSON:MID"]["components"]["betweenness"] == 1.0
    assert by_id["PERSON:A"]["components"]["betweenness"] == 0.0
    assert by_id["PERSON:B"]["components"]["betweenness"] == 0.0


def test_ranking_and_robustness_deterministic_across_runs() -> None:
    graph_data = {
        "nodes": [
            _suspect("PERSON:A", "Alpha"),
            _suspect("PERSON:B", "Beta"),
            _node("PHONE:1", "PHONE"),
            _node("ACCOUNT:1", "ACCOUNT"),
        ],
        "edges": [
            {"source": "PERSON:A", "target": "PHONE:1", "relation": "OWNS_DEVICE", "source_kind": "FIR"},
            {"source": "PERSON:B", "target": "ACCOUNT:1", "relation": "CONTROLS_ACCOUNT", "source_kind": "FIR"},
            {
                "source": "PERSON:A",
                "target": "ACCOUNT:1",
                "relation": "TRANSFERRED_FUNDS",
                "source_kind": "CSV",
                "txn_count": 4,
                "total_amount_paise": 5000,
            },
        ],
    }

    s1 = compute_kingpin_scores(graph_data, mode="strict")
    s2 = compute_kingpin_scores(graph_data, mode="strict")
    r1 = compute_robustness(graph_data, mode="strict", n_samples=200, seed=20261112)
    r2 = compute_robustness(graph_data, mode="strict", n_samples=200, seed=20261112)

    assert json.dumps(s1, sort_keys=True) == json.dumps(s2, sort_keys=True)
    assert json.dumps(r1, sort_keys=True) == json.dumps(r2, sort_keys=True)


def test_run_kingpin_scores_refuses_existing_output_dir(tmp_path: Path) -> None:
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps({"nodes": [], "edges": []}), encoding="utf-8")
    out_dir = tmp_path / "analytics"
    out_dir.mkdir()

    rc = run_cli_main(["--graph", str(graph_path), "--out-dir", str(out_dir)])
    assert rc != 0


def test_baseline_call_count_ranking_tiny_cdr() -> None:
    graph_data = {
        "nodes": [
            _suspect("PERSON:A", "Heavy Caller"),
            _suspect("PERSON:B", "Light Caller"),
            _node("PHONE:1", "PHONE"),
            _node("PHONE:2", "PHONE"),
            _node("PHONE:3", "PHONE"),
        ],
        "edges": [
            {"source": "PERSON:A", "target": "PHONE:1", "relation": "OWNS_DEVICE", "source_kind": "FIR"},
            {"source": "PERSON:B", "target": "PHONE:2", "relation": "OWNS_DEVICE", "source_kind": "FIR"},
            {
                "source": "PHONE:1",
                "target": "PHONE:3",
                "relation": "COMMUNICATED_WITH",
                "source_kind": "CSV",
                "voice_count": 8,
                "sms_count": 4,
            },
            {
                "source": "PHONE:2",
                "target": "PHONE:3",
                "relation": "COMMUNICATED_WITH",
                "source_kind": "CSV",
                "voice_count": 2,
                "sms_count": 1,
            },
        ],
    }

    b = compute_baselines(graph_data, mode="strict")["baselines"]
    call_rank = b["call_count"]
    assert call_rank[0]["node_id"] == "PERSON:A"
    assert call_rank[0]["score"] == 12
    assert call_rank[1]["node_id"] == "PERSON:B"
    assert call_rank[1]["score"] == 3


def test_case_analytics_source_never_mentions_truth() -> None:
    for py_file in (REPO_ROOT / "case_analytics").rglob("*.py"):
        assert "truth" not in py_file.read_text(encoding="utf-8").lower()
