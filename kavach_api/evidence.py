"""Evidence and document inspection services for KAVACH case graphs."""
from __future__ import annotations

import csv
from pathlib import Path
import re
from typing import Any, Sequence

from kavach_api.render import compute_edge_id
from kavach_api.storage import Storage


class EvidenceError(Exception):
    """Exception for evidence retrieval failures."""

    def __init__(self, message: str, code: str = "evidence_error") -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _extract_confidence(val: Any) -> float:
    """Extract float confidence preserving 0.0 and defaulting to 0.0 if None."""
    if val is None:
        return 0.0
    try:
        f = float(val)
        return max(0.0, min(1.0, f))
    except (ValueError, TypeError):
        return 0.0


def node_evidence(
    store: Storage,
    case_id: str,
    graph: dict[str, Any],
    node_id: str,
) -> dict[str, Any]:
    """
    Retrieve FIR spans, CSV row references, and immediate neighbours for a node.
    Raises EvidenceError(code='node_not_found') if node is missing.
    Raises EvidenceError(code='document_missing') if referenced document is missing.
    """
    target_node = None
    for n in graph.get("nodes", []):
        if n.get("id") == node_id:
            target_node = n
            break

    if target_node is None:
        raise EvidenceError(f"Node '{node_id}' not found in case graph", code="node_not_found")

    node_conf = _extract_confidence(target_node.get("ai_confidence"))

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
            raise EvidenceError(
                f"Document '{fir_id}' missing in case '{case_id}'",
                code="document_missing",
            )

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
                        "ai_confidence": node_conf,
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
                    "ai_confidence": node_conf,
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

    first_fir = compute_first_fir_mention(store, case_id, graph, node_id)
    first_record = compute_first_record(store, case_id, graph, node_id)

    return {
        "node_id": node_id,
        "fir_evidence": fir_evidence,
        "csv_evidence": csv_evidence,
        "neighbours": neighbours,
        "first_fir": first_fir,
        "first_record": first_record,
    }


def compute_first_record(
    store: Storage,
    case_id: str,
    graph: dict[str, Any],
    node_id: str,
) -> dict[str, Any] | None:
    """
    Retrieve the counterpart(s) of a node's FIRST record in CDR/bank data.
    - Phone: other party (b_party/a_party) and IMEI used (imei_a/imei) from cdr.csv.
    - Account: other account (to_acct/from_acct) from bank.csv.
    - IMEI: phone that used it (a_party) from cdr.csv.
    Includes first timestamp and 1-based data-row reference(s) (capped at 5).
    """
    target_node = None
    for n in graph.get("nodes", []):
        if n.get("id") == node_id:
            target_node = n
            break

    node_type = target_node.get("type", "") if target_node else ""
    raw_val = target_node.get("value") or target_node.get("label") or node_id if target_node else node_id
    raw_val = str(raw_val).strip()
    for prefix in ("PHONE:", "ACCOUNT:", "IMEI:", "PERSON:", "VEHICLE:"):
        if raw_val.startswith(prefix):
            raw_val = raw_val[len(prefix):].strip()

    if not node_type:
        if node_id.startswith("PHONE:"):
            node_type = "PHONE"
        elif node_id.startswith("ACCOUNT:"):
            node_type = "ACCOUNT"
        elif node_id.startswith("IMEI:"):
            node_type = "IMEI"

    if node_type == "PHONE":
        cdr_path = store.csv_path(case_id, "cdr")
        if not cdr_path.is_file():
            return None
        earliest_t: str | None = None
        records: list[dict[str, Any]] = []
        with open(cdr_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for r_num, row in enumerate(reader, start=1):
                st = row.get("start_time", "").strip()
                if not st:
                    continue
                a_p = row.get("a_party", "").strip()
                b_p = row.get("b_party", "").strip()
                if a_p != raw_val and b_p != raw_val:
                    continue

                other_party = b_p if a_p == raw_val else a_p
                imei_used = row.get("imei_a", "").strip() or row.get("imei", "").strip()
                cps: list[str] = []
                if other_party:
                    cps.append(other_party)
                if imei_used:
                    cps.append(imei_used)

                rec_entry = {"row": r_num, "timestamp": st, "counterparts": cps}
                if earliest_t is None or st < earliest_t:
                    earliest_t = st
                    records = [rec_entry]
                elif st == earliest_t:
                    if len(records) < 5:
                        records.append(rec_entry)

        if earliest_t is None:
            return None

        unique_cps: list[str] = []
        seen: set[str] = set()
        for r in records:
            for cp in r.get("counterparts", []):
                if cp and cp not in seen:
                    seen.add(cp)
                    unique_cps.append(cp)

        return {
            "file": "cdr",
            "timestamp": earliest_t,
            "rows": [r["row"] for r in records],
            "counterparts": unique_cps,
            "records": records,
        }

    elif node_type == "ACCOUNT":
        bank_path = store.csv_path(case_id, "bank")
        if not bank_path.is_file():
            return None
        earliest_t: str | None = None
        records: list[dict[str, Any]] = []
        with open(bank_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for r_num, row in enumerate(reader, start=1):
                dt = row.get("datetime", "").strip()
                if not dt:
                    continue
                from_a = row.get("from_acct", "").strip()
                to_a = row.get("to_acct", "").strip()
                if from_a != raw_val and to_a != raw_val:
                    continue

                other_acct = to_a if from_a == raw_val else from_a
                cps = [other_acct] if other_acct else []

                rec_entry = {"row": r_num, "timestamp": dt, "counterparts": cps}
                if earliest_t is None or dt < earliest_t:
                    earliest_t = dt
                    records = [rec_entry]
                elif dt == earliest_t:
                    if len(records) < 5:
                        records.append(rec_entry)

        if earliest_t is None:
            return None

        unique_cps: list[str] = []
        seen = set()
        for r in records:
            for cp in r.get("counterparts", []):
                if cp and cp not in seen:
                    seen.add(cp)
                    unique_cps.append(cp)

        return {
            "file": "bank",
            "timestamp": earliest_t,
            "rows": [r["row"] for r in records],
            "counterparts": unique_cps,
            "records": records,
        }

    elif node_type == "IMEI":
        cdr_path = store.csv_path(case_id, "cdr")
        if not cdr_path.is_file():
            return None
        earliest_t: str | None = None
        records: list[dict[str, Any]] = []
        with open(cdr_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for r_num, row in enumerate(reader, start=1):
                st = row.get("start_time", "").strip()
                if not st:
                    continue
                im_a = row.get("imei_a", "").strip()
                im_b = row.get("imei", "").strip()
                if im_a != raw_val and im_b != raw_val:
                    continue

                phone_used = row.get("a_party", "").strip()
                cps = [phone_used] if phone_used else []

                rec_entry = {"row": r_num, "timestamp": st, "counterparts": cps}
                if earliest_t is None or st < earliest_t:
                    earliest_t = st
                    records = [rec_entry]
                elif st == earliest_t:
                    if len(records) < 5:
                        records.append(rec_entry)

        if earliest_t is None:
            return None

        unique_cps: list[str] = []
        seen = set()
        for r in records:
            for cp in r.get("counterparts", []):
                if cp and cp not in seen:
                    seen.add(cp)
                    unique_cps.append(cp)

        return {
            "file": "cdr",
            "timestamp": earliest_t,
            "rows": [r["row"] for r in records],
            "counterparts": unique_cps,
            "records": records,
        }

    return None


def compute_first_fir_mention(
    store: Storage,
    case_id: str,
    graph: dict[str, Any],
    node_id: str,
) -> dict[str, Any] | None:
    """
    Determine a node's earliest FIR mention and partition entities in that FIR
    into: (a) entities related to this node via stated FIR relations, and
          (b) other entities mentioned in the same FIR with no stated relation.
    """
    target_node = None
    for n in graph.get("nodes", []):
        if n.get("id") == node_id:
            target_node = n
            break

    if target_node is None:
        return None

    # Collect all FIR IDs mentioning this node
    fir_ids: set[str] = set()
    for f in target_node.get("source_firs", []):
        if f:
            fir_ids.add(str(f))
    for s in target_node.get("evidence_spans", []):
        fid = s.get("fir_id")
        if fid:
            fir_ids.add(str(fid))

    # Also check FIR edges incident to this node
    for e in graph.get("edges", []):
        if e.get("source_kind") == "FIR" and (e.get("source") == node_id or e.get("target") == node_id):
            for f in e.get("source_firs", []):
                if f:
                    fir_ids.add(str(f))
            for s in e.get("evidence_spans", []):
                fid = s.get("fir_id")
                if fid:
                    fir_ids.add(str(fid))

    if not fir_ids:
        return {
            "first_fir_id": None,
            "date": None,
            "related_entities": [],
            "other_entities": [],
        }

    # Determine earliest FIR: earliest FIR date if available, otherwise lowest FIR number
    def fir_key(fid: str) -> tuple[int, str, int, str]:
        date_str = ""
        try:
            meta, _ = store.get_document(case_id, fid)
            date_str = str(meta.get("date") or meta.get("fir_date") or "").strip()
        except Exception:
            pass
        num_m = re.search(r"\d+", fid)
        num = int(num_m.group()) if num_m else 999999
        if date_str:
            return (0, date_str, num, fid)
        return (1, "", num, fid)

    first_fir_id = min(fir_ids, key=fir_key)
    first_fir_date = None
    try:
        meta, _ = store.get_document(case_id, first_fir_id)
        first_fir_date = meta.get("date") or meta.get("fir_date") or None
    except Exception:
        pass

    node_map = {n["id"]: n for n in graph.get("nodes", [])}

    # Group (a): entities the FIR itself relates to this node
    related_entities: list[dict[str, Any]] = []
    related_node_ids: set[str] = set()

    for e in graph.get("edges", []):
        if e.get("source_kind") != "FIR":
            continue
        edge_firs: set[str] = set(e.get("source_firs", []))
        for s in e.get("evidence_spans", []):
            fid = s.get("fir_id")
            if fid:
                edge_firs.add(str(fid))
        if first_fir_id not in edge_firs:
            continue

        src = e.get("source")
        tgt = e.get("target")
        rel = e.get("relation")

        if src == node_id and tgt in node_map and tgt != node_id:
            other = node_map[tgt]
            related_entities.append({
                "id": tgt,
                "label": other.get("canonical_name") or other.get("value") or tgt,
                "type": other.get("type", "UNKNOWN"),
                "relation": rel,
                "direction": "out",
            })
            related_node_ids.add(tgt)
        elif tgt == node_id and src in node_map and src != node_id:
            other = node_map[src]
            related_entities.append({
                "id": src,
                "label": other.get("canonical_name") or other.get("value") or src,
                "type": other.get("type", "UNKNOWN"),
                "relation": rel,
                "direction": "in",
            })
            related_node_ids.add(src)

    # Deduplicate related_entities by (id, relation, direction)
    dedup_related: list[dict[str, Any]] = []
    seen_rel = set()
    for item in related_entities:
        key = (item["id"], item["relation"], item["direction"])
        if key not in seen_rel:
            seen_rel.add(key)
            dedup_related.append(item)
    dedup_related.sort(key=lambda x: (x["type"], x["label"], x["id"]))

    # Group (b): other entities mentioned in the same FIR with no stated relation to this node
    other_entities: list[dict[str, Any]] = []
    for n in graph.get("nodes", []):
        nid = n["id"]
        if nid == node_id or nid in related_node_ids:
            continue
        n_firs: set[str] = set(n.get("source_firs", []))
        for s in n.get("evidence_spans", []):
            fid = s.get("fir_id")
            if fid:
                n_firs.add(str(fid))
        if first_fir_id in n_firs:
            other_entities.append({
                "id": nid,
                "label": n.get("canonical_name") or n.get("value") or nid,
                "type": n.get("type", "UNKNOWN"),
            })

    other_entities.sort(key=lambda x: (x["type"], x["label"], x["id"]))

    return {
        "first_fir_id": first_fir_id,
        "date": first_fir_date,
        "related_entities": dedup_related,
        "other_entities": other_entities,
    }


def edge_evidence_by_id(
    store: Storage,
    case_id: str,
    graph: dict[str, Any],
    edge_id: str,
) -> dict[str, Any]:
    """
    Retrieve evidence for an edge by its Contract 2 edge ID.
    Merges evidence from ALL internal edges that share the same edge ID.
    Raises EvidenceError(code='edge_not_found') if edge ID is not found.
    Raises EvidenceError(code='document_missing') if referenced document is missing.
    """
    matched_edges = []
    for e in graph.get("edges", []):
        src = str(e.get("source", ""))
        tgt = str(e.get("target", ""))
        rel = str(e.get("relation", ""))
        skind = str(e.get("source_kind", "FIR"))
        eid = compute_edge_id(src, tgt, rel, skind)
        if eid == edge_id:
            matched_edges.append(e)

    if not matched_edges:
        raise EvidenceError(f"Edge '{edge_id}' not found in case graph", code="edge_not_found")

    primary = matched_edges[0]
    source_kind = primary.get("source_kind", "FIR")
    src = primary.get("source")
    tgt = primary.get("target")
    rel = primary.get("relation")

    fir_evidence: list[dict[str, Any]] = []
    csv_evidence: dict[str, Any] | None = None
    aggregates: dict[str, Any] = {}

    if source_kind == "FIR":
        seen_spans: set[tuple[str, int, int]] = set()
        for e in matched_edges:
            for span in e.get("evidence_spans", []):
                fir_id = span.get("fir_id")
                if not fir_id:
                    continue
                try:
                    meta, text = store.get_document(case_id, fir_id)
                    sha256_raw = meta.get("sha256_raw", "")
                except Exception:
                    raise EvidenceError(
                        f"Document '{fir_id}' missing in case '{case_id}'",
                        code="document_missing",
                    )

                coords = span.get("evidence_char_span", [0, 0])
                start, end = coords[0], coords[1]
                span_key = (fir_id, start, end)
                if span_key in seen_spans:
                    continue
                seen_spans.add(span_key)

                surface = text[start:end] if text else ""
                excerpt = text[max(0, start - 80) : min(len(text), end + 80)] if text else ""
                fir_evidence.append(
                    {
                        "doc_id": fir_id,
                        "sha256_raw": sha256_raw,
                        "char_span": coords,
                        "surface": surface,
                        "trigger": span.get("trigger", ""),
                        "ai_confidence": _extract_confidence(span.get("confidence")),
                        "excerpt": excerpt,
                    }
                )

    elif source_kind == "CSV":
        all_row_numbers: set[int] = set()
        for e in matched_edges:
            all_row_numbers.update(e.get("row_numbers", []))

        fname = primary.get("source_file", "")
        clean_key = fname[:-4] if fname.endswith(".csv") else fname
        f_info = store.files_info(case_id).get(fname) or store.files_info(case_id).get(clean_key) or {}
        sorted_rows = sorted(all_row_numbers)

        csv_evidence = {
            "file": fname,
            "sha256": f_info.get("sha256", ""),
            "row_numbers": sorted_rows[:50],
            "row_count": len(sorted_rows),
        }
        aggregates = {
            "first_time": primary.get("first_time"),
            "last_time": primary.get("last_time"),
            "modes": primary.get("modes", []),
            "total_amount": primary.get("total_amount"),
            "total_amount_paise": primary.get("total_amount_paise"),
            "txn_count": primary.get("txn_count"),
        }

    return {
        "edge_id": edge_id,
        "source": src,
        "target": tgt,
        "relation": rel,
        "source_kind": source_kind,
        "fir_evidence": fir_evidence,
        "csv_evidence": csv_evidence,
        "aggregates": aggregates,
    }


def edge_evidence(
    store: Storage,
    case_id: str,
    graph: dict[str, Any],
    source: str,
    target: str | None = None,
    relation: str | None = None,
    edge_id: str | None = None,
) -> dict[str, Any]:
    """
    Retrieve FIR spans or CSV row numbers with aggregates for an edge.
    Supports either (source, target, relation) or edge_id lookup.
    """
    if edge_id is not None:
        return edge_evidence_by_id(store, case_id, graph, edge_id)

    if target is None and source.startswith("E-"):
        return edge_evidence_by_id(store, case_id, graph, source)

    matched_edge = None
    for e in graph.get("edges", []):
        if e.get("source") == source and e.get("target") == target:
            if relation is None or e.get("relation") == relation:
                matched_edge = e
                break

    if matched_edge is None:
        raise EvidenceError(f"Edge from '{source}' to '{target}' (rel={relation}) not found", code="edge_not_found")

    eid = compute_edge_id(
        str(matched_edge.get("source", "")),
        str(matched_edge.get("target", "")),
        str(matched_edge.get("relation", "")),
        str(matched_edge.get("source_kind", "FIR")),
    )
    return edge_evidence_by_id(store, case_id, graph, eid)


def document_view(
    store: Storage,
    case_id: str,
    doc_id: str,
    graph: dict[str, Any],
) -> dict[str, Any]:
    """
    Retrieve document text, hashes, and entity/edge spans for UI highlighting.
    Returns doc_id, filename, text, sha256_raw, sha256_text, spans.
    Guards span sort against None char_span values.
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

    def _span_key(s: dict[str, Any]) -> tuple[int, int]:
        c = s.get("char_span")
        if isinstance(c, (list, tuple)) and len(c) >= 2 and c[0] is not None and c[1] is not None:
            return (int(c[0]), int(c[1]))
        return (999999999, 999999999)

    spans.sort(key=_span_key)

    return {
        "doc_id": doc_id,
        "filename": meta.get("filename", f"{doc_id}.txt"),
        "text": text,
        "sha256_raw": meta.get("sha256_raw", ""),
        "sha256_text": meta.get("sha256_text", ""),
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
