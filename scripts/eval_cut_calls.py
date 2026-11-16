"""Evaluation of call-layer network break and bridging phone detection.

PRE-REGISTERED HYPOTHESES (registered before code execution; not edited afterwards):
 C1 at coverage 1.0 with the true gangs given (GANG_A members, GANG_B members that have a node;
    couriers belong to neither group), the call-layer min vertex cut equals exactly the set of the two
    bridge couriers in a majority of cases (more than 50 percent).
 C2 at coverage 1.0 the exact-match share of the cut is higher than for top2_betweenness and for top2_degree.
 C3 the exact-match share at coverage 0.6 is lower than at coverage 1.0.
 C4 at coverage 1.0 the cut has size 2 in a majority of cases.
 C5 the Louvain variant (groups = the two largest communities of the call-layer graph, seed 20261116)
    has a lower exact-match share than the true-gangs variant.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import sys
from typing import Any

import networkx as nx
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from case_detectors.cut_calls import (
    articulation_persons,
    break_groups,
    call_layer_graph,
    detect_communities_calls,
    top2_betweenness,
    top2_degree,
    unowned_bridging_phones,
)
from case_simulation.v2 import build_planted_graph_v2


def _load_truth(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _paired_bootstrap_diff(
    a: list[float],
    b: list[float],
    n_resamples: int = 2000,
    seed: int = 20261116,
) -> dict[str, Any]:
    """Paired bootstrap for difference in means (a - b)."""
    diffs = np.array(a, dtype=float) - np.array(b, dtype=float)
    rng = np.random.RandomState(seed)
    n = len(diffs)
    if n == 0:
        return {"ci_95": [0.0, 0.0], "mean_diff": 0.0}

    boot_means = np.empty(n_resamples, dtype=float)
    for i in range(n_resamples):
        idx = rng.randint(0, n, size=n)
        boot_means[i] = float(np.mean(diffs[idx]))

    mean_diff = round(float(np.mean(diffs)), 6)
    ci_low = round(float(np.percentile(boot_means, 2.5)), 6)
    ci_high = round(float(np.percentile(boot_means, 97.5)), 6)
    return {"ci_95": [ci_low, ci_high], "mean_diff": mean_diff}


def evaluate_case_suite(
    cases_dir: str | Path,
    start_seed: int,
    end_seed: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Evaluate call-layer network break across a set of seeds.

    Returns:
        (suite_summary, suite_per_case)
    """
    base_path = Path(cases_dir)
    case_dirs = [
        base_path / f"seed_{s}"
        for s in range(start_seed, end_seed + 1)
        if (base_path / f"seed_{s}").is_dir()
    ]
    case_dirs.sort(key=lambda d: int(d.name.split("_")[-1]))

    coverages = [("0.6", 1), ("1.0", 2)]
    per_case_report: dict[str, Any] = {}

    # Accumulators per coverage
    acc: dict[str, dict[str, list[Any]]] = {
        cov_str: {
            "cut_exact": [],
            "top2_bet_exact": [],
            "top2_deg_exact": [],
            "finite": [],
            "has_cr1": [],
            "has_cr2": [],
            "has_pizza": [],
            "cut_size": [],
            "non_couriers": [],
            "skipped": [],
            "courier_art_share": [],
            # Louvain variant
            "louvain_finite": [],
            "louvain_exact": [],
            "louvain_has_cr1": [],
            "louvain_has_cr2": [],
            "louvain_has_pizza": [],
            "louvain_non_couriers": [],
            "louvain_agreement_a": [],
            # Unowned bridging phones
            "unowned_count": [],
            "unowned_burner": [],
            "unowned_decoy": [],
            "unowned_pizza": [],
            "unowned_none": [],
        }
        for cov_str, _ in coverages
    }

    for cd in case_dirs:
        case_name = cd.name
        seed_num = int(case_name.split("_")[-1])
        truth = _load_truth(cd / "truth.json")

        gang_a_truth_ids = [
            str(p["person_id"]) for p in truth.get("people", []) if p.get("gang") == "GANG_A"
        ]
        gang_b_truth_ids = [
            str(p["person_id"]) for p in truth.get("people", []) if p.get("gang") == "GANG_B"
        ]
        courier_truth_ids = [str(x) for x in truth.get("bridge_courier_ids", [])]
        burner_phones = set(str(x) for x in truth.get("burner_phones", []))
        decoy_customers = set(str(x) for x in truth.get("decoy_customers", []))
        pizza_shop_number = str(truth.get("decoys", {}).get("pizza_shop_number", ""))

        cdr_path = cd / "cdr.csv"
        with cdr_path.open("r", encoding="utf-8") as fh:
            cdr_rows = list(csv.DictReader(fh))

        case_record: dict[str, Any] = {}

        for cov_str, cov_idx in coverages:
            cov_val = float(cov_str)
            graph_v2, truth_to_opaque, _ = build_planted_graph_v2(
                case_dir=cd,
                coverage=cov_val,
                seed=seed_num,
                coverage_index=cov_idx,
            )

            # Build owners mapping: device -> list of opaque person IDs
            owners_phones: dict[str, list[str]] = {}
            for edge in graph_v2.get("edges", []):
                if (
                    edge.get("relation") == "OWNS_DEVICE"
                    and str(edge.get("source", "")).startswith("PERSON:")
                    and str(edge.get("target", "")).startswith("PHONE:")
                ):
                    ph = str(edge["target"]).replace("PHONE:", "").strip()
                    owners_phones.setdefault(ph, []).append(str(edge["source"]))

            # Build call layer graph
            call_graph = call_layer_graph(cdr_rows, owners_phones)

            # Map truth groups to opaque node IDs
            group_a = [
                truth_to_opaque[pid] for pid in gang_a_truth_ids if pid in truth_to_opaque
            ]
            group_b = [
                truth_to_opaque[pid] for pid in gang_b_truth_ids if pid in truth_to_opaque
            ]
            cr1_op = truth_to_opaque.get("PER_CR_01")
            cr2_op = truth_to_opaque.get("PER_CR_02")
            expected_couriers = {cr for cr in (cr1_op, cr2_op) if cr is not None}
            pizza_op = truth_to_opaque.get("DEC_PIZZA_01")

            # 1. True Gangs Break
            cut_res = break_groups(call_graph, group_a, group_b)
            is_skipped = cut_res.get("skipped") == "empty_group"
            is_finite = cut_res.get("finite", False)
            cut_list = cut_res.get("cut", []) if is_finite else []
            cut_set = set(cut_list)

            exact_match = (
                is_finite
                and len(expected_couriers) == 2
                and cut_set == expected_couriers
            )
            has_cr1 = (cr1_op in cut_set) if cr1_op else False
            has_cr2 = (cr2_op in cut_set) if cr2_op else False
            has_pizza = (pizza_op in cut_set) if pizza_op else False
            non_couriers = len(cut_set - expected_couriers) if is_finite else 0
            cut_size = cut_res.get("size") if is_finite else None

            # 2. Baselines (top2_betweenness and top2_degree)
            bet_res = top2_betweenness(call_graph)
            deg_res = top2_degree(call_graph)

            bet_exact = (
                not bet_res["tied"]
                and len(expected_couriers) == 2
                and set(bet_res["top2"]) == expected_couriers
            )
            deg_exact = (
                not deg_res["tied"]
                and len(expected_couriers) == 2
                and set(deg_res["top2"]) == expected_couriers
            )

            # 3. Articulation Points
            arts = articulation_persons(call_graph)
            art_ids = {a["node_id"] for a in arts}
            courier_art_count = sum(1 for cr in expected_couriers if cr in art_ids)
            courier_art_share = (
                courier_art_count / len(expected_couriers) if expected_couriers else 0.0
            )

            # 4. Louvain Variant
            comms = detect_communities_calls(call_graph, seed=20261116)
            if len(comms) >= 2:
                comm_a = comms[0]
                comm_b = comms[1]
                louvain_res = break_groups(call_graph, comm_a, comm_b)
                l_finite = louvain_res.get("finite", False)
                l_cut = set(louvain_res.get("cut", [])) if l_finite else set()
                l_exact = (
                    l_finite
                    and len(expected_couriers) == 2
                    and l_cut == expected_couriers
                )
                l_has_cr1 = (cr1_op in l_cut) if cr1_op else False
                l_has_cr2 = (cr2_op in l_cut) if cr2_op else False
                l_has_pizza = (pizza_op in l_cut) if pizza_op else False
                l_non_couriers = len(l_cut - expected_couriers) if l_finite else 0

                ga_nodes = set(group_a)
                if ga_nodes:
                    agr_a = len(ga_nodes & set(comm_a)) / len(ga_nodes)
                    agr_b = len(ga_nodes & set(comm_b)) / len(ga_nodes)
                    adjusted_agreement = max(agr_a, agr_b)
                else:
                    adjusted_agreement = 0.0
            else:
                l_finite = False
                l_exact = False
                l_has_cr1 = False
                l_has_cr2 = False
                l_has_pizza = False
                l_non_couriers = 0
                adjusted_agreement = 0.0

            # 5. Unowned Bridging Phones
            unowned = unowned_bridging_phones(cdr_rows, owners_phones, group_a, group_b)
            u_burner = 0
            u_decoy = 0
            u_pizza = 0
            u_none = 0
            for lead in unowned:
                ph = lead["phone"]
                matched = False
                if ph == pizza_shop_number:
                    u_pizza += 1
                    matched = True
                if ph in burner_phones:
                    u_burner += 1
                    matched = True
                if ph in decoy_customers:
                    u_decoy += 1
                    matched = True
                if not matched:
                    u_none += 1

            # Store in accumulators
            acc[cov_str]["skipped"].append(1.0 if is_skipped else 0.0)
            acc[cov_str]["finite"].append(1.0 if is_finite else 0.0)
            acc[cov_str]["cut_exact"].append(1.0 if exact_match else 0.0)
            acc[cov_str]["top2_bet_exact"].append(1.0 if bet_exact else 0.0)
            acc[cov_str]["top2_deg_exact"].append(1.0 if deg_exact else 0.0)
            acc[cov_str]["has_cr1"].append(1.0 if has_cr1 else 0.0)
            acc[cov_str]["has_cr2"].append(1.0 if has_cr2 else 0.0)
            acc[cov_str]["has_pizza"].append(1.0 if has_pizza else 0.0)
            acc[cov_str]["cut_size"].append(cut_size)
            acc[cov_str]["non_couriers"].append(non_couriers)
            acc[cov_str]["courier_art_share"].append(courier_art_share)

            acc[cov_str]["louvain_finite"].append(1.0 if l_finite else 0.0)
            acc[cov_str]["louvain_exact"].append(1.0 if l_exact else 0.0)
            acc[cov_str]["louvain_has_cr1"].append(1.0 if l_has_cr1 else 0.0)
            acc[cov_str]["louvain_has_cr2"].append(1.0 if l_has_cr2 else 0.0)
            acc[cov_str]["louvain_has_pizza"].append(1.0 if l_has_pizza else 0.0)
            acc[cov_str]["louvain_non_couriers"].append(l_non_couriers)
            acc[cov_str]["louvain_agreement_a"].append(adjusted_agreement)

            acc[cov_str]["unowned_count"].append(len(unowned))
            acc[cov_str]["unowned_burner"].append(u_burner)
            acc[cov_str]["unowned_decoy"].append(u_decoy)
            acc[cov_str]["unowned_pizza"].append(u_pizza)
            acc[cov_str]["unowned_none"].append(u_none)

            case_record[f"cov_{cov_str}"] = {
                "cut_result": cut_res,
                "exact_match": exact_match,
                "has_cr1": has_cr1,
                "has_cr2": has_cr2,
                "has_pizza": has_pizza,
                "non_couriers": non_couriers,
                "baseline_betweenness_exact": bet_exact,
                "baseline_degree_exact": deg_exact,
                "courier_art_share": courier_art_share,
                "louvain_exact": l_exact,
                "louvain_agreement": adjusted_agreement,
                "unowned_bridging_phones_count": len(unowned),
            }

        per_case_report[case_name] = case_record

    # Build summary
    summary: dict[str, Any] = {}
    N = len(case_dirs)

    for cov_str, _ in coverages:
        c_acc = acc[cov_str]
        size_counts = Counter(
            [str(s) if s is not None else "None" for s in c_acc["cut_size"]]
        )

        un_counts = c_acc["unowned_count"]
        un_mean = round(float(np.mean(un_counts)), 4) if un_counts else 0.0
        un_med = round(float(np.median(un_counts)), 4) if un_counts else 0.0
        un_max = int(np.max(un_counts)) if un_counts else 0

        boot_res = _paired_bootstrap_diff(
            c_acc["cut_exact"],
            c_acc["top2_bet_exact"],
            n_resamples=2000,
            seed=20261116,
        )

        cov_summary = {
            "avg_non_courier_persons": round(float(np.mean(c_acc["non_couriers"])), 4),
            "baseline_top2_betweenness_exact_share": round(
                float(np.mean(c_acc["top2_bet_exact"])), 4
            ),
            "baseline_top2_degree_exact_share": round(
                float(np.mean(c_acc["top2_deg_exact"])), 4
            ),
            "cases_evaluated": N,
            "cases_skipped": int(sum(c_acc["skipped"])),
            "courier_articulation_share": round(
                float(np.mean(c_acc["courier_art_share"])), 4
            ),
            "distribution_cut_size": dict(sorted(size_counts.items())),
            "louvain_variant": {
                "adjusted_agreement_gang_a": round(
                    float(np.mean(c_acc["louvain_agreement_a"])), 4
                ),
                "avg_non_courier_persons": round(
                    float(np.mean(c_acc["louvain_non_couriers"])), 4
                ),
                "share_containing_cr1": round(
                    float(np.mean(c_acc["louvain_has_cr1"])), 4
                ),
                "share_containing_cr2": round(
                    float(np.mean(c_acc["louvain_has_cr2"])), 4
                ),
                "share_containing_pizza_owner": round(
                    float(np.mean(c_acc["louvain_has_pizza"])), 4
                ),
                "share_exact_couriers": round(
                    float(np.mean(c_acc["louvain_exact"])), 4
                ),
                "share_finite": round(float(np.mean(c_acc["louvain_finite"])), 4),
            },
            "paired_bootstrap_cut_minus_top2_betweenness": boot_res,
            "share_containing_cr1": round(float(np.mean(c_acc["has_cr1"])), 4),
            "share_containing_cr2": round(float(np.mean(c_acc["has_cr2"])), 4),
            "share_containing_pizza_owner": round(
                float(np.mean(c_acc["has_pizza"])), 4
            ),
            "share_exact_couriers": round(float(np.mean(c_acc["cut_exact"])), 4),
            "share_finite": round(float(np.mean(c_acc["finite"])), 4),
            "unowned_bridging_phones": {
                "breakdown": {
                    "burner_phones": int(sum(c_acc["unowned_burner"])),
                    "decoy_customers": int(sum(c_acc["unowned_decoy"])),
                    "none_of_these": int(sum(c_acc["unowned_none"])),
                    "pizza_shop_number": int(sum(c_acc["unowned_pizza"])),
                },
                "number_per_case": {
                    "max": un_max,
                    "mean": un_mean,
                    "median": un_med,
                },
            },
        }
        summary[cov_str] = cov_summary

    return summary, per_case_report


def run_evaluation(
    out_dir: str | Path = "data/graph/out/planted_eval_v3",
    planted_v3_dir: str | Path = "data/synthetic/out/planted_v3",
    planted_v2_dir: str | Path = "data/synthetic/out/planted_v2",
) -> None:
    out_path = Path(out_dir)
    summary_file = out_path / "summary.json"
    if summary_file.exists():
        raise FileExistsError(
            f"ERROR: Output summary already exists, refusing to overwrite: {summary_file}"
        )

    out_path.mkdir(parents=True, exist_ok=True)

    # 1. Primary evaluation on fresh seeds 201..250
    summary_v3, per_case_v3 = evaluate_case_suite(
        cases_dir=planted_v3_dir,
        start_seed=201,
        end_seed=250,
    )

    # 2. Exploratory seen seeds 151..200
    summary_v2, per_case_v2 = evaluate_case_suite(
        cases_dir=planted_v2_dir,
        start_seed=151,
        end_seed=200,
    )

    summary_v3["exploratory_seen_seeds_151_200"] = summary_v2

    all_per_case = {**per_case_v3, **{f"v2_{k}": v for k, v in per_case_v2.items()}}

    run_info = {
        "bootstrap": {
            "n_resamples": 2000,
            "seed": 20261116,
        },
        "exploratory_seeds": list(range(151, 201)),
        "library_versions": {
            "networkx": nx.__version__,
            "numpy": np.__version__,
            "python": sys.version.split()[0],
        },
        "number_of_cases_evaluated": 50,
        "seeds_evaluated": list(range(201, 251)),
    }

    # Write outputs
    with summary_file.open("w", encoding="utf-8") as fh:
        json.dump(summary_v3, fh, indent=2, sort_keys=True)

    per_case_file = out_path / "per_case.json"
    with per_case_file.open("w", encoding="utf-8") as fh:
        json.dump(all_per_case, fh, indent=2, sort_keys=True)

    run_info_file = out_path / "run_info.json"
    with run_info_file.open("w", encoding="utf-8") as fh:
        json.dump(run_info, fh, indent=2, sort_keys=True)

    print(f"Evaluation complete. Saved outputs to {out_path}.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate call-layer network break on planted cases."
    )
    parser.add_argument(
        "--out-dir",
        default="data/graph/out/planted_eval_v3",
        help="Output directory.",
    )
    parser.add_argument(
        "--planted-v3",
        default="data/synthetic/out/planted_v3",
        help="Directory with planted v3 cases (seeds 201..250).",
    )
    parser.add_argument(
        "--planted-v2",
        default="data/synthetic/out/planted_v2",
        help="Directory with planted v2 cases (seeds 151..200).",
    )
    args = parser.parse_args(argv)

    try:
        run_evaluation(
            out_dir=args.out_dir,
            planted_v3_dir=args.planted_v3,
            planted_v2_dir=args.planted_v2,
        )
    except FileExistsError as err:
        print(str(err), file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
