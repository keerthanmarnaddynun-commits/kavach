"""Mule account detection from banking transaction logs (bank.csv).

Cycle detection is NOT implemented in this module.

Features computed per account:
  - fan_in: count of distinct sender accounts
  - fan_out: count of distinct recipient accounts
  - passthrough: min(total_in, total_out) / max(total_in, total_out) in paise
  - dwell: median hours until earliest subsequent debit after credit
  - structuring_share: share of incoming deposits in [threshold * (1 - band), threshold)
  - fan_in_norm: fan_in / max(fan_in) over all accounts
"""

from __future__ import annotations

from collections import defaultdict
import csv
from datetime import datetime
import json
from pathlib import Path
import statistics
from typing import Any

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "detector_defaults.json"


def _load_config(config_path: str | Path | None = None) -> dict[str, Any]:
    p = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    if p.exists():
        with p.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    return {
        "mule_weights": {
            "dwell_score": 0.25,
            "fan_in_norm": 0.30,
            "passthrough": 0.25,
            "structuring_share": 0.20,
        },
        "mule_weights_no_threshold": {
            "dwell_score": 0.3125,
            "fan_in_norm": 0.375,
            "passthrough": 0.3125,
        },
        "structuring_band": 0.10,
        "structuring_threshold": 50000,
    }


def detect_mules(
    bank_csv_path: str | Path,
    config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Score and rank all accounts in bank.csv for mule account characteristics.

    Args:
        bank_csv_path: Path to bank.csv file.
        config: Optional configuration dictionary.

    Returns:
        List of dicts representing ranked leads (highest score first).
    """
    if config is None:
        config = _load_config()

    threshold = float(config.get("structuring_threshold", 50000))
    band = float(config.get("structuring_band", 0.10))
    thresh_paise = int(round(threshold * 100))
    lower_paise = int(round(threshold * (1.0 - band) * 100))

    weights = config.get(
        "mule_weights",
        {
            "dwell_score": 0.25,
            "fan_in_norm": 0.30,
            "passthrough": 0.25,
            "structuring_share": 0.20,
        },
    )

    bank_file = Path(bank_csv_path)

    # Per account storage:
    # senders, receivers, credits: list of (dt, paise, row_num), debits: list of (dt, paise, row_num)
    senders: dict[str, set[str]] = defaultdict(set)
    receivers: dict[str, set[str]] = defaultdict(set)
    credits: dict[str, list[tuple[datetime, int, int]]] = defaultdict(list)
    debits: dict[str, list[tuple[datetime, int, int]]] = defaultdict(list)
    evidence_rows_map: dict[str, list[int]] = defaultdict(list)

    all_accounts: set[str] = set()

    with bank_file.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row_idx, row in enumerate(reader, start=2):
            s_acc = str(row["from_acct"]).strip()
            r_acc = str(row["to_acct"]).strip()
            all_accounts.add(s_acc)
            all_accounts.add(r_acc)

            dt_str = str(row.get("datetime", "")).strip()
            dt = datetime.fromisoformat(dt_str)
            amt_float = float(row.get("amount", 0.0))
            amt_paise = int(round(amt_float * 100))

            senders[r_acc].add(s_acc)
            receivers[s_acc].add(r_acc)

            credits[r_acc].append((dt, amt_paise, row_idx))
            debits[s_acc].append((dt, amt_paise, row_idx))

            if len(evidence_rows_map[s_acc]) < 10:
                evidence_rows_map[s_acc].append(row_idx)
            if len(evidence_rows_map[r_acc]) < 10 and row_idx not in evidence_rows_map[r_acc]:
                evidence_rows_map[r_acc].append(row_idx)

    if not all_accounts:
        return []

    # Calculate fan_in to determine max_fan_in
    fan_in_map: dict[str, int] = {acc: len(senders[acc]) for acc in all_accounts}
    max_fan_in = max(fan_in_map.values()) if fan_in_map else 0

    results: list[dict[str, Any]] = []

    for acc in sorted(all_accounts):
        acc_credits = sorted(credits[acc], key=lambda x: x[0])
        acc_debits = sorted(debits[acc], key=lambda x: x[0])

        total_in_paise = sum(c[1] for c in acc_credits)
        total_out_paise = sum(d[1] for d in acc_debits)

        # Passthrough
        if total_in_paise == 0 or total_out_paise == 0:
            passthrough = 0.0
        else:
            passthrough = min(total_in_paise, total_out_paise) / max(total_in_paise, total_out_paise)

        # Dwell hours: for each credit, find earliest debit at or after credit time
        dwell_hours_list: list[float] = []
        d_idx = 0
        n_debits = len(acc_debits)

        for c_dt, _, _ in acc_credits:
            # Advance d_idx to first debit >= c_dt
            while d_idx < n_debits and acc_debits[d_idx][0] < c_dt:
                d_idx += 1
            if d_idx < n_debits:
                diff_hours = (acc_debits[d_idx][0] - c_dt).total_seconds() / 3600.0
                dwell_hours_list.append(diff_hours)

        if dwell_hours_list:
            median_dwell_hours: float | None = float(statistics.median(dwell_hours_list))
            dwell_score = 1.0 / (1.0 + median_dwell_hours / 24.0)
        else:
            median_dwell_hours = None
            dwell_score = 0.0

        # Structuring share
        total_credits_count = len(acc_credits)
        if total_credits_count > 0:
            structured_count = sum(
                1 for _, amt_p, _ in acc_credits if lower_paise <= amt_p < thresh_paise
            )
            structuring_share = structured_count / total_credits_count
        else:
            structuring_share = 0.0

        fan_in = fan_in_map[acc]
        fan_out = len(receivers[acc])
        fan_in_norm = (fan_in / max_fan_in) if max_fan_in > 0 else 0.0

        w_fan = float(weights.get("fan_in_norm", 0.30))
        w_pass = float(weights.get("passthrough", 0.25))
        w_dwell = float(weights.get("dwell_score", 0.25))
        w_struct = float(weights.get("structuring_share", 0.20))

        score = (
            w_fan * fan_in_norm
            + w_pass * passthrough
            + w_dwell * dwell_score
            + w_struct * structuring_share
        )

        # No-threshold variant score
        denom_no_thresh = w_fan + w_pass + w_dwell
        if denom_no_thresh > 0:
            score_no_threshold = (
                w_fan * fan_in_norm + w_pass * passthrough + w_dwell * dwell_score
            ) / denom_no_thresh
        else:
            score_no_threshold = 0.0

        # Formulate human-readable reasons
        reasons: list[str] = []
        if fan_in >= 3:
            reasons.append(f"High fan-in: {fan_in} distinct senders")
        if passthrough >= 0.70:
            reasons.append(f"High pass-through ratio: {passthrough * 100:.1f}% turnover")
        if median_dwell_hours is not None and median_dwell_hours <= 12.0:
            reasons.append(f"Rapid onward movement: median dwell {median_dwell_hours:.1f} hours")
        if structuring_share >= 0.25:
            reasons.append(
                f"Structuring pattern: {structuring_share * 100:.1f}% deposits just below reporting threshold"
            )
        if not reasons:
            reasons.append("Standard transaction activity")

        features = {
            "dwell_score": round(dwell_score, 6),
            "fan_in": fan_in,
            "fan_in_norm": round(fan_in_norm, 6),
            "fan_out": fan_out,
            "median_dwell_hours": round(median_dwell_hours, 4) if median_dwell_hours is not None else None,
            "passthrough": round(passthrough, 6),
            "score_no_threshold": round(score_no_threshold, 6),
            "structuring_share": round(structuring_share, 6),
            "total_in_paise": total_in_paise,
            "total_out_paise": total_out_paise,
            "volume_paise": total_in_paise + total_out_paise,
        }

        results.append(
            {
                "evidence_rows": sorted(evidence_rows_map[acc])[:10],
                "features": features,
                "id": acc,
                "reasons": reasons,
                "score": round(score, 6),
            }
        )

    # Sort descending by score, tie-break by ascending account id
    results.sort(key=lambda x: (-x["score"], x["id"]))
    return results
