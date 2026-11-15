"""Generate 50 seeded synthetic crime cases for planted-case evaluation v2 (seeds 151..200)."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from data.synthetic.generate_case import generate_case


def generate_planted_cases_v2(
    start_seed: int = 151,
    end_seed: int = 200,
    days: int = 30,
    out_base_dir: str | Path = "data/synthetic/out/planted_v2",
) -> tuple[int, dict[int, str]]:
    """Generate cases for seeds in [start_seed, end_seed]. Refuse if base folder exists."""
    base_path = Path(out_base_dir)
    if base_path.exists():
        raise FileExistsError(
            f"ERROR: Output directory already exists, refusing to overwrite: {base_path}"
        )

    base_path.mkdir(parents=True, exist_ok=False)
    ok_count = 0
    errors: dict[int, str] = {}

    for seed in range(start_seed, end_seed + 1):
        case_dir = base_path / f"seed_{seed}"
        try:
            generate_case(seed=seed, days=days, out_dir=str(case_dir))
            ok_count += 1
        except Exception as exc:
            errors[seed] = str(exc)
            print(f"ERROR generating seed {seed}: {exc}", file=sys.stderr)

    return ok_count, errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate 50 seeded synthetic cases (seeds 151..200)."
    )
    parser.add_argument("--start-seed", type=int, default=151)
    parser.add_argument("--end-seed", type=int, default=200)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument(
        "--out-dir",
        default="data/synthetic/out/planted_v2",
        help="Base directory for generated cases.",
    )
    args = parser.parse_args(argv)

    try:
        ok_count, errors = generate_planted_cases_v2(
            start_seed=args.start_seed,
            end_seed=args.end_seed,
            days=args.days,
            out_base_dir=args.out_dir,
        )
    except FileExistsError as err:
        print(str(err), file=sys.stderr)
        return 1

    print(f"Planted cases generation complete: {ok_count} OK, {len(errors)} errors.")
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())

