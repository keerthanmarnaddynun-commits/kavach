"""Structural and schema checks for assembled case graphs."""

from __future__ import annotations

from typing import Any

ALLOWED_NODE_TYPES: frozenset[str] = frozenset(
    {
        "PERSON",
        "PHONE",
        "IMEI",
        "ACCOUNT",
        "AADHAAR",
        "PAN",
        "UPI",
        "VEHICLE",
    }
)

ALLOWED_RELATION_TYPES: frozenset[str] = frozenset(
    {
        "OWNS_DEVICE",
        "ASSOCIATED_IMEI",
        "COMMUNICATED_WITH",
        "CONTROLS_ACCOUNT",
        "TRANSFERRED_FUNDS",
        "SAME_AS_CANDIDATE",
    }
)

ALLOWED_SOURCE_KINDS: frozenset[str] = frozenset({"FIR", "CSV", "RULE"})


def validate_graph(graph: dict[str, Any]) -> list[str]:
    """Validate nodes, edges, keys, allowed types, and CSV row provenance."""
    errors: list[str] = []
    if not isinstance(graph, dict):
        return ["graph must be a dict"]

    nodes = graph.get("nodes")
    edges = graph.get("edges")
    if not isinstance(nodes, list):
        errors.append("graph['nodes'] must be a list")
        return errors
    if not isinstance(edges, list):
        errors.append("graph['edges'] must be a list")
        return errors

    node_ids: set[str] = set()
    for idx, node in enumerate(nodes):
        if not isinstance(node, dict):
            errors.append(f"node[{idx}] must be a dict")
            continue
        nid = node.get("id")
        ntype = node.get("type")
        if not isinstance(nid, str) or not nid:
            errors.append(f"node[{idx}] missing non-empty string 'id'")
            continue
        if nid in node_ids:
            errors.append(f"duplicate node id: {nid}")
        node_ids.add(nid)

        if ntype not in ALLOWED_NODE_TYPES:
            errors.append(f"node {nid} has disallowed type: {ntype!r}")

    seen_edge_keys: set[tuple[Any, Any, Any, Any]] = set()
    for idx, edge in enumerate(edges):
        if not isinstance(edge, dict):
            errors.append(f"edge[{idx}] must be a dict")
            continue

        src = edge.get("source")
        tgt = edge.get("target")
        rel = edge.get("relation")
        skind = edge.get("source_kind")

        if not isinstance(src, str) or src not in node_ids:
            errors.append(f"edge[{idx}] has dangling source node: {src!r}")
        if not isinstance(tgt, str) or tgt not in node_ids:
            errors.append(f"edge[{idx}] has dangling target node: {tgt!r}")
        if rel not in ALLOWED_RELATION_TYPES:
            errors.append(f"edge[{idx}] has disallowed relation: {rel!r}")
        if skind not in ALLOWED_SOURCE_KINDS:
            errors.append(f"edge[{idx}] has disallowed source_kind: {skind!r}")

        edge_key = (src, tgt, rel, skind)
        if edge_key in seen_edge_keys:
            errors.append(f"duplicate edge key: {edge_key!r}")
        seen_edge_keys.add(edge_key)

        if skind == "CSV":
            row_nums = edge.get("row_numbers")
            if (
                not isinstance(row_nums, list)
                or len(row_nums) == 0
                or not all(isinstance(r, int) and not isinstance(r, bool) and r >= 1 for r in row_nums)
            ):
                errors.append(
                    f"CSV edge {edge_key!r} must have non-empty integer 'row_numbers'"
                )

    return errors

