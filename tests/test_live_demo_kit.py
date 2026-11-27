"""Unit tests for live-demo kit generator and intake validation."""
from __future__ import annotations

import csv
from pathlib import Path
import pytest

from kavach_api.ingest import decode_fir, validate_bank, validate_cdr
from kavach_api.settings import load_settings
from scripts.case_timing import inspect_case_timing
from scripts.make_live_demo_kit import write_kit, SCRATCH_DIR

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_live_demo_kit_determinism(tmp_path):
    """Verify that the live-demo kit generates identical content across independent runs."""
    dir1 = tmp_path / "run1"
    dir2 = tmp_path / "run2"

    res1 = write_kit(dir1)
    res2 = write_kit(dir2)

    assert res1["validation_ok"] is True
    assert res2["validation_ok"] is True

    # Check byte-for-byte identity of all generated files
    for fname in ["FIR_A.txt", "FIR_B.txt", "FIR_C.txt", "cdr.csv", "bank.csv", "bad_cdr.csv", "EXPECTED.txt"]:
        f1_bytes = (dir1 / fname).read_bytes()
        f2_bytes = (dir2 / fname).read_bytes()
        assert f1_bytes == f2_bytes, f"Determinism failure: {fname} differed between runs"


def test_live_demo_kit_intake_validation(tmp_path):
    """Verify generated FIRs, CDR and Bank CSVs pass real kavach_api intake validation."""
    out_dir = tmp_path / "test_kit"
    res = write_kit(out_dir)
    assert res["validation_ok"] is True

    settings = load_settings()

    # 1. FIR files validation
    for fir_name in ["FIR_A.txt", "FIR_B.txt", "FIR_C.txt"]:
        p = out_dir / fir_name
        raw = p.read_bytes()
        decoded = decode_fir(raw, settings.max_fir_chars)
        assert len(decoded) > 500, f"{fir_name} too short"
        assert len(decoded) <= settings.max_fir_chars, f"{fir_name} exceeds max_fir_chars"

    # 2. Valid CDR CSV
    cdr_bytes = (out_dir / "cdr.csv").read_bytes()
    cdr_rep = validate_cdr(cdr_bytes, settings)
    assert cdr_rep.ok is True
    assert cdr_rep.error_count == 0
    assert 400 <= cdr_rep.rows <= 600, f"CDR rows {cdr_rep.rows} outside 400-600 range"

    # 3. Valid Bank CSV
    bank_bytes = (out_dir / "bank.csv").read_bytes()
    bank_rep = validate_bank(bank_bytes, settings)
    assert bank_rep.ok is True
    assert bank_rep.error_count == 0
    assert 100 <= bank_rep.rows <= 200, f"Bank rows {bank_rep.rows} outside 100-200 range"

    # 4. Bad CDR CSV triggers expected rejection
    bad_cdr_bytes = (out_dir / "bad_cdr.csv").read_bytes()
    bad_rep = validate_cdr(bad_cdr_bytes, settings)
    assert bad_rep.ok is False
    assert bad_rep.error_count > 0
    assert any(err.get("code") == "missing_column" for err in bad_rep.errors)


def test_live_demo_kit_entity_linkage(tmp_path):
    """Verify that the 3 FIRs share at least 2 persons, 2 phone numbers, and 1 bank account."""
    out_dir = tmp_path / "test_kit"
    write_kit(out_dir)

    fir_a = (out_dir / "FIR_A.txt").read_text(encoding="utf-8")
    fir_b = (out_dir / "FIR_B.txt").read_text(encoding="utf-8")
    fir_c = (out_dir / "FIR_C.txt").read_text(encoding="utf-8")

    # Shared persons check
    shared_persons = ["Amitabh Sen", "Rohit Verma", "Kunal Mehra"]
    for p in shared_persons:
        count = sum(1 for text in [fir_a, fir_b, fir_c] if p in text)
        assert count >= 2, f"Expected {p} in at least 2 FIRs, found in {count}"

    # Shared phones check
    shared_phones = ["9811022334", "9823011223", "9877033445"]
    for phone in shared_phones:
        count = sum(1 for text in [fir_a, fir_b, fir_c] if phone in text)
        assert count >= 2, f"Expected {phone} in at least 2 FIRs, found in {count}"

    # Shared bank account check
    shared_account = "40192837465"
    for text in [fir_a, fir_b, fir_c]:
        assert shared_account in text, f"Expected shared account {shared_account} in all 3 FIRs"


def test_case_timing_script():
    """Verify that case_timing.py inspects existing demo case cleanly without error."""
    runtime_dir = REPO_ROOT / "runtime"
    if not (runtime_dir / "cases" / "C-927fc7de12").is_dir():
        pytest.skip("Reference demo case C-927fc7de12 not found in runtime")

    report = inspect_case_timing("C-927fc7de12", runtime_dir)
    assert report["case_id"] == "C-927fc7de12"
    assert report["earliest_upload"]["iso"] != "N/A"
    assert report["results_ready"]["iso"] != "N/A"
    assert report["total_duration_sec"] is not None
    assert report["total_duration_sec"] >= 0.0
