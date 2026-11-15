"""Planted-case evaluation on 50 synthetic cases across coverage and fragmentation.

Pre-registered hypotheses:
H1 the composite puts a kingpin in the top 3 more often than call count;
H2 no prediction versus unweighted degree, PageRank and transfer amount;
H3 lower coverage lowers every ranker;
H4 fragmented lowers every ranker versus resolved.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import copy
import json
from pathlib import Path
import statistics
import sys
from typing import Any

import networkx as nx
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from case_analytics.baselines import compute_baselines  # noqa: E402
from case_analytics.scores import compute_kingpin_scores  # noqa: E402
from case_graph.builder import _collect_bank_edges, _collect_cdr_edges  # noqa: E402
from case_simulation.builder import build_planted_graph  # noqa: E402

COVERAGES: tuple[float, ...] = (0.3, 0.6, 1.0)
MODES: tuple[str, ...] = ("resolved", "fragmented")
BASELINES: tuple[str, ...] = (
    "call_count",
    "unweighted_degree",
    "weighted_pagerank",
    "transfer_amount_paise",
)
ALL_RANKERS: tuple[str, ...] = ("composite",) + BASELINES


def _find_best_rank(
    ranking: list[dict[str, Any]], target_pid: str
) -> int | None:
    best: int | None = None
    prefix = f"PERSON:{target_pid}"
    for row in ranking:
        nid = str(row.get("node_id", ""))
        if nid == prefix or nid.startswith(f"{prefix}:"):
            r = int(row["rank"])
            if best is None or r < best:
                best = r
    return best


def run_paired_bootstrap(
    comp_hits: list[int],
    base_hits: list[int],
    n_resamples: int = 2000,
    seed: int = 20261113,
) -> dict[str, Any]:
    """Compute 95% bootstrap interval of pooled top-3 rate difference (comp - base)."""
    c_arr = np.asarray(comp_hits, dtype=np.float64)
    b_arr = np.asarray(base_hits, dtype=np.float64)
    N = len(c_arr)
    if N == 0:
        return {"ci_95": [0.0, 0.0], "mean_diff": 0.0}

    d = c_arr - b_arr
    mean_diff = float(np.mean(d) / 2.0)

    rng = np.random.RandomState(seed)
    matrix = rng.randint(0, N, size=(n_resamples, N))
    boot_diffs = d[matrix].sum(axis=1) / (2.0 * N)
    ci_low, ci_high = np.percentile(boot_diffs, [2.5, 97.5])

    return {
        "ci_95": [round(float(ci_low), 6), round(float(ci_high), 6)],
        "mean_diff": round(mean_diff, 6),
    }


def evaluate_planted_cases(
    cases_dir: str | Path = "data/synthetic/out/planted_v1",
    out_dir: str | Path = "data/graph/out/planted_eval_v1",
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

    # Pre-parse CSVs per case once to optimize execution
    csv_caches: dict[str, tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, dict[str, Any]]]] = {}
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

    # Storage for pooling across cases: (mode, cov_str, ranker, kp_id) -> list of ranks
    kp_ranks_by_config: dict[tuple[str, str, str, str], list[int | None]] = defaultdict(list)
    decoy_ranks_by_config: dict[tuple[str, str, str], list[int | None]] = defaultdict(list)
    # Storage for bootstrap: (mode, cov_str, ranker) -> list of hits (0, 1, or 2) per case
    kp_hits_by_case: dict[tuple[str, str, str], list[int]] = defaultdict(list)

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
            attributions[case_name][cov_str] = {}

            for mode in MODES:
                if mode not in per_case_ranks[case_name]:
                    per_case_ranks[case_name][mode] = {}
                per_case_ranks[case_name][mode][cov_str] = {}

                # Deterministic RandomState for sampling stated facts
                rng = np.random.RandomState(seed_num * 1000 + cov_idx)
                fragmented = mode == "fragmented"

                graph = build_planted_graph(
                    case_dir=cd,
                    coverage=coverage,
                    fragmented=fragmented,
                    rng=rng,
                    csv_cache=cached_csv,
                )

                if mode == "resolved":
                    # Save stated facts once per coverage
                    attributions[case_name][cov_str] = graph.get("attributions", {})

                scores_res = compute_kingpin_scores(graph, mode="strict")
                baselines_res = compute_baselines(graph, mode="strict")

                ranker_lists: dict[str, list[dict[str, Any]]] = {
                    "composite": scores_res.get("ranking", []),
                }
                for b_name in BASELINES:
                    ranker_lists[b_name] = baselines_res.get("baselines", {}).get(
                        b_name, []
                    )

                for ranker in ALL_RANKERS:
                    ranking = ranker_lists[ranker]
                    ranked_count = len(ranking)

                    kp_best_ranks: dict[str, int | None] = {}
                    hits_count = 0
                    for kp in kp_ids:
                        brank = _find_best_rank(ranking, kp)
                        kp_best_ranks[kp] = brank
                        kp_ranks_by_config[(mode, cov_str, ranker, kp)].append(brank)
                        if brank is not None and brank <= 3:
                            hits_count += 1

                    decoy_best = _find_best_rank(ranking, decoy_pid)
                    decoy_ranks_by_config[(mode, cov_str, ranker)].append(decoy_best)
                    kp_hits_by_case[(mode, cov_str, ranker)].append(hits_count)

                    per_case_ranks[case_name][mode][cov_str][ranker] = {
                        "decoy_owner": decoy_best,
                        "kingpins": kp_best_ranks,
                        "ranked_persons": ranked_count,
                    }

    total_cases = len(case_dirs)

    # Compute Summary
    summary_by_config: dict[str, Any] = {}
    for mode in MODES:
        summary_by_config[mode] = {}
        for coverage in COVERAGES:
            cov_str = str(coverage)
            summary_by_config[mode][cov_str] = {}

            for ranker in ALL_RANKERS:
                decoy_ranks = decoy_ranks_by_config[(mode, cov_str, ranker)]
                decoy_t3 = (
                    sum(1 for r in decoy_ranks if r is not None and r <= 3)
                    / total_cases
                )

                kp_metrics: dict[str, Any] = {}
                for kp_role in ("PER_A_KP_01", "PER_B_KP_01"):
                    ranks = kp_ranks_by_config[(mode, cov_str, ranker, kp_role)]
                    present_ranks = [r for r in ranks if r is not None]
                    presence_rate = len(present_ranks) / total_cases
                    t1_rate = sum(1 for r in present_ranks if r <= 1) / total_cases
                    t3_rate = sum(1 for r in present_ranks if r <= 3) / total_cases
                    t5_rate = sum(1 for r in present_ranks if r <= 5) / total_cases
                    med_rank = (
                        float(statistics.median(present_ranks))
                        if present_ranks
                        else None
                    )

                    kp_metrics[kp_role] = {
                        "median_rank_present": med_rank,
                        "presence_rate": round(presence_rate, 4),
                        "top_1_rate": round(t1_rate, 4),
                        "top_3_rate": round(t3_rate, 4),
                        "top_5_rate": round(t5_rate, 4),
                    }

                summary_by_config[mode][cov_str][ranker] = {
                    "decoy_top_3_rate": round(decoy_t3, 4),
                    "kingpins": kp_metrics,
                }

    # Paired Bootstrap Differences
    bootstrap_results: dict[str, Any] = {}
    for mode in MODES:
        bootstrap_results[mode] = {}
        for coverage in COVERAGES:
            cov_str = str(coverage)
            bootstrap_results[mode][cov_str] = {}
            comp_hits = kp_hits_by_case[(mode, cov_str, "composite")]

            for baseline in BASELINES:
                base_hits = kp_hits_by_case[(mode, cov_str, baseline)]
                boot_stat = run_paired_bootstrap(
                    comp_hits=comp_hits,
                    base_hits=base_hits,
                    n_resamples=2000,
                    seed=20261113,
                )
                bootstrap_results[mode][cov_str][baseline] = boot_stat

    summary_report = {
        "by_configuration": summary_by_config,
        "paired_bootstrap_top_3_differences": bootstrap_results,
    }

    run_info = {
        "bootstrap": {
            "n_resamples": 2000,
            "seed": 20261113,
        },
        "coverages": list(COVERAGES),
        "days": 30,
        "library_versions": {
            "networkx": nx.__version__,
            "numpy": np.__version__,
            "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        },
        "modes": list(MODES),
        "number_of_cases_ok": total_cases,
        "rankers": list(ALL_RANKERS),
        "seeds": seeds_processed,
    }

    out_path.mkdir(parents=True, exist_ok=True)

    with (out_path / "per_case_ranks.json").open("w", encoding="utf-8", newline="\n") as fh:
        json.dump(per_case_ranks, fh, indent=2, sort_keys=True, ensure_ascii=False)
        fh.write("\n")

    with (out_path / "attributions.json").open("w", encoding="utf-8", newline="\n") as fh:
        json.dump(attributions, fh, indent=2, sort_keys=True, ensure_ascii=False)
        fh.write("\n")

    with summary_file.open("w", encoding="utf-8", newline="\n") as fh:
        json.dump(summary_report, fh, indent=2, sort_keys=True, ensure_ascii=False)
        fh.write("\n")

    with (out_path / "run_info.json").open("w", encoding="utf-8", newline="\n") as fh:
        json.dump(run_info, fh, indent=2, sort_keys=True, ensure_ascii=False)
        fh.write("\n")

    return {
        "per_case_ranks": per_case_ranks,
        "run_info": run_info,
        "summary": summary_report,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate kingpin identification on planted cases."
    )
    parser.add_argument(
        "--cases-dir",
        default="data/synthetic/out/planted_v1",
        help="Directory with seed_NNN case subdirectories.",
    )
    parser.add_argument(
        "--out-dir",
        default="data/graph/out/planted_eval_v1",
        help="Output evaluation directory.",
    )
    args = parser.parse_args(argv)

    try:
        evaluate_planted_cases(cases_dir=args.cases_dir, out_dir=args.out_dir)
    except FileExistsError as err:
        print(str(err), file=sys.stderr)
        return 1

    print(f"Planted case evaluation complete -> {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
