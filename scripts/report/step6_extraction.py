"""
Step 6d: End-to-end extraction pipeline evaluation and reporting script.
Runs tests, offline live-model extraction twice for determinism, degraded heuristic mode,
golden demo paragraph, negative input suite, and computes all mention, entity, attribute,
relation, latency, robustness, and digest metrics from saved files only.
Documents results in docs/RESULTS.md under <!-- STEP6:BEGIN --> ... <!-- STEP6:END -->.
"""

from __future__ import annotations

import argparse
import copy
import datetime
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

import torch
import transformers

from ai_pipeline import ner_baseline
from ai_pipeline.pipeline import analyze_text
from ai_pipeline.relations import extract_relations, split_sentences
from scripts.check_results_docs import ALL_BANNED
from ai_pipeline.scoring import (
    _load_contract_docs,
    load_doc_meta,
    load_gold_mentions,
    prf,
    score_mentions,
    score_relations,
)
from contracts.v1_1.validate import VALID_TYPE_PAIRS, validate_ai_output

SCORED_MENTION_TYPES: tuple[str, ...] = (
    "PERSON", "ALIAS", "FATHER", "PHONE", "IMEI", "ACCOUNT", "AMOUNT",
)
CORE_ENTITY_TYPES: tuple[str, ...] = ("PERSON", "PHONE", "IMEI", "ACCOUNT")
RELATION_LABELS: tuple[str, ...] = (
    "OWNS_DEVICE",
    "ASSOCIATED_IMEI",
    "COMMUNICATED_WITH",
    "CONTROLS_ACCOUNT",
    "TRANSFERRED_FUNDS",
)
SPLITS: tuple[str, ...] = ("train", "dev", "test")
LANGUAGES: tuple[str, ...] = ("hinglish", "hindi", "english")

# Explicit subset excludes ownership of the master number by the second suspect (unstated in text)
EXPLICIT_GOLDEN_EXCLUSION_RULE: dict[str, Any] = {
    "relation": "OWNS_DEVICE",
    "suspect_index": 1,
    "phone_index": 1,
}

PIPELINE_MODULES: tuple[str, ...] = (
    "normalizer.py",
    "validators.py",
    "identifiers.py",
    "names.py",
    "ner_baseline.py",
    "assemble.py",
    "relations.py",
    "pipeline.py",
    "scoring.py",
)

FORBIDDEN_PROSE_WORDS: tuple[str, ...] = ALL_BANNED


def compute_sha256(filepath: Path) -> str:
    """Compute standard SHA-256 hex digest for a single file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def compute_combined_sha256(files: list[Path], base_dir: Path | None = None) -> str:
    """Compute SHA-256 digest over sorted 'name:sha256\\n' lines."""
    if base_dir is not None:
        keyed = [(fp.relative_to(base_dir).as_posix(), fp) for fp in files]
    else:
        keyed = [(fp.name, fp) for fp in files]
    keyed.sort(key=lambda pair: pair[0])
    lines = [f"{name}:{compute_sha256(fp)}\n" for name, fp in keyed]
    return hashlib.sha256("".join(lines).encode("utf-8")).hexdigest()


def _counts_to_dict(counts_obj: Any, include_prf: bool = True) -> dict[str, Any]:
    """Convert Counts or dict to plain JSON dict optionally with precision, recall, f1."""
    if isinstance(counts_obj, dict):
        tp = int(counts_obj.get("tp", 0))
        fp = int(counts_obj.get("fp", 0))
        fn = int(counts_obj.get("fn", 0))
    else:
        tp = int(counts_obj.tp)
        fp = int(counts_obj.fp)
        fn = int(counts_obj.fn)
    out: dict[str, Any] = {"tp": tp, "fp": fp, "fn": fn}
    if include_prf:
        p, r, f = prf(tp, fp, fn)
        out["precision"] = p
        out["recall"] = r
        out["f1"] = f
    return out


def align_contract_entities(
    gold_doc: dict[str, Any],
    pred_doc: dict[str, Any],
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """
    Reproduce exact Contract v1.1 entity alignment from ai_pipeline.scoring.score_relations
    and return aligned (pred_ent, gold_ent) pairs.
    """
    g_map: dict[str, dict[str, Any]] = {}
    g_spans: dict[str, set[tuple[int, int]]] = {}
    for ent in gold_doc.get("entities", []):
        eid = ent["id"]
        g_map[eid] = ent
        spans: set[tuple[int, int]] = set()
        for m in ent.get("mentions", []):
            cs = m.get("char_span")
            if cs and len(cs) == 2:
                spans.add((int(cs[0]), int(cs[1])))
        cs = ent.get("char_span")
        if cs and len(cs) == 2:
            spans.add((int(cs[0]), int(cs[1])))
        g_spans[eid] = spans

    p_map: dict[str, dict[str, Any]] = {}
    p_spans: dict[str, set[tuple[int, int]]] = {}
    for ent in pred_doc.get("entities", []):
        eid = ent["id"]
        p_map[eid] = ent
        spans = set()
        for m in ent.get("mentions", []):
            cs = m.get("char_span")
            if cs and len(cs) == 2:
                spans.add((int(cs[0]), int(cs[1])))
        cs = ent.get("char_span")
        if cs and len(cs) == 2:
            spans.add((int(cs[0]), int(cs[1])))
        p_spans[eid] = spans

    candidate_pairs: list[tuple[int, str, str]] = []
    for pid, ps in p_spans.items():
        for gid, gs in g_spans.items():
            if p_map[pid].get("type") == g_map[gid].get("type"):
                shared = len(ps & gs)
                if shared >= 1:
                    candidate_pairs.append((shared, pid, gid))
    candidate_pairs.sort(key=lambda x: (-x[0], x[1], x[2]))

    aligned_pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    used_p: set[str] = set()
    used_g: set[str] = set()
    for _, pid, gid in candidate_pairs:
        if pid not in used_p and gid not in used_g:
            used_p.add(pid)
            used_g.add(gid)
            aligned_pairs.append((p_map[pid], g_map[gid]))
    return aligned_pairs


def run_contrast_relations(
    text: str,
    doc: dict[str, Any],
    aux: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Baseline CONTRAST extractor: emits every type-valid relation pair among entities
    co-occurring within the same sentence without checking any cue words.
    """
    if not text or not doc.get("entities"):
        return []

    sentences = split_sentences(text)
    if not sentences:
        return []

    all_mentions: list[dict[str, Any]] = []
    for ent in doc.get("entities", []):
        eid = ent["id"]
        etype = ent["type"]
        valid_kind = "NAME" if etype == "PERSON" else "VALUE"
        for m in ent.get("mentions", []):
            if m.get("kind") != valid_kind:
                continue
            cs = m["char_span"]
            all_mentions.append({
                "id": eid,
                "type": etype,
                "start": int(cs[0]),
                "end": int(cs[1]),
            })

    amounts = list(aux.get("amounts", []))
    relationships: list[dict[str, Any]] = []
    seen_triples: set[tuple[str, str, str]] = set()

    for sent_start, sent_end, _ in sentences:
        s_mentions = sorted(
            (m for m in all_mentions if sent_start <= m["start"] and m["end"] <= sent_end),
            key=lambda m: (m["start"], m["end"]),
        )
        # First mention per distinct entity id within the sentence
        s_ents: list[dict[str, Any]] = []
        seen_ent_ids: set[str] = set()
        for m in s_mentions:
            if m["id"] not in seen_ent_ids:
                seen_ent_ids.add(m["id"])
                s_ents.append(m)

        s_amounts = [
            float(a["value"])
            for a in amounts
            if sent_start <= int(a["start"]) and int(a["end"]) <= sent_end and float(a["value"]) > 0
        ]
        ev_span = [sent_start, sent_end]

        for rel_type in RELATION_LABELS:
            allowed_pairs = VALID_TYPE_PAIRS[rel_type]
            for i, src_ent in enumerate(s_ents):
                for j, tgt_ent in enumerate(s_ents):
                    if src_ent["id"] == tgt_ent["id"]:
                        continue
                    if src_ent["type"] == tgt_ent["type"] and i >= j:
                        continue
                    if (src_ent["type"], tgt_ent["type"]) not in allowed_pairs:
                        continue
                    key = (src_ent["id"], tgt_ent["id"], rel_type)
                    if key in seen_triples:
                        continue
                    seen_triples.add(key)
                    rel_obj: dict[str, Any] = {
                        "source": src_ent["id"],
                        "target": tgt_ent["id"],
                        "relation": rel_type,
                        "trigger": "CONTRAST",
                        "confidence": 0.1,
                        "evidence_char_span": list(ev_span),
                    }
                    if rel_type == "TRANSFERRED_FUNDS" and s_amounts:
                        rel_obj["amount"] = s_amounts[0]
                    relationships.append(rel_obj)

    return relationships


def extract_mentions_from_analysis(
    payload: dict[str, Any],
) -> tuple[list[dict[str, Any]], int, int]:
    """
    Extract scored mentions (PERSON, ALIAS, FATHER, PHONE, IMEI, ACCOUNT, AMOUNT) from a
    saved analysis payload, plus separate VEHICLE mention and entity counts.
    """
    doc = payload["doc"]
    aux = payload["aux"]
    mentions: list[dict[str, Any]] = []
    vehicle_mentions = 0
    vehicle_entities = 0

    for ent in doc.get("entities", []):
        etype = ent["type"]
        if etype == "VEHICLE":
            vehicle_entities += 1
            vehicle_mentions += len(ent.get("mentions", []))
            continue
        for m in ent.get("mentions", []):
            kind = m.get("kind")
            cs = m["char_span"]
            surf = m.get("surface", "")
            if kind == "NAME":
                m_type = "PERSON"
            elif kind in ("ALIAS", "FATHER"):
                m_type = kind
            elif kind == "VALUE":
                m_type = etype
            else:
                continue
            if m_type in SCORED_MENTION_TYPES:
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

    return mentions, vehicle_mentions, vehicle_entities


def compute_attribute_metrics(
    gold_docs: dict[str, dict[str, Any]],
    pred_docs: dict[str, dict[str, Any]],
    meta: dict[str, dict[str, str]],
) -> dict[str, Any]:
    """
    Compute aliases, father_name (against gold FATHER mention surface), and role agreement
    among aligned PERSON entities overall and per language.
    """
    buckets: dict[str, dict[str, int]] = {}
    for scope in ("overall",) + LANGUAGES:
        buckets[scope] = {
            "aligned_persons": 0,
            "aliases_match": 0,
            "father_match": 0,
            "role_match": 0,
            "with_gold_father_total": 0,
            "with_gold_father_match": 0,
        }

    for doc_id in sorted(gold_docs.keys()):
        g_doc = gold_docs[doc_id]
        p_doc = pred_docs.get(doc_id, {"entities": []})
        lang = meta[doc_id]["language"].lower()
        aligned = align_contract_entities(g_doc, p_doc)
        for p_ent, g_ent in aligned:
            if g_ent.get("type") != "PERSON":
                continue
            aliases_eq = set(p_ent.get("aliases") or []) == set(g_ent.get("aliases") or [])
            gold_father_surfaces = [
                m["surface"] for m in g_ent.get("mentions", []) if m.get("kind") == "FATHER"
            ]
            p_father = p_ent.get("father_name")
            if gold_father_surfaces:
                father_eq = p_father in set(gold_father_surfaces)
            else:
                father_eq = p_father is None
            role_eq = p_ent.get("role") == g_ent.get("role")

            for scope in ("overall", lang):
                b = buckets[scope]
                b["aligned_persons"] += 1
                if aliases_eq:
                    b["aliases_match"] += 1
                if father_eq:
                    b["father_match"] += 1
                if role_eq:
                    b["role_match"] += 1
                if gold_father_surfaces:
                    b["with_gold_father_total"] += 1
                    if father_eq:
                        b["with_gold_father_match"] += 1

    out: dict[str, Any] = {}
    for scope, b in buckets.items():
        tot = b["aligned_persons"]
        ftot = b["with_gold_father_total"]
        out[scope] = {
            "aligned_persons": tot,
            "aliases": {
                "matches": b["aliases_match"],
                "total": tot,
                "rate": (b["aliases_match"] / tot) if tot else None,
            },
            "father_name": {
                "matches": b["father_match"],
                "total": tot,
                "rate": (b["father_match"] / tot) if tot else None,
                "with_gold_father_matches": b["with_gold_father_match"],
                "with_gold_father_total": ftot,
            },
            "role": {
                "matches": b["role_match"],
                "total": tot,
                "rate": (b["role_match"] / tot) if tot else None,
            },
        }
    return out


def compute_relation_suite(
    gold_docs: dict[str, dict[str, Any]],
    pred_docs: dict[str, dict[str, Any]],
    meta: dict[str, dict[str, str]],
) -> dict[str, Any]:
    """Compute overall per-label + micro, by-split micro, and by-language micro relation scores."""
    res_all = score_relations(gold_docs, pred_docs)
    by_label = {
        lbl: _counts_to_dict(res_all["by_label"].get(lbl, {"tp": 0, "fp": 0, "fn": 0}))
        for lbl in RELATION_LABELS
    }
    overall_micro = _counts_to_dict(res_all["micro"])

    by_split: dict[str, Any] = {}
    for sp in SPLITS:
        ids = [d for d in sorted(gold_docs.keys()) if meta[d]["split"] == sp]
        sub_res = score_relations(
            {d: gold_docs[d] for d in ids},
            {d: pred_docs[d] for d in ids},
        )
        by_split[sp] = {"micro": _counts_to_dict(sub_res["micro"])}

    by_language: dict[str, Any] = {}
    for lang in LANGUAGES:
        ids = [d for d in sorted(gold_docs.keys()) if meta[d]["language"].lower() == lang]
        sub_res = score_relations(
            {d: gold_docs[d] for d in ids},
            {d: pred_docs[d] for d in ids},
        )
        by_language[lang] = {"micro": _counts_to_dict(sub_res["micro"])}

    return {
        "overall": {"by_label": by_label, "micro": overall_micro},
        "by_split": by_split,
        "by_language": by_language,
    }


def classify_origin(trigger: str) -> str:
    """Map relationship trigger string into lexicon_cue, ANAPHORA, ROLE_CUE, or STRUCTURE."""
    if trigger in ("STRUCTURE", "ANAPHORA", "ROLE_CUE"):
        return trigger
    return "lexicon_cue"


def compute_percentile(values: list[float], pct: float) -> float:
    """Compute nearest-rank percentile on a non-empty list of floats."""
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, math.ceil((pct / 100.0) * len(ordered)) - 1))
    return ordered[idx]


def parse_pytest_summary(pytest_raw_text: str) -> dict[str, Any]:
    """Parse per-file passed/failed/skipped/error counts and failures list from pytest -v output."""
    line_rx = re.compile(
        r"^(tests[/\\][^:\s]+)::(.+?)\s+(PASSED|FAILED|SKIPPED|ERROR)(?:\s+\[.*\])?\s*$",
        re.MULTILINE,
    )
    by_file: dict[str, dict[str, int]] = {}
    failures: list[dict[str, str]] = []

    for m in line_rx.finditer(pytest_raw_text):
        test_file = m.group(1).replace("\\", "/")
        test_node = m.group(2)
        outcome = m.group(3)
        entry = by_file.setdefault(
            test_file,
            {"passed": 0, "failed": 0, "skipped": 0, "errors": 0},
        )
        if outcome == "PASSED":
            entry["passed"] += 1
        elif outcome == "FAILED":
            entry["failed"] += 1
            failures.append({"file": test_file, "test": test_node, "outcome": outcome})
        elif outcome == "SKIPPED":
            entry["skipped"] += 1
        elif outcome == "ERROR":
            entry["errors"] += 1
            failures.append({"file": test_file, "test": test_node, "outcome": outcome})

    sorted_files = {k: by_file[k] for k in sorted(by_file.keys())}
    tot_passed = sum(v["passed"] for v in sorted_files.values())
    tot_failed = sum(v["failed"] for v in sorted_files.values())
    tot_skipped = sum(v["skipped"] for v in sorted_files.values())
    tot_errors = sum(v["errors"] for v in sorted_files.values())
    tot_collected = tot_passed + tot_failed + tot_skipped + tot_errors

    m_coll = re.search(r"collected\s+(\d+)\s+items", pytest_raw_text)
    if m_coll and tot_collected != int(m_coll.group(1)):
        raise ValueError(
            f"Parsed test count {tot_collected} != pytest collected {m_coll.group(1)}"
        )

    return {
        "by_file": sorted_files,
        "total_passed": tot_passed,
        "total_failed": tot_failed,
        "total_skipped": tot_skipped,
        "total_errors": tot_errors,
        "total_collected": tot_collected,
        "failures": failures,
    }


def get_metric_by_path(metrics: dict[str, Any], path: str) -> tuple[str, Any]:
    """
    Walk metrics dict step by step using dot notation.
    Returns (path, value). Aborts with ValueError if any step is missing.
    """
    curr: Any = metrics
    for step in path.split("."):
        if isinstance(curr, dict) and step in curr:
            curr = curr[step]
        else:
            raise ValueError(f"Missing metrics path step {step!r} in {path!r}")
    return path, curr


def format_key_number_line(metrics: dict[str, Any], path: str, label: str) -> str:
    """Format a nested Key Numbers bullet line using get_metric_by_path."""
    resolved_path, val = get_metric_by_path(metrics, path)
    if re.search(r"\d", label):
        raise ValueError(f"Key Numbers label must not contain typed digits: {label!r}")
    if isinstance(val, float):
        val_str = f"{val:.4f}"
    else:
        val_str = str(val)
    return f"  - `metrics.json` (`{resolved_path}`): {val_str} {label}"


def _assert_opt_float(cell: str, val: float | None, decimals: int = 4) -> None:
    """Assert cell matches optional float rounded to decimals or em dash."""
    if val is None:
        assert cell == "—", f"Expected '—', got {cell!r}"
    else:
        assert float(cell) == round(val, decimals), f"Float mismatch: {cell} != {round(val, decimals)}"


def _fmt_num(val: float | None, decimals: int = 4) -> str:
    """Format optional float or return em dash."""
    if val is None:
        return "—"
    return f"{val:.{decimals}f}"


def extract_table_rows(section_md: str, heading_keyword: str) -> list[list[str]]:
    """Extract data rows from markdown table immediately following heading_keyword."""
    lines = section_md.splitlines()
    table_lines: list[str] = []
    found = False
    for line in lines:
        if heading_keyword in line:
            found = True
            continue
        if found:
            stripped = line.strip()
            if stripped.startswith("|"):
                table_lines.append(stripped)
            elif table_lines:
                break
    if len(table_lines) < 3:
        raise ValueError(f"Table {heading_keyword!r} missing header/separator/rows.")
    rows: list[list[str]] = []
    for tl in table_lines[2:]:
        cells = [c.strip() for c in tl.split("|")[1:-1]]
        rows.append(cells)
    return rows


def assert_tables_match_metrics(section_md: str, metrics: dict[str, Any]) -> None:
    """Assert every table value matches metrics.json and all table formatting rules hold."""
    # Table A: Mentions (run1)
    for row in extract_table_rows(section_md, "Table A:"):
        etype, sp, sr, sf1, stp, sfp, sfn, lp, lr, lf1, ltp, lfp, lfn = row
        m_st = metrics["mentions"]["overall"][etype]["strict"]
        m_lt = metrics["mentions"]["overall"][etype]["lenient"]
        _assert_opt_float(sp, m_st["precision"])
        _assert_opt_float(sr, m_st["recall"])
        _assert_opt_float(sf1, m_st["f1"])
        assert int(stp) == m_st["tp"] and int(sfp) == m_st["fp"] and int(sfn) == m_st["fn"]
        _assert_opt_float(lp, m_lt["precision"])
        _assert_opt_float(lr, m_lt["recall"])
        _assert_opt_float(lf1, m_lt["f1"])
        assert int(ltp) == m_lt["tp"] and int(lfp) == m_lt["fp"] and int(lfn) == m_lt["fn"]

    # Table B: Entities (overall, split, language)
    for row in extract_table_rows(section_md, "Table B:"):
        scope_type, scope_val, etype, p_s, r_s, f_s, tp_s, fp_s, fn_s = row
        if scope_type == "Overall":
            d = metrics["entities"]["overall"][etype]
        elif scope_type == "Split":
            d = metrics["entities"]["by_split"][scope_val][etype]
        else:
            d = metrics["entities"]["by_language"][scope_val][etype]
        _assert_opt_float(p_s, d["precision"])
        _assert_opt_float(r_s, d["recall"])
        _assert_opt_float(f_s, d["f1"])
        assert int(tp_s) == d["tp"] and int(fp_s) == d["fp"] and int(fn_s) == d["fn"]

    # Table C: Attributes
    for row in extract_table_rows(section_md, "Table C:"):
        lang, al_tot, a_m, a_r, f_m, f_r, r_m, r_r = row
        d = metrics["attributes"][lang]
        assert int(al_tot) == d["aligned_persons"]
        assert int(a_m) == d["aliases"]["matches"]
        _assert_opt_float(a_r, d["aliases"]["rate"])
        assert int(f_m) == d["father_name"]["matches"]
        _assert_opt_float(f_r, d["father_name"]["rate"])
        assert int(r_m) == d["role"]["matches"]
        _assert_opt_float(r_r, d["role"]["rate"])

    # Table D: Relations overall by label & micro
    for row in extract_table_rows(section_md, "Table D:"):
        ext, _, rel_lbl, tp_s, fp_s, fn_s, p_s, r_s, f_s = row
        if rel_lbl == "MICRO":
            d = metrics["relations"][ext]["overall"]["micro"]
        else:
            d = metrics["relations"][ext]["overall"]["by_label"][rel_lbl]
        assert int(tp_s) == d["tp"] and int(fp_s) == d["fp"] and int(fn_s) == d["fn"]
        _assert_opt_float(p_s, d["precision"])
        _assert_opt_float(r_s, d["recall"])
        _assert_opt_float(f_s, d["f1"])

    # Table E: Relations micro by split and language
    for row in extract_table_rows(section_md, "Table E:"):
        ext, gtype, gval, tp_s, fp_s, fn_s, p_s, r_s, f_s = row
        section_key = "by_split" if gtype == "Split" else "by_language"
        d = metrics["relations"][ext][section_key][gval]["micro"]
        assert int(tp_s) == d["tp"] and int(fp_s) == d["fp"] and int(fn_s) == d["fn"]
        _assert_opt_float(p_s, d["precision"])
        _assert_opt_float(r_s, d["recall"])
        _assert_opt_float(f_s, d["f1"])

    # Table F: Relation origins per split
    for row in extract_table_rows(section_md, "Table F:"):
        sp, lex_s, ana_s, role_s, str_s, tot_s = row
        d = metrics["origins"][sp]
        assert int(lex_s) == d["lexicon_cue"]
        assert int(ana_s) == d["ANAPHORA"]
        assert int(role_s) == d["ROLE_CUE"]
        assert int(str_s) == d["STRUCTURE"]
        assert int(tot_s) == d["total"]

    # Table G: Dev-vs-Test Micro F1
    for row in extract_table_rows(section_md, "Table G:"):
        ext, dev_s, test_s, diff_s = row
        d = metrics["dev_vs_test"][ext]
        _assert_opt_float(dev_s, d["dev_micro_f1"])
        _assert_opt_float(test_s, d["test_micro_f1"])
        _assert_opt_float(diff_s, d["diff_test_minus_dev"])

    # Table H: Degraded Entities
    for row in extract_table_rows(section_md, "Table H:"):
        etype, tp_s, fp_s, fn_s, p_s, r_s, f_s = row
        d = metrics["degraded"]["entities"][etype]
        assert int(tp_s) == d["tp"] and int(fp_s) == d["fp"] and int(fn_s) == d["fn"]
        _assert_opt_float(p_s, d["precision"])
        _assert_opt_float(r_s, d["recall"])
        _assert_opt_float(f_s, d["f1"])

    # Table I: Degraded Relations
    for row in extract_table_rows(section_md, "Table I:"):
        sp, tp_s, fp_s, fn_s, p_s, r_s, f_s = row
        d = metrics["degraded"]["relations"][sp]["micro"]
        assert int(tp_s) == d["tp"] and int(fp_s) == d["fp"] and int(fn_s) == d["fn"]
        _assert_opt_float(p_s, d["precision"])
        _assert_opt_float(r_s, d["recall"])
        _assert_opt_float(f_s, d["f1"])

    # Table L: Golden Score Summary
    for row in extract_table_rows(section_md, "Table L:"):
        ext, gold_key, cnt_s, tp_s, fp_s, fn_s, p_s, r_s, f_s = row
        d = metrics["golden"]["scores"][ext][gold_key]
        assert int(cnt_s) == d["gold_count"]
        assert int(tp_s) == d["tp"] and int(fp_s) == d["fp"] and int(fn_s) == d["fn"]
        _assert_opt_float(p_s, d["precision"])
        _assert_opt_float(r_s, d["recall"])
        _assert_opt_float(f_s, d["f1"])

    # Table M: Latency Breakdown
    for row in extract_table_rows(section_md, "Table M:"):
        stage, mean_s, p95_s = row
        if stage == "model_load":
            assert float(mean_s) == round(metrics["latency"]["model_load_ms"], 3)
            assert p95_s == "—"
        else:
            d = metrics["latency"]["run2"][stage]
            assert float(mean_s) == round(d["mean_ms"], 3)
            assert float(p95_s) == round(d["p95_ms"], 3)

    # Table N: Determinism
    rows_n = extract_table_rows(section_md, "Table N:")
    assert int(rows_n[0][3]) == metrics["determinism"]["exact_matches"]
    assert int(rows_n[0][4]) == metrics["determinism"]["total_docs"]
    assert rows_n[0][5] == str(metrics["determinism"]["all_match"])

    # Table O: Corpus Validation & Exceptions
    for row in extract_table_rows(section_md, "Table O:"):
        mode_k, tot_s, val_s, exc_s = row
        d = metrics["robustness"][mode_k]
        assert int(tot_s) == d["total_docs"]
        assert int(val_s) == d["valid_docs"]
        assert int(exc_s) == sum(d["exceptions_by_class"].values())

    # Table P: Negative Input Outcomes
    for row in extract_table_rows(section_md, "Table P:"):
        lbl, raised_s, exc_cls = row
        d = metrics["robustness"]["negative_inputs"][lbl]
        assert raised_s == str(d["raised"])
        assert exc_cls == d["exception_class"]

    # Table R: Pytest Suite Results
    for row in extract_table_rows(section_md, "Table R:"):
        tfile, p_s, f_s, sk_s, e_s = row
        if tfile == "TOTAL":
            ts = metrics["tests_summary"]
            assert int(p_s) == ts["total_passed"]
            assert int(f_s) == ts["total_failed"]
            assert int(sk_s) == ts["total_skipped"]
            assert int(e_s) == ts["total_errors"]
        else:
            tfile_clean = tfile.strip("`")
            d = metrics["tests_summary"]["by_file"][tfile_clean]
            assert int(p_s) == d["passed"]
            assert int(f_s) == d["failed"]
            assert int(sk_s) == d["skipped"]
            assert int(e_s) == d["errors"]


def validate_markdown_rules(section_md: str) -> None:
    """Enforce uniform table column counts, bullet spacing, zero forbidden words, and zero digits in prose."""
    for line in section_md.splitlines():
        if "test_perfect_predictions_give_one" in line:
            continue
        for word in FORBIDDEN_PROSE_WORDS:
            if re.search(rf"\b{re.escape(word)}\b", line, re.IGNORECASE):
                raise ValueError(f"Forbidden word {word!r} appeared in Step 6 markdown: {line!r}")

    lines = section_md.splitlines()
    table_block: list[str] = []
    in_prose_only_section = False
    prose_no_digit_sections = {
        "### Glossary",
        "### Design Decisions",
        "### Caveats",
        "### What This Does Not Show",
    }

    def _check_table(block: list[str]) -> None:
        counts = [len(tl.split("|")[1:-1]) for tl in block]
        if len(set(counts)) != 1:
            raise ValueError(f"Inconsistent column counts {counts} in table:\n" + "\n".join(block))

    for line in lines:
        trimmed = line.strip()
        if trimmed.startswith("|") and trimmed.endswith("|"):
            table_block.append(trimmed)
        else:
            if table_block:
                _check_table(table_block)
                table_block = []

        if trimmed.startswith("### "):
            in_prose_only_section = trimmed in prose_no_digit_sections

        if trimmed.startswith("-"):
            if not re.match(r"^(?:  )*- ", line):
                raise ValueError(f"Invalid bullet indentation: {line!r}")

        # Prose outside backticks, tables, headings, HTML markers, and Key Numbers metric values must have no digits
        if (
            in_prose_only_section
            and trimmed
            and not trimmed.startswith("#")
            and not trimmed.startswith("<!--")
        ):
            # Strip inline code spans for prose digit checks cleanly
            prose_part = re.sub(r"`[^`]*`", "", line)
            if re.search(r"\d", prose_part):
                raise ValueError(f"Digit found in prose section line: {line!r}")

    if table_block:
        _check_table(table_block)


def build_markdown_section(
    metrics: dict[str, Any],
    output_hashes: dict[str, str],
) -> str:
    """Build complete <!-- STEP6:BEGIN --> ... <!-- STEP6:END --> block from metrics.json."""
    meta = metrics["meta"]
    ih = metrics["input_hashes"]

    # Results card paths built exclusively from get_metric_by_path
    key_numbers = "\n".join([
        format_key_number_line(metrics, "determinism.exact_matches", "byte-identical files between first and second offline runs"),
        format_key_number_line(metrics, "mentions.overall.PERSON.strict.f1", "mention strict score for persons"),
        format_key_number_line(metrics, "mentions.overall.ALIAS.strict.f1", "mention strict score for aliases"),
        format_key_number_line(metrics, "mentions.overall.FATHER.strict.f1", "mention strict score for father names"),
        format_key_number_line(metrics, "mentions.overall.PHONE.strict.f1", "mention strict score for phone numbers"),
        format_key_number_line(metrics, "mentions.overall.IMEI.strict.f1", "mention strict score for device identifiers"),
        format_key_number_line(metrics, "mentions.overall.ACCOUNT.strict.f1", "mention strict score for bank accounts"),
        format_key_number_line(metrics, "mentions.overall.AMOUNT.strict.f1", "mention strict score for monetary amounts"),
        format_key_number_line(metrics, "mentions.vehicle_mentions_found", "vehicle candidate mentions detected without scoring"),
        format_key_number_line(metrics, "entities.overall.PERSON.f1", "entity alignment score for persons"),
        format_key_number_line(metrics, "attributes.overall.role.rate", "role agreement rate among aligned person entities"),
        format_key_number_line(metrics, "attributes.overall.aliases.rate", "alias set agreement rate among aligned person entities"),
        format_key_number_line(metrics, "attributes.overall.father_name.rate", "father surface agreement rate among aligned person entities"),
        format_key_number_line(metrics, "relations.CUE.overall.micro.f1", "relation micro score for cue extractor (first scored)"),
        format_key_number_line(metrics, "relations.HYBRID.overall.micro.f1", "relation micro score for hybrid extractor (second look)"),
        format_key_number_line(metrics, "relations.CONTRAST.overall.micro.f1", "relation micro score for co-occurrence contrast"),
        format_key_number_line(metrics, "relations.HYBRID.by_split.dev.micro.f1", "hybrid relation micro score on dev split"),
        format_key_number_line(metrics, "relations.HYBRID.by_split.test.micro.f1", "hybrid relation micro score on test split"),
        format_key_number_line(metrics, "origins.test.STRUCTURE", "fallback structural relations emitted on test split"),
        format_key_number_line(metrics, "degraded.relations.overall.micro.f1", "degraded mode relation micro score without neural model"),
        format_key_number_line(metrics, "golden.scores.CUE.all_gold.f1", "golden paragraph cue score against full gold set"),
        format_key_number_line(metrics, "golden.scores.HYBRID.all_gold.f1", "golden paragraph hybrid score against full gold set"),
        format_key_number_line(metrics, "golden.scores.HYBRID.explicit_subset.f1", "golden paragraph hybrid score against explicit subset"),
        format_key_number_line(metrics, "latency.model_load_ms", "cold offline model load duration in milliseconds"),
        format_key_number_line(metrics, "latency.run2.total.mean_ms", "mean per-document runtime in milliseconds during cached run"),
        format_key_number_line(metrics, "latency.run2.total.p95_ms", "high percentile per-document runtime in milliseconds during cached run"),
        format_key_number_line(metrics, "robustness.run1.valid_docs", "documents passing schema validation in first live run"),
        format_key_number_line(metrics, "robustness.degraded.valid_docs", "documents passing schema validation in degraded mode"),
        format_key_number_line(metrics, "tests_summary.total_passed", "unit tests passing across full test folder"),
    ])

    # Table A: Mentions
    rows_a = []
    for etype in SCORED_MENTION_TYPES:
        st = metrics["mentions"]["overall"][etype]["strict"]
        lt = metrics["mentions"]["overall"][etype]["lenient"]
        rows_a.append(
            f"| {etype} | {_fmt_num(st['precision'])} | {_fmt_num(st['recall'])} | {_fmt_num(st['f1'])} "
            f"| {st['tp']} | {st['fp']} | {st['fn']} "
            f"| {_fmt_num(lt['precision'])} | {_fmt_num(lt['recall'])} | {_fmt_num(lt['f1'])} "
            f"| {lt['tp']} | {lt['fp']} | {lt['fn']} |"
        )
    table_a = "\n".join(rows_a)

    # Table B: Entities
    rows_b = []
    for etype in CORE_ENTITY_TYPES:
        d = metrics["entities"]["overall"][etype]
        rows_b.append(
            f"| Overall | all | {etype} | {_fmt_num(d['precision'])} | {_fmt_num(d['recall'])} | {_fmt_num(d['f1'])} "
            f"| {d['tp']} | {d['fp']} | {d['fn']} |"
        )
    for sp in SPLITS:
        for etype in CORE_ENTITY_TYPES:
            d = metrics["entities"]["by_split"][sp][etype]
            rows_b.append(
                f"| Split | {sp} | {etype} | {_fmt_num(d['precision'])} | {_fmt_num(d['recall'])} | {_fmt_num(d['f1'])} "
                f"| {d['tp']} | {d['fp']} | {d['fn']} |"
            )
    for lang in LANGUAGES:
        for etype in CORE_ENTITY_TYPES:
            d = metrics["entities"]["by_language"][lang][etype]
            rows_b.append(
                f"| Language | {lang} | {etype} | {_fmt_num(d['precision'])} | {_fmt_num(d['recall'])} | {_fmt_num(d['f1'])} "
                f"| {d['tp']} | {d['fp']} | {d['fn']} |"
            )
    table_b = "\n".join(rows_b)

    # Table C: Attributes
    rows_c = []
    for scope in ("overall",) + LANGUAGES:
        d = metrics["attributes"][scope]
        rows_c.append(
            f"| {scope} | {d['aligned_persons']} | {d['aliases']['matches']} | {_fmt_num(d['aliases']['rate'])} "
            f"| {d['father_name']['matches']} | {_fmt_num(d['father_name']['rate'])} "
            f"| {d['role']['matches']} | {_fmt_num(d['role']['rate'])} |"
        )
    table_c = "\n".join(rows_c)

    # Table D: Relations Overall
    ext_roles = [("CUE", "first scored"), ("HYBRID", "second look"), ("CONTRAST", "co-occurrence baseline")]
    rows_d = []
    for ext, role_lbl in ext_roles:
        ov = metrics["relations"][ext]["overall"]
        for rel_lbl in RELATION_LABELS:
            d = ov["by_label"][rel_lbl]
            rows_d.append(
                f"| {ext} | {role_lbl} | {rel_lbl} | {d['tp']} | {d['fp']} | {d['fn']} "
                f"| {_fmt_num(d['precision'])} | {_fmt_num(d['recall'])} | {_fmt_num(d['f1'])} |"
            )
        m = ov["micro"]
        rows_d.append(
            f"| {ext} | {role_lbl} | MICRO | {m['tp']} | {m['fp']} | {m['fn']} "
            f"| {_fmt_num(m['precision'])} | {_fmt_num(m['recall'])} | {_fmt_num(m['f1'])} |"
        )
    table_d = "\n".join(rows_d)

    # Table E: Relations by Split and Language
    rows_e = []
    for ext, _ in ext_roles:
        for sp in SPLITS:
            d = metrics["relations"][ext]["by_split"][sp]["micro"]
            rows_e.append(
                f"| {ext} | Split | {sp} | {d['tp']} | {d['fp']} | {d['fn']} "
                f"| {_fmt_num(d['precision'])} | {_fmt_num(d['recall'])} | {_fmt_num(d['f1'])} |"
            )
        for lang in LANGUAGES:
            d = metrics["relations"][ext]["by_language"][lang]["micro"]
            rows_e.append(
                f"| {ext} | Language | {lang} | {d['tp']} | {d['fp']} | {d['fn']} "
                f"| {_fmt_num(d['precision'])} | {_fmt_num(d['recall'])} | {_fmt_num(d['f1'])} |"
            )
    table_e = "\n".join(rows_e)

    # Table F: Origins by Split
    rows_f = []
    for sp in SPLITS + ("overall",):
        d = metrics["origins"][sp]
        rows_f.append(
            f"| {sp} | {d['lexicon_cue']} | {d['ANAPHORA']} | {d['ROLE_CUE']} | {d['STRUCTURE']} | {d['total']} |"
        )
    table_f = "\n".join(rows_f)

    # Table G: Dev-vs-Test
    rows_g = []
    for ext in ("CUE", "HYBRID", "CONTRAST"):
        d = metrics["dev_vs_test"][ext]
        rows_g.append(
            f"| {ext} | {_fmt_num(d['dev_micro_f1'])} | {_fmt_num(d['test_micro_f1'])} | {d['diff_test_minus_dev']:+.4f} |"
        )
    table_g = "\n".join(rows_g)

    # Table H & I: Degraded Mode
    rows_h = []
    for etype in CORE_ENTITY_TYPES:
        d = metrics["degraded"]["entities"][etype]
        rows_h.append(
            f"| {etype} | {d['tp']} | {d['fp']} | {d['fn']} "
            f"| {_fmt_num(d['precision'])} | {_fmt_num(d['recall'])} | {_fmt_num(d['f1'])} |"
        )
    table_h = "\n".join(rows_h)

    rows_i = []
    for sp in SPLITS + ("overall",):
        d = metrics["degraded"]["relations"][sp]["micro"]
        rows_i.append(
            f"| {sp} | {d['tp']} | {d['fp']} | {d['fn']} "
            f"| {_fmt_num(d['precision'])} | {_fmt_num(d['recall'])} | {_fmt_num(d['f1'])} |"
        )
    table_i = "\n".join(rows_i)

    # Table J, K, L: Golden Demo
    g_info = metrics["golden"]
    rows_j = []
    for e in g_info["entities"]:
        val_or_name = (e.get("canonical_name") or e.get("value") or "").replace("|", "/")
        aliases_str = ", ".join(e.get("aliases", [])) if e.get("aliases") else "—"
        role_str = e.get("role") or "—"
        bank_str = e.get("bank") or "—"
        rows_j.append(f"| {e['id']} | {e['type']} | {val_or_name} | {aliases_str} | {role_str} | {bank_str} |")
    table_j = "\n".join(rows_j)

    rows_k = []
    for r in g_info["relationships"]:
        amt_str = str(r["amount"]) if "amount" in r else "—"
        src_disp = str(r["source_label"]).replace("|", "/")
        tgt_disp = str(r["target_label"]).replace("|", "/")
        trig_disp = str(r["trigger"]).replace("|", "/")
        rows_k.append(
            f"| {r['extractor']} | {r['relation']} | {src_disp} | {tgt_disp} | {amt_str} | {trig_disp} | {r['confidence']:.1f} |"
        )
    table_k = "\n".join(rows_k)

    rows_l = []
    for ext in ("CUE", "HYBRID"):
        for gset in ("all_gold", "explicit_subset"):
            d = g_info["scores"][ext][gset]
            rows_l.append(
                f"| {ext} | {gset} | {d['gold_count']} | {d['tp']} | {d['fp']} | {d['fn']} "
                f"| {_fmt_num(d['precision'])} | {_fmt_num(d['recall'])} | {_fmt_num(d['f1'])} |"
            )
    table_l = "\n".join(rows_l)

    # Table M: Latency
    lat = metrics["latency"]
    rows_m = [f"| model_load | {lat['model_load_ms']:.3f} | — |"]
    for st_name in ("model", "postprocess", "names_identifiers", "assemble", "relations", "validate", "total"):
        d = lat["run2"][st_name]
        rows_m.append(f"| {st_name} | {d['mean_ms']:.3f} | {d['p95_ms']:.3f} |")
    table_m = "\n".join(rows_m)

    # Table N: Determinism
    det = metrics["determinism"]
    table_n = (
        f"| All corpus analysis files | `{det['run1_combined_sha256'][:16]}...` | `{det['run2_combined_sha256'][:16]}...` "
        f"| {det['exact_matches']} | {det['total_docs']} | {det['all_match']} |"
    )

    # Table O & P: Validation & Negative Inputs
    rob = metrics["robustness"]
    rows_o = []
    for mode_k in ("run1", "run2", "degraded"):
        d = rob[mode_k]
        exc_cnt = sum(d["exceptions_by_class"].values())
        rows_o.append(f"| {mode_k} | {d['total_docs']} | {d['valid_docs']} | {exc_cnt} |")
    table_o = "\n".join(rows_o)

    rows_p = []
    for lbl in ("empty_string", "whitespace", "too_long_5001", "no_entities", "non_string_int_42"):
        d = rob["negative_inputs"][lbl]
        rows_p.append(f"| {lbl} | {d['raised']} | {d['exception_class']} |")
    table_p = "\n".join(rows_p)

    # Table Q: Input and Output Hashes
    hash_rows = []
    for name, digest in ih["ai_pipeline_modules"].items():
        hash_rows.append(f"| `ai_pipeline/{name}` | `{digest}` | Pipeline Module |")
    hash_rows.append(f"| `contracts/v1_1/validate.py` | `{ih['validate_py']}` | Contract Validator |")
    hash_rows.append(f"| `contracts/v1_1/ai_output_schema.json` | `{ih['ai_output_schema_json']}` | Output Schema |")
    hash_rows.append(f"| `contracts/v1_1/graph_render_schema.json` | `{ih['graph_render_schema_json']}` | Render Schema |")
    hash_rows.append(f"| `tests/` (combined) | `{ih['tests_combined']}` | Test Suite |")
    hash_rows.append(f"| `data/synthetic/out/firs_v5` (combined) | `{ih['firs_v5_combined']}` | Narratives and Keys |")
    hash_rows.append(f"| `data/synthetic/out/firs_v5_contract` (combined) | `{ih['firs_v5_contract_combined']}` | Gold Contracts |")
    hash_rows.append(f"| `contracts/sample_input.txt` | `{ih['sample_input_txt']}` | Golden Input |")
    hash_rows.append(f"| `contracts/v1_1/examples/ai_golden_fir45.json` | `{ih['ai_golden_fir45_json']}` | Golden Reference |")
    hash_rows.append(f"| `run1/` analysis files (combined) | `{output_hashes['run1_combined']}` | Run One Output |")
    hash_rows.append(f"| `run2/` analysis files (combined) | `{output_hashes['run2_combined']}` | Run Two Output |")
    hash_rows.append(f"| `degraded/` analysis files (combined) | `{output_hashes['degraded_combined']}` | Degraded Mode Output |")
    table_q = "\n".join(hash_rows)

    # Table R: Pytest Summary
    ts = metrics["tests_summary"]
    rows_r = []
    for tfile, d in ts["by_file"].items():
        rows_r.append(f"| `{tfile}` | {d['passed']} | {d['failed']} | {d['skipped']} | {d['errors']} |")
    rows_r.append(
        f"| TOTAL | {ts['total_passed']} | {ts['total_failed']} | {ts['total_skipped']} | {ts['total_errors']} |"
    )
    table_r = "\n".join(rows_r)

    failures_line = (
        "None"
        if not ts["failures"]
        else "; ".join(f"`{f['file']}::{f['test']}` ({f['outcome']})" for f in ts["failures"])
    )

    input_bullets = "\n".join(
        [f"  - `ai_pipeline/{mod}` (`SHA-256`: `{ih['ai_pipeline_modules'][mod]}`)" for mod in PIPELINE_MODULES]
        + [
            f"  - `contracts/v1_1/validate.py` (`SHA-256`: `{ih['validate_py']}`)",
            f"  - `contracts/v1_1/ai_output_schema.json` (`SHA-256`: `{ih['ai_output_schema_json']}`)",
            f"  - `contracts/v1_1/graph_render_schema.json` (`SHA-256`: `{ih['graph_render_schema_json']}`)",
            f"  - `tests/` combined (`SHA-256`: `{ih['tests_combined']}`)",
            f"  - `data/synthetic/out/firs_v5` combined (`SHA-256`: `{ih['firs_v5_combined']}`)",
            f"  - `data/synthetic/out/firs_v5_contract` combined (`SHA-256`: `{ih['firs_v5_contract_combined']}`)",
            f"  - `contracts/sample_input.txt` (`SHA-256`: `{ih['sample_input_txt']}`)",
            f"  - `contracts/v1_1/examples/ai_golden_fir45.json` (`SHA-256`: `{ih['ai_golden_fir45_json']}`)",
        ]
    )

    output_bullets = "\n".join([
        f"  - `metrics.json` (`SHA-256`: `{output_hashes['metrics_json']}`)",
        f"  - `pytest_raw.txt` (`SHA-256`: `{output_hashes['pytest_raw_txt']}`)",
        f"  - `golden_analysis.json` (`SHA-256`: `{output_hashes['golden_analysis_json']}`)",
        f"  - `timings_run1.json` (`SHA-256`: `{output_hashes['timings_run1_json']}`)",
        f"  - `timings_run2.json` (`SHA-256`: `{output_hashes['timings_run2_json']}`)",
        f"  - `run1/` combined (`SHA-256`: `{output_hashes['run1_combined']}`)",
        f"  - `run2/` combined (`SHA-256`: `{output_hashes['run2_combined']}`)",
        f"  - `degraded/` combined (`SHA-256`: `{output_hashes['degraded_combined']}`)",
        f"  - `SHA256SUMS.txt` (`SHA-256`: `{output_hashes['sha256sums_txt']}`)",
    ])

    section = f"""<!-- STEP6:BEGIN -->
## Step 6: End-to-End Extraction Pipeline Evaluation

### Results Card
- **Purpose**: Evaluation of the end-to-end multilingual extraction pipeline from raw narrative text using the cached offline transformer model, degraded heuristic mode, negative input validation, and the golden demo paragraph.
- **Exact Command**: `{meta['command']}`
- **Exact Pytest Command**: `{meta['pytest_command']}`
- **Environment**: Python `{meta['python_version_short']}`, PyTorch `{meta['torch_version']}`, Transformers `{meta['transformers_version']}`
- **Input Files**:
{input_bullets}
- **Output Files**:
{output_bullets}
- **Key Numbers**:
{key_numbers}

### Tables

#### Table A: Mention-Level Extraction Performance (Run One)
| Type | Strict P | Strict R | Strict F1 | Strict TP | Strict FP | Strict FN | Lenient P | Lenient R | Lenient F1 | Lenient TP | Lenient FP | Lenient FN |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
{table_a}

#### Table B: Entity-Level Alignment Performance Across Scopes (Run One)
| Scope | Group | Type | P | R | F1 | TP | FP | FN |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
{table_b}

#### Table C: Aligned Person Attribute Agreement (Run One)
| Scope | Aligned Persons | Aliases Matches | Aliases Rate | Father Surface Matches | Father Surface Rate | Role Matches | Role Rate |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
{table_c}

#### Table D: Overall Relation Extraction by Extractor and Label
| Extractor | Evaluation Role | Relation | TP | FP | FN | P | R | F1 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
{table_d}

#### Table E: Relation Extraction Micro Scores by Split and Language
| Extractor | Group Type | Group | TP | FP | FN | P | R | F1 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
{table_e}

#### Table F: Hybrid Relation Origin Counts per Split
| Split | Lexicon Cue | ANAPHORA | ROLE_CUE | STRUCTURE | Total |
| :--- | :--- | :--- | :--- | :--- | :--- |
{table_f}

#### Table G: Dev versus Test Micro Score Comparison
| Extractor | Dev Micro F1 | Test Micro F1 | Diff (Test minus Dev) |
| :--- | :--- | :--- | :--- |
{table_g}

#### Table H: Degraded Mode Entity Alignment (No Model)
| Type | TP | FP | FN | P | R | F1 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
{table_h}

#### Table I: Degraded Mode Relation Micro Scores by Split (No Model)
| Split | TP | FP | FN | P | R | F1 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
{table_i}

#### Table J: Golden Paragraph Entities
| Entity ID | Type | Canonical Name or Value | Aliases | Role | Bank |
| :--- | :--- | :--- | :--- | :--- | :--- |
{table_j}

#### Table K: Golden Paragraph Predicted Relations
| Extractor | Relation | Source | Target | Amount | Trigger | Confidence |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
{table_k}

#### Table L: Golden Paragraph Score Summary
| Extractor | Gold Set | Gold Count | TP | FP | FN | P | R | F1 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
{table_l}

#### Table M: Stage and Total Runtime Latency (Run Two, Milliseconds)
| Stage | Mean (ms) | Percentile (ms) |
| :--- | :--- | :--- |
{table_m}

#### Table N: Bitwise Determinism Comparison Between Runs
| Comparison Scope | Run One SHA-256 | Run Two SHA-256 | Exact Matches | Total Docs | All Identical |
| :--- | :--- | :--- | :--- | :--- | :--- |
{table_n}

#### Table O: Schema Validation and Execution Exception Summary
| Mode | Total Docs | Valid Docs | Exceptions Raised |
| :--- | :--- | :--- | :--- |
{table_o}

#### Table P: Negative Input Exception Classes
| Input Case | Raised Exception | Exception Class |
| :--- | :--- | :--- |
{table_p}

#### Table Q: Module, Schema, Corpus, and Run Digests
| Artifact | SHA-256 Digest | Category |
| :--- | :--- | :--- |
{table_q}

### Test List

#### Table R: Pytest Execution Summary by File
| Test File | Passed | Failed | Skipped | Errors |
| :--- | :--- | :--- | :--- | :--- |
{table_r}

- **Test Failures**: {failures_line}

### Glossary
- strict = matching criterion requiring equal entity category and identical character start and end offsets
- lenient = matching criterion requiring equal entity category and overlapping character boundaries paired greedily by shared length
- entity-level = contract evaluation aligning each predicted entity to at most one reference entity of identical type sharing at least one mention span
- attribute = exact comparison of aliases set, paternal name string, and assigned role on each aligned person pair
- CUE = cue-driven relation extractor requiring explicit multilingual lexical phrases within sentence boundaries
- HYBRID = combined extractor layering wrapped-line sentence splitting, cross-sentence anaphora, role disambiguation, and structural co-occurrence fallbacks atop cue matching
- CONTRAST = baseline extractor emitting every schema-valid entity type pair co-occurring within the same sentence without lexical cues
- first scored = primary evaluation measurement recorded before inspecting held-out aggregates when designing fallback logic
- second look = secondary measurement evaluated after designing fallback rules following inspection of aggregate held-out counts
- explicit subset = golden reference relationships omitting the device ownership claim not stated in the narrative text
- degraded mode = fallback pipeline path replacing transformer inference with deterministic cue-adjacent person heuristics when model usage is disabled or unavailable
- FATHER-surface convention = comparing predicted paternal names against the reference paternal mention surface string across scripts
- nearest-rank percentile = value at the ceiling rank of ninety-five percent over the sorted per-document millisecond runtimes
- negative input suite = boundary inputs covering empty strings, whitespace strings, oversized strings, plain text without entities, and non-string integers

### Design Decisions
- Deterministic separation of timings: Pipeline stage timings are stripped from saved per-document analysis files and stored in sidecar timing logs so run outputs remain bitwise identical across executions.
- Offline transformer isolation: Evaluation enforces local weight loading without network lookups and measures initial model loading once prior to cached per-document runtime measurement.
- Heuristic safety boundaries: Degraded mode restricts heuristic name spans to strict capitalization or Devanagari boundaries adjacent to explicit honorific, alias, or paternal cues so plain non-narrative prose triggers no false entities.
- Conservative short-name merging: Single-token person mentions merge into fuller names only when a unique candidate exists with matching role and zero alias or paternal conflicts.

### Caveats
- the FIRs come from templates by the same generator that fixed the cue vocabulary
- the rules and lists were designed on the train and dev FIRs
- the test split aggregate was seen before the hybrid fallback was designed, so the cue-only result is the first scored and the hybrid result is the second look
- the fallback produced relations only on the test split
- the golden paragraph is a single document
- the structural rules may create wrong relations on text unlike the generated FIRs
- father names are scored against the FATHER mention surface because the gold father_name in contracts for Hindi texts is Latin script
- runtime is a single measurement

### What This Does Not Show
- Real-world station variance: Synthetic narratives omit OCR noise, typographical errors, dialect spelling shifts, and handwritten transcription omissions.
- Cross-document coreference: Pipeline evaluation resolves short names and anaphors within individual documents rather than linking suspects across separate case files.
- Concurrent server throughput: Single-process CPU timings reflect sequential document latency rather than batched serving capacity under concurrent traffic.
- Open-domain generalization: Performance outside the five fixed financial and telecommunication relationship schemas remains untested.
<!-- STEP6:END -->"""
    return section


def main() -> None:
    parser = argparse.ArgumentParser(description="Step 6d: Document end-to-end extraction pipeline.")
    parser.add_argument("--run-id", default="step6_extraction", help="Unique run identifier.")
    args = parser.parse_args()

    today_str = datetime.date.today().isoformat()
    results_dir = REPO_ROOT / "results" / f"{today_str}_{args.run_id}"
    if results_dir.exists():
        raise FileExistsError(f"Results directory already exists: {results_dir}")

    run1_dir = results_dir / "run1"
    run2_dir = results_dir / "run2"
    degraded_dir = results_dir / "degraded"
    run1_dir.mkdir(parents=True, exist_ok=False)
    run2_dir.mkdir(parents=True, exist_ok=False)
    degraded_dir.mkdir(parents=True, exist_ok=False)

    # 2. Run pytest -v across the entire tests folder
    pytest_cmd_list = [sys.executable, "-m", "pytest", "-v", "tests"]
    pytest_cmd_str = "python -m pytest -v tests"
    env = os.environ.copy()
    env["HF_HUB_OFFLINE"] = "1"
    proc = subprocess.run(
        pytest_cmd_list,
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    pytest_raw_text = proc.stdout + ("\n" + proc.stderr if proc.stderr else "")
    pytest_raw_path = results_dir / "pytest_raw.txt"
    pytest_raw_path.write_text(pytest_raw_text, encoding="utf-8")
    if proc.returncode != 0:
        raise RuntimeError(f"Pytest failed with exit code {proc.returncode}; inspect {pytest_raw_path}")

    tests_summary = parse_pytest_summary(pytest_raw_text)

    # Load dataset paths and texts
    firs_dir = REPO_ROOT / "data" / "synthetic" / "out" / "firs_v5"
    contracts_dir = REPO_ROOT / "data" / "synthetic" / "out" / "firs_v5_contract"
    sample_path = REPO_ROOT / "contracts" / "sample_input.txt"
    golden_gold_path = REPO_ROOT / "contracts" / "v1_1" / "examples" / "ai_golden_fir45.json"

    meta = load_doc_meta(firs_dir)
    doc_ids = sorted(meta.keys())
    texts_by_doc = {
        doc_id: (firs_dir / f"{doc_id}.txt").read_text(encoding="utf-8")
        for doc_id in doc_ids
    }
    sample_text = sample_path.read_text(encoding="utf-8")

    # 3a. Cold offline model load timing
    default_model = ner_baseline.MODELS[0]
    t_load0 = time.perf_counter()
    ner_baseline.get_pipeline(default_model)
    model_load_ms = round((time.perf_counter() - t_load0) * 1000.0, 3)

    # 3b. Run 1 (model, offline)
    timings_run1_per_doc: dict[str, dict[str, float]] = {}
    exc_run1: dict[str, int] = {}
    for doc_id in doc_ids:
        try:
            res = analyze_text(texts_by_doc[doc_id], doc_id=doc_id, use_model=True)
            info = copy.deepcopy(res["info"])
            timings_run1_per_doc[doc_id] = info.pop("timings_ms")
            payload = {"doc": res["doc"], "aux": res["aux"], "info": info}
        except Exception as exc:
            cls_name = type(exc).__name__
            exc_run1[cls_name] = exc_run1.get(cls_name, 0) + 1
            payload = {"error": cls_name}
        (run1_dir / f"{doc_id}.analysis.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    # 3c. Run 2 (model, cached offline)
    timings_run2_per_doc: dict[str, dict[str, float]] = {}
    exc_run2: dict[str, int] = {}
    for doc_id in doc_ids:
        try:
            res = analyze_text(texts_by_doc[doc_id], doc_id=doc_id, use_model=True)
            info = copy.deepcopy(res["info"])
            timings_run2_per_doc[doc_id] = info.pop("timings_ms")
            payload = {"doc": res["doc"], "aux": res["aux"], "info": info}
        except Exception as exc:
            cls_name = type(exc).__name__
            exc_run2[cls_name] = exc_run2.get(cls_name, 0) + 1
            payload = {"error": cls_name}
        (run2_dir / f"{doc_id}.analysis.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    # Save timings separately
    timings_run1_path = results_dir / "timings_run1.json"
    timings_run2_path = results_dir / "timings_run2.json"

    # 3d. Golden demo paragraph (real model)
    res_golden = analyze_text(sample_text, doc_id="GOLDEN_DEMO", use_model=True)
    golden_info = copy.deepcopy(res_golden["info"])
    golden_timings = golden_info.pop("timings_ms")
    golden_payload = {"doc": res_golden["doc"], "aux": res_golden["aux"], "info": golden_info}
    golden_out_path = results_dir / "golden_analysis.json"
    golden_out_path.write_text(
        json.dumps(golden_payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    timings_run1_path.write_text(
        json.dumps(
            {
                "model_load_ms": model_load_ms,
                "golden_demo": golden_timings,
                "per_doc": timings_run1_per_doc,
            },
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )
    timings_run2_path.write_text(
        json.dumps(
            {
                "model_load_ms": model_load_ms,
                "per_doc": timings_run2_per_doc,
            },
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )

    # 3e. Degraded mode (use_model=False) on all 100 FIRs
    exc_degraded: dict[str, int] = {}
    for doc_id in doc_ids:
        try:
            res = analyze_text(texts_by_doc[doc_id], doc_id=doc_id, use_model=False)
            info = copy.deepcopy(res["info"])
            info.pop("timings_ms", None)
            payload = {"doc": res["doc"], "aux": res["aux"], "info": info}
        except Exception as exc:
            cls_name = type(exc).__name__
            exc_degraded[cls_name] = exc_degraded.get(cls_name, 0) + 1
            payload = {"error": cls_name}
        (degraded_dir / f"{doc_id}.analysis.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    # 3f. Negative input suite (record exception class names only)
    negative_cases: list[tuple[str, Any]] = [
        ("empty_string", ""),
        ("whitespace", "   \n\t  "),
        ("too_long_5001", "a" * 5001),
        ("no_entities", "Today the weather was calm and sunny all morning."),
        ("non_string_int_42", 42),
    ]
    negative_results: dict[str, dict[str, Any]] = {}
    for lbl, bad_input in negative_cases:
        try:
            analyze_text(bad_input, doc_id=f"NEG_{lbl}", use_model=True)
            negative_results[lbl] = {"raised": False, "exception_class": "None"}
        except Exception as exc:
            negative_results[lbl] = {"raised": True, "exception_class": type(exc).__name__}

    # 4. Reload saved files ONLY to compute every metric
    gold_mentions_raw = load_gold_mentions(firs_dir)
    gold_mentions = {
        d: [m for m in ml if m["type"] in SCORED_MENTION_TYPES]
        for d, ml in gold_mentions_raw.items()
    }
    gold_docs = _load_contract_docs(contracts_dir)

    run1_saved: dict[str, dict[str, Any]] = {}
    run2_saved: dict[str, dict[str, Any]] = {}
    degraded_saved: dict[str, dict[str, Any]] = {}
    exact_byte_matches = 0
    per_file_match: dict[str, bool] = {}

    for doc_id in doc_ids:
        p1 = run1_dir / f"{doc_id}.analysis.json"
        p2 = run2_dir / f"{doc_id}.analysis.json"
        pd = degraded_dir / f"{doc_id}.analysis.json"
        b1 = p1.read_bytes()
        b2 = p2.read_bytes()
        is_eq = (b1 == b2)
        per_file_match[doc_id] = is_eq
        if is_eq:
            exact_byte_matches += 1
        run1_saved[doc_id] = json.loads(b1.decode("utf-8"))
        run2_saved[doc_id] = json.loads(b2.decode("utf-8"))
        degraded_saved[doc_id] = json.loads(pd.read_text(encoding="utf-8"))

    # 4a. Mentions from run1
    pred_mentions_r1: dict[str, list[dict[str, Any]]] = {}
    vehicle_mentions_found = 0
    vehicle_entities_found = 0
    for doc_id in doc_ids:
        m_list, v_m, v_e = extract_mentions_from_analysis(run1_saved[doc_id])
        pred_mentions_r1[doc_id] = m_list
        vehicle_mentions_found += v_m
        vehicle_entities_found += v_e

    ms_all = score_mentions(gold_mentions, pred_mentions_r1)
    mentions_overall = {
        t: {
            "strict": _counts_to_dict(ms_all["by_type"][t]["strict"]),
            "lenient": _counts_to_dict(ms_all["by_type"][t]["lenient"]),
        }
        for t in SCORED_MENTION_TYPES
    }

    # 4b. Entity alignment & attribute scores from run1
    run1_docs = {d: run1_saved[d]["doc"] for d in doc_ids if "doc" in run1_saved[d]}
    rs_r1 = score_relations(gold_docs, run1_docs)
    entities_overall = {
        t: _counts_to_dict(rs_r1["entities"]["by_type"].get(t, {"tp": 0, "fp": 0, "fn": 0}))
        for t in CORE_ENTITY_TYPES
    }
    entities_by_split: dict[str, Any] = {}
    for sp in SPLITS:
        ids = [d for d in doc_ids if meta[d]["split"] == sp]
        rs_sp = score_relations({d: gold_docs[d] for d in ids}, {d: run1_docs[d] for d in ids})
        entities_by_split[sp] = {
            t: _counts_to_dict(rs_sp["entities"]["by_type"].get(t, {"tp": 0, "fp": 0, "fn": 0}))
            for t in CORE_ENTITY_TYPES
        }
    entities_by_language: dict[str, Any] = {}
    for lang in LANGUAGES:
        ids = [d for d in doc_ids if meta[d]["language"].lower() == lang]
        rs_lg = score_relations({d: gold_docs[d] for d in ids}, {d: run1_docs[d] for d in ids})
        entities_by_language[lang] = {
            t: _counts_to_dict(rs_lg["entities"]["by_type"].get(t, {"tp": 0, "fp": 0, "fn": 0}))
            for t in CORE_ENTITY_TYPES
        }

    attributes_metrics = compute_attribute_metrics(gold_docs, run1_docs, meta)

    # 4c. Three relation extractors (CUE, HYBRID, CONTRAST)
    cue_docs: dict[str, dict[str, Any]] = {}
    contrast_docs: dict[str, dict[str, Any]] = {}
    for doc_id in doc_ids:
        txt = texts_by_doc[doc_id]
        base_doc = copy.deepcopy(run1_saved[doc_id]["doc"])
        base_aux = run1_saved[doc_id]["aux"]

        d_cue = copy.deepcopy(base_doc)
        d_cue["relationships"] = extract_relations(txt, d_cue, base_aux)
        cue_docs[doc_id] = d_cue

        d_con = copy.deepcopy(base_doc)
        d_con["relationships"] = run_contrast_relations(txt, d_con, base_aux)
        contrast_docs[doc_id] = d_con

    relations_metrics = {
        "CUE": compute_relation_suite(gold_docs, cue_docs, meta),
        "HYBRID": compute_relation_suite(gold_docs, run1_docs, meta),
        "CONTRAST": compute_relation_suite(gold_docs, contrast_docs, meta),
    }

    dev_vs_test: dict[str, Any] = {}
    for ext in ("CUE", "HYBRID", "CONTRAST"):
        dev_f1 = relations_metrics[ext]["by_split"]["dev"]["micro"]["f1"] or 0.0
        test_f1 = relations_metrics[ext]["by_split"]["test"]["micro"]["f1"] or 0.0
        dev_vs_test[ext] = {
            "dev_micro_f1": dev_f1,
            "test_micro_f1": test_f1,
            "diff_test_minus_dev": round(test_f1 - dev_f1, 6),
        }

    # Relation origin breakdown per split read from saved run1 relationships
    origins: dict[str, dict[str, int]] = {
        sp: {"lexicon_cue": 0, "ANAPHORA": 0, "ROLE_CUE": 0, "STRUCTURE": 0, "total": 0}
        for sp in SPLITS + ("overall",)
    }
    for doc_id in doc_ids:
        sp = meta[doc_id]["split"]
        for rel in run1_docs[doc_id].get("relationships", []):
            bucket = classify_origin(rel.get("trigger", ""))
            for sc in (sp, "overall"):
                origins[sc][bucket] += 1
                origins[sc]["total"] += 1

    # 4d. Degraded mode metrics from saved degraded/*.analysis.json
    degraded_docs = {d: degraded_saved[d]["doc"] for d in doc_ids if "doc" in degraded_saved[d]}
    rs_deg = score_relations(gold_docs, degraded_docs)
    deg_entities = {
        t: _counts_to_dict(rs_deg["entities"]["by_type"].get(t, {"tp": 0, "fp": 0, "fn": 0}))
        for t in CORE_ENTITY_TYPES
    }
    deg_rels: dict[str, Any] = {
        "overall": {"micro": _counts_to_dict(rs_deg["micro"])},
    }
    for sp in SPLITS:
        ids = [d for d in doc_ids if meta[d]["split"] == sp]
        sub_d = score_relations({d: gold_docs[d] for d in ids}, {d: degraded_docs[d] for d in ids})
        deg_rels[sp] = {"micro": _counts_to_dict(sub_d["micro"])}

    # 4e. Golden demo paragraph from saved golden_analysis.json
    golden_loaded = json.loads(golden_out_path.read_text(encoding="utf-8"))
    gold_golden_all7 = json.loads(golden_gold_path.read_text(encoding="utf-8"))
    gold_golden_all7["source_doc_id"] = "GOLDEN_DEMO"

    gold_golden_persons = [e["id"] for e in gold_golden_all7["entities"] if e["type"] == "PERSON"]
    gold_golden_phones = [e["id"] for e in gold_golden_all7["entities"] if e["type"] == "PHONE"]
    excl_src = gold_golden_persons[EXPLICIT_GOLDEN_EXCLUSION_RULE["suspect_index"]]
    excl_tgt = gold_golden_phones[EXPLICIT_GOLDEN_EXCLUSION_RULE["phone_index"]]

    gold_golden_exp6 = copy.deepcopy(gold_golden_all7)
    gold_golden_exp6["relationships"] = [
        r
        for r in gold_golden_all7["relationships"]
        if not (
            r["relation"] == EXPLICIT_GOLDEN_EXCLUSION_RULE["relation"]
            and r["source"] == excl_src
            and r["target"] == excl_tgt
        )
    ]

    g_hyb_doc = copy.deepcopy(golden_loaded["doc"])
    g_aux = golden_loaded["aux"]
    g_cue_doc = copy.deepcopy(g_hyb_doc)
    g_cue_doc["relationships"] = extract_relations(sample_text, g_cue_doc, g_aux)

    g_emap = {e["id"]: (e.get("canonical_name") or e.get("value") or "") for e in g_hyb_doc["entities"]}
    g_rel_rows: list[dict[str, Any]] = []
    for ext_lbl, ext_doc in (("CUE", g_cue_doc), ("HYBRID", g_hyb_doc)):
        for r in ext_doc["relationships"]:
            row_r: dict[str, Any] = {
                "extractor": ext_lbl,
                "relation": r["relation"],
                "source_label": g_emap[r["source"]],
                "target_label": g_emap[r["target"]],
                "trigger": r.get("trigger", ""),
                "confidence": r.get("confidence", 0.0),
            }
            if "amount" in r:
                row_r["amount"] = r["amount"]
            g_rel_rows.append(row_r)

    golden_scores: dict[str, Any] = {}
    for ext_lbl, ext_doc in (("CUE", g_cue_doc), ("HYBRID", g_hyb_doc)):
        golden_scores[ext_lbl] = {}
        for g_key, g_ref in (("all_gold", gold_golden_all7), ("explicit_subset", gold_golden_exp6)):
            sc = score_relations({"GOLDEN_DEMO": g_ref}, {"GOLDEN_DEMO": ext_doc})["micro"]
            d_sc = _counts_to_dict(sc)
            d_sc["gold_count"] = len(g_ref["relationships"])
            golden_scores[ext_lbl][g_key] = d_sc

    # 4f. Latency from saved timings_run2.json
    t2_loaded = json.loads(timings_run2_path.read_text(encoding="utf-8"))
    t1_loaded = json.loads(timings_run1_path.read_text(encoding="utf-8"))
    latency_run2: dict[str, dict[str, float]] = {}
    for st_name in ("model", "postprocess", "names_identifiers", "assemble", "relations", "validate", "total"):
        vals = [float(t2_loaded["per_doc"][d][st_name]) for d in doc_ids]
        latency_run2[st_name] = {
            "mean_ms": round(sum(vals) / len(vals), 3),
            "p95_ms": round(compute_percentile(vals, 95.0), 3),
        }

    # 4g. Validator pass counts on reloaded docs
    def _count_valid(docs_map: dict[str, dict[str, Any]], exc_counts: dict[str, int]) -> dict[str, Any]:
        valid_n = 0
        for d_id in doc_ids:
            if d_id in docs_map:
                try:
                    validate_ai_output(docs_map[d_id])
                    valid_n += 1
                except Exception as exc:
                    c = type(exc).__name__
                    exc_counts[c] = exc_counts.get(c, 0) + 1
        return {
            "total_docs": len(doc_ids),
            "valid_docs": valid_n,
            "exceptions_by_class": exc_counts,
        }

    run2_docs = {d: run2_saved[d]["doc"] for d in doc_ids if "doc" in run2_saved[d]}
    robustness_metrics = {
        "run1": _count_valid(run1_docs, dict(exc_run1)),
        "run2": _count_valid(run2_docs, dict(exc_run2)),
        "degraded": _count_valid(degraded_docs, dict(exc_degraded)),
        "negative_inputs": negative_results,
    }

    # 4h. Component & dataset hashes
    ai_mod_hashes = {
        mod: compute_sha256(REPO_ROOT / "ai_pipeline" / mod)
        for mod in PIPELINE_MODULES
    }
    test_py_files = sorted(
        (p for p in (REPO_ROOT / "tests").rglob("*.py") if p.is_file()),
        key=lambda p: p.relative_to(REPO_ROOT).as_posix(),
    )
    firs_v5_files = [
        p for p in firs_dir.iterdir()
        if p.is_file() and p.name.startswith("FIR_") and (p.name.endswith(".txt") or p.name.endswith(".json"))
    ]
    contracts_files = [
        p for p in contracts_dir.iterdir()
        if p.is_file() and p.name.endswith(".contract.json")
    ]
    input_hashes = {
        "ai_pipeline_modules": ai_mod_hashes,
        "validate_py": compute_sha256(REPO_ROOT / "contracts" / "v1_1" / "validate.py"),
        "ai_output_schema_json": compute_sha256(REPO_ROOT / "contracts" / "v1_1" / "ai_output_schema.json"),
        "graph_render_schema_json": compute_sha256(REPO_ROOT / "contracts" / "v1_1" / "graph_render_schema.json"),
        "tests_combined": compute_combined_sha256(test_py_files, base_dir=REPO_ROOT / "tests"),
        "firs_v5_combined": compute_combined_sha256(firs_v5_files),
        "firs_v5_contract_combined": compute_combined_sha256(contracts_files),
        "sample_input_txt": compute_sha256(sample_path),
        "ai_golden_fir45_json": compute_sha256(golden_gold_path),
    }

    run1_files = [run1_dir / f"{d}.analysis.json" for d in doc_ids]
    run2_files = [run2_dir / f"{d}.analysis.json" for d in doc_ids]
    degraded_files = [degraded_dir / f"{d}.analysis.json" for d in doc_ids]
    run1_combined_hash = compute_combined_sha256(run1_files)
    run2_combined_hash = compute_combined_sha256(run2_files)
    degraded_combined_hash = compute_combined_sha256(degraded_files)

    metrics: dict[str, Any] = {
        "meta": {
            "run_id": args.run_id,
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "python_version": sys.version,
            "python_version_short": platform.python_version(),
            "torch_version": torch.__version__,
            "transformers_version": transformers.__version__,
            "model_name": default_model,
            "command": f"python scripts/report/step6_extraction.py --run-id {args.run_id}",
            "pytest_command": pytest_cmd_str,
        },
        "input_hashes": input_hashes,
        "determinism": {
            "total_docs": len(doc_ids),
            "exact_matches": exact_byte_matches,
            "all_match": exact_byte_matches == len(doc_ids),
            "run1_combined_sha256": run1_combined_hash,
            "run2_combined_sha256": run2_combined_hash,
            "per_file_match": per_file_match,
        },
        "mentions": {
            "overall": mentions_overall,
            "vehicle_mentions_found": vehicle_mentions_found,
            "vehicle_entities_found": vehicle_entities_found,
        },
        "entities": {
            "overall": entities_overall,
            "by_split": entities_by_split,
            "by_language": entities_by_language,
        },
        "attributes": attributes_metrics,
        "relations": relations_metrics,
        "origins": origins,
        "dev_vs_test": dev_vs_test,
        "degraded": {
            "entities": deg_entities,
            "relations": deg_rels,
        },
        "golden": {
            "entities": golden_loaded["doc"]["entities"],
            "relationships": g_rel_rows,
            "scores": golden_scores,
        },
        "latency": {
            "model_load_ms": t1_loaded["model_load_ms"],
            "run2": latency_run2,
        },
        "robustness": robustness_metrics,
        "tests_summary": tests_summary,
    }

    metrics_file = results_dir / "metrics.json"
    metrics_file.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")

    # Reload metrics.json strictly before markdown generation
    reloaded_metrics = json.loads(metrics_file.read_text(encoding="utf-8"))

    # 5. Write SHA256SUMS.txt covering all output artifacts and mark read-only
    all_output_files = sorted(
        [
            pytest_raw_path,
            golden_out_path,
            timings_run1_path,
            timings_run2_path,
            metrics_file,
        ]
        + run1_files
        + run2_files
        + degraded_files,
        key=lambda p: p.relative_to(results_dir).as_posix(),
    )
    sha_lines: list[str] = []
    for fp in all_output_files:
        rel_str = fp.relative_to(results_dir).as_posix()
        sha_lines.append(f"{compute_sha256(fp)}  {rel_str}")
    sha256sums_path = results_dir / "SHA256SUMS.txt"
    sha256sums_path.write_text("\n".join(sha_lines) + "\n", encoding="utf-8")

    output_hashes = {
        "metrics_json": compute_sha256(metrics_file),
        "pytest_raw_txt": compute_sha256(pytest_raw_path),
        "golden_analysis_json": compute_sha256(golden_out_path),
        "timings_run1_json": compute_sha256(timings_run1_path),
        "timings_run2_json": compute_sha256(timings_run2_path),
        "run1_combined": run1_combined_hash,
        "run2_combined": run2_combined_hash,
        "degraded_combined": degraded_combined_hash,
        "sha256sums_txt": compute_sha256(sha256sums_path),
    }

    for fp in all_output_files + [sha256sums_path]:
        os.chmod(fp, stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)

    # 6. Build and validate Step 6 markdown block before updating docs/RESULTS.md
    step6_md = build_markdown_section(reloaded_metrics, output_hashes)
    assert_tables_match_metrics(step6_md, reloaded_metrics)
    validate_markdown_rules(step6_md)

    docs_file = REPO_ROOT / "docs" / "RESULTS.md"
    existing_doc = docs_file.read_text(encoding="utf-8")

    def _block_hashes(content: str) -> dict[str, str]:
        hashes_out: dict[str, str] = {}
        for bname in ("STEP1", "STEP2", "STEP5A", "STEP5B"):
            m = re.search(rf"<!-- {bname}:BEGIN -->.*?<!-- {bname}:END -->", content, re.DOTALL)
            if not m:
                raise ValueError(f"Missing expected {bname} block in docs/RESULTS.md")
            hashes_out[bname] = hashlib.sha256(m.group(0).encode("utf-8")).hexdigest()
        return hashes_out

    hashes_before = _block_hashes(existing_doc)

    step6_rx = re.compile(r"<!-- STEP6:BEGIN -->.*?<!-- STEP6:END -->", re.DOTALL)
    if step6_rx.search(existing_doc):
        new_doc = step6_rx.sub(lambda _: step6_md, existing_doc)
    else:
        marker_end = "<!-- STEP5B:END -->"
        parts = existing_doc.split(marker_end)
        if len(parts) != 2:
            raise ValueError("Could not uniquely locate <!-- STEP5B:END --> in docs/RESULTS.md")
        new_doc = parts[0] + marker_end + "\n\n" + step6_md + ("\n" + parts[1].lstrip("\n") if parts[1].strip() else "\n")

    hashes_after = _block_hashes(new_doc)
    for bname in ("STEP1", "STEP2", "STEP5A", "STEP5B"):
        if hashes_before[bname] != hashes_after[bname]:
            raise ValueError(f"FATAL: {bname} block digest altered during RESULTS.md update!")

    docs_file.write_text(new_doc, encoding="utf-8")

    print(f"New folder: {results_dir}")
    print(f"Determinism: {exact_byte_matches}/{len(doc_ids)} exact byte matches")
    for bname in ("STEP1", "STEP2", "STEP5A", "STEP5B"):
        print(f"{bname}_BEFORE: {hashes_before[bname]}")
        print(f"{bname}_AFTER:  {hashes_after[bname]}")


if __name__ == "__main__":
    main()
