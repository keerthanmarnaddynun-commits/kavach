"""Contract 2 rendering for KAVACH case graphs."""
from __future__ import annotations

import hashlib
import logging
from typing import Any

from case_analytics.projection import compute_projection_scores
from contracts.v1_1.validate import validate_graph

logger = logging.getLogger(__name__)

ALLOWED_NODE_TYPES = frozenset(
    {"PERSON", "PHONE", "IMEI", "ACCOUNT", "AADHAAR", "PAN", "UPI", "VEHICLE"}
)

ALLOWED_EDGE_LABELS = frozenset(
    {"OWNS_DEVICE", "ASSOCIATED_IMEI", "COMMUNICATED_WITH", "CONTROLS_ACCOUNT", "TRANSFERRED_FUNDS"}
)

ALLOWED_ROLES = frozenset({"SUSPECT", "OFFICER", "COMPLAINANT", "WITNESS"})


def compute_edge_id(source: str, target: str, relation: str, source_kind: str) -> str:
    """Deterministic edge ID formula for Contract 2 edges."""
    key = f"{source}|{target}|{relation}|{source_kind}"
    return "E-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def render_graph(
    graph: dict[str, Any],
    document_hash: str | None = None,
) -> dict[str, Any]:
    """
    Render internal case graph to Contract 2 Cytoscape elements and summary.
    Excludes candidate edges not in Contract 2 edge label enum.
    Validates output with contracts.v1_1.validate.validate_graph.
    """
    proj_scores = compute_projection_scores(graph)
    # F9: Structural composite score from raw_scores["projection_only"]
    scores_map = proj_scores.get("raw_scores", {}).get("projection_only", {})

    rendered_nodes: list[dict[str, Any]] = []
    seen_node_ids: set[str] = set()

    for node in graph.get("nodes", []):
        nid = str(node["id"])
        ntype = str(node.get("type", "PERSON"))
        if ntype not in ALLOWED_NODE_TYPES:
            continue

        label = str(node.get("canonical_name") or node.get("value") or nid)
        if ntype == "PERSON":
            score_val = float(round(scores_map.get(nid, 0.0), 6))
        else:
            score_val = 0.0

        # F7: ai_confidence preserves real values including 0.0, defaults to 0.0 when missing
        raw_conf = node.get("ai_confidence")
        if raw_conf is not None:
            try:
                conf_val = max(0.0, min(1.0, float(raw_conf)))
            except (ValueError, TypeError):
                conf_val = 0.0
        else:
            conf_val = 0.0

        ndata: dict[str, Any] = {
            "id": nid,
            "label": label,
            "type": ntype,
            "isKingpin": False,
            "centrality_score": max(0.0, min(1.0, score_val)),
            "ai_confidence": conf_val,
        }

        roles = node.get("roles", [])
        if roles and roles[0] in ALLOWED_ROLES:
            ndata["role"] = roles[0]

        rendered_nodes.append({"data": ndata})
        seen_node_ids.add(nid)

    rendered_edges: list[dict[str, Any]] = []
    seen_edge_ids: set[str] = set()
    dropped_non_enum = 0
    dropped_duplicates = 0

    for edge in graph.get("edges", []):
        rel = str(edge.get("relation", ""))
        if rel not in ALLOWED_EDGE_LABELS:
            dropped_non_enum += 1
            continue

        src = str(edge["source"])
        tgt = str(edge["target"])
        if src not in seen_node_ids or tgt not in seen_node_ids:
            continue

        skind = str(edge.get("source_kind", "FIR"))
        eid = compute_edge_id(src, tgt, rel, skind)
        if eid in seen_edge_ids:
            dropped_duplicates += 1
            continue
        seen_edge_ids.add(eid)

        edata: dict[str, Any] = {
            "id": eid,
            "source": src,
            "target": tgt,
            "label": rel,
        }

        if "txn_count" in edge and isinstance(edge["txn_count"], int) and edge["txn_count"] >= 0:
            edata["count"] = edge["txn_count"]

        if "total_amount" in edge:
            try:
                amt = float(edge["total_amount"])
                if amt > 0:
                    edata["amount"] = amt
            except (ValueError, TypeError):
                pass

        rendered_edges.append({"data": edata})

    doc_hash = document_hash or graph.get("document_hash") or ("0" * 64)

    rendered = {
        "summary": {
            "schema_version": "1.1",
            "total_nodes": len(rendered_nodes),
            "total_edges": len(rendered_edges),
            "kingpin_node_id": None,
            "document_hash": doc_hash,
        },
        "elements": {
            "nodes": rendered_nodes,
            "edges": rendered_edges,
        },
    }

    logger.info(
        "Rendered graph: %d nodes, %d edges (dropped %d non-enum, %d duplicates)",
        len(rendered_nodes),
        len(rendered_edges),
        dropped_non_enum,
        dropped_duplicates,
    )
    validate_graph(rendered)
    return rendered
