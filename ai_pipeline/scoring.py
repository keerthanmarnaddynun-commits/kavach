"""
Scoring library for mentions and relations (Step 5a-1).
"""

from __future__ import annotations

import glob
import json
import os
from pathlib import Path
from typing import Any


class Counts(dict):
    """Container for tp, fp, fn counts supporting dict and attribute access."""

    def __init__(self, tp: int = 0, fp: int = 0, fn: int = 0):
        super().__init__(tp=tp, fp=fp, fn=fn)

    @property
    def tp(self) -> int:
        return self["tp"]

    @tp.setter
    def tp(self, val: int) -> None:
        self["tp"] = val

    @property
    def fp(self) -> int:
        return self["fp"]

    @fp.setter
    def fp(self, val: int) -> None:
        self["fp"] = val

    @property
    def fn(self) -> int:
        return self["fn"]

    @fn.setter
    def fn(self, val: int) -> None:
        self["fn"] = val


def prf(
    counts_or_tp: Counts | dict | tuple | list | int,
    fp: int | None = None,
    fn: int | None = None,
) -> tuple[float | None, float | None, float | None]:
    """
    Compute (precision, recall, f1) from counts.
    Returns None where the denominator is zero.
    """
    if fp is not None and fn is not None:
        tp_val = int(counts_or_tp)
        fp_val = int(fp)
        fn_val = int(fn)
    elif isinstance(counts_or_tp, dict):
        tp_val = counts_or_tp.get("tp", 0)
        fp_val = counts_or_tp.get("fp", 0)
        fn_val = counts_or_tp.get("fn", 0)
    elif hasattr(counts_or_tp, "tp") and hasattr(counts_or_tp, "fp") and hasattr(counts_or_tp, "fn"):
        tp_val = counts_or_tp.tp
        fp_val = counts_or_tp.fp
        fn_val = counts_or_tp.fn
    elif isinstance(counts_or_tp, (tuple, list)) and len(counts_or_tp) == 3:
        tp_val, fp_val, fn_val = counts_or_tp
    else:
        raise ValueError(f"Cannot parse counts from {counts_or_tp}")

    prec = (tp_val / (tp_val + fp_val)) if (tp_val + fp_val) > 0 else None
    rec = (tp_val / (tp_val + fn_val)) if (tp_val + fn_val) > 0 else None

    if prec is not None and rec is not None:
        if (prec + rec) > 0:
            f1 = 2 * prec * rec / (prec + rec)
        else:
            f1 = 0.0
    else:
        f1 = None

    return (prec, rec, f1)


def _map_mention_type(label: str, role: str | None) -> str:
    """
    Map raw label and role to gold mention type:
      - PERSON with role FATHER -> FATHER
      - other PERSON roles (SUSPECT, OFFICER, COMPLAINANT, WITNESS) -> PERSON
      - ALIAS, PHONE, IMEI, ACCOUNT, AMOUNT unchanged
    """
    if label == "PERSON":
        if role == "FATHER":
            return "FATHER"
        return "PERSON"
    return label


def load_gold_mentions(firs_dir: str | Path) -> dict[str, list[dict[str, Any]]]:
    """
    Load gold mentions from answer keys in firs_dir (FIR_*.json).
    Returns {doc_id: [ {type, start, end, text} ]}.
    """
    firs_path = Path(firs_dir)
    json_files = sorted(
        [
            p
            for p in firs_path.glob("FIR_*.json")
            if not p.name.endswith(".contract.json") and not p.name.endswith(".links.json")
        ]
    )

    gold: dict[str, list[dict[str, Any]]] = {}
    for jf in json_files:
        with open(jf, "r", encoding="utf-8") as f:
            data = json.load(f)

        doc_id = data.get("source_doc_id") or jf.stem
        mentions = []
        for ent in data.get("entities", []):
            raw_label = ent.get("label") or ent.get("type")
            role = ent.get("role")
            m_type = _map_mention_type(raw_label, role)

            char_span = ent.get("char_span")
            if char_span:
                start, end = char_span[0], char_span[1]
            else:
                start = ent.get("start", 0)
                end = ent.get("end", 0)

            text = ent.get("text", ent.get("surface", ""))
            mentions.append({
                "type": m_type,
                "start": start,
                "end": end,
                "text": text,
            })
        gold[doc_id] = mentions

    return gold


def load_doc_meta(firs_dir: str | Path) -> dict[str, dict[str, str]]:
    """
    Load {doc_id: {split, language}} from index.json in firs_dir.
    """
    index_path = Path(firs_dir) / "index.json"
    with open(index_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    meta: dict[str, dict[str, str]] = {}
    if isinstance(data, list):
        for item in data:
            doc_id = item.get("doc_id") or item.get("source_doc_id")
            meta[doc_id] = {
                "split": item.get("split"),
                "language": item.get("language"),
            }
    elif isinstance(data, dict):
        for doc_id, item in data.items():
            meta[doc_id] = {
                "split": item.get("split"),
                "language": item.get("language"),
            }
    return meta


def _normalize_mention(m: Any) -> dict[str, Any]:
    """Normalize mention input to dict with type, start, end, text."""
    if isinstance(m, dict):
        return {
            "type": m.get("type"),
            "start": m.get("start"),
            "end": m.get("end"),
            "text": m.get("text", m.get("surface", "")),
        }
    return {
        "type": getattr(m, "type", None),
        "start": getattr(m, "start", 0),
        "end": getattr(m, "end", 0),
        "text": getattr(m, "text", getattr(m, "surface", "")),
    }


def _score_mentions_subset(
    gold_subset: dict[str, list[dict[str, Any]]],
    pred_subset: dict[str, list[dict[str, Any]]],
    all_types: list[str],
) -> dict[str, Any]:
    """Score mentions for a single subset of documents."""
    doc_ids = sorted(set(gold_subset.keys()) | set(pred_subset.keys()))

    strict_by_type = {t: Counts(0, 0, 0) for t in all_types}
    lenient_by_type = {t: Counts(0, 0, 0) for t in all_types}

    for doc_id in doc_ids:
        g_raw = gold_subset.get(doc_id, [])
        p_raw = pred_subset.get(doc_id, [])

        g_list = [_normalize_mention(m) for m in g_raw]
        p_list = [_normalize_mention(m) for m in p_raw]

        for t in all_types:
            g_t = [m for m in g_list if m["type"] == t]
            p_t = [m for m in p_list if m["type"] == t]

            # 1. STRICT: same type and identical (start, end)
            unmatched_g_spans = [(m["start"], m["end"]) for m in g_t]
            for p in p_t:
                span = (p["start"], p["end"])
                if span in unmatched_g_spans:
                    unmatched_g_spans.remove(span)
                    strict_by_type[t].tp += 1
                else:
                    strict_by_type[t].fp += 1
            strict_by_type[t].fn += len(unmatched_g_spans)

            # 2. LENIENT: same type and overlapping, matched greedily by largest overlap
            overlap_pairs = []
            for p_idx, p in enumerate(p_t):
                for g_idx, g in enumerate(g_t):
                    ov = min(p["end"], g["end"]) - max(p["start"], g["start"])
                    if ov > 0:
                        overlap_pairs.append((ov, p_idx, g_idx))

            # Greedy by largest overlap, deterministic tie-breaking
            overlap_pairs.sort(key=lambda x: (-x[0], x[1], x[2]))
            matched_p = set()
            matched_g = set()
            for ov, p_idx, g_idx in overlap_pairs:
                if p_idx not in matched_p and g_idx not in matched_g:
                    matched_p.add(p_idx)
                    matched_g.add(g_idx)

            tp_l = len(matched_p)
            fp_l = len(p_t) - tp_l
            fn_l = len(g_t) - tp_l

            lenient_by_type[t].tp += tp_l
            lenient_by_type[t].fp += fp_l
            lenient_by_type[t].fn += fn_l

    strict_micro = Counts(
        tp=sum(c.tp for c in strict_by_type.values()),
        fp=sum(c.fp for c in strict_by_type.values()),
        fn=sum(c.fn for c in strict_by_type.values()),
    )
    lenient_micro = Counts(
        tp=sum(c.tp for c in lenient_by_type.values()),
        fp=sum(c.fp for c in lenient_by_type.values()),
        fn=sum(c.fn for c in lenient_by_type.values()),
    )

    by_type = {
        t: {
            "strict": strict_by_type[t],
            "lenient": lenient_by_type[t],
        }
        for t in all_types
    }

    result: dict[str, Any] = {
        "by_type": by_type,
        "micro": {
            "strict": strict_micro,
            "lenient": lenient_micro,
        },
    }
    # Direct access convenience by type name
    for t in all_types:
        result[t] = by_type[t]

    return result


def score_mentions(
    gold: dict[str, list[dict[str, Any]]],
    pred: dict[str, list[dict[str, Any]]],
    meta: dict[str, dict[str, str]] | None = None,
    group_by: str | None = None,
) -> dict[str, Any]:
    """
    Score predicted mentions against gold mentions.
    STRICT mode: same type and identical (start, end).
    LENIENT mode: same type and overlapping, matched one-to-one greedily by largest overlap.
    Duplicate predictions count as false positives.

    group_by: None, 'split', or 'language'.
    """
    # Collect all types across all documents in gold and pred
    all_types_set = set()
    for doc_mentions in gold.values():
        for m in doc_mentions:
            t = m.get("type") if isinstance(m, dict) else getattr(m, "type", None)
            if t:
                all_types_set.add(t)
    for doc_mentions in pred.values():
        for m in doc_mentions:
            t = m.get("type") if isinstance(m, dict) else getattr(m, "type", None)
            if t:
                all_types_set.add(t)
    all_types = sorted(all_types_set)

    if group_by is None:
        return _score_mentions_subset(gold, pred, all_types)

    if group_by not in ("split", "language"):
        raise ValueError(f"group_by must be None, 'split', or 'language', got {group_by}")

    if meta is None:
        raise ValueError("meta dictionary must be provided when group_by is specified")

    # Partition documents by group value
    all_doc_ids = sorted(set(gold.keys()) | set(pred.keys()))
    grouped_docs: dict[str, list[str]] = {}
    for doc_id in all_doc_ids:
        doc_meta = meta.get(doc_id, {})
        grp_val = doc_meta.get(group_by, "unknown")
        if grp_val not in grouped_docs:
            grouped_docs[grp_val] = []
        grouped_docs[grp_val].append(doc_id)

    results: dict[str, Any] = {}
    for grp_val, doc_list in sorted(grouped_docs.items()):
        gold_sub = {doc_id: gold.get(doc_id, []) for doc_id in doc_list}
        pred_sub = {doc_id: pred.get(doc_id, []) for doc_id in doc_list}
        results[grp_val] = _score_mentions_subset(gold_sub, pred_sub, all_types)

    return results


def _load_contract_docs(docs: Any) -> dict[str, dict[str, Any]]:
    """Helper to convert contract docs input (path, list, or dict) to {doc_id: doc_dict}."""
    if isinstance(docs, (str, Path)):
        p = Path(docs)
        if p.is_dir():
            files = sorted(p.glob("*.contract.json"))
            res = {}
            for f in files:
                with open(f, "r", encoding="utf-8") as fp:
                    d = json.load(fp)
                doc_id = d.get("source_doc_id") or f.name.replace(".contract.json", "")
                res[doc_id] = d
            return res
        with open(p, "r", encoding="utf-8") as fp:
            d = json.load(fp)
        doc_id = d.get("source_doc_id", "doc_0")
        return {doc_id: d}

    if isinstance(docs, list):
        res = {}
        for i, d in enumerate(docs):
            doc_id = d.get("source_doc_id") or d.get("doc_id") or f"doc_{i}"
            res[doc_id] = d
        return res

    if isinstance(docs, dict):
        # Could be {doc_id: doc_dict} or single contract doc dict
        if "entities" in docs and ("relationships" in docs or "source_doc_id" in docs):
            doc_id = docs.get("source_doc_id", "doc_0")
            return {doc_id: docs}
        return docs

    raise ValueError(f"Unsupported contract documents type: {type(docs)}")


def score_relations(
    gold_docs: Any,
    pred_docs: Any,
) -> dict[str, Any]:
    """
    Score relations and entity alignment on contract v1.1 documents.
    Entity alignment:
      - same type and at least one identical mention span (start, end)
      - pick the gold entity sharing the most spans
      - each gold entity used at most once
    Relation matching:
      - aligned source and target equal gold relation source and target
      - relation label is equal
      - for TRANSFERRED_FUNDS: amount matches within 0.01 when gold has one
      - each gold relation matches at most once
    """
    g_map = _load_contract_docs(gold_docs)
    p_map = _load_contract_docs(pred_docs)

    doc_ids = sorted(set(g_map.keys()) | set(p_map.keys()))

    rel_by_label: dict[str, Counts] = {}
    ent_by_type: dict[str, Counts] = {}

    for doc_id in doc_ids:
        g_doc = g_map.get(doc_id, {})
        p_doc = p_map.get(doc_id, {})

        # 1. Extract gold entity spans and types
        g_spans: dict[str, set[tuple[int, int]]] = {}
        g_types: dict[str, str] = {}
        for ent in g_doc.get("entities", []):
            eid = ent["id"]
            spans = set()
            for m in ent.get("mentions", []):
                cs = m.get("char_span")
                if cs and len(cs) == 2:
                    spans.add((cs[0], cs[1]))
            cs = ent.get("char_span")
            if cs and len(cs) == 2:
                spans.add((cs[0], cs[1]))
            g_spans[eid] = spans
            g_types[eid] = ent.get("type", "")

        # 2. Extract pred entity spans and types
        p_spans: dict[str, set[tuple[int, int]]] = {}
        p_types: dict[str, str] = {}
        for ent in p_doc.get("entities", []):
            eid = ent["id"]
            spans = set()
            for m in ent.get("mentions", []):
                cs = m.get("char_span")
                if cs and len(cs) == 2:
                    spans.add((cs[0], cs[1]))
            cs = ent.get("char_span")
            if cs and len(cs) == 2:
                spans.add((cs[0], cs[1]))
            p_spans[eid] = spans
            p_types[eid] = ent.get("type", "")

        # 3. Align predicted entities to gold entities
        candidate_pairs = []
        for pid, ps in p_spans.items():
            for gid, gs in g_spans.items():
                if p_types[pid] == g_types[gid]:
                    sh = ps & gs
                    if len(sh) >= 1:
                        candidate_pairs.append((len(sh), pid, gid))

        # Sort by shared spans descending, then pid, gid for stable tie-break
        candidate_pairs.sort(key=lambda x: (-x[0], x[1], x[2]))

        aligned_p_to_g: dict[str, str] = {}
        used_g: set[str] = set()
        for sh, pid, gid in candidate_pairs:
            if pid not in aligned_p_to_g and gid not in used_g:
                aligned_p_to_g[pid] = gid
                used_g.add(gid)

        # 4. Entity-level scoring
        for pid in p_spans:
            t = p_types[pid]
            if t not in ent_by_type:
                ent_by_type[t] = Counts(0, 0, 0)
            if pid in aligned_p_to_g:
                ent_by_type[t].tp += 1
            else:
                ent_by_type[t].fp += 1

        for gid in g_spans:
            t = g_types[gid]
            if t not in ent_by_type:
                ent_by_type[t] = Counts(0, 0, 0)
            if gid not in used_g:
                ent_by_type[t].fn += 1

        # 5. Relation scoring
        g_rels = g_doc.get("relationships", [])
        p_rels = p_doc.get("relationships", [])
        unmatched_g_rels = set(range(len(g_rels)))

        for p_rel in p_rels:
            p_src = aligned_p_to_g.get(p_rel.get("source"))
            p_tgt = aligned_p_to_g.get(p_rel.get("target"))
            p_lbl = p_rel.get("relation") or p_rel.get("type")
            p_amt = p_rel.get("amount")

            if p_lbl not in rel_by_label:
                rel_by_label[p_lbl] = Counts(0, 0, 0)

            matched_idx = None
            if p_src is not None and p_tgt is not None:
                for g_idx in sorted(unmatched_g_rels):
                    g_rel = g_rels[g_idx]
                    g_src = g_rel.get("source")
                    g_tgt = g_rel.get("target")
                    g_lbl = g_rel.get("relation") or g_rel.get("type")
                    g_amt = g_rel.get("amount")

                    if g_src == p_src and g_tgt == p_tgt and g_lbl == p_lbl:
                        if p_lbl == "TRANSFERRED_FUNDS" and g_amt is not None:
                            if p_amt is not None and abs(float(p_amt) - float(g_amt)) <= 0.01:
                                matched_idx = g_idx
                                break
                        else:
                            matched_idx = g_idx
                            break

            if matched_idx is not None:
                unmatched_g_rels.remove(matched_idx)
                rel_by_label[p_lbl].tp += 1
            else:
                rel_by_label[p_lbl].fp += 1

        for g_idx in unmatched_g_rels:
            g_lbl = g_rels[g_idx].get("relation") or g_rels[g_idx].get("type")
            if g_lbl not in rel_by_label:
                rel_by_label[g_lbl] = Counts(0, 0, 0)
            rel_by_label[g_lbl].fn += 1

    rel_micro = Counts(
        tp=sum(c.tp for c in rel_by_label.values()),
        fp=sum(c.fp for c in rel_by_label.values()),
        fn=sum(c.fn for c in rel_by_label.values()),
    )
    ent_micro = Counts(
        tp=sum(c.tp for c in ent_by_type.values()),
        fp=sum(c.fp for c in ent_by_type.values()),
        fn=sum(c.fn for c in ent_by_type.values()),
    )

    results = {
        "relations": {
            "by_label": rel_by_label,
            "micro": rel_micro,
        },
        "entities": {
            "by_type": ent_by_type,
            "micro": ent_micro,
        },
    }

    # Add convenience accessors
    for lbl, c in rel_by_label.items():
        results["relations"][lbl] = c
    for t, c in ent_by_type.items():
        results["entities"][t] = c

    results["by_label"] = rel_by_label
    results["micro"] = rel_micro
    results["by_entity_type"] = ent_by_type

    return results

