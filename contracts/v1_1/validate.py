"""
Validation module for Contract v1.1 schemas and semantic rules.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
from jsonschema import Draft202012Validator

SCHEMA_DIR = Path(__file__).resolve().parent

with open(SCHEMA_DIR / "ai_output_schema.json", "r", encoding="utf-8") as _f:
    AI_OUTPUT_SCHEMA: dict[str, Any] = json.load(_f)

with open(SCHEMA_DIR / "graph_render_schema.json", "r", encoding="utf-8") as _f:
    GRAPH_RENDER_SCHEMA: dict[str, Any] = json.load(_f)

_AI_OUTPUT_VALIDATOR = Draft202012Validator(AI_OUTPUT_SCHEMA)
_GRAPH_RENDER_VALIDATOR = Draft202012Validator(GRAPH_RENDER_SCHEMA)

VALID_TYPE_PAIRS: dict[str, set[tuple[str, str]]] = {
    "OWNS_DEVICE": {("PERSON", "PHONE")},
    "ASSOCIATED_IMEI": {("PHONE", "IMEI")},
    "COMMUNICATED_WITH": {("PHONE", "PHONE")},
    "CONTROLS_ACCOUNT": {("PERSON", "ACCOUNT")},
    "TRANSFERRED_FUNDS": {("PERSON", "ACCOUNT"), ("ACCOUNT", "ACCOUNT")},
}


def validate_ai_output(doc: dict[str, Any]) -> None:
    """Validate AI output against Contract 1 v1.1 schema and semantic rules."""
    try:
        _AI_OUTPUT_VALIDATOR.validate(doc)
    except jsonschema.ValidationError as e:
        raise ValueError(f"AI output schema validation error: {e.message}") from e

    # Semantic checks
    seen_ids: set[str] = set()
    entity_map: dict[str, dict[str, Any]] = {}
    for ent in doc.get("entities", []):
        eid = ent["id"]
        if eid in seen_ids:
            raise ValueError(f"Duplicate entity id: '{eid}'")
        seen_ids.add(eid)
        entity_map[eid] = ent

        # Span checks
        span = ent.get("char_span")
        if span:
            s, e = span
            if s >= e:
                raise ValueError(f"Entity '{eid}' char_span start >= end: [{s}, {e}]")

        mentions = ent.get("mentions", [])
        if not mentions:
            raise ValueError(f"Entity '{eid}' has no mentions")

        first_span = mentions[0].get("char_span")
        if span != first_span:
            raise ValueError(
                f"Entity '{eid}' char_span {span} does not match first mention span {first_span}"
            )

        for m_idx, m in enumerate(mentions):
            ms, me = m["char_span"]
            if ms >= me:
                raise ValueError(
                    f"Entity '{eid}' mention[{m_idx}] char_span start >= end: [{ms}, {me}]"
                )

    for rel in doc.get("relationships", []):
        src = rel["source"]
        tgt = rel["target"]
        if src not in entity_map:
            raise ValueError(f"Relationship source '{src}' does not exist in entities")
        if tgt not in entity_map:
            raise ValueError(f"Relationship target '{tgt}' does not exist in entities")

        relation_name = rel["relation"]
        allowed = VALID_TYPE_PAIRS.get(relation_name)
        if allowed is None:
            raise ValueError(f"Unknown relation '{relation_name}'")

        src_type = entity_map[src]["type"]
        tgt_type = entity_map[tgt]["type"]
        if (src_type, tgt_type) not in allowed:
            raise ValueError(
                f"Invalid type pair ({src_type} -> {tgt_type}) for relation '{relation_name}'"
            )

        if "amount" in rel and rel["amount"] is not None and rel["amount"] <= 0:
            raise ValueError(f"Relationship amount must be positive, got {rel['amount']}")

        ev_span = rel.get("evidence_char_span")
        if ev_span:
            es, ee = ev_span
            if es >= ee:
                raise ValueError(f"Relationship evidence_char_span start >= end: [{es}, {ee}]")


def validate_graph(doc: dict[str, Any]) -> None:
    """Validate Graph Render against Contract 2 v1.1 schema and semantic rules."""
    try:
        _GRAPH_RENDER_VALIDATOR.validate(doc)
    except jsonschema.ValidationError as e:
        raise ValueError(f"Graph render schema validation error: {e.message}") from e

    summary = doc.get("summary", {})
    elements = doc.get("elements", {})
    nodes = elements.get("nodes", [])
    edges = elements.get("edges", [])

    total_nodes = summary.get("total_nodes")
    if total_nodes != len(nodes):
        raise ValueError(
            f"summary.total_nodes ({total_nodes}) does not match nodes count ({len(nodes)})"
        )

    total_edges = summary.get("total_edges")
    if total_edges != len(edges):
        raise ValueError(
            f"summary.total_edges ({total_edges}) does not match edges count ({len(edges)})"
        )

    seen_node_ids: set[str] = set()
    node_map: dict[str, dict[str, Any]] = {}
    for node in nodes:
        ndata = node["data"]
        nid = ndata["id"]
        if nid in seen_node_ids:
            raise ValueError(f"Duplicate node id: '{nid}'")
        seen_node_ids.add(nid)
        node_map[nid] = ndata

    seen_edge_ids: set[str] = set()
    for edge in edges:
        edata = edge["data"]
        eid = edata["id"]
        if eid in seen_edge_ids:
            raise ValueError(f"Duplicate edge id: '{eid}'")
        seen_edge_ids.add(eid)

        src = edata["source"]
        tgt = edata["target"]
        if src not in node_map:
            raise ValueError(f"Edge source '{src}' does not exist in nodes")
        if tgt not in node_map:
            raise ValueError(f"Edge target '{tgt}' does not exist in nodes")

        label = edata["label"]
        allowed = VALID_TYPE_PAIRS.get(label)
        if allowed is None:
            raise ValueError(f"Unknown edge label '{label}'")

        src_type = node_map[src]["type"]
        tgt_type = node_map[tgt]["type"]
        if (src_type, tgt_type) not in allowed:
            raise ValueError(
                f"Invalid type pair ({src_type} -> {tgt_type}) for edge label '{label}'"
            )

        if "amount" in edata and edata["amount"] is not None and edata["amount"] <= 0:
            raise ValueError(f"Edge amount must be positive, got {edata['amount']}")

        ev_span = edata.get("evidence_char_span")
        if ev_span:
            es, ee = ev_span
            if es >= ee:
                raise ValueError(f"Edge evidence_char_span start >= end: [{es}, {ee}]")

    # Kingpin semantic check
    kp_id = summary.get("kingpin_node_id")
    kingpin_nodes = [nid for nid, nd in node_map.items() if nd.get("isKingpin") is True]
    if kp_id:
        if kp_id not in node_map:
            raise ValueError(f"kingpin_node_id '{kp_id}' not found in nodes")
        if not node_map[kp_id].get("isKingpin"):
            raise ValueError(f"Node '{kp_id}' indicated by kingpin_node_id does not have isKingpin=True")
        if len(kingpin_nodes) != 1 or kingpin_nodes[0] != kp_id:
            raise ValueError(
                f"Only node '{kp_id}' may have isKingpin=True, found: {kingpin_nodes}"
            )
    else:
        if kingpin_nodes:
            raise ValueError(f"kingpin_node_id is not set, but nodes have isKingpin=True: {kingpin_nodes}")

