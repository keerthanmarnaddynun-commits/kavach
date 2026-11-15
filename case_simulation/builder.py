"""Planted case graph builder from synthetic case directory and simulated FIR coverage."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import numpy as np

from case_graph.builder import _collect_bank_edges, _collect_cdr_edges


def sample_stated_facts(
    truth: dict[str, Any],
    coverage: float,
    rng: np.random.RandomState,
) -> dict[str, list[dict[str, str]]]:
    """Sample true ownership facts per person independently with probability = coverage.

    Returns dict mapping person_id to a list of stated fact dicts:
    [{'type': 'PHONE', 'value': '...'}, {'type': 'ACCOUNT', 'value': '...'}]
    """
    stated_by_person: dict[str, list[dict[str, str]]] = {}

    for person in truth.get("people", []):
        pid = str(person.get("person_id", ""))
        stated_by_person[pid] = []

        # Phones: sorted by phone string for determinism
        phones = sorted(
            person.get("phones", []),
            key=lambda x: str(x.get("phone", "") if isinstance(x, dict) else x),
        )
        for ph_obj in phones:
            val = str(ph_obj.get("phone", "") if isinstance(ph_obj, dict) else ph_obj).strip()
            if not val:
                continue
            is_stated = coverage >= 1.0 or (coverage > 0.0 and bool(rng.rand() < coverage))
            if is_stated:
                stated_by_person[pid].append({"type": "PHONE", "value": val})

        # Accounts: sorted by account_number string for determinism
        accounts = sorted(
            person.get("accounts", []),
            key=lambda x: str(
                x.get("account_number", "") if isinstance(x, dict) else x
            ),
        )
        for acc_obj in accounts:
            val = str(
                acc_obj.get("account_number", "") if isinstance(acc_obj, dict) else acc_obj
            ).strip()
            if not val:
                continue
            is_stated = coverage >= 1.0 or (coverage > 0.0 and bool(rng.rand() < coverage))
            if is_stated:
                stated_by_person[pid].append({"type": "ACCOUNT", "value": val})

    return stated_by_person


def build_planted_graph(
    case_dir: str | Path,
    coverage: float,
    fragmented: bool,
    rng: np.random.RandomState,
    csv_cache: tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Build a graph dict in the same format as case_graph graph.json.

    Args:
        case_dir: Path to case folder containing truth.json, cdr.csv, bank.csv.
        coverage: Float probability for stating each ownership fact (e.g. 0.3, 0.6, 1.0).
        fragmented: False for resolved (1 PERSON node per person), True for fragmented.
        rng: np.random.RandomState instance for sampling.
        csv_cache: Optional tuple of (cdr_edges, bank_edges, non_person_nodes) to avoid re-parsing CSVs.

    Returns:
        Dict with 'nodes', 'edges', and 'attributions'.
    """
    case_path = Path(case_dir)
    truth_file = case_path / "truth.json"
    with truth_file.open("r", encoding="utf-8") as fh:
        truth = json.load(fh)

    if csv_cache is not None:
        cached_cdr, cached_bank, cached_nodes = csv_cache
        cdr_edges = copy.deepcopy(cached_cdr)
        bank_edges = copy.deepcopy(cached_bank)
        non_person_nodes = copy.deepcopy(cached_nodes)
    else:
        cdr_file = case_path / "cdr.csv"
        bank_file = case_path / "bank.csv"
        non_person_nodes = {}
        cdr_edges, _, _ = _collect_cdr_edges(cdr_file, non_person_nodes)
        bank_edges, _ = _collect_bank_edges(bank_file, non_person_nodes)

    stated_facts = sample_stated_facts(truth, coverage, rng)

    people_by_id = {str(p["person_id"]): p for p in truth.get("people", [])}

    person_nodes: dict[str, dict[str, Any]] = {}
    fir_edges: list[dict[str, Any]] = []
    attributions_map: dict[str, list[str]] = {}

    for pid in sorted(stated_facts.keys()):
        facts = stated_facts[pid]
        p_obj = people_by_id.get(pid, {})
        canonical_name = str(p_obj.get("name", pid)).strip()
        attr_ids = [f"{f['type']}:{f['value']}" for f in facts]
        attributions_map[pid] = attr_ids

        if not facts:
            # Person with no stated fact gets no node
            continue

        if not fragmented:
            # Mode resolved: one PERSON node per person
            node_id = f"PERSON:{pid}"
            person_nodes[node_id] = {
                "canonical_name": canonical_name,
                "id": node_id,
                "person_id": pid,
                "roles": ["SUSPECT"],
                "type": "PERSON",
            }
            for f in facts:
                target_id = f"{f['type']}:{f['value']}"
                rel = "OWNS_DEVICE" if f["type"] == "PHONE" else "CONTROLS_ACCOUNT"
                if target_id not in non_person_nodes:
                    non_person_nodes[target_id] = {
                        "evidence_spans": [],
                        "id": target_id,
                        "source_files": [],
                        "source_firs": [],
                        "type": f["type"],
                        "value": f["value"],
                    }
                fir_edges.append(
                    {
                        "count": 1,
                        "relation": rel,
                        "source": node_id,
                        "source_kind": "FIR",
                        "target": target_id,
                    }
                )
        else:
            # Mode fragmented: every stated fact gets its own PERSON node
            for fact_idx, f in enumerate(facts, start=1):
                node_id = f"PERSON:{pid}:{fact_idx}"
                person_nodes[node_id] = {
                    "canonical_name": canonical_name,
                    "id": node_id,
                    "person_id": pid,
                    "roles": ["SUSPECT"],
                    "type": "PERSON",
                }
                target_id = f"{f['type']}:{f['value']}"
                rel = "OWNS_DEVICE" if f["type"] == "PHONE" else "CONTROLS_ACCOUNT"
                if target_id not in non_person_nodes:
                    non_person_nodes[target_id] = {
                        "evidence_spans": [],
                        "id": target_id,
                        "source_files": [],
                        "source_firs": [],
                        "type": f["type"],
                        "value": f["value"],
                    }
                fir_edges.append(
                    {
                        "count": 1,
                        "relation": rel,
                        "source": node_id,
                        "source_kind": "FIR",
                        "target": target_id,
                    }
                )

    all_nodes = list(person_nodes.values()) + list(non_person_nodes.values())
    all_nodes.sort(key=lambda n: n["id"])

    all_edges = fir_edges + cdr_edges + bank_edges
    all_edges.sort(
        key=lambda e: (e["source"], e["target"], e["relation"], e["source_kind"])
    )

    return {
        "attributions": attributions_map,
        "edges": all_edges,
        "nodes": all_nodes,
    }

