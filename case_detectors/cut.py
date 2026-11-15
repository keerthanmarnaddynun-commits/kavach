"""Network break analysis: articulation points, minimum vertex cut, and community detection."""

from __future__ import annotations

from typing import Any, Sequence

import networkx as nx
from networkx.algorithms.flow import dinitz, minimum_cut

from case_analytics.projection import build_person_projection


def _build_undirected_graph(
    graph_data: dict[str, Any],
) -> tuple[nx.Graph, dict[str, str]]:
    G = nx.Graph()
    node_types: dict[str, str] = {}
    for n in graph_data.get("nodes", []):
        nid = str(n["id"])
        ntype = str(n.get("type", ""))
        node_types[nid] = ntype
        G.add_node(nid, type=ntype)
    for e in graph_data.get("edges", []):
        src = str(e["source"])
        tgt = str(e["target"])
        G.add_edge(src, tgt)
    return G, node_types


def articulation_persons(graph_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Find articulation points restricted to PERSON nodes with component sizes after removal.

    Args:
        graph_data: Graph dictionary containing nodes and edges.

    Returns:
        List of dicts with node_id, component_sizes, and total_neighbors.
    """
    G, node_types = _build_undirected_graph(graph_data)
    if G.number_of_nodes() == 0:
        return []

    art_nodes = set(nx.articulation_points(G))
    results: list[dict[str, Any]] = []

    for v in sorted(art_nodes):
        if node_types.get(v) == "PERSON":
            neighbors = list(G.neighbors(v))
            G_sub = G.copy()
            G_sub.remove_node(v)

            split_sizes: list[int] = []
            seen: set[str] = set()
            for nb in neighbors:
                if nb not in seen and nb in G_sub:
                    comp = nx.node_connected_component(G_sub, nb)
                    split_sizes.append(len(comp))
                    seen.update(comp)

            split_sizes.sort(reverse=True)
            results.append(
                {
                    "component_sizes": split_sizes,
                    "node_id": v,
                    "total_neighbors": len(neighbors),
                }
            )

    return results


def min_vertex_cut(
    graph_data: dict[str, Any],
    group_a: Sequence[str],
    group_b: Sequence[str],
    arrestable_types: Sequence[str] = ("PERSON",),
) -> dict[str, Any]:
    """Compute minimum vertex cut disconnecting group_a from group_b using node-splitting flow.

    Args:
        graph_data: Graph dictionary with nodes and edges.
        group_a: Collection of terminal node IDs for group A.
        group_b: Collection of terminal node IDs for group B.
        arrestable_types: Node types that have finite capacity 1 (default: ('PERSON',)).

    Returns:
        Dict with keys:
          - skipped: 'empty_group' if either group has no members in graph.
          - finite: False if max flow is unbounded.
          - finite: True, size: k, cut: sorted list of cut node IDs.
    """
    G, node_types = _build_undirected_graph(graph_data)

    members_a = sorted(str(m) for m in group_a if str(m) in G)
    members_b = sorted(str(m) for m in group_b if str(m) in G)

    if not members_a or not members_b:
        return {"skipped": "empty_group"}

    set_a = set(members_a)
    set_b = set(members_b)

    if set_a & set_b:
        return {"finite": False}

    H = nx.DiGraph()
    H.add_node("S")
    H.add_node("T")

    arrestable_set = set(arrestable_types)

    for n, data in G.nodes(data=True):
        n_in = f"{n}_in"
        n_out = f"{n}_out"
        ntype = data.get("type", "")
        if ntype in arrestable_set and n not in set_a and n not in set_b:
            H.add_edge(n_in, n_out, capacity=1)
        else:
            H.add_edge(n_in, n_out, capacity=float("inf"))

    for u, v in G.edges():
        H.add_edge(f"{u}_out", f"{v}_in", capacity=float("inf"))
        H.add_edge(f"{v}_out", f"{u}_in", capacity=float("inf"))

    for m in members_a:
        H.add_edge("S", f"{m}_in", capacity=float("inf"))

    for m in members_b:
        H.add_edge(f"{m}_out", "T", capacity=float("inf"))

    try:
        cut_val, (reachable, non_reachable) = minimum_cut(
            H, "S", "T", flow_func=dinitz
        )
    except (nx.NetworkXUnbounded, nx.NetworkXException):
        return {"finite": False}

    if cut_val == float("inf"):
        return {"finite": False}

    cut_persons = sorted(
        n
        for n, data in G.nodes(data=True)
        if data.get("type", "") in arrestable_set
        and n not in set_a
        and n not in set_b
        and f"{n}_in" in reachable
        and f"{n}_out" in non_reachable
    )

    return {
        "cut": cut_persons,
        "finite": True,
        "size": int(cut_val),
    }


def detect_communities(
    graph_data: dict[str, Any],
    seed: int = 20261115,
) -> list[list[str]]:
    """Run Louvain community detection on person projection and return communities ordered by size."""
    G_proj, _, _ = build_person_projection(graph_data)
    if G_proj.number_of_nodes() == 0:
        return []

    comms = nx.community.louvain_communities(G_proj, weight="weight", seed=seed)
    ordered = sorted(
        [sorted(str(x) for x in c) for c in comms],
        key=lambda c: (-len(c), c[0] if c else ""),
    )
    return ordered
