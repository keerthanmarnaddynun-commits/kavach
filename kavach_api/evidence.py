"""Evidence and document inspection services for KAVACH case graphs."""
from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any, Sequence

from kavach_api.storage import Storage


def node_evidence(
    store: Storage,
    case_id: str,
    graph: dict[str, Any],
    node_id: str,
) -> dict[str, Any]:
    """
    Retrieve FIR spans, CSV row references, and immediate neighbours for a node.
    """
    target_node = None
    for n in graph.get("nodes", []):
        if n.get("id") == node_id:
            target_node = n
            break

    if target_node is None:
        raise ValueError(f"Node '{node_id}' not found in case graph")

    fir_evidence: list[dict[str, Any]] = []
    # Collect FIR evidence
    for span in target_node.get("evidence_spans", []):
        fir_id = span.get("fir_id")
        if not fir_id:
            continue
        try:
            meta, text = store.get_document(case_id, fir_id)
            sha256_raw = meta.get("sha256_raw", "")
        except Exception:
            text = ""
            sha256_raw = ""

        mentions = span.get("mentions", [])
        if mentions:
            for m in mentions:
                coords = m.get("char_span", [0, 0])
                surface = m.get("surface", "")
                start, end = coords[0], coords[1]
                excerpt = text[max(0, start - 80) : min(len(text), end + 80)]
                fir_evidence.append(
                    {
                        "doc_id": fir_id,
                        "sha256_raw": sha256_raw,
                        "char_span": coords,
                        "surface": surface,
                        "entity_id": span.get("entity_id", ""),
                        "ai_confidence": target_node.get("ai_confidence", 1.0),
                        "excerpt": excerpt,
                    }
                )
        else:
            coords = span.get("char_span", [0, 0])
            start, end = coords[0], coords[1]
            surface = text[start:end] if text else ""
            excerpt = text[max(0, start - 80) : min(len(text), end + 80)] if text else ""
            fir_evidence.append(
                {
                    "doc_id": fir_id,
                    "sha256_raw": sha256_raw,
                    "char_span": coords,
                    "surface": surface,
                    "entity_id": span.get("entity_id", ""),
                    "ai_confidence": target_node.get("ai_confidence", 1.0),
                    "excerpt": excerpt,
                }
            )

    # Collect CSV evidence
    files_info = store.files_info(case_id)
    csv_rows_by_file: dict[str, set[int]] = {}

    for e in graph.get("edges", []):
        if e.get("source_kind") == "CSV" and (e.get("source") == node_id or e.get("target") == node_id):
            fname = e.get("source_file", "")
            if fname:
                csv_rows_by_file.setdefault(fname, set()).update(e.get("row_numbers", []))

    csv_evidence: list[dict[str, Any]] = []
    for fname in sorted(csv_rows_by_file.keys()):
        all_rows = sorted(csv_rows_by_file[fname])
        clean_key = fname[:-4] if fname.endswith(".csv") else fname
        f_info = files_info.get(fname) or files_info.get(clean_key) or {}
        csv_evidence.append(
            {
                "file": fname,
                "sha256": f_info.get("sha256", ""),
                "row_numbers": all_rows[:50],
                "row_count": len(all_rows),
            }
        )

    # Collect neighbours
    node_map = {n["id"]: n for n in graph.get("nodes", [])}
    neighbours: list[dict[str, Any]] = []
    for e in graph.get("edges", []):
        src = e.get("source")
        tgt = e.get("target")
        rel = e.get("relation")
        if src == node_id and tgt in node_map:
            other = node_map[tgt]
            neighbours.append(
                {
                    "id": tgt,
                    "label": other.get("canonical_name") or other.get("value") or tgt,
                    "type": other.get("type", "UNKNOWN"),
                    "relation": rel,
                    "direction": "out",
                }
            )
        elif tgt == node_id and src in node_map:
            other = node_map[src]
            neighbours.append(
                {
                    "id": src,
                    "label": other.get("canonical_name") or other.get("value") or src,
                    "type": other.get("type", "UNKNOWN"),
                    "relation": rel,
                    "direction": "in",
                }
            )

    return {
        "node_id": node_id,
        "fir_evidence": fir_evidence,
        "csv_evidence": csv_evidence,
        "neighbours": neighbours,
    }


def edge_evidence(
    store: Storage,
    case_id: str,
    graph: dict[str, Any],
    source: str,
    target: str,
    relation: str | None = None,
) -> dict[str, Any]:
    """
    Retrieve FIR spans or CSV row numbers with aggregates for an edge.
    """
    matched_edge = None
    for e in graph.get("edges", []):
        if e.get("source") == source and e.get("target") == target:
            if relation is None or e.get("relation") == relation:
                matched_edge = e
                break

    if matched_edge is None:
        raise ValueError(f"Edge from '{source}' to '{target}' (rel={relation}) not found")

    fir_evidence: list[dict[str, Any]] = []
    csv_evidence: dict[str, Any] | None = None
    aggregates: dict[str, Any] = {}

    if matched_edge.get("source_kind") == "FIR":
        for span in matched_edge.get("evidence_spans", []):
            fir_id = span.get("fir_id")
            try:
                meta, text = store.get_document(case_id, fir_id)
                sha256_raw = meta.get("sha256_raw", "")
            except Exception:
                text = ""
                sha256_raw = ""

            coords = span.get("evidence_char_span", [0, 0])
            start, end = coords[0], coords[1]
            surface = text[start:end] if text else ""
            excerpt = text[max(0, start - 80) : min(len(text), end + 80)] if text else ""
            fir_evidence.append(
                {
                    "doc_id": fir_id,
                    "sha256_raw": sha256_raw,
                    "char_span": coords,
                    "surface": surface,
                    "trigger": span.get("trigger", ""),
                    "ai_confidence": span.get("confidence", 1.0),
                    "excerpt": excerpt,
                }
            )
    elif matched_edge.get("source_kind") == "CSV":
        fname = matched_edge.get("source_file", "")
        clean_key = fname[:-4] if fname.endswith(".csv") else fname
        f_info = store.files_info(case_id).get(fname) or store.files_info(case_id).get(clean_key) or {}
        rows_list = matched_edge.get("row_numbers", [])
        csv_evidence = {
            "file": fname,
            "sha256": f_info.get("sha256", ""),
            "row_numbers": rows_list[:50],
            "row_count": len(rows_list),
        }
        aggregates = {
            "first_time": matched_edge.get("first_time"),
            "last_time": matched_edge.get("last_time"),
            "modes": matched_edge.get("modes", []),
            "total_amount": matched_edge.get("total_amount"),
            "total_amount_paise": matched_edge.get("total_amount_paise"),
            "txn_count": matched_edge.get("txn_count"),
        }

    return {
        "edge": matched_edge,
        "fir_evidence": fir_evidence,
        "csv_evidence": csv_evidence,
        "aggregates": aggregates,
    }


def document_view(
    store: Storage,
    case_id: str,
    doc_id: str,
    graph: dict[str, Any],
) -> dict[str, Any]:
    """
    Retrieve document text, hashes, and entity/edge spans for UI highlighting.
    """
    meta, text = store.get_document(case_id, doc_id)
    spans: list[dict[str, Any]] = []

    # Collect entity mention spans
    for n in graph.get("nodes", []):
        for span in n.get("evidence_spans", []):
            if span.get("fir_id") == doc_id:
                for m in span.get("mentions", []):
                    spans.append(
                        {
                            "char_span": m.get("char_span"),
                            "surface": m.get("surface"),
                            "kind": m.get("kind"),
                            "node_id": n.get("id"),
                            "type": n.get("type"),
                        }
                    )

    # Collect relationship spans
    for e in graph.get("edges", []):
        for span in e.get("evidence_spans", []):
            if span.get("fir_id") == doc_id:
                coords = span.get("evidence_char_span")
                if coords:
                    spans.append(
                        {
                            "char_span": coords,
                            "trigger": span.get("trigger"),
                            "relation": e.get("relation"),
                            "source": e.get("source"),
                            "target": e.get("target"),
                        }
                    )

    spans.sort(key=lambda s: (s.get("char_span", [0])[0], s.get("char_span", [0, 0])[1]))

    return {
        "doc_id": doc_id,
        "text": text,
        "sha256_raw": meta.get("sha256_raw"),
        "sha256_stored": meta.get("sha256_stored"),
        "spans": spans,
    }


def rows(
    store: Storage,
    case_id: str,
    kind: str,
    row_numbers: Sequence[int],
) -> list[dict[str, Any]]:
    """
    Retrieve requested raw rows (max 200) from stored CSV matching builder 1-based indexing.
    """
    csv_file = store.csv_path(case_id, kind)
    if not csv_file.is_file():
        raise FileNotFoundError(f"CSV file '{kind}' does not exist for case {case_id}")

    requested = set(row_numbers[:200])
    results: list[dict[str, Any]] = []

    with open(csv_file, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for r_num, row_dict in enumerate(reader, start=1):
            if r_num in requested:
                results.append({"row": r_num, **dict(row_dict)})
                if len(results) >= len(requested):
                    break

    results.sort(key=lambda r: r["row"])
    return results
