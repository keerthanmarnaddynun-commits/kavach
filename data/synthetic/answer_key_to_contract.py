"""
Converter from synthetic FIR answer keys to Contract 1 v1.1.

Converts answer keys (FIR_XX.json) to Contract 1 v1.1 compliant JSON schemas
(FIR_XX.contract.json) along with companion link mapping files (FIR_XX.links.json).
"""

from __future__ import annotations

import argparse
import glob
import json
import os
from pathlib import Path
import re
import sys
from typing import Any

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from contracts.v1_1.validate import validate_ai_output


def convert_fir(
    fir_data: dict[str, Any],
    truth_fathers: dict[str, str],
    truth_banks: dict[str, str],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Convert a single FIR answer key dict to Contract 1 v1.1 format."""
    transfer_amounts = [
        r.get("amount")
        for r in fir_data.get("relationships", [])
        if r.get("relation") == "TRANSFERRED_FUNDS"
    ]

    cash_dropped = 0
    groups: dict[str, dict[str, Any]] = {}
    last_suspect_key: str | None = None

    for e in fir_data.get("entities", []):
        etype = e.get("type")
        erole = e.get("role")
        ekey = e.get("entity_key")

        # AMOUNT is not an entity
        if etype == "AMOUNT":
            val = e.get("value")
            if val not in transfer_amounts:
                cash_dropped += 1
            continue

        # Attach FATHER mention to suspect
        if erole == "FATHER":
            # Use explicit link field if available, else nearest preceding SUSPECT
            suspect_key = (
                e.get("suspect_key")
                or e.get("linked_suspect")
                or e.get("suspect_id")
                or last_suspect_key
            )
            if suspect_key is None or suspect_key not in groups:
                raise ValueError(f"FATHER mention '{e.get('id')}' has no preceding suspect to attach to.")

            father_mention = {
                "char_span": list(e["char_span"]),
                "surface": e["surface"],
                "kind": "FATHER",
            }
            groups[suspect_key]["mentions"].append(father_mention)

            tid = groups[suspect_key].get("truth_id")
            truth_father = truth_fathers.get(tid) if tid else None
            groups[suspect_key]["father_name"] = (
                truth_father or e.get("value") or e.get("surface")
            )
            continue

        if erole == "SUSPECT" and etype == "PERSON":
            last_suspect_key = ekey

        if ekey not in groups:
            groups[ekey] = {
                "entity_key": ekey,
                "type": "PERSON" if etype == "ALIAS" else etype,
                "truth_id": e.get("truth_id"),
                "role": erole,
                "mentions": [],
                "aliases": [],
                "canonical_name": None,
                "value": None,
                "father_name": None,
                "bank": None,
            }

        g = groups[ekey]
        if etype == "ALIAS":
            g["mentions"].append(
                {"char_span": list(e["char_span"]), "surface": e["surface"], "kind": "ALIAS"}
            )
            surf = e["surface"]
            if surf not in g["aliases"]:
                g["aliases"].append(surf)
        elif etype == "PERSON":
            g["mentions"].append(
                {"char_span": list(e["char_span"]), "surface": e["surface"], "kind": "NAME"}
            )
            if g["canonical_name"] is None:
                g["canonical_name"] = e["surface"]
            if g["role"] is None and erole:
                g["role"] = erole
            if g["truth_id"] is None and e.get("truth_id"):
                g["truth_id"] = e.get("truth_id")
        else:  # PHONE, IMEI, ACCOUNT
            g["mentions"].append(
                {"char_span": list(e["char_span"]), "surface": e["surface"], "kind": "VALUE"}
            )
            if g["value"] is None:
                val = re.sub(r"\D", "", str(e.get("value") or e.get("surface")))
                g["value"] = val
                if etype == "ACCOUNT" and val in truth_banks:
                    g["bank"] = truth_banks[val]

    # Sort mentions for each group by start position
    for g in groups.values():
        g["mentions"].sort(key=lambda m: m["char_span"][0])
        g["first_start"] = g["mentions"][0]["char_span"][0]

    # Sort entities by first mention position
    sorted_groups = sorted(groups.values(), key=lambda g: g["first_start"])
    key_to_id: dict[str, str] = {}
    contract_entities: list[dict[str, Any]] = []
    links: dict[str, dict[str, Any]] = {}
    ent_type_counts: dict[str, int] = {}

    for idx, g in enumerate(sorted_groups, start=1):
        ent_id = f"ent_{idx:02d}"
        key_to_id[g["entity_key"]] = ent_id
        ent_obj: dict[str, Any] = {
            "id": ent_id,
            "type": g["type"],
            "char_span": list(g["mentions"][0]["char_span"]),
            "mentions": g["mentions"],
            "ai_confidence": 1.0,
            "flags": ["GOLD"],
        }
        if g["type"] == "PERSON":
            ent_obj["canonical_name"] = g["canonical_name"]
            if g["aliases"]:
                ent_obj["aliases"] = g["aliases"]
            if g["role"]:
                ent_obj["role"] = g["role"]
            if g["father_name"]:
                ent_obj["father_name"] = g["father_name"]
        else:
            ent_obj["value"] = g["value"]
            if g.get("bank"):
                ent_obj["bank"] = g["bank"]

        contract_entities.append(ent_obj)
        links[ent_id] = {
            "entity_key": g["entity_key"],
            "truth_id": g["truth_id"],
        }
        ent_type_counts[g["type"]] = ent_type_counts.get(g["type"], 0) + 1

    # Relationships
    seen_rel_sigs: set[tuple[Any, ...]] = set()
    contract_rels: list[dict[str, Any]] = []
    dup_rels_dropped = 0
    rel_type_counts: dict[str, int] = {}

    for r in fir_data.get("relationships", []):
        src_id = key_to_id[r["source_key"]]
        tgt_id = key_to_id[r["target_key"]]
        rel_obj: dict[str, Any] = {
            "source": src_id,
            "target": tgt_id,
            "relation": r["relation"],
        }
        if r.get("amount") is not None and r["amount"] > 0:
            rel_obj["amount"] = float(r["amount"])
        if r.get("evidence_char_span") is not None:
            rel_obj["evidence_char_span"] = list(r["evidence_char_span"])

        sig = (
            src_id,
            tgt_id,
            r["relation"],
            rel_obj.get("amount"),
            tuple(rel_obj.get("evidence_char_span") or []),
        )
        if sig in seen_rel_sigs:
            dup_rels_dropped += 1
        else:
            seen_rel_sigs.add(sig)
            contract_rels.append(rel_obj)
            rel_type_counts[r["relation"]] = rel_type_counts.get(r["relation"], 0) + 1

    contract_doc = {
        "schema_version": "1.1",
        "case_id": "CASE_DEMO_V2",
        "source_doc_id": fir_data["source_doc_id"],
        "entities": contract_entities,
        "relationships": contract_rels,
    }

    # Validate output schema & semantic checks
    validate_ai_output(contract_doc)

    stats = {
        "entities_by_type": ent_type_counts,
        "relations_by_type": rel_type_counts,
        "cash_amounts_dropped": cash_dropped,
        "duplicate_relations_dropped": dup_rels_dropped,
    }

    return contract_doc, links, stats


def convert_all(
    firs_dir: Path | str,
    case_dir: Path | str,
    out_dir: Path | str,
) -> dict[str, Any]:
    """Convert all FIR answer keys in firs_dir to Contract 1 v1.1 in out_dir."""
    firs_dir = Path(firs_dir).resolve()
    case_dir = Path(case_dir).resolve()
    out_dir = Path(out_dir).resolve()

    if out_dir.exists():
        raise FileExistsError(f"Output directory '{out_dir}' already exists. Refusing to overwrite.")

    truth_path = case_dir / "truth.json"
    if not truth_path.exists():
        raise FileNotFoundError(f"Case truth file not found at '{truth_path}'.")

    with open(truth_path, "r", encoding="utf-8") as f:
        truth = json.load(f)

    truth_fathers = {
        p["person_id"]: p.get("father_name")
        for p in truth.get("people", [])
        if "person_id" in p
    }
    truth_banks = {
        acc["account_number"]: acc.get("bank")
        for acc in truth.get("accounts", [])
        if "account_number" in acc and "bank" in acc
    }

    fir_files = sorted(glob.glob(str(firs_dir / "FIR_*.json")))
    if not fir_files:
        raise FileNotFoundError(f"No FIR JSON answer keys found in '{firs_dir}'.")

    out_dir.mkdir(parents=True, exist_ok=False)

    firs_converted = 0
    total_entities_by_type: dict[str, int] = {}
    total_relations_by_type: dict[str, int] = {}
    total_cash_dropped = 0
    total_dup_rels_dropped = 0

    for fpath in fir_files:
        with open(fpath, "r", encoding="utf-8") as f:
            fir_data = json.load(f)

        fir_id = fir_data.get("source_doc_id") or Path(fpath).stem
        contract_doc, links_doc, stats = convert_fir(fir_data, truth_fathers, truth_banks)

        contract_out_path = out_dir / f"{fir_id}.contract.json"
        links_out_path = out_dir / f"{fir_id}.links.json"

        with open(contract_out_path, "w", encoding="utf-8") as f:
            json.dump(contract_doc, f, indent=2, ensure_ascii=False)
            f.write("\n")

        with open(links_out_path, "w", encoding="utf-8") as f:
            json.dump(links_doc, f, indent=2, ensure_ascii=False)
            f.write("\n")

        firs_converted += 1
        for k, v in stats["entities_by_type"].items():
            total_entities_by_type[k] = total_entities_by_type.get(k, 0) + v
        for k, v in stats["relations_by_type"].items():
            total_relations_by_type[k] = total_relations_by_type.get(k, 0) + v
        total_cash_dropped += stats["cash_amounts_dropped"]
        total_dup_rels_dropped += stats["duplicate_relations_dropped"]

    return {
        "firs_converted": firs_converted,
        "entities_by_type": total_entities_by_type,
        "relations_by_type": total_relations_by_type,
        "cash_amounts_dropped": total_cash_dropped,
        "duplicate_relations_dropped": total_dup_rels_dropped,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert FIR answer keys to Contract 1 v1.1 schemas.")
    parser.add_argument("--firs-dir", required=True, help="Directory containing FIR_XX.json answer keys")
    parser.add_argument(
        "--case-dir",
        action="append",
        required=True,
        help="Case directory containing truth.json (if repeated, the last valid one is used)",
    )
    parser.add_argument("--out", required=True, help="Output directory for contract and link files")

    args = parser.parse_args()

    # Handle multiple --case-dir flags if provided
    case_dir_candidate = args.case_dir[-1]
    # Check if truth.json exists in candidate; if not check earlier entries
    if not (Path(case_dir_candidate) / "truth.json").exists():
        for cd in reversed(args.case_dir):
            if (Path(cd) / "truth.json").exists():
                case_dir_candidate = cd
                break

    try:
        metrics = convert_all(
            firs_dir=args.firs_dir,
            case_dir=case_dir_candidate,
            out_dir=args.out,
        )
    except FileExistsError as e:
        sys.stderr.write(f"Error: {e}\n")
        sys.exit(1)
    except Exception as e:
        sys.stderr.write(f"Conversion failed: {e}\n")
        sys.exit(1)

    print("Conversion Summary:")
    print(f"  FIRs Converted: {metrics['firs_converted']}")
    print(f"  Entities by Type: {metrics['entities_by_type']}")
    print(f"  Relations by Type: {metrics['relations_by_type']}")
    print(f"  Cash Amounts Dropped: {metrics['cash_amounts_dropped']}")
    print(f"  Duplicate Relations Dropped: {metrics['duplicate_relations_dropped']}")


if __name__ == "__main__":
    main()

