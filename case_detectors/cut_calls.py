"""Call-layer network analysis and group separation."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Iterable, Mapping, Sequence

import networkx as nx

from case_detectors.cut import articulation_persons, min_vertex_cut


def call_layer_graph(
    cdr_rows: Iterable[Mapping[str, Any]],
    owners: Mapping[str, Sequence[str]],
) -> dict[str, list[dict[str, Any]]]:
    """Build call-layer graph containing only PERSON nodes from CDR and ownership.

    Two persons u and v (u != v) are linked by an undirected edge if:
      (a) a device owned by u appears with a device owned by v in at least one CDR row
          (either direction; self-pairs ignored), or
      (b) u and v own the same device.

    Unowned devices create no nodes.

    Args:
        cdr_rows: Iterable of CDR rows with 'a_party' and 'b_party'.
        owners: Mapping of device number string to sequence of person node IDs.

    Returns:
        Graph dict with 'nodes' (list of PERSON node dicts) and 'edges' (undirected edges).
    """
    # Collect all distinct person IDs from ownership
    all_persons: set[str] = set()
    phone_to_persons: dict[str, list[str]] = {}

    for ph, pids in owners.items():
        clean_ph = str(ph).strip()
        clean_pids = [str(p).strip() for p in pids if str(p).strip()]
        if clean_pids:
            phone_to_persons[clean_ph] = clean_pids
            all_persons.update(clean_pids)

    edges_set: set[tuple[str, str]] = set()

    # Rule (b): shared devices link co-owners
    for pids in phone_to_persons.values():
        if len(pids) > 1:
            for i in range(len(pids)):
                for j in range(i + 1, len(pids)):
                    u, v = pids[i], pids[j]
                    if u != v:
                        edges_set.add((min(u, v), max(u, v)))

    # Rule (a): CDR communication between devices
    for row in cdr_rows:
        dev_a = str(row.get("a_party", "")).strip()
        dev_b = str(row.get("b_party", "")).strip()

        if not dev_a or not dev_b or dev_a == dev_b:
            continue

        owners_a = phone_to_persons.get(dev_a, [])
        owners_b = phone_to_persons.get(dev_b, [])

        if not owners_a or not owners_b:
            continue

        for u in owners_a:
            for v in owners_b:
                if u != v:
                    edges_set.add((min(u, v), max(u, v)))

    # Construct deterministic node and edge lists
    nodes = [{"id": pid, "type": "PERSON"} for pid in sorted(all_persons)]
    edges = [
        {"relation": "COMMUNICATED_WITH", "source": u, "target": v}
        for u, v in sorted(edges_set)
    ]

    return {"edges": edges, "nodes": nodes}


def break_groups(
    graph: dict[str, Any],
    group_a: Sequence[str] | set[str],
    group_b: Sequence[str] | set[str],
) -> dict[str, Any]:
    """Break communication groups using min vertex cut.

    Checks for direct terminal-to-terminal links between group_a and group_b.
    If any direct cross-group links exist, the cut is infinite by construction.

    Args:
        graph: Graph dict with 'nodes' and 'edges' (all PERSON nodes).
        group_a: Source group person IDs.
        group_b: Target group person IDs.

    Returns:
        Dict with 'finite' (bool), and either 'cut', 'size', or 'reason'.
    """
    set_a = set(str(x) for x in group_a)
    set_b = set(str(x) for x in group_b)

    # Empty group check
    if not set_a or not set_b:
        return {"skipped": "empty_group"}

    # Count direct cross-group person links
    direct_links = 0
    for edge in graph.get("edges", []):
        src = str(edge.get("source", ""))
        tgt = str(edge.get("target", ""))
        if (src in set_a and tgt in set_b) or (src in set_b and tgt in set_a):
            direct_links += 1

    if direct_links > 0:
        return {
            "direct_links_count": direct_links,
            "finite": False,
            "reason": "direct_link",
        }

    # Call existing min_vertex_cut
    cut_res = min_vertex_cut(graph, group_a, group_b, arrestable_types=("PERSON",))
    cut_res["direct_links_count"] = 0
    return cut_res


def top2_betweenness(graph: dict[str, Any]) -> dict[str, Any]:
    """Compute top 2 nodes by betweenness centrality with pessimistic tie detection.

    Args:
        graph: Graph dict with 'nodes' and 'edges'.

    Returns:
        Dict with 'ranked', 'scores', 'tied', and 'top2'.
    """
    G = nx.Graph()
    for node in graph.get("nodes", []):
        G.add_node(str(node["id"]))
    for edge in graph.get("edges", []):
        G.add_edge(str(edge["source"]), str(edge["target"]))

    if G.number_of_nodes() < 2:
        nodes = sorted(G.nodes())
        return {
            "ranked": [(n, 0.0) for n in nodes],
            "scores": {n: 0.0 for n in nodes},
            "tied": True if len(nodes) < 2 else False,
            "top2": nodes,
        }

    bet = nx.betweenness_centrality(G, normalized=True)
    # Sort descending by betweenness, tie-break by ascending node ID
    ranked = sorted(bet.items(), key=lambda kv: (-round(float(kv[1]), 9), kv[0]))

    s1 = round(float(ranked[0][1]), 9)
    s2 = round(float(ranked[1][1]), 9)
    s3 = round(float(ranked[2][1]), 9) if len(ranked) > 2 else -1.0

    tied = (s2 == s3) if len(ranked) > 2 else False
    top2 = [ranked[0][0], ranked[1][0]]

    return {
        "ranked": ranked,
        "scores": bet,
        "tied": tied,
        "top2": top2,
    }


def top2_degree(graph: dict[str, Any]) -> dict[str, Any]:
    """Compute top 2 nodes by degree with pessimistic tie detection.

    Args:
        graph: Graph dict with 'nodes' and 'edges'.

    Returns:
        Dict with 'ranked', 'scores', 'tied', and 'top2'.
    """
    G = nx.Graph()
    for node in graph.get("nodes", []):
        G.add_node(str(node["id"]))
    for edge in graph.get("edges", []):
        G.add_edge(str(edge["source"]), str(edge["target"]))

    if G.number_of_nodes() < 2:
        nodes = sorted(G.nodes())
        return {
            "ranked": [(n, 0) for n in nodes],
            "scores": {n: 0 for n in nodes},
            "tied": True if len(nodes) < 2 else False,
            "top2": nodes,
        }

    deg = dict(G.degree())
    ranked = sorted(deg.items(), key=lambda kv: (-kv[1], kv[0]))

    s1 = ranked[0][1]
    s2 = ranked[1][1]
    s3 = ranked[2][1] if len(ranked) > 2 else -1

    tied = (s2 == s3) if len(ranked) > 2 else False
    top2 = [ranked[0][0], ranked[1][0]]

    return {
        "ranked": ranked,
        "scores": deg,
        "tied": tied,
        "top2": top2,
    }


def unowned_bridging_phones(
    cdr_rows: Iterable[Mapping[str, Any]],
    owners: Mapping[str, Sequence[str]],
    group_a: Sequence[str] | set[str],
    group_b: Sequence[str] | set[str],
) -> list[dict[str, Any]]:
    """Identify devices with no stated owner that communicate with both groups.

    Args:
        cdr_rows: Iterable of CDR rows with 'a_party', 'b_party'.
        owners: Mapping of device string to list of owner person IDs.
        group_a: Person IDs belonging to group A.
        group_b: Person IDs belonging to group B.

    Returns:
        List of unverified lead dicts sorted by call count descending.
    """
    set_a = set(str(x) for x in group_a)
    set_b = set(str(x) for x in group_b)

    owned_devices = {
        str(ph).strip()
        for ph, pids in owners.items()
        if pids and len(pids) > 0 and str(ph).strip()
    }

    # Devices owned by group A and group B
    devs_a = {
        str(ph).strip()
        for ph, pids in owners.items()
        if any(str(p) in set_a for p in pids)
    }
    devs_b = {
        str(ph).strip()
        for ph, pids in owners.items()
        if any(str(p) in set_b for p in pids)
    }

    calls_a: Counter[str] = Counter()
    calls_b: Counter[str] = Counter()
    evidence: dict[str, list[int]] = defaultdict(list)

    for row_idx, row in enumerate(cdr_rows, start=1):
        dev_a = str(row.get("a_party", "")).strip()
        dev_b = str(row.get("b_party", "")).strip()

        if not dev_a or not dev_b or dev_a == dev_b:
            continue

        # Check dev_a unowned
        if dev_a not in owned_devices:
            is_ev = False
            if dev_b in devs_a:
                calls_a[dev_a] += 1
                is_ev = True
            if dev_b in devs_b:
                calls_b[dev_a] += 1
                is_ev = True
            if is_ev and len(evidence[dev_a]) < 10:
                evidence[dev_a].append(row_idx)

        # Check dev_b unowned
        if dev_b not in owned_devices:
            is_ev = False
            if dev_a in devs_a:
                calls_a[dev_b] += 1
                is_ev = True
            if dev_a in devs_b:
                calls_b[dev_b] += 1
                is_ev = True
            if is_ev and len(evidence[dev_b]) < 10:
                evidence[dev_b].append(row_idx)

    bridging_candidates = set(calls_a.keys()) & set(calls_b.keys())
    results: list[dict[str, Any]] = []

    for dev in sorted(bridging_candidates):
        ca = calls_a[dev]
        cb = calls_b[dev]
        if ca >= 1 and cb >= 1:
            results.append(
                {
                    "calls_with_group_a": ca,
                    "calls_with_group_b": cb,
                    "evidence_rows": evidence[dev],
                    "phone": dev,
                    "status": "unverified leads: who holds this number?",
                    "total_calls": ca + cb,
                }
            )

    results.sort(key=lambda d: (-d["total_calls"], d["phone"]))
    return results


def detect_communities_calls(
    graph: dict[str, Any],
    seed: int,
) -> list[list[str]]:
    """Detect communities in call-layer graph using Louvain algorithm.

    Communities are ordered by size descending, then by smallest node id ascending.

    Args:
        graph: Call-layer graph dict with 'nodes' and 'edges'.
        seed: Random seed integer for Louvain partitioning.

    Returns:
        List of communities, each a list of node IDs.
    """
    G = nx.Graph()
    for node in graph.get("nodes", []):
        G.add_node(str(node["id"]))
    for edge in graph.get("edges", []):
        G.add_edge(str(edge["source"]), str(edge["target"]))

    if G.number_of_nodes() == 0:
        return []

    comms = nx.community.louvain_communities(G, seed=seed)
    sorted_comms: list[list[str]] = []
    for comm in comms:
        sorted_comms.append(sorted(str(n) for n in comm))

    sorted_comms.sort(key=lambda c: (-len(c), c[0] if c else ""))
    return sorted_comms
