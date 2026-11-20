"""Unit tests for ingestion validation of FIR text, CDR CSV, and Bank CSV files."""
from __future__ import annotations

import json
from pathlib import Path
import time
import pytest

from kavach_api.ingest import (
    REQUIRED_BANK_COLUMNS,
    REQUIRED_CDR_COLUMNS,
    CsvReport,
    IngestError,
    decode_fir,
    validate_bank,
    validate_cdr,
)
from kavach_api.settings import Settings, repo_root


@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    """Fixture providing settings configured with temporary runtime directory."""
    return Settings(
        runtime_dir=tmp_path / "runtime",
        max_upload_bytes=15 * 1024 * 1024,
        max_fir_chars=5000,
        max_csv_rows=500000,
    )


def test_decode_fir_valid_and_hindi() -> None:
    """FIR text decodes UTF-8 and Hindi characters, preserving newlines."""
    # Plain English with newlines and punctuation
    text = "First Information Report\nDate: 2026-01-01\nDetails here.\r\n"
    res = decode_fir(text.encode("utf-8"), max_chars=5000)
    assert res == text

    # Hindi / Devanagari text
    hindi_text = "प्रथम सूचना रिपोर्ट\nदिनांक: 2026-01-01\nशिकायतकर्ता: विकास कुमार\n"
    res_hindi = decode_fir(hindi_text.encode("utf-8"), max_chars=5000)
    assert res_hindi == hindi_text

    # UTF-8 BOM removed without altering text or newlines
    bom_bytes = b"\xef\xbb\xbf" + text.encode("utf-8")
    res_bom = decode_fir(bom_bytes, max_chars=5000)
    assert res_bom == text


def test_decode_fir_errors() -> None:
    """FIR decoding raises IngestError on invalid bytes, empty text, or length limit."""
    # Invalid non-UTF-8 bytes
    with pytest.raises(IngestError) as exc_info:
        decode_fir(b"\xff\xfe\x00\x12\x80", max_chars=5000)
    assert exc_info.value.code == "invalid_encoding"

    # Empty text
    with pytest.raises(IngestError) as exc_info:
        decode_fir(b"", max_chars=5000)
    assert exc_info.value.code == "empty_text"

    # Whitespace only
    with pytest.raises(IngestError) as exc_info:
        decode_fir(b"   \r\n\t  ", max_chars=5000)
    assert exc_info.value.code == "empty_text"

    # Only BOM
    with pytest.raises(IngestError) as exc_info:
        decode_fir(b"\xef\xbb\xbf   \n", max_chars=5000)
    assert exc_info.value.code == "empty_text"

    # Text too long
    long_text = "A" * 105
    with pytest.raises(IngestError) as exc_info:
        decode_fir(long_text.encode("utf-8"), max_chars=100)
    assert exc_info.value.code == "text_too_long"


def test_validate_cdr_valid_minimal(test_settings: Settings) -> None:
    """Minimal single-row valid CDR CSV passes validation."""
    header = ",".join(REQUIRED_CDR_COLUMNS)
    data_row = "9876543210,9123456789,123456789012345,404123456789012,2026-01-01T12:00:00,60,VOICE,TWR_01,28.6,77.2"
    csv_bytes = f"{header}\n{data_row}\n".encode("utf-8")

    report = validate_cdr(csv_bytes, test_settings)
    assert report.ok is True
    assert report.rows == 1
    assert report.errors == []
    assert report.error_count == 0

    # Test tuple unpacking
    ok, rows, cols, errs = report
    assert ok is True
    assert rows == 1
    assert len(cols) == 10
    assert errs == []


def test_validate_cdr_leading_zeros_and_bom_crlf(test_settings: Settings) -> None:
    """CDR validation accepts BOM, CRLF, empty IMEI, and retains leading zeros."""
    header = ",".join(REQUIRED_CDR_COLUMNS)
    # IMEI with leading zero, empty IMEI
    row1 = "9876543210,9123456789,012345678901234,404123456789012,2026-01-01T12:00:00,60,VOICE,TWR_01,28.6,77.2"
    row2 = "8765432109,7654321098,,404123456789012,2026-01-01T12:05:00,0,SMS,TWR_02,28.7,77.3"
    csv_text = f"{header}\r\n{row1}\r\n{row2}\r\n"
    csv_bytes = b"\xef\xbb\xbf" + csv_text.encode("utf-8")

    report = validate_cdr(csv_bytes, test_settings)
    assert report.ok is True
    assert report.rows == 2
    assert report.errors == []


def test_validate_cdr_rule_failures(test_settings: Settings) -> None:
    """Each CDR row rule failure is reported with exact 1-based data row and column."""
    header = ",".join(REQUIRED_CDR_COLUMNS)
    # Row 1: invalid a_party (starts with 5), invalid imei_a (14 digits)
    row1 = "5876543210,9123456789,12345678901234,404123456789012,2026-01-01T12:00:00,60,VOICE,TWR_01,28.6,77.2"
    # Row 2: invalid b_party (9 digits), invalid start_time, invalid duration_sec (-5), invalid call_type (DATA)
    row2 = "9876543210,912345678,123456789012345,404123456789012,not-a-time,-5,DATA,TWR_01,28.6,77.2"
    csv_bytes = f"{header}\n{row1}\n{row2}\n".encode("utf-8")

    report = validate_cdr(csv_bytes, test_settings)
    assert report.ok is False
    assert report.rows == 2

    row1_errors = [e for e in report.errors if e["row"] == 1]
    row2_errors = [e for e in report.errors if e["row"] == 2]

    # Row 1 checks
    cols1 = {e["column"]: e["code"] for e in row1_errors}
    assert cols1.get("a_party") == "invalid_phone"
    assert cols1.get("imei_a") == "invalid_imei"

    # Row 2 checks
    cols2 = {e["column"]: e["code"] for e in row2_errors}
    assert cols2.get("b_party") == "invalid_phone"
    assert cols2.get("start_time") == "invalid_datetime"
    assert cols2.get("duration_sec") == "invalid_duration"
    assert cols2.get("call_type") == "invalid_call_type"


def test_validate_cdr_missing_column(test_settings: Settings) -> None:
    """CDR upload missing a required column names that column in error report."""
    cols_without_tower = [c for c in REQUIRED_CDR_COLUMNS if c != "tower_id"]
    header = ",".join(cols_without_tower)
    row = "9876543210,9123456789,123456789012345,404123456789012,2026-01-01T12:00:00,60,VOICE,28.6,77.2"
    csv_bytes = f"{header}\n{row}\n".encode("utf-8")

    report = validate_cdr(csv_bytes, test_settings)
    assert report.ok is False
    assert report.rows == 0
    assert any("tower_id" in e["message"] for e in report.errors)
    assert any(e["column"] == "tower_id" for e in report.errors)


def test_validate_cdr_file_level_rejections(test_settings: Settings) -> None:
    """CDR upload rejects empty file, header-only, non-UTF-8, and oversized files."""
    header = ",".join(REQUIRED_CDR_COLUMNS)

    # Empty file
    r_empty = validate_cdr(b"", test_settings)
    assert r_empty.ok is False
    assert r_empty.errors[0]["code"] == "empty_file"

    # Header only
    r_header = validate_cdr(f"{header}\n".encode("utf-8"), test_settings)
    assert r_header.ok is False
    assert r_header.errors[0]["code"] == "header_only"

    # Non UTF-8 bytes
    r_encoding = validate_cdr(b"\xff\xfe\x00\x11", test_settings)
    assert r_encoding.ok is False
    assert r_encoding.errors[0]["code"] == "invalid_encoding"

    # Oversized file
    small_settings = Settings(
        runtime_dir=test_settings.runtime_dir,
        max_upload_bytes=10,
    )
    r_size = validate_cdr(f"{header}\n".encode("utf-8"), small_settings)
    assert r_size.ok is False
    assert r_size.errors[0]["code"] == "size_over_limit"


def test_validate_bank_valid_minimal(test_settings: Settings) -> None:
    """Minimal single-row valid Bank CSV passes validation."""
    header = ",".join(REQUIRED_BANK_COLUMNS)
    data_row = "TXN001,2026-01-01T08:00:00,12345678901,98765432109,1500.50,NEFT,SBIN0001234,Payment"
    csv_bytes = f"{header}\n{data_row}\n".encode("utf-8")

    report = validate_bank(csv_bytes, test_settings)
    assert report.ok is True
    assert report.rows == 1
    assert report.errors == []
    assert report.error_count == 0


def test_validate_bank_rule_failures(test_settings: Settings) -> None:
    """Each Bank row rule failure is reported with exact 1-based data row and column."""
    header = ",".join(REQUIRED_BANK_COLUMNS)
    # Row 1: invalid from_acct (4 digits), invalid to_acct (letters)
    row1 = "TXN001,2026-01-01T08:00:00,1234,ABCD5678901,1500.50,NEFT,SBIN0001234,Payment"
    # Row 2: invalid amount (0.00), invalid datetime, empty mode
    row2 = "TXN002,not-a-datetime,12345678901,98765432109,0.00,,SBIN0001234,Payment"
    # Row 3: invalid amount (3 decimal places: 15.555)
    row3 = "TXN003,2026-01-01T09:00:00,12345678901,98765432109,15.555,IMPS,SBIN0001234,Payment"
    csv_bytes = f"{header}\n{row1}\n{row2}\n{row3}\n".encode("utf-8")

    report = validate_bank(csv_bytes, test_settings)
    assert report.ok is False
    assert report.rows == 3

    r1_errs = {e["column"]: e["code"] for e in report.errors if e["row"] == 1}
    assert r1_errs.get("from_acct") == "invalid_account"
    assert r1_errs.get("to_acct") == "invalid_account"

    r2_errs = {e["column"]: e["code"] for e in report.errors if e["row"] == 2}
    assert r2_errs.get("amount") == "invalid_amount"
    assert r2_errs.get("datetime") == "invalid_datetime"
    assert r2_errs.get("mode") == "invalid_mode"

    r3_errs = {e["column"]: e["code"] for e in report.errors if e["row"] == 3}
    assert r3_errs.get("amount") == "invalid_amount"


def test_validate_bank_missing_column(test_settings: Settings) -> None:
    """Bank upload missing a required column names that column in error report."""
    cols_without_ifsc = [c for c in REQUIRED_BANK_COLUMNS if c != "ifsc"]
    header = ",".join(cols_without_ifsc)
    row = "TXN001,2026-01-01T08:00:00,12345678901,98765432109,1500.50,NEFT,Payment"
    csv_bytes = f"{header}\n{row}\n".encode("utf-8")

    report = validate_bank(csv_bytes, test_settings)
    assert report.ok is False
    assert report.rows == 0
    assert any("ifsc" in e["message"] for e in report.errors)
    assert any(e["column"] == "ifsc" for e in report.errors)


def test_error_capping_at_50_with_error_count(test_settings: Settings) -> None:
    """Errors collection is capped at 50 but total error_count continues counting."""
    header = ",".join(REQUIRED_CDR_COLUMNS)
    # Generate 70 rows each having an invalid a_party
    bad_rows = [
        f"12345,9123456789,123456789012345,404123456789012,2026-01-01T12:00:00,60,VOICE,TWR_01,28.6,77.2"
        for _ in range(70)
    ]
    csv_bytes = (header + "\n" + "\n".join(bad_rows) + "\n").encode("utf-8")

    report = validate_cdr(csv_bytes, test_settings)
    assert report.ok is False
    assert report.rows == 70
    assert len(report.errors) == 50
    assert report.error_count == 70


def test_real_demo_v2_files_pass_and_row_counts_match_stats(test_settings: Settings) -> None:
    """Real files cdr.csv and bank.csv pass with 0 errors and match stats.json counts."""
    root = repo_root()
    stats_path = root / "data" / "graph" / "out" / "case_demo_v2_r2" / "stats.json"
    cdr_path = root / "data" / "synthetic" / "out" / "case_demo_v2" / "cdr.csv"
    bank_path = root / "data" / "synthetic" / "out" / "case_demo_v2" / "bank.csv"

    with stats_path.open("r", encoding="utf-8") as f:
        stats = json.load(f)

    expected_cdr_rows = stats["cdr_rows_read"]
    expected_bank_rows = stats["bank_rows_read"]

    # Validate real demo CDR
    cdr_bytes = cdr_path.read_bytes()
    cdr_report = validate_cdr(cdr_bytes, test_settings)
    assert cdr_report.ok is True
    assert cdr_report.error_count == 0
    assert cdr_report.errors == []
    assert cdr_report.rows == expected_cdr_rows

    # Validate real demo Bank
    bank_bytes = bank_path.read_bytes()
    bank_report = validate_bank(bank_bytes, test_settings)
    assert bank_report.ok is True
    assert bank_report.error_count == 0
    assert bank_report.errors == []
    assert bank_report.rows == expected_bank_rows


def test_large_10mb_file_performance(test_settings: Settings) -> None:
    """Generated 10 MB CSV passes quickly in under 5 seconds."""
    header = ",".join(REQUIRED_CDR_COLUMNS) + "\n"
    row = "9876543210,9123456789,123456789012345,404123456789012,2026-01-01T12:00:00,60,VOICE,TWR_01,28.6,77.2\n"
    target_bytes = 10 * 1024 * 1024
    repeat = int(target_bytes / len(row)) + 1
    large_csv_bytes = (header + (row * repeat)).encode("utf-8")
    assert len(large_csv_bytes) >= target_bytes

    start_time = time.time()
    report = validate_cdr(large_csv_bytes, test_settings)
    duration = time.time() - start_time

    assert report.ok is True
    assert report.error_count == 0
    assert report.rows == repeat
    assert duration < 5.0
