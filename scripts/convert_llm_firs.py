"""Convert and validate LLM-authored FIR text files into gold answer keys and clean texts."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from llm_firs.convert import levenshtein_dist, parse_file


def compute_sha256(path: Path) -> str:
    """Compute SHA-256 of a file."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(65536):
            h.update(chunk)
    return h.hexdigest()


def compute_coverage_for_file(res: Any, raw_content: str) -> dict[str, Any]:
    """Compute per-file entity, mention, relation counts and brief requirements."""
    entities = res.entities
    rels = res.relationships

    persons_by_role = Counter([e["role"] for e in entities if e["label"] == "PERSON" and e.get("role") != "FATHER"])
    father_names = [e for e in entities if e.get("role") == "FATHER"]
    aliases_by_person: Counter[str] = Counter()
    for e in entities:
        if e["type"] == "ALIAS":
            aliases_by_person[e["entity_key"]] += 1

    counts = {
        "aadhaar": sum(1 for e in entities if e["type"] == "AADHAAR"),
        "accounts": sum(1 for e in entities if e["type"] == "ACCOUNT"),
        "aliases": sum(1 for e in entities if e["type"] == "ALIAS"),
        "aliases_per_person": dict(aliases_by_person),
        "amounts": sum(1 for e in entities if e["type"] == "AMOUNT"),
        "father_names": len(father_names),
        "ifsc": sum(1 for e in entities if e["type"] == "IFSC"),
        "imeis": sum(1 for e in entities if e["type"] == "IMEI"),
        "pan": sum(1 for e in entities if e["type"] == "PAN"),
        "persons_by_role": {
            "COMPLAINANT": persons_by_role.get("COMPLAINANT", 0),
            "OFFICER": persons_by_role.get("OFFICER", 0),
            "SUSPECT": persons_by_role.get("SUSPECT", 0),
            "WITNESS": persons_by_role.get("WITNESS", 0),
        },
        "phones": sum(1 for e in entities if e["type"] == "PHONE"),
        "relations_by_type": dict(Counter([r["relation"] for r in rels])),
        "upi": sum(1 for e in entities if e["type"] == "UPI"),
        "vehicle": sum(1 for e in entities if e["type"] == "VEHICLE"),
    }

    # Mechanically determined brief requirements
    satisfied_reqs: list[str] = []
    stem = res.stem

    # H_01 baseline: 1 suspect with phone, IMEI, account, amount
    if stem == "H_01":
        if (
            counts["persons_by_role"]["SUSPECT"] == 1
            and counts["phones"] >= 1
            and counts["imeis"] >= 1
            and counts["accounts"] >= 1
            and counts["amounts"] >= 1
        ):
            satisfied_reqs.append("H_01_baseline")

    # H_02/H_03: two different PERSON keys whose names differ by edit distance 1 or 2
    if stem in ("H_02", "H_03"):
        person_names_by_key: dict[str, str] = {}
        for e in entities:
            if e["type"] == "PERSON" and e.get("role") != "FATHER":
                person_names_by_key.setdefault(e["entity_key"], e["surface"])
        keys = list(person_names_by_key.keys())
        found_dist = False
        for i in range(len(keys)):
            for j in range(i + 1, len(keys)):
                n1 = person_names_by_key[keys[i]]
                n2 = person_names_by_key[keys[j]]
                # Check full string or first token edit distance
                d_full = levenshtein_dist(n1, n2)
                t1 = n1.split()[0] if n1.split() else n1
                t2 = n2.split()[0] if n2.split() else n2
                d_token = levenshtein_dist(t1, t2)
                if d_full in (1, 2) or d_token in (1, 2):
                    satisfied_reqs.append(f"{stem}_name_edit_dist_{min(d_full, d_token)}")
                    found_dist = True
                    break
            if found_dist:
                break

    # H_04/H_05: one person key with 3 or more ALIAS tags
    if stem in ("H_04", "H_05"):
        max_al = max(aliases_by_person.values()) if aliases_by_person else 0
        if max_al >= 3:
            satisfied_reqs.append(f"{stem}_3_or_more_aliases")

    # H_06: two different persons with OWNS_DEVICE to same phone key
    if stem == "H_06":
        phone_owners: dict[str, set[str]] = {}
        for r in rels:
            if r["relation"] == "OWNS_DEVICE":
                phone_owners.setdefault(r["target_key"], set()).add(r["source_key"])
        if any(len(owners) > 1 for owners in phone_owners.values()):
            satisfied_reqs.append("H_06_shared_phone")

    # H_07/H_08: no PHONE and no ACCOUNT tag
    if stem in ("H_07", "H_08"):
        if counts["phones"] == 0 and counts["accounts"] == 0:
            satisfied_reqs.append(f"{stem}_no_phone_no_account")

    # H_09/H_10: clean text containing line break inside digit sequence or double space inside number
    if stem in ("H_09", "H_10"):
        has_break = bool(re.search(r"\d\n\d", res.clean_text)) or bool(re.search(r"\d\n\d", raw_content))
        has_doublespace = bool(re.search(r"\d  \d", res.clean_text)) or bool(re.search(r"\d  \d", raw_content))
        if has_break or has_doublespace:
            satisfied_reqs.append(f"{stem}_broken_number_in_clean_text")

    # E files: at least one of UPI/PAN/AADHAAR/VEHICLE
    if stem.startswith("E_"):
        if counts["upi"] > 0 or counts["pan"] > 0 or counts["aadhaar"] > 0 or counts["vehicle"] > 0:
            satisfied_reqs.append("E_contains_special_identifier")

    # D files: account-to-account transfer
    if stem.startswith("D_"):
        has_acct_transfer = any(
            r["relation"] == "TRANSFERRED_FUNDS"
            and any(e["entity_key"] == r["source_key"] and e["type"] == "ACCOUNT" for e in entities)
            and any(e["entity_key"] == r["target_key"] and e["type"] == "ACCOUNT" for e in entities)
            for r in rels
        )
        if has_acct_transfer:
            satisfied_reqs.append("D_account_to_account_transfer")

    # Devanagari ratio
    dev_ratio = 0.0
    if res.language == "hindi":
        dev_chars = len(re.findall(r"[\u0900-\u097f]", res.clean_text))
        total_alpha = len(re.findall(r"\w", res.clean_text))
        dev_ratio = round(dev_chars / total_alpha, 4) if total_alpha else 0.0

    return {
        "brief_requirements": satisfied_reqs,
        "counts": counts,
        "devanagari_ratio": dev_ratio,
        "language": res.language,
        "mentions_count": len(entities),
        "relations_count": len(rels),
    }


def convert_all_firs(
    raw_dir: str | Path = "data/llm_firs/raw",
    out_dir: str | Path = "data/llm_firs/converted_r1",
) -> None:
    raw_path = Path(raw_dir)
    out_path = Path(out_dir)

    if out_path.exists():
        raise FileExistsError(
            f"ERROR: Output directory already exists, refusing to overwrite: {out_path}"
        )

    out_path.mkdir(parents=True, exist_ok=False)

    raw_files = sorted(raw_path.glob("*.txt"))
    raw_hashes: dict[str, str] = {}
    validation_files: dict[str, Any] = {}
    coverage_files: dict[str, Any] = {}

    warnings_by_type: dict[str, int] = Counter()
    files_by_warning: dict[str, list[str]] = {}

    lang_counts: dict[str, dict[str, int]] = {
        "english": {"invalid": 0, "total": 0, "valid": 0},
        "hindi": {"invalid": 0, "total": 0, "valid": 0},
        "hinglish": {"invalid": 0, "total": 0, "valid": 0},
    }

    aggregate_entities: Counter[str] = Counter()
    aggregate_relations: Counter[str] = Counter()
    mentions_total = 0
    valid_count = 0
    invalid_count = 0

    for rf in raw_files:
        rel_name = rf.name
        sha = compute_sha256(rf)
        raw_hashes[rel_name] = sha

        raw_content = rf.read_text(encoding="utf-8")
        parsed = parse_file(rf)
        lang = parsed.language or "unknown"
        if lang in lang_counts:
            lang_counts[lang]["total"] += 1

        if parsed.is_valid:
            valid_count += 1
            if lang in lang_counts:
                lang_counts[lang]["valid"] += 1

            # Write clean text
            txt_path = out_path / f"{parsed.stem}.txt"
            txt_path.write_text(parsed.clean_text, encoding="utf-8")

            # Write answer key JSON
            json_path = out_path / f"{parsed.stem}.json"
            gold_dict = parsed.to_gold_dict()
            json_path.write_text(
                json.dumps(gold_dict, indent=2, sort_keys=True),
                encoding="utf-8",
            )

            # Accumulate coverage
            cov_res = compute_coverage_for_file(parsed, raw_content)
            coverage_files[parsed.stem] = cov_res
            mentions_total += len(parsed.entities)
            for e in parsed.entities:
                aggregate_entities[e["type"]] += 1
            for r in parsed.relationships:
                aggregate_relations[r["relation"]] += 1

        else:
            invalid_count += 1
            if lang in lang_counts:
                lang_counts[lang]["invalid"] += 1

        # Track warnings
        file_warn_types = set()
        for w in parsed.warnings:
            wtype = w.get("type", "unknown")
            file_warn_types.add(wtype)
            warnings_by_type[wtype] += 1

        for wt in file_warn_types:
            files_by_warning.setdefault(wt, []).append(rel_name)

        validation_files[rel_name] = {
            "errors": parsed.errors,
            "valid": parsed.is_valid,
            "warnings": parsed.warnings,
        }

    # Build validation report
    validation_report = {
        "files": validation_files,
        "summary": {
            "invalid_files": invalid_count,
            "total_files": len(raw_files),
            "valid_files": valid_count,
        },
        "warnings_summary": {
            "counts_by_type": dict(sorted(warnings_by_type.items())),
            "files_affected": {k: sorted(v) for k, v in sorted(files_by_warning.items())},
        },
    }

    # Build coverage report
    coverage_report = {
        "aggregate": {
            "counts_by_language": lang_counts,
            "entities_by_type": dict(sorted(aggregate_entities.items())),
            "files_invalid_total": invalid_count,
            "files_valid_total": valid_count,
            "mentions_total": mentions_total,
            "relations_by_type": dict(sorted(aggregate_relations.items())),
        },
        "per_file": coverage_files,
    }

    # Write report files
    val_path = out_path / "validation_report.json"
    val_path.write_text(json.dumps(validation_report, indent=2, sort_keys=True), encoding="utf-8")

    cov_path = out_path / "coverage_report.json"
    cov_path.write_text(json.dumps(coverage_report, indent=2, sort_keys=True), encoding="utf-8")

    hash_path = out_path / "raw_hashes.json"
    hash_path.write_text(json.dumps(raw_hashes, indent=2, sort_keys=True), encoding="utf-8")

    print(f"Processed {len(raw_files)} files: {valid_count} VALID, {invalid_count} INVALID.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert and validate LLM-authored FIR files."
    )
    parser.add_argument(
        "raw_dir",
        nargs="?",
        default="data/llm_firs/raw",
        help="Input directory containing raw .txt files.",
    )
    parser.add_argument(
        "out_dir",
        nargs="?",
        default="data/llm_firs/converted_r1",
        help="Output directory for converted files.",
    )
    args = parser.parse_args(argv)

    try:
        convert_all_firs(raw_dir=args.raw_dir, out_dir=args.out_dir)
    except FileExistsError as err:
        print(str(err), file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
