"""Run mule and burner detectors on CSV logs (cdr.csv, bank.csv) of a case directory."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from case_detectors.burner import detect_burners
from case_detectors.mule import detect_mules


def run_detectors(
    case_dir: str | Path,
    out_dir: str | Path,
) -> tuple[Path, Path]:
    case_path = Path(case_dir)
    out_path = Path(out_dir)

    if out_path.exists():
        raise FileExistsError(
            f"ERROR: Output directory already exists, refusing to overwrite: {out_path}"
        )

    bank_csv = case_path / "bank.csv"
    cdr_csv = case_path / "cdr.csv"

    if not bank_csv.exists():
        raise FileNotFoundError(f"bank.csv not found in {case_path}")
    if not cdr_csv.exists():
        raise FileNotFoundError(f"cdr.csv not found in {case_path}")

    mules = detect_mules(bank_csv)
    burners = detect_burners(cdr_csv)

    out_path.mkdir(parents=True, exist_ok=False)

    mule_file = out_path / "mule_scores.json"
    with mule_file.open("w", encoding="utf-8") as fh:
        json.dump(mules, fh, indent=2, sort_keys=True)

    burner_file = out_path / "burner_scores.json"
    with burner_file.open("w", encoding="utf-8") as fh:
        json.dump(burners, fh, indent=2, sort_keys=True)

    return mule_file, burner_file


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run CSV detectors on bank.csv and cdr.csv."
    )
    parser.add_argument("case_dir", help="Directory containing cdr.csv and bank.csv")
    parser.add_argument("out_dir", help="Output directory to write results")
    args = parser.parse_args(argv)

    try:
        mule_file, burner_file = run_detectors(args.case_dir, args.out_dir)
    except (FileExistsError, FileNotFoundError) as err:
        print(str(err), file=sys.stderr)
        return 1

    print(f"Detectors executed successfully:")
    print(f"  Mule leads written to: {mule_file}")
    print(f"  Burner leads written to: {burner_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
