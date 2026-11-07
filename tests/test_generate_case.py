"""
tests/test_generate_case.py
Pytest suite for the seeded synthetic case generator.
Verifies determinism, Luhn checks, phone formats, kingpin call counts,
bridge courier graph disconnection, burner lifespans, and row counts.
"""

import csv
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
import pytest

# Ensure repository root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.synthetic.generate_case import (
    STRUCTURING_THRESHOLD,
    generate_case,
    luhn_checksum,
)


@pytest.fixture(scope="module")
def generated_case(tmp_path_factory):
    """Generates a standard case with seed=42 and days=30 for testing."""
    out_dir = tmp_path_factory.mktemp("case_test")
    stats = generate_case(seed=42, days=30, out_dir=str(out_dir))
    return {
        "out_dir": out_dir,
        "stats": stats,
        "truth": json.loads((out_dir / "truth.json").read_text(encoding="utf-8")),
        "cdr_rows": list(csv.DictReader((out_dir / "cdr.csv").open(encoding="utf-8"))),
        "bank_rows": list(csv.DictReader((out_dir / "bank.csv").open(encoding="utf-8"))),
    }


def test_determinism_by_seed(tmp_path):
    """Same seed must produce byte-identical truth.json, cdr.csv, and bank.csv."""
    dir1 = tmp_path / "run1"
    dir2 = tmp_path / "run2"

    generate_case(seed=42, days=30, out_dir=str(dir1))
    generate_case(seed=42, days=30, out_dir=str(dir2))

    for fname in ["truth.json", "cdr.csv", "bank.csv"]:
        b1 = (dir1 / fname).read_bytes()
        b2 = (dir2 / fname).read_bytes()
        assert b1 == b2, f"Determinism failure: {fname} is not byte-identical across runs!"


def test_all_imeis_luhn_valid(generated_case):
    """All generated IMEIs in truth metadata and CDR records must be 15 digits and pass Luhn."""
    truth = generated_case["truth"]
    cdr_rows = generated_case["cdr_rows"]

    # Check truth IMEIs
    for imei in truth["imeis"]:
        assert len(imei) == 15, f"IMEI length is not 15: {imei}"
        assert imei.isdigit(), f"IMEI is not digits: {imei}"
        assert luhn_checksum(imei), f"IMEI failed Luhn check: {imei}"

    # Check CDR IMEIs
    for row in cdr_rows:
        imei = row["imei_a"]
        assert len(imei) == 15, f"CDR IMEI length is not 15: {imei}"
        assert luhn_checksum(imei), f"CDR IMEI failed Luhn check: {imei}"


def test_phone_format(generated_case):
    """All phone numbers in truth.json and cdr.csv must be 10 digits starting with 6, 7, 8, or 9."""
    phone_pattern = re.compile(r"^[6-9]\d{9}$")
    truth = generated_case["truth"]
    cdr_rows = generated_case["cdr_rows"]

    for p in truth["phones"]:
        phone = p["phone"]
        assert phone_pattern.match(phone), f"Invalid phone format in truth: {phone}"

    for row in cdr_rows:
        assert phone_pattern.match(row["a_party"]), f"Invalid a_party phone: {row['a_party']}"
        assert phone_pattern.match(row["b_party"]), f"Invalid b_party phone: {row['b_party']}"


def test_kingpin_phone_not_top_by_call_count(generated_case):
    """Kingpin calls rarely; raw call count must NOT rank a kingpin phone first."""
    truth = generated_case["truth"]
    cdr_rows = generated_case["cdr_rows"]

    kp_ids = set(truth["kingpin_ids"])
    kp_phones = set()
    for person in truth["people"]:
        if person["person_id"] in kp_ids:
            for ph in person["phones"]:
                kp_phones.add(ph["phone"])

    # Count call appearances
    call_counts = Counter()
    for row in cdr_rows:
        call_counts[row["a_party"]] += 1
        call_counts[row["b_party"]] += 1

    top_phone, top_count = call_counts.most_common(1)[0]

    # Verify no kingpin phone is the top phone
    for kp_phone in kp_phones:
        kp_count = call_counts[kp_phone]
        assert kp_phone != top_phone, f"Kingpin phone {kp_phone} ranked #1 in calls ({kp_count})!"
        assert kp_count < 100, f"Kingpin phone {kp_phone} had unexpectedly high calls: {kp_count}"


def test_removing_bridge_couriers_disconnects_gang_a_from_b(generated_case):
    """Removing the 2 bridge couriers must completely disconnect Gang A from Gang B in CDR."""
    truth = generated_case["truth"]
    cdr_rows = generated_case["cdr_rows"]

    courier_ids = set(truth.get("bridge_courier_ids", []))
    gang_a_phones = set()
    gang_b_phones = set()
    courier_phones = set()

    for person in truth["people"]:
        phs = {ph["phone"] for ph in person["phones"]}
        if person.get("role") == "BRIDGE_COURIER" or person.get("person_id") in courier_ids:
            courier_phones.update(phs)
        elif person["gang"] == "GANG_A":
            gang_a_phones.update(phs)
        elif person["gang"] == "GANG_B":
            gang_b_phones.update(phs)

    # Include burners into their assigned gangs
    for p in truth["phones"]:
        if p["is_burner"]:
            pid = p["person_id"]
            for person in truth["people"]:
                if person["person_id"] == pid:
                    if person.get("role") != "BRIDGE_COURIER" and person.get("person_id") not in courier_ids:
                        if person["gang"] == "GANG_A":
                            gang_a_phones.add(p["phone"])
                        elif person["gang"] == "GANG_B":
                            gang_b_phones.add(p["phone"])

    assert len(courier_phones) == 2, f"courier_phones must contain 2 couriers' phones, got {len(courier_phones)}: {courier_phones}"

    # Positive control: full call graph including bridge couriers must connect Gang A to Gang B
    adj_full = {}
    for row in cdr_rows:
        a = row["a_party"]
        b = row["b_party"]
        adj_full.setdefault(a, set()).add(b)
        adj_full.setdefault(b, set()).add(a)

    visited_full = set(gang_a_phones)
    queue_full = list(gang_a_phones)
    for node in queue_full:
        for neighbor in adj_full.get(node, []):
            if neighbor not in visited_full:
                visited_full.add(neighbor)
                queue_full.append(neighbor)

    assert len(visited_full.intersection(gang_b_phones)) > 0, (
        "Positive control failed: Gang A cannot reach Gang B even with bridge couriers included"
    )

    # Negative control: call graph excluding bridge couriers must disconnect Gang A from Gang B
    adj_isolated = {}
    for row in cdr_rows:
        a = row["a_party"]
        b = row["b_party"]
        if a in courier_phones or b in courier_phones:
            continue
        adj_isolated.setdefault(a, set()).add(b)
        adj_isolated.setdefault(b, set()).add(a)

    visited_isolated = set(gang_a_phones)
    queue_isolated = list(gang_a_phones)
    for node in queue_isolated:
        for neighbor in adj_isolated.get(node, []):
            if neighbor not in visited_isolated:
                visited_isolated.add(neighbor)
                queue_isolated.append(neighbor)

    cross_gang_overlap = visited_isolated.intersection(gang_b_phones)
    assert len(cross_gang_overlap) == 0, (
        f"Gang A is still connected to Gang B without couriers via: {cross_gang_overlap}"
    )


def test_burner_life_3_to_8_days(generated_case):
    """Each burner phone must be active for 3-8 days and call only 1-2 numbers."""
    truth = generated_case["truth"]
    cdr_rows = generated_case["cdr_rows"]
    burner_phones = truth["burner_phones"]

    assert len(burner_phones) == 4, f"Expected 4 burner phones, got {len(burner_phones)}"

    for b_phone in burner_phones:
        b_calls = [
            row for row in cdr_rows
            if row["a_party"] == b_phone or row["b_party"] == b_phone
        ]
        assert len(b_calls) > 0, f"Burner phone {b_phone} has no calls in CDR!"

        timestamps = [datetime.fromisoformat(r["start_time"]) for r in b_calls]
        min_dt = min(timestamps)
        max_dt = max(timestamps)
        span_days = (max_dt - min_dt).total_seconds() / 86400.0

        # Lifespan must be between 3 and 8 days (span_days >= 2.0 calendar difference)
        assert 2.0 <= span_days <= 8.0, (
            f"Burner {b_phone} active span {span_days:.2f} days is outside 3-8 day range!"
        )

        # Check unique call partners (only 1-2 numbers)
        partners = set()
        for r in b_calls:
            partner = r["b_party"] if r["a_party"] == b_phone else r["a_party"]
            partners.add(partner)
        assert 1 <= len(partners) <= 2, (
            f"Burner {b_phone} called {len(partners)} numbers (expected 1-2): {partners}"
        )


def test_row_counts_within_range(generated_case):
    """Row counts for the CDR and bank files must fall within the bounds asserted in this test."""
    cdr_count = len(generated_case["cdr_rows"])
    bank_count = len(generated_case["bank_rows"])

    assert 7000 <= cdr_count <= 9000, f"CDR row count {cdr_count} not in ~8000 range [7000, 9000]"
    assert 1300 <= bank_count <= 1700, f"Bank row count {bank_count} not in ~1500 range [1300, 1700]"


def test_mule_accounts_and_structuring(generated_case):
    """4 mule accounts with deposits just under STRUCTURING_THRESHOLD (50000) and 1 dormant 15+ days."""
    truth = generated_case["truth"]
    bank_rows = generated_case["bank_rows"]
    mule_accounts = set(truth["mule_accounts"])

    assert len(mule_accounts) == 4, f"Expected 4 mule accounts, found {len(mule_accounts)}"

    # Check deposits just under 50000 into mule accounts
    structured_deposits = [
        r for r in bank_rows
        if r["to_acct"] in mule_accounts and 45000 <= float(r["amount"]) < STRUCTURING_THRESHOLD
    ]
    assert len(structured_deposits) >= 10, (
        f"Found only {len(structured_deposits)} structured deposits under {STRUCTURING_THRESHOLD}"
    )

    # Check for at least one dormant mule for 15+ days
    mule_first_dates = {}
    for m in mule_accounts:
        m_txns = [r for r in bank_rows if r["to_acct"] == m or r["from_acct"] == m]
        assert len(m_txns) > 0, f"Mule account {m} has no transactions!"
        first_dt = min(datetime.fromisoformat(r["datetime"]) for r in m_txns)
        mule_first_dates[m] = first_dt

    # Base date is 2026-01-01, 15+ days dormant means first txn on or after day 16 (2026-01-16)
    dormant_found = any(dt.day >= 16 for dt in mule_first_dates.values())
    assert dormant_found, f"No mule account was dormant for 15+ days! First dates: {mule_first_dates}"


def test_decoys_metadata(generated_case):
    """Verifies presence and correctness of all decoy elements in truth.json."""
    decoys = generated_case["truth"]["decoys"]

    # 1. Pizza shop
    assert "pizza_shop_number" in decoys
    assert len(decoys["pizza_shop_number"]) == 10

    # 2. Similar names (Vikas / Bikas)
    sim_names = decoys["similar_names"]
    assert len(sim_names) == 2
    names = [s["name"] for s in sim_names]
    assert any("Vikas" in n for n in names)
    assert any("Bikas" in n for n in names)

    # 3. Person with 3 aliases
    p3 = decoys["person_with_3_aliases"]
    assert len(p3["aliases"]) == 3

    # 4. Shared handset IMEI
    shared = decoys["shared_handset_imei"]
    assert len(shared["shared_by"]) == 2
    assert luhn_checksum(shared["imei"])


def test_pizza_shop_at_least_20_distinct_contacts(generated_case):
    """Pizza shop must have at least 20 distinct contacts (customers + operatives)."""
    truth = generated_case["truth"]
    cdr_rows = generated_case["cdr_rows"]
    pizza_phone = truth["decoys"]["pizza_shop_number"]

    contacts = set()
    for row in cdr_rows:
        if row["a_party"] == pizza_phone:
            contacts.add(row["b_party"])
        elif row["b_party"] == pizza_phone:
            contacts.add(row["a_party"])

    assert len(contacts) >= 20, f"Expected at least 20 distinct contacts, got {len(contacts)}"


def test_pizza_shop_is_top_3_by_call_count(generated_case):
    """Pizza shop must rank in the top 3 phones by call count, and both kingpins in the bottom 3."""
    truth = generated_case["truth"]
    cdr_rows = generated_case["cdr_rows"]
    pizza_phone = truth["decoys"]["pizza_shop_number"]

    call_counts = Counter()
    for row in cdr_rows:
        call_counts[row["a_party"]] += 1
        call_counts[row["b_party"]] += 1

    ranked_phones = [p for p, _ in call_counts.most_common()]
    pizza_rank = ranked_phones.index(pizza_phone) + 1
    assert pizza_rank <= 3, f"Pizza shop rank was #{pizza_rank}, expected top 3!"

    # Verify both kingpins are in the bottom 3
    kp_ids = set(truth["kingpin_ids"])
    kp_phones = {
        ph["phone"]
        for p in truth["people"]
        if p["person_id"] in kp_ids
        for ph in p["phones"]
    }
    bottom_3 = set(ranked_phones[-3:])
    for kp_ph in kp_phones:
        assert kp_ph in bottom_3, f"Kingpin phone {kp_ph} was not in bottom 3: rank #{ranked_phones.index(kp_ph) + 1} of {len(ranked_phones)}"


def test_pizza_shop_no_contact_with_both_gangs(generated_case):
    """Pizza shop must never be linked to members of both gangs (at most 3 operatives from ONE gang)."""
    truth = generated_case["truth"]
    cdr_rows = generated_case["cdr_rows"]
    pizza_phone = truth["decoys"]["pizza_shop_number"]

    contacts = set()
    for row in cdr_rows:
        if row["a_party"] == pizza_phone:
            contacts.add(row["b_party"])
        elif row["b_party"] == pizza_phone:
            contacts.add(row["a_party"])

    gang_a_phones = {ph["phone"] for p in truth["people"] if p.get("gang") == "GANG_A" for ph in p["phones"]}
    gang_b_phones = {ph["phone"] for p in truth["people"] if p.get("gang") == "GANG_B" for ph in p["phones"]}

    has_gang_a = len(contacts.intersection(gang_a_phones)) > 0
    has_gang_b = len(contacts.intersection(gang_b_phones)) > 0

    assert not (has_gang_a and has_gang_b), "Pizza shop must not have contact with both gangs!"
    # Ensure at most 3 operatives from the contacted gang
    if has_gang_a:
        assert len(contacts.intersection(gang_a_phones)) <= 3
    if has_gang_b:
        assert len(contacts.intersection(gang_b_phones)) <= 3


def test_ifsc_format_in_truth_and_bank(generated_case):
    """Every IFSC in truth.json and bank.csv matches ^[A-Z]{4}0[A-Z0-9]{6}$."""
    pattern = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
    truth = generated_case["truth"]
    bank_rows = generated_case["bank_rows"]

    for acct in truth["accounts"]:
        ifsc = acct["ifsc"]
        assert pattern.match(ifsc), f"Invalid IFSC in truth.json accounts: {ifsc}"

    for person in truth["people"]:
        for acct in person.get("accounts", []):
            ifsc = acct["ifsc"]
            assert pattern.match(ifsc), f"Invalid IFSC in truth.json person {person['person_id']}: {ifsc}"

    assert len(bank_rows) > 0
    for row in bank_rows:
        ifsc = row["ifsc"]
        assert pattern.match(ifsc), f"Invalid IFSC in bank.csv row {row['txn_id']}: {ifsc}"


def test_ifsc_prefix_matches_bank(generated_case):
    """IFSC prefix matches the bank (SBIN for SBI, ICIC for ICICI, HDFC for HDFC, PUNB for PNB)."""
    expected_prefixes = {
        "SBI": "SBIN",
        "ICICI": "ICIC",
        "HDFC": "HDFC",
        "PNB": "PUNB",
    }
    truth = generated_case["truth"]

    for acct in truth["accounts"]:
        bank = acct["bank"]
        ifsc = acct["ifsc"]
        assert bank in expected_prefixes, f"Unknown bank: {bank}"
        prefix = expected_prefixes[bank]
        assert ifsc.startswith(prefix), f"IFSC {ifsc} does not start with {prefix} for bank {bank}"
        assert ifsc[4] == "0", f"IFSC {ifsc} does not have '0' at 5th character"

    for person in truth["people"]:
        for acct in person.get("accounts", []):
            bank = acct["bank"]
            ifsc = acct["ifsc"]
            prefix = expected_prefixes[bank]
            assert ifsc.startswith(prefix), f"Person {person['person_id']} IFSC {ifsc} does not start with {prefix} for bank {bank}"


def test_account_length_matches_bank(generated_case):
    """Account length matches the bank: SBI 11 digits, ICICI 12, HDFC 14, PNB 16. Digits only."""
    expected_lengths = {
        "SBI": 11,
        "ICICI": 12,
        "HDFC": 14,
        "PNB": 16,
    }
    truth = generated_case["truth"]

    for acct in truth["accounts"]:
        bank = acct["bank"]
        num = acct["account_number"]
        assert bank in expected_lengths, f"Unknown bank: {bank}"
        assert len(num) == expected_lengths[bank], (
            f"Account {num} length {len(num)} does not match bank {bank} expected length {expected_lengths[bank]}"
        )
        assert num.isdigit(), f"Account {num} contains non-digits"

    for person in truth["people"]:
        for acct in person.get("accounts", []):
            bank = acct["bank"]
            num = acct["account_number"]
            assert len(num) == expected_lengths[bank], (
                f"Person {person['person_id']} account {num} length {len(num)} != {expected_lengths[bank]}"
            )
            assert num.isdigit(), f"Person {person['person_id']} account {num} contains non-digits"


def test_no_account_has_10_or_15_digits(generated_case):
    """No account may have 10 or 15 digits (to prevent confusion with phone number or IMEI)."""
    truth = generated_case["truth"]
    bank_rows = generated_case["bank_rows"]

    for acct in truth["accounts"]:
        num = acct["account_number"]
        assert len(num) != 10, f"Account {num} has 10 digits"
        assert len(num) != 15, f"Account {num} has 15 digits"

    for row in bank_rows:
        for field in ["from_acct", "to_acct"]:
            num = row[field]
            assert len(num) != 10, f"Bank row {row['txn_id']} {field} {num} has 10 digits"
            assert len(num) != 15, f"Bank row {row['txn_id']} {field} {num} has 15 digits"


def test_bank_csv_ifsc_equals_receiving_account_ifsc(generated_case):
    """In bank.csv the ifsc column is the IFSC of the RECEIVING account (to_acct)."""
    truth = generated_case["truth"]
    bank_rows = generated_case["bank_rows"]

    truth_accts = {a["account_number"]: a for a in truth["accounts"]}

    for row in bank_rows:
        to_acct = row["to_acct"]
        if to_acct in truth_accts:
            expected_ifsc = truth_accts[to_acct]["ifsc"]
            assert row["ifsc"] == expected_ifsc, (
                f"Txn {row['txn_id']}: bank.csv ifsc {row['ifsc']} != receiving account truth IFSC {expected_ifsc}"
            )
            bank = truth_accts[to_acct]["bank"]
            prefix = {"SBI": "SBIN", "ICICI": "ICIC", "HDFC": "HDFC", "PNB": "PUNB"}[bank]
            assert row["ifsc"].startswith(prefix)


def test_no_account_number_equals_any_phone_or_imei(generated_case):
    """No account number equals any phone number or IMEI value."""
    truth = generated_case["truth"]
    cdr_rows = generated_case["cdr_rows"]
    bank_rows = generated_case["bank_rows"]

    all_phones = {p["phone"] for p in truth["phones"]}
    for row in cdr_rows:
        all_phones.add(row["a_party"])
        all_phones.add(row["b_party"])

    all_imeis = set(truth["imeis"])
    for row in cdr_rows:
        all_imeis.add(row["imei_a"])

    # Check truth accounts
    for acct in truth["accounts"]:
        num = acct["account_number"]
        assert num not in all_phones, f"Account number {num} matches a phone number!"
        assert num not in all_imeis, f"Account number {num} matches an IMEI!"

    # Check bank accounts
    for row in bank_rows:
        for field in ["from_acct", "to_acct"]:
            num = row[field]
            assert num not in all_phones, f"Bank row {row['txn_id']} {field} {num} matches a phone number!"
            assert num not in all_imeis, f"Bank row {row['txn_id']} {field} {num} matches an IMEI!"



