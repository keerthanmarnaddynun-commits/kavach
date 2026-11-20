"""Ingestion validation for FIR text, CDR CSV and Bank CSV files."""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
import io
import re
from typing import Any, Sequence

from kavach_api.settings import Settings

REQUIRED_CDR_COLUMNS: tuple[str, ...] = (
    "a_party",
    "b_party",
    "imei_a",
    "imsi_a",
    "start_time",
    "duration_sec",
    "call_type",
    "tower_id",
    "lat",
    "lon",
)

REQUIRED_BANK_COLUMNS: tuple[str, ...] = (
    "txn_id",
    "datetime",
    "from_acct",
    "to_acct",
    "amount",
    "mode",
    "ifsc",
    "narration",
)

_PHONE_RE = re.compile(r"^[6-9]\d{9}$")
_IMEI_RE = re.compile(r"^\d{15}$")
_DURATION_RE = re.compile(r"^\d+$")
_ACCT_RE = re.compile(r"^\d{5,20}$")
_AMOUNT_RE = re.compile(r"^\d+(\.\d{1,2})?$")
_ISO_DT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}")


class IngestError(Exception):
    """Raised when ingestion validation fails for a single document."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class CsvReport:
    """Report detailing CSV validation outcome and row errors."""

    ok: bool
    rows: int
    columns: list[str]
    errors: list[dict[str, Any]]
    error_count: int = 0

    def __post_init__(self) -> None:
        if self.error_count == 0 and self.errors:
            self.error_count = len(self.errors)

    def __iter__(self):
        return iter((self.ok, self.rows, self.columns, self.errors))


def decode_fir(raw_bytes: bytes, max_chars: int) -> str:
    """
    Decode FIR raw bytes as UTF-8 without newline translation or stripping.

    Raises IngestError with codes:
      - 'invalid_encoding': non-UTF-8 bytes
      - 'empty_text': empty or whitespace-only text
      - 'text_too_long': character count exceeds max_chars
    A UTF-8 BOM (byte-order mark) is removed if present.
    """
    if raw_bytes.startswith(b"\xef\xbb\xbf"):
        raw_bytes = raw_bytes[3:]
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise IngestError("invalid_encoding", f"Text is not valid UTF-8: {exc}") from exc

    if not text.strip():
        raise IngestError("empty_text", "FIR text is empty or whitespace only")
    if len(text) > max_chars:
        raise IngestError(
            "text_too_long",
            f"FIR text length {len(text)} exceeds limit of {max_chars} characters",
        )
    return text


def _is_iso_datetime(val: str) -> bool:
    """Check if string is a valid ISO date-time."""
    if not val or not _ISO_DT_RE.match(val):
        return False
    try:
        datetime.fromisoformat(val.replace("Z", "+00:00"))
        return True
    except Exception:
        return False


def _is_positive_decimal_2places(val: str) -> bool:
    """Check if string is a positive decimal with at most 2 decimal places."""
    if not val or not _AMOUNT_RE.match(val):
        return False
    try:
        d = Decimal(val)
        return d > Decimal(0)
    except Exception:
        return False


def validate_cdr(raw_bytes: bytes, settings: Settings) -> CsvReport:
    """
    Validate Call Detail Record (CDR) CSV upload.

    Checks size limits, UTF-8 encoding, presence of required columns,
    and row-level rules for phone numbers, IMEI, date-time, duration, and call type.
    """
    if len(raw_bytes) > settings.max_upload_bytes:
        return CsvReport(
            ok=False,
            rows=0,
            columns=[],
            errors=[
                {
                    "row": 0,
                    "column": "",
                    "code": "size_over_limit",
                    "message": (
                        f"File size {len(raw_bytes)} bytes exceeds limit of "
                        f"{settings.max_upload_bytes} bytes"
                    ),
                }
            ],
            error_count=1,
        )

    if raw_bytes.startswith(b"\xef\xbb\xbf"):
        raw_bytes = raw_bytes[3:]
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        return CsvReport(
            ok=False,
            rows=0,
            columns=[],
            errors=[
                {
                    "row": 0,
                    "column": "",
                    "code": "invalid_encoding",
                    "message": f"File is not valid UTF-8: {exc}",
                }
            ],
            error_count=1,
        )

    if not text.strip():
        return CsvReport(
            ok=False,
            rows=0,
            columns=[],
            errors=[
                {
                    "row": 0,
                    "column": "",
                    "code": "empty_file",
                    "message": "File is empty",
                }
            ],
            error_count=1,
        )

    reader = csv.reader(io.StringIO(text))
    try:
        raw_header = next(reader)
    except StopIteration:
        return CsvReport(
            ok=False,
            rows=0,
            columns=[],
            errors=[
                {
                    "row": 0,
                    "column": "",
                    "code": "empty_file",
                    "message": "File is empty",
                }
            ],
            error_count=1,
        )

    columns = [col.strip() for col in raw_header]
    col_idx: dict[str, int] = {name: i for i, name in enumerate(columns)}

    missing_cols = [c for c in REQUIRED_CDR_COLUMNS if c not in col_idx]
    if missing_cols:
        errs = [
            {
                "row": 0,
                "column": c,
                "code": "missing_column",
                "message": f"Required column '{c}' is missing",
            }
            for c in missing_cols
        ]
        return CsvReport(
            ok=False,
            rows=0,
            columns=columns,
            errors=errs,
            error_count=len(errs),
        )

    idx_a = col_idx["a_party"]
    idx_b = col_idx["b_party"]
    idx_imei = col_idx["imei_a"]
    idx_start = col_idx["start_time"]
    idx_dur = col_idx["duration_sec"]
    idx_call = col_idx["call_type"]

    total_errors = 0
    errors: list[dict[str, Any]] = []

    def _record_error(r_num: int, col: str, code: str, msg: str) -> None:
        nonlocal total_errors
        total_errors += 1
        if len(errors) < 50:
            errors.append(
                {
                    "row": r_num,
                    "column": col,
                    "code": code,
                    "message": msg,
                }
            )

    row_count = 0
    for row_num, row in enumerate(reader, start=1):
        row_count += 1
        if row_count > settings.max_csv_rows:
            _record_error(
                row_num,
                "",
                "rows_over_limit",
                f"Row count exceeds maximum limit of {settings.max_csv_rows} rows",
            )
            break

        val_a = row[idx_a].strip() if idx_a < len(row) else ""
        if not _PHONE_RE.match(val_a):
            _record_error(
                row_num,
                "a_party",
                "invalid_phone",
                f"Invalid a_party '{val_a}': must match 10-digit Indian phone format",
            )

        val_b = row[idx_b].strip() if idx_b < len(row) else ""
        if not _PHONE_RE.match(val_b):
            _record_error(
                row_num,
                "b_party",
                "invalid_phone",
                f"Invalid b_party '{val_b}': must match 10-digit Indian phone format",
            )

        val_imei = row[idx_imei].strip() if idx_imei < len(row) else ""
        if val_imei and not _IMEI_RE.match(val_imei):
            _record_error(
                row_num,
                "imei_a",
                "invalid_imei",
                f"Invalid imei_a '{val_imei}': must be empty or 15 digits",
            )

        val_start = row[idx_start].strip() if idx_start < len(row) else ""
        if not _is_iso_datetime(val_start):
            _record_error(
                row_num,
                "start_time",
                "invalid_datetime",
                f"Invalid start_time '{val_start}': must be an ISO date-time",
            )

        val_dur = row[idx_dur].strip() if idx_dur < len(row) else ""
        if not _DURATION_RE.match(val_dur):
            _record_error(
                row_num,
                "duration_sec",
                "invalid_duration",
                f"Invalid duration_sec '{val_dur}': must be an integer >= 0",
            )

        val_call = row[idx_call].strip() if idx_call < len(row) else ""
        if val_call not in ("VOICE", "SMS"):
            _record_error(
                row_num,
                "call_type",
                "invalid_call_type",
                f"Invalid call_type '{val_call}': must be VOICE or SMS",
            )

    if row_count == 0:
        return CsvReport(
            ok=False,
            rows=0,
            columns=columns,
            errors=[
                {
                    "row": 0,
                    "column": "",
                    "code": "header_only",
                    "message": "File contains header only, no data rows",
                }
            ],
            error_count=1,
        )

    return CsvReport(
        ok=(total_errors == 0),
        rows=row_count,
        columns=columns,
        errors=errors,
        error_count=total_errors,
    )


def validate_bank(raw_bytes: bytes, settings: Settings) -> CsvReport:
    """
    Validate Bank Transaction CSV upload.

    Checks size limits, UTF-8 encoding, presence of required columns,
    and row-level rules for account numbers, amount, date-time, and mode.
    """
    if len(raw_bytes) > settings.max_upload_bytes:
        return CsvReport(
            ok=False,
            rows=0,
            columns=[],
            errors=[
                {
                    "row": 0,
                    "column": "",
                    "code": "size_over_limit",
                    "message": (
                        f"File size {len(raw_bytes)} bytes exceeds limit of "
                        f"{settings.max_upload_bytes} bytes"
                    ),
                }
            ],
            error_count=1,
        )

    if raw_bytes.startswith(b"\xef\xbb\xbf"):
        raw_bytes = raw_bytes[3:]
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        return CsvReport(
            ok=False,
            rows=0,
            columns=[],
            errors=[
                {
                    "row": 0,
                    "column": "",
                    "code": "invalid_encoding",
                    "message": f"File is not valid UTF-8: {exc}",
                }
            ],
            error_count=1,
        )

    if not text.strip():
        return CsvReport(
            ok=False,
            rows=0,
            columns=[],
            errors=[
                {
                    "row": 0,
                    "column": "",
                    "code": "empty_file",
                    "message": "File is empty",
                }
            ],
            error_count=1,
        )

    reader = csv.reader(io.StringIO(text))
    try:
        raw_header = next(reader)
    except StopIteration:
        return CsvReport(
            ok=False,
            rows=0,
            columns=[],
            errors=[
                {
                    "row": 0,
                    "column": "",
                    "code": "empty_file",
                    "message": "File is empty",
                }
            ],
            error_count=1,
        )

    columns = [col.strip() for col in raw_header]
    col_idx: dict[str, int] = {name: i for i, name in enumerate(columns)}

    missing_cols = [c for c in REQUIRED_BANK_COLUMNS if c not in col_idx]
    if missing_cols:
        errs = [
            {
                "row": 0,
                "column": c,
                "code": "missing_column",
                "message": f"Required column '{c}' is missing",
            }
            for c in missing_cols
        ]
        return CsvReport(
            ok=False,
            rows=0,
            columns=columns,
            errors=errs,
            error_count=len(errs),
        )

    idx_from = col_idx["from_acct"]
    idx_to = col_idx["to_acct"]
    idx_amt = col_idx["amount"]
    idx_dt = col_idx["datetime"]
    idx_mode = col_idx["mode"]

    total_errors = 0
    errors: list[dict[str, Any]] = []

    def _record_error(r_num: int, col: str, code: str, msg: str) -> None:
        nonlocal total_errors
        total_errors += 1
        if len(errors) < 50:
            errors.append(
                {
                    "row": r_num,
                    "column": col,
                    "code": code,
                    "message": msg,
                }
            )

    row_count = 0
    for row_num, row in enumerate(reader, start=1):
        row_count += 1
        if row_count > settings.max_csv_rows:
            _record_error(
                row_num,
                "",
                "rows_over_limit",
                f"Row count exceeds maximum limit of {settings.max_csv_rows} rows",
            )
            break

        val_from = row[idx_from].strip() if idx_from < len(row) else ""
        if not _ACCT_RE.match(val_from):
            _record_error(
                row_num,
                "from_acct",
                "invalid_account",
                f"Invalid from_acct '{val_from}': must be 5 to 20 digits",
            )

        val_to = row[idx_to].strip() if idx_to < len(row) else ""
        if not _ACCT_RE.match(val_to):
            _record_error(
                row_num,
                "to_acct",
                "invalid_account",
                f"Invalid to_acct '{val_to}': must be 5 to 20 digits",
            )

        val_amt = row[idx_amt].strip() if idx_amt < len(row) else ""
        if not _is_positive_decimal_2places(val_amt):
            _record_error(
                row_num,
                "amount",
                "invalid_amount",
                f"Invalid amount '{val_amt}': must be a positive decimal with <= 2 decimal places",
            )

        val_dt = row[idx_dt].strip() if idx_dt < len(row) else ""
        if not _is_iso_datetime(val_dt):
            _record_error(
                row_num,
                "datetime",
                "invalid_datetime",
                f"Invalid datetime '{val_dt}': must be an ISO date-time",
            )

        val_mode = row[idx_mode].strip() if idx_mode < len(row) else ""
        if not val_mode:
            _record_error(
                row_num,
                "mode",
                "invalid_mode",
                "Mode must not be empty",
            )

    if row_count == 0:
        return CsvReport(
            ok=False,
            rows=0,
            columns=columns,
            errors=[
                {
                    "row": 0,
                    "column": "",
                    "code": "header_only",
                    "message": "File contains header only, no data rows",
                }
            ],
            error_count=1,
        )

    return CsvReport(
        ok=(total_errors == 0),
        rows=row_count,
        columns=columns,
        errors=errors,
        error_count=total_errors,
    )
