"""
Deterministic generator for the Insights scenario dataset.
Constructed scenario with planted bursts for demonstrating the Insights feature (not evaluation data).
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import random
import shutil
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent

# Input paths
DEFAULT_CDR_SRC = REPO_ROOT / "data" / "synthetic" / "out" / "case_demo_v2" / "cdr.csv"
DEFAULT_BANK_SRC = REPO_ROOT / "data" / "synthetic" / "out" / "case_demo_v2" / "bank.csv"
DEFAULT_FIRS_DIR = REPO_ROOT / "data" / "synthetic" / "out" / "firs_v5"
DEFAULT_ANALYSES_DIR = REPO_ROOT / "results" / "2026-11-11_step6_extraction_r2" / "run1"

# Target scenario directory
DEFAULT_OUT_DIR = REPO_ROOT / "data" / "synthetic" / "out" / "insights_scenario"

# Planted identifiers
NEW_PHONE = "9899112233"
NEW_IMEI = "358811223344556"
NEW_ACCT = "998811223344"
IFSC_EXAMPLE = "SBIN0123456"


def generate_insights_scenario(
    out_dir: Path | str | None = None,
    seed: int = 42,
) -> dict[str, Any]:
    """
    Generate the constructed insights scenario files deterministically.
    Copies original demo files, appends burst rows, writes README, and returns summary stats.
    """
    target_path = Path(out_dir).resolve() if out_dir else DEFAULT_OUT_DIR
    target_path.mkdir(parents=True, exist_ok=True)

    firs_out = target_path / "firs"
    firs_out.mkdir(parents=True, exist_ok=True)
    analyses_out = target_path / "analyses"
    analyses_out.mkdir(parents=True, exist_ok=True)

    # 1. Copy 100 FIR text files and analyses
    for fir_file in sorted(DEFAULT_FIRS_DIR.glob("FIR_*.txt")):
        shutil.copy2(fir_file, firs_out / fir_file.name)

    if DEFAULT_ANALYSES_DIR.is_dir():
        for a_file in sorted(DEFAULT_ANALYSES_DIR.glob("*.analysis.json")):
            shutil.copy2(a_file, analyses_out / a_file.name)

    # 2. Add extra FIR_101.txt and matching analysis for new phone
    fir_101_text = (
        "Special Staff Police Station ke antargat FIR No.301/2026 u/s 318(4) BNS darj kiya gaya. "
        "Gupte suchna ke aadhar par police team ne suspect Rajendra Singh s/o Maheshwar Singh ko hirasat mein liya. "
        "Search proceedings ke dauran suspect ke pas se naya operational calling connection 9899112233 zabt shuda paya gaya."
    )
    fir_101_path = firs_out / "FIR_101.txt"
    fir_101_bytes = fir_101_text.encode("utf-8")
    fir_101_path.write_bytes(fir_101_bytes)
    fir_101_hash = hashlib.sha256(fir_101_bytes).hexdigest()

    # Pre-calculated char spans for FIR_101
    rs_start = fir_101_text.find("Rajendra Singh")
    rs_end = rs_start + len("Rajendra Singh")
    phone_start = fir_101_text.find(NEW_PHONE)
    phone_end = phone_start + len(NEW_PHONE)

    fir_101_analysis = {
        "aux": {"source_doc_id": "FIR_101"},
        "doc": {
            "case_id": "INSIGHTS_SCENARIO",
            "source_doc_id": "FIR_101",
            "schema_version": "1.1",
            "entities": [
                {
                    "id": "ent_01",
                    "type": "PERSON",
                    "canonical_name": "Rajendra Singh",
                    "father_name": "Maheshwar Singh",
                    "role": "SUSPECT",
                    "char_span": [rs_start, rs_end],
                    "mentions": [{"surface": "Rajendra Singh", "kind": "NAME", "char_span": [rs_start, rs_end]}],
                    "ai_confidence": 0.99,
                    "confidence_breakdown": {"context": None, "model": 0.99, "validator": None},
                    "flags": [],
                },
                {
                    "id": "ent_02",
                    "type": "PHONE",
                    "value": NEW_PHONE,
                    "char_span": [phone_start, phone_end],
                    "mentions": [{"surface": NEW_PHONE, "kind": "VALUE", "char_span": [phone_start, phone_end]}],
                    "ai_confidence": 0.99,
                    "confidence_breakdown": {"context": None, "model": None, "validator": 0.99},
                    "flags": [],
                },
            ],
            "relationships": [
                {
                    "source": "ent_01",
                    "target": "ent_02",
                    "relation": "OWNS_DEVICE",
                    "trigger": "calling connection",
                    "confidence": 0.95,
                    "evidence_char_span": [rs_start, phone_end],
                }
            ],
        },
        "info": {
            "document_hash": fir_101_hash,
            "char_count": len(fir_101_text),
            "amounts_count": 0,
            "entities_by_type": {"PERSON": 1, "PHONE": 1},
            "relations_by_label": {"OWNS_DEVICE": 1},
            "mode": "MODEL",
            "warnings": [],
        },
    }
    (analyses_out / "FIR_101.analysis.json").write_text(
        json.dumps(fir_101_analysis, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # 3. Read base CDR and Bank records
    with open(DEFAULT_CDR_SRC, "r", encoding="utf-8") as f:
        cdr_reader = csv.DictReader(f)
        cdr_fields = list(cdr_reader.fieldnames or [])
        base_cdr_rows = list(cdr_reader)

    with open(DEFAULT_BANK_SRC, "r", encoding="utf-8") as f:
        bank_reader = csv.DictReader(f)
        bank_fields = list(bank_reader.fieldnames or [])
        base_bank_rows = list(bank_reader)

    # Collect existing demo identifiers to interoperate with
    demo_phones = sorted(list(set(r["a_party"] for r in base_cdr_rows) | set(r["b_party"] for r in base_cdr_rows)))
    demo_imeis = sorted(list(set(r["imei_a"] for r in base_cdr_rows if r.get("imei_a"))))
    demo_accts = sorted(list(set(r["from_acct"] for r in base_bank_rows) | set(r["to_acct"] for r in base_bank_rows)))

    rng = random.Random(seed)
    extra_cdr: list[dict[str, str]] = []
    extra_bank: list[dict[str, str]] = []

    # --- PLANTING BURSTS ---

    # A. Day 10 (2026-01-10): Call Spike 1 (exceeds 3x median call count)
    # NEW_PHONE carries 175 calls (21.5% of 815 >= 20% and >= 5) -> new_and_busy phone
    for _ in range(175):
        h = rng.randint(8, 22)
        m = rng.randint(0, 59)
        s = rng.randint(0, 59)
        extra_cdr.append({
            "a_party": NEW_PHONE,
            "b_party": rng.choice(demo_phones),
            "imei_a": rng.choice(demo_imeis),
            "imsi_a": "404450123456789",
            "start_time": f"2026-01-10T{h:02d}:{m:02d}:{s:02d}",
            "duration_sec": str(rng.randint(20, 300)),
            "call_type": "VOICE",
            "tower_id": "TWR_DEL_01",
            "lat": "28.64700",
            "lon": "77.19126",
        })

    # Remaining 385 calls on Day 10 spread uniformly across demo phones
    for i in range(385):
        h = rng.randint(8, 22)
        m = rng.randint(0, 59)
        s = rng.randint(0, 59)
        p1 = demo_phones[i % len(demo_phones)]
        p2 = demo_phones[(i + 1) % len(demo_phones)]
        im = demo_imeis[i % len(demo_imeis)]
        extra_cdr.append({
            "a_party": p1,
            "b_party": p2,
            "imei_a": im,
            "imsi_a": "404450123456789",
            "start_time": f"2026-01-10T{h:02d}:{m:02d}:{s:02d}",
            "duration_sec": str(rng.randint(20, 300)),
            "call_type": "VOICE",
            "tower_id": "TWR_DEL_02",
            "lat": "28.65160",
            "lon": "77.23078",
        })

    # B. Day 12 (2026-01-12): Transfer Spike 1 (Count spike > 3x median count, followed Day 10 by 2 days)
    # Forms call_then_transfer pair with Day 10!
    # NEW_ACCT carries 35 transfers (21.6% of 162 >= 20% and >= 5) -> new_and_busy account
    txn_id_counter = 900000
    for _ in range(35):
        txn_id_counter += 1
        h = rng.randint(9, 21)
        m = rng.randint(0, 59)
        s = rng.randint(0, 59)
        amt = round(rng.uniform(3000, 8000), 2)
        extra_bank.append({
            "txn_id": f"TXN{txn_id_counter}",
            "datetime": f"2026-01-12T{h:02d}:{m:02d}:{s:02d}",
            "from_acct": rng.choice(demo_accts),
            "to_acct": NEW_ACCT,
            "amount": f"{amt:.2f}",
            "mode": "UPI",
            "ifsc": IFSC_EXAMPLE,
            "narration": "P2P Settlement",
        })

    for i in range(75):
        txn_id_counter += 1
        h = rng.randint(9, 21)
        m = rng.randint(0, 59)
        s = rng.randint(0, 59)
        a1 = demo_accts[i % len(demo_accts)]
        a2 = demo_accts[(i + 1) % len(demo_accts)]
        amt = round(rng.uniform(2000, 5000), 2)
        extra_bank.append({
            "txn_id": f"TXN{txn_id_counter}",
            "datetime": f"2026-01-12T{h:02d}:{m:02d}:{s:02d}",
            "from_acct": a1,
            "to_acct": a2,
            "amount": f"{amt:.2f}",
            "mode": "IMPS",
            "ifsc": IFSC_EXAMPLE,
            "narration": "Petty Cash",
        })

    # C. Day 20 (2026-01-20): Call Spike 2 (exceeds 3x median call count)
    # NEW_IMEI carries 175 calls (21.6% of 809 >= 20% and >= 5) -> new_and_busy IMEI
    for _ in range(175):
        h = rng.randint(8, 22)
        m = rng.randint(0, 59)
        s = rng.randint(0, 59)
        extra_cdr.append({
            "a_party": rng.choice(demo_phones),
            "b_party": rng.choice(demo_phones),
            "imei_a": NEW_IMEI,
            "imsi_a": "404450123456789",
            "start_time": f"2026-01-20T{h:02d}:{m:02d}:{s:02d}",
            "duration_sec": str(rng.randint(20, 300)),
            "call_type": "VOICE",
            "tower_id": "TWR_DEL_03",
            "lat": "28.64700",
            "lon": "77.19126",
        })

    for i in range(385):
        h = rng.randint(8, 22)
        m = rng.randint(0, 59)
        s = rng.randint(0, 59)
        p1 = demo_phones[i % len(demo_phones)]
        p2 = demo_phones[(i + 1) % len(demo_phones)]
        im = demo_imeis[i % len(demo_imeis)]
        extra_cdr.append({
            "a_party": p1,
            "b_party": p2,
            "imei_a": im,
            "imsi_a": "404450123456789",
            "start_time": f"2026-01-20T{h:02d}:{m:02d}:{s:02d}",
            "duration_sec": str(rng.randint(20, 300)),
            "call_type": "VOICE",
            "tower_id": "TWR_DEL_04",
            "lat": "28.65160",
            "lon": "77.23078",
        })

    # D. Day 21 (2026-01-21): Transfer Spike 2 (Amount spike > 3x median amount, followed Day 20 by 1 day)
    # Forms call_then_transfer pair with Day 20!
    for i in range(5):
        txn_id_counter += 1
        h = rng.randint(10, 16)
        m = rng.randint(0, 59)
        s = rng.randint(0, 59)
        a1 = demo_accts[i % len(demo_accts)]
        a2 = demo_accts[(i + 1) % len(demo_accts)]
        amt = 840000.00  # Rs 8,40,000 * 5 = Rs 42,00,000
        extra_bank.append({
            "txn_id": f"TXN{txn_id_counter}",
            "datetime": f"2026-01-21T{h:02d}:{m:02d}:{s:02d}",
            "from_acct": a1,
            "to_acct": a2,
            "amount": f"{amt:.2f}",
            "mode": "RTGS",
            "ifsc": IFSC_EXAMPLE,
            "narration": "Commercial Property Settlement",
        })

    # 4. Write scenario CSVs with original rows untouched and extra rows appended
    out_cdr_path = target_path / "cdr.csv"
    with open(out_cdr_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=cdr_fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(base_cdr_rows)
        writer.writerows(extra_cdr)

    out_bank_path = target_path / "bank.csv"
    with open(out_bank_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=bank_fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(base_bank_rows)
        writer.writerows(extra_bank)

    # 5. Write README.md
    readme_path = target_path / "README.md"
    readme_content = (
        "# Insights Scenario Dataset (Constructed Synthetic)\n\n"
        "This dataset is a constructed scenario with planted bursts and temporal patterns "
        "designed specifically for demonstrating and testing the Timeline Insights feature in KAVACH. "
        "It is NOT evaluation or benchmark ground truth data.\n\n"
        "## Planted Patterns Summary:\n"
        "- 2 Call Volume Spikes: Day 10 (2026-01-10) and Day 20 (2026-01-20).\n"
        "- 2 Transfer Volume Spikes: Day 12 (2026-01-12, count spike) and Day 21 (2026-01-21, amount spike).\n"
        "- 2 Call-then-Transfer Correlations: 2026-01-10 -> 2026-01-12 and 2026-01-20 -> 2026-01-21.\n"
        "- 3 New and Busy Identifiers:\n"
        "  - Phone 9899112233: first seen 2026-01-10, carries ~21.5% of calls on Day 10 spike.\n"
        "  - Account 998811223344: first seen 2026-01-12, carries ~21.6% of transfers on Day 12 spike.\n"
        "  - IMEI 358811223344556: first seen 2026-01-20, carries ~21.6% of calls on Day 20 spike.\n"
        "- 1 Additional FIR (FIR_101.txt): links new phone 9899112233 to suspect Rajendra Singh.\n"
    )
    readme_path.write_text(readme_content, encoding="utf-8")

    return {
        "out_dir": str(target_path),
        "cdr_rows": len(base_cdr_rows) + len(extra_cdr),
        "bank_rows": len(base_bank_rows) + len(extra_bank),
        "extra_cdr": len(extra_cdr),
        "extra_bank": len(extra_bank),
        "fir_count": len(list(firs_out.glob("FIR_*.txt"))),
    }


def main() -> None:
    res = generate_insights_scenario()
    print(
        f"Insights scenario created in {res['out_dir']}: "
        f"{res['cdr_rows']} CDR rows ({res['extra_cdr']} injected), "
        f"{res['bank_rows']} Bank rows ({res['extra_bank']} injected), "
        f"{res['fir_count']} FIRs."
    )


if __name__ == "__main__":
    main()
