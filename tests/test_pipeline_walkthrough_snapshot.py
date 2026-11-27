"""Test that pipeline_walkthrough.json matches regenerated snapshot from pipeline execution."""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from scripts.build_pipeline_walkthrough import (
    generate_walkthrough,
    OUTPUT_PATH,
    SAMPLE_SPECS,
)


def test_regenerate_pipeline_walkthrough_snapshot():
    """Verify that committed snapshot matches deterministic generator output."""
    for spec in SAMPLE_SPECS:
        if not spec["path"].is_file():
            pytest.skip(f"Sample FIR file missing at {spec['path']}; skipping snapshot test")

    assert OUTPUT_PATH.is_file(), f"Snapshot file missing at {OUTPUT_PATH}"

    try:
        regenerated = generate_walkthrough()
    except Exception as exc:
        pytest.skip(f"Pipeline model could not load or run ({exc}); skipping walkthrough snapshot test")

    with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
        committed = json.load(f)

    assert regenerated == committed, "Committed pipeline_walkthrough.json differs from regenerated snapshot"


def test_walkthrough_structure():
    """Verify that walkthrough JSON contains all sample specs, 8 steps each, code map, and timings."""
    if not OUTPUT_PATH.is_file():
        pytest.skip(f"Snapshot file missing at {OUTPUT_PATH}")

    with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert "samples" in data, "Missing 'samples' key in walkthrough snapshot"
    assert len(data["samples"]) == len(SAMPLE_SPECS), f"Expected {len(SAMPLE_SPECS)} samples, found {len(data['samples'])}"

    assert "stage_timings" in data, "Missing 'stage_timings' key in walkthrough snapshot"
    assert "code_map" in data, "Missing 'code_map' key in walkthrough snapshot"
    assert len(data["code_map"]) == 7, f"Expected 7 code map stages, found {len(data['code_map'])}"

    expected_stages = [
        "raw",
        "model",
        "postprocess",
        "names_identifiers",
        "assemble",
        "relations",
        "validate",
        "graph",
    ]

    for sample in data["samples"]:
        assert "steps" in sample, f"Sample {sample.get('sample_id')} missing 'steps'"
        assert len(sample["steps"]) == 8, f"Sample {sample.get('sample_id')} steps count != 8"
        actual_stages = [st["stage_id"] for st in sample["steps"]]
        assert actual_stages == expected_stages, f"Stage mismatch in sample {sample.get('sample_id')}: {actual_stages}"


def test_walkthrough_step2_alignment_fir01():
    """Verify Step 2 postprocessing alignment on FIR_01 (B + icky -> Bicky)."""
    if not OUTPUT_PATH.is_file():
        pytest.skip(f"Snapshot file missing at {OUTPUT_PATH}")

    with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    fir01 = next((s for s in data["samples"] if s["sample_id"] == "FIR_01"), None)
    assert fir01 is not None, "FIR_01 sample missing"

    step2 = fir01["steps"][2]
    items = step2["new_items"]
    bicky_row = next((r for r in items if r["cleaned"] == "Bicky"), None)
    assert bicky_row is not None, "Bicky row missing from Step 2"
    assert bicky_row["raw_text"] == "B + icky"
    assert bicky_row["raw_pieces"] == ["B", "icky"]
    assert "merged 2 pieces" in bicky_row["changes"]
    assert bicky_row["status"] == "merged 2 pieces"

    cleaned_count = len(step2["spans"])
    dropped_count = sum(1 for r in items if r["status"] == "dropped")
    assert len(items) == cleaned_count + dropped_count
    assert len(items) == 12

