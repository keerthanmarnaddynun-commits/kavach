"""Test that model_performance.json matches regenerated snapshot from official results."""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from scripts.build_model_performance import generate_snapshot, OFFICIAL_FILES, OUTPUT_PATH

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_regenerate_model_performance_snapshot():
    """Verify that committed snapshot matches deterministic generation from source files."""
    # Check if results directory exists; skip with clear message if missing
    for name, path in OFFICIAL_FILES.items():
        if not path.is_file():
            pytest.skip(f"results/ source file {path} missing; skipping model performance snapshot test")

    assert OUTPUT_PATH.is_file(), f"Snapshot file missing at {OUTPUT_PATH}"

    # Generate fresh in-memory snapshot
    regenerated = generate_snapshot()

    # Load committed snapshot
    with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
        committed = json.load(f)

    # Compare snapshots
    assert regenerated == committed, "Committed model_performance.json differs from regenerated snapshot"


def test_snapshot_does_not_contain_post_hoc_estimates():
    """Ensure post-hoc estimates from gap analysis are strictly excluded from the snapshot."""
    if not OUTPUT_PATH.is_file():
        pytest.skip(f"Snapshot file missing at {OUTPUT_PATH}")

    with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    assert "post_hoc" not in content, "Found forbidden 'post_hoc' estimates in model_performance.json"
    assert "post_hoc_adjusted" not in content, "Found forbidden 'post_hoc_adjusted' in model_performance.json"


def test_snapshot_has_provenance_and_hashes():
    """Verify each block in the snapshot contains provenance captions and source file SHA-256."""
    if not OUTPUT_PATH.is_file():
        pytest.skip(f"Snapshot file missing at {OUTPUT_PATH}")

    with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    blocks = ["headline", "entities_by_type", "relations_by_type", "error_breakdown", "generalisation_gap", "baselines", "speed"]
    for b in blocks:
        assert b in data, f"Missing block '{b}' in model_performance.json"
        block_data = data[b]
        assert "provenance_caption" in block_data, f"Block '{b}' missing provenance_caption"
        assert "source" in block_data or "sources" in block_data, f"Block '{b}' missing source file hash info"
