"""Timeline insights module for detecting patterns in call and transfer records."""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import statistics
from typing import Any

from kavach_api.storage import Storage
from kavach_api.timeline import build_timeline

# Named constants for rules and thresholds
MIN_ACTIVE_DAYS = 7

# Call spike thresholds
CALL_SPIKE_MULTIPLIER = 3.0
CALL_SPIKE_MAD_MULTIPLIER = 3.0
MIN_CALL_EVENTS = 10

# Transfer spike thresholds
TRANSFER_SPIKE_MULTIPLIER = 3.0
TRANSFER_SPIKE_MAD_MULTIPLIER = 3.0
MIN_TRANSFER_EVENTS = 10
TRANSFER_AMOUNT_MULTIPLIER = 3.0
MIN_TRANSFER_AMOUNT_PAISE = 5_000_000  # 50,000 INR = 5,000,000 paise

# Correlation window
CALL_THEN_TRANSFER_WINDOW_DAYS = 2  # D to D+2

# New and busy thresholds
NEW_BUSY_DAY_WINDOW = 3  # first seen within 3 days before or on spike day
NEW_BUSY_VOLUME_SHARE = 0.20  # >= 20%
NEW_BUSY_MIN_EVENTS = 5  # >= 5 events

RULES: dict[str, Any] = {
    "min_active_days": MIN_ACTIVE_DAYS,
    "call_spike_multiplier": CALL_SPIKE_MULTIPLIER,
    "call_spike_mad_multiplier": CALL_SPIKE_MAD_MULTIPLIER,
    "min_call_events": MIN_CALL_EVENTS,
    "transfer_spike_multiplier": TRANSFER_SPIKE_MULTIPLIER,
    "transfer_spike_mad_multiplier": TRANSFER_SPIKE_MAD_MULTIPLIER,
    "min_transfer_events": MIN_TRANSFER_EVENTS,
    "transfer_amount_multiplier": TRANSFER_AMOUNT_MULTIPLIER,
    "min_transfer_amount_paise": MIN_TRANSFER_AMOUNT_PAISE,
    "call_then_transfer_window_days": CALL_THEN_TRANSFER_WINDOW_DAYS,
    "new_busy_day_window": NEW_BUSY_DAY_WINDOW,
    "new_busy_volume_share": NEW_BUSY_VOLUME_SHARE,
    "new_busy_min_events": NEW_BUSY_MIN_EVENTS,
}


def _calc_median_and_mad(values: list[float | int]) -> tuple[float, float]:
    """Calculate median and Median Absolute Deviation (MAD)."""
    if not values:
        return 0.0, 0.0
    med = float(statistics.median(values))
    devs = [abs(float(x) - med) for x in values]
    mad = float(statistics.median(devs)) if devs else 0.0
    return med, mad


def _parse_date(d_str: str) -> datetime.date | None:
    try:
        return datetime.strptime(d_str[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def _load_daily_identifier_counts(
    store: Storage, case_id: str
) -> tuple[
    dict[str, dict[str, int]],  # day -> phone -> call count
    dict[str, dict[str, int]],  # day -> imei -> call count
    dict[str, dict[str, int]],  # day -> account -> transfer count
]:
    cdr_path = store.csv_path(case_id, "cdr")
    bank_path = store.csv_path(case_id, "bank")

    daily_phone_calls: dict[str, dict[str, int]] = {}
    daily_imei_calls: dict[str, dict[str, int]] = {}
    daily_acct_transfers: dict[str, dict[str, int]] = {}

    if cdr_path.is_file():
        with open(cdr_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                st = row.get("start_time", "").strip()
                if not st:
                    continue
                d = st[:10]
                dp = daily_phone_calls.setdefault(d, {})
                di = daily_imei_calls.setdefault(d, {})

                parties = {
                    row.get("a_party", "").strip(),
                    row.get("b_party", "").strip(),
                }
                for p in parties:
                    if p:
                        dp[p] = dp.get(p, 0) + 1

                imeis = {
                    row.get("imei_a", "").strip(),
                    row.get("imei", "").strip(),
                }
                for im in imeis:
                    if im:
                        di[im] = di.get(im, 0) + 1

    if bank_path.is_file():
        with open(bank_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                dt = row.get("datetime", "").strip()
                if not dt:
                    continue
                d = dt[:10]
                da = daily_acct_transfers.setdefault(d, {})

                accts = {
                    row.get("from_acct", "").strip(),
                    row.get("to_acct", "").strip(),
                }
                for a in accts:
                    if a:
                        da[a] = da.get(a, 0) + 1

    return daily_phone_calls, daily_imei_calls, daily_acct_transfers


def compute_timeline_insights(
    store: Storage,
    case_id: str,
    timeline_data: dict[str, Any] | None = None,
    daily_counts: tuple[
        dict[str, dict[str, int]],
        dict[str, dict[str, int]],
        dict[str, dict[str, int]],
    ] | None = None,
) -> dict[str, Any]:
    """
    Compute pattern insights on timeline data using deterministic rules.
    Returns dictionary with rules, count, insights, and optional reason.
    """
    tl = timeline_data if timeline_data is not None else build_timeline(store, case_id, bucket="day")
    calls = tl.get("calls", [])
    transfers = tl.get("transfers", [])
    first_seen_phones = tl.get("first_seen", [])
    first_seen_accounts = tl.get("first_seen_accounts", [])
    first_seen_imeis = tl.get("first_seen_imeis", [])

    # Active days check
    active_days_set = set(c["t"][:10] for c in calls if c.get("t")) | set(
        tr["t"][:10] for tr in transfers if tr.get("t")
    )

    call_counts = [c.get("count", 0) for c in calls]
    call_med, call_mad = _calc_median_and_mad(call_counts)
    call_thresh = max(CALL_SPIKE_MULTIPLIER * call_med, call_med + CALL_SPIKE_MAD_MULTIPLIER * call_mad)

    transfer_counts = [tr.get("count", 0) for tr in transfers]
    tr_count_med, tr_count_mad = _calc_median_and_mad(transfer_counts)
    tr_count_thresh = max(
        TRANSFER_SPIKE_MULTIPLIER * tr_count_med,
        tr_count_med + TRANSFER_SPIKE_MAD_MULTIPLIER * tr_count_mad,
    )

    transfer_paise = [tr.get("paise", 0) for tr in transfers]
    tr_amt_med, tr_amt_mad = _calc_median_and_mad(transfer_paise)
    tr_amt_thresh = max(
        TRANSFER_AMOUNT_MULTIPLIER * tr_amt_med,
        tr_amt_med + TRANSFER_SPIKE_MAD_MULTIPLIER * tr_amt_mad,
    )

    # Compute busiest days summary
    top_call = max(calls, key=lambda c: c.get("count", 0)) if calls else None
    top_call_cnt = top_call.get("count", 0) if top_call else 0
    c_ratio = round(top_call_cnt / call_med, 2) if (top_call and call_med > 0) else (1.0 if top_call else 0.0)

    top_tr = max(transfers, key=lambda tr: tr.get("count", 0)) if transfers else None
    top_tr_cnt = top_tr.get("count", 0) if top_tr else 0
    t_ratio = round(top_tr_cnt / tr_count_med, 2) if (top_tr and tr_count_med > 0) else (1.0 if top_tr else 0.0)

    summary = {
        "busiest_call_day": {
            "date": top_call.get("t", "")[:10],
            "count": top_call_cnt,
            "ratio": c_ratio,
        } if top_call else None,
        "busiest_transfer_day": {
            "date": top_tr.get("t", "")[:10],
            "count": top_tr_cnt,
            "ratio": t_ratio,
        } if top_tr else None,
    }

    if len(active_days_set) < MIN_ACTIVE_DAYS:
        return {
            "case_id": case_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "count": 0,
            "reason": "not enough days to judge",
            "rules": RULES,
            "insights": [],
            "summary": summary,
        }

    if daily_counts is not None:
        daily_phones, daily_imeis, daily_accts = daily_counts
    else:
        try:
            daily_phones, daily_imeis, daily_accts = _load_daily_identifier_counts(store, case_id)
        except Exception:
            daily_phones, daily_imeis, daily_accts = {}, {}, {}

    call_counts = [c.get("count", 0) for c in calls]
    call_med, call_mad = _calc_median_and_mad(call_counts)
    call_thresh = max(CALL_SPIKE_MULTIPLIER * call_med, call_med + CALL_SPIKE_MAD_MULTIPLIER * call_mad)

    transfer_counts = [tr.get("count", 0) for tr in transfers]
    tr_count_med, tr_count_mad = _calc_median_and_mad(transfer_counts)
    tr_count_thresh = max(
        TRANSFER_SPIKE_MULTIPLIER * tr_count_med,
        tr_count_med + TRANSFER_SPIKE_MAD_MULTIPLIER * tr_count_mad,
    )

    transfer_paise = [tr.get("paise", 0) for tr in transfers]
    tr_amt_med, tr_amt_mad = _calc_median_and_mad(transfer_paise)
    tr_amt_thresh = max(
        TRANSFER_AMOUNT_MULTIPLIER * tr_amt_med,
        tr_amt_med + TRANSFER_SPIKE_MAD_MULTIPLIER * tr_amt_mad,
    )

    raw_insights: list[dict[str, Any]] = []

    # 1. Detect call spikes
    call_spikes: dict[str, dict[str, Any]] = {}
    for c in calls:
        d = c.get("t", "")[:10]
        cnt = c.get("count", 0)
        if cnt >= call_thresh and cnt >= MIN_CALL_EVENTS:
            call_spikes[d] = c
            ratio = (cnt / call_med) if call_med > 0 else float(cnt)
            top_phones = sorted(
                daily_phones.get(d, {}).items(), key=lambda x: x[1], reverse=True
            )[:2]
            identifiers = [{"type": "phone", "id": p} for p, _ in top_phones]
            links = [f"PHONE:{p}" for p, _ in top_phones]

            raw_insights.append({
                "kind": "call_spike",
                "chart": "calls",
                "days": [d],
                "headline": f"High call volume on {d} (worth a look)",
                "why": f"{cnt} calls on {d}; typical day is {call_med:.0f} (median); {ratio:.1f}x",
                "identifiers": identifiers,
                "links": links,
            })

    # 2. Detect transfer spikes
    transfer_spikes: dict[str, dict[str, Any]] = {}
    for tr in transfers:
        d = tr.get("t", "")[:10]
        cnt = tr.get("count", 0)
        paise = tr.get("paise", 0)

        count_triggered = cnt >= tr_count_thresh and cnt >= MIN_TRANSFER_EVENTS
        amount_triggered = (
            paise >= (TRANSFER_AMOUNT_MULTIPLIER * tr_amt_med)
            and paise >= MIN_TRANSFER_AMOUNT_PAISE
        )

        if count_triggered or amount_triggered:
            transfer_spikes[d] = tr
            top_accts = sorted(
                daily_accts.get(d, {}).items(), key=lambda x: x[1], reverse=True
            )[:2]
            identifiers = [{"type": "account", "id": a} for a, _ in top_accts]
            links = [f"ACCOUNT:{a}" for a, _ in top_accts]

            if count_triggered and not amount_triggered:
                ratio = (cnt / tr_count_med) if tr_count_med > 0 else float(cnt)
                why = f"{cnt} transfers on {d}; typical day is {tr_count_med:.0f} (median); {ratio:.1f}x"
                headline = f"High transfer count on {d} (worth a look)"
            elif amount_triggered and not count_triggered:
                ratio = (paise / tr_amt_med) if tr_amt_med > 0 else float(paise)
                amt_inr = paise / 100.0
                med_inr = tr_amt_med / 100.0
                why = f"Rs. {amt_inr:,.2f} on {d}; typical day is Rs. {med_inr:,.2f} (median); {ratio:.1f}x"
                headline = f"High transfer volume on {d} (worth a look)"
            else:
                ratio_cnt = (cnt / tr_count_med) if tr_count_med > 0 else float(cnt)
                amt_inr = paise / 100.0
                med_inr = tr_amt_med / 100.0
                why = f"{cnt} transfers (Rs. {amt_inr:,.2f}) on {d}; typical is {tr_count_med:.0f} transfers, Rs. {med_inr:,.2f}; {ratio_cnt:.1f}x"
                headline = f"High transfer count and volume on {d} (worth a look)"

            raw_insights.append({
                "kind": "transfer_spike",
                "chart": "transfers",
                "days": [d],
                "headline": headline,
                "why": why,
                "identifiers": identifiers,
                "links": links,
            })

    # 3. Detect call_then_transfer correlations (D to D+2)
    for call_day, call_obj in sorted(call_spikes.items()):
        c_date = _parse_date(call_day)
        if not c_date:
            continue
        for tr_day, tr_obj in sorted(transfer_spikes.items()):
            t_date = _parse_date(tr_day)
            if not t_date:
                continue
            delta = (t_date - c_date).days
            if 0 <= delta <= CALL_THEN_TRANSFER_WINDOW_DAYS:
                c_cnt = call_obj.get("count", 0)
                t_cnt = tr_obj.get("count", 0)
                t_paise = tr_obj.get("paise", 0)
                t_amt_inr = t_paise / 100.0

                top_phones = sorted(
                    daily_phones.get(call_day, {}).items(), key=lambda x: x[1], reverse=True
                )[:1]
                top_accts = sorted(
                    daily_accts.get(tr_day, {}).items(), key=lambda x: x[1], reverse=True
                )[:1]

                idents: list[dict[str, str]] = []
                lnks: list[str] = []
                for p, _ in top_phones:
                    idents.append({"type": "phone", "id": p})
                    lnks.append(f"PHONE:{p}")
                for a, _ in top_accts:
                    idents.append({"type": "account", "id": a})
                    lnks.append(f"ACCOUNT:{a}")

                day_desc = f"{delta} day{'s' if delta != 1 else ''} later" if delta > 0 else "same day"
                why = (
                    f"{c_cnt} calls on {call_day} followed by {t_cnt} transfers "
                    f"(Rs. {t_amt_inr:,.2f}) on {tr_day} ({day_desc})"
                )
                raw_insights.append({
                    "kind": "call_then_transfer",
                    "chart": "both",
                    "days": [call_day, tr_day],
                    "headline": f"Call spike on {call_day} followed by transfer spike on {tr_day} (worth a look)",
                    "why": why,
                    "identifiers": idents,
                    "links": lnks,
                })

    # 4. Detect new_and_busy identifiers
    # Check phones and IMEIs on call spike days
    for spike_day, call_obj in call_spikes.items():
        s_date = _parse_date(spike_day)
        if not s_date:
            continue
        spike_volume = call_obj.get("count", 0)
        if spike_volume <= 0:
            continue

        # Check phones
        for p_item in first_seen_phones:
            p_val = p_item.get("phone", "")
            f_time = p_item.get("t", "")
            f_date = _parse_date(f_time)
            if not p_val or not f_date:
                continue
            delta = (s_date - f_date).days
            if 0 <= delta <= NEW_BUSY_DAY_WINDOW:
                p_events = daily_phones.get(spike_day, {}).get(p_val, 0)
                share = p_events / spike_volume
                if share >= NEW_BUSY_VOLUME_SHARE and p_events >= NEW_BUSY_MIN_EVENTS:
                    day_desc = f"{delta} day{'s' if delta != 1 else ''} before spike" if delta > 0 else "on spike day"
                    raw_insights.append({
                        "kind": "new_and_busy",
                        "chart": "calls",
                        "days": [spike_day],
                        "headline": f"New phone {p_val} active during call spike on {spike_day} (worth a look)",
                        "why": (
                            f"First seen on {f_time[:10]} ({day_desc}); accounted for "
                            f"{p_events} calls on {spike_day} ({share * 100:.1f}% of day's total {spike_volume})"
                        ),
                        "identifiers": [{"type": "phone", "id": p_val}],
                        "links": [f"PHONE:{p_val}"],
                    })

        # Check IMEIs
        for im_item in first_seen_imeis:
            im_val = im_item.get("imei") or im_item.get("id") or ""
            f_time = im_item.get("t", "")
            f_date = _parse_date(f_time)
            if not im_val or not f_date:
                continue
            delta = (s_date - f_date).days
            if 0 <= delta <= NEW_BUSY_DAY_WINDOW:
                im_events = daily_imeis.get(spike_day, {}).get(im_val, 0)
                share = im_events / spike_volume
                if share >= NEW_BUSY_VOLUME_SHARE and im_events >= NEW_BUSY_MIN_EVENTS:
                    day_desc = f"{delta} day{'s' if delta != 1 else ''} before spike" if delta > 0 else "on spike day"
                    raw_insights.append({
                        "kind": "new_and_busy",
                        "chart": "calls",
                        "days": [spike_day],
                        "headline": f"New IMEI {im_val} active during call spike on {spike_day} (worth a look)",
                        "why": (
                            f"First seen on {f_time[:10]} ({day_desc}); accounted for "
                            f"{im_events} calls on {spike_day} ({share * 100:.1f}% of day's total {spike_volume})"
                        ),
                        "identifiers": [{"type": "imei", "id": im_val}],
                        "links": [f"IMEI:{im_val}"],
                    })

    # Check accounts on transfer spike days
    for spike_day, tr_obj in transfer_spikes.items():
        s_date = _parse_date(spike_day)
        if not s_date:
            continue
        spike_volume = tr_obj.get("count", 0)
        if spike_volume <= 0:
            continue

        for a_item in first_seen_accounts:
            a_val = a_item.get("account") or a_item.get("id") or ""
            f_time = a_item.get("t", "")
            f_date = _parse_date(f_time)
            if not a_val or not f_date:
                continue
            delta = (s_date - f_date).days
            if 0 <= delta <= NEW_BUSY_DAY_WINDOW:
                a_events = daily_accts.get(spike_day, {}).get(a_val, 0)
                share = a_events / spike_volume
                if share >= NEW_BUSY_VOLUME_SHARE and a_events >= NEW_BUSY_MIN_EVENTS:
                    day_desc = f"{delta} day{'s' if delta != 1 else ''} before spike" if delta > 0 else "on spike day"
                    raw_insights.append({
                        "kind": "new_and_busy",
                        "chart": "transfers",
                        "days": [spike_day],
                        "headline": f"New account {a_val} active during transfer spike on {spike_day} (worth a look)",
                        "why": (
                            f"First seen on {f_time[:10]} ({day_desc}); accounted for "
                            f"{a_events} transfers on {spike_day} ({share * 100:.1f}% of day's total {spike_volume})"
                        ),
                        "identifiers": [{"type": "account", "id": a_val}],
                        "links": [f"ACCOUNT:{a_val}"],
                    })

    # Sort insights chronologically by earliest day, then assign sequential IDs
    raw_insights.sort(key=lambda x: (x["days"][0] if x["days"] else "", x["kind"]))
    insights = []
    for idx, item in enumerate(raw_insights, start=1):
        item["id"] = f"insight-{idx}"
        insights.append(item)

    return {
        "case_id": case_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(insights),
        "reason": None,
        "rules": RULES,
        "insights": insights,
        "summary": summary,
    }
