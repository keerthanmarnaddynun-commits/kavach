"""CLI to run strict and resolved kingpin scoring, baselines, and robustness."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from case_analytics.baselines import compute_baselines  # noqa: E402
from case_analytics.scores import (  # noqa: E402
    COMPOSITE_WEIGHTS,
    DEFAULT_BASE_WEIGHTS,
    compute_kingpin_scores,
    compute_robustness,
)


def _dump_json(path: Path, data: dict) -> None:
    text = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compute kingpin scores, baselines, and weight robustness."
    )
    parser.add_argument(
        "--graph",
        default="data/graph/out/case_demo_v2_r2/graph.json",
        help="Input case graph JSON path.",
    )
    parser.add_argument(
        "--out-dir",
        default="data/graph/out/case_demo_v2_r2/analytics",
        help="Output analytics directory (must not already exist).",
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=200,
        help="Number of robustness perturbation samples (default: 200).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=20261112,
        help="NumPy RandomState seed (default: 20261112).",
    )
    args = parser.parse_args(argv)

    out_dir = Path(args.out_dir)
    if out_dir.exists():
        print(
            f"ERROR: Output folder already exists, refusing to overwrite: {out_dir}",
            file=sys.stderr,
        )
        return 1

    with Path(args.graph).open("r", encoding="utf-8") as fh:
        graph_data = json.load(fh)

    scores_strict = compute_kingpin_scores(graph_data, mode="strict")
    scores_resolved = compute_kingpin_scores(graph_data, mode="resolved")

    baselines_strict = compute_baselines(graph_data, mode="strict")
    baselines_resolved = compute_baselines(graph_data, mode="resolved")

    robustness_strict = compute_robustness(
        graph_data, mode="strict", n_samples=args.samples, seed=args.seed
    )
    robustness_resolved = compute_robustness(
        graph_data, mode="resolved", n_samples=args.samples, seed=args.seed
    )

    run_info = {
        "base_weights": dict(DEFAULT_BASE_WEIGHTS),
        "composite_weights": dict(COMPOSITE_WEIGHTS),
        "modes": {
            "resolved": {
                "edges_used": scores_resolved["edges_used"],
                "eigenvector_converged": scores_resolved["eigenvector_converged"],
                "eigenvector_method": scores_resolved["eigenvector_method"],
                "nodes_used": scores_resolved["nodes_used"],
                "person_nodes_ranked": scores_resolved["person_nodes_ranked"],
            },
            "strict": {
                "edges_used": scores_strict["edges_used"],
                "eigenvector_converged": scores_strict["eigenvector_converged"],
                "eigenvector_method": scores_strict["eigenvector_method"],
                "nodes_used": scores_strict["nodes_used"],
                "person_nodes_ranked": scores_strict["person_nodes_ranked"],
            },
        },
        "robustness_n_samples": args.samples,
        "robustness_seed": args.seed,
    }

    out_dir.mkdir(parents=True, exist_ok=False)
    _dump_json(out_dir / "scores_strict.json", scores_strict)
    _dump_json(out_dir / "scores_resolved.json", scores_resolved)
    _dump_json(out_dir / "baselines_strict.json", baselines_strict)
    _dump_json(out_dir / "baselines_resolved.json", baselines_resolved)
    _dump_json(out_dir / "robustness_strict.json", robustness_strict)
    _dump_json(out_dir / "robustness_resolved.json", robustness_resolved)
    _dump_json(out_dir / "run_info.json", run_info)

    print(f"Wrote kingpin analytics outputs to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

