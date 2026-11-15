"""Simulation builder v2 for planted cases: opaque relabelling and leak-free graph."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import numpy as np

from case_simulation.builder import build_planted_graph


def build_planted_graph_v2(
    case_dir: str | Path,
    coverage: float,
    seed: int,
    coverage_index: int,
    csv_cache: tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, dict[str, Any]]] | None = None,
) -> tuple[dict[str, Any], dict[str, str], dict[str, list[str]]]:
    """Build planted graph with opaque person node IDs and canonical names.

    Args:
        case_dir: Path to case directory containing truth.json, cdr.csv, bank.csv.
        coverage: Fact sampling probability (e.g. 0.3, 0.6, 1.0).
        seed: Seed number for the case (e.g. 151..200).
        coverage_index: Index of coverage (0, 1, or 2) for RandomState(seed*1000 + coverage_index).
        csv_cache: Optional cached CSV parsed edges and nodes.

    Returns:
        (graph, truth_to_opaque, attributions)
        graph has opaque person IDs ('PERSON:P001', ...) and canonical names ('P001', ...),
        with NO truth IDs, 'PER_', or 'DEC_' in any node id or name.
    """
    rng_facts = np.random.RandomState(seed * 1000 + coverage_index)

    unlabeled_graph = build_planted_graph(
        case_dir=case_dir,
        coverage=coverage,
        fragmented=False,
        rng=rng_facts,
        csv_cache=csv_cache,
    )

    attributions_map = unlabeled_graph.pop("attributions", {})

    # Extract all person nodes
    person_nodes = [
        n for n in unlabeled_graph["nodes"] if n.get("type") == "PERSON"
    ]
    person_nodes.sort(key=lambda n: str(n["id"]))
    M = len(person_nodes)

    rng_relabel = np.random.RandomState(seed * 1000 + 500)
    opaque_ids = [f"PERSON:P{i:03d}" for i in range(1, M + 1)]
    perm = rng_relabel.permutation(M)
    assigned_opaque = [opaque_ids[p] for p in perm]

    truth_to_opaque: dict[str, str] = {}
    orig_to_opaque: dict[str, str] = {}

    for i, pnode in enumerate(person_nodes):
        orig_id = str(pnode["id"])
        truth_pid = str(pnode.get("person_id", orig_id.replace("PERSON:", "")))
        op_id = assigned_opaque[i]
        op_name = op_id.split(":")[-1]

        pnode["id"] = op_id
        pnode["canonical_name"] = op_name
        if "person_id" in pnode:
            del pnode["person_id"]

        truth_to_opaque[truth_pid] = op_id
        orig_to_opaque[orig_id] = op_id

    # Update edge endpoints
    for edge in unlabeled_graph["edges"]:
        src = str(edge.get("source"))
        tgt = str(edge.get("target"))
        if src in orig_to_opaque:
            edge["source"] = orig_to_opaque[src]
        if tgt in orig_to_opaque:
            edge["target"] = orig_to_opaque[tgt]

    # Re-sort nodes and edges
    unlabeled_graph["nodes"].sort(key=lambda n: str(n["id"]))
    unlabeled_graph["edges"].sort(
        key=lambda e: (
            str(e.get("source")),
            str(e.get("target")),
            str(e.get("relation")),
            str(e.get("source_kind")),
        )
    )

    # Sanity check: ensure no leak in node id or canonical_name
    for node in unlabeled_graph["nodes"]:
        nid = str(node.get("id", ""))
        name = str(node.get("canonical_name", ""))
        if "PER_" in nid or "PER_" in name or "DEC_" in nid or "DEC_" in name:
            raise ValueError(f"Leak detected in node: {node}")

    return unlabeled_graph, truth_to_opaque, attributions_map

