"""Baseline rankings for kingpin identification on the analytics graph."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from networkx.algorithms.link_analysis import pagerank_alg

from case_analytics.scores import build_analytics_graph


def _format_ranking(
    scores: dict[str, float | int],
    names: dict[str, str],
    collapsed_members: dict[str, list[str]],
    score_key: str,
) -> list[dict[str, Any]]:
    ordered = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    ranking: list[dict[str, Any]] = []
    for idx, (pid, val) in enumerate(ordered, start=1):
        ranking.append(
            {
                "canonical_name": names.get(pid, ""),
                "collapsed_node_ids": collapsed_members.get(pid, [pid]),
                "node_id": pid,
                "rank": idx,
                score_key: round(val, 6) if isinstance(val, float) else val,
            }
        )
    return ranking


def compute_baselines(
    graph_data: dict[str, Any],
    mode: str = "strict",
) -> dict[str, Any]:
    """Compute all four baseline rankings on the same person set and mode."""
    G, meta = build_analytics_graph(graph_data, mode=mode)
    person_ids = sorted(
        str(nid) for nid, data in G.nodes(data=True) if data.get("type") == "PERSON"
    )
    person_set = set(person_ids)
    names = {pid: str(G.nodes[pid].get("canonical_name", "")) for pid in person_ids}
    collapsed_members = meta["collapsed_members"]
    rep_map = meta["rep_map"]

    node_types = {
        str(n["id"]): str(n.get("type", "")) for n in graph_data.get("nodes", [])
    }

    owned_phones: dict[str, set[str]] = defaultdict(set)
    controlled_accts: dict[str, set[str]] = defaultdict(set)
    cdr_comm_edges: list[tuple[str, str, int]] = []
    bank_tx_edges: list[tuple[str, str, int]] = []

    for edge in graph_data.get("edges", []):
        rel = edge.get("relation")
        src = str(edge.get("source"))
        tgt = str(edge.get("target"))

        if rel == "OWNS_DEVICE":
            if node_types.get(src) == "PERSON" and node_types.get(tgt) == "PHONE":
                p = rep_map.get(src, src)
                if p in person_set:
                    owned_phones[p].add(tgt)
            elif node_types.get(tgt) == "PERSON" and node_types.get(src) == "PHONE":
                p = rep_map.get(tgt, tgt)
                if p in person_set:
                    owned_phones[p].add(src)
        elif rel == "CONTROLS_ACCOUNT":
            if node_types.get(src) == "PERSON" and node_types.get(tgt) == "ACCOUNT":
                p = rep_map.get(src, src)
                if p in person_set:
                    controlled_accts[p].add(tgt)
            elif node_types.get(tgt) == "PERSON" and node_types.get(src) == "ACCOUNT":
                p = rep_map.get(tgt, tgt)
                if p in person_set:
                    controlled_accts[p].add(src)
        elif rel == "COMMUNICATED_WITH" and edge.get("source_kind") == "CSV":
            if "voice_count" in edge or "sms_count" in edge:
                cnt = int(edge.get("voice_count", 0)) + int(edge.get("sms_count", 0))
            else:
                cnt = int(edge.get("count", 0))
            cdr_comm_edges.append((src, tgt, cnt))
        elif rel == "TRANSFERRED_FUNDS" and edge.get("source_kind") == "CSV":
            paise = int(edge.get("total_amount_paise", 0))
            bank_tx_edges.append((src, tgt, paise))

    # Baseline 1: CDR call+SMS count over owned phones
    call_scores: dict[str, int] = {}
    for pid in person_ids:
        phones = owned_phones.get(pid, set())
        total_calls = sum(
            cnt
            for src, tgt, cnt in cdr_comm_edges
            if src in phones or tgt in phones
        )
        call_scores[pid] = total_calls

    # Baseline 2: Unweighted degree on the same analytics graph
    unweighted_deg_scores: dict[str, int] = {
        pid: int(G.degree(pid)) for pid in person_ids
    }

    # Baseline 3: Weighted PageRank on the same analytics graph
    if G.number_of_nodes() > 0 and G.number_of_edges() > 0:
        pr_all = pagerank_alg._pagerank_python(G, weight="weight")
        pagerank_scores: dict[str, float] = {
            pid: float(pr_all.get(pid, 0.0)) for pid in person_ids
        }
    else:
        pagerank_scores = {pid: 0.0 for pid in person_ids}

    # Baseline 4: Total bank transfer amount (paise) over controlled accounts
    transfer_scores: dict[str, int] = {}
    for pid in person_ids:
        accts = controlled_accts.get(pid, set())
        total_paise = sum(
            paise
            for src, tgt, paise in bank_tx_edges
            if src in accts or tgt in accts
        )
        transfer_scores[pid] = total_paise

    return {
        "baselines": {
            "call_count": _format_ranking(
                call_scores, names, collapsed_members, "score"
            ),
            "transfer_amount_paise": _format_ranking(
                transfer_scores, names, collapsed_members, "score"
            ),
            "unweighted_degree": _format_ranking(
                unweighted_deg_scores, names, collapsed_members, "score"
            ),
            "weighted_pagerank": _format_ranking(
                pagerank_scores, names, collapsed_members, "score"
            ),
        },
        "mode": mode,
        "person_nodes_ranked": len(person_ids),
    }

