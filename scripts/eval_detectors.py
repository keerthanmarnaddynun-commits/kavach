"""Evaluation of mule detectors, burner detectors, and network-break min vertex cut.

Pre-registered hypotheses:
M1 mule_score has a higher precision@4 than the volume baseline.
M2 mule_score has a higher precision@4 than fan_in alone.
M3 the no_threshold variant is at least as good as random but may be worse than mule_score.
B1 burner_score has a higher precision@4 than both burner baselines.
C1 at coverage 1.0 with the true gangs given, the min vertex cut equals exactly the two bridge couriers in a majority of cases.
C2 that exact-match rate is higher than for the baseline "the two persons with highest betweenness".
C3 coverage 0.6 gives a lower exact-match rate than coverage 1.0.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import platform
import statistics
import sys
from typing import Any, Sequence

import networkx as nx
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from case_analytics.projection import build_person_projection
from case_detectors.burner import detect_burners
from case_detectors.cut import articulation_persons, detect_communities, min_vertex_cut
from case_detectors.mule import detect_mules
from case_simulation.v2 import build_planted_graph_v2


def _load_truth(truth_file: Path) -> dict[str, Any]:
    with truth_file.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _compute_auroc(scores: dict[str, float], true_set: set[str]) -> float:
    """Compute AUROC using average ranks for ties."""
    sorted_items = sorted(scores.items(), key=lambda kv: (kv[1], kv[0]))
    n = len(sorted_items)
    n_pos = len(true_set)
    n_neg = n - n_pos
    if n_pos == 0 or n_neg == 0:
        return 0.5

    ranks: dict[str, float] = {}
    i = 0
    while i < n:
        j = i
        while j < n and sorted_items[j][1] == sorted_items[i][1]:
            j += 1
        avg_rank = (i + 1 + j) / 2.0
        for k in range(i, j):
            ranks[sorted_items[k][0]] = avg_rank
        i = j

    sum_ranks_pos = sum(ranks[item] for item in true_set if item in ranks)
    u = sum_ranks_pos - (n_pos * (n_pos + 1)) / 2.0
    return float(u / (n_pos * n_neg))


def _compute_mean_rank(scores: dict[str, float], true_set: set[str]) -> float:
    """Compute mean 1-based rank of true items (descending score, average ranks for ties)."""
    sorted_items = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    n = len(sorted_items)
    if not true_set:
        return 0.0

    ranks: dict[str, float] = {}
    i = 0
    while i < n:
        j = i
        while j < n and sorted_items[j][1] == sorted_items[i][1]:
            j += 1
        avg_rank = (i + 1 + j) / 2.0
        for k in range(i, j):
            ranks[sorted_items[k][0]] = avg_rank
        i = j

    present_ranks = [ranks[item] for item in true_set if item in ranks]
    if not present_ranks:
        return float(n)
    return float(statistics.mean(present_ranks))


def _compute_ranking_metrics(
    scores: dict[str, float],
    true_set: set[str],
) -> dict[str, float]:
    sorted_items = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    top4 = [kv[0] for kv in sorted_items[:4]]
    top8 = [kv[0] for kv in sorted_items[:8]]

    prec4 = len(set(top4) & true_set) / 4.0
    rec8 = len(set(top8) & true_set) / len(true_set) if true_set else 0.0
    mean_rank = _compute_mean_rank(scores, true_set)
    auroc = _compute_auroc(scores, true_set)

    return {
        "auroc": round(auroc, 6),
        "mean_rank": round(mean_rank, 4),
        "precision_at_4": round(prec4, 6),
        "recall_at_8": round(rec8, 6),
    }


def _run_bootstrap_mean(
    values: list[float],
    n_resamples: int = 2000,
    seed: int = 20261115,
) -> dict[str, Any]:
    arr = np.asarray(values, dtype=np.float64)
    N = len(arr)
    if N == 0:
        return {"bootstrap_95": [0.0, 0.0], "mean": 0.0, "median": 0.0}

    mean_val = float(np.mean(arr))
    med_val = float(np.median(arr))

    rng = np.random.RandomState(seed)
    matrix = rng.randint(0, N, size=(n_resamples, N))
    boot_means = arr[matrix].mean(axis=1)
    ci_low, ci_high = np.percentile(boot_means, [2.5, 97.5])

    return {
        "bootstrap_95": [round(float(ci_low), 6), round(float(ci_high), 6)],
        "mean": round(mean_val, 6),
        "median": round(med_val, 6),
    }


def _run_paired_bootstrap(
    vals_comp: list[float],
    vals_base: list[float],
    n_resamples: int = 2000,
    seed: int = 20261115,
) -> dict[str, Any]:
    c_arr = np.asarray(vals_comp, dtype=np.float64)
    b_arr = np.asarray(vals_base, dtype=np.float64)
    N = len(c_arr)
    if N == 0:
        return {"ci_95": [0.0, 0.0], "mean_diff": 0.0}

    d = c_arr - b_arr
    mean_diff = float(np.mean(d))

    rng = np.random.RandomState(seed)
    matrix = rng.randint(0, N, size=(n_resamples, N))
    boot_diffs = d[matrix].mean(axis=1)
    ci_low, ci_high = np.percentile(boot_diffs, [2.5, 97.5])

    return {
        "ci_95": [round(float(ci_low), 6), round(float(ci_high), 6)],
        "mean_diff": round(mean_diff, 6),
    }


def evaluate_detectors(
    planted_dir: str | Path = "data/synthetic/out/planted_v2",
    demo_dir: str | Path = "data/synthetic/out/case_demo_v2",
    out_dir: str | Path = "data/graph/out/detectors_eval_v1",
    attributions_file: str | Path = "data/graph/out/planted_eval_v2/attributions.json",
    config_file: str | Path = "config/detector_defaults.json",
) -> dict[str, Any]:
    out_path = Path(out_dir)
    if out_path.exists():
        raise FileExistsError(
            f"ERROR: Output directory already exists, refusing to overwrite: {out_path}"
        )

    planted_path = Path(planted_dir)
    case_dirs = sorted(
        [d for d in planted_path.iterdir() if d.is_dir() and d.name.startswith("seed_")],
        key=lambda d: int(d.name.split("_")[-1]) if d.name.split("_")[-1].isdigit() else d.name,
    )

    with Path(config_file).open("r", encoding="utf-8") as fh:
        config = json.load(fh)

    with Path(attributions_file).open("r", encoding="utf-8") as fh:
        saved_attributions = json.load(fh)

    per_case_report: dict[str, Any] = {}

    # Accumulators for mules across 50 cases: ranker -> list of metrics
    mule_metric_acc: dict[str, dict[str, list[float]]] = {
        r: defaultdict(list)
        for r in ("mule_score", "no_threshold", "volume", "fan_in", "random")
    }

    # Accumulators for burners across 50 cases: ranker -> list of metrics
    burner_metric_acc: dict[str, dict[str, list[float]]] = {
        r: defaultdict(list)
        for r in ("burner_score", "fewest_calls", "latest_first_appearance", "random")
    }

    # Cut metric accumulators: coverage -> {true_gangs: [...], comms: [...]}
    cut_acc: dict[str, dict[str, list[dict[str, Any]]]] = {
        "0.6": {"comms": [], "true_gangs": []},
        "1.0": {"comms": [], "true_gangs": []},
    }
    art_courier_share_acc: list[float] = []

    for cd in case_dirs:
        case_name = cd.name
        seed_num = int(case_name.split("_")[-1])
        truth = _load_truth(cd / "truth.json")

        true_mules = set(truth.get("mule_accounts", []))
        true_burners = set(truth.get("burner_phones", []))

        # --- 1. MULE EVALUATION ---
        mule_leads = detect_mules(cd / "bank.csv", config=config)
        mule_scores = {lead["id"]: float(lead["score"]) for lead in mule_leads}
        no_thresh_scores = {
            lead["id"]: float(lead["features"]["score_no_threshold"]) for lead in mule_leads
        }
        volume_scores = {
            lead["id"]: float(lead["features"]["volume_paise"]) for lead in mule_leads
        }
        fan_in_scores = {
            lead["id"]: float(lead["features"]["fan_in"]) for lead in mule_leads
        }

        n_accs = len(mule_leads)
        random_mule_prec4 = (4.0 / n_accs) if n_accs > 0 else 0.0

        m_mule = _compute_ranking_metrics(mule_scores, true_mules)
        m_no_th = _compute_ranking_metrics(no_thresh_scores, true_mules)
        m_vol = _compute_ranking_metrics(volume_scores, true_mules)
        m_fan = _compute_ranking_metrics(fan_in_scores, true_mules)

        for metric in ("precision_at_4", "recall_at_8", "mean_rank", "auroc"):
            mule_metric_acc["mule_score"][metric].append(m_mule[metric])
            mule_metric_acc["no_threshold"][metric].append(m_no_th[metric])
            mule_metric_acc["volume"][metric].append(m_vol[metric])
            mule_metric_acc["fan_in"][metric].append(m_fan[metric])

        # Random baseline: expected precision@4 is 4/N, recall@8 is 8/N, mean_rank is (N+1)/2, auroc is 0.5
        mule_metric_acc["random"]["precision_at_4"].append(random_mule_prec4)
        mule_metric_acc["random"]["recall_at_8"].append(min(1.0, 8.0 / n_accs) if n_accs > 0 else 0.0)
        mule_metric_acc["random"]["mean_rank"].append((n_accs + 1.0) / 2.0)
        mule_metric_acc["random"]["auroc"].append(0.5)

        # --- 2. BURNER EVALUATION ---
        burner_leads = detect_burners(cd / "cdr.csv", config=config)
        burner_scores = {lead["id"]: float(lead["score"]) for lead in burner_leads}
        # Fewest calls: negative calls so highest score has fewest calls
        fewest_calls_scores = {
            lead["id"]: -float(lead["features"]["total_calls"]) for lead in burner_leads
        }
        latest_act_scores = {
            lead["id"]: float(lead["features"]["first_seen_day"]) for lead in burner_leads
        }

        n_phones = len(burner_leads)
        random_burner_prec4 = (4.0 / n_phones) if n_phones > 0 else 0.0

        b_burner = _compute_ranking_metrics(burner_scores, true_burners)
        b_fewest = _compute_ranking_metrics(fewest_calls_scores, true_burners)
        b_latest = _compute_ranking_metrics(latest_act_scores, true_burners)

        for metric in ("precision_at_4", "recall_at_8", "mean_rank", "auroc"):
            burner_metric_acc["burner_score"][metric].append(b_burner[metric])
            burner_metric_acc["fewest_calls"][metric].append(b_fewest[metric])
            burner_metric_acc["latest_first_appearance"][metric].append(b_latest[metric])

        burner_metric_acc["random"]["precision_at_4"].append(random_burner_prec4)
        burner_metric_acc["random"]["recall_at_8"].append(min(1.0, 8.0 / n_phones) if n_phones > 0 else 0.0)
        burner_metric_acc["random"]["mean_rank"].append((n_phones + 1.0) / 2.0)
        burner_metric_acc["random"]["auroc"].append(0.5)

        case_cut_records: dict[str, Any] = {}

        # --- 3. CUT & NETWORK BREAK EVALUATION ---
        gang_a_truth_ids = [
            str(p["person_id"]) for p in truth.get("people", []) if p.get("gang") == "GANG_A"
        ]
        gang_b_truth_ids = [
            str(p["person_id"]) for p in truth.get("people", []) if p.get("gang") == "GANG_B"
        ]
        courier_truth_ids = [str(x) for x in truth.get("bridge_courier_ids", [])]

        for cov_str, cov_idx in (("0.6", 1), ("1.0", 2)):
            cov_val = float(cov_str)

            # Build graph with opaque IDs using deterministic builder
            graph, truth_to_opaque, _ = build_planted_graph_v2(
                case_dir=cd,
                coverage=cov_val,
                seed=seed_num,
                coverage_index=cov_idx,
            )

            # Node sets
            cr1_op = truth_to_opaque.get("PER_CR_01")
            cr2_op = truth_to_opaque.get("PER_CR_02")
            expected_cut_set = {cr for cr in (cr1_op, cr2_op) if cr is not None}
            decoy_op = truth_to_opaque.get("DEC_PIZZA_01")

            gang_a_nodes = [
                truth_to_opaque[pid] for pid in gang_a_truth_ids if pid in truth_to_opaque
            ]
            gang_b_nodes = [
                truth_to_opaque[pid] for pid in gang_b_truth_ids if pid in truth_to_opaque
            ]

            # 3a. True gangs cut
            cut_res = min_vertex_cut(graph, gang_a_nodes, gang_b_nodes)
            is_skipped = cut_res.get("skipped") == "empty_group"
            is_finite = cut_res.get("finite", False)
            cut_list = cut_res.get("cut", []) if is_finite else []
            cut_set = set(cut_list)

            exact_match = (
                is_finite
                and len(expected_cut_set) == 2
                and cut_set == expected_cut_set
            )
            has_cr1 = cr1_op in cut_set if cr1_op else False
            has_cr2 = cr2_op in cut_set if cr2_op else False
            has_decoy = decoy_op in cut_set if decoy_op else False
            non_courier_count = len(cut_set - expected_cut_set) if is_finite else 0

            # Baseline: two highest betweenness in person projection
            G_proj, _, _ = build_person_projection(graph)
            base_bet_match = False
            if G_proj.number_of_nodes() >= 2:
                raw_B = nx.betweenness_centrality(G_proj, weight="distance", normalized=True)
                sorted_B = sorted(raw_B.items(), key=lambda kv: (-round(float(kv[1]), 9), kv[0]))
                # Check for tie at position 2
                s1 = round(float(sorted_B[0][1]), 9)
                s2 = round(float(sorted_B[1][1]), 9)
                s3 = round(float(sorted_B[2][1]), 9) if len(sorted_B) > 2 else -1.0

                if s1 > s2 and s2 > s3:
                    top2_bet = {sorted_B[0][0], sorted_B[1][0]}
                    base_bet_match = (len(expected_cut_set) == 2 and top2_bet == expected_cut_set)
                elif s1 == s2 and s2 > s3:
                    top2_bet = {sorted_B[0][0], sorted_B[1][0]}
                    base_bet_match = (len(expected_cut_set) == 2 and top2_bet == expected_cut_set)
                else:
                    base_bet_match = False

            true_gang_record = {
                "avg_non_courier_persons": non_courier_count,
                "baseline_betweenness_exact": base_bet_match,
                "cut_size": cut_res.get("size") if is_finite else None,
                "exact_couriers": exact_match,
                "finite": is_finite,
                "has_cr1": has_cr1,
                "has_cr2": has_cr2,
                "has_decoy": has_decoy,
                "skipped": is_skipped,
            }
            cut_acc[cov_str]["true_gangs"].append(true_gang_record)

            # 3b. Community detection variant
            comms = detect_communities(graph, seed=20261115)
            if len(comms) >= 2:
                comm_a = comms[0]
                comm_b = comms[1]
                comm_cut_res = min_vertex_cut(graph, comm_a, comm_b)
                comm_finite = comm_cut_res.get("finite", False)
                comm_cut_set = set(comm_cut_res.get("cut", [])) if comm_finite else set()

                comm_exact = (
                    comm_finite
                    and len(expected_cut_set) == 2
                    and comm_cut_set == expected_cut_set
                )
                comm_has_cr1 = cr1_op in comm_cut_set if cr1_op else False
                comm_has_cr2 = cr2_op in comm_cut_set if cr2_op else False
                comm_has_decoy = decoy_op in comm_cut_set if decoy_op else False
                comm_non_cr = len(comm_cut_set - expected_cut_set) if comm_finite else 0

                # Adjusted agreement of communities with True Gang A
                gang_a_set = set(gang_a_nodes)
                if gang_a_set:
                    best_match_frac = max(
                        len(set(c) & gang_a_set) / len(gang_a_set) for c in comms
                    )
                else:
                    best_match_frac = 0.0

                comm_record = {
                    "adjusted_agreement_gang_a": round(best_match_frac, 4),
                    "avg_non_courier_persons": comm_non_cr,
                    "cut_size": comm_cut_res.get("size") if comm_finite else None,
                    "exact_couriers": comm_exact,
                    "finite": comm_finite,
                    "has_cr1": comm_has_cr1,
                    "has_cr2": comm_has_cr2,
                    "has_decoy": comm_has_decoy,
                    "skipped": False,
                }
            else:
                comm_record = {
                    "adjusted_agreement_gang_a": 0.0,
                    "avg_non_courier_persons": 0,
                    "cut_size": None,
                    "exact_couriers": False,
                    "finite": False,
                    "has_cr1": False,
                    "has_cr2": False,
                    "has_decoy": False,
                    "skipped": True,
                }
            cut_acc[cov_str]["comms"].append(comm_record)

            # 3c. Articulation points at coverage 1.0
            if cov_str == "1.0":
                art_items = articulation_persons(graph)
                art_ids = {item["node_id"] for item in art_items}
                cr_present = [cr for cr in (cr1_op, cr2_op) if cr is not None]
                n_cr_art = sum(1 for cr in cr_present if cr in art_ids)
                share_cr_art = (n_cr_art / len(cr_present)) if cr_present else 0.0
                art_courier_share_acc.append(share_cr_art)
                case_cut_records["articulation_couriers_share"] = round(share_cr_art, 4)

            case_cut_records[f"cov_{cov_str}"] = {
                "communities_variant": comm_record,
                "true_gangs": true_gang_record,
            }

        per_case_report[case_name] = {
            "burners": {
                "burner_score": b_burner,
                "fewest_calls": b_fewest,
                "latest_first_appearance": b_latest,
                "random": {"precision_at_4": round(random_burner_prec4, 6)},
            },
            "cut": case_cut_records,
            "mules": {
                "fan_in": m_fan,
                "mule_score": m_mule,
                "no_threshold": m_no_th,
                "random": {"precision_at_4": round(random_mule_prec4, 6)},
                "volume": m_vol,
            },
        }

    # Evaluate case_demo_v2 as single case reference
    demo_truth = _load_truth(Path(demo_dir) / "truth.json")
    demo_true_mules = set(demo_truth.get("mule_accounts", []))
    demo_true_burners = set(demo_truth.get("burner_phones", []))

    demo_mule_leads = detect_mules(Path(demo_dir) / "bank.csv", config=config)
    demo_m_scores = {lead["id"]: float(lead["score"]) for lead in demo_mule_leads}
    demo_m_no_th = {
        lead["id"]: float(lead["features"]["score_no_threshold"]) for lead in demo_mule_leads
    }
    demo_m_vol = {
        lead["id"]: float(lead["features"]["volume_paise"]) for lead in demo_mule_leads
    }
    demo_m_fan = {
        lead["id"]: float(lead["features"]["fan_in"]) for lead in demo_mule_leads
    }
    demo_m_rand_p4 = 4.0 / len(demo_mule_leads)

    demo_burner_leads = detect_burners(Path(demo_dir) / "cdr.csv", config=config)
    demo_b_scores = {lead["id"]: float(lead["score"]) for lead in demo_burner_leads}
    demo_b_few = {
        lead["id"]: -float(lead["features"]["total_calls"]) for lead in demo_burner_leads
    }
    demo_b_lat = {
        lead["id"]: float(lead["features"]["first_seen_day"]) for lead in demo_burner_leads
    }
    demo_b_rand_p4 = 4.0 / len(demo_burner_leads)

    demo_results = {
        "burners": {
            "burner_score": _compute_ranking_metrics(demo_b_scores, demo_true_burners),
            "fewest_calls": _compute_ranking_metrics(demo_b_few, demo_true_burners),
            "latest_first_appearance": _compute_ranking_metrics(demo_b_lat, demo_true_burners),
            "random": {"precision_at_4": round(demo_b_rand_p4, 6)},
        },
        "mules": {
            "fan_in": _compute_ranking_metrics(demo_m_fan, demo_true_mules),
            "mule_score": _compute_ranking_metrics(demo_m_scores, demo_true_mules),
            "no_threshold": _compute_ranking_metrics(demo_m_no_th, demo_true_mules),
            "random": {"precision_at_4": round(demo_m_rand_p4, 6)},
            "volume": _compute_ranking_metrics(demo_m_vol, demo_true_mules),
        },
    }
    per_case_report["case_demo_v2"] = demo_results

    # Summary aggregations
    N_cases = len(case_dirs)

    # 1. Mule Summary
    mule_summary: dict[str, Any] = {}
    for r_name in ("mule_score", "no_threshold", "volume", "fan_in", "random"):
        mule_summary[r_name] = {}
        for metric in ("precision_at_4", "recall_at_8", "mean_rank", "auroc"):
            vals = mule_metric_acc[r_name][metric]
            mule_summary[r_name][metric] = _run_bootstrap_mean(vals, seed=20261115)

    # Paired bootstrap precision@4 differences (mule_score - baseline)
    mule_paired_bootstrap: dict[str, Any] = {}
    mule_p4 = mule_metric_acc["mule_score"]["precision_at_4"]
    for base in ("volume", "fan_in", "no_threshold", "random"):
        base_p4 = mule_metric_acc[base]["precision_at_4"]
        mule_paired_bootstrap[base] = _run_paired_bootstrap(
            mule_p4, base_p4, n_resamples=2000, seed=20261115
        )

    # 2. Burner Summary
    burner_summary: dict[str, Any] = {}
    for r_name in ("burner_score", "fewest_calls", "latest_first_appearance", "random"):
        burner_summary[r_name] = {}
        for metric in ("precision_at_4", "recall_at_8", "mean_rank", "auroc"):
            vals = burner_metric_acc[r_name][metric]
            burner_summary[r_name][metric] = _run_bootstrap_mean(vals, seed=20261115)

    # Paired bootstrap precision@4 differences (burner_score - baseline)
    burner_paired_bootstrap: dict[str, Any] = {}
    burner_p4 = burner_metric_acc["burner_score"]["precision_at_4"]
    for base in ("fewest_calls", "latest_first_appearance", "random"):
        base_p4 = burner_metric_acc[base]["precision_at_4"]
        burner_paired_bootstrap[base] = _run_paired_bootstrap(
            burner_p4, base_p4, n_resamples=2000, seed=20261115
        )

    # 3. Cut Summary
    cut_summary: dict[str, Any] = {}
    for cov_str in ("0.6", "1.0"):
        tg_recs = cut_acc[cov_str]["true_gangs"]
        comm_recs = cut_acc[cov_str]["comms"]

        # Distribution of cut sizes
        cut_sizes = [r["cut_size"] for r in tg_recs if r["cut_size"] is not None]
        cut_size_dist = {
            str(k): sum(1 for sz in cut_sizes if sz == k)
            for k in sorted(set(cut_sizes))
        }

        cut_summary[cov_str] = {
            "communities_variant": {
                "adjusted_agreement_gang_a": round(
                    statistics.mean(r["adjusted_agreement_gang_a"] for r in comm_recs), 4
                ),
                "avg_non_courier_persons": round(
                    statistics.mean(r["avg_non_courier_persons"] for r in comm_recs), 4
                ),
                "share_containing_cr1": round(
                    sum(1 for r in comm_recs if r["has_cr1"]) / N_cases, 4
                ),
                "share_containing_cr2": round(
                    sum(1 for r in comm_recs if r["has_cr2"]) / N_cases, 4
                ),
                "share_containing_decoy": round(
                    sum(1 for r in comm_recs if r["has_decoy"]) / N_cases, 4
                ),
                "share_exact_couriers": round(
                    sum(1 for r in comm_recs if r["exact_couriers"]) / N_cases, 4
                ),
                "share_finite_cut": round(
                    sum(1 for r in comm_recs if r["finite"]) / N_cases, 4
                ),
            },
            "true_gangs": {
                "avg_non_courier_persons": round(
                    statistics.mean(r["avg_non_courier_persons"] for r in tg_recs), 4
                ),
                "baseline_betweenness_exact_share": round(
                    sum(1 for r in tg_recs if r["baseline_betweenness_exact"]) / N_cases, 4
                ),
                "cases_skipped": sum(1 for r in tg_recs if r["skipped"]),
                "distribution_cut_size": cut_size_dist,
                "share_containing_cr1": round(
                    sum(1 for r in tg_recs if r["has_cr1"]) / N_cases, 4
                ),
                "share_containing_cr2": round(
                    sum(1 for r in tg_recs if r["has_cr2"]) / N_cases, 4
                ),
                "share_containing_decoy": round(
                    sum(1 for r in tg_recs if r["has_decoy"]) / N_cases, 4
                ),
                "share_exact_couriers": round(
                    sum(1 for r in tg_recs if r["exact_couriers"]) / N_cases, 4
                ),
                "share_finite_cut": round(
                    sum(1 for r in tg_recs if r["finite"]) / N_cases, 4
                ),
            },
        }

    cut_summary["coverage_1_0_articulation_couriers_share"] = round(
        statistics.mean(art_courier_share_acc), 4
    )

    summary_report = {
        "burners": {
            "metrics": burner_summary,
            "paired_bootstrap_precision_at_4": burner_paired_bootstrap,
        },
        "case_demo_v2": demo_results,
        "cut": cut_summary,
        "mules": {
            "metrics": mule_summary,
            "paired_bootstrap_precision_at_4": mule_paired_bootstrap,
        },
    }

    run_info = {
        "bootstrap": {
            "n_resamples": 2000,
            "seed": 20261115,
        },
        "config": config,
        "library_versions": {
            "networkx": nx.__version__,
            "numpy": np.__version__,
            "python": platform.python_version(),
        },
        "number_of_cases_evaluated": N_cases,
        "seeds": [int(cd.name.split("_")[-1]) for cd in case_dirs],
    }

    out_path.mkdir(parents=True, exist_ok=False)

    with (out_path / "per_case.json").open("w", encoding="utf-8") as fh:
        json.dump(per_case_report, fh, indent=2, sort_keys=True)

    with (out_path / "run_info.json").open("w", encoding="utf-8") as fh:
        json.dump(run_info, fh, indent=2, sort_keys=True)

    with (out_path / "summary.json").open("w", encoding="utf-8") as fh:
        json.dump(summary_report, fh, indent=2, sort_keys=True)

    return summary_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run evaluation of mule, burner, and cut detectors."
    )
    parser.add_argument(
        "--planted-dir",
        default="data/synthetic/out/planted_v2",
        help="Directory with planted cases (seeds 151..200).",
    )
    parser.add_argument(
        "--demo-dir",
        default="data/synthetic/out/case_demo_v2",
        help="Directory with case_demo_v2.",
    )
    parser.add_argument(
        "--out-dir",
        default="data/graph/out/detectors_eval_v1",
        help="Directory to save evaluation results.",
    )
    args = parser.parse_args(argv)

    try:
        report = evaluate_detectors(
            planted_dir=args.planted_dir,
            demo_dir=args.demo_dir,
            out_dir=args.out_dir,
        )
    except FileExistsError as err:
        print(str(err), file=sys.stderr)
        return 1

    print("Detectors evaluation completed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
