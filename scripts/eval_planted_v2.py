"""Planted-case evaluation v2 on 50 synthetic cases (seeds 151..200).

Pre-registered hypotheses:
H1 composite_v2 has a higher top-3 rate than call_count (kingpins pooled) at coverage 1.0.
H2 no prediction versus financial_only (a tie or a small difference is expected).
H3 composite_v2 has a higher top-3 rate than projection_only.
H4 composite_v2 has a higher top-3 rate than v1_composite.
H5 composite_v2 puts the decoy owner in the top 3 less often than call_count.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import copy
import json
from pathlib import Path
import platform
import statistics
import sys
from typing import Any

import networkx as nx
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from case_analytics.baselines import compute_baselines
from case_analytics.projection import (
    compute_pessimistic_ranks,
    compute_projection_scores,
)
from case_analytics.scores import compute_kingpin_scores
from case_graph.builder import _collect_bank_edges, _collect_cdr_edges
from case_simulation.v2 import build_planted_graph_v2

COVERAGES: tuple[float, ...] = (0.3, 0.6, 1.0)
ALL_RANKERS: tuple[str, ...] = (
    "composite_v2",
    "projection_only",
    "financial_only",
    "v1_composite",
    "call_count",
    "unweighted_degree",
    "weighted_pagerank",
    "transfer_amount_paise",
)


def run_paired_bootstrap(
    comp_hits: list[int],
    base_hits: list[int],
    n_resamples: int = 2000,
    seed: int = 20261114,
) -> dict[str, Any]:
    """Compute 95% bootstrap interval of pooled top-3 rate difference (comp - base)."""
    c_arr = np.asarray(comp_hits, dtype=np.float64)
    b_arr = np.asarray(base_hits, dtype=np.float64)
    N = len(c_arr)
    if N == 0:
        return {"ci_95": [0.0, 0.0], "mean_diff": 0.0}

    d = c_arr - b_arr
    # Pooled rate over N cases (2 kingpins per case = 2N kingpin opportunities)
    mean_diff = float(np.sum(d) / (2.0 * N))

    rng = np.random.RandomState(seed)
    matrix = rng.randint(0, N, size=(n_resamples, N))
    boot_diffs = d[matrix].sum(axis=1) / (2.0 * N)
    ci_low, ci_high = np.percentile(boot_diffs, [2.5, 97.5])

    return {
        "ci_95": [round(float(ci_low), 6), round(float(ci_high), 6)],
        "mean_diff": round(mean_diff, 6),
    }


def evaluate_planted_cases_v2(
    cases_dir: str | Path = "data/synthetic/out/planted_v2",
    out_dir: str | Path = "data/graph/out/planted_eval_v2",
) -> dict[str, Any]:
    cases_path = Path(cases_dir)
    out_path = Path(out_dir)

    summary_file = out_path / "summary.json"
    if summary_file.exists():
        raise FileExistsError(
            f"ERROR: Output summary file already exists, refusing to overwrite: {summary_file}"
        )

    case_dirs = sorted(
        [d for d in cases_path.iterdir() if d.is_dir() and d.name.startswith("seed_")],
        key=lambda d: int(d.name.split("_")[-1])
        if d.name.split("_")[-1].isdigit()
        else d.name,
    )

    per_case_ranks: dict[str, Any] = {}
    attributions: dict[str, Any] = {}
    seeds_processed: list[int] = []

    # Pre-parse CSVs per case once to optimize performance
    csv_caches: dict[
        str,
        tuple[
            list[dict[str, Any]],
            list[dict[str, Any]],
            dict[str, dict[str, Any]],
        ],
    ] = {}
    case_truths: dict[str, dict[str, Any]] = {}

    for cd in case_dirs:
        case_name = cd.name
        try:
            s_num = int(case_name.split("_")[-1])
            seeds_processed.append(s_num)
        except ValueError:
            pass

        with (cd / "truth.json").open("r", encoding="utf-8") as fh:
            case_truths[case_name] = json.load(fh)

        nodes_init: dict[str, dict[str, Any]] = {}
        cdr_e, _, _ = _collect_cdr_edges(cd / "cdr.csv", nodes_init)
        bank_e, _ = _collect_bank_edges(cd / "bank.csv", nodes_init)
        csv_caches[case_name] = (cdr_e, bank_e, nodes_init)

    financial_mismatches: list[dict[str, Any]] = []

    # Per-case storage for metric aggregation:
    # (cov_str, ranker, entity_key) -> list over 50 cases of record dicts
    case_records: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    # (cov_str, ranker) -> list of int hits (0, 1, or 2) per case for bootstrap
    pooled_kp_hits_by_case: dict[tuple[str, str], list[int]] = defaultdict(list)

    for cd in case_dirs:
        case_name = cd.name
        seed_num = int(case_name.split("_")[-1])
        truth = case_truths[case_name]
        kp_ids = [str(x) for x in truth.get("kingpin_ids", [])]

        decoy_pid = "DEC_PIZZA_01"
        for p in truth.get("people", []):
            if p.get("is_decoy") or "DEC" in str(p.get("person_id", "")):
                decoy_pid = str(p.get("person_id", ""))
                break

        cached_csv = csv_caches[case_name]
        per_case_ranks[case_name] = {}
        attributions[case_name] = {}

        for cov_idx, coverage in enumerate(COVERAGES):
            cov_str = str(coverage)
            per_case_ranks[case_name][cov_str] = {}

            graph, truth_to_opaque, stated_facts = build_planted_graph_v2(
                case_dir=cd,
                coverage=coverage,
                seed=seed_num,
                coverage_index=cov_idx,
                csv_cache=cached_csv,
            )

            attributions[case_name][cov_str] = stated_facts

            # 1. Projection-based rankers (composite_v2, projection_only, financial_only)
            proj_res = compute_projection_scores(graph)
            proj_pessimistic = proj_res["pessimistic_ranks"]
            proj_raw = proj_res["raw_scores"]

            # 2. Existing v1 composite (leak-free pessimistic ranks)
            v1_res = compute_kingpin_scores(graph, mode="strict")
            v1_scores = {
                row["node_id"]: float(row.get("composite", row.get("score", 0.0)))
                for row in v1_res.get("ranking", [])
            }
            v1_pessimistic = compute_pessimistic_ranks(v1_scores)

            # 3. Existing baselines (leak-free pessimistic ranks)
            baselines_res = compute_baselines(graph, mode="strict")
            base_dict = baselines_res.get("baselines", {})

            ranker_ranks: dict[str, dict[str, int]] = {
                "composite_v2": proj_pessimistic["composite_v2"],
                "projection_only": proj_pessimistic["projection_only"],
                "financial_only": proj_pessimistic["financial_only"],
                "v1_composite": v1_pessimistic,
            }
            ranker_scores: dict[str, dict[str, float | int]] = {
                "composite_v2": proj_raw["composite_v2"],
                "projection_only": proj_raw["projection_only"],
                "financial_only": proj_raw["financial_only"],
                "v1_composite": v1_scores,
            }

            for b_name in (
                "call_count",
                "unweighted_degree",
                "weighted_pagerank",
                "transfer_amount_paise",
            ):
                b_ranking = base_dict.get(b_name, [])
                b_scores = {row["node_id"]: row["score"] for row in b_ranking}
                ranker_scores[b_name] = b_scores
                ranker_ranks[b_name] = compute_pessimistic_ranks(b_scores)

            # Assertion: financial_only pessimistic ranks == transfer_amount_paise pessimistic ranks
            fin_ranks = ranker_ranks["financial_only"]
            tx_ranks = ranker_ranks["transfer_amount_paise"]
            if fin_ranks != tx_ranks:
                mismatch_info = {
                    "case": case_name,
                    "coverage": coverage,
                    "financial_ranks": fin_ranks,
                    "transfer_ranks": tx_ranks,
                }
                financial_mismatches.append(mismatch_info)

            # Collect metrics per ranker
            for ranker in ALL_RANKERS:
                ranks_map = ranker_ranks[ranker]
                scores_map = ranker_scores[ranker]

                kp_ranks_for_case: dict[str, int | None] = {}
                kp_hits_case = 0

                for kp in kp_ids:
                    op_id = truth_to_opaque.get(kp)
                    if op_id is not None and op_id in ranks_map:
                        r = ranks_map[op_id]
                        kp_ranks_for_case[kp] = r
                        # Check ties with other persons
                        s_i = round(float(scores_map[op_id]), 9)
                        is_tied = any(
                            other != op_id and round(float(scores_map[other]), 9) == s_i
                            for other in scores_map
                        )
                        record = {
                            "is_tied": is_tied,
                            "present": True,
                            "rank": r,
                            "rr": 1.0 / r,
                            "top1": r <= 1,
                            "top3": r <= 3,
                            "top5": r <= 5,
                        }
                        if r <= 3:
                            kp_hits_case += 1
                    else:
                        kp_ranks_for_case[kp] = None
                        record = {
                            "is_tied": False,
                            "present": False,
                            "rank": None,
                            "rr": 0.0,
                            "top1": False,
                            "top3": False,
                            "top5": False,
                        }
                    case_records[(cov_str, ranker, kp)].append(record)

                pooled_kp_hits_by_case[(cov_str, ranker)].append(kp_hits_case)

                # Decoy owner
                decoy_op = truth_to_opaque.get(decoy_pid)
                if decoy_op is not None and decoy_op in ranks_map:
                    decoy_r = ranks_map[decoy_op]
                else:
                    decoy_r = None

                case_records[(cov_str, ranker, "decoy")].append(
                    {"rank": decoy_r, "top3": decoy_r is not None and decoy_r <= 3}
                )

                per_case_ranks[case_name][cov_str][ranker] = {
                    "decoy_owner": decoy_r,
                    "kingpins": kp_ranks_for_case,
                    "ranked_persons": len(ranks_map),
                }

    total_cases = len(case_dirs)

    # Compute Summary
    summary_by_config: dict[str, Any] = {}
    for coverage in COVERAGES:
        cov_str = str(coverage)
        summary_by_config[cov_str] = {}

        for ranker in ALL_RANKERS:
            # Decoy owner metric
            decoy_recs = case_records[(cov_str, ranker, "decoy")]
            decoy_t3 = (
                sum(1 for rec in decoy_recs if rec["top3"]) / total_cases
                if total_cases
                else 0.0
            )

            kp_metrics: dict[str, Any] = {}
            for kp_role in ("PER_A_KP_01", "PER_B_KP_01"):
                recs = case_records[(cov_str, ranker, kp_role)]
                present_recs = [rec for rec in recs if rec["present"]]
                present_ranks = [rec["rank"] for rec in present_recs]

                presence_rate = len(present_recs) / total_cases
                top1_rate = sum(1 for rec in recs if rec["top1"]) / total_cases
                top3_rate = sum(1 for rec in recs if rec["top3"]) / total_cases
                top5_rate = sum(1 for rec in recs if rec["top5"]) / total_cases
                mrr = sum(rec["rr"] for rec in recs) / total_cases
                med_rank = (
                    float(statistics.median(present_ranks))
                    if present_ranks
                    else None
                )
                tied_share_all = sum(1 for rec in recs if rec["is_tied"]) / total_cases
                tied_share_present = (
                    sum(1 for rec in present_recs if rec["is_tied"])
                    / len(present_recs)
                    if present_recs
                    else 0.0
                )

                kp_metrics[kp_role] = {
                    "mean_reciprocal_rank": round(mrr, 4),
                    "median_pessimistic_rank_present": med_rank,
                    "presence_rate": round(presence_rate, 4),
                    "tied_share_all_cases": round(tied_share_all, 4),
                    "tied_share_present": round(tied_share_present, 4),
                    "top_1_rate": round(top1_rate, 4),
                    "top_3_rate": round(top3_rate, 4),
                    "top_5_rate": round(top5_rate, 4),
                }

            # Pooled kingpins (A and B combined over total_cases * 2)
            all_kp_recs = (
                case_records[(cov_str, ranker, "PER_A_KP_01")]
                + case_records[(cov_str, ranker, "PER_B_KP_01")]
            )
            pooled_n = len(all_kp_recs)
            pooled_present = [rec for rec in all_kp_recs if rec["present"]]
            pooled_ranks = [rec["rank"] for rec in pooled_present]

            pooled_metrics = {
                "mean_reciprocal_rank": round(
                    sum(rec["rr"] for rec in all_kp_recs) / pooled_n, 4
                ),
                "median_pessimistic_rank_present": (
                    float(statistics.median(pooled_ranks))
                    if pooled_ranks
                    else None
                ),
                "presence_rate": round(len(pooled_present) / pooled_n, 4),
                "tied_share_all_cases": round(
                    sum(1 for rec in all_kp_recs if rec["is_tied"]) / pooled_n, 4
                ),
                "tied_share_present": round(
                    sum(1 for rec in pooled_present if rec["is_tied"])
                    / len(pooled_present)
                    if pooled_present
                    else 0.0,
                    4,
                ),
                "top_1_rate": round(
                    sum(1 for rec in all_kp_recs if rec["top1"]) / pooled_n, 4
                ),
                "top_3_rate": round(
                    sum(1 for rec in all_kp_recs if rec["top3"]) / pooled_n, 4
                ),
                "top_5_rate": round(
                    sum(1 for rec in all_kp_recs if rec["top5"]) / pooled_n, 4
                ),
            }

            summary_by_config[cov_str][ranker] = {
                "decoy_top_3_rate": round(decoy_t3, 4),
                "kingpins": kp_metrics,
                "kingpins_pooled": pooled_metrics,
            }

    # Paired Bootstrap Differences (composite_v2 - X)
    bootstrap_results: dict[str, Any] = {}
    for coverage in COVERAGES:
        cov_str = str(coverage)
        bootstrap_results[cov_str] = {}
        comp_hits = pooled_kp_hits_by_case[(cov_str, "composite_v2")]

        for other_ranker in ALL_RANKERS:
            if other_ranker == "composite_v2":
                continue
            other_hits = pooled_kp_hits_by_case[(cov_str, other_ranker)]
            boot_stat = run_paired_bootstrap(
                comp_hits=comp_hits,
                base_hits=other_hits,
                n_resamples=2000,
                seed=20261114,
            )
            bootstrap_results[cov_str][other_ranker] = boot_stat

    summary_report = {
        "by_configuration": summary_by_config,
        "financial_only_mismatches_count": len(financial_mismatches),
        "paired_bootstrap_top_3_differences": bootstrap_results,
    }

    run_info = {
        "bootstrap": {
            "n_resamples": 2000,
            "seed": 20261114,
        },
        "coverages": list(COVERAGES),
        "days": 30,
        "formulas_and_weights": {
            "composite_v2": "0.70 * structural + 0.30 * financial_control",
            "financial_control": (
                "sum over person's controlled accounts of (paise sent + paise received on bank "
                "TRANSFERRED_FUNDS edges), normalised by max over ranked persons"
            ),
            "pessimistic_rank": "1 + count of other persons with score >= person score (rounded to 9 decimals)",
            "projection_weights": {
                "phone_communication": "1.5 * log2(1 + voice_count + sms_count)",
                "shared_controlled_account": 3.0,
                "shared_owned_phone": 1.5,
                "transfer_funds": "1.0 * log2(1 + txn_count)",
            },
            "structural": "0.40 * norm_degree + 0.30 * norm_betweenness + 0.30 * norm_eigenvector",
        },
        "library_versions": {
            "networkx": nx.__version__,
            "numpy": np.__version__,
            "python": platform.python_version(),
        },
        "number_of_cases_ok": total_cases,
        "rankers": list(ALL_RANKERS),
        "seeds": sorted(seeds_processed),
    }

    out_path.mkdir(parents=True, exist_ok=True)

    with (out_path / "per_case_ranks.json").open("w", encoding="utf-8") as fh:
        json.dump(per_case_ranks, fh, indent=2, sort_keys=True)

    with (out_path / "attributions.json").open("w", encoding="utf-8") as fh:
        json.dump(attributions, fh, indent=2, sort_keys=True)

    with (out_path / "run_info.json").open("w", encoding="utf-8") as fh:
        json.dump(run_info, fh, indent=2, sort_keys=True)

    with summary_file.open("w", encoding="utf-8") as fh:
        json.dump(summary_report, fh, indent=2, sort_keys=True)

    return summary_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run planted cases evaluation v2 (leak-free, projection composite)."
    )
    parser.add_argument(
        "--cases-dir",
        default="data/synthetic/out/planted_v2",
        help="Directory with planted synthetic cases.",
    )
    parser.add_argument(
        "--out-dir",
        default="data/graph/out/planted_eval_v2",
        help="Directory for evaluation outputs.",
    )
    args = parser.parse_args(argv)

    try:
        report = evaluate_planted_cases_v2(args.cases_dir, args.out_dir)
    except FileExistsError as err:
        print(str(err), file=sys.stderr)
        return 1

    print("Evaluation v2 completed successfully.")
    print(
        f"Financial-only mismatches count: {report['financial_only_mismatches_count']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
