"""Analytics graph construction, centrality scoring, and weight robustness."""

from __future__ import annotations

from collections import defaultdict
import math
from typing import Any

import networkx as nx
import numpy as np

ALLOWED_GRAPH_NODE_TYPES: frozenset[str] = frozenset(
    {"PERSON", "PHONE", "IMEI", "ACCOUNT"}
)

DEFAULT_BASE_WEIGHTS: dict[str, float] = {
    "CONTROLS_ACCOUNT": 3.0,
    "COMMUNICATED_WITH": 1.5,
    "OWNS_DEVICE": 1.5,
    "TRANSFERRED_FUNDS": 1.0,
    "ASSOCIATED_IMEI": 0.5,
}

WEIGHT_RELATIONS: tuple[str, ...] = (
    "CONTROLS_ACCOUNT",
    "COMMUNICATED_WITH",
    "OWNS_DEVICE",
    "TRANSFERRED_FUNDS",
    "ASSOCIATED_IMEI",
)

COMPOSITE_WEIGHTS: dict[str, float] = {
    "degree": 0.40,
    "betweenness": 0.30,
    "eigenvector": 0.30,
}


class _UnionFind:
    def __init__(self, items: list[str]) -> None:
        self.parent: dict[str, str] = {x: x for x in items}

    def find(self, x: str) -> str:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        # Representative is always the lexicographically lowest node id.
        if ra < rb:
            self.parent[rb] = ra
        else:
            self.parent[ra] = rb


def _is_suspect_person(node: dict[str, Any]) -> bool:
    if node.get("type") != "PERSON":
        return False
    roles = {str(r).upper() for r in node.get("roles", [])}
    if node.get("role"):
        roles.add(str(node["role"]).upper())
    return "SUSPECT" in roles


def _edge_count(edge: dict[str, Any]) -> int:
    if edge.get("source_kind") != "CSV":
        return 1
    rel = edge.get("relation")
    if rel == "COMMUNICATED_WITH":
        if "voice_count" in edge or "sms_count" in edge:
            return int(edge.get("voice_count", 0)) + int(edge.get("sms_count", 0))
        return int(edge.get("count", 1))
    if rel == "TRANSFERRED_FUNDS":
        return int(edge.get("txn_count", edge.get("count", 1)))
    if rel == "ASSOCIATED_IMEI":
        return int(edge.get("row_count", edge.get("count", 1)))
    return int(edge.get("count", 1))


def resolve_candidate_representatives(
    graph_data: dict[str, Any],
) -> tuple[dict[str, str], dict[str, list[str]]]:
    """Return representative node id per suspect node and collapsed member lists."""
    suspect_ids = sorted(
        str(n["id"]) for n in graph_data.get("nodes", []) if _is_suspect_person(n)
    )
    suspect_set = set(suspect_ids)
    uf = _UnionFind(suspect_ids)

    for edge in graph_data.get("edges", []):
        if edge.get("relation") != "SAME_AS_CANDIDATE":
            continue
        src = str(edge["source"])
        tgt = str(edge["target"])
        if src in suspect_set and tgt in suspect_set:
            uf.union(src, tgt)

    rep_map = {nid: uf.find(nid) for nid in suspect_ids}
    members_by_rep: dict[str, list[str]] = defaultdict(list)
    for nid in suspect_ids:
        members_by_rep[rep_map[nid]].append(nid)
    for rep in members_by_rep:
        members_by_rep[rep].sort()
    return rep_map, dict(members_by_rep)


def build_analytics_graph(
    graph_data: dict[str, Any],
    mode: str = "strict",
    base_weights: dict[str, float] | None = None,
) -> tuple[nx.Graph, dict[str, Any]]:
    """Build simple undirected NetworkX graph for 'strict' or 'resolved' mode."""
    if mode not in ("strict", "resolved"):
        raise ValueError(f"Unsupported analytics mode: {mode!r}")

    weights_cfg = dict(DEFAULT_BASE_WEIGHTS)
    if base_weights:
        weights_cfg.update(base_weights)

    kept_nodes: dict[str, dict[str, Any]] = {}
    for node in graph_data.get("nodes", []):
        ntype = node.get("type")
        if ntype not in ALLOWED_GRAPH_NODE_TYPES:
            continue
        if ntype == "PERSON" and not _is_suspect_person(node):
            continue
        kept_nodes[str(node["id"])] = node

    if mode == "resolved":
        rep_map, members_by_rep = resolve_candidate_representatives(graph_data)
    else:
        suspect_ids = sorted(
            nid for nid, n in kept_nodes.items() if n.get("type") == "PERSON"
        )
        rep_map = {nid: nid for nid in suspect_ids}
        members_by_rep = {nid: [nid] for nid in suspect_ids}

    active_nodes: dict[str, dict[str, Any]] = {}
    for nid, node in kept_nodes.items():
        rep = rep_map.get(nid, nid)
        if rep not in active_nodes:
            active_nodes[rep] = dict(kept_nodes[rep])

    G = nx.Graph()
    for nid in sorted(active_nodes.keys()):
        node = active_nodes[nid]
        G.add_node(
            nid,
            type=node.get("type"),
            canonical_name=node.get("canonical_name", ""),
        )

    # Accumulate simple undirected edge weights & per-(u, v, relation) weights for explanations.
    pair_rel_weights: dict[tuple[str, str, str], float] = defaultdict(float)

    for edge in graph_data.get("edges", []):
        rel = str(edge.get("relation", ""))
        if rel == "SAME_AS_CANDIDATE":
            continue
        if rel not in weights_cfg:
            continue

        raw_u = str(edge["source"])
        raw_v = str(edge["target"])
        if raw_u not in kept_nodes or raw_v not in kept_nodes:
            continue

        u = rep_map.get(raw_u, raw_u)
        v = rep_map.get(raw_v, raw_v)
        if u == v:
            continue

        count = max(0, _edge_count(edge))
        w = float(weights_cfg[rel]) * math.log2(1.0 + count)
        if w <= 0.0:
            continue

        if G.has_edge(u, v):
            G[u][v]["weight"] += w
        else:
            G.add_edge(u, v, weight=w)

        a, b = (u, v) if u < v else (v, u)
        pair_rel_weights[(a, b, rel)] += w

    for u, v, data in G.edges(data=True):
        data["distance"] = 1.0 / data["weight"]

    isolates = list(nx.isolates(G))
    if isolates:
        G.remove_nodes_from(isolates)

    # Index incident relation weights per remaining node for explanations.
    incident_edges: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for (a, b, rel), w in pair_rel_weights.items():
        if a in G and b in G and G.has_edge(a, b):
            incident_edges[a].append({"neighbour": b, "relation": rel, "weight": w})
            incident_edges[b].append({"neighbour": a, "relation": rel, "weight": w})

    for nid in incident_edges:
        incident_edges[nid].sort(
            key=lambda item: (-item["weight"], item["neighbour"], item["relation"])
        )

    meta = {
        "collapsed_members": {
            nid: members_by_rep.get(nid, [nid])
            for nid in G.nodes()
            if G.nodes[nid].get("type") == "PERSON"
        },
        "incident_edges": dict(incident_edges),
        "mode": mode,
        "rep_map": rep_map,
    }
    return G, meta


def _power_iteration_eigenvector(
    G: nx.Graph, max_iter: int = 1000, tol: float = 1e-6
) -> dict[str, float]:
    """Deterministic power-iteration fallback on weighted undirected graph."""
    nodes = sorted(G.nodes())
    n = len(nodes)
    if n == 0:
        return {}
    vec: dict[str, float] = {u: 1.0 / math.sqrt(n) for u in nodes}
    for _ in range(max_iter):
        nxt: dict[str, float] = {u: 0.0 for u in nodes}
        for u in nodes:
            total = 0.0
            for v, data in G[u].items():
                total += float(data.get("weight", 1.0)) * vec[v]
            nxt[u] = total
        norm = math.sqrt(sum(val * val for val in nxt.values()))
        if norm <= 0.0:
            return {u: 0.0 for u in nodes}
        for u in nodes:
            nxt[u] /= norm
        diff = sum(abs(nxt[u] - vec[u]) for u in nodes)
        vec = nxt
        if diff < n * tol:
            break
    return vec


def _compute_eigenvector(G: nx.Graph) -> tuple[dict[str, float], bool]:
    if G.number_of_nodes() == 0:
        return {}, True
    try:
        ev = nx.eigenvector_centrality(G, weight="weight", max_iter=1000)
        return {str(k): float(v) for k, v in ev.items()}, True
    except (nx.PowerIterationFailedConvergence, nx.NetworkXException):
        return _power_iteration_eigenvector(G, max_iter=1000), False


def _normalise_over_persons(
    values: dict[str, float], person_ids: list[str]
) -> dict[str, float]:
    if not person_ids:
        return {}
    max_val = max(float(values.get(pid, 0.0)) for pid in person_ids)
    if max_val <= 0.0:
        return {pid: 0.0 for pid in person_ids}
    return {pid: float(values.get(pid, 0.0)) / max_val for pid in person_ids}


def _rank_persons_from_graph(
    G: nx.Graph,
) -> tuple[list[tuple[str, float, float, float, float]], bool]:
    """Return sorted (node_id, composite, norm_deg, norm_bet, norm_eig) and ev_converged."""
    person_ids = sorted(
        str(nid) for nid, data in G.nodes(data=True) if data.get("type") == "PERSON"
    )
    if not person_ids:
        return [], True

    raw_deg = {pid: float(G.degree(pid, weight="weight")) for pid in person_ids}
    raw_bet = nx.betweenness_centrality(G, weight="distance", normalized=True)
    raw_eig, ev_converged = _compute_eigenvector(G)

    norm_deg = _normalise_over_persons(raw_deg, person_ids)
    norm_bet = _normalise_over_persons(raw_bet, person_ids)
    norm_eig = _normalise_over_persons(raw_eig, person_ids)

    rows: list[tuple[str, float, float, float, float]] = []
    for pid in person_ids:
        comp = (
            COMPOSITE_WEIGHTS["degree"] * norm_deg[pid]
            + COMPOSITE_WEIGHTS["betweenness"] * norm_bet[pid]
            + COMPOSITE_WEIGHTS["eigenvector"] * norm_eig[pid]
        )
        rows.append((pid, comp, norm_deg[pid], norm_bet[pid], norm_eig[pid]))

    rows.sort(key=lambda item: (-item[1], item[0]))
    return rows, ev_converged


def _linked_counts(G: nx.Graph, pid: str) -> dict[str, int]:
    phone_neighbors = [
        nb for nb in G.neighbors(pid) if G.nodes[nb].get("type") == "PHONE"
    ]
    account_neighbors = [
        nb for nb in G.neighbors(pid) if G.nodes[nb].get("type") == "ACCOUNT"
    ]
    imei_neighbors = {
        nb for nb in G.neighbors(pid) if G.nodes[nb].get("type") == "IMEI"
    }
    for ph in phone_neighbors:
        for nb2 in G.neighbors(ph):
            if G.nodes[nb2].get("type") == "IMEI":
                imei_neighbors.add(nb2)

    return {
        "accounts": len(set(account_neighbors)),
        "imeis": len(imei_neighbors),
        "phones": len(set(phone_neighbors)),
    }


def compute_kingpin_scores(
    graph_data: dict[str, Any],
    mode: str = "strict",
    base_weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Compute normalised centrality components, composite score, and explanations."""
    G, meta = build_analytics_graph(graph_data, mode=mode, base_weights=base_weights)
    ranked_rows, ev_converged = _rank_persons_from_graph(G)

    incident_edges = meta["incident_edges"]
    collapsed_members = meta["collapsed_members"]

    ranking: list[dict[str, Any]] = []
    for rank_idx, (pid, comp, ndeg, nbet, neig) in enumerate(ranked_rows, start=1):
        top3_edges = [
            {
                "neighbour": item["neighbour"],
                "relation": item["relation"],
                "weight": round(float(item["weight"]), 6),
            }
            for item in incident_edges.get(pid, [])[:3]
        ]
        ranking.append(
            {
                "canonical_name": G.nodes[pid].get("canonical_name", ""),
                "collapsed_node_ids": collapsed_members.get(pid, [pid]),
                "components": {
                    "betweenness": round(nbet, 6),
                    "degree": round(ndeg, 6),
                    "eigenvector": round(neig, 6),
                },
                "composite": round(comp, 6),
                "explanation": top3_edges,
                "linked": _linked_counts(G, pid),
                "node_id": pid,
                "rank": rank_idx,
            }
        )

    return {
        "composite_weights": dict(COMPOSITE_WEIGHTS),
        "edges_used": G.number_of_edges(),
        "eigenvector_converged": ev_converged,
        "eigenvector_method": "networkx" if ev_converged else "power_iteration_fallback",
        "mode": mode,
        "nodes_used": G.number_of_nodes(),
        "person_nodes_ranked": len(ranking),
        "ranking": ranking,
    }


def compute_robustness(
    graph_data: dict[str, Any],
    mode: str = "strict",
    n_samples: int = 200,
    seed: int = 20261112,
) -> dict[str, Any]:
    """Perturb base weights 200 times in [0.8, 1.2] and track rank-1 / top-3 stability."""
    base_G, meta = build_analytics_graph(graph_data, mode=mode)
    person_ids = sorted(
        str(nid)
        for nid, data in base_G.nodes(data=True)
        if data.get("type") == "PERSON"
    )
    collapsed_members = meta["collapsed_members"]

    if not person_ids:
        return {
            "mode": mode,
            "n_samples": n_samples,
            "samples_top3": [],
            "seed": seed,
            "top_10": [],
        }

    # Build reusable edge contributions keyed by (u, v) -> list[(relation, log2(1+count))]
    kept_nodes: dict[str, dict[str, Any]] = {}
    for node in graph_data.get("nodes", []):
        ntype = node.get("type")
        if ntype not in ALLOWED_GRAPH_NODE_TYPES:
            continue
        if ntype == "PERSON" and not _is_suspect_person(node):
            continue
        kept_nodes[str(node["id"])] = node

    rep_map = meta["rep_map"]
    edge_terms: dict[tuple[str, str], dict[str, float]] = defaultdict(
        lambda: defaultdict(float)
    )
    active_node_ids = set(base_G.nodes())

    for edge in graph_data.get("edges", []):
        rel = str(edge.get("relation", ""))
        if rel == "SAME_AS_CANDIDATE" or rel not in DEFAULT_BASE_WEIGHTS:
            continue
        raw_u = str(edge["source"])
        raw_v = str(edge["target"])
        if raw_u not in kept_nodes or raw_v not in kept_nodes:
            continue
        u = rep_map.get(raw_u, raw_u)
        v = rep_map.get(raw_v, raw_v)
        if u == v or u not in active_node_ids or v not in active_node_ids:
            continue
        term = math.log2(1.0 + max(0, _edge_count(edge)))
        if term <= 0.0:
            continue
        a, b = (u, v) if u < v else (v, u)
        edge_terms[(a, b)][rel] += term

    rng = np.random.RandomState(seed)
    rank1_counts: dict[str, int] = {pid: 0 for pid in person_ids}
    top3_counts: dict[str, int] = {pid: 0 for pid in person_ids}
    samples_top3: list[list[str]] = []

    work_G = base_G.copy()
    for _ in range(n_samples):
        factors = rng.uniform(0.8, 1.2, size=len(WEIGHT_RELATIONS))
        sampled_base = {
            rel: DEFAULT_BASE_WEIGHTS[rel] * float(factor)
            for rel, factor in zip(WEIGHT_RELATIONS, factors)
        }
        for (a, b), rel_sums in edge_terms.items():
            w = sum(sampled_base[rel] * log_term for rel, log_term in rel_sums.items())
            work_G[a][b]["weight"] = w
            work_G[a][b]["distance"] = 1.0 / w

        ranked_rows, _ = _rank_persons_from_graph(work_G)
        top3_ids = [row[0] for row in ranked_rows[:3]]
        samples_top3.append(top3_ids)
        if ranked_rows:
            rank1_counts[ranked_rows[0][0]] += 1
        for pid in top3_ids:
            top3_counts[pid] += 1

    records: list[dict[str, Any]] = []
    for pid in person_ids:
        r1 = rank1_counts[pid]
        t3 = top3_counts[pid]
        records.append(
            {
                "canonical_name": base_G.nodes[pid].get("canonical_name", ""),
                "collapsed_node_ids": collapsed_members.get(pid, [pid]),
                "node_id": pid,
                "rank_1_count": r1,
                "rank_1_share": round(r1 / n_samples, 6),
                "top_3_count": t3,
                "top_3_share": round(t3 / n_samples, 6),
            }
        )

    records.sort(key=lambda r: (-r["top_3_share"], -r["rank_1_share"], r["node_id"]))
    return {
        "mode": mode,
        "n_samples": n_samples,
        "samples_top3": samples_top3,
        "seed": seed,
        "top_10": records[:10],
    }

