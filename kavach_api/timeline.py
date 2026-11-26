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
    first_seen_imeis_map: dict[str, str] = {}
    phone_records: dict[str, list[dict[str, Any]]] = {}
    imei_records: dict[str, list[dict[str, Any]]] = {}

    if cdr_path.is_file():
        with open(cdr_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for r_num, row in enumerate(reader, start=1):
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
                        other_party = row.get("b_party" if phone_col == "a_party" else "a_party", "").strip()
                        imei_used = row.get("imei_a", "").strip() or row.get("imei", "").strip()
                        cps: list[str] = []
                        if other_party:
                            cps.append(other_party)
                        if imei_used:
                            cps.append(imei_used)
                        rec_entry = {"row": r_num, "timestamp": st, "counterparts": cps}

                        if p not in first_seen_map or st < first_seen_map[p]:
                            first_seen_map[p] = st
                            phone_records[p] = [rec_entry]
                        elif st == first_seen_map[p]:
                            if len(phone_records[p]) < 5:
                                phone_records[p].append(rec_entry)

                for imei_col in ("imei_a", "imei"):
                    im = row.get(imei_col, "").strip()
                    if im:
                        phone_used = row.get("a_party", "").strip()
                        cps_im = [phone_used] if phone_used else []
                        rec_entry_im = {"row": r_num, "timestamp": st, "counterparts": cps_im}

                        if im not in first_seen_imeis_map or st < first_seen_imeis_map[im]:
                            first_seen_imeis_map[im] = st
                            imei_records[im] = [rec_entry_im]
                        elif st == first_seen_imeis_map[im]:
                            if len(imei_records[im]) < 5:
                                imei_records[im].append(rec_entry_im)
                        break

    transfer_buckets: dict[str, dict[str, Any]] = {}
    first_seen_accounts_map: dict[str, str] = {}
    account_records: dict[str, list[dict[str, Any]]] = {}

    if bank_path.is_file():
        with open(bank_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for r_num, row in enumerate(reader, start=1):
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

                for acct_col in ("from_acct", "to_acct"):
                    acct = row.get(acct_col, "").strip()
                    if acct:
                        other_acct = row.get("to_acct" if acct_col == "from_acct" else "from_acct", "").strip()
                        cps_acct = [other_acct] if other_acct else []
                        rec_entry_acct = {"row": r_num, "timestamp": dt, "counterparts": cps_acct}

                        if acct not in first_seen_accounts_map or dt < first_seen_accounts_map[acct]:
                            first_seen_accounts_map[acct] = dt
                            account_records[acct] = [rec_entry_acct]
                        elif dt == first_seen_accounts_map[acct]:
                            if len(account_records[acct]) < 5:
                                account_records[acct].append(rec_entry_acct)

    def _format_first_record(file_kind: str, timestamp: str, recs: list[dict[str, Any]]) -> dict[str, Any]:
        rows_list = [r["row"] for r in recs]
        unique_cps: list[str] = []
        seen: set[str] = set()
        for r in recs:
            for cp in r.get("counterparts", []):
                if cp and cp not in seen:
                    seen.add(cp)
                    unique_cps.append(cp)
        return {
            "file": file_kind,
            "timestamp": timestamp,
            "rows": rows_list,
            "counterparts": unique_cps,
            "records": recs,
        }

    fir_map: dict[str, dict[str, Any]] = {}
    try:
        from kavach_api.analysis_service import build_graph
        from kavach_api.evidence import compute_first_fir_mention

        graph = build_graph(store, case_id)
        if graph:
            fir_incident: dict[str, list[dict[str, Any]]] = {}
            for e in graph.get("edges", []):
                if e.get("source_kind") == "FIR":
                    fir_incident.setdefault(e.get("source", ""), []).append(e)
                    fir_incident.setdefault(e.get("target", ""), []).append(e)

            n_map = {n.get("id", ""): n for n in graph.get("nodes", [])}
            all_target_ids = (
                [f"PHONE:{p}" for p in first_seen_map.keys()]
                + [f"ACCOUNT:{a}" for a in first_seen_accounts_map.keys()]
                + [f"IMEI:{im}" for im in first_seen_imeis_map.keys()]
            )
            for nid in all_target_ids:
                n = n_map.get(nid)
                if n and (n.get("source_firs") or n.get("evidence_spans") or nid in fir_incident):
                    ff = compute_first_fir_mention(store, case_id, graph, nid)
                    if ff and ff.get("first_fir_id"):
                        fir_map[nid] = {
                            "first_fir_id": ff.get("first_fir_id"),
                            "date": ff.get("date"),
                            "related_count": len(ff.get("related_entities", [])),
                        }
    except Exception:
        fir_map = {}

    calls_list = sorted(call_buckets.values(), key=lambda x: x["t"])
    transfers_list = sorted(transfer_buckets.values(), key=lambda x: x["t"])
    first_seen_list = sorted(
        [
            {
                "phone": p,
                "t": t,
                "first_record": _format_first_record("cdr", t, phone_records.get(p, [])),
                "first_fir": fir_map.get(f"PHONE:{p}"),
            }
            for p, t in first_seen_map.items()
        ],
        key=lambda x: (x["t"], x["phone"]),
    )
    first_seen_accounts_list = sorted(
        [
            {
                "account": a,
                "id": a,
                "t": t,
                "first_record": _format_first_record("bank", t, account_records.get(a, [])),
                "first_fir": fir_map.get(f"ACCOUNT:{a}"),
            }
            for a, t in first_seen_accounts_map.items()
        ],
        key=lambda x: (x["t"], x["account"]),
    )
    first_seen_imeis_list = sorted(
        [
            {
                "imei": im,
                "id": im,
                "t": t,
                "first_record": _format_first_record("cdr", t, imei_records.get(im, [])),
                "first_fir": fir_map.get(f"IMEI:{im}"),
            }
            for im, t in first_seen_imeis_map.items()
        ],
        key=lambda x: (x["t"], x["imei"]),
    )

    return {
        "bucket": bucket,
        "calls": calls_list,
        "transfers": transfers_list,
        "first_seen": first_seen_list,
        "first_seen_accounts": first_seen_accounts_list,
        "first_seen_imeis": first_seen_imeis_list,
    }
