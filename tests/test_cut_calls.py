"""Tests for call_layer_graph, break_groups, baselines, and unowned bridging phones."""

from __future__ import annotations

import itertools
import json
from pathlib import Path
import pytest
import networkx as nx
import numpy as np

from case_detectors.cut_calls import (
    articulation_persons,
    break_groups,
    call_layer_graph,
    detect_communities_calls,
    top2_betweenness,
    top2_degree,
    unowned_bridging_phones,
)


def test_call_layer_edges_and_unowned_ignored():
    """call-layer edges from calls between owned phones and shared phones; no edge from unowned phones."""
    # P1 owns PH1, P2 owns PH2, P3 owns PH3, P4 shares PH3 with P3.
    # PH_UNOWNED is not owned by anyone.
    owners = {
        "PH1": ["P1"],
        "PH2": ["P2"],
        "PH3": ["P3", "P4"],  # shared phone -> edge (P3, P4)
    }

    cdr_rows = [
        # Call between owned phones -> edge (P1, P2)
        {"a_party": "PH1", "b_party": "PH2"},
        # Call between owned and unowned -> NO edge
        {"a_party": "PH1", "b_party": "PH_UNOWNED"},
        # Call between two unowned -> NO edge
        {"a_party": "PH_UNOWNED", "b_party": "PH_ANOTHER"},
        # Self call -> ignored
        {"a_party": "PH1", "b_party": "PH1"},
    ]

    graph = call_layer_graph(cdr_rows, owners)
    node_ids = [n["id"] for n in graph["nodes"]]
    assert node_ids == ["P1", "P2", "P3", "P4"]

    edges = sorted([(e["source"], e["target"]) for e in graph["edges"]])
    expected_edges = [("P1", "P2"), ("P3", "P4")]
    assert edges == expected_edges


def test_min_vertex_cut_equals_brute_force_on_random_call_layer_graphs():
    """min vertex cut equals brute-force search over person subsets on at least 5 small random graphs."""
    for seed in (201, 202, 203, 204, 205):
        rng = np.random.RandomState(seed)
        # 7 nodes: 0, 1 in group_a; 5, 6 in group_b; 2, 3, 4 candidates
        # Make an erdos-renyi graph
        G_raw = nx.erdos_renyi_graph(n=7, p=0.45, seed=seed)

        # Remove any direct edges between group A and group B to ensure a valid cut is tested
        group_a = ["N0", "N1"]
        group_b = ["N5", "N6"]
        candidates = ["N2", "N3", "N4"]

        for u in (0, 1):
            for v in (5, 6):
                if G_raw.has_edge(u, v):
                    G_raw.remove_edge(u, v)

        nodes = [{"id": f"N{i}", "type": "PERSON"} for i in range(7)]
        edges = [
            {"source": f"N{min(u, v)}", "target": f"N{max(u, v)}"}
            for u, v in G_raw.edges()
        ]
        graph = {"edges": edges, "nodes": nodes}

        res = break_groups(graph, group_a, group_b)

        # Brute force search over candidate subsets
        G = nx.Graph()
        for e in edges:
            G.add_edge(e["source"], e["target"])
        for n in nodes:
            G.add_node(n["id"])

        bf_found_cut = False
        bf_min_size = 999
        bf_cut: list[str] = []

        # Check if already disconnected
        connected = False
        for a in group_a:
            for b in group_b:
                if nx.has_path(G, a, b):
                    connected = True
                    break
            if connected:
                break

        if not connected:
            bf_found_cut = True
            bf_min_size = 0
            bf_cut = []
        else:
            for k in range(1, len(candidates) + 1):
                found_k = False
                for subset in itertools.combinations(candidates, k):
                    H = G.copy()
                    H.remove_nodes_from(subset)
                    has_ab_path = False
                    for a in group_a:
                        for b in group_b:
                            if nx.has_path(H, a, b):
                                has_ab_path = True
                                break
                        if has_ab_path:
                            break
                    if not has_ab_path:
                        bf_found_cut = True
                        bf_min_size = k
                        bf_cut = sorted(subset)
                        found_k = True
                        break
                if found_k:
                    break

        if bf_found_cut:
            assert res["finite"] is True
            assert res["size"] == bf_min_size
            # Verify the returned cut indeed separates group_a and group_b
            H_res = G.copy()
            H_res.remove_nodes_from(res["cut"])
            for a in group_a:
                for b in group_b:
                    assert not nx.has_path(H_res, a, b)
        else:
            assert res["finite"] is False


def test_direct_terminal_link_gives_finite_false():
    """direct terminal link gives finite False with reason direct_link."""
    graph = {
        "nodes": [
            {"id": "A", "type": "PERSON"},
            {"id": "B", "type": "PERSON"},
            {"id": "M", "type": "PERSON"},
        ],
        "edges": [
            {"source": "A", "target": "B"},  # direct link
            {"source": "A", "target": "M"},
            {"source": "M", "target": "B"},
        ],
    }
    res = break_groups(graph, ["A"], ["B"])
    assert res["finite"] is False
    assert res["reason"] == "direct_link"
    assert res["direct_links_count"] == 1


def test_terminals_never_appear_in_cut():
    """terminals never appear in the cut."""
    graph = {
        "nodes": [
            {"id": "GA_1", "type": "PERSON"},
            {"id": "CR_1", "type": "PERSON"},
            {"id": "CR_2", "type": "PERSON"},
            {"id": "GB_1", "type": "PERSON"},
        ],
        "edges": [
            {"source": "GA_1", "target": "CR_1"},
            {"source": "CR_1", "target": "CR_2"},
            {"source": "CR_2", "target": "GB_1"},
        ],
    }
    res = break_groups(graph, ["GA_1"], ["GB_1"])
    assert res["finite"] is True
    assert res["size"] in (1, 2)
    assert "GA_1" not in res["cut"]
    assert "GB_1" not in res["cut"]


def test_top2_baselines_with_ties_not_exact():
    """top2 baselines with ties count as not exact."""
    # Star graph with center C and 3 leaves L1, L2, L3:
    # C is #1 (deg 3, betw 1.0).
    # L1, L2, L3 all have equal score (deg 1, betw 0.0), so position 2 and 3 are tied!
    graph = {
        "nodes": [
            {"id": "C", "type": "PERSON"},
            {"id": "L1", "type": "PERSON"},
            {"id": "L2", "type": "PERSON"},
            {"id": "L3", "type": "PERSON"},
        ],
        "edges": [
            {"source": "C", "target": "L1"},
            {"source": "C", "target": "L2"},
            {"source": "C", "target": "L3"},
        ],
    }
    res_b = top2_betweenness(graph)
    assert res_b["tied"] is True

    res_d = top2_degree(graph)
    assert res_d["tied"] is True


def test_unowned_bridging_phones():
    """unowned_bridging_phones finds a phone calling both groups and ignores phones calling only one."""
    owners = {
        "PH_A": ["GA1"],
        "PH_B": ["GB1"],
    }
    cdr_rows = [
        # BRIDGE calls PH_A and PH_B -> should be detected
        {"a_party": "BRIDGE", "b_party": "PH_A"},
        {"a_party": "BRIDGE", "b_party": "PH_B"},
        # ONE_SIDE only calls PH_A -> should NOT be detected
        {"a_party": "ONE_SIDE", "b_party": "PH_A"},
        # OWNED_PHONE calls both -> should NOT be detected because it is owned
        {"a_party": "PH_A", "b_party": "PH_B"},
    ]
    leads = unowned_bridging_phones(cdr_rows, owners, ["GA1"], ["GB1"])
    assert len(leads) == 1
    assert leads[0]["phone"] == "BRIDGE"
    assert leads[0]["calls_with_group_a"] == 1
    assert leads[0]["calls_with_group_b"] == 1
    assert leads[0]["total_calls"] == 2
    assert leads[0]["evidence_rows"] == [1, 2]
    assert "unverified leads" in leads[0]["status"]


def test_opaque_ids_contain_no_per_or_dec():
    """opaque ids contain no PER_ or DEC_."""
    from case_simulation.v2 import build_planted_graph_v2

    # Check on seed 151
    g, t2o, _ = build_planted_graph_v2(
        case_dir="data/synthetic/out/planted_v2/seed_151",
        coverage=1.0,
        seed=151,
        coverage_index=2,
    )
    for node in g["nodes"]:
        nid = str(node.get("id", ""))
        name = str(node.get("canonical_name", ""))
        assert "PER_" not in nid
        assert "DEC_" not in nid
        assert "PER_" not in name
        assert "DEC_" not in name


def test_same_seed_gives_identical_output():
    """same seed gives identical output across two runs."""
    owners = {
        "P1": ["PERSON:P1"],
        "P2": ["PERSON:P2"],
        "P3": ["PERSON:P3"],
    }
    cdr = [
        {"a_party": "P1", "b_party": "P2"},
        {"a_party": "P2", "b_party": "P3"},
    ]
    g1 = call_layer_graph(cdr, owners)
    g2 = call_layer_graph(cdr, owners)
    assert json.dumps(g1, sort_keys=True) == json.dumps(g2, sort_keys=True)

    c1 = detect_communities_calls(g1, seed=20261116)
    c2 = detect_communities_calls(g2, seed=20261116)
    assert c1 == c2


def test_scripts_refuse_existing_output_folder(tmp_path):
    """scripts refuse an existing output folder."""
    from scripts.generate_planted_cases_v3 import generate_planted_cases_v3
    from scripts.check_planted_cases_v3 import run_checks

    existing_dir = tmp_path / "already_exists"
    existing_dir.mkdir()

    with pytest.raises(FileExistsError):
        generate_planted_cases_v3(out_base_dir=existing_dir)

    existing_file = tmp_path / "check.json"
    existing_file.write_text("{}", encoding="utf-8")

    with pytest.raises(FileExistsError):
        run_checks(cases_dir=tmp_path, out_file=existing_file)


def test_no_truth_in_case_detectors_and_config():
    """the word 'truth' appears nowhere in case_detectors/ sources or config/."""
    for p in Path("case_detectors").glob("*.py"):
        content = p.read_text(encoding="utf-8").lower()
        assert "truth" not in content, f"Found 'truth' in {p}"

    for p in Path("config").glob("*.json"):
        content = p.read_text(encoding="utf-8").lower()
        assert "truth" not in content, f"Found 'truth' in {p}"
