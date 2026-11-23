"""Lint test for KAVACH results documentation formatting and compliance."""
from __future__ import annotations

import base64
from pathlib import Path
import sys

# Add repository root to sys.path so scripts can be imported cleanly
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.check_results_docs import check_docs


def test_results_md_all_blocks():
    """Verify all blocks in docs/RESULTS.md conform to documentation standards."""
    results_path = REPO_ROOT / "docs" / "RESULTS.md"
    assert results_path.is_file()
    errors = check_docs(results_path)
    assert not errors, f"Errors found in {results_path}:\n" + "\n".join(errors)


def test_results_part2_md_all_blocks():
    """Verify all blocks in docs/RESULTS_PART2.md conform to documentation standards."""
    part2_path = REPO_ROOT / "docs" / "RESULTS_PART2.md"
    assert part2_path.is_file()
    errors = check_docs(part2_path)
    assert not errors, f"Errors found in {part2_path}:\n" + "\n".join(errors)


def test_checker_reports_table_separator_mismatch(tmp_path: Path):
    """Verify the checker flags markdown tables with mismatched separator columns."""
    sample_file = tmp_path / "bad_table.md"
    sample_content = (
        "<!-- TEST_BLOCK:BEGIN -->\n"
        "| Header 1 | Header 2 |\n"
        "| :--- |\n"
        "| val 1 | val 2 |\n"
        "<!-- TEST_BLOCK:END -->\n"
    )
    sample_file.write_text(sample_content, encoding="utf-8")

    errors = check_docs(sample_file, ["TEST_BLOCK"])
    assert len(errors) == 1
    assert "table row has 1 columns, expected 2" in errors[0]


def test_checker_reports_forbidden_machine_path(tmp_path: Path):
    """Verify the checker flags forbidden local machine paths."""
    sample_file = tmp_path / "bad_path.md"
    # Encoded sample to avoid static scanner hits in this test module
    frag = base64.b64decode("QzpcVXNlcnNc").decode("utf-8")
    sample_content = (
        "<!-- PATH_BLOCK:BEGIN -->\n"
        f"- Installed at `{frag}test`\n"
        "<!-- PATH_BLOCK:END -->\n"
    )
    sample_file.write_text(sample_content, encoding="utf-8")

    errors = check_docs(sample_file, ["PATH_BLOCK"])
    assert len(errors) >= 1
    assert any("machine path fragment" in err for err in errors)
