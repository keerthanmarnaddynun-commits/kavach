"""Evaluate SUSPECT person merging and SAME_AS_CANDIDATE edges against answer keys."""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import statistics
import sys
from typing import Any


def _load_answer_keys(
    answer_key_dir: Path,
) -> tuple[dict[tuple[str, tuple[int, int]], str], dict[str, str]]:
    files = sorted(answer_key_dir.glob("FIR_*.json"))
    if not files:
        files = sorted(
            p
            for p in answer_key_dir.iterdir()
            if p.is_file() and p.suffix == ".json" and p.name != "index.json"
        )

    span_to_truth: dict[tuple[str, tuple[int, int]], str] = {}
    fir_to_split: dict[str, str] = {}

    for path in files:
        with path.open("r", encoding="utf-8") as fh:
            doc = json.load(fh)
        fir_id = str(doc["source_doc_id"])
        split = str(doc.get("split", "unknown"))
        fir_to_split[fir_id] = split

        for ent in doc.get("entities", []):
            if ent.get("type") != "PERSON":
                continue
            if ent.get("role") == "FATHER":
                continue
            tid = ent.get("truth_id")
            span = ent.get("char_span")
            if tid and isinstance(span, list) and len(span) == 2:
                span_to_truth[(fir_id, (int(span[0]), int(span[1])))] = str(tid)

    return span_to_truth, fir_to_split


def _compute_scope_metrics(
    entity_truths: list[tuple[str, str, str, str]],
    node_truth_map: dict[str, set[str]],
    candidate_edges: list[dict[str, Any]],
) -> dict[str, Any]:
    real_people = sorted({tid for tids in node_truth_map.values() for tid in tids})
    nodes_per_person: list[int] = []
    pairs_merged = 0
    pairs_not_merged = 0
    node_pairs_not_merged = 0

    for tid in real_people:
        by_node: dict[str, int] = defaultdict(int)
        for nid, _fid, _eid, unit_tid in entity_truths:
            if unit_tid == tid:
                by_node[nid] += 1
        nodes_for_tid = {nid for nid, tids in node_truth_map.items() if tid in tids}
        k = len(nodes_for_tid)
        nodes_per_person.append(k)

        total_entities = sum(by_node.values())
        merged = sum(cnt * (cnt - 1) // 2 for cnt in by_node.values())
        total_entity_pairs = total_entities * (total_entities - 1) // 2
        pairs_merged += merged
        pairs_not_merged += total_entity_pairs - merged
        node_pairs_not_merged += k * (k - 1) // 2

    if nodes_per_person:
        dist_stats = {
            "max": max(nodes_per_person),
            "median": statistics.median(nodes_per_person),
            "min": min(nodes_per_person),
        }
    else:
        dist_stats = {"max": 0, "median": 0, "min": 0}

    wrong_merges = sum(1 for tids in node_truth_map.values() if len(tids) > 1)

    cand_same = 0
    cand_diff = 0
    for edge in candidate_edges:
        src = edge.get("source")
        tgt = edge.get("target")
        if src in node_truth_map and tgt in node_truth_map:
            if node_truth_map[src] & node_truth_map[tgt]:
                cand_same += 1
            else:
                cand_diff += 1

    return {
        "nodes": len(node_truth_map),
        "nodes_per_real_person": dist_stats,
        "real_people": len(real_people),
        "same_as_candidate_different_people": cand_diff,
        "same_as_candidate_same_person": cand_same,
        "same_person_node_pairs_not_merged": node_pairs_not_merged,
        "same_person_pairs_merged": pairs_merged,
        "same_person_pairs_not_merged": pairs_not_merged,
        "wrong_merge_nodes": wrong_merges,
    }


def evaluate_person_merge(
    graph: dict[str, Any],
    answer_key_dir: str | Path,
) -> dict[str, Any]:
    """Compute SUSPECT merge quality metrics overall and by split."""
    span_to_truth, fir_to_split = _load_answer_keys(Path(answer_key_dir))

    overall_units: list[tuple[str, str, str, str]] = []
    overall_node_truths: dict[str, set[str]] = defaultdict(set)

    split_units: dict[str, list[tuple[str, str, str, str]]] = defaultdict(list)
    split_node_truths: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: defaultdict(set)
    )

    unmatched_mentions = 0

    for node in graph.get("nodes", []):
        if node.get("type") != "PERSON":
            continue
        roles = {str(r).upper() for r in node.get("roles", [])}
        if node.get("role"):
            roles.add(str(node["role"]).upper())
        if "SUSPECT" not in roles:
            continue

        nid = str(node["id"])
        for ev_idx, ev in enumerate(node.get("evidence_spans", [])):
            fid = str(ev["fir_id"])
            eid = str(ev.get("entity_id", f"ev_{ev_idx}"))
            split = fir_to_split.get(fid, "unknown")

            mentions = [
                m for m in ev.get("mentions", []) if m.get("kind") == "NAME"
            ]
            if not mentions and isinstance(ev.get("char_span"), list):
                mentions = [{"char_span": ev["char_span"], "kind": "NAME"}]

            ev_matched_tids: set[str] = set()
            for men in mentions:
                span = men.get("char_span")
                if not isinstance(span, list) or len(span) != 2:
                    continue
                key = (fid, (int(span[0]), int(span[1])))
                tid = span_to_truth.get(key)
                if tid is None:
                    unmatched_mentions += 1
                    continue
                ev_matched_tids.add(tid)
                overall_node_truths[nid].add(tid)
                split_node_truths[split][nid].add(tid)

            for tid in sorted(ev_matched_tids):
                unit = (nid, fid, eid, tid)
                overall_units.append(unit)
                split_units[split].append(unit)

    candidate_edges = [
        e
        for e in graph.get("edges", [])
        if e.get("relation") == "SAME_AS_CANDIDATE"
    ]

    overall_metrics = _compute_scope_metrics(
        overall_units, overall_node_truths, candidate_edges
    )

    splits_out: dict[str, Any] = {}
    for split_name in ("train", "dev", "test"):
        splits_out[split_name] = _compute_scope_metrics(
            split_units[split_name],
            split_node_truths[split_name],
            candidate_edges,
        )

    return {
        "by_split": splits_out,
        "overall": overall_metrics,
        "unmatched_name_mentions": unmatched_mentions,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate cross-FIR SUSPECT merging against answer keys."
    )
    parser.add_argument("graph_json", help="Path to graph.json")
    parser.add_argument("answer_key_dir", help="Path to answer-key FIR JSON directory")
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
        graph = json.load(fh)

    report = evaluate_person_merge(graph, Path(args.answer_key_dir))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

