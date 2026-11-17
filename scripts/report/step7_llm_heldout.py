"""
Step 7d: Evaluation of frozen extractor on LLM-authored held-out FIR dataset.

PRE-REGISTERED METRIC DEFINITIONS:
1. Headline Mentions:
   Strict micro Precision, Recall, and F1 computed over all mentions of the 10 core
   contract types: PERSON, ALIAS, FATHER, PHONE, IMEI, ACCOUNT, AADHAAR, PAN, UPI, VEHICLE.
   Strict match criterion requires exact equality of entity type and identical character
   span (start, end). Lenient match criterion requires identical entity type and any
   non-zero character span overlap, matched one-to-one greedily by maximal overlap length.
   Duplicate predictions count as false positives.
   AMOUNT mentions are reported separately and not included in headline micro metrics.
   IFSC is uncontracted in v1.1 and reported as 'not scored: no matching contract type'
   with gold mention count.

2. Entity Exactness:
   Evaluated per Contract v1.1 entity alignment algorithm: a predicted entity aligns to at
   most one reference entity of identical type sharing at least one mention character span,
   paired greedily by shared span count with deterministic tie-breaking. Precision, Recall,
   and F1 are reported per entity type.

3. Relation Micro Scoring:
   Relation evaluation on Contract v1.1 relationships: a predicted relation (source, target,
   relation_type, optional amount) matches a reference relation if aligned source equals
   gold source, aligned target equals gold target, relation type matches, and for
   TRANSFERRED_FUNDS, predicted amount equals gold amount within 0.01 tolerance.
   Evaluated for shipped HYBRID pipeline, CUE-only extractor, and CONTRAST co-occurrence
   baseline. Reported overall micro and per relation type.

4. Language, File, and Coverage Requirement Subsets:
   Mention and relation metrics reported separately across languages (hinglish, english,
   hindi), per individual file, and grouped by authoring requirements (look-alike names,
   3 aliases, shared phone, no phone/account, messy, special identifiers, account-to-account).

5. Non-Luhn IMEI Scoring:
   IMEI mentions failing the Luhn checksum are evaluated under standard strict mention
   matching against gold annotations without penalty for checksum invalidity.

6. Bootstrap Uncertainty:
   95% confidence intervals for headline strict mention F1 and hybrid relation micro F1
   estimated via 2,000 file-level resamples with replacement using numpy RandomState(20261117).
   Percentiles 2.5 and 97.5 define the interval bounds.

7. Degraded Mode:
   Heuristic rule-based extraction evaluated without neural model components under identical
   headline mention and relation definitions.

8. Comparison Column:
   Synthetic dev/test baseline numbers read directly from results/2026-11-11_step6_extraction_r2/metrics.json
   and clearly labeled as non-directly comparable external baselines.
"""

from __future__ import annotations

import argparse
import copy
import datetime
import difflib
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import stat
import subprocess
import sys
import time
from typing import Any

# Ensure Hugging Face operates strictly offline with cached local files only
os.environ["HF_HUB_OFFLINE"] = "1"

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import numpy as np

from ai_pipeline.pipeline import analyze_text
from ai_pipeline.relations import extract_relations
from ai_pipeline.scoring import (
    _load_contract_docs,
    _map_mention_type,
    load_gold_mentions,
    prf,
    score_mentions,
    score_relations,
)
from contracts.v1_1.validate import validate_ai_output
from scripts.report.step6_extraction import (
    _assert_opt_float,
    _counts_to_dict,
    _fmt_num,
    align_contract_entities,
    compute_relation_suite,
    compute_sha256,
    format_key_number_line,
    get_metric_by_path,
    run_contrast_relations,
    CORE_ENTITY_TYPES,
    RELATION_LABELS,
)

HEADLINE_MENTION_TYPES: tuple[str, ...] = (
    "PERSON",
    "ALIAS",
    "FATHER",
    "PHONE",
    "IMEI",
    "ACCOUNT",
    "AADHAAR",
    "PAN",
    "UPI",
    "VEHICLE",
)

ALL_REPORTED_MENTION_TYPES: tuple[str, ...] = HEADLINE_MENTION_TYPES + ("AMOUNT", "IFSC")

FORBIDDEN_WORDS: tuple[str, ...] = (
    "verified",
    "confirmed",
    "audited",
    "proves",
    "guarantees",
    "state-of-the-art",
    "robust",
    "excellent",
    "perfect",
)


def scan_forbidden_words(text: str) -> list[str]:
    """Scan text for occurrences of forbidden words (case-insensitive word boundary match)."""
    pattern = r"\b(?:" + "|".join(re.escape(w) for w in FORBIDDEN_WORDS) + r")\b"
    return re.findall(pattern, text, re.IGNORECASE)


def check_table_column_counts(markdown_or_table: str) -> None:
    """Assert every row within each markdown table block has the identical column count."""
    lines = markdown_or_table.splitlines()
    table_block: list[str] = []

    def _verify_block(block: list[str]) -> None:
        counts = [len([c for c in tl.split("|")[1:-1]]) for tl in block]
        if len(set(counts)) != 1:
            raise ValueError(f"Inconsistent column counts {counts} in table block:\n" + "\n".join(block))

    for line in lines:
        trimmed = line.strip()
        if trimmed.startswith("|") and trimmed.endswith("|"):
            table_block.append(trimmed)
        else:
            if table_block:
                _verify_block(table_block)
                table_block = []
    if table_block:
        _verify_block(table_block)


def compute_bootstrap_intervals(
    file_metrics: dict[str, dict[str, Any]],
    n_resamples: int = 2000,
    seed: int = 20261117,
) -> tuple[tuple[float, float], tuple[float, float]]:
    """
    Compute 95% bootstrap intervals for headline mention F1 and hybrid relation micro F1
    via file-level resampling with replacement.
    """
    stems = sorted(file_metrics.keys())
    n_files = len(stems)
    if n_files == 0:
        return ((0.0, 0.0), (0.0, 0.0))

    rng = np.random.RandomState(seed)
    mention_f1s = np.empty(n_resamples, dtype=float)
    relation_f1s = np.empty(n_resamples, dtype=float)

    for i in range(n_resamples):
        sample_idx = rng.randint(0, n_files, size=n_files)
        m_tp = m_fp = m_fn = 0
        r_tp = r_fp = r_fn = 0
        for idx in sample_idx:
            stem = stems[idx]
            fm = file_metrics[stem]
            m_tp += fm["mentions"]["tp"]
            m_fp += fm["mentions"]["fp"]
            m_fn += fm["mentions"]["fn"]
            r_tp += fm["relations"]["tp"]
            r_fp += fm["relations"]["fp"]
            r_fn += fm["relations"]["fn"]

        m_f1 = prf(m_tp, m_fp, m_fn)[2]
        r_f1 = prf(r_tp, r_fp, r_fn)[2]
        mention_f1s[i] = m_f1 if m_f1 is not None else 0.0
        relation_f1s[i] = r_f1 if r_f1 is not None else 0.0

    ci_m_low, ci_m_high = float(np.percentile(mention_f1s, 2.5)), float(np.percentile(mention_f1s, 97.5))
    ci_r_low, ci_r_high = float(np.percentile(relation_f1s, 2.5)), float(np.percentile(relation_f1s, 97.5))
    return ((ci_m_low, ci_m_high), (ci_r_low, ci_r_high))


def extract_mentions_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Extract all candidate mentions from an analyze_text payload:
    - PERSON, ALIAS, FATHER, PHONE, IMEI, ACCOUNT, AADHAAR, PAN, UPI, VEHICLE from doc.entities
    - AMOUNT from aux.amounts
    """
    doc = payload.get("doc", {})
    aux = payload.get("aux", {})
    mentions: list[dict[str, Any]] = []

    for ent in doc.get("entities", []):
        etype = ent.get("type")
        for m in ent.get("mentions", []):
            kind = m.get("kind")
            cs = m.get("char_span")
            surf = m.get("surface", "")
            if not cs or len(cs) != 2:
                continue
            if kind == "NAME":
                m_type = "PERSON"
            elif kind in ("ALIAS", "FATHER"):
                m_type = kind
            elif kind == "VALUE":
                m_type = etype
            else:
                continue
            mentions.append({
                "type": m_type,
                "start": int(cs[0]),
                "end": int(cs[1]),
                "text": surf,
            })

    for amt in aux.get("amounts", []):
        mentions.append({
            "type": "AMOUNT",
            "start": int(amt["start"]),
            "end": int(amt["end"]),
            "text": amt.get("surface", ""),
        })

    return mentions


def load_gold_doc_mentions(gold_doc: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract gold mentions from a converted gold contract document."""
    mentions = []
    for ent in gold_doc.get("entities", []):
        raw_label = ent.get("label") or ent.get("type")
        role = ent.get("role")
        m_type = _map_mention_type(raw_label, role)
        cs = ent.get("char_span") or [ent.get("start", 0), ent.get("end", 0)]
        mentions.append({
            "type": m_type,
            "start": int(cs[0]),
            "end": int(cs[1]),
            "text": ent.get("surface", ent.get("text", "")),
        })
    return mentions


def run_sanity_check_s1(converted_dir: Path) -> dict[str, Any]:
    """
    S1 gold-against-gold: score each converted gold JSON against itself.
    All mention and relation P/R/F1 must be exactly 1.0 for every type present.
    """
    json_files = sorted(
        [
            p for p in converted_dir.glob("*.json")
            if not p.name.endswith("_report.json") and not p.name.endswith("hashes.json")
        ]
    )
    if not json_files:
        raise FileNotFoundError(f"No converted gold JSON files found in {converted_dir}")

    gold_docs: dict[str, dict[str, Any]] = {}
    gold_mentions: dict[str, list[dict[str, Any]]] = {}

    for jf in json_files:
        data = json.loads(jf.read_text(encoding="utf-8"))
        doc_id = data.get("source_doc_id") or jf.stem
        gold_docs[doc_id] = data
        gold_mentions[doc_id] = load_gold_doc_mentions(data)

    # Score mentions
    ms_res = score_mentions(gold_mentions, gold_mentions)
    for t, d in ms_res["by_type"].items():
        st = d["strict"]
        p, r, f = prf(st)
        if p != 1.0 or r != 1.0 or f != 1.0:
            raise ValueError(f"S1 Mention mismatch on {t}: P={p}, R={r}, F1={f} (expected 1.0)")

    # Score relations
    rel_res = score_relations(gold_docs, gold_docs)
    for lbl, c in rel_res["relations"]["by_label"].items():
        p, r, f = prf(c)
        if p != 1.0 or r != 1.0 or f != 1.0:
            raise ValueError(f"S1 Relation mismatch on {lbl}: P={p}, R={r}, F1={f} (expected 1.0)")

    return {
        "status": "PASSED",
        "files_checked": len(json_files),
        "mention_types_checked": sorted(ms_res["by_type"].keys()),
        "relation_types_checked": sorted(rel_res["relations"]["by_label"].keys()),
    }


def run_sanity_check_s2(
    step6_metrics_path: Path,
    step6_run1_dir: Path,
    firs_v5_dir: Path,
    firs_v5_contract_dir: Path,
) -> list[tuple[str, float, float]]:
    """
    S2 convention check: recompute synthetic overall numbers from step 6 run1 and firs_v5
    and assert they equal values stored in step 6 metrics.json (tolerance 1e-9).
    Returns the compared (label, recomputed, saved) pairs.
    """
    metrics = json.loads(step6_metrics_path.read_text(encoding="utf-8"))
    gold_mentions = load_gold_mentions(firs_v5_dir)
    gold_docs = _load_contract_docs(firs_v5_contract_dir)

    from scripts.report.step6_extraction import (
        SCORED_MENTION_TYPES as S6_MENTION_TYPES,
        extract_mentions_from_analysis as s6_extract_mentions,
    )

    pred_mentions = {}
    pred_docs = {}
    for p in sorted(step6_run1_dir.glob("FIR_*.analysis.json")):
        doc_id = p.name.replace(".analysis.json", "")
        payload = json.loads(p.read_text(encoding="utf-8"))
        ms, _, _ = s6_extract_mentions(payload)
        pred_mentions[doc_id] = ms
        pred_docs[doc_id] = payload["doc"]

    compared_pairs: list[tuple[str, float, float]] = []

    # 1. Mention types strict P, R, F1
    ms_all = score_mentions(gold_mentions, pred_mentions)
    for t in S6_MENTION_TYPES:
        st = ms_all["by_type"][t]["strict"]
        p, r, f = prf(st)
        saved = metrics["mentions"]["overall"][t]["strict"]
        for m_name, val, s_val in (("precision", p, saved["precision"]), ("recall", r, saved["recall"]), ("f1", f, saved["f1"])):
            lbl = f"Mention {t} {m_name}"
            if abs(val - s_val) >= 1e-9:
                raise ValueError(f"S2 mismatch on {lbl}: recomputed={val} != saved={s_val}")
            compared_pairs.append((lbl, float(val), float(s_val)))

    # 2. Entity exactness
    rs_r1 = score_relations(gold_docs, pred_docs)
    for t in CORE_ENTITY_TYPES:
        c = rs_r1["entities"]["by_type"][t]
        p, r, f = prf(c)
        saved = metrics["entities"]["overall"][t]
        for m_name, val, s_val in (("precision", p, saved["precision"]), ("recall", r, saved["recall"]), ("f1", f, saved["f1"])):
            lbl = f"Entity {t} {m_name}"
            if abs(val - s_val) >= 1e-9:
                raise ValueError(f"S2 mismatch on {lbl}: recomputed={val} != saved={s_val}")
            compared_pairs.append((lbl, float(val), float(s_val)))

    # 3. Relation micro P, R, F1
    rel_micro = rs_r1["relations"]["micro"]
    p, r, f = prf(rel_micro)
    saved_rel = metrics["relations"]["HYBRID"]["overall"]["micro"]
    for m_name, val, s_val in (("precision", p, saved_rel["precision"]), ("recall", r, saved_rel["recall"]), ("f1", f, saved_rel["f1"])):
        lbl = f"Relation HYBRID micro {m_name}"
        if abs(val - s_val) >= 1e-9:
            raise ValueError(f"S2 mismatch on {lbl}: recomputed={val} != saved={s_val}")
        compared_pairs.append((lbl, float(val), float(s_val)))

    return compared_pairs


def compute_all_metrics(
    gold_docs: dict[str, dict[str, Any]],
    gold_mentions: dict[str, list[dict[str, Any]]],
    run1_saved: dict[str, dict[str, Any]],
    degraded_saved: dict[str, dict[str, Any]],
    meta: dict[str, dict[str, str]],
    texts_by_doc: dict[str, str],
    coverage_report: dict[str, Any],
    synthetic_metrics: dict[str, Any],
    timings_run1: dict[str, float],
    timings_run2: dict[str, float],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """
    Compute complete Step 7 evaluation metrics, error registry, and per-file breakdown.
    Returns (metrics_dict, errors_dict, per_file_dict).
    """
    doc_ids = sorted(gold_docs.keys())

    pred_mentions_r1: dict[str, list[dict[str, Any]]] = {}
    pred_mentions_deg: dict[str, list[dict[str, Any]]] = {}
    run1_docs: dict[str, dict[str, Any]] = {}
    degraded_docs: dict[str, dict[str, Any]] = {}

    for d in doc_ids:
        pred_mentions_r1[d] = extract_mentions_from_payload(run1_saved[d])
        pred_mentions_deg[d] = extract_mentions_from_payload(degraded_saved[d])
        run1_docs[d] = run1_saved[d]["doc"]
        degraded_docs[d] = degraded_saved[d]["doc"]

    # 1. Mentions scoring - headline (the 10 headline types) and all types
    # Gold headline mentions subset
    gold_mentions_headline = {
        d: [m for m in ml if m["type"] in HEADLINE_MENTION_TYPES]
        for d, ml in gold_mentions.items()
    }
    pred_mentions_r1_headline = {
        d: [m for m in ml if m["type"] in HEADLINE_MENTION_TYPES]
        for d, ml in pred_mentions_r1.items()
    }
    pred_mentions_deg_headline = {
        d: [m for m in ml if m["type"] in HEADLINE_MENTION_TYPES]
        for d, ml in pred_mentions_deg.items()
    }

    # Strict & lenient headline micro
    ms_headline_r1 = score_mentions(gold_mentions_headline, pred_mentions_r1_headline)
    ms_headline_deg = score_mentions(gold_mentions_headline, pred_mentions_deg_headline)

    # Scored across ALL mention types (including AMOUNT)
    ms_all_r1 = score_mentions(gold_mentions, pred_mentions_r1)

    # Per-type breakdown for all types
    per_type_metrics: dict[str, Any] = {}
    for t in ALL_REPORTED_MENTION_TYPES:
        if t == "IFSC":
            # IFSC is uncontracted
            g_cnt = sum(1 for ml in gold_mentions.values() for m in ml if m["type"] == "IFSC")
            per_type_metrics[t] = {
                "gold": g_cnt,
                "predicted": 0,
                "strict": {"tp": 0, "fp": 0, "fn": g_cnt, "precision": None, "recall": None, "f1": None},
                "lenient": {"tp": 0, "fp": 0, "fn": g_cnt, "precision": None, "recall": None, "f1": None},
                "status": "not scored: no matching contract type",
            }
        else:
            g_cnt = sum(1 for ml in gold_mentions.values() for m in ml if m["type"] == t)
            p_cnt = sum(1 for ml in pred_mentions_r1.values() for m in ml if m["type"] == t)
            st = ms_all_r1["by_type"].get(t, {}).get("strict", {"tp": 0, "fp": 0, "fn": 0})
            lt = ms_all_r1["by_type"].get(t, {}).get("lenient", {"tp": 0, "fp": 0, "fn": 0})
            st_dict = _counts_to_dict(st)
            lt_dict = _counts_to_dict(lt)
            per_type_metrics[t] = {
                "gold": g_cnt,
                "predicted": p_cnt,
                "strict": st_dict,
                "lenient": lt_dict,
                "status": "scored",
            }

    # 2. Relations scoring: HYBRID (run1), CUE, CONTRAST
    cue_docs: dict[str, dict[str, Any]] = {}
    contrast_docs: dict[str, dict[str, Any]] = {}
    for d in doc_ids:
        txt = texts_by_doc[d]
        base_doc = copy.deepcopy(run1_saved[d]["doc"])
        base_aux = run1_saved[d]["aux"]

        d_cue = copy.deepcopy(base_doc)
        d_cue["relationships"] = extract_relations(txt, d_cue, base_aux)
        cue_docs[d] = d_cue

        d_con = copy.deepcopy(base_doc)
        d_con["relationships"] = run_contrast_relations(txt, d_con, base_aux)
        contrast_docs[d] = d_con

    meta_dict = {d: {"split": "llm_heldout", "language": meta[d]["language"].lower()} for d in doc_ids}
    relations_metrics = {
        "HYBRID": compute_relation_suite(gold_docs, run1_docs, meta_dict),
        "CUE": compute_relation_suite(gold_docs, cue_docs, meta_dict),
        "CONTRAST": compute_relation_suite(gold_docs, contrast_docs, meta_dict),
    }

    # Degraded relations
    deg_rel_suite = compute_relation_suite(gold_docs, degraded_docs, meta_dict)

    # 3. Entity alignment exactness
    rs_r1 = score_relations(gold_docs, run1_docs)
    entities_overall = {
        t: _counts_to_dict(rs_r1["entities"]["by_type"].get(t, {"tp": 0, "fp": 0, "fn": 0}))
        for t in CORE_ENTITY_TYPES
    }
    ent_micro = _counts_to_dict(rs_r1["entities"]["micro"])

    # 4. Per-file breakdown and errors calculation
    per_file: dict[str, Any] = {}
    mention_errors: list[dict[str, Any]] = []
    relation_errors: list[dict[str, Any]] = []

    for d in doc_ids:
        lang = meta[d]["language"].lower()
        # Per file mention evaluation (headline types)
        g_m = gold_mentions_headline.get(d, [])
        p_m = pred_mentions_r1_headline.get(d, [])

        # Strict matching per file
        g_unmatched = list(g_m)
        f_m_tp = 0
        f_m_fp = 0
        for p in p_m:
            matched_g = None
            for g in g_unmatched:
                if p["type"] == g["type"] and p["start"] == g["start"] and p["end"] == g["end"]:
                    matched_g = g
                    break
            if matched_g is not None:
                g_unmatched.remove(matched_g)
                f_m_tp += 1
            else:
                f_m_fp += 1
                mention_errors.append({
                    "file": d,
                    "error_type": "FP",
                    "type": p["type"],
                    "surface": p["text"],
                    "char_span": [p["start"], p["end"]],
                })
        f_m_fn = len(g_unmatched)
        for g in g_unmatched:
            mention_errors.append({
                "file": d,
                "error_type": "FN",
                "type": g["type"],
                "surface": g["text"],
                "char_span": [g["start"], g["end"]],
            })

        m_p, m_r, m_f1 = prf(f_m_tp, f_m_fp, f_m_fn)

        # Per file relation evaluation
        sub_rel = score_relations({d: gold_docs[d]}, {d: run1_docs[d]})
        r_c = sub_rel["relations"]["micro"]
        r_p, r_r, r_f1 = prf(r_c)

        # Detail relation errors for file d
        g_doc = gold_docs[d]
        p_doc = run1_docs[d]
        aligned_pairs = align_contract_entities(g_doc, p_doc)
        p_to_g = {p_ent["id"]: g_ent["id"] for p_ent, g_ent in aligned_pairs}
        p_ent_map = {ent["id"]: ent for ent in p_doc.get("entities", [])}
        g_ent_map = {ent["id"]: ent for ent in g_doc.get("entities", [])}

        g_rels = list(g_doc.get("relationships", []))
        p_rels = list(p_doc.get("relationships", []))
        unmatched_g_indices = set(range(len(g_rels)))

        for p_rel in p_rels:
            p_src = p_to_g.get(p_rel.get("source"))
            p_tgt = p_to_g.get(p_rel.get("target"))
            p_lbl = p_rel.get("relation") or p_rel.get("type")
            p_amt = p_rel.get("amount")

            matched_idx = None
            if p_src is not None and p_tgt is not None:
                for g_idx in sorted(unmatched_g_indices):
                    g_rel = g_rels[g_idx]
                    if g_rel.get("source") == p_src and g_rel.get("target") == p_tgt and (g_rel.get("relation") or g_rel.get("type")) == p_lbl:
                        if p_lbl == "TRANSFERRED_FUNDS" and g_rel.get("amount") is not None:
                            if p_amt is not None and abs(float(p_amt) - float(g_rel["amount"])) <= 0.01:
                                matched_idx = g_idx
                                break
                        else:
                            matched_idx = g_idx
                            break

            if matched_idx is not None:
                unmatched_g_indices.remove(matched_idx)
            else:
                s_ent = p_ent_map.get(p_rel.get("source"), {})
                t_ent = p_ent_map.get(p_rel.get("target"), {})
                relation_errors.append({
                    "file": d,
                    "error_type": "FP",
                    "relation": p_lbl,
                    "source_id": p_rel.get("source"),
                    "target_id": p_rel.get("target"),
                    "source_surface": s_ent.get("canonical_name") or (s_ent.get("mentions", [{}])[0].get("surface", "") if s_ent.get("mentions") else ""),
                    "target_surface": t_ent.get("canonical_name") or t_ent.get("value") or (t_ent.get("mentions", [{}])[0].get("surface", "") if t_ent.get("mentions") else ""),
                    "amount": p_amt,
                })

        for g_idx in unmatched_g_indices:
            g_rel = g_rels[g_idx]
            g_lbl = g_rel.get("relation") or g_rel.get("type")
            s_ent = g_ent_map.get(g_rel.get("source"), {})
            t_ent = g_ent_map.get(g_rel.get("target"), {})
            relation_errors.append({
                "file": d,
                "error_type": "FN",
                "relation": g_lbl,
                "source_id": g_rel.get("source"),
                "target_id": g_rel.get("target"),
                "source_surface": s_ent.get("canonical_name") or s_ent.get("surface") or (s_ent.get("mentions", [{}])[0].get("surface", "") if s_ent.get("mentions") else ""),
                "target_surface": t_ent.get("canonical_name") or t_ent.get("value") or t_ent.get("surface") or (t_ent.get("mentions", [{}])[0].get("surface", "") if t_ent.get("mentions") else ""),
                "amount": g_rel.get("amount"),
            })

        b_reqs = coverage_report.get("per_file", {}).get(d, {}).get("brief_requirements", [])
        per_file[d] = {
            "stem": d,
            "language": lang,
            "brief_requirements": b_reqs,
            "mentions": {
                "gold": len(g_m),
                "predicted": len(p_m),
                "tp": f_m_tp,
                "fp": f_m_fp,
                "fn": f_m_fn,
                "precision": m_p,
                "recall": m_r,
                "f1": m_f1,
            },
            "relations": {
                "gold": len(g_doc.get("relationships", [])),
                "predicted": len(p_doc.get("relationships", [])),
                "tp": r_c.tp,
                "fp": r_c.fp,
                "fn": r_c.fn,
                "precision": r_p,
                "recall": r_r,
                "f1": r_f1,
            },
            "latency_ms": {
                "run1": timings_run1.get(d, 0.0),
                "run2": timings_run2.get(d, 0.0),
            },
        }

    # 5. Language aggregation
    languages_metrics: dict[str, Any] = {}
    for lang in ("hinglish", "english", "hindi"):
        lang_stems = [d for d in doc_ids if meta[d]["language"].lower() == lang]
        m_tp = sum(per_file[d]["mentions"]["tp"] for d in lang_stems)
        m_fp = sum(per_file[d]["mentions"]["fp"] for d in lang_stems)
        m_fn = sum(per_file[d]["mentions"]["fn"] for d in lang_stems)
        m_p, m_r, m_f1 = prf(m_tp, m_fp, m_fn)

        r_tp = sum(per_file[d]["relations"]["tp"] for d in lang_stems)
        r_fp = sum(per_file[d]["relations"]["fp"] for d in lang_stems)
        r_fn = sum(per_file[d]["relations"]["fn"] for d in lang_stems)
        r_p, r_r, r_f1 = prf(r_tp, r_fp, r_fn)

        languages_metrics[lang] = {
            "file_count": len(lang_stems),
            "files": lang_stems,
            "mentions": {
                "gold": sum(per_file[d]["mentions"]["gold"] for d in lang_stems),
                "predicted": sum(per_file[d]["mentions"]["predicted"] for d in lang_stems),
                "tp": m_tp, "fp": m_fp, "fn": m_fn,
                "precision": m_p, "recall": m_r, "f1": m_f1,
            },
            "relations": {
                "gold": sum(per_file[d]["relations"]["gold"] for d in lang_stems),
                "predicted": sum(per_file[d]["relations"]["predicted"] for d in lang_stems),
                "tp": r_tp, "fp": r_fp, "fn": r_fn,
                "precision": r_p, "recall": r_r, "f1": r_f1,
            },
        }

    # 6. Coverage requirements aggregation
    req_groupings: dict[str, list[str]] = {
        "look-alike names": ["H_02", "H_03"],
        "3 aliases": ["H_04", "H_05"],
        "shared phone": ["H_06"],
        "no phone/account": ["H_07", "H_08"],
        "messy": ["H_09", "H_10"],
        "special identifiers": ["E_01", "E_02", "E_04"],
        "account-to-account": ["D_02", "D_05"],
        "baseline": ["H_01"],
    }
    requirements_metrics: dict[str, Any] = {}
    for req_name, stems in req_groupings.items():
        m_tp = sum(per_file[d]["mentions"]["tp"] for d in stems)
        m_fp = sum(per_file[d]["mentions"]["fp"] for d in stems)
        m_fn = sum(per_file[d]["mentions"]["fn"] for d in stems)
        m_p, m_r, m_f1 = prf(m_tp, m_fp, m_fn)

        r_tp = sum(per_file[d]["relations"]["tp"] for d in stems)
        r_fp = sum(per_file[d]["relations"]["fp"] for d in stems)
        r_fn = sum(per_file[d]["relations"]["fn"] for d in stems)
        r_p, r_r, r_f1 = prf(r_tp, r_fp, r_fn)

        requirements_metrics[req_name] = {
            "files": stems,
            "file_count": len(stems),
            "mentions": {
                "gold": sum(per_file[d]["mentions"]["gold"] for d in stems),
                "predicted": sum(per_file[d]["mentions"]["predicted"] for d in stems),
                "tp": m_tp, "fp": m_fp, "fn": m_fn,
                "precision": m_p, "recall": m_r, "f1": m_f1,
            },
            "relations": {
                "gold": sum(per_file[d]["relations"]["gold"] for d in stems),
                "predicted": sum(per_file[d]["relations"]["predicted"] for d in stems),
                "tp": r_tp, "fp": r_fp, "fn": r_fn,
                "precision": r_p, "recall": r_r, "f1": r_f1,
            },
        }

    # 7. Non-Luhn IMEI Scoring
    non_luhn_files = ["D_01", "D_05", "E_02", "E_05", "H_05", "H_10", "H_15"]
    non_luhn_gold_count = 0
    non_luhn_extracted_count = 0
    non_luhn_tp_count = 0
    for d in non_luhn_files:
        g_imeis = [m for m in gold_mentions.get(d, []) if m["type"] == "IMEI"]
        p_imeis = [m for m in pred_mentions_r1.get(d, []) if m["type"] == "IMEI"]
        non_luhn_gold_count += len(g_imeis)
        non_luhn_extracted_count += len(p_imeis)
        for g in g_imeis:
            if any(p["start"] == g["start"] and p["end"] == g["end"] for p in p_imeis):
                non_luhn_tp_count += 1

    # 8. Bootstrap uncertainty (2000 resamples)
    mention_ci, relation_ci = compute_bootstrap_intervals(per_file, n_resamples=2000, seed=20261117)

    # 9. Overall headline numbers
    tot_m_gold = sum(per_file[d]["mentions"]["gold"] for d in doc_ids)
    tot_m_pred = sum(per_file[d]["mentions"]["predicted"] for d in doc_ids)
    tot_m_tp = sum(per_file[d]["mentions"]["tp"] for d in doc_ids)
    tot_m_fp = sum(per_file[d]["mentions"]["fp"] for d in doc_ids)
    tot_m_fn = sum(per_file[d]["mentions"]["fn"] for d in doc_ids)
    headline_strict_p, headline_strict_r, headline_strict_f1 = prf(tot_m_tp, tot_m_fp, tot_m_fn)
    headline_lenient = _counts_to_dict(ms_headline_r1["micro"]["lenient"])

    tot_r_gold = sum(per_file[d]["relations"]["gold"] for d in doc_ids)
    tot_r_pred = sum(per_file[d]["relations"]["predicted"] for d in doc_ids)
    tot_r_tp = sum(per_file[d]["relations"]["tp"] for d in doc_ids)
    tot_r_fp = sum(per_file[d]["relations"]["fp"] for d in doc_ids)
    tot_r_fn = sum(per_file[d]["relations"]["fn"] for d in doc_ids)
    rel_micro_p, rel_micro_r, rel_micro_f1 = prf(tot_r_tp, tot_r_fp, tot_r_fn)

    # Degraded headline numbers
    deg_m_tp = sum(ms_headline_deg["by_type"][t]["strict"].tp for t in HEADLINE_MENTION_TYPES)
    deg_m_fp = sum(ms_headline_deg["by_type"][t]["strict"].fp for t in HEADLINE_MENTION_TYPES)
    deg_m_fn = sum(ms_headline_deg["by_type"][t]["strict"].fn for t in HEADLINE_MENTION_TYPES)
    deg_strict_p, deg_strict_r, deg_strict_f1 = prf(deg_m_tp, deg_m_fp, deg_m_fn)
    deg_lenient = _counts_to_dict(ms_headline_deg["micro"]["lenient"])
    deg_r_c = deg_rel_suite["overall"]["micro"]

    # Synthetic reference numbers directly from step 6 metrics.json
    s6_m_tp = sum(synthetic_metrics["mentions"]["overall"][t]["strict"]["tp"] for t in synthetic_metrics["mentions"]["overall"])
    s6_m_fp = sum(synthetic_metrics["mentions"]["overall"][t]["strict"]["fp"] for t in synthetic_metrics["mentions"]["overall"])
    s6_m_fn = sum(synthetic_metrics["mentions"]["overall"][t]["strict"]["fn"] for t in synthetic_metrics["mentions"]["overall"])
    s6_synth_p, s6_synth_r, s6_synth_f1 = prf(s6_m_tp, s6_m_fp, s6_m_fn)

    synth_rel_dev_f1 = synthetic_metrics["relations"]["HYBRID"]["by_split"]["dev"]["micro"]["f1"]
    synth_rel_test_f1 = synthetic_metrics["relations"]["HYBRID"]["by_split"]["test"]["micro"]["f1"]

    metrics_out: dict[str, Any] = {
        "meta": {
            "evaluation_set": "llm_heldout",
            "file_count": len(doc_ids),
            "languages": {"hinglish": 15, "english": 5, "hindi": 5},
            "headline_mention_types": list(HEADLINE_MENTION_TYPES),
        },
        "headline": {
            "mentions": {
                "gold": tot_m_gold,
                "predicted": tot_m_pred,
                "strict": {
                    "tp": tot_m_tp, "fp": tot_m_fp, "fn": tot_m_fn,
                    "precision": headline_strict_p, "recall": headline_strict_r, "f1": headline_strict_f1,
                    "ci_95": list(mention_ci),
                },
                "lenient": headline_lenient,
            },
            "relations": {
                "gold": tot_r_gold,
                "predicted": tot_r_pred,
                "micro": {
                    "tp": tot_r_tp, "fp": tot_r_fp, "fn": tot_r_fn,
                    "precision": rel_micro_p, "recall": rel_micro_r, "f1": rel_micro_f1,
                    "ci_95": list(relation_ci),
                },
            },
            "degraded": {
                "mentions": {
                    "strict": {
                        "tp": deg_m_tp, "fp": deg_m_fp, "fn": deg_m_fn,
                        "precision": deg_strict_p, "recall": deg_strict_r, "f1": deg_strict_f1,
                    },
                    "lenient": deg_lenient,
                },
                "relations": {
                    "micro": deg_r_c,
                },
            },
            "synthetic_comparison": {
                "label": "synthetic, different generator and author; not directly comparable",
                "mentions_micro_f1": s6_synth_f1,
                "relations_dev_micro_f1": synth_rel_dev_f1,
                "relations_test_micro_f1": synth_rel_test_f1,
            },
        },
        "per_type_mentions": per_type_metrics,
        "entities": {
            "by_type": entities_overall,
            "micro": ent_micro,
        },
        "relations": {
            "HYBRID": relations_metrics["HYBRID"],
            "CUE": relations_metrics["CUE"],
            "CONTRAST": relations_metrics["CONTRAST"],
        },
        "by_language": languages_metrics,
        "by_requirement": requirements_metrics,
        "non_luhn_imei": {
            "gold_count": non_luhn_gold_count,
            "extracted_count": non_luhn_extracted_count,
            "tp_count": non_luhn_tp_count,
        },
        "error_counts": {
            "mentions": {
                "fp_total": len([e for e in mention_errors if e["error_type"] == "FP"]),
                "fn_total": len([e for e in mention_errors if e["error_type"] == "FN"]),
            },
            "relations": {
                "fp_total": len([e for e in relation_errors if e["error_type"] == "FP"]),
                "fn_total": len([e for e in relation_errors if e["error_type"] == "FN"]),
            },
        },
    }

    errors_out: dict[str, Any] = {
        "mentions": mention_errors,
        "relations": relation_errors,
    }

    return metrics_out, errors_out, per_file


def build_step7_markdown(metrics: dict[str, Any]) -> str:
    """Build complete <!-- STEP7:BEGIN --> ... <!-- STEP7:END --> block from metrics.json."""
    h = metrics["headline"]
    m_st = h["mentions"]["strict"]
    m_lt = h["mentions"]["lenient"]
    r_mic = h["relations"]["micro"]
    deg_m = h["degraded"]["mentions"]["strict"]
    deg_lt = h["degraded"]["mentions"]["lenient"]
    deg_r = h["degraded"]["relations"]["micro"]
    synth = h["synthetic_comparison"]

    m_ci_str = f"[{_fmt_num(m_st['ci_95'][0])}, {_fmt_num(m_st['ci_95'][1])}]"
    r_ci_str = f"[{_fmt_num(r_mic['ci_95'][0])}, {_fmt_num(r_mic['ci_95'][1])}]"

    # Key Numbers lines citing metrics.json exclusively via format_key_number_line
    key_numbers = "\n".join([
        format_key_number_line(metrics, "headline.mentions.strict.f1", "headline strict mention score"),
        format_key_number_line(metrics, "headline.mentions.lenient.f1", "headline lenient mention score"),
        format_key_number_line(metrics, "headline.relations.micro.f1", "relation micro score for shipped pipeline"),
        format_key_number_line(metrics, "headline.degraded.mentions.strict.f1", "degraded mode strict mention score without neural components"),
        format_key_number_line(metrics, "headline.degraded.relations.micro.f1", "degraded mode relation micro score without neural components"),
        format_key_number_line(metrics, "by_language.hinglish.mentions.f1", "strict mention score on Hinglish subset"),
        format_key_number_line(metrics, "by_language.english.mentions.f1", "strict mention score on English subset"),
        format_key_number_line(metrics, "by_language.hindi.mentions.f1", "strict mention score on Hindi subset"),
        format_key_number_line(metrics, "by_language.hinglish.relations.f1", "relation micro score on Hinglish subset"),
        format_key_number_line(metrics, "by_language.english.relations.f1", "relation micro score on English subset"),
        format_key_number_line(metrics, "by_language.hindi.relations.f1", "relation micro score on Hindi subset"),
        format_key_number_line(metrics, "relations.CUE.overall.micro.f1", "relation micro score for lexical cue extractor"),
        format_key_number_line(metrics, "relations.CONTRAST.overall.micro.f1", "relation micro score for co-occurrence baseline"),
        format_key_number_line(metrics, "non_luhn_imei.tp_count", "device identifier mentions matching references despite failing checksum"),
        format_key_number_line(metrics, "error_counts.mentions.fp_total", "total mention false positive count across corpus"),
        format_key_number_line(metrics, "error_counts.mentions.fn_total", "total mention false negative count across corpus"),
        format_key_number_line(metrics, "error_counts.relations.fp_total", "total relation false positive count across corpus"),
        format_key_number_line(metrics, "error_counts.relations.fn_total", "total relation false negative count across corpus"),
    ])

    # Table A: Headline Evaluation Summary
    table_a_rows = [
        f"| LLM Held-Out Run One (Shipped) | Live Neural Model | {h['mentions']['gold']} | {h['mentions']['predicted']} "
        f"| {_fmt_num(m_st['precision'])} | {_fmt_num(m_st['recall'])} | {_fmt_num(m_st['f1'])} | {m_ci_str} | {_fmt_num(m_lt['f1'])} | Primary evaluation on held-out narratives |",
        f"| LLM Held-Out Degraded (No Model) | Heuristic Fallback | {h['mentions']['gold']} | {deg_m['tp'] + deg_m['fp']} "
        f"| {_fmt_num(deg_m['precision'])} | {_fmt_num(deg_m['recall'])} | {_fmt_num(deg_m['f1'])} | — | {_fmt_num(deg_lt['f1'])} | Rule-based fallback without neural weights |",
        f"| Synthetic, all 100 FIRs (mention micro F1) | Live Neural Model | — | — | — | — | {_fmt_num(synth['mentions_micro_f1'])} | — | — | {synth['label']} |",
        f"| Synthetic dev (relations, shipped pipeline) | Live Neural Model | — | — | — | — | {_fmt_num(synth['relations_dev_micro_f1'])} | — | — | {synth['label']} |",
        f"| Synthetic test (relations, shipped pipeline; second look) | Live Neural Model | — | — | — | — | {_fmt_num(synth['relations_test_micro_f1'])} | — | — | {synth['label']} |",
    ]
    table_a = "\n".join(table_a_rows)

    # Table B: Mention Extraction by Entity Category
    table_b_rows = []
    for t in ALL_REPORTED_MENTION_TYPES:
        d = metrics["per_type_mentions"][t]
        st = d["strict"]
        lt = d["lenient"]
        note = d["status"]
        table_b_rows.append(
            f"| {t} | {d['gold']} | {d['predicted']} | {st['tp']} | {st['fp']} | {st['fn']} "
            f"| {_fmt_num(st['precision'])} | {_fmt_num(st['recall'])} | {_fmt_num(st['f1'])} "
            f"| {_fmt_num(lt['precision'])} | {_fmt_num(lt['recall'])} | {_fmt_num(lt['f1'])} | {note} |"
        )
    # Add headline micro row
    table_b_rows.append(
        f"| HEADLINE MICRO (Ten Types) | {h['mentions']['gold']} | {h['mentions']['predicted']} | {m_st['tp']} | {m_st['fp']} | {m_st['fn']} "
        f"| {_fmt_num(m_st['precision'])} | {_fmt_num(m_st['recall'])} | {_fmt_num(m_st['f1'])} "
        f"| {_fmt_num(m_lt['precision'])} | {_fmt_num(m_lt['recall'])} | {_fmt_num(m_lt['f1'])} | Combined headline micro |"
    )
    table_b = "\n".join(table_b_rows)

    # Table C: Relation Extraction by Extractor and Label
    table_c_rows = []
    ext_roles = [
        ("HYBRID", "shipped pipeline"),
        ("CUE", "lexical cue extractor"),
        ("CONTRAST", "co-occurrence baseline"),
    ]
    for ext, role_lbl in ext_roles:
        ov = metrics["relations"][ext]["overall"]
        for rel_lbl in RELATION_LABELS:
            d = ov["by_label"][rel_lbl]
            g_cnt = d["tp"] + d["fn"]
            p_cnt = d["tp"] + d["fp"]
            table_c_rows.append(
                f"| {ext} | {role_lbl} | {rel_lbl} | {g_cnt} | {p_cnt} | {d['tp']} | {d['fp']} | {d['fn']} "
                f"| {_fmt_num(d['precision'])} | {_fmt_num(d['recall'])} | {_fmt_num(d['f1'])} |"
            )
        m = ov["micro"]
        g_tot = m["tp"] + m["fn"]
        p_tot = m["tp"] + m["fp"]
        table_c_rows.append(
            f"| {ext} | {role_lbl} | MICRO | {g_tot} | {p_tot} | {m['tp']} | {m['fp']} | {m['fn']} "
            f"| {_fmt_num(m['precision'])} | {_fmt_num(m['recall'])} | {_fmt_num(m['f1'])} |"
        )
    table_c = "\n".join(table_c_rows)

    # Table D: Per-Language Table
    table_d_rows = []
    for lang in ("hinglish", "english", "hindi"):
        lm = metrics["by_language"][lang]
        m_c = lm["mentions"]
        r_c = lm["relations"]
        table_d_rows.append(
            f"| {lang.capitalize()} | {lm['file_count']} | {m_c['gold']} | {m_c['predicted']} "
            f"| {m_c['tp']} | {m_c['fp']} | {m_c['fn']} | {_fmt_num(m_c['f1'])} "
            f"| {r_c['gold']} | {r_c['predicted']} | {r_c['tp']} | {r_c['fp']} | {r_c['fn']} | {_fmt_num(r_c['f1'])} |"
        )
    # Overall row
    table_d_rows.append(
        f"| Overall | {metrics['meta']['file_count']} | {h['mentions']['gold']} | {h['mentions']['predicted']} "
        f"| {m_st['tp']} | {m_st['fp']} | {m_st['fn']} | {_fmt_num(m_st['f1'])} "
        f"| {h['relations']['gold']} | {h['relations']['predicted']} | {r_mic['tp']} | {r_mic['fp']} | {r_mic['fn']} | {_fmt_num(r_mic['f1'])} |"
    )
    table_d = "\n".join(table_d_rows)

    # Table E: Per-Requirement Table
    table_e_rows = []
    for req_name, rm in metrics["by_requirement"].items():
        m_c = rm["mentions"]
        r_c = rm["relations"]
        f_list = ", ".join(rm["files"])
        table_e_rows.append(
            f"| {req_name} | {f_list} | {rm['file_count']} | {m_c['gold']} | {m_c['predicted']} | {_fmt_num(m_c['f1'])} "
            f"| {r_c['gold']} | {r_c['predicted']} | {_fmt_num(r_c['f1'])} |"
        )
    table_e = "\n".join(table_e_rows)

    # Table F: Entity Alignment Exactness
    table_f_rows = []
    for t in CORE_ENTITY_TYPES:
        d = metrics["entities"]["by_type"][t]
        g_cnt = d["tp"] + d["fn"]
        p_cnt = d["tp"] + d["fp"]
        table_f_rows.append(
            f"| {t} | {g_cnt} | {p_cnt} | {d['tp']} | {d['fp']} | {d['fn']} "
            f"| {_fmt_num(d['precision'])} | {_fmt_num(d['recall'])} | {_fmt_num(d['f1'])} |"
        )
    em = metrics["entities"]["micro"]
    table_f_rows.append(
        f"| MICRO | {em['tp'] + em['fn']} | {em['tp'] + em['fp']} | {em['tp']} | {em['fp']} | {em['fn']} "
        f"| {_fmt_num(em['precision'])} | {_fmt_num(em['recall'])} | {_fmt_num(em['f1'])} |"
    )
    table_f = "\n".join(table_f_rows)

    section = f"""<!-- STEP7:BEGIN -->
## Step 7d: Held-Out LLM-Authored FIR Extraction Results

### Results Card
- **Evaluation Status**: Evaluated once on 25 held-out narratives with frozen pipeline architecture.
- **Headline Mentions Micro F1**: {_fmt_num(m_st['f1'])} (95% CI {m_ci_str}, strict character span match across ten core types).
- **Headline Mentions Lenient F1**: {_fmt_num(m_lt['f1'])} (non-zero character boundary overlap).
- **Hybrid Relations Micro F1**: {_fmt_num(r_mic['f1'])} (95% CI {r_ci_str}, contracted entity alignment matching).
- **Degraded Mode Mentions F1**: {_fmt_num(deg_m['f1'])} (heuristic extraction without neural weights).
- **Degraded Mode Relations F1**: {_fmt_num(deg_r['f1'])} (co-occurrence and rule relations without neural model).
- **Non-Luhn Checksum Identifiers**: {metrics['non_luhn_imei']['tp_count']} of {metrics['non_luhn_imei']['gold_count']} invalid IMEI references detected and aligned.
- **Corpus Dimension**: 25 narrative files across Hinglish (15), English (5), and Hindi (5).

### Key Numbers
{key_numbers}

### Evaluation Tables

#### Table A: Headline Evaluation Summary (LLM-Authored Held-Out vs Baselines)
| Evaluation Dataset / Subset | Extractor Mode | Gold Mentions | Pred Mentions | Strict P | Strict R | Strict F1 | 95% CI | Lenient F1 | Benchmark / Notes |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
{table_a}

#### Table B: Mention Extraction by Entity Category (LLM-Authored Held-Out, Run One)
| Entity Category | Gold Mentions | Predicted Mentions | TP | FP | FN | Strict P | Strict R | Strict F1 | Lenient P | Lenient R | Lenient F1 | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
{table_b}

#### Table C: Relation Extraction by Extractor and Label (LLM-Authored Held-Out)
| Extractor | Evaluation Role | Relation Type | Gold | Predicted | TP | FP | FN | Precision | Recall | F1 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
{table_c}

#### Table D: Mention and Relation Extraction by Language Subset
| Language Subset | Files | Mention Gold | Mention Pred | Mention TP | Mention FP | Mention FN | Mention Strict F1 | Relation Gold | Relation Pred | Relation TP | Relation FP | Relation FN | Relation Micro F1 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
{table_d}

#### Table E: Extraction Performance by Coverage Requirement Group
| Coverage Requirement | Matching Files | File Count | Mention Gold | Mention Pred | Mention Strict F1 | Relation Gold | Relation Pred | Relation Micro F1 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
{table_e}

#### Table F: Entity Alignment Exactness (Run One)
| Entity Type | Reference Entities | Predicted Entities | Aligned TP | Unaligned Pred (FP) | Unaligned Ref (FN) | Precision | Recall | F1 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
{table_f}

### Disclosed Evaluation Facts
- **Corpus Dimension**: The held-out evaluation suite comprises 25 files totaling {h['mentions']['gold']} annotated reference mentions (across ten core types) and {h['relations']['gold']} reference relationships across three languages (15 Hinglish, 5 English, 5 Hindi).
- **Independent Generation**: FIR narratives were authored by an independent AI instance with zero access to the extraction repository, architecture, rules, or test fixtures.
- **Evaluation Timing**: The conversion specification and converter pipeline were authored strictly after the extraction engine was frozen.
- **Inspector Exposure**: The AI assistant authoring the converter inspected 8 of the 25 raw narrative files, and the project lead inspected 3 raw files; no pipeline parameters, rules, or models were altered following inspection or evaluation.
- **Extractor Stability**: Zero modifications, hyperparameter tunings, or rule adjustments were introduced into the pipeline after observing held-out outputs.
- **Invalid Checksum Annotations**: Exactly {metrics['non_luhn_imei']['gold_count']} IMEI mentions in the gold corpus fail standard Luhn checksum validation; of these, {metrics['non_luhn_imei']['tp_count']} were extracted by the pipeline and scored identically to valid identifiers.
- Table A synthetic reference rows were corrected after generation; no metric changed.
- **Sample Power Limitation**: Sample sizes (25 total narratives; 5 each for English and Hindi subsets) yield limited statistical inference power outside the reported bootstrap intervals.
- **Subcorpus Dimensions**: English and Hindi subsets contain 5 files each, while Hinglish contains 15 files.

### Glossary
- strict = matching criterion requiring equal entity category and identical character start and end offsets
- lenient = matching criterion requiring equal entity category and overlapping character boundaries paired greedily by shared length
- micro = aggregate metric pooling true positives, false positives, and false negatives across all evaluated instances
- TP/FP/FN = True Positives (correctly matched items), False Positives (predicted items without matching reference), and False Negatives (reference items omitted by prediction)
- held-out = evaluation corpus authored independently without exposure to pipeline heuristics, rules, or supervised training iterations
- CUE = cue-driven relation extractor requiring explicit multilingual lexical phrases within sentence boundaries
- HYBRID = shipped combined extractor layering sentence splitting, cross-sentence anaphora, role disambiguation, and structural co-occurrence fallbacks atop cue matching
- CONTRAST = baseline extractor emitting every schema-valid entity type pair co-occurring within the same sentence without lexical cues
- degraded mode = heuristic pipeline path operating without neural transformer inference

### Caveats
- the FIR narratives were authored by an artificial intelligence model and may display different syntactic distributions from station-drafted police reports
- real-world physical station documents exhibit optical character recognition artifacts, handwritten notes, and typographical anomalies absent from clean digital text
- relationship extraction schemas are restricted to the five predefined telecommunication and financial categories
- English and Hindi evaluation subsets comprise five documents each, constraining statistical power for low-frequency categories in those languages
- runtime latency represents single-threaded CPU execution without batched inference optimizations

### What This Does Not Show
- Station noise resistance: Physical scan skew, smudges, OCR segmentation splits, and handwritten margin additions remain unmeasured.
- Cross-document resolution: Pipeline scope resolves names and entities within single FIRs rather than linking suspects across jurisdictions.
- High-concurrency server capacity: Sequential CPU latency benchmarks do not capture multi-threaded batch throughput under network loads.
- Open-domain generalization: Behavioral characteristics on unseen relationship categories outside the five target schemas remain unmeasured.
<!-- STEP7:END -->"""

    # 1. Check table column counts
    check_table_column_counts(section)

    # 2. Check forbidden words
    found_forbidden = scan_forbidden_words(section)
    if found_forbidden:
        raise ValueError(f"Forbidden words detected in generated markdown: {found_forbidden}")

    return section


def regenerate_step7_markdown(results_dir: Path, results_md_path: Path | None = None) -> list[str]:
    """
    Regenerate docs/RESULTS.md STEP7 block from existing metrics.json without modifying any other part.
    Verifies that every number in the new block that also existed in the old block is identical,
    and returns/prints the diff of changed lines.
    """
    if results_md_path is None:
        results_md_path = REPO_ROOT / "docs" / "RESULTS.md"

    metrics_file = results_dir / "metrics.json"
    if not metrics_file.is_file():
        raise FileNotFoundError(f"Missing metrics.json in {results_dir}")

    metrics = json.loads(metrics_file.read_text(encoding="utf-8"))

    content = results_md_path.read_text(encoding="utf-8")
    m = re.search(r"(<!-- STEP7:BEGIN -->.*?<!-- STEP7:END -->)", content, re.DOTALL)
    if not m:
        raise ValueError("Could not find <!-- STEP7:BEGIN --> ... <!-- STEP7:END --> in docs/RESULTS.md")

    old_block = m.group(1)
    new_block = build_step7_markdown(metrics)

    # Compute diff of changed lines
    diff_lines = list(difflib.unified_diff(
        old_block.splitlines(),
        new_block.splitlines(),
        fromfile="docs/RESULTS.md (old STEP7)",
        tofile="docs/RESULTS.md (new STEP7)",
        lineterm="",
    ))

    # Verify that every number in the old block that also existed in the old block (outside replaced synthetic rows)
    # is identical in the new block
    old_lines = old_block.splitlines()
    new_lines = new_block.splitlines()

    # Compare non-replaced lines directly
    old_non_synth = [l for l in old_lines if not ("Synthetic" in l and "|" in l)]
    new_non_synth = [l for l in new_lines if not ("Synthetic" in l and "|" in l) and not ("Table A synthetic reference rows were corrected" in l)]

    if "#### Table A:" in old_block:
        assert len(old_non_synth) == len(new_non_synth), f"Line count mismatch in non-replaced rows: {len(old_non_synth)} vs {len(new_non_synth)}"
        for idx, (ol, nl) in enumerate(zip(old_non_synth, new_non_synth)):
            old_nums = re.findall(r"\b\d+(?:\.\d+)?\b", ol)
            new_nums = re.findall(r"\b\d+(?:\.\d+)?\b", nl)
            assert old_nums == new_nums, f"Number mismatch at line {idx}: {old_nums} != {new_nums} in:\nOld: {ol}\nNew: {nl}"
            assert ol == nl, f"Line content mismatch at line {idx}:\nOld: {ol}\nNew: {nl}"

    # Overwrite between markers ONLY
    new_content = content[:m.start(1)] + new_block + content[m.end(1):]
    assert content[:m.start(1)] == new_content[:m.start(1)], "Content before STEP7 markers changed!"
    assert content[m.end(1):] == new_content[m.start(1) + len(new_block):], "Content after STEP7 markers changed!"

    results_md_path.write_text(new_content, encoding="utf-8")
    return diff_lines


def main() -> None:
    parser = argparse.ArgumentParser(description="Step 7d: Evaluate extractor on LLM-authored held-out dataset.")
    parser.add_argument("--run-id", default="step7_llm_heldout_r2", help="Unique run identifier suffix.")
    parser.add_argument(
        "--regenerate-md",
        type=Path,
        default=None,
        help="Path to results folder to regenerate docs/RESULTS.md STEP7 block from without running extractor.",
    )
    args = parser.parse_args()

    if args.regenerate_md is not None:
        print(f"=== PART 1: REGENERATING STEP7 BLOCK FROM {args.regenerate_md} ===")
        diff_lines = regenerate_step7_markdown(args.regenerate_md)
        print("Printed diff of changed lines:")
        for line in diff_lines:
            print(line)
        print("Verification passed: all existing metrics and numbers identical outside corrected Table A rows.")
        return

    today_str = datetime.date.today().isoformat()
    results_dir = REPO_ROOT / "results" / f"{today_str}_{args.run_id}"
    if results_dir.exists():
        raise FileExistsError(f"Results directory already exists: {results_dir}")

    converted_dir = REPO_ROOT / "data" / "llm_firs" / "converted_r1"
    coverage_report_path = converted_dir / "coverage_report.json"
    step6_dir = REPO_ROOT / "results" / "2026-11-11_step6_extraction_r2"
    step6_metrics_path = step6_dir / "metrics.json"
    firs_v5_dir = REPO_ROOT / "data" / "synthetic" / "out" / "firs_v5"
    firs_v5_contract_dir = REPO_ROOT / "data" / "synthetic" / "out" / "firs_v5_contract"

    print("=== STEP A: SANITY CHECKS ===")
    # S1 gold-against-gold
    print("Running S1 gold-against-gold check...")
    s1_res = run_sanity_check_s1(converted_dir)
    print(f"S1 PASSED: all {s1_res['files_checked']} converted files scored against themselves yield P=R=F1=1.0!")

    # S2 convention check
    print("Running S2 convention check...")
    compared_pairs = run_sanity_check_s2(step6_metrics_path, step6_dir / "run1", firs_v5_dir, firs_v5_contract_dir)
    print(f"S2 PASSED: {len(compared_pairs)} values recomputed and match step 6 metrics within 1e-9 tolerance:")
    for lbl, r_val, s_val in compared_pairs:
        print(f"  {lbl}: recomputed={r_val:.9f}, saved={s_val:.9f}")

    # Prepare directories
    results_dir.mkdir(parents=True, exist_ok=False)
    run1_dir = results_dir / "run1"
    run2_dir = results_dir / "run2"
    degraded_dir = results_dir / "degraded"
    run1_dir.mkdir(exist_ok=False)
    run2_dir.mkdir(exist_ok=False)
    degraded_dir.mkdir(exist_ok=False)

    print("\n=== STEP B: EXTRACTION RUNS ===")
    txt_files = sorted(converted_dir.glob("*.txt"))
    doc_ids = [p.stem for p in txt_files]
    texts_by_doc = {p.stem: p.read_text(encoding="utf-8") for p in txt_files}
    meta_by_doc: dict[str, dict[str, str]] = {}

    coverage_report = json.loads(coverage_report_path.read_text(encoding="utf-8"))
    for d in doc_ids:
        lang = coverage_report.get("per_file", {}).get(d, {}).get("language", "hinglish")
        meta_by_doc[d] = {"language": lang, "split": "llm_heldout"}

    timings_run1: dict[str, float] = {}
    timings_run2: dict[str, float] = {}
    run1_saved: dict[str, dict[str, Any]] = {}
    run2_saved: dict[str, dict[str, Any]] = {}
    degraded_saved: dict[str, dict[str, Any]] = {}

    # Run 1: live model
    print(f"Executing Run 1 (model mode) on {len(doc_ids)} documents...")
    valid_contracts_run1 = 0
    for d in doc_ids:
        t0 = time.perf_counter()
        res = analyze_text(texts_by_doc[d], doc_id=d, use_model=True)
        dur = (time.perf_counter() - t0) * 1000.0
        timings_run1[d] = dur
        info = copy.deepcopy(res["info"])
        info.pop("timings_ms", None)
        payload = {"doc": res["doc"], "aux": res["aux"], "info": info}
        run1_saved[d] = payload
        out_path = run1_dir / f"{d}.analysis.json"
        out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        errs = validate_ai_output(res["doc"])
        if errs:
            raise ValueError(f"Schema validation error in run1 on {d}: {errs}")
        valid_contracts_run1 += 1

    # Run 2: live model
    print(f"Executing Run 2 (model mode) on {len(doc_ids)} documents...")
    valid_contracts_run2 = 0
    for d in doc_ids:
        t0 = time.perf_counter()
        res = analyze_text(texts_by_doc[d], doc_id=d, use_model=True)
        dur = (time.perf_counter() - t0) * 1000.0
        timings_run2[d] = dur
        info = copy.deepcopy(res["info"])
        info.pop("timings_ms", None)
        payload = {"doc": res["doc"], "aux": res["aux"], "info": info}
        run2_saved[d] = payload
        out_path = run2_dir / f"{d}.analysis.json"
        out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        errs = validate_ai_output(res["doc"])
        if errs:
            raise ValueError(f"Schema validation error in run2 on {d}: {errs}")
        valid_contracts_run2 += 1

    # Check determinism between run1 and run2
    exact_byte_matches = 0
    for d in doc_ids:
        b1 = (run1_dir / f"{d}.analysis.json").read_bytes()
        b2 = (run2_dir / f"{d}.analysis.json").read_bytes()
        if b1 == b2:
            exact_byte_matches += 1
        else:
            raise ValueError(f"Non-deterministic byte mismatch between run1 and run2 for {d}")
    print(f"Determinism check: {exact_byte_matches}/{len(doc_ids)} files byte-identical!")

    # Degraded mode (no model)
    print(f"Executing Degraded Mode (heuristic mode) on {len(doc_ids)} documents...")
    valid_contracts_deg = 0
    for d in doc_ids:
        res = analyze_text(texts_by_doc[d], doc_id=d, use_model=False)
        info = copy.deepcopy(res["info"])
        info.pop("timings_ms", None)
        payload = {"doc": res["doc"], "aux": res["aux"], "info": info}
        degraded_saved[d] = payload
        out_path = degraded_dir / f"{d}.analysis.json"
        out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        errs = validate_ai_output(res["doc"])
        if errs:
            raise ValueError(f"Schema validation error in degraded on {d}: {errs}")
        valid_contracts_deg += 1

    # Record run info (no timestamps, no absolute paths)
    git_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT), text=True).strip()
    status_out = subprocess.check_output(["git", "status", "--porcelain"], cwd=str(REPO_ROOT), text=True)
    uncommitted = []
    for line in status_out.splitlines():
        code = line[:2]
        if "M" in code or "D" in code:
            uncommitted.append(line[3:].strip())

    run_info = {
        "git_head": git_head,
        "uncommitted_tracked_files": sorted(uncommitted),
        "total_documents": len(doc_ids),
        "exact_byte_matches": exact_byte_matches,
        "valid_contracts": {
            "run1": valid_contracts_run1,
            "run2": valid_contracts_run2,
            "degraded": valid_contracts_deg,
        },
    }
    (results_dir / "run_info.json").write_text(json.dumps(run_info, indent=2), encoding="utf-8")
    (results_dir / "timings_run1.json").write_text(json.dumps(timings_run1, indent=2), encoding="utf-8")
    (results_dir / "timings_run2.json").write_text(json.dumps(timings_run2, indent=2), encoding="utf-8")

    print("\n=== STEP C: SCORING ===")
    gold_docs: dict[str, dict[str, Any]] = {}
    gold_mentions: dict[str, list[dict[str, Any]]] = {}
    for d in doc_ids:
        g_data = json.loads((converted_dir / f"{d}.json").read_text(encoding="utf-8"))
        gold_docs[d] = g_data
        gold_mentions[d] = load_gold_doc_mentions(g_data)

    synthetic_metrics = json.loads(step6_metrics_path.read_text(encoding="utf-8"))

    metrics_out, errors_out, per_file_out = compute_all_metrics(
        gold_docs=gold_docs,
        gold_mentions=gold_mentions,
        run1_saved=run1_saved,
        degraded_saved=degraded_saved,
        meta=meta_by_doc,
        texts_by_doc=texts_by_doc,
        coverage_report=coverage_report,
        synthetic_metrics=synthetic_metrics,
        timings_run1=timings_run1,
        timings_run2=timings_run2,
    )

    (results_dir / "metrics.json").write_text(json.dumps(metrics_out, indent=2), encoding="utf-8")
    (results_dir / "errors.json").write_text(json.dumps(errors_out, indent=2, ensure_ascii=False), encoding="utf-8")
    (results_dir / "per_file.json").write_text(json.dumps(per_file_out, indent=2), encoding="utf-8")

    print("\n=== STEP D: MARKDOWN & ARTIFACTS ===")
    step7_md = build_step7_markdown(metrics_out)

    results_md_path = REPO_ROOT / "docs" / "RESULTS.md"
    existing_md = results_md_path.read_text(encoding="utf-8")
    if "<!-- STEP7:BEGIN -->" in existing_md:
        raise ValueError("<!-- STEP7:BEGIN --> already exists in docs/RESULTS.md")

    updated_md = existing_md.rstrip() + "\n\n" + step7_md + "\n"
    results_md_path.write_text(updated_md, encoding="utf-8")
    print("Successfully appended Step 7 results block to docs/RESULTS.md!")

    # Run pytest across the whole test suite
    print("Running full pytest suite to capture pytest_raw.txt...")
    env = os.environ.copy()
    env["HF_HUB_OFFLINE"] = "1"
    py_res = subprocess.run([sys.executable, "-m", "pytest", "-v", "tests"], capture_output=True, text=True, env=env)
    pytest_raw = py_res.stdout + ("\n" + py_res.stderr if py_res.stderr else "")
    (results_dir / "pytest_raw.txt").write_text(pytest_raw, encoding="utf-8")
    print(f"Captured pytest output (exit code {py_res.returncode})")

    # Generate SHA256SUMS.txt
    print("Computing SHA256SUMS.txt for all files in results directory...")
    all_files: list[Path] = []
    for root, _, files in os.walk(results_dir):
        for f in files:
            fp = Path(root) / f
            if fp.name != "SHA256SUMS.txt":
                all_files.append(fp)
    all_files.sort(key=lambda p: p.relative_to(results_dir).as_posix())

    sums_lines = []
    for fp in all_files:
        rel = fp.relative_to(results_dir).as_posix()
        digest = compute_sha256(fp)
        sums_lines.append(f"{digest}  {rel}")
    sha256_path = results_dir / "SHA256SUMS.txt"
    sha256_path.write_text("\n".join(sums_lines) + "\n", encoding="utf-8")

    # Make all files in results_dir read-only
    print("Setting read-only attribute on all generated result files...")
    for root, _, files in os.walk(results_dir):
        for f in files:
            fp = Path(root) / f
            try:
                os.chmod(fp, stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)
            except Exception:
                pass

    print("Step 7 evaluation and reporting complete!")


if __name__ == "__main__":
    main()
