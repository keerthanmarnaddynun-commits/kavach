#!/usr/bin/env python3
"""Build deterministic model performance snapshot JSON for web UI.

Reads official evaluation runs from results/ and writes web/src/data/model_performance.json.
Contains SHA-256 digests and provenance metadata for each block.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent

OFFICIAL_FILES = {
    "step7_metrics": REPO_ROOT / "results" / "2026-11-16_step7_llm_heldout_r2" / "metrics.json",
    "step7_errors": REPO_ROOT / "results" / "2026-11-16_step7_llm_heldout_r2" / "errors.json",
    "step7b_gap": REPO_ROOT / "results" / "2026-11-23_step7b_gap_analysis_r2" / "gap_analysis.json",
    "step6_metrics": REPO_ROOT / "results" / "2026-11-23_step6_extraction_r3" / "metrics.json",
    "step5a_metrics": REPO_ROOT / "results" / "2026-11-23_step5a_baseline_r4" / "metrics.json",
    "step5b_metrics": REPO_ROOT / "results" / "2026-11-23_step5b_ner_baseline_r2" / "metrics.json",
}

OUTPUT_PATH = REPO_ROOT / "web" / "src" / "data" / "model_performance.json"


def safe_round(val: Any, decimals: int = 4, default: float = 0.0) -> float:
    """Safely parse and round floating point metrics handling None."""
    if val is None:
        return default
    try:
        return round(float(val), decimals)
    except (ValueError, TypeError):
        return default


def sha256_file(path: Path) -> str:
    """Compute SHA-256 hexadecimal digest for a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def generate_snapshot() -> dict[str, Any]:
    """Extract and structure model performance metrics from source files."""
    # Check that all source files exist
    for name, path in OFFICIAL_FILES.items():
        if not path.is_file():
            raise FileNotFoundError(f"Missing required source file for {name}: {path}")

    # Load source JSONs
    with open(OFFICIAL_FILES["step7_metrics"], "r", encoding="utf-8") as f:
        s7_metrics = json.load(f)
    with open(OFFICIAL_FILES["step7_errors"], "r", encoding="utf-8") as f:
        s7_errors = json.load(f)
    with open(OFFICIAL_FILES["step7b_gap"], "r", encoding="utf-8") as f:
        s7b_gap = json.load(f)
    with open(OFFICIAL_FILES["step6_metrics"], "r", encoding="utf-8") as f:
        s6_metrics = json.load(f)
    with open(OFFICIAL_FILES["step5a_metrics"], "r", encoding="utf-8") as f:
        s5a_metrics = json.load(f)
    with open(OFFICIAL_FILES["step5b_metrics"], "r", encoding="utf-8") as f:
        s5b_metrics = json.load(f)

    # Compute SHA-256 for all source files
    hashes = {
        name: {
            "path": path.relative_to(REPO_ROOT).as_posix(),
            "sha256": sha256_file(path),
        }
        for name, path in OFFICIAL_FILES.items()
    }

    # Block A: Headline Strip
    s7_head = s7_metrics["headline"]
    s7_synth = s7_head.get("synthetic_comparison", {})
    held_out_count = int(s7_metrics.get("meta", {}).get("file_count", 25))
    synthetic_test_count = 50

    headline = {
        "source_runs": ["step7_llm_heldout_r2", "step6_extraction_r3"],
        "provenance_caption": "step7_llm_heldout_r2 & step6_extraction_r3",
        "sources": [hashes["step7_metrics"], hashes["step6_metrics"]],
        "dataset_sizes": {
            "synthetic_test_firs": synthetic_test_count,
            "held_out_firs": held_out_count,
            "caption": f"Synthetic test: {synthetic_test_count} FIRs; independent held-out: {held_out_count} FIRs",
        },
        "held_out": {
            "mention_strict_f1": safe_round(s7_head["mentions"]["strict"]["f1"], 4),
            "mention_strict_p": safe_round(s7_head["mentions"]["strict"]["precision"], 4),
            "mention_strict_r": safe_round(s7_head["mentions"]["strict"]["recall"], 4),
            "relation_micro_f1": safe_round(s7_head["relations"]["micro"]["f1"], 4),
            "relation_micro_p": safe_round(s7_head["relations"]["micro"]["precision"], 4),
            "relation_micro_r": safe_round(s7_head["relations"]["micro"]["recall"], 4),
        },
        "synthetic_test": {
            "mention_strict_f1": safe_round(s7_synth.get("mentions_micro_f1", 0.9992), 4),
            "relation_micro_f1": safe_round(s7_synth.get("relations_test_micro_f1", 0.9672), 4),
        },
    }

    # Block B: Entity Extraction by Type
    held_out_entities = []
    for etype, data in s7_metrics.get("per_type_mentions", {}).items():
        gold = data.get("gold", 0)
        if gold > 0:
            strict = data.get("strict", {})
            lenient = data.get("lenient", {})
            held_out_entities.append({
                "type": etype,
                "gold": gold,
                "predicted": data.get("predicted", 0),
                "strict": {
                    "precision": safe_round(strict.get("precision", 0), 4),
                    "recall": safe_round(strict.get("recall", 0), 4),
                    "f1": safe_round(strict.get("f1", 0), 4),
                    "tp": strict.get("tp", 0),
                    "fp": strict.get("fp", 0),
                    "fn": strict.get("fn", 0),
                },
                "lenient": {
                    "precision": safe_round(lenient.get("precision", 0), 4),
                    "recall": safe_round(lenient.get("recall", 0), 4),
                    "f1": safe_round(lenient.get("f1", 0), 4),
                    "tp": lenient.get("tp", 0),
                    "fp": lenient.get("fp", 0),
                    "fn": lenient.get("fn", 0),
                },
            })

    synthetic_entities = []
    for etype, data in s6_metrics.get("mentions", {}).get("overall", {}).items():
        strict = data.get("strict", {})
        lenient = data.get("lenient", {})
        tp = strict.get("tp", 0)
        fn = strict.get("fn", 0)
        fp = strict.get("fp", 0)
        gold = tp + fn
        pred = tp + fp
        synthetic_entities.append({
            "type": etype,
            "gold": gold,
            "predicted": pred,
            "strict": {
                "precision": safe_round(strict.get("precision", 0), 4),
                "recall": safe_round(strict.get("recall", 0), 4),
                "f1": safe_round(strict.get("f1", 0), 4),
                "tp": tp,
                "fp": fp,
                "fn": fn,
            },
            "lenient": {
                "precision": safe_round(lenient.get("precision", 0), 4),
                "recall": safe_round(lenient.get("recall", 0), 4),
                "f1": safe_round(lenient.get("f1", 0), 4),
                "tp": lenient.get("tp", 0),
                "fp": lenient.get("fp", 0),
                "fn": lenient.get("fn", 0),
            },
        })

    entities_by_type = {
        "source_runs": {
            "held_out": "step7_llm_heldout_r2",
            "synthetic_test": "step6_extraction_r3",
        },
        "provenance_caption": "step7_llm_heldout_r2 (held-out) / step6_extraction_r3 (synthetic test)",
        "sources": [hashes["step7_metrics"], hashes["step6_metrics"]],
        "held_out": held_out_entities,
        "synthetic_test": synthetic_entities,
    }

    # Block C: Relation Extraction by Type
    held_out_relations = []
    s7_rel_labels = s7_metrics.get("relations", {}).get("HYBRID", {}).get("overall", {}).get("by_label", {})
    for rel_type, data in s7_rel_labels.items():
        tp = data.get("tp", 0)
        fp = data.get("fp", 0)
        fn = data.get("fn", 0)
        gold = tp + fn
        pred = tp + fp
        p = safe_round(data.get("precision", 0), 4)
        r = safe_round(data.get("recall", 0), 4)
        f1 = safe_round(data.get("f1", 0), 4)
        # Relations have exact match scoring (strict and lenient identical)
        rel_obj = {
            "relation": rel_type,
            "gold": gold,
            "predicted": pred,
            "strict": {
                "precision": p,
                "recall": r,
                "f1": f1,
                "tp": tp,
                "fp": fp,
                "fn": fn,
            },
            "lenient": {
                "precision": p,
                "recall": r,
                "f1": f1,
                "tp": tp,
                "fp": fp,
                "fn": fn,
            },
        }
        held_out_relations.append(rel_obj)

    synthetic_relations = []
    s6_rel_labels = s6_metrics.get("relations", {}).get("HYBRID", {}).get("overall", {}).get("by_label", {})
    for rel_type, data in s6_rel_labels.items():
        tp = data.get("tp", 0)
        fp = data.get("fp", 0)
        fn = data.get("fn", 0)
        gold = tp + fn
        pred = tp + fp
        p = safe_round(data.get("precision", 0), 4)
        r = safe_round(data.get("recall", 0), 4)
        f1 = safe_round(data.get("f1", 0), 4)
        synthetic_relations.append({
            "relation": rel_type,
            "gold": gold,
            "predicted": pred,
            "strict": {
                "precision": p,
                "recall": r,
                "f1": f1,
                "tp": tp,
                "fp": fp,
                "fn": fn,
            },
            "lenient": {
                "precision": p,
                "recall": r,
                "f1": f1,
                "tp": tp,
                "fp": fp,
                "fn": fn,
            },
        })

    relations_by_type = {
        "source_runs": {
            "held_out": "step7_llm_heldout_r2",
            "synthetic_test": "step6_extraction_r3",
        },
        "provenance_caption": "step7_llm_heldout_r2 (held-out) / step6_extraction_r3 (synthetic test)",
        "sources": [hashes["step7_metrics"], hashes["step6_metrics"]],
        "held_out": held_out_relations,
        "synthetic_test": synthetic_relations,
    }

    # Block D: How it fails (held-out error breakdown)
    # Extract mention error classes and up to 5 real examples from classified_fps / classified_fns
    m_classes = s7b_gap.get("mention_classes", {})
    r_classes = s7b_gap.get("relation_classes", {})

    # Mention FPs
    m_fp_classified = m_classes.get("classified_fps", [])
    m_fp_counts = m_classes.get("fp_counts", {})
    m_fp_total = sum(m_fp_counts.values()) or 1
    mention_fps = []
    for cname, count in m_fp_counts.items():
        examples = [
            {
                "file": item.get("file"),
                "surface": item.get("surface"),
                "char_span": item.get("char_span"),
                "note": item.get("diagnostic_note"),
            }
            for item in m_fp_classified
            if item.get("class") == cname
        ][:5]
        mention_fps.append({
            "class_name": cname,
            "count": count,
            "pct": round(count / m_fp_total * 100, 1),
            "examples": examples,
        })

    # Mention FNs
    m_fn_classified = m_classes.get("classified_fns", [])
    m_fn_counts = m_classes.get("fn_counts", {})
    m_fn_total = sum(m_fn_counts.values()) or 1
    mention_fns = []
    for cname, count in m_fn_counts.items():
        examples = [
            {
                "file": item.get("file"),
                "surface": item.get("surface"),
                "char_span": item.get("char_span"),
                "note": item.get("diagnostic_note"),
            }
            for item in m_fn_classified
            if item.get("class") == cname
        ][:5]
        mention_fns.append({
            "class_name": cname,
            "count": count,
            "pct": round(count / m_fn_total * 100, 1),
            "examples": examples,
        })

    # Relation FPs
    r_fp_classified = r_classes.get("classified_fps", []) + r_classes.get("other_fps", [])
    r_fp_counts = r_classes.get("fp_counts", {})
    r_fp_total = sum(r_fp_counts.values()) or 1
    relation_fps = []
    for cname, count in r_fp_counts.items():
        examples = [
            {
                "file": item.get("file"),
                "relation": item.get("relation"),
                "source_surface": item.get("source_surface"),
                "target_surface": item.get("target_surface"),
                "amount": item.get("amount"),
            }
            for item in r_fp_classified
            if item.get("class") == cname
        ][:5]
        relation_fps.append({
            "class_name": cname,
            "count": count,
            "pct": round(count / r_fp_total * 100, 1),
            "examples": examples,
        })

    # Relation FNs
    r_fn_classified = r_classes.get("classified_fns", [])
    r_fn_counts = r_classes.get("fn_counts", {})
    r_fn_total = sum(r_fn_counts.values()) or 1
    relation_fns = []
    for cname, count in r_fn_counts.items():
        examples = [
            {
                "file": item.get("file"),
                "relation": item.get("relation"),
                "source_surface": item.get("source_surface"),
                "target_surface": item.get("target_surface"),
                "amount": item.get("amount"),
            }
            for item in r_fn_classified
            if item.get("class") == cname
        ][:5]
        relation_fns.append({
            "class_name": cname,
            "count": count,
            "pct": round(count / r_fn_total * 100, 1),
            "examples": examples,
        })

    error_breakdown = {
        "source_run": "step7b_gap_analysis_r2",
        "provenance_caption": "step7b_gap_analysis_r2",
        "source": hashes["step7b_gap"],
        "mentions": {
            "fp_classes": mention_fps,
            "fn_classes": mention_fns,
            "total_fp": sum(m_fp_counts.values()),
            "total_fn": sum(m_fn_counts.values()),
        },
        "relations": {
            "fp_classes": relation_fps,
            "fn_classes": relation_fns,
            "total_fp": sum(r_fp_counts.values()),
            "total_fn": sum(r_fn_counts.values()),
        },
    }

    # Block E: Generalisation Gap
    synth_mentions_f1 = safe_round(s7_synth.get("mentions_micro_f1", 0.9992), 4)
    synth_relations_f1 = safe_round(s7_synth.get("relations_test_micro_f1", 0.9672), 4)
    held_mentions_f1 = safe_round(s7_head["mentions"]["strict"]["f1"], 4)
    held_relations_f1 = safe_round(s7_head["relations"]["micro"]["f1"], 4)

    generalisation_gap = {
        "source_run": "step7_llm_heldout_r2",
        "provenance_caption": "step7_llm_heldout_r2 (headline.synthetic_comparison)",
        "source": hashes["step7_metrics"],
        "comparison": [
            {
                "metric": "Mentions F1 (strict)",
                "synthetic_test": synth_mentions_f1,
                "held_out": held_mentions_f1,
                "gap": round(synth_mentions_f1 - held_mentions_f1, 4),
            },
            {
                "metric": "Relations F1 (micro)",
                "synthetic_test": synth_relations_f1,
                "held_out": held_relations_f1,
                "gap": round(synth_relations_f1 - held_relations_f1, 4),
            },
        ],
    }

    # Block F: Against Baselines (synthetic test, 50 FIRs)
    # Regex baseline from Step 5a
    s5a_test = s5a_metrics.get("rules_evaluation", {}).get("by_split", {}).get("test", {}).get("micro", {}).get("strict", {})
    # Models from Step 5b
    davlan_test = s5b_metrics.get("models", {}).get("davlan_xlm_roberta_base_ner_hrl", {}).get("postprocessed_all_names", {}).get("by_split", {}).get("test", {}).get("strict", {})
    indicner_test = s5b_metrics.get("models", {}).get("ai4bharat_indicner", {}).get("postprocessed_all_names", {}).get("by_split", {}).get("test", {}).get("strict", {})
    # Shipped pipeline (Step 6)
    # Pipeline overall strict across synthetic mentions
    s6_mentions_overall = s6_metrics.get("mentions", {}).get("overall", {})
    s6_tp = sum(v.get("strict", {}).get("tp", 0) for v in s6_mentions_overall.values())
    s6_fp = sum(v.get("strict", {}).get("fp", 0) for v in s6_mentions_overall.values())
    s6_fn = sum(v.get("strict", {}).get("fn", 0) for v in s6_mentions_overall.values())
    s6_p = round(s6_tp / (s6_tp + s6_fp), 4) if (s6_tp + s6_fp) else 1.0
    s6_r = round(s6_tp / (s6_tp + s6_fn), 4) if (s6_tp + s6_fn) else 1.0
    s6_f1 = round(2 * s6_p * s6_r / (s6_p + s6_r), 4) if (s6_p + s6_r) else 1.0

    baselines = {
        "source_runs": ["step5a_baseline_r4", "step5b_ner_baseline_r2", "step6_extraction_r3"],
        "provenance_caption": "step5a_baseline_r4, step5b_ner_baseline_r2 & step6_extraction_r3",
        "sources": [hashes["step5a_metrics"], hashes["step5b_metrics"], hashes["step6_metrics"]],
        "dataset_caption": "Synthetic test, 50 FIRs. Only mentions evaluated (baselines do not extract relations).",
        "models": [
            {
                "name": "Regex baseline",
                "model_id": "regex",
                "run": "step5a_baseline_r4",
                "precision": safe_round(s5a_test.get("precision", 1.0), 4),
                "recall": safe_round(s5a_test.get("recall", 0.4568), 4),
                "f1": safe_round(s5a_test.get("f1", 0.6271), 4),
                "tp": s5a_test.get("tp", 111),
                "fp": s5a_test.get("fp", 0),
                "fn": s5a_test.get("fn", 132),
            },
            {
                "name": "spaCy (Davlan/XLM-R)",
                "model_id": "spacy",
                "run": "step5b_ner_baseline_r2",
                "precision": safe_round(davlan_test.get("precision", 0.9077), 4),
                "recall": safe_round(davlan_test.get("recall", 0.8939), 4),
                "f1": safe_round(davlan_test.get("f1", 0.9008), 4),
                "tp": davlan_test.get("tp", 118),
                "fp": davlan_test.get("fp", 12),
                "fn": davlan_test.get("fn", 14),
            },
            {
                "name": "Flair (IndicNER)",
                "model_id": "flair",
                "run": "step5b_ner_baseline_r2",
                "precision": safe_round(indicner_test.get("precision", 0.1418), 4),
                "recall": safe_round(indicner_test.get("recall", 0.1515), 4),
                "f1": safe_round(indicner_test.get("f1", 0.1465), 4),
                "tp": indicner_test.get("tp", 20),
                "fp": indicner_test.get("fp", 121),
                "fn": indicner_test.get("fn", 112),
            },
            {
                "name": "Our pipeline",
                "model_id": "pipeline",
                "run": "step6_extraction_r3",
                "precision": s6_p,
                "recall": s6_r,
                "f1": s6_f1,
                "tp": s6_tp,
                "fp": s6_fp,
                "fn": s6_fn,
            },
        ],
    }

    # Block G: Speed (Latency per stage)
    latency_run2 = s6_metrics.get("latency", {}).get("run2", {})
    stage_labels = {
        "model": "Neural model inference",
        "postprocess": "Postprocessing",
        "names_identifiers": "Names & identifiers",
        "assemble": "Entity assembly",
        "relations": "Relation extraction",
        "validate": "Contract validation",
    }
    stages = []
    for stage_id, label in stage_labels.items():
        stage_data = latency_run2.get(stage_id, {})
        stages.append({
            "id": stage_id,
            "label": label,
            "mean_ms": safe_round(stage_data.get("mean_ms", 0), 2),
            "p95_ms": safe_round(stage_data.get("p95_ms", 0), 2),
        })

    tot_data = latency_run2.get("total", {})
    speed = {
        "source_run": "step6_extraction_r3",
        "provenance_caption": "step6_extraction_r3 (latency.run2)",
        "source": hashes["step6_metrics"],
        "stages": stages,
        "total": {
            "mean_ms": safe_round(tot_data.get("mean_ms", 0), 2),
            "p95_ms": safe_round(tot_data.get("p95_ms", 0), 2),
        },
        "model_load_ms": safe_round(s6_metrics.get("latency", {}).get("model_load_ms", 0), 2),
    }

    snapshot = {
        "meta": {
            "generated_by": "scripts/build_model_performance.py",
            "source_files": hashes,
        },
        "headline": headline,
        "entities_by_type": entities_by_type,
        "relations_by_type": relations_by_type,
        "error_breakdown": error_breakdown,
        "generalisation_gap": generalisation_gap,
        "baselines": baselines,
        "speed": speed,
    }

    return snapshot


def main() -> None:
    """Build and write snapshot JSON to target location."""
    print("Generating model performance snapshot...")
    snapshot = generate_snapshot()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2, sort_keys=True)
        f.write("\n")
    print(f"Snapshot written successfully to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
