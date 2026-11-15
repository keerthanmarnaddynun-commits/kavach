"""Burner phone detection from Call Detail Records (cdr.csv).

Features computed per phone:
  - lifespan_days: last_seen_day - first_seen_day
  - short_lifespan: 1 - min(1, lifespan_days / observation_days)
  - late_activation: first_seen_day / observation_days
  - distinct_contacts: count of distinct contact numbers
  - low_contacts: 1 - distinct_contacts / max(distinct_contacts)
  - top2_share: fraction of total calls conducted with top 2 contacts
  - imei_hop: 1 if phone's imei_a is shared across multiple a_party numbers (reason only)
"""

from __future__ import annotations

from collections import Counter, defaultdict
import csv
from datetime import datetime
import json
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "detector_defaults.json"


def _load_config(config_path: str | Path | None = None) -> dict[str, Any]:
    p = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    if p.exists():
        with p.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    return {
        "burner_weights": {
            "late_activation": 0.25,
            "low_contacts": 0.20,
            "short_lifespan": 0.30,
            "top2_share": 0.25,
        }
    }


def detect_burners(
    cdr_csv_path: str | Path,
    config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Score and rank all phones in cdr.csv for burner phone characteristics.

    Args:
        cdr_csv_path: Path to cdr.csv file.
        config: Optional configuration dictionary.

    Returns:
        List of dicts representing ranked leads (highest score first).
    """
    if config is None:
        config = _load_config()

    weights = config.get(
        "burner_weights",
        {
            "late_activation": 0.25,
            "low_contacts": 0.20,
            "short_lifespan": 0.30,
            "top2_share": 0.25,
        },
    )

    cdr_file = Path(cdr_csv_path)

    all_phones: set[str] = set()
    timestamps: list[datetime] = []
    phone_timestamps: dict[str, list[datetime]] = defaultdict(list)
    phone_contacts: dict[str, Counter[str]] = defaultdict(Counter)
    phone_imeis: dict[str, set[str]] = defaultdict(set)
    imei_a_phones: dict[str, set[str]] = defaultdict(set)
    evidence_rows_map: dict[str, list[int]] = defaultdict(list)

    with cdr_file.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row_idx, row in enumerate(reader, start=2):
            a_party = str(row["a_party"]).strip()
            b_party = str(row["b_party"]).strip()
            dt_str = str(row.get("start_time", "")).strip()
            dt = datetime.fromisoformat(dt_str)
            timestamps.append(dt)

            all_phones.add(a_party)
            all_phones.add(b_party)

            phone_timestamps[a_party].append(dt)
            phone_timestamps[b_party].append(dt)

            phone_contacts[a_party][b_party] += 1
            phone_contacts[b_party][a_party] += 1

            imei_a = str(row.get("imei_a", "")).strip()
            if imei_a:
                phone_imeis[a_party].add(imei_a)
                imei_a_phones[imei_a].add(a_party)

            if len(evidence_rows_map[a_party]) < 10:
                evidence_rows_map[a_party].append(row_idx)
            if len(evidence_rows_map[b_party]) < 10 and row_idx not in evidence_rows_map[b_party]:
                evidence_rows_map[b_party].append(row_idx)

    if not all_phones or not timestamps:
        return []

    min_file_dt = min(timestamps)
    max_file_dt = max(timestamps)
    observation_days = (max_file_dt - min_file_dt).total_seconds() / 86400.0
    if observation_days <= 0.0:
        observation_days = 1.0

    distinct_contacts_map = {
        ph: len(phone_contacts[ph]) for ph in all_phones
    }
    max_distinct_contacts = max(distinct_contacts_map.values()) if distinct_contacts_map else 0

    results: list[dict[str, Any]] = []

    for ph in sorted(all_phones):
        ts_list = phone_timestamps[ph]
        first_dt = min(ts_list)
        last_dt = max(ts_list)

        first_seen_day = (first_dt - min_file_dt).total_seconds() / 86400.0
        last_seen_day = (last_dt - min_file_dt).total_seconds() / 86400.0
        lifespan_days = last_seen_day - first_seen_day

        short_lifespan = 1.0 - min(1.0, lifespan_days / observation_days)
        late_activation = first_seen_day / observation_days

        distinct_contacts = distinct_contacts_map[ph]
        low_contacts = (
            1.0 - (distinct_contacts / max_distinct_contacts)
            if max_distinct_contacts > 0
            else 0.0
        )

        contacts_counter = phone_contacts[ph]
        total_calls = sum(contacts_counter.values())
        if total_calls > 0:
            top2_calls = sum(cnt for _, cnt in contacts_counter.most_common(2))
            top2_share = top2_calls / total_calls
        else:
            top2_share = 0.0

        # IMEI hop: 1 if phone's imei_a is associated with > 1 distinct a_party numbers
        imei_hop = 1 if any(len(imei_a_phones[im]) > 1 for im in phone_imeis[ph]) else 0

        w_short = float(weights.get("short_lifespan", 0.30))
        w_late = float(weights.get("late_activation", 0.25))
        w_top2 = float(weights.get("top2_share", 0.25))
        w_low = float(weights.get("low_contacts", 0.20))

        score = (
            w_short * short_lifespan
            + w_late * late_activation
            + w_top2 * top2_share
            + w_low * low_contacts
        )

        reasons: list[str] = []
        if lifespan_days <= 10.0:
            reasons.append(f"Short active lifespan: {lifespan_days:.1f} days")
        if late_activation >= 0.40:
            reasons.append(f"Late network activation: Day {first_seen_day:.1f}")
        if top2_share >= 0.80:
            reasons.append(f"High contact concentration: {top2_share * 100:.1f}% with top 2 contacts")
        if distinct_contacts <= 3:
            reasons.append(f"Limited distinct contacts: {distinct_contacts} peers")
        if imei_hop == 1:
            reasons.append("Device hopping observed across multiple numbers on IMEI")
        if not reasons:
            reasons.append(f"Regular subscriber pattern ({total_calls} calls, {distinct_contacts} contacts)")

        features = {
            "distinct_contacts": distinct_contacts,
            "first_seen_day": round(first_seen_day, 4),
            "imei_hop": imei_hop,
            "last_seen_day": round(last_seen_day, 4),
            "late_activation": round(late_activation, 6),
            "lifespan_days": round(lifespan_days, 4),
            "low_contacts": round(low_contacts, 6),
            "observation_days": round(observation_days, 4),
            "short_lifespan": round(short_lifespan, 6),
            "top2_share": round(top2_share, 6),
            "total_calls": total_calls,
        }

        results.append(
            {
                "evidence_rows": sorted(evidence_rows_map[ph])[:10],
                "features": features,
                "id": ph,
                "reasons": reasons,
                "score": round(score, 6),
            }
        )

    results.sort(key=lambda x: (-x["score"], x["id"]))
    return results
