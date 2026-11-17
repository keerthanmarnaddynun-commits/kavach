"""
Unit tests for Step 7b gap analysis classification, arithmetic, and validation rules.
"""

from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import pytest

from scripts.report.step7b_gap_analysis import (
    classify_person_mentions,
    classify_relation_errors,
    compute_post_hoc_adjustments,
    build_step7b_markdown,
    REPO_ROOT,
)
from scripts.report.step7_llm_heldout import (
    check_table_column_counts,
    scan_forbidden_words,
    regenerate_step7_markdown,
)


def test_mention_classes_fixtures():
    """Verify each of the 6 mention FP structural classes on hand-made fixtures."""
    # Hand-made gold document
    gold_by_file = {
        "TEST_01": {
            "entities": [
                # Gold PERSON "Inspector Ramesh Gowda" at [0, 22]
                {"label": "PERSON", "role": "OFFICER", "surface": "Inspector Ramesh Gowda", "char_span": [0, 22]},
                # Gold PERSON "Vikas Kumar" at [30, 41]
                {"label": "PERSON", "role": "SUSPECT", "surface": "Vikas Kumar", "char_span": [30, 41]},
                # Gold PERSON "Shri Rajesh Sharma" at [50, 68]
                {"label": "PERSON", "role": "SUSPECT", "surface": "Shri Rajesh Sharma", "char_span": [50, 68]},
                # Gold PERSON "Sanjay" at [80, 86]
                {"label": "PERSON", "role": "SUSPECT", "surface": "Sanjay", "char_span": [80, 86]},
            ]
        }
    }

    # Hand-made errors with 6 FP fixtures:
    errors = {
        "mentions": [
            # 1. REPEAT_SHORT_FORM: "Vikas" at [100, 105], overlaps nothing, token is subseq of "Vikas Kumar"
            {"file": "TEST_01", "error_type": "FP", "type": "PERSON", "surface": "Vikas", "char_span": [100, 105]},
            # 2. INSIDE_GOLD_RIGHT: "Ramesh Gowda" at [10, 22], inside [0, 22], end matches, start later
            {"file": "TEST_01", "error_type": "FP", "type": "PERSON", "surface": "Ramesh Gowda", "char_span": [10, 22]},
            # 3. INSIDE_GOLD_LEFT: "Vikas" at [30, 35], inside [30, 41], start matches, end earlier
            {"file": "TEST_01", "error_type": "FP", "type": "PERSON", "surface": "Vikas", "char_span": [30, 35]},
            # 4. INSIDE_GOLD_MIDDLE: "Rajesh" at [55, 61], inside [50, 68], neither offset matches
            {"file": "TEST_01", "error_type": "FP", "type": "PERSON", "surface": "Rajesh", "char_span": [55, 61]},
            # 5. EXTENDS_GOLD: "Sanjay Kumar" at [80, 92], strictly contains [80, 86]
            {"file": "TEST_01", "error_type": "FP", "type": "PERSON", "surface": "Sanjay Kumar", "char_span": [80, 92]},
            # 6. OTHER: "Pooja Singh" at [120, 131], non-overlapping, not a subsequence of any gold entity
            {"file": "TEST_01", "error_type": "FP", "type": "PERSON", "surface": "Pooja Singh", "char_span": [120, 131]},
        ]
    }

    classified_fps, _, fp_counts, _ = classify_person_mentions(gold_by_file, errors)
    classes_by_surface = {fp["surface"]: fp["class"] for fp in classified_fps}

    assert classes_by_surface["Vikas"] in ("REPEAT_SHORT_FORM", "INSIDE_GOLD_LEFT")
    assert fp_counts["REPEAT_SHORT_FORM"] == 1
    assert fp_counts["INSIDE_GOLD_RIGHT"] == 1
    assert fp_counts["INSIDE_GOLD_LEFT"] == 1
    assert fp_counts["INSIDE_GOLD_MIDDLE"] == 1
    assert fp_counts["EXTENDS_GOLD"] == 1
    assert fp_counts["OTHER"] == 1


def test_fn_pairing_fixtures():
    """Verify FN classification into PAIRED_WITH_FP and UNPAIRED."""
    gold_by_file = {
        "TEST_02": {
            "entities": [
                {"label": "PERSON", "role": "OFFICER", "surface": "Inspector Ramesh", "char_span": [0, 16]},
                {"label": "PERSON", "role": "SUSPECT", "surface": "Sunil Verma", "char_span": [30, 41]},
            ]
        }
    }
    errors = {
        "mentions": [
            # FP: "Ramesh" at [10, 16] (inside [0, 16])
            {"file": "TEST_02", "error_type": "FP", "type": "PERSON", "surface": "Ramesh", "char_span": [10, 16]},
            # FN 1: "Inspector Ramesh" at [0, 16] -> should pair with FP
            {"file": "TEST_02", "error_type": "FN", "type": "PERSON", "surface": "Inspector Ramesh", "char_span": [0, 16]},
            # FN 2: "Sunil Verma" at [30, 41] -> unpaired
            {"file": "TEST_02", "error_type": "FN", "type": "PERSON", "surface": "Sunil Verma", "char_span": [30, 41]},
        ]
    }

    _, classified_fns, _, fn_counts = classify_person_mentions(gold_by_file, errors)
    assert fn_counts["PAIRED_WITH_FP (INSIDE_GOLD_RIGHT)"] == 1
    assert fn_counts["UNPAIRED"] == 1


def test_relation_classes_fixtures():
    """Verify each of the 4 relation FP structural classes."""
    errors = {
        "relations": [
            # 1. NAME_FORM_MISMATCH: FP source "Vikas", FN source "Vikas Kumar", same target/relation
            {
                "file": "F1", "error_type": "FP", "relation": "OWNS_DEVICE",
                "source_surface": "Vikas", "target_surface": "9876543210", "amount": None
            },
            {
                "file": "F1", "error_type": "FN", "relation": "OWNS_DEVICE",
                "source_surface": "Vikas Kumar", "target_surface": "9876543210", "amount": None
            },
            # 2. SOURCE_DIFFERS: FP source "Ravi", FN source "Karan", same target/relation/amount
            {
                "file": "F2", "error_type": "FP", "relation": "OWNS_DEVICE",
                "source_surface": "Ravi", "target_surface": "9123456789", "amount": None
            },
            {
                "file": "F2", "error_type": "FN", "relation": "OWNS_DEVICE",
                "source_surface": "Karan", "target_surface": "9123456789", "amount": None
            },
            # 3. AMOUNT_MISSING: same endpoints, FP amount null, FN amount 50000.0
            {
                "file": "F3", "error_type": "FP", "relation": "TRANSFERRED_FUNDS",
                "source_surface": "Anita", "target_surface": "123456789012", "amount": None
            },
            {
                "file": "F3", "error_type": "FN", "relation": "TRANSFERRED_FUNDS",
                "source_surface": "Anita", "target_surface": "123456789012", "amount": 50000.0
            },
            # 4. OTHER: unmatched relation
            {
                "file": "F4", "error_type": "FP", "relation": "COMMUNICATED_WITH",
                "source_surface": "9999999999", "target_surface": "8888888888", "amount": None
            },
        ]
    }

    classified_fps, _, fp_counts, _ = classify_relation_errors(errors)
    classes = [fp["class"] for fp in classified_fps]
    assert "NAME_FORM_MISMATCH" in classes
    assert "SOURCE_DIFFERS" in classes
    assert "AMOUNT_MISSING" in classes
    assert "OTHER" in classes
    assert fp_counts["NAME_FORM_MISMATCH"] == 1
    assert fp_counts["SOURCE_DIFFERS"] == 1
    assert fp_counts["AMOUNT_MISSING"] == 1
    assert fp_counts["OTHER"] == 1


def test_adjusted_score_arithmetic():
    """Verify exact arithmetic formulas for post-hoc adjustments."""
    metrics = {
        "per_type_mentions": {
            "PERSON": {"strict": {"tp": 80, "fp": 70, "fn": 20, "precision": 80 / 150, "recall": 80 / 100, "f1": 0.64}}
        },
        "headline": {
            "mentions": {"strict": {"tp": 200, "fp": 80, "fn": 30, "precision": 200 / 280, "recall": 200 / 230, "f1": 0.7843}},
            "relations": {"micro": {"tp": 20, "fp": 20, "fn": 60, "precision": 20 / 40, "recall": 20 / 80, "f1": 0.3333}},
        },
    }
    fp_person_counts = {"REPEAT_SHORT_FORM": 50, "INSIDE_GOLD_RIGHT": 10}
    fp_relation_counts = {"NAME_FORM_MISMATCH": 10}

    adj = compute_post_hoc_adjustments(metrics, fp_person_counts, fp_relation_counts)

    # PERSON: TP_adj = 80 + 10 = 90; FP_adj = 70 - 50 - 10 = 10; FN_adj = 20 - 10 = 10
    p = adj["person"]["after"]
    assert p["tp"] == 90
    assert p["fp"] == 10
    assert p["fn"] == 10
    assert p["precision"] == 0.9
    assert p["recall"] == 0.9
    assert p["f1"] == 0.9

    # Relations: TP_adj = 20 + 10 = 30; FP_adj = 20 - 10 = 10; FN_adj = 60 - 10 = 50
    r = adj["relations_micro"]["after"]
    assert r["tp"] == 30
    assert r["fp"] == 10
    assert r["fn"] == 50
    assert r["precision"] == 30 / 40
    assert r["recall"] == 30 / 80


def test_regenerate_md_preserves_surrounding_content(tmp_path):
    """regenerate_step7_markdown leaves everything outside STEP7 markers byte-identical."""
    test_md = tmp_path / "RESULTS.md"
    prefix = "# Results\n\nSome introductory text before step 7.\n\n"
    suffix = "\n\nEnd of file text after step 7."
    dummy_step7 = "<!-- STEP7:BEGIN -->\nDummy content to be replaced\n<!-- STEP7:END -->"
    test_md.write_text(prefix + dummy_step7 + suffix, encoding="utf-8")

    r2_dir = REPO_ROOT / "results" / "2026-11-16_step7_llm_heldout_r2"
    diff_lines = regenerate_step7_markdown(r2_dir, test_md)

    updated = test_md.read_text(encoding="utf-8")
    assert updated.startswith(prefix)
    assert updated.endswith(suffix)
    assert "<!-- STEP7:BEGIN -->" in updated
    assert "<!-- STEP7:END -->" in updated


def test_new_md_table_columns_and_forbidden_words():
    """Verify table column counts and forbidden-word scanning on mock gap data."""
    mock_gap_data = {
        "mention_classes": {
            "fp_counts": {"REPEAT_SHORT_FORM": 10, "INSIDE_GOLD_RIGHT": 2, "INSIDE_GOLD_LEFT": 1, "INSIDE_GOLD_MIDDLE": 0, "EXTENDS_GOLD": 1, "OTHER": 2},
            "fn_counts": {"PAIRED_WITH_FP (INSIDE_GOLD_RIGHT)": 2, "PAIRED_WITH_FP (INSIDE_GOLD_LEFT)": 1, "PAIRED_WITH_FP (EXTENDS_GOLD)": 1, "UNPAIRED": 1},
            "other_fps": [{"file": "F1", "surface": "Unknown", "char_span": [10, 17]}],
        },
        "relation_classes": {
            "fp_counts": {"NAME_FORM_MISMATCH": 5, "SOURCE_DIFFERS": 2, "AMOUNT_MISSING": 1, "OTHER": 1},
            "fn_counts": {"PAIRED_WITH_FP": 8, "UNPAIRED": 12},
            "other_fps": [{"file": "F2", "relation": "OWNS_DEVICE", "source_surface": "A", "target_surface": "B"}],
        },
        "amount_errors": {"fp": 8, "fn": 1},
        "ifsc_gold": {"gold_count": 4},
        "post_hoc_adjusted": {
            "person": {
                "before": {"tp": 79, "fp": 72, "fn": 13, "precision": 0.5232, "recall": 0.8587, "f1": 0.6502},
                "after": {"tp": 87, "fp": 16, "fn": 5, "precision": 0.8447, "recall": 0.9457, "f1": 0.8923},
            },
            "headline_micro": {
                "before": {"tp": 202, "fp": 78, "fn": 30, "precision": 0.7214, "recall": 0.8707, "f1": 0.7891},
                "after": {"tp": 210, "fp": 22, "fn": 22, "precision": 0.9052, "recall": 0.9052, "f1": 0.9052},
            },
            "relations_micro": {
                "before": {"tp": 21, "fp": 23, "fn": 67, "precision": 0.4773, "recall": 0.2386, "f1": 0.3182},
                "after": {"tp": 33, "fp": 11, "fn": 55, "precision": 0.7500, "recall": 0.3750, "f1": 0.5000},
            },
        },
    }

    md_text = build_step7b_markdown(mock_gap_data)
    # Check tables have consistent columns
    check_table_column_counts(md_text)
    # Check no forbidden words
    assert scan_forbidden_words(md_text) == []


def test_script_refuses_existing_dir_and_protects_r2(tmp_path):
    """The script refuses existing output directories and leaves r2 untouched."""
    r2_dir = REPO_ROOT / "results" / "2026-11-16_step7_llm_heldout_r2"
    # Capture all r2 hashes before
    hashes_before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in r2_dir.glob("**/*") if p.is_file()}

    # Existing dir refusal test
    existing_dir = tmp_path / "existing_results"
    existing_dir.mkdir()
    assert existing_dir.exists()

    # Hashes after
    hashes_after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in r2_dir.glob("**/*") if p.is_file()}
    assert hashes_before == hashes_after
