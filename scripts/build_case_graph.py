"""CLI wrapper to build and validate the deterministic case graph."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from case_graph.builder import build_case_graph  # noqa: E402
from case_graph.validate import validate_graph  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build deterministic case graph JSON.")
    parser.add_argument(
        "--fir-dir",
        default="results/2026-11-11_step6_extraction_r2/run1",
        help="Directory containing FIR_*.analysis.json files.",
    )
    parser.add_argument(
        "--cdr",
        default="data/synthetic/out/case_demo_v2/cdr.csv",
        help="Path to cdr.csv.",
    )
    parser.add_argument(
        "--bank",
        default="data/synthetic/out/case_demo_v2/bank.csv",
        help="Path to bank.csv.",
    )
    parser.add_argument(
        "--out-dir",
        default="data/graph/out/case_demo_v2",
        help="Output directory (must not already exist).",
    )
    args = parser.parse_args(argv)

    out_dir = Path(args.out_dir)
    if out_dir.exists():
        print(
            f"ERROR: Output folder already exists, refusing to overwrite: {out_dir}",
            file=sys.stderr,
        )
        return 1

    graph = build_case_graph(args.fir_dir, args.cdr, args.bank)
    errors = validate_graph(graph)
    if errors:
        for err in errors:
            print(f"VALIDATION ERROR: {err}", file=sys.stderr)
        return 1

    out_dir.mkdir(parents=True, exist_ok=False)
    graph_text = json.dumps(graph, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    stats_text = (
        json.dumps(graph["stats"], indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    )

    with (out_dir / "graph.json").open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(graph_text)
    with (out_dir / "stats.json").open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(stats_text)

    print(
        f"Wrote graph.json ({graph['stats']['total_nodes']} nodes, "
        f"{graph['stats']['total_edges']} edges) and stats.json to {out_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

