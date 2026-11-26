"""Leads generation, role chips, and communication network break service."""
from __future__ import annotations

from collections import Counter, defaultdict
import csv
import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Sequence

from case_analytics.projection import (
    compute_pessimistic_ranks,
    compute_projection_scores,
)
from case_detectors.burner import detect_burners
from case_detectors.cut_calls import (
    break_groups,
    call_layer_graph,
    unowned_bridging_phones,
)
from case_detectors.mule import detect_mules
from case_detectors.roles import assign_role_chips
from kavach_api.analysis_service import build_graph, compute_case_fingerprint
from kavach_api.settings import DISCLAIMER, repo_root
from kavach_api.storage import Storage, _atomic_write_json

logger = logging.getLogger(__name__)

LIMITATIONS: list[str] = [
    "persons appear only when a document states ownership or control",
    "phones and accounts without a stated owner are unidentified",
    "scores are decision support",
    "relation extraction from text was measured at F1 0.32 on an independent held-out set",
    "no scanned documents",
]

BREAK_NOTE = "Only observed calls are used; unobserved links are ignored."


class BreakError(Exception):
    """Base exception for break operations."""


class InvalidGroupError(BreakError):
    """Raised when group_a or group_b is invalid."""


class DetectorConfigError(Exception):
    """Raised when detector configuration file is missing or invalid."""


def load_detector_config(config_path: str | Path | None = None) -> dict[str, Any]:
    """Load detector default configuration from disk. Raises DetectorConfigError if missing."""
    p = Path(config_path) if config_path else repo_root() / "config" / "detector_defaults.json"
    if not p.is_file():
        raise DetectorConfigError(f"Detector configuration file missing: {p}")
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def _get_config_sha256(config_path: str | Path | None = None) -> str:
    """Compute SHA-256 digest of detector defaults configuration file."""
    p = Path(config_path) if config_path else repo_root() / "config" / "detector_defaults.json"
    if p.is_file():
        return hashlib.sha256(p.read_bytes()).hexdigest()
    return ""


def _extract_owner_maps(graph: dict[str, Any]) -> dict[str, Any]:
    """
    Extract ownership and control mappings from graph edges.
    Returns owner_maps dict.
    """
    person_nodes = [n for n in graph.get("nodes", []) if n.get("type") == "PERSON"]
    person_ids = {n["id"] for n in person_nodes}

    person_to_accounts: dict[str, set[str]] = defaultdict(set)
    account_to_persons: dict[str, set[str]] = defaultdict(set)
    person_to_phones: dict[str, set[str]] = defaultdict(set)
    phone_to_persons: dict[str, set[str]] = defaultdict(set)

    for edge in graph.get("edges", []):
        rel = edge.get("relation")
        src = str(edge.get("source", ""))
        tgt = str(edge.get("target", ""))

        if rel == "CONTROLS_ACCOUNT":
            if src in person_ids:
                pid, acc = src, tgt
            elif tgt in person_ids:
                pid, acc = tgt, src
            else:
                continue
            clean_acc = acc[len("ACCOUNT:"):] if acc.startswith("ACCOUNT:") else acc
            person_to_accounts[pid].add(clean_acc)
            person_to_accounts[pid].add(acc)
            account_to_persons[clean_acc].add(pid)
            account_to_persons[acc].add(pid)

        elif rel == "OWNS_DEVICE":
            if src in person_ids:
                pid, ph = src, tgt
            elif tgt in person_ids:
                pid, ph = tgt, src
            else:
                continue
            clean_ph = ph[len("PHONE:"):] if ph.startswith("PHONE:") else ph
            person_to_phones[pid].add(clean_ph)
            person_to_phones[pid].add(ph)
            phone_to_persons[clean_ph].add(pid)
            phone_to_persons[ph].add(pid)

    return {
        "controlled_accounts": {k: sorted(v) for k, v in person_to_accounts.items()},
        "owned_phones": {k: sorted(v) for k, v in person_to_phones.items()},
        "person_to_accounts": {k: sorted(v) for k, v in person_to_accounts.items()},
        "person_to_phones": {k: sorted(v) for k, v in person_to_phones.items()},
        "account_to_persons": {k: sorted(v) for k, v in account_to_persons.items()},
        "phone_to_persons": {k: sorted(v) for k, v in phone_to_persons.items()},
    }


def _normalize_lead_evidence_rows(data: dict[str, Any]) -> dict[str, Any]:
    """
    Ensure evidence_rows.rows match builder 1-based data row indexing (header not counted)
    used by evidence.py /rows endpoint. Detectors output 1-based file lines (start=2).
    """
    out = dict(data)
    for lead_key in ("mule_accounts", "burner_phones"):
        if lead_key in out:
            items = []
            for item in out[lead_key]:
                item_copy = dict(item)
                if "evidence_rows" in item_copy and isinstance(item_copy["evidence_rows"], dict):
                    ev = dict(item_copy["evidence_rows"])
                    if "rows" in ev and isinstance(ev["rows"], list):
                        ev["rows"] = [max(1, r - 1) for r in ev["rows"]]
                    item_copy["evidence_rows"] = ev
                items.append(item_copy)
            out[lead_key] = items
    return out


def build_leads(
    store: Storage,
    case_id: str,
    config: dict[str, Any] | None = None,
    cut_members: Sequence[str] | set[str] | None = None,
) -> dict[str, Any]:
    """
    Compute and cache deterministic investigative leads in derived/leads.json.
    Keyed by case input fingerprint and detector config_sha256.
    When custom config or cut_members is provided, never reads or writes leads.json.
    """
    with store.case_lock(case_id):
        cdir = store.case_dir(case_id)
        derived_dir = cdir / "derived"
        derived_dir.mkdir(exist_ok=True)
        leads_path = derived_dir / "leads.json"

        fingerprint, doc_hash = compute_case_fingerprint(store, case_id)
        is_default_run = (config is None and cut_members is None)
        curr_cfg_sha = _get_config_sha256()

        # F3: Check freshness from leads.json contents (not fingerprint.json)
        if is_default_run and leads_path.is_file():
            try:
                cached = json.loads(leads_path.read_text(encoding="utf-8"))
                if (
                    cached.get("fingerprint") == fingerprint
                    and cached.get("config_sha256") == curr_cfg_sha
                ):
                    return _normalize_lead_evidence_rows(cached)
            except Exception:
                pass

        # Load graph and configuration
        graph = build_graph(store, case_id)
        if config is None:
            config = load_detector_config()

        chip_min_score = config.get("chip_min_score", {})
        mule_min_score = float(chip_min_score.get("mule", 0.70))
        burner_min_score = float(chip_min_score.get("burner", 0.70))

        person_nodes = [n for n in graph.get("nodes", []) if n.get("type") == "PERSON"]
        person_ids = sorted(n["id"] for n in person_nodes)
        person_name_map = {}
        for n in person_nodes:
            pname = n.get("canonical_name") or (n.get("names", [None])[0] if n.get("names") else n["id"])
            person_name_map[n["id"]] = pname

        # 1. Money flow & structural explanations via projection scores
        scores_data = compute_projection_scores(graph)
        raw_scores = scores_data.get("raw_scores", {})
        norm_financial = raw_scores.get("financial_only", {})
        pessimistic_fin_ranks = scores_data.get("pessimistic_ranks", {}).get("financial_only", {})
        raw_financial_paise = scores_data.get("raw_financial_paise", {})
        components = scores_data.get("components", {})
        # F9: Structural composite score from raw_scores["projection_only"]
        structural_composite = raw_scores.get("projection_only", {})

        # Ties detection for money flow: rounded to 9 decimal places
        rounded_scores = {pid: round(float(norm_financial.get(pid, 0.0)), 9) for pid in person_ids}
        score_counts = Counter(rounded_scores.values())

        # Extract owner mappings from graph
        owner_maps = _extract_owner_maps(graph)
        person_to_accounts = owner_maps["person_to_accounts"]
        account_to_persons = owner_maps["account_to_persons"]
        person_to_phones = owner_maps["person_to_phones"]
        phone_to_persons = owner_maps["phone_to_persons"]

        money_flow_items: list[dict[str, Any]] = []
        for pid in person_ids:
            score = round(float(norm_financial.get(pid, 0.0)), 6)
            rank = pessimistic_fin_ranks.get(pid, len(person_ids))
            tied = score_counts[rounded_scores[pid]] > 1
            name = person_name_map.get(pid, pid)
            ctrl_accounts = sorted(
                [a for a in person_to_accounts.get(pid, []) if not str(a).startswith("ACCOUNT:")]
            )
            paise = int(raw_financial_paise.get(pid, 0))
            reasons = [
                f"Paise flow: {paise:,} across {len(ctrl_accounts)} controlled accounts",
                f"Financial control score: {score:.6f}",
            ]
            evidence = {
                "accounts": ctrl_accounts,
                "paise_flow": paise,
                "controlled_account_count": len(ctrl_accounts),
            }
            money_flow_items.append(
                {
                    "rank": rank,
                    "tied": tied,
                    "person_id": pid,
                    "name": name,
                    "score": score,
                    "accounts": ctrl_accounts,
                    "reasons": reasons,
                    "evidence": evidence,
                }
            )

        # Sort money flow: best rank first (rank 1 is best), then score descending, then person_id
        money_flow_items.sort(key=lambda x: (x["rank"], -x["score"], x["person_id"]))
        money_flow = money_flow_items[:25]

        # 2. Structural explanation
        structural_explanation: dict[str, dict[str, Any]] = {}
        for pid in person_ids:
            structural_explanation[pid] = {
                "person_id": pid,
                "degree": round(float(components.get("degree", {}).get(pid, 0.0)), 6),
                "betweenness": round(float(components.get("betweenness", {}).get(pid, 0.0)), 6),
                "eigenvector": round(float(components.get("eigenvector", {}).get(pid, 0.0)), 6),
                "composite": round(float(structural_composite.get(pid, 0.0)), 6),
            }

        # 3. Detectors: mule accounts and burner phones
        bank_path = store.csv_path(case_id, "bank")
        cdr_path = store.csv_path(case_id, "cdr")
        files_info = store.files_info(case_id)
        # F2: files_info()["bank"|"cdr"] can be None when absent
        bank_info = files_info.get("bank") or {}
        bank_sha256 = bank_info.get("sha256", "") if isinstance(bank_info, dict) else ""
        cdr_info = files_info.get("cdr") or {}
        cdr_sha256 = cdr_info.get("sha256", "") if isinstance(cdr_info, dict) else ""

        raw_mules = detect_mules(bank_path, config) if bank_path.is_file() else []
        raw_burners = detect_burners(cdr_path, config) if cdr_path.is_file() else []

        mule_items: list[dict[str, Any]] = []
        for m in raw_mules:
            acc_id = str(m["id"])
            m_score = float(m["score"])
            ctrl_by = sorted(
                set(account_to_persons.get(acc_id, []))
                | set(account_to_persons.get(f"ACCOUNT:{acc_id}", []))
            )
            mule_items.append(
                {
                    "id": acc_id,
                    "score": m_score,
                    "flagged": m_score >= mule_min_score,
                    "reasons": m.get("reasons", []),
                    "evidence_rows": {
                        "file": "bank.csv",
                        "sha256": bank_sha256,
                        "rows": [max(1, r - 1) for r in m.get("evidence_rows", [])],
                    },
                    "controlled_by": ctrl_by,
                }
            )
        mule_accounts = mule_items[:25]

        burner_items: list[dict[str, Any]] = []
        for b in raw_burners:
            ph_id = str(b["id"])
            b_score = float(b["score"])
            owned_by = sorted(
                set(phone_to_persons.get(ph_id, []))
                | set(phone_to_persons.get(f"PHONE:{ph_id}", []))
            )
            burner_items.append(
                {
                    "id": ph_id,
                    "score": b_score,
                    "flagged": b_score >= burner_min_score,
                    "reasons": b.get("reasons", []),
                    "evidence_rows": {
                        "file": "cdr.csv",
                        "sha256": cdr_sha256,
                        "rows": [max(1, r - 1) for r in b.get("evidence_rows", [])],
                    },
                    "owned_by": owned_by,
                }
            )
        burner_phones = burner_items[:25]

        # 4. Role chips
        flagged_mule_ids = {m["id"] for m in mule_items if m["flagged"]}
        flagged_burner_ids = {b["id"] for b in burner_items if b["flagged"]}

        role_chips = assign_role_chips(
            person_nodes=person_nodes,
            financial_rank=pessimistic_fin_ranks,
            cut_members=cut_members or set(),
            mule_accounts_flagged=flagged_mule_ids,
            burner_phones_flagged=flagged_burner_ids,
            owner_maps=owner_maps,
            mule_min_score=mule_min_score,
            burner_min_score=burner_min_score,
        )

        # 5. Generated from references
        doc_metas = store.list_documents(case_id)
        generated_from = {
            "documents": [
                {"doc_id": d["doc_id"], "sha256": d.get("sha256_raw", d.get("sha256", ""))}
                for d in doc_metas
            ],
            "cdr": {
                "file": "cdr.csv",
                "sha256": cdr_sha256,
            },
            "bank": {
                "file": "bank.csv",
                "sha256": bank_sha256,
            },
        }

        leads_payload = {
            "case_id": case_id,
            "config_sha256": curr_cfg_sha,
            "disclaimer": DISCLAIMER,
            "document_hash": doc_hash,
            "fingerprint": fingerprint,
            "generated_from": generated_from,
            "limitations": LIMITATIONS,
            "money_flow": money_flow,
            "mule_accounts": mule_accounts,
            "burner_phones": burner_phones,
            "role_chips": role_chips,
            "schema_version": "1.1",
            "structural_explanation": structural_explanation,
        }

        if is_default_run:
            _atomic_write_json(leads_path, leads_payload)
        return leads_payload


def run_break(
    store: Storage,
    case_id: str,
    group_a: Sequence[str],
    group_b: Sequence[str],
) -> dict[str, Any]:
    """
    Compute communication-layer break between group_a and group_b using min vertex cut.
    """
    if not group_a or not group_b:
        raise InvalidGroupError("Groups must be non-empty")

    set_a = set(str(x).strip() for x in group_a if str(x).strip())
    set_b = set(str(x).strip() for x in group_b if str(x).strip())

    if not set_a or not set_b:
        raise InvalidGroupError("Groups must be non-empty")

    if set_a & set_b:
        raise InvalidGroupError("group_a and group_b must be disjoint")

    if len(set_a) > 200 or len(set_b) > 200:
        raise InvalidGroupError("Groups must each contain at most 200 members")

    graph = build_graph(store, case_id)
    known_persons: dict[str, str] = {}
    for n in graph.get("nodes", []):
        if n.get("type") == "PERSON":
            pid = str(n.get("id"))
            pname = n.get("canonical_name") or (n.get("names", [None])[0] if n.get("names") else pid)
            known_persons[pid] = pname

    unknown = (set_a | set_b) - set(known_persons.keys())
    if unknown:
        raise InvalidGroupError(f"Unknown person IDs in groups: {sorted(unknown)}")

    # Build owners map for call layer: device -> person node IDs
    owners: dict[str, list[str]] = defaultdict(list)
    for edge in graph.get("edges", []):
        if edge.get("relation") == "OWNS_DEVICE":
            src = str(edge.get("source", "")).strip()
            tgt = str(edge.get("target", "")).strip()
            if src in known_persons:
                pid, ph = src, tgt
            elif tgt in known_persons:
                pid, ph = tgt, src
            else:
                continue

            clean_ph = ph[len("PHONE:"):] if ph.startswith("PHONE:") else ph
            if pid not in owners[clean_ph]:
                owners[clean_ph].append(pid)
            if pid not in owners[ph]:
                owners[ph].append(pid)

    # Read CDR rows
    cdr_path = store.csv_path(case_id, "cdr")
    cdr_rows: list[dict[str, Any]] = []
    if cdr_path.is_file():
        with open(cdr_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            cdr_rows = list(reader)

    # Build call layer graph & run break
    call_graph = call_layer_graph(cdr_rows, owners)
    break_res = break_groups(call_graph, sorted(set_a), sorted(set_b))
    bridging = unowned_bridging_phones(cdr_rows, owners, sorted(set_a), sorted(set_b))

    finite = bool(break_res.get("finite", False))
    # F10: Read direct_links_count and reason from frozen break_groups
    direct_link = (
        break_res.get("reason") == "direct_link"
        or break_res.get("direct_links_count", 0) > 0
    )
    size = int(break_res.get("size", 0)) if finite else 0
    raw_cut = break_res.get("cut", []) if finite else []
    cut_formatted = [
        {"name": known_persons.get(pid, pid), "person_id": pid}
        for pid in raw_cut
    ]

    try:
        cut_details = _compute_cut_details(
            call_graph=call_graph,
            raw_cut=raw_cut,
            group_a=sorted(set_a),
            group_b=sorted(set_b),
            known_persons=known_persons,
            person_to_phones=_extract_owner_maps(graph)["person_to_phones"],
            case_graph=graph,
        )
    except Exception:
        cut_details = {}

    return {
        "bridging_unowned_phones": bridging,
        "cut": cut_formatted,
        "cut_details": cut_details,
        "direct_link": direct_link,
        "disclaimer": DISCLAIMER,
        "finite": finite,
        "groups_used": {
            "group_a": sorted(set_a),
            "group_b": sorted(set_b),
        },
        "note": BREAK_NOTE,
        "size": size,
    }


def _compute_cut_details(
    call_graph: dict[str, Any],
    raw_cut: Sequence[str],
    group_a: Sequence[str],
    group_b: Sequence[str],
    known_persons: dict[str, str],
    person_to_phones: dict[str, list[str]],
    case_graph: dict[str, Any],
) -> dict[str, Any]:
    """
    Determine observed call-layer shortest paths connecting group A and group B members via each cut person.
    """
    import networkx as nx
    from kavach_api.render import render_graph

    cut_set = set(raw_cut)
    if not cut_set:
        return {}

    G = nx.Graph()
    for node in call_graph.get("nodes", []):
        G.add_node(str(node.get("id", "")))
    for edge in call_graph.get("edges", []):
        G.add_edge(str(edge.get("source", "")), str(edge.get("target", "")))

    rendered = render_graph(case_graph)
    edge_id_map: dict[tuple[str, str], list[str]] = defaultdict(list)
    for e in rendered.get("elements", {}).get("edges", []):
        ed = e.get("data", {})
        src = str(ed.get("source", "")).strip()
        tgt = str(ed.get("target", "")).strip()
        eid = str(ed.get("id", "")).strip()
        if src and tgt and eid:
            edge_id_map[(min(src, tgt), max(src, tgt))].append(eid)

    cut_details: dict[str, Any] = {}
    for p in raw_cut:
        p_name = known_persons.get(p, p)
        connects: list[dict[str, Any]] = []
        hl_node_ids = set([p])
        hl_edge_ids: set[str] = set()

        if str(p) in G:
            for a in group_a:
                a_str = str(a)
                if a_str not in G:
                    continue
                for b in group_b:
                    b_str = str(b)
                    if b_str not in G:
                        continue
                    best_path = None
                    try:
                        if nx.has_path(G, a_str, b_str):
                            for sp in nx.all_shortest_paths(G, a_str, b_str):
                                if (set(sp) & cut_set) == {p}:
                                    best_path = sp
                                    break
                    except Exception:
                        best_path = None

                    if best_path is not None:
                        a_name = known_persons.get(a, a)
                        b_name = known_persons.get(b, b)
                        connects.append({
                            "a_id": a,
                            "a_name": a_name,
                            "b_id": b,
                            "b_name": b_name,
                            "pair_text": f"{a_name} <-> {b_name}",
                            "path": best_path,
                        })
                        for pid in best_path:
                            hl_node_ids.add(pid)
                        for idx in range(len(best_path) - 1):
                            u_pid = best_path[idx]
                            v_pid = best_path[idx + 1]
                            u_devs = [
                                ("PHONE:" + d if not str(d).startswith("PHONE:") else str(d))
                                for d in person_to_phones.get(u_pid, [])
                            ]
                            v_devs = [
                                ("PHONE:" + d if not str(d).startswith("PHONE:") else d)
                                for d in person_to_phones.get(v_pid, [])
                            ]
                            for ud in u_devs:
                                for vd in v_devs:
                                    e_key = (min(ud, vd), max(ud, vd))
                                    if e_key in edge_id_map:
                                        hl_node_ids.add(ud)
                                        hl_node_ids.add(vd)
                                        hl_edge_ids.update(edge_id_map[e_key])
                                        oe_u = (min(u_pid, ud), max(u_pid, ud))
                                        if oe_u in edge_id_map:
                                            hl_edge_ids.update(edge_id_map[oe_u])
                                        oe_v = (min(v_pid, vd), max(v_pid, vd))
                                        if oe_v in edge_id_map:
                                            hl_edge_ids.update(edge_id_map[oe_v])

        cut_details[p] = {
            "person_id": p,
            "name": p_name,
            "connects": connects,
            "highlight_ids": sorted(hl_node_ids | hl_edge_ids),
            "highlight_node_ids": sorted(hl_node_ids),
            "highlight_edge_ids": sorted(hl_edge_ids),
        }

    return cut_details
