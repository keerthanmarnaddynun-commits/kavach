"""Design check (B4) for 50 planted cases v2 (seeds 151..200).

Computes entity and transaction counts, call-count rankings of pizza shop and
kingpins, mule and burner counts, validation flags, and file SHA-256 hashes.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(65536):
            h.update(chunk)
    return h.hexdigest()


def check_case_directory(case_dir: Path) -> dict[str, Any]:
    truth_file = case_dir / "truth.json"
    cdr_file = case_dir / "cdr.csv"
    bank_file = case_dir / "bank.csv"

    with truth_file.open("r", encoding="utf-8") as fh:
        truth = json.load(fh)

    call_counts: Counter[str] = Counter()
    cdr_rows = 0
    with cdr_file.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            cdr_rows += 1
            call_counts[row["a_party"]] += 1
            call_counts[row["b_party"]] += 1

    bank_rows = 0
    with bank_file.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for _ in reader:
            bank_rows += 1

    # Include all phones from truth and CDR
    all_phones = set(call_counts.keys())
    for ph in truth.get("phones", []):
        p_val = ph.get("phone") if isinstance(ph, dict) else str(ph)
        if p_val:
            all_phones.add(p_val)
    for p in truth.get("people", []):
        for ph in p.get("phones", []):
            p_val = ph.get("phone") if isinstance(ph, dict) else str(ph)
            if p_val:
                all_phones.add(p_val)

    # Rank by descending call count, breaking ties by ascending phone string
    ranked_phones = sorted(all_phones, key=lambda p: (-call_counts[p], str(p)))
    phone_rank_map = {ph: idx + 1 for idx, ph in enumerate(ranked_phones)}
    total_phones = len(ranked_phones)

    pizza_shop_number = str(truth.get("decoys", {}).get("pizza_shop_number", ""))
    pizza_rank = phone_rank_map.get(pizza_shop_number)

    kp_ids = [str(x) for x in truth.get("kingpin_ids", [])]
    kp_info: dict[str, dict[str, Any]] = {}
    kp_ranks: list[int] = []

    for p in truth.get("people", []):
        pid = str(p.get("person_id", ""))
        if pid in kp_ids:
            phones = [
                str(ph.get("phone"))
                for ph in p.get("phones", [])
                if isinstance(ph, dict) and ph.get("phone")
            ]
            ranks = [phone_rank_map.get(ph) for ph in phones if ph in phone_rank_map]
            kp_info[pid] = {
                "name": p.get("name", ""),
                "phones": phones,
                "ranks": ranks,
            }
            for r in ranks:
                if r is not None:
                    kp_ranks.append(r)

    pizza_shop_is_rank_1 = pizza_rank == 1
    # Bottom 10% condition: rank > 0.90 * total_phones
    bottom_10_threshold = 0.90 * total_phones
    kingpins_in_bottom_10_percent = bool(
        kp_ranks and all(r > bottom_10_threshold for r in kp_ranks)
    )

    seed_name = case_dir.name
    try:
        seed_num = int(seed_name.split("_")[-1])
    except ValueError:
        seed_num = None

    return {
        "accounts_count": len(truth.get("accounts", [])),
        "bank_rows": bank_rows,
        "burner_phones_count": len(truth.get("burner_phones", [])),
        "case_name": seed_name,
        "cdr_rows": cdr_rows,
        "flags": {
            "kingpins_in_bottom_10_percent_by_calls": kingpins_in_bottom_10_percent,
            "pizza_shop_is_rank_1": pizza_shop_is_rank_1,
        },
        "kingpin_phones": kp_info,
        "kingpin_ranks": kp_ranks,
        "mule_accounts_count": len(truth.get("mule_accounts", [])),
        "people_count": len(truth.get("people", [])),
        "phones_count": total_phones,
        "pizza_shop_phone": pizza_shop_number,
        "pizza_shop_rank": pizza_rank,
        "seed": seed_num,
        "sha256": {
            "bank_csv": _compute_sha256(bank_file),
            "cdr_csv": _compute_sha256(cdr_file),
            "truth_json": _compute_sha256(truth_file),
        },
    }


def run_checks(
    cases_dir: str | Path = "data/synthetic/out/planted_v2",
    out_file: str | Path = "data/graph/out/planted_eval_v2/planted_check.json",
) -> dict[str, Any]:
    cases_path = Path(cases_dir)
    out_path = Path(out_file)

    if out_path.exists():
        raise FileExistsError(
            f"ERROR: Output file already exists, refusing to overwrite: {out_path}"
        )

    case_dirs = sorted(
        [d for d in cases_path.iterdir() if d.is_dir() and d.name.startswith("seed_")],
        key=lambda d: int(d.name.split("_")[-1])
        if d.name.split("_")[-1].isdigit()
        else d.name,
    )

    cases_results: list[dict[str, Any]] = []
    pizza_rank_1_count = 0
    kp_bottom_10_count = 0

    for cd in case_dirs:
        res = check_case_directory(cd)
        cases_results.append(res)
        if res["flags"]["pizza_shop_is_rank_1"]:
            pizza_rank_1_count += 1
        if res["flags"]["kingpins_in_bottom_10_percent_by_calls"]:
            kp_bottom_10_count += 1

    total = len(cases_results)
    summary = {
        "kingpins_in_bottom_10_percent_by_calls_count": kp_bottom_10_count,
        "pizza_shop_is_rank_1_count": pizza_rank_1_count,
        "total_cases_checked": total,
    }

    report = {
        "cases": cases_results,
        "summary": summary,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, sort_keys=True)

    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Design check (B4) for planted cases v2."
    )
    parser.add_argument(
        "--cases-dir",
        default="data/synthetic/out/planted_v2",
        help="Directory containing generated planted cases.",
    )
    parser.add_argument(
        "--out-file",
        default="data/graph/out/planted_eval_v2/planted_check.json",
        help="Output JSON file for check report.",
    )
    args = parser.parse_args(argv)

    try:
        report = run_checks(args.cases_dir, args.out_file)
    except FileExistsError as err:
        print(str(err), file=sys.stderr)
        return 1

    sm = report["summary"]
    print(
        f"Checked {sm['total_cases_checked']} cases: "
        f"pizza_rank_1={sm['pizza_shop_is_rank_1_count']}, "
        f"kp_bottom_10={sm['kingpins_in_bottom_10_percent_by_calls_count']}."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

