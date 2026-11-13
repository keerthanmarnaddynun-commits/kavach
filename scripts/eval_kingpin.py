"""Evaluate strict/resolved kingpin rankings, baselines, and robustness."""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from case_analytics.scores import resolve_candidate_representatives  # noqa: E402
from scripts.eval_person_merge import _load_answer_keys  # noqa: E402


def _build_node_truth_maps(
    graph_data: dict[str, Any],
    answer_key_dir: Path,
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    span_to_truth, _ = _load_answer_keys(answer_key_dir)

    strict_map: dict[str, set[str]] = defaultdict(set)
    for node in graph_data.get("nodes", []):
        if node.get("type") != "PERSON":
            continue
        nid = str(node["id"])
        for ev in node.get("evidence_spans", []):
            fid = str(ev["fir_id"])
            mentions = [m for m in ev.get("mentions", []) if m.get("kind") == "NAME"]
            if not mentions and isinstance(ev.get("char_span"), list):
                mentions = [{"char_span": ev["char_span"], "kind": "NAME"}]
            for men in mentions:
                span = men.get("char_span")
                if isinstance(span, list) and len(span) == 2:
                    tid = span_to_truth.get((fid, (int(span[0]), int(span[1]))))
                    if tid:
                        strict_map[nid].add(tid)

    rep_map, _ = resolve_candidate_representatives(graph_data)
    resolved_map: dict[str, set[str]] = defaultdict(set)
    for nid, tids in strict_map.items():
        rep = rep_map.get(nid, nid)
        resolved_map[rep].update(tids)

    return dict(strict_map), dict(resolved_map)


def _extract_decoy_ids(truth_data: dict[str, Any]) -> set[str]:
    decoy_ids: set[str] = set()
    for key in ("decoy_ids", "decoy_person_ids"):
        for item in truth_data.get(key, []):
            if item:
                decoy_ids.add(str(item))
    for person in truth_data.get("people", []):
        if person.get("is_decoy"):
            pid = person.get("person_id") or person.get("id")
            if pid:
                decoy_ids.add(str(pid))
    return decoy_ids


def _score_ranking(
    ranking: list[dict[str, Any]],
    node_to_truths: dict[str, set[str]],
    kingpin_ids: list[str],
    decoy_ids: set[str],
) -> dict[str, Any]:
    kingpin_set = set(kingpin_ids)
    kingpin_ranks: dict[str, list[int]] = {kp: [] for kp in kingpin_ids}

    for entry in ranking:
        rank = int(entry["rank"])
        nid = str(entry["node_id"])
        tids = set(node_to_truths.get(nid, set()))
        for cid in entry.get("collapsed_node_ids", []):
            tids.update(node_to_truths.get(str(cid), set()))
        for kp in kingpin_ids:
            if kp in tids:
                kingpin_ranks[kp].append(rank)

    kingpin_best_rank = {
        kp: (min(ranks) if ranks else None) for kp, ranks in kingpin_ranks.items()
    }
    kingpin_node_counts = {kp: len(ranks) for kp, ranks in kingpin_ranks.items()}

    valid_best = [r for r in kingpin_best_rank.values() if r is not None]
    any_r1 = any(r == 1 for r in valid_best)
    any_top3 = any(r <= 3 for r in valid_best)
    any_top5 = any(r <= 5 for r in valid_best)
    all_top5 = len(valid_best) == len(kingpin_ids) and all(r <= 5 for r in valid_best)

    top5 = ranking[:5]
    top5_decoy_nodes = 0
    top5_non_kingpin_nodes = 0
    top5_non_kingpin_people: set[str] = set()
    top5_decoy_people: set[str] = set()

    for entry in top5:
        nid = str(entry["node_id"])
        tids = set(node_to_truths.get(nid, set()))
        for cid in entry.get("collapsed_node_ids", []):
            tids.update(node_to_truths.get(str(cid), set()))
        if not (tids & kingpin_set):
            top5_non_kingpin_nodes += 1
            for t in tids:
                top5_non_kingpin_people.add(t)
        if tids & decoy_ids:
            top5_decoy_nodes += 1
            for t in tids & decoy_ids:
                top5_decoy_people.add(t)

    return {
        "all_kingpins_top_5": all_top5,
        "any_kingpin_rank_1": any_r1,
        "any_kingpin_top_3": any_top3,
        "any_kingpin_top_5": any_top5,
        "kingpin_best_rank": kingpin_best_rank,
        "kingpin_node_counts": kingpin_node_counts,
        "top_5_decoy_nodes": top5_decoy_nodes,
        "top_5_decoy_people": len(top5_decoy_people),
        "top_5_non_kingpin_nodes": top5_non_kingpin_nodes,
        "top_5_non_kingpin_real_people": len(top5_non_kingpin_people),
    }


def _score_robustness(
    robustness_data: dict[str, Any],
    node_to_truths: dict[str, set[str]],
    kingpin_ids: list[str],
) -> dict[str, Any]:
    kingpin_set = set(kingpin_ids)
    samples = robustness_data.get("samples_top3", [])
    n_samples = len(samples)
    if n_samples == 0:
        return {
            "any_kingpin_rank_1_fraction": 0.0,
            "any_kingpin_top_3_fraction": 0.0,
            "n_samples": 0,
            "per_kingpin": {
                kp: {"rank_1_fraction": 0.0, "top_3_fraction": 0.0}
                for kp in kingpin_ids
            },
        }

    any_r1 = 0
    any_t3 = 0
    per_kp_r1: dict[str, int] = {kp: 0 for kp in kingpin_ids}
    per_kp_t3: dict[str, int] = {kp: 0 for kp in kingpin_ids}

    for top3_ids in samples:
        if top3_ids:
            r1_tids = node_to_truths.get(str(top3_ids[0]), set())
            if r1_tids & kingpin_set:
                any_r1 += 1
            for kp in r1_tids & kingpin_set:
                per_kp_r1[kp] += 1

        t3_tids: set[str] = set()
        for nid in top3_ids:
            t3_tids.update(node_to_truths.get(str(nid), set()))
        if t3_tids & kingpin_set:
            any_t3 += 1
        for kp in t3_tids & kingpin_set:
            per_kp_t3[kp] += 1

    return {
        "any_kingpin_rank_1_fraction": round(any_r1 / n_samples, 6),
        "any_kingpin_top_3_fraction": round(any_t3 / n_samples, 6),
        "n_samples": n_samples,
        "per_kingpin": {
            kp: {
                "rank_1_fraction": round(per_kp_r1[kp] / n_samples, 6),
                "top_3_fraction": round(per_kp_t3[kp] / n_samples, 6),
            }
            for kp in kingpin_ids
        },
    }


def evaluate_kingpin(
    analytics_dir: Path,
    graph_data: dict[str, Any],
    answer_key_dir: Path,
    truth_data: dict[str, Any],
) -> dict[str, Any]:
    """Score strict & resolved composite, baselines, and robustness vs truth."""
    strict_map, resolved_map = _build_node_truth_maps(graph_data, answer_key_dir)
    kingpin_ids = [str(x) for x in truth_data.get("kingpin_ids", [])]
    decoy_ids = _extract_decoy_ids(truth_data)

    results: dict[str, Any] = {
        "decoy_person_ids": sorted(decoy_ids),
        "kingpin_ids": kingpin_ids,
        "modes": {},
    }

    for mode, n_map in (("strict", strict_map), ("resolved", resolved_map)):
        with (analytics_dir / f"scores_{mode}.json").open("r", encoding="utf-8") as fh:
            scores_data = json.load(fh)
        with (analytics_dir / f"baselines_{mode}.json").open(
            "r", encoding="utf-8"
        ) as fh:
            baselines_data = json.load(fh)
        with (analytics_dir / f"robustness_{mode}.json").open(
            "r", encoding="utf-8"
        ) as fh:
            robustness_data = json.load(fh)

        rankers: dict[str, Any] = {
            "composite": _score_ranking(
                scores_data["ranking"], n_map, kingpin_ids, decoy_ids
            )
        }
        for bname, branking in baselines_data.get("baselines", {}).items():
            rankers[bname] = _score_ranking(branking, n_map, kingpin_ids, decoy_ids)

        results["modes"][mode] = {
            "rankers": rankers,
            "robustness": _score_robustness(robustness_data, n_map, kingpin_ids),
        }

    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate kingpin rankings and baselines against truth."
    )
    parser.add_argument("analytics_dir", help="Analytics output directory")
    parser.add_argument("graph_json", help="Path to graph.json")
    parser.add_argument("answer_key_dir", help="Path to answer-key FIR JSON directory")
    parser.add_argument("truth_json", help="Path to truth.json")
    parser.add_argument("out_json", help="Output evaluation JSON path")
    args = parser.parse_args(argv)

    out_path = Path(args.out_json)
    if out_path.exists():
        print(
            f"ERROR: Output file already exists, refusing to overwrite: {out_path}",
            file=sys.stderr,
        )
        return 1

    with Path(args.graph_json).open("r", encoding="utf-8") as fh:
        graph_data = json.load(fh)
    with Path(args.truth_json).open("r", encoding="utf-8") as fh:
        truth_data = json.load(fh)

    report = evaluate_kingpin(
        Path(args.analytics_dir),
        graph_data,
        Path(args.answer_key_dir),
        truth_data,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    with out_path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

