"""
Tests for Step 7 held-out reporting helpers and validators.
"""

from __future__ import annotations

import pytest
import numpy as np

from scripts.report.step7_llm_heldout import (
    check_table_column_counts,
    scan_forbidden_words,
    compute_bootstrap_intervals,
    FORBIDDEN_WORDS,
)
from scripts.report.step6_extraction import get_metric_by_path


def test_table_column_counts_valid():
    """Valid markdown table with consistent column counts passes."""
    table = (
        "| Col1 | Col2 | Col3 |\n"
        "| :--- | :--- | :--- |\n"
        "| A    | B    | C    |\n"
        "| D    | E    | F    |\n"
    )
    # Should not raise
    check_table_column_counts(table)


def test_table_column_counts_mismatch():
    """Markdown table with mismatched column count raises ValueError."""
    table = (
        "| Col1 | Col2 | Col3 |\n"
        "| :--- | :--- | :--- |\n"
        "| A    | B    |\n"  # missing column
        "| D    | E    | F    |\n"
    )
    with pytest.raises(ValueError, match="Inconsistent column counts"):
        check_table_column_counts(table)


def test_key_number_helper_resolves_and_raises():
    """get_metric_by_path resolves valid nested paths and raises on missing steps."""
    data = {
        "headline": {
            "mentions": {
                "strict": {
                    "f1": 0.885,
                    "tp": 200,
                }
            }
        }
    }
    path, val = get_metric_by_path(data, "headline.mentions.strict.f1")
    assert path == "headline.mentions.strict.f1"
    assert val == 0.885

    # Missing step
    with pytest.raises(ValueError, match="Missing metrics path step"):
        get_metric_by_path(data, "headline.relations.micro.f1")


def test_bootstrap_reproducible():
    """Bootstrap interval calculation is bitwise reproducible with fixed seed."""
    sample_file_metrics = {
        "F1": {
            "mentions": {"tp": 10, "fp": 1, "fn": 2},
            "relations": {"tp": 5, "fp": 0, "fn": 1},
        },
        "F2": {
            "mentions": {"tp": 8, "fp": 2, "fn": 1},
            "relations": {"tp": 4, "fp": 1, "fn": 0},
        },
        "F3": {
            "mentions": {"tp": 12, "fp": 0, "fn": 3},
            "relations": {"tp": 6, "fp": 0, "fn": 2},
        },
    }

    ci1_m, ci1_r = compute_bootstrap_intervals(sample_file_metrics, n_resamples=500, seed=20261117)
    ci2_m, ci2_r = compute_bootstrap_intervals(sample_file_metrics, n_resamples=500, seed=20261117)

    assert ci1_m == ci2_m
    assert ci1_r == ci2_r
    assert ci1_m[0] <= ci1_m[1]
    assert ci1_r[0] <= ci1_r[1]


def test_forbidden_word_scan_flags_each_forbidden_word():
    """Forbidden word scan flags each prohibited word individually."""
    for word in FORBIDDEN_WORDS:
        text = f"This result is {word} by experiment."
        detected = scan_forbidden_words(text)
        assert len(detected) == 1
        assert detected[0].lower() == word.lower()


def test_forbidden_word_scan_clean():
    """Forbidden word scan returns empty list on compliant prose."""
    clean_text = (
        "The extractor was evaluated on held-out data. "
        "Strict character span matching yielded consistent outcomes."
    )
    detected = scan_forbidden_words(clean_text)
    assert detected == []


def test_regenerate_step7_markdown_preserves_surrounding(tmp_path):
    """Regenerating markdown modifies strictly the block between STEP7 markers."""
    from scripts.report.step7_llm_heldout import regenerate_step7_markdown, REPO_ROOT

    # Setup dummy md file
    md_file = tmp_path / "RESULTS.md"
    pre_content = "# Results Title\n\nSome introductory text.\n\n"
    step7_dummy = "<!-- STEP7:BEGIN -->\nDummy content to replace\n<!-- STEP7:END -->"
    post_content = "\n\n## Section Next\nTrailing content.\n"
    md_file.write_text(pre_content + step7_dummy + post_content, encoding="utf-8")

    r2_dir = REPO_ROOT / "results" / "2026-11-16_step7_llm_heldout_r2"
    if (r2_dir / "metrics.json").is_file():
        diff = regenerate_step7_markdown(r2_dir, results_md_path=md_file)
        new_text = md_file.read_text(encoding="utf-8")
        assert new_text.startswith(pre_content)
        assert new_text.endswith(post_content)
        assert "<!-- STEP7:BEGIN -->" in new_text
        assert "<!-- STEP7:END -->" in new_text
        assert "Dummy content to replace" not in new_text
        assert len(diff) > 0

