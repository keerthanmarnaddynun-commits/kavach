#!/usr/bin/env python3
"""
Step 6b: Like-for-like pipeline measurement on the 20 test FIRs for baseline comparison.
Runs the shipped extraction pipeline (offline) on the synthetic test split (FIR_81 to FIR_100)
and evaluates:
  (a) Names subset (PERSON, ALIAS, FATHER mapped to NAME) identically to Step 5b (spaCy/Flair).
  (b) Identifiers subset (PHONE, IMEI, ACCOUNT, AMOUNT) identically to Step 5a (Regex baseline).
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any

# Force offline execution for Hugging Face
os.environ["HF_HUB_OFFLINE"] = "1"

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai_pipeline.pipeline import analyze_text
from ai_pipeline.scoring import (
    load_doc_meta,
    load_gold_mentions,
    prf,
    score_mentions,
)
from ai_pipeline.ner_baseline import gold_for_mode, preds_for_mode
from scripts.report.step6_extraction import extract_mentions_from_analysis


def compute_sha256(filepath: Path) -> str:
    """Compute SHA-256 digest of a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def run_test_split_evaluation(run_id: str = "step6b_test_split_r1") -> Path:
    firs_dir = REPO_ROOT / "data" / "synthetic" / "out" / "firs_v5"
    index_file = firs_dir / "index.json"

    # Identify test FIRs from index
    doc_meta = load_doc_meta(firs_dir)
    test_doc_ids = sorted([d for d, m in doc_meta.items() if m.get("split") == "test"])
    if len(test_doc_ids) != 20:
        raise ValueError(f"Expected exactly 20 test FIRs, found {len(test_doc_ids)}: {test_doc_ids}")

    # Results directory
    today_str = datetime.date.today().isoformat()
    results_dir = REPO_ROOT / "results" / f"{today_str}_{run_id}"
    results_dir.mkdir(parents=True, exist_ok=True)

    # 1. Run pipeline on the 20 test FIRs
    pipeline_mentions: dict[str, list[dict[str, Any]]] = {}
    analysis_outputs: dict[str, Any] = {}

    for doc_id in test_doc_ids:
        txt_path = firs_dir / f"{doc_id}.txt"
        text = txt_path.read_text(encoding="utf-8")
        res = analyze_text(text, doc_id=doc_id, use_model=True)
        mentions, _, _ = extract_mentions_from_analysis({"doc": res["doc"], "aux": res["aux"]})
        pipeline_mentions[doc_id] = mentions
        analysis_outputs[doc_id] = {
            "entities": res["doc"].get("entities", []),
            "aux": res["aux"],
            "mentions": mentions,
        }

    # Save per-doc predictions
    preds_file = results_dir / "predictions.json"
    with open(preds_file, "w", encoding="utf-8") as f:
        json.dump(analysis_outputs, f, indent=2, sort_keys=True)

    # 2. Ground truth
    all_gold = load_gold_mentions(firs_dir)
    test_gold = {d: all_gold[d] for d in test_doc_ids}

    # Gold counts by type
    gold_by_type: dict[str, int] = {}
    for d in test_doc_ids:
        for m in test_gold[d]:
            t = m["type"]
            gold_by_type[t] = gold_by_type.get(t, 0) + 1

    total_gold_test = sum(gold_by_type.values())
    name_types = ("PERSON", "ALIAS", "FATHER")
    id_types = ("PHONE", "IMEI", "ACCOUNT", "AMOUNT")

    gold_names_count = sum(gold_by_type.get(t, 0) for t in name_types)
    gold_id_count = sum(gold_by_type.get(t, 0) for t in id_types)

    # Validate gold counts against baselines
    if gold_names_count != 132:
        raise ValueError(f"Gold names count mismatch: expected 132, got {gold_names_count}")
    if total_gold_test != 243:
        raise ValueError(f"Total test gold mentions mismatch: expected 243, got {total_gold_test}")

    # (a) Evaluate Names (identical to step5b ALL_NAMES mode)
    pred_names = {
        d: [m for m in pipeline_mentions[d] if m["type"] in name_types]
        for d in test_doc_ids
    }
    g_all_names = gold_for_mode(test_gold, "ALL_NAMES")
    p_all_names = preds_for_mode(pred_names, "ALL_NAMES")
    res_names = score_mentions(g_all_names, p_all_names)

    st_n = res_names["micro"]["strict"]
    lt_n = res_names["micro"]["lenient"]
    p_n, r_n, f1_n = prf(st_n)
    p_n_lt, r_n_lt, f1_n_lt = prf(lt_n)

    names_eval = {
        "mode": "ALL_NAMES",
        "types": list(name_types),
        "gold_count": st_n["tp"] + st_n["fn"],
        "strict": {
            "tp": st_n["tp"],
            "fp": st_n["fp"],
            "fn": st_n["fn"],
            "precision": round(p_n, 4),
            "recall": round(r_n, 4),
            "f1": round(f1_n, 4),
        },
        "lenient": {
            "tp": lt_n["tp"],
            "fp": lt_n["fp"],
            "fn": lt_n["fn"],
            "precision": round(p_n_lt, 4),
            "recall": round(r_n_lt, 4),
            "f1": round(f1_n_lt, 4),
        },
    }

    # (b) Evaluate Identifiers (restricted to identifier types targeted by regex: PHONE, IMEI, ACCOUNT, AMOUNT)
    gold_ids = {
        d: [m for m in test_gold[d] if m["type"] in id_types]
        for d in test_doc_ids
    }
    pred_ids = {
        d: [m for m in pipeline_mentions[d] if m["type"] in id_types]
        for d in test_doc_ids
    }
    res_ids = score_mentions(gold_ids, pred_ids)

    st_i = res_ids["micro"]["strict"]
    lt_i = res_ids["micro"]["lenient"]
    p_i, r_i, f1_i = prf(st_i)
    p_i_lt, r_i_lt, f1_i_lt = prf(lt_i)

    # Individual identifier types for pipeline
    per_id_type = {}
    for it in id_types:
        if it in res_ids:
            st = res_ids[it]["strict"]
            p, r, f = prf(st)
            per_id_type[it] = {
                "tp": st["tp"],
                "fp": st["fp"],
                "fn": st["fn"],
                "precision": round(p, 4),
                "recall": round(r, 4),
                "f1": round(f, 4),
                "gold": st["tp"] + st["fn"],
            }

    identifiers_eval = {
        "types": list(id_types),
        "gold_count": st_i["tp"] + st_i["fn"],  # 111 across targeted identifier mentions
        "strict": {
            "tp": st_i["tp"],
            "fp": st_i["fp"],
            "fn": st_i["fn"],
            "precision": round(p_i, 4),
            "recall": round(r_i, 4),
            "f1": round(f1_i, 4),
        },
        "lenient": {
            "tp": lt_i["tp"],
            "fp": lt_i["fp"],
            "fn": lt_i["fn"],
            "precision": round(p_i_lt, 4),
            "recall": round(r_i_lt, 4),
            "f1": round(f1_i_lt, 4),
        },
        "by_type": per_id_type,
    }

    # Re-derive Regex baseline numbers restricted to targeted identifier types from step5a_baseline_r4
    s5a_path = REPO_ROOT / "results" / "2026-11-23_step5a_baseline_r4" / "metrics.json"
    regex_per_type = {}
    if s5a_path.is_file():
        with open(s5a_path, "r", encoding="utf-8") as f:
            s5a_data = json.load(f)
        s5a_test_split = s5a_data.get("rules_evaluation", {}).get("by_split", {}).get("test", {})
        for it in id_types:
            if it in s5a_test_split:
                st = s5a_test_split[it]["strict"]
                regex_per_type[it] = {
                    "tp": st["tp"],
                    "fp": st["fp"],
                    "fn": st["fn"],
                    "precision": round(st["precision"], 4),
                    "recall": round(st["recall"], 4),
                    "f1": round(st["f1"], 4),
                    "gold": st["tp"] + st["fn"],
                }

    reg_tp = sum(v["tp"] for v in regex_per_type.values())
    reg_fp = sum(v["fp"] for v in regex_per_type.values())
    reg_fn = sum(v["fn"] for v in regex_per_type.values())
    reg_p, reg_r, reg_f1 = prf({"tp": reg_tp, "fp": reg_fp, "fn": reg_fn})
    regex_eval = {
        "types": list(id_types),
        "gold_count": reg_tp + reg_fn,
        "strict": {
            "tp": reg_tp,
            "fp": reg_fp,
            "fn": reg_fn,
            "precision": round(reg_p, 4),
            "recall": round(reg_r, 4),
            "f1": round(reg_f1, 4),
        },
        "by_type": regex_per_type,
    }

    # Track input hashes
    pipeline_modules = [
        "pipeline.py",
        "identifiers.py",
        "names.py",
        "assemble.py",
        "relations.py",
        "scoring.py",
        "normalizer.py",
        "validators.py",
    ]
    input_hashes = {
        m: compute_sha256(REPO_ROOT / "ai_pipeline" / m)
        for m in pipeline_modules
    }
    input_hashes["firs_v5_index"] = compute_sha256(index_file)

    metrics_payload = {
        "meta": {
            "run_id": run_id,
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "command": f"python scripts/report/step6b_baseline_comparison.py --run-id {run_id}",
            "python_version": sys.version,
            "python_version_short": "3.11.9",
            "test_split_firs_count": len(test_doc_ids),
            "test_split_firs": test_doc_ids,
        },
        "input_hashes": input_hashes,
        "dataset_counts": {
            "total_test_firs": len(test_doc_ids),
            "total_gold_mentions": total_gold_test,
            "gold_names_count": gold_names_count,
            "gold_identifiers_count": gold_id_count,
            "by_type": gold_by_type,
        },
        "names_evaluation": names_eval,
        "identifiers_evaluation": identifiers_eval,
        "regex_identifiers_evaluation": regex_eval,
    }

    metrics_file = results_dir / "metrics.json"
    with open(metrics_file, "w", encoding="utf-8") as f:
        json.dump(metrics_payload, f, indent=2, sort_keys=True)
        f.write("\n")

    # Write SHA256SUMS.txt
    sums_file = results_dir / "SHA256SUMS.txt"
    with open(sums_file, "w", encoding="utf-8") as f:
        for p in [metrics_file, preds_file]:
            h = compute_sha256(p)
            f.write(f"{h}  {p.name}\n")

    print(f"Results written to {results_dir}")
    print(f"  Names (Pipeline): P={names_eval['strict']['precision']:.4f}, R={names_eval['strict']['recall']:.4f}, F1={names_eval['strict']['f1']:.4f} (Gold={names_eval['gold_count']})")
    print(f"  Identifiers Overall (Pipeline): P={identifiers_eval['strict']['precision']:.4f}, R={identifiers_eval['strict']['recall']:.4f}, F1={identifiers_eval['strict']['f1']:.4f} (Gold={identifiers_eval['gold_count']})")
    print(f"  Identifiers Overall (Regex):    P={regex_eval['strict']['precision']:.4f}, R={regex_eval['strict']['recall']:.4f}, F1={regex_eval['strict']['f1']:.4f} (Gold={regex_eval['gold_count']})")
    for it in id_types:
        p_info = identifiers_eval["by_type"].get(it, {})
        r_info = regex_eval["by_type"].get(it, {})
        print(f"    {it:8s} | Pipeline: TP={p_info.get('tp',0)} FP={p_info.get('fp',0)} FN={p_info.get('fn',0)} P={p_info.get('precision',0):.4f} R={p_info.get('recall',0):.4f} F1={p_info.get('f1',0):.4f} Gold={p_info.get('gold',0)}")
        print(f"             | Regex:    TP={r_info.get('tp',0)} FP={r_info.get('fp',0)} FN={r_info.get('fn',0)} P={r_info.get('precision',0):.4f} R={r_info.get('recall',0):.4f} F1={r_info.get('f1',0):.4f} Gold={r_info.get('gold',0)}")
    return results_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Step 6b: Like-for-like pipeline measurement on test split.")
    parser.add_argument("--run-id", default="step6b_test_split_r1", help="Run identifier.")
    args = parser.parse_args()

    run_test_split_evaluation(run_id=args.run_id)


if __name__ == "__main__":
    main()
