#!/usr/bin/env python3
"""Deterministic generator for live-demo upload kit.

Generates 3 connected FIR text files, valid CDR and Bank CSVs with realistic
burner phone and mule account patterns, a bad CDR file for demonstration,
and an EXPECTED.txt verification guide.

All outputs are deterministically generated with a fixed seed.
"""
from __future__ import annotations

import csv
from datetime import datetime, timedelta
import io
import os
from pathlib import Path
import random
import shutil
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from kavach_api.ingest import decode_fir, validate_bank, validate_cdr
from kavach_api.settings import load_settings

# Fixed random seed for complete determinism
SEED = 20260301

# Default output locations
DESKTOP_DIR = Path(r"C:\Users\Kirthan\Desktop\kavach_live_demo")
SCRATCH_DIR = REPO_ROOT / "scratch" / "kavach_live_demo"


# ---------------------------------------------------------------------------
# FIR Texts
# ---------------------------------------------------------------------------
# The three FIRs are linked by:
# Shared persons: Amitabh Sen, Rohit Verma, Kunal Mehra
# Shared phones: 9811022334 (Amitabh Sen), 9877033445 (Kunal Mehra), 9823011223 (Rohit Verma)
# Shared account: 40192837465 (managed by Amitabh Sen)

FIR_A_TEXT = """POLICE STATION CYBER CRIME, NORTH DISTRICT, DELHI
FIRST INFORMATION REPORT
FIR No.: 142/2026
Date & Time: 2026-03-02 11:30:00
U/S: 318(4)/61(2) BNS

Mukadma ba-tahreer SI Anil Deshmukh darj register kiya gaya. Gupte suchna ke aadhar par police team ne Sector 18 ke pass ek suspicious vehicle DL-01-AB-1234 ko intercept karke suspect Rohit Verma urf Rocky s/o Shri Mohan Verma r/o Lane 4, Shastri Nagar ko hirasat mein liya. Accused Rohit Verma ke personal talashi ke dauran uske kabze se mobile phone 9823011223 (bearing IMEI 864201948201948) baramad hua. CDR scrutiny se pata chala ki handset 9823011223 ne master calling number 9811022334 par frequent voice calls kiye. Accused Rohit Verma ne confess kiya ki usne hawala proceeds ki rashi Rs. 2,25,000.00/- transfer kiya into bank account 40192837465. Jaanch se yeh clear ho gaya ki ukt khata 40192837465 syndicate handler Amitabh Sen @ Amit s/o Shri Pradip Sen dwara secretly control kiya jata tha. Baramad shuda phone tatha cash rashi ko police custody mein liya gaya."""

FIR_B_TEXT = """POLICE STATION CRIME BRANCH, SPECIAL OPERATIONS, NEW DELHI
FIRST INFORMATION REPORT
FIR No.: 178/2026
Date & Time: 2026-03-06 14:15:00
U/S: 318(4)/61(2)/111 BNS

Special Staff team ne transport nagar godown par raid conduct karke suspect Kunal Mehra urf KD s/o Shri Anand Mehra r/o Sector 22, Rohini ko apprehend kiya. Spot par suspect ki vehicle HR-26-CD-5678 park thi. Personal search memo ke dauran suspect Kunal Mehra ke kabze se active burner handset 9877033445 (hardware IMEI 359876102938475) seized kiya gaya. Technical surveillance se record hua ki number 9877033445 was in regular contact with key coordinator 9811022334 and associate Rohit Verma operating number 9823011223. Accused Kunal Mehra ne bataya ki usne sum of INR 1,80,000.00 remitted into beneficiary account 40192837465. Primary account 40192837465 syndicate head Amitabh Sen dwara operated tha, jisme alag-alag mule sources se deposits aate the. Mobile phone 9877033445 aur relevant documents ko case property ke roop mein zapt kiya gaya."""

FIR_C_TEXT = """POLICE STATION ECONOMIC OFFENCES WING, DELHI POLICE
FIRST INFORMATION REPORT
FIR No.: 205/2026
Date & Time: 2026-03-10 16:45:00
U/S: 318(4)/316(2)/61(2) BNS

Complainant ki complaint par inquiry shuru karte hue cyber fraud syndicate ke mule layering layer ka parda-fash hua. Investigation ke dauran suspect Pooja Batra d/o Shri Ramesh Batra r/o Mayur Vihar Phase-1 ko summon karke interrogate kiya gaya. Suspect Pooja Batra registered user thi calling connection 9899044556 ki. CDR exchange show karta hai ki phone 9899044556 se multiple voice calls dialled to 9811022334 managed by mastermind Amitabh Sen tatha secondary contact 9877033445 belonging to Kunal Mehra. Banking ledger scrutiny ke mutabik accused Pooja Batra ne sum INR 3,10,000.00 deposited into central collection account 40192837465. Ukt khata 40192837465 Amitabh Sen ke direct control mein tha, jisse funds ko subsequent payout account 50281920394 mein divert kiya gaya. Mamle ki tafteesh jari hai."""


def generate_cdr_rows(rng: random.Random) -> list[dict[str, Any]]:
    """Generate ~520 realistic CDR rows covering a 14-day window (2026-03-01 to 2026-03-14)."""
    start_dt = datetime(2026, 3, 1, 8, 0, 0)

    # Core syndicate phones
    p_rohit = "9823011223"
    p_amitabh = "9811022334"
    p_kunal_burner = "9877033445"
    p_pooja = "9899044556"

    # IMEIs
    imei_rohit = "864201948201948"
    imei_kunal = "359876102938475"
    imei_amitabh = "354091028374651"
    imei_pooja = "869102837465019"

    # Background civilian phones
    bg_phones = [
        f"98{rng.randint(10000000, 99999999)}"
        for _ in range(18)
    ]
    towers = [f"TWR_DEL_{i:02d}" for i in range(1, 12)]

    rows: list[dict[str, Any]] = []

    # 1. Background traffic: distributed evenly across 14 days (~380 rows)
    for day in range(14):
        day_date = start_dt + timedelta(days=day)
        # ~27 calls per day
        for _ in range(27):
            call_time = day_date + timedelta(
                hours=rng.randint(0, 14),
                minutes=rng.randint(0, 59),
                seconds=rng.randint(0, 59),
            )
            caller, callee = rng.sample(bg_phones, 2)
            dur = rng.randint(15, 360)
            twr = rng.choice(towers)
            rows.append({
                "a_party": caller,
                "b_party": callee,
                "imei_a": f"35{rng.randint(1000000000000, 9999999999999)}",
                "imsi_a": f"40585{rng.randint(1000000000, 9999999999)}",
                "start_time": call_time.strftime("%Y-%m-%dT%H:%M:%S"),
                "duration_sec": str(dur),
                "call_type": "VOICE" if rng.random() > 0.15 else "SMS",
                "tower_id": twr,
                "lat": f"{28.60 + rng.random()*0.12:.5f}",
                "lon": f"{77.15 + rng.random()*0.12:.5f}",
            })

    # 2. Syndicate calls between Rohit, Amitabh, Pooja (~100 rows across 14 days)
    for day in range(14):
        day_date = start_dt + timedelta(days=day)
        for _ in range(7):
            call_time = day_date + timedelta(
                hours=rng.randint(1, 13),
                minutes=rng.randint(0, 59),
                seconds=rng.randint(0, 59),
            )
            pair = rng.choice([
                (p_rohit, p_amitabh, imei_rohit),
                (p_amitabh, p_rohit, imei_amitabh),
                (p_pooja, p_amitabh, imei_pooja),
                (p_amitabh, p_pooja, imei_amitabh),
                (p_rohit, rng.choice(bg_phones), imei_rohit),
                (p_pooja, rng.choice(bg_phones), imei_pooja),
            ])
            rows.append({
                "a_party": pair[0],
                "b_party": pair[1],
                "imei_a": pair[2],
                "imsi_a": f"40585{rng.randint(1000000000, 9999999999)}",
                "start_time": call_time.strftime("%Y-%m-%dT%H:%M:%S"),
                "duration_sec": str(rng.randint(40, 420)),
                "call_type": "VOICE",
                "tower_id": "TWR_DEL_04",
                "lat": "28.64720",
                "lon": "77.21940",
            })

    # 3. Burner Phone Pattern: Kunal's phone 9877033445
    # First seen on Day 9 (late activation), active ONLY Day 9 and Day 10 (short lifespan: 2 days)
    # Exactly 2 contacts: Amitabh (9811022334) and Rohit (9823011223) -> top2_share = 1.0 (~35 calls)
    for day in [8, 9]:  # Day 9 and Day 10 (0-indexed 8 and 9)
        day_date = start_dt + timedelta(days=day)
        for _ in range(18):
            call_time = day_date + timedelta(
                hours=rng.randint(2, 11),
                minutes=rng.randint(0, 59),
                seconds=rng.randint(0, 59),
            )
            target = p_amitabh if rng.random() > 0.4 else p_rohit
            rows.append({
                "a_party": p_kunal_burner,
                "b_party": target,
                "imei_a": imei_kunal,
                "imsi_a": f"40585{rng.randint(1000000000, 9999999999)}",
                "start_time": call_time.strftime("%Y-%m-%dT%H:%M:%S"),
                "duration_sec": str(rng.randint(60, 300)),
                "call_type": "VOICE",
                "tower_id": "TWR_DEL_08",
                "lat": "28.68210",
                "lon": "77.14250",
            })

    # Sort deterministically by start_time
    rows.sort(key=lambda r: r["start_time"])
    return rows


def generate_bank_rows(rng: random.Random) -> list[dict[str, Any]]:
    """Generate ~150 realistic Bank transaction rows covering a 14-day window (2026-03-01 to 2026-03-14)."""
    start_dt = datetime(2026, 3, 1, 9, 0, 0)

    # Core syndicate accounts
    acct_mule = "40192837465"      # Primary mule account (managed by Amitabh Sen)
    acct_payout = "50281920394"    # Downstream consolidation payout account

    # Feeder accounts (victims / conduits depositing structuring amounts)
    feeder_accts = [
        "91827364501",
        "92837465012",
        "93847560123",
        "94857601234",
        "95867012345",
        "96870123456",
    ]

    # Background civilian accounts
    bg_accts = [f"{rng.randint(10000000000, 99999999999)}" for _ in range(14)]

    rows: list[dict[str, Any]] = []
    txn_counter = 1

    # 1. Background transactions across 14 days (~110 rows)
    for day in range(14):
        day_date = start_dt + timedelta(days=day)
        # ~8 txns per day
        for _ in range(8):
            txn_time = day_date + timedelta(
                hours=rng.randint(0, 8),
                minutes=rng.randint(0, 59),
                seconds=rng.randint(0, 59),
            )
            src, dst = rng.sample(bg_accts, 2)
            amt = f"{rng.randint(500, 24000)}.{rng.randint(10, 99)}"
            mode = rng.choice(["IMPS", "NEFT", "UPI"])
            rows.append({
                "txn_id": f"TXN{txn_counter:06d}",
                "datetime": txn_time.strftime("%Y-%m-%dT%H:%M:%S"),
                "from_acct": src,
                "to_acct": dst,
                "amount": amt,
                "mode": mode,
                "ifsc": "SBIN0001234",
                "narration": rng.choice(["Vendor payment", "Rent transfer", "Utility bill", "Online purchase", "Consulting fee"]),
            })
            txn_counter += 1

    # 2. Mule Account Pattern on acct_mule (40192837465) (~40 rows):
    # - High fan-in: 6 distinct feeder accounts depositing money
    # - Structuring: deposits between 45000.00 and 49900.00 (just under 50000 threshold)
    # - Low dwell & high passthrough: inward money promptly transferred out to acct_payout
    for cycle in range(5):
        # Days 2, 4, 7, 10, 13
        cycle_day = [1, 3, 6, 9, 12][cycle]
        day_date = start_dt + timedelta(days=cycle_day)

        cycle_in_total = 0.0
        # 3 deposits from different feeder accounts in structuring range
        for d_idx in range(3):
            dep_time = day_date + timedelta(hours=1 + d_idx, minutes=rng.randint(5, 55))
            sender = feeder_accts[(cycle * 2 + d_idx) % len(feeder_accts)]
            # Structuring amount: [46500, 49800]
            amt_val = rng.randint(46500, 49800) + rng.randint(10, 90) / 100.0
            cycle_in_total += amt_val
            rows.append({
                "txn_id": f"TXN{txn_counter:06d}",
                "datetime": dep_time.strftime("%Y-%m-%dT%H:%M:%S"),
                "from_acct": sender,
                "to_acct": acct_mule,
                "amount": f"{amt_val:.2f}",
                "mode": "IMPS",
                "ifsc": "HDFC0004321",
                "narration": "Immediate transfer credit",
            })
            txn_counter += 1

        # Outward drain to payout account within 2 hours of last deposit (low dwell, high passthrough)
        drain_time = day_date + timedelta(hours=5, minutes=rng.randint(10, 40))
        drain_amt = round(cycle_in_total * 0.98, 2)  # 98% passthrough
        rows.append({
            "txn_id": f"TXN{txn_counter:06d}",
            "datetime": drain_time.strftime("%Y-%m-%dT%H:%M:%S"),
            "from_acct": acct_mule,
            "to_acct": acct_payout,
            "amount": f"{drain_amt:.2f}",
            "mode": "NEFT",
            "ifsc": "ICIC0008899",
            "narration": "Consolidation transfer",
        })
        txn_counter += 1

    # Sort deterministically by datetime
    rows.sort(key=lambda r: r["datetime"])
    return rows


def generate_bad_cdr_content() -> str:
    """Generate deliberately invalid CDR CSV content with a missing required column."""
    # Header replaces 'a_party' with invalid 'caller_phone'
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow([
        "caller_phone",  # INVALID COLUMN NAME (triggers missing_column validation error)
        "b_party",
        "imei_a",
        "imsi_a",
        "start_time",
        "duration_sec",
        "call_type",
        "tower_id",
        "lat",
        "lon",
    ])
    writer.writerow([
        "9823011223",
        "9811022334",
        "864201948201948",
        "405851234567890",
        "2026-03-02T10:15:00",
        "120",
        "VOICE",
        "TWR_DEL_01",
        "28.64000",
        "77.21000",
    ])
    return out.getvalue()


EXPECTED_GUIDE_TEXT = """KAVACH LIVE-DEMO DATASET EXPECTATION GUIDE
===========================================
This dataset is designed for live demonstration of FIR upload, entity extraction,
relational graph linking, and automated lead detection.

1. FIR TEXT EXTRACTIONS
-----------------------
FIR_A.txt:
  - Incident: Illegal financial fraud syndicate operating in North Delhi
  - Suspect: Rohit Verma (Alias: Rocky, Father: Mohan Verma)
  - Associate: Amitabh Sen (Alias: Amit, Father: Pradip Sen)
  - Vehicle: DL-01-AB-1234
  - Phone: 9823011223 (IMEI: 864201948201948)
  - Bank Account: 40192837465 (Amount: INR 2,25,000.00)
  - Relations:
      Rohit Verma OWNS_DEVICE 9823011223
      Phone 9823011223 COMMUNICATED_WITH 9811022334
      Rohit Verma TRANSFERRED_FUNDS 40192837465 (Rs. 2,25,000)
      Amitabh Sen CONTROLS_ACCOUNT 40192837465

FIR_B.txt:
  - Incident: Transport nagar godown raid & fake SIM card conduit
  - Suspect: Kunal Mehra (Alias: KD, Father: Anand Mehra)
  - Associates: Rohit Verma, Amitabh Sen
  - Vehicle: HR-26-CD-5678
  - Phone: 9877033445 (IMEI: 359876102938475)
  - Bank Account: 40192837465 (Amount: INR 1,80,000.00)
  - Relations:
      Kunal Mehra OWNS_DEVICE 9877033445
      Phone 9877033445 COMMUNICATED_WITH 9811022334
      Kunal Mehra TRANSFERRED_FUNDS 40192837465 (Rs. 1,80,000)
      Amitabh Sen CONTROLS_ACCOUNT 40192837465

FIR_C.txt:
  - Incident: Cyber layering & downstream account laundering
  - Suspect: Pooja Batra (Father: Ramesh Batra)
  - Associates: Amitabh Sen, Kunal Mehra
  - Phone: 9899044556
  - Bank Accounts: 40192837465 (collection), 50281920394 (payout)
  - Amount: INR 3,10,000.00
  - Relations:
      Pooja Batra OWNS_DEVICE 9899044556
      Phone 9899044556 COMMUNICATED_WITH 9811022334
      Phone 9899044556 COMMUNICATED_WITH 9877033445
      Pooja Batra TRANSFERRED_FUNDS 40192837465 (Rs. 3,10,000)
      Amitabh Sen CONTROLS_ACCOUNT 40192837465

2. SHARED ENTITIES & GRAPH COHESION
------------------------------------
  - Shared Persons (3): Amitabh Sen (FIR_A, B, C), Rohit Verma (FIR_A, B), Kunal Mehra (FIR_B, C)
  - Shared Phones (3): 9811022334 (FIR_A, B, C), 9823011223 (FIR_A, B), 9877033445 (FIR_B, C)
  - Shared Account (1): 40192837465 (FIR_A, B, C)
  - Graph Topology: Multi-component connected graph bridging cyber fraud, logistics, and layering operations.

3. EXPECTED OVERVIEW LEADS
--------------------------
  - Mule Account: 40192837465
      * High fan-in: multiple distinct sender accounts
      * Structuring deposits: multiple credits in [45000, 50000) range
      * Rapid passthrough: ~98% of deposited balance drained to 50281920394 within hours
  - Burner Phone: 9877033445 (Kunal Mehra)
      * Late activation: first seen Day 9 of 14-day observation window
      * Short lifespan: active for only 2 days
      * Limited contacts: 100% of calls concentrated on top 2 contacts (9811022334, 9823011223)

4. BAD CDR FOR LIVE ERROR DISPLAY
---------------------------------
  - bad_cdr.csv has header column 'caller_phone' instead of required 'a_party'.
  - Uploading bad_cdr.csv triggers an immediate 400 Bad Request with missing_column error message.
"""


def write_kit(out_dir: Path) -> dict[str, Any]:
    """Generate and write all kit files to target directory."""
    rng = random.Random(SEED)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Write FIRs
    fir_a_path = out_dir / "FIR_A.txt"
    fir_b_path = out_dir / "FIR_B.txt"
    fir_c_path = out_dir / "FIR_C.txt"

    fir_a_path.write_text(FIR_A_TEXT, encoding="utf-8")
    fir_b_path.write_text(FIR_B_TEXT, encoding="utf-8")
    fir_c_path.write_text(FIR_C_TEXT, encoding="utf-8")

    # 2. Write CDR CSV
    cdr_rows = generate_cdr_rows(rng)
    cdr_path = out_dir / "cdr.csv"
    with open(cdr_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "a_party", "b_party", "imei_a", "imsi_a", "start_time",
            "duration_sec", "call_type", "tower_id", "lat", "lon"
        ])
        writer.writeheader()
        writer.writerows(cdr_rows)

    # 3. Write Bank CSV
    bank_rows = generate_bank_rows(rng)
    bank_path = out_dir / "bank.csv"
    with open(bank_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "txn_id", "datetime", "from_acct", "to_acct", "amount", "mode", "ifsc", "narration"
        ])
        writer.writeheader()
        writer.writerows(bank_rows)

    # 4. Write bad CDR CSV
    bad_cdr_path = out_dir / "bad_cdr.csv"
    bad_cdr_path.write_text(generate_bad_cdr_content(), encoding="utf-8")

    # 5. Write EXPECTED.txt
    expected_path = out_dir / "EXPECTED.txt"
    expected_path.write_text(EXPECTED_GUIDE_TEXT, encoding="utf-8")

    # Validation check using actual intake validators
    settings = load_settings()

    # Validate FIRs
    fir_errors = []
    for fpath in [fir_a_path, fir_b_path, fir_c_path]:
        try:
            decode_fir(fpath.read_bytes(), settings.max_fir_chars)
        except Exception as exc:
            fir_errors.append(f"{fpath.name}: {exc}")

    # Validate CDR
    cdr_report = validate_cdr(cdr_path.read_bytes(), settings)

    # Validate Bank
    bank_report = validate_bank(bank_path.read_bytes(), settings)

    # Validate Bad CDR (expected to fail)
    bad_cdr_report = validate_cdr(bad_cdr_path.read_bytes(), settings)

    summary = {
        "out_dir": str(out_dir),
        "files": {
            "FIR_A.txt": {"chars": len(FIR_A_TEXT), "lines": len(FIR_A_TEXT.splitlines())},
            "FIR_B.txt": {"chars": len(FIR_B_TEXT), "lines": len(FIR_B_TEXT.splitlines())},
            "FIR_C.txt": {"chars": len(FIR_C_TEXT), "lines": len(FIR_C_TEXT.splitlines())},
            "cdr.csv": {"rows": len(cdr_rows), "valid": cdr_report.ok, "errors": cdr_report.error_count},
            "bank.csv": {"rows": len(bank_rows), "valid": bank_report.ok, "errors": bank_report.error_count},
            "bad_cdr.csv": {"rows": 1, "valid": bad_cdr_report.ok, "expected_rejection": not bad_cdr_report.ok},
            "EXPECTED.txt": {"lines": len(EXPECTED_GUIDE_TEXT.splitlines())},
        },
        "validation_ok": (len(fir_errors) == 0 and cdr_report.ok and bank_report.ok and not bad_cdr_report.ok),
        "fir_errors": fir_errors,
        "cdr_errors": cdr_report.errors[:3],
        "bank_errors": bank_report.errors[:3],
    }

    return summary


def main() -> None:
    """Generate kit in scratch/ and attempt Desktop location."""
    print("Generating live-demo kit...")
    summary = write_kit(SCRATCH_DIR)
    print(f"Kit generated at {SCRATCH_DIR}:")
    for fname, meta in summary["files"].items():
        print(f"  {fname}: {meta}")
    print(f"Intake validation status: {'PASSED' if summary['validation_ok'] else 'FAILED'}")

    # Attempt to copy or create on Desktop if possible
    desktop_success = False
    try:
        DESKTOP_DIR.mkdir(parents=True, exist_ok=True)
        write_kit(DESKTOP_DIR)
        print(f"Copied successfully to {DESKTOP_DIR}")
        desktop_success = True
    except Exception as e:
        print(f"Note: Cannot write directly to {DESKTOP_DIR} ({e}).")
        print(f"Exact path to copy from: {SCRATCH_DIR}")


if __name__ == "__main__":
    main()
