"""Person-to-person graph projection, structural centrality, and composite scoring."""

from __future__ import annotations

from collections import defaultdict
import math
from typing import Any

import networkx as nx
import numpy as np


def compute_pessimistic_ranks(scores: dict[str, float | int]) -> dict[str, int]:
    """Compute pessimistic rank for each person.

    Score is rounded to 9 decimal places;
    rank(i) = 1 + number of OTHER persons with score >= person i's.
    Tied persons all receive the worst rank of their tie group.
    Ties are never broken by identifier.
    """
    rounded = {pid: round(float(val), 9) for pid, val in scores.items()}
    ranks: dict[str, int] = {}
    for pid, s_i in rounded.items():
        count_ge = sum(
            1 for other_pid, s_j in rounded.items() if other_pid != pid and s_j >= s_i
        )
        ranks[pid] = 1 + count_ge
    return ranks


def build_person_projection(
    graph_data: dict[str, Any],
) -> tuple[nx.Graph, dict[str, float], dict[str, int]]:
    """Build undirected person-to-person projection graph and financial control values.

    Returns:
        (G, norm_financial_control, raw_financial_paise)
    """
    person_ids = sorted(
        str(n["id"]) for n in graph_data.get("nodes", []) if n.get("type") == "PERSON"
    )
    person_set = set(person_ids)

    owners: dict[str, set[str]] = defaultdict(set)
    controllers: dict[str, set[str]] = defaultdict(set)
    controlled_accounts_by_person: dict[str, set[str]] = defaultdict(set)

    for edge in graph_data.get("edges", []):
        rel = edge.get("relation")
        src = str(edge.get("source"))
        tgt = str(edge.get("target"))

        if rel == "OWNS_DEVICE":
            if src in person_set:
                owners[tgt].add(src)
            elif tgt in person_set:
                owners[src].add(tgt)
        elif rel == "CONTROLS_ACCOUNT":
            if src in person_set:
                controllers[tgt].add(src)
                controlled_accounts_by_person[src].add(tgt)
            elif tgt in person_set:
                controllers[src].add(tgt)
                controlled_accounts_by_person[tgt].add(src)

    pair_weights: dict[tuple[str, str], float] = defaultdict(float)

    def add_pair_weight(p1: str, p2: str, delta: float) -> None:
        if p1 == p2 or delta <= 0.0:
            return
        key = (p1, p2) if p1 < p2 else (p2, p1)
        pair_weights[key] += delta

    # 1. Calls and SMS from CSV COMMUNICATED_WITH edges between owned phones
    for edge in graph_data.get("edges", []):
        if (
            edge.get("relation") == "COMMUNICATED_WITH"
            and edge.get("source_kind") == "CSV"
        ):
            u = str(edge.get("source"))
            v = str(edge.get("target"))
            calls = int(
                edge.get("voice_count", edge.get("call_count", edge.get("count", 0)))
            )
            sms = int(edge.get("sms_count", 0))
            comms = calls + sms
            w_comm = 1.5 * math.log2(1.0 + comms)
            for a in owners.get(u, set()):
                for b in owners.get(v, set()):
                    if a != b:
                        add_pair_weight(a, b, w_comm)

    # 2. Bank transactions from CSV TRANSFERRED_FUNDS edges between controlled accounts
    for edge in graph_data.get("edges", []):
        if (
            edge.get("relation") == "TRANSFERRED_FUNDS"
            and edge.get("source_kind") == "CSV"
        ):
            u = str(edge.get("source"))
            v = str(edge.get("target"))
            txns = int(edge.get("txn_count", edge.get("count", 1)))
            w_tx = 1.0 * math.log2(1.0 + txns)
            for a in controllers.get(u, set()):
                for b in controllers.get(v, set()):
                    if a != b:
                        add_pair_weight(a, b, w_tx)

    # 3. Two persons sharing a controlled account: add 3.0
    for acct, ctrls in controllers.items():
        sorted_ctrls = sorted(ctrls)
        n_ctrls = len(sorted_ctrls)
        for i in range(n_ctrls):
            for j in range(i + 1, n_ctrls):
                add_pair_weight(sorted_ctrls[i], sorted_ctrls[j], 3.0)

    # 4. Two persons sharing an owned phone: add 1.5
    for phone, owns in owners.items():
        sorted_owns = sorted(owns)
        n_owns = len(sorted_owns)
        for i in range(n_owns):
            for j in range(i + 1, n_owns):
                add_pair_weight(sorted_owns[i], sorted_owns[j], 1.5)

    # Build undirected projection graph
    G = nx.Graph()
    G.add_nodes_from(person_ids)
    for (a, b), w in pair_weights.items():
        if w > 0.0:
            G.add_edge(a, b, weight=w, distance=1.0 / w)

    # Financial control: sum over controlled accounts of paise sent + paise received
    acct_sent_paise: dict[str, int] = defaultdict(int)
    acct_rec_paise: dict[str, int] = defaultdict(int)
    for edge in graph_data.get("edges", []):
        if (
            edge.get("relation") == "TRANSFERRED_FUNDS"
            and edge.get("source_kind") == "CSV"
        ):
            u = str(edge.get("source"))
            v = str(edge.get("target"))
            paise = int(edge.get("total_amount_paise", 0))
            acct_sent_paise[u] += paise
            acct_rec_paise[v] += paise

    raw_financial_paise: dict[str, int] = {}
    for pid in person_ids:
        my_accts = controlled_accounts_by_person.get(pid, set())
        total_p = sum(
            acct_sent_paise.get(acc, 0) + acct_rec_paise.get(acc, 0)
            for acc in my_accts
        )
        raw_financial_paise[pid] = total_p

    max_fin = max(raw_financial_paise.values()) if raw_financial_paise else 0
    norm_financial: dict[str, float] = {}
    for pid in person_ids:
        norm_financial[pid] = (
            (raw_financial_paise[pid] / max_fin) if max_fin > 0 else 0.0
        )

    return G, norm_financial, raw_financial_paise


def compute_projection_scores(graph_data: dict[str, Any]) -> dict[str, Any]:
    """Compute projection-based structural metrics, financial control, and composites."""
    person_ids = sorted(
        str(n["id"]) for n in graph_data.get("nodes", []) if n.get("type") == "PERSON"
    )
    G, norm_financial, raw_financial_paise = build_person_projection(graph_data)

    if not person_ids:
        return {
            "eigenvector_converged": True,
            "person_ids": [],
            "raw_scores": {
                "composite_v2": {},
                "financial_only": {},
                "projection_only": {},
            },
            "pessimistic_ranks": {
                "composite_v2": {},
                "financial_only": {},
                "projection_only": {},
            },
            "components": {
                "betweenness": {},
                "degree": {},
                "eigenvector": {},
                "financial": {},
            },
        }

    # 1. Degree (weighted strength)
    raw_D: dict[str, float] = {
        pid: float(G.degree(pid, weight="weight")) for pid in person_ids
    }

    # 2. Betweenness (weight=distance)
    raw_B: dict[str, float] = nx.betweenness_centrality(
        G, weight="distance", normalized=True
    )
    for pid in person_ids:
        if pid not in raw_B:
            raw_B[pid] = 0.0

    # 3. Eigenvector centrality
    ev_converged = True
    if G.number_of_edges() == 0:
        raw_E: dict[str, float] = {pid: 1.0 / len(person_ids) for pid in person_ids}
    else:
        try:
            raw_E = nx.eigenvector_centrality(G, weight="weight", max_iter=1000)
        except (nx.PowerIterationFailedConvergence, nx.NetworkXException):
            ev_converged = False
            try:
                raw_E = nx.eigenvector_centrality_numpy(G, weight="weight")
            except Exception:
                nodes = list(G.nodes())
                adj = nx.to_numpy_array(G, nodelist=nodes, weight="weight")
                vals, vecs = np.linalg.eigh(adj)
                idx = int(np.argmax(vals))
                top_vec = np.abs(vecs[:, idx])
                norm_c = float(np.linalg.norm(top_vec))
                if norm_c > 0:
                    top_vec = top_vec / norm_c
                raw_E = {nodes[i]: float(top_vec[i]) for i in range(len(nodes))}

    for pid in person_ids:
        if pid not in raw_E:
            raw_E[pid] = 0.0

    # Normalise D, B, E by maximum over ranked persons
    max_D = max(raw_D.values()) if raw_D else 0.0
    norm_D = {pid: (raw_D[pid] / max_D) if max_D > 0.0 else 0.0 for pid in person_ids}

    max_B = max(raw_B.values()) if raw_B else 0.0
    norm_B = {pid: (raw_B[pid] / max_B) if max_B > 0.0 else 0.0 for pid in person_ids}

    max_E = max(raw_E.values()) if raw_E else 0.0
    norm_E = {pid: (raw_E[pid] / max_E) if max_E > 0.0 else 0.0 for pid in person_ids}

    structural: dict[str, float] = {}
    composite_v2: dict[str, float] = {}
    for pid in person_ids:
        s = 0.40 * norm_D[pid] + 0.30 * norm_B[pid] + 0.30 * norm_E[pid]
        structural[pid] = s
        composite_v2[pid] = 0.70 * s + 0.30 * norm_financial[pid]

    raw_scores = {
        "composite_v2": composite_v2,
        "financial_only": norm_financial,
        "projection_only": structural,
    }

    pessimistic_ranks = {
        ranker: compute_pessimistic_ranks(scores)
        for ranker, scores in raw_scores.items()
    }

    return {
        "components": {
            "betweenness": norm_B,
            "degree": norm_D,
            "eigenvector": norm_E,
            "financial": norm_financial,
        },
        "eigenvector_converged": ev_converged,
        "person_ids": person_ids,
        "pessimistic_ranks": pessimistic_ranks,
        "raw_financial_paise": raw_financial_paise,
        "raw_scores": raw_scores,
    }

