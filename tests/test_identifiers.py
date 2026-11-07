"""
Tests for precedence-based identifier resolution (Step 4b).
"""

from __future__ import annotations

import sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai_pipeline.identifiers import PRECEDENCE, find_all_identifiers
from ai_pipeline.validators import Candidate
from tests.test_validators import generate_verhoeff_check_digit


# ---------------------------------------------------------------------------
# 1. Module-level Precedence Tuple
# ---------------------------------------------------------------------------

def test_precedence_tuple():
    """Verify PRECEDENCE tuple matches the exact sequence specified."""
    assert PRECEDENCE == (
        "UPI",
        "AADHAAR",
        "PAN",
        "IFSC",
        "VEHICLE",
        "IMEI",
        "ACCOUNT",
        "AMOUNT",
        "PHONE",
    )


# ---------------------------------------------------------------------------
# 2. Precedence and Disambiguation Tests
# ---------------------------------------------------------------------------

def test_upi_phone_overlap():
    """'9876543210@paytm' -> UPI only, DROPPED_OVERLAP:PHONE flag, surface is full UPI string."""
    text = "Please transfer the amount to 9876543210@paytm immediately."
    res = find_all_identifiers(text)
    assert len(res) == 1
    c = res[0]
    assert c.type == "UPI"
    assert c.surface == "9876543210@paytm"
    assert c.value == "9876543210@paytm"
    assert "DROPPED_OVERLAP:PHONE" in c.flags


def test_imei_only_not_account():
    """'IMEI 490154203237518' -> IMEI only (not ACCOUNT)."""
    text1 = "Recovered handset with IMEI 490154203237518 from accused."
    res1 = find_all_identifiers(text1)
    assert len(res1) == 1
    assert res1[0].type == "IMEI"
    assert res1[0].value == "490154203237518"

    # Even with account keyword present near IMEI, IMEI has higher precedence
    text2 = "Bank account IMEI 490154203237518 logged."
    res2 = find_all_identifiers(text2)
    assert len(res2) == 1
    assert res2[0].type == "IMEI"
    assert res2[0].value == "490154203237518"
    assert "DROPPED_OVERLAP:ACCOUNT" in res2[0].flags


def test_aadhaar_only_not_account():
    """Verhoeff-valid 12-digit number preceded by 'Aadhaar' -> AADHAAR only (not ACCOUNT)."""
    chk = generate_verhoeff_check_digit("23456789012")
    aadhaar_num = f"23456789012{chk}"
    text1 = f"Accused presented Aadhaar {aadhaar_num} at checkpost."
    res1 = find_all_identifiers(text1)
    assert len(res1) == 1
    assert res1[0].type == "AADHAAR"
    assert res1[0].value == aadhaar_num

    # Even if 'A/c' appears before 'Aadhaar', AADHAAR beats ACCOUNT
    text2 = f"A/c Aadhaar {aadhaar_num} noted."
    res2 = find_all_identifiers(text2)
    assert len(res2) == 1
    assert res2[0].type == "AADHAAR"
    assert res2[0].value == aadhaar_num
    assert "DROPPED_OVERLAP:ACCOUNT" in res2[0].flags


def test_account_only_without_aadhaar():
    """12-digit number preceded by 'A/c' with no Aadhaar keyword -> ACCOUNT only."""
    text = "Account A/c 693103413164 credited with funds."
    res = find_all_identifiers(text)
    assert len(res) == 1
    assert res[0].type == "ACCOUNT"
    assert res[0].value == "693103413164"
    assert res[0].flags == []


def test_alias_with_at_is_empty():
    """'Rajendra Singh @ Raju Bhai' -> empty (neither UPI nor anything else)."""
    text = "Suspect Rajendra Singh @ Raju Bhai fled the spot."
    res = find_all_identifiers(text)
    assert len(res) == 0


def test_invalid_pan_not_extracted():
    """'XABCPE1234FX' -> no PAN."""
    text = "Ref code XABCPE1234FX is an internal token."
    res = find_all_identifiers(text)
    pan_matches = [c for c in res if c.type == "PAN"]
    assert len(pan_matches) == 0


def test_email_not_upi():
    """'ravi@gmail.com' -> no UPI."""
    text = "Send email enquiry to ravi@gmail.com for details."
    res = find_all_identifiers(text)
    upi_matches = [c for c in res if c.type == "UPI"]
    assert len(upi_matches) == 0


def test_phone_next_to_amount_both_found():
    """Phone with +91 and spaces next to an amount 'Rs. 1,57,400/-' -> both found, unchanged, no dropped overlap."""
    text = "Phone +91 98765 43210 sent Rs. 1,57,400/- to merchant."
    res = find_all_identifiers(text)
    assert len(res) == 2
    phone_cand, amount_cand = res[0], res[1]

    assert phone_cand.type == "PHONE"
    assert phone_cand.surface == "+91 98765 43210"
    assert phone_cand.flags == []

    assert amount_cand.type == "AMOUNT"
    assert amount_cand.surface == "Rs. 1,57,400/-"
    assert amount_cand.flags == []


# ---------------------------------------------------------------------------
# 3. Integrated Test (All 9 Types in One Synthetic Paragraph)
# ---------------------------------------------------------------------------

def test_integrated_all_nine_types():
    """Synthetic paragraph containing every one of the 9 types in text order."""
    chk = generate_verhoeff_check_digit("23456789012")
    aadhaar_val = f"23456789012{chk}"

    paragraph = (
        f"Suspect transferred payment to UPI vikas@okhdfcbank after verification. "
        f"His Aadhaar {aadhaar_val} was recorded along with PAN ABCPE1234F. "
        f"The branch IFSC SBIN0001234 was identified for the transaction. "
        f"He arrived in vehicle DL-8C-AB-5198 carrying handset with IMEI 490154203237518. "
        f"The bank account 95217729622 received an amount of Rs. 1,57,400/- directly. "
        f"Contact mobile number is +91 98765 43210."
    )

    expected_types = [
        "UPI",
        "AADHAAR",
        "PAN",
        "IFSC",
        "VEHICLE",
        "IMEI",
        "ACCOUNT",
        "AMOUNT",
        "PHONE",
    ]

    candidates = find_all_identifiers(paragraph)
    assert len(candidates) == 9

    observed_types = [c.type for c in candidates]
    assert observed_types == expected_types

    # Verify spans and surfaces strictly match paragraph
    for c in candidates:
        assert paragraph[c.start:c.end] == c.surface
        assert c.flags == []

    # Verify strictly monotonic start positions
    for i in range(len(candidates) - 1):
        assert candidates[i].end <= candidates[i + 1].start


# ---------------------------------------------------------------------------
# 4. Same Type Tie-Breaking
# ---------------------------------------------------------------------------

def test_same_type_overlap_longer_stays(monkeypatch):
    """If two candidates have the same type, keep the longer."""
    # Construct synthetic text where a custom mock finder produces two overlapping spans of same type
    import ai_pipeline.identifiers as ident_mod

    c_short = Candidate(type="ACCOUNT", value="1111", start=5, end=15, surface="1111111111")
    c_long = Candidate(type="ACCOUNT", value="2222", start=2, end=18, surface="2222222222222222")

    monkeypatch.setattr(ident_mod, "find_accounts", lambda t: [c_short, c_long])
    monkeypatch.setattr(ident_mod, "find_upi", lambda t: [])
    monkeypatch.setattr(ident_mod, "find_aadhaar", lambda t: [])
    monkeypatch.setattr(ident_mod, "find_pan", lambda t: [])
    monkeypatch.setattr(ident_mod, "find_ifsc", lambda t: [])
    monkeypatch.setattr(ident_mod, "find_vehicle_plates", lambda t: [])
    monkeypatch.setattr(ident_mod, "find_imeis", lambda t: [])
    monkeypatch.setattr(ident_mod, "find_amounts", lambda t: [])
    monkeypatch.setattr(ident_mod, "find_phones", lambda t: [])

    res = ident_mod.find_all_identifiers("dummy text for mock")
    assert len(res) == 1
    assert res[0].surface == c_long.surface
    assert "DROPPED_OVERLAP:ACCOUNT" in res[0].flags


def test_same_type_overlap_equal_length_earlier_stays(monkeypatch):
    """If two candidates have the same type and equal length, keep the earlier."""
    import ai_pipeline.identifiers as ident_mod

    c_earlier = Candidate(type="PHONE", value="9876543210", start=2, end=12, surface="9876543210")
    c_later = Candidate(type="PHONE", value="9876543211", start=5, end=15, surface="9876543211")

    monkeypatch.setattr(ident_mod, "find_phones", lambda t: [c_earlier, c_later])
    monkeypatch.setattr(ident_mod, "find_upi", lambda t: [])
    monkeypatch.setattr(ident_mod, "find_aadhaar", lambda t: [])
    monkeypatch.setattr(ident_mod, "find_pan", lambda t: [])
    monkeypatch.setattr(ident_mod, "find_ifsc", lambda t: [])
    monkeypatch.setattr(ident_mod, "find_vehicle_plates", lambda t: [])
    monkeypatch.setattr(ident_mod, "find_imeis", lambda t: [])
    monkeypatch.setattr(ident_mod, "find_accounts", lambda t: [])
    monkeypatch.setattr(ident_mod, "find_amounts", lambda t: [])

    res = ident_mod.find_all_identifiers("dummy text for mock")
    assert len(res) == 1
    assert res[0].surface == c_earlier.surface
    assert "DROPPED_OVERLAP:PHONE" in res[0].flags


# ---------------------------------------------------------------------------
# 5. Property Tests
# ---------------------------------------------------------------------------

SAMPLE_TEXTS = [
    "",
    "   \n\t  ",
    "Plain text without any identifiers mentioned anywhere in this statement.",
    "9876543210@paytm and 9876543210 were both in the logs.",
    "A/c 693103413164 and IFSC SBIN0001234 credited Rs. 50,000/-.",
    "Vehicle DL-8C-AB-5198 chased down phone +91 98765 43210 IMEI 490154203237518.",
]


@pytest.mark.parametrize("txt", SAMPLE_TEXTS)
def test_property_never_overlapping(txt: str):
    """Output never has overlapping candidates (for any text)."""
    res = find_all_identifiers(txt)
    for i in range(len(res) - 1):
        assert res[i].end <= res[i + 1].start, (
            f"Overlap found between [{res[i].start}:{res[i].end}] "
            f"and [{res[i+1].start}:{res[i+1].end}]"
        )


@pytest.mark.parametrize("txt", SAMPLE_TEXTS)
def test_property_always_sorted_by_start(txt: str):
    """Output is always sorted by start position."""
    res = find_all_identifiers(txt)
    for i in range(len(res) - 1):
        assert res[i].start <= res[i + 1].start


@pytest.mark.parametrize("txt", SAMPLE_TEXTS)
def test_property_idempotent_and_deterministic(txt: str):
    """Calling find_all_identifiers twice on the same text returns identical results."""
    run1 = find_all_identifiers(txt)
    run2 = find_all_identifiers(txt)
    assert run1 == run2


@pytest.mark.parametrize("txt", SAMPLE_TEXTS)
def test_property_surface_equals_slice(txt: str):
    """text[start:end] == surface for all candidates in the result."""
    res = find_all_identifiers(txt)
    for c in res:
        assert txt[c.start:c.end] == c.surface

