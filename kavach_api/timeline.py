"""Timeline aggregation service for calls and financial transfers."""
from __future__ import annotations

import csv
from decimal import Decimal
import io
from pathlib import Path
from typing import Any

from kavach_api.storage import Storage


def build_timeline(
    store: Storage,
    case_id: str,
    bucket: str = "day",
) -> dict[str, Any]:
    """
    Build timeline aggregating calls, transfers, and first-seen phone timestamps.
    Bucket must be 'day' or 'hour'. Times are used as written without timezone conversion.
    """
    if bucket not in ("day", "hour"):
        raise ValueError(f"Invalid timeline bucket '{bucket}', must be 'day' or 'hour'")

    cdr_path = store.csv_path(case_id, "cdr")
    bank_path = store.csv_path(case_id, "bank")

    call_buckets: dict[str, dict[str, Any]] = {}
    first_seen_map: dict[str, str] = {}

    if cdr_path.is_file():
        with open(cdr_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                st = row.get("start_time", "").strip()
                if not st:
                    continue
                t_key = st[:10] if bucket == "day" else st[:13] + ":00:00"

                b = call_buckets.setdefault(t_key, {"t": t_key, "count": 0, "voice": 0, "sms": 0})
                b["count"] += 1
                ctype = row.get("call_type", "").strip().upper()
                if ctype == "VOICE":
                    b["voice"] += 1
                elif ctype == "SMS":
                    b["sms"] += 1

                for phone_col in ("a_party", "b_party"):
                    p = row.get(phone_col, "").strip()
                    if p:
                        if p not in first_seen_map or st < first_seen_map[p]:
                            first_seen_map[p] = st

    transfer_buckets: dict[str, dict[str, Any]] = {}

    if bank_path.is_file():
        with open(bank_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                dt = row.get("datetime", "").strip()
                if not dt:
                    continue
                t_key = dt[:10] if bucket == "day" else dt[:13] + ":00:00"

                b = transfer_buckets.setdefault(t_key, {"t": t_key, "count": 0, "paise": 0})
                b["count"] += 1

                amt_str = row.get("amount", "0").strip()
                try:
                    paise = int(round(float(Decimal(amt_str) * 100)))
                except Exception:
                    paise = 0
                b["paise"] += paise

    calls_list = sorted(call_buckets.values(), key=lambda x: x["t"])
    transfers_list = sorted(transfer_buckets.values(), key=lambda x: x["t"])
    first_seen_list = sorted(
        [{"phone": p, "t": t} for p, t in first_seen_map.items()],
        key=lambda x: (x["t"], x["phone"]),
    )

    return {
        "bucket": bucket,
        "calls": calls_list,
        "transfers": transfers_list,
        "first_seen": first_seen_list,
    }
