"""
Tests for Indian identifier finders and checksum validators (ai_pipeline/validators.py).
"""

from __future__ import annotations

import sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai_pipeline.validators import (
    Candidate,
    find_aadhaar,
    find_accounts,
    find_amounts,
    find_ifsc,
    find_imeis,
    find_pan,
    find_phones,
    find_upi,
    find_vehicle_plates,
    luhn_valid,
    mask_aadhaar,
    verhoeff_valid,
)


# ---------------------------------------------------------------------------
# Independent Verhoeff Generator for Tests
# ---------------------------------------------------------------------------

_TEST_VERHOEFF_D = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
    [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
    [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
    [4, 0, 1, 2, 3, 9, 5, 6, 7, 8],
    [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
    [6, 5, 9, 8, 7, 1, 0, 4, 3, 2],
    [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
    [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
    [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
]

_TEST_VERHOEFF_P = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
    [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
    [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
    [9, 4, 5, 3, 1, 2, 6, 8, 7, 0],
    [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5],
    [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
]

_TEST_VERHOEFF_INV = [0, 4, 3, 2, 1, 5, 6, 7, 8, 9]


def generate_verhoeff_check_digit(num_str: str) -> int:
    """Generate Verhoeff check digit independently inside test suite."""
    c = 0
    digits = [int(x) for x in reversed(num_str)]
    for i, item in enumerate(digits):
        c = _TEST_VERHOEFF_D[c][_TEST_VERHOEFF_P[(i + 1) % 8][item]]
    return _TEST_VERHOEFF_INV[c]


# ---------------------------------------------------------------------------
# 1. Helpers & Checksums Tests
# ---------------------------------------------------------------------------

def test_verhoeff_classic_example_and_generator():
    """Verify classic example '236' -> check digit 3 and generated vectors."""
    assert generate_verhoeff_check_digit("236") == 3
    assert verhoeff_valid("2363") is True
    assert verhoeff_valid("2364") is False

    test_numbers = ["12345", "987654321", "23456789012", "76543210987", "90123456789"]
    for num in test_numbers:
        chk = generate_verhoeff_check_digit(num)
        valid_full = f"{num}{chk}"
        assert verhoeff_valid(valid_full) is True
        invalid_full = f"{num}{(chk + 1) % 10}"
        assert verhoeff_valid(invalid_full) is False


def test_luhn_imei_checksums():
    """Verify known-valid IMEI 490154203237518 and invalid variant."""
    valid_imei = "490154203237518"
    assert luhn_valid(valid_imei) is True

    # One-digit-changed invalid IMEI
    invalid_imei = "490154203237519"
    assert luhn_valid(invalid_imei) is False


def test_mask_aadhaar():
    """Verify Aadhaar masking leaves only the last 4 digits visible."""
    assert mask_aadhaar("234567890124") == "XXXXXXXX0124"
    assert mask_aadhaar("2345 6789 0124") == "XXXX XXXX 0124"
    assert mask_aadhaar("2345-6789-0124") == "XXXX-XXXX-0124"
    assert mask_aadhaar("123") == "123"  # invalid length untouched


# ---------------------------------------------------------------------------
# 2. find_phones Tests (>= 8 valid, >= 8 invalid)
# ---------------------------------------------------------------------------

PHONE_VALID_CASES = [
    ("9876543210", "9876543210"),
    ("8765432109", "8765432109"),
    ("7654321098", "7654321098"),
    ("6543210987", "6543210987"),
    ("98765 43210", "9876543210"),
    ("+91 98765 43210", "9876543210"),
    ("+91-98765-43210", "9876543210"),
    ("09876543210", "9876543210"),
    ("+91-6647468723", "6647468723"),
    ("९८७६५४३२१०", "9876543210"),
]

PHONE_INVALID_CASES = [
    "1234567890",  # Starts with 1
    "5432109876",  # Starts with 5
    "987654321",   # 9 digits
    "98765432109", # 11 digits without prefix
    "490154203237518",   # 15-digit IMEI: phone must NOT be found inside
    "123456789012",      # 12-digit number: phone must NOT be found inside
    "1234567890123456",  # 16-digit account: phone must NOT be found inside
    "98765A43210",       # Contains letters
    "++919876543210",    # Malformed prefix
]


@pytest.mark.parametrize("inp,expected_val", PHONE_VALID_CASES)
def test_find_phones_valid(inp: str, expected_val: str):
    res = find_phones(inp)
    assert len(res) == 1
    assert res[0].value == expected_val
    assert res[0].surface == inp
    assert res[0].start == 0
    assert res[0].end == len(inp)
    assert res[0].valid is True


@pytest.mark.parametrize("inp", PHONE_INVALID_CASES)
def test_find_phones_invalid(inp: str):
    res = find_phones(inp)
    assert len(res) == 0, f"Expected 0 phones in {inp}, got {res}"


def test_phone_not_found_inside_longer_digit_runs():
    """Specific check: phone is never found inside 15-digit IMEI, 12-digit number or 16-digit account."""
    text = (
        "Subject used IMEI 490154203237518 with Aadhaar 234567890124 "
        "and account 6869261796405377 during transfer."
    )
    phones = find_phones(text)
    assert len(phones) == 0, f"Found unintended phones inside longer digit runs: {phones}"


# ---------------------------------------------------------------------------
# 3. find_imeis Tests (>= 8 valid, >= 8 invalid)
# ---------------------------------------------------------------------------

IMEI_VALID_CASES = [
    "490154203237518",
    "490154203237526",
    "490154203237534",
    "490154203237542",
    "490154203237559",
    "490154203237567",
    "490154203237575",
    "४९०१५४२०३२३७५१८",
]

IMEI_INVALID_CASES = [
    ("490154203237519", True),   # 15 digits, bad checksum -> returned with CHECKSUM_INVALID
    ("864201948201940", True),   # 15 digits, bad checksum
    ("12345678901234", False),   # 14 digits -> not an IMEI
    ("1234567890123456", False), # 16 digits -> not an IMEI
    ("86420194820194A", False),  # Contains letter
    ("86420 1948201948", False), # Contains space
    ("12345", False),            # Too short
    ("86420194820194", False),   # 14 digits
]


@pytest.mark.parametrize("inp", IMEI_VALID_CASES)
def test_find_imeis_valid(inp: str):
    res = find_imeis(inp)
    assert len(res) == 1
    assert res[0].surface == inp
    assert res[0].valid is True
    assert res[0].flags == []


@pytest.mark.parametrize("inp,has_checksum_flag", IMEI_INVALID_CASES)
def test_find_imeis_invalid(inp: str, has_checksum_flag: bool):
    res = find_imeis(inp)
    if has_checksum_flag:
        assert len(res) == 1
        assert res[0].valid is False
        assert "CHECKSUM_INVALID" in res[0].flags
    else:
        assert len(res) == 0


# ---------------------------------------------------------------------------
# 4. find_aadhaar Tests (>= 8 valid, >= 8 invalid)
# ---------------------------------------------------------------------------

AADHAAR_VALID_CASES = [
    "Aadhaar card: 234567890124",
    "Aadhar number 345678901238",
    "UID: 456789012341",
    "आधार कार्ड 567890123458",
    "2345 6789 0124",   # 4-4-4 grouped + valid Verhoeff without context
    "3456-7890-1238",   # 4-4-4 hyphen grouped + valid Verhoeff without context
    "4567 8901 2341",
    "5678 9012 3458",
]

AADHAAR_INVALID_CASES = [
    "234567890124",                 # Bare 12 digits without context -> NOT returned
    "123456789012",                 # Starts with 1
    "012345678901",                 # Starts with 0
    "Account 693103413164 credited", # 12-digit bank account without Aadhaar context -> NOT returned
    "2345 6789 0125",               # 4-4-4 grouped but INVALID Verhoeff and no context -> NOT returned
    "Aadhaar: 23456789012",         # 11 digits
    "Aadhaar: 2345678901234",       # 13 digits
    "Aadhaar: 2345 6789 012",       # Incomplete grouping
]


@pytest.mark.parametrize("inp", AADHAAR_VALID_CASES)
def test_find_aadhaar_valid(inp: str):
    res = find_aadhaar(inp)
    assert len(res) == 1
    assert res[0].valid is True
    assert res[0].flags == []


@pytest.mark.parametrize("inp", AADHAAR_INVALID_CASES)
def test_find_aadhaar_invalid(inp: str):
    res = find_aadhaar(inp)
    assert len(res) == 0


# ---------------------------------------------------------------------------
# 5. find_pan Tests (>= 8 valid, >= 8 invalid)
# ---------------------------------------------------------------------------

PAN_VALID_CASES = [
    "ABCPE1234F",  # P = Individual
    "ABCCE1234F",  # C = Company
    "ABCHE1234F",  # H = HUF
    "ABCFE1234F",  # F = Firm
    "ABCAT1234F",  # A = AOP
    "ABCTP1234F",  # T = Trust
    "ABCBA1234F",  # B = BOI
    "ABCLP1234F",  # L = Local Authority
]

PAN_INVALID_CASES = [
    ("ABCZE1234F", True),   # 4th letter 'Z' invalid holder -> BAD_HOLDER_TYPE
    ("ABCDX1234F", True),   # 4th letter 'D' invalid holder -> BAD_HOLDER_TYPE
    ("ABCDE123F", False),   # 3 digits
    ("ABCDE12345", False),  # Ends in digit
    ("12345ABCDE", False),  # Numbers first
    ("ABCD1234F", False),   # 4 letters prefix
    ("ABCDEF1234F", False), # 6 letters prefix
    ("ABCDE12345F", False), # 5 digits
]


@pytest.mark.parametrize("inp", PAN_VALID_CASES)
def test_find_pan_valid(inp: str):
    res = find_pan(inp)
    assert len(res) == 1
    assert res[0].value == inp
    assert res[0].valid is True
    assert res[0].flags == []


@pytest.mark.parametrize("inp,has_bad_holder_flag", PAN_INVALID_CASES)
def test_find_pan_invalid(inp: str, has_bad_holder_flag: bool):
    res = find_pan(inp)
    if has_bad_holder_flag:
        assert len(res) == 1
        assert res[0].valid is False
        assert "BAD_HOLDER_TYPE" in res[0].flags
    else:
        assert len(res) == 0


# ---------------------------------------------------------------------------
# 6. find_ifsc Tests (>= 8 valid, >= 8 invalid)
# ---------------------------------------------------------------------------

IFSC_VALID_CASES = [
    "SBIN0001234",
    "HDFC0002345",
    "ICIC0003456",
    "PUNB0004567",
    "UTIB0005678",
    "BARB0006789",
    "KKBK0007890",
    "YESB0008901",
]

IFSC_INVALID_CASES = [
    "SBIN1001234",   # 5th char not '0'
    "SBI0001234",    # 3 letters prefix
    "SBINO001234",   # 5 letters prefix
    "SBIN000123",    # 10 chars
    "SBIN00012345",  # 12 chars
    "12340001234",   # starts with digits
    "SBIN000123$",   # contains symbol
    "SBIN 0001234",  # contains space
]


@pytest.mark.parametrize("inp", IFSC_VALID_CASES)
def test_find_ifsc_valid(inp: str):
    res = find_ifsc(inp)
    assert len(res) == 1
    assert res[0].value == inp
    assert res[0].valid is True


@pytest.mark.parametrize("inp", IFSC_INVALID_CASES)
def test_find_ifsc_invalid(inp: str):
    res = find_ifsc(inp)
    assert len(res) == 0


# ---------------------------------------------------------------------------
# 7. find_upi Tests (>= 8 valid, >= 8 invalid)
# ---------------------------------------------------------------------------

UPI_VALID_CASES = [
    "ravi@okhdfcbank",
    "9876543210@paytm",
    "user.name@okaxis",
    "merchant_store@icici",
    "amit-kumar@ybl",
    "payment123@sbi",
    "shop@apl",
    "rajesh@barodampay",
]

UPI_INVALID_CASES = [
    "ravi@gmail.com",               # Email with dot in domain
    "Rajendra Singh @ Raju Bhai",   # Spaces around @
    "someone@company.co.in",        # Email with multiple dots
    "@okhdfcbank",                  # Missing handle
    "ravi@",                        # Missing domain
    "ravi @okhdfcbank",             # Space before @
    "ravi@ okhdfcbank",             # Space after @
    "user@domain.org",              # Email
]


@pytest.mark.parametrize("inp", UPI_VALID_CASES)
def test_find_upi_valid(inp: str):
    res = find_upi(inp)
    assert len(res) == 1
    assert res[0].value == inp
    assert res[0].valid is True


@pytest.mark.parametrize("inp", UPI_INVALID_CASES)
def test_find_upi_invalid(inp: str):
    res = find_upi(inp)
    assert len(res) == 0


# ---------------------------------------------------------------------------
# 8. find_vehicle_plates Tests (>= 8 valid, >= 8 invalid)
# ---------------------------------------------------------------------------

VEHICLE_VALID_CASES = [
    ("MH12AB1234", "MH12AB1234"),
    ("MH 12 AB 1234", "MH12AB1234"),
    ("MH-12-AB-1234", "MH12AB1234"),
    ("DL-8C-AB-5198", "DL8CAB5198"),
    ("KA01AB1234", "KA01AB1234"),
    ("UP32CD5678", "UP32CD5678"),
    ("HR26DQ1111", "HR26DQ1111"),
    ("GJ01EF9999", "GJ01EF9999"),
]

VEHICLE_INVALID_CASES = [
    ("XX12AB1234", True),   # Unknown state -> UNKNOWN_STATE flag
    ("ZZ01CD5678", True),   # Unknown state -> UNKNOWN_STATE flag
    ("MH123AB1234", False), # 3 digits district code
    ("M12AB1234", False),   # 1 letter state code
    ("MH12ABCD1234", False),# 4 letters series
    ("MH12AB12345", False), # 5 digits number
    ("12MHAB1234", False),  # Numbers first
    ("MH 12 AB", False),    # Incomplete plate
]


@pytest.mark.parametrize("inp,expected_val", VEHICLE_VALID_CASES)
def test_find_vehicle_plates_valid(inp: str, expected_val: str):
    res = find_vehicle_plates(inp)
    assert len(res) == 1
    assert res[0].value == expected_val
    assert res[0].valid is True
    assert res[0].flags == []


@pytest.mark.parametrize("inp,has_unknown_state", VEHICLE_INVALID_CASES)
def test_find_vehicle_plates_invalid(inp: str, has_unknown_state: bool):
    res = find_vehicle_plates(inp)
    if has_unknown_state:
        assert len(res) == 1
        assert res[0].valid is False
        assert "UNKNOWN_STATE" in res[0].flags
    else:
        assert len(res) == 0


# ---------------------------------------------------------------------------
# 9. find_amounts Tests (>= 8 valid, >= 8 invalid)
# ---------------------------------------------------------------------------

AMOUNT_KNOWN_PAIRS = [
    ("1,57,400", 157400.0),
    ("Rs. 1,57,400/-", 157400.0),
    ("INR 1,57,400.00", 157400.0),
    ("INR 5,00,000.00", 500000.0),
    ("Rs. 25,628/-", 25628.0),
    ("1.5 lakh", 150000.0),
    ("2 lakh", 200000.0),
    ("Rs. 73,500/-", 73500.0),
    ("₹5,00,000", 500000.0),
    ("Rupees 5,00,000", 500000.0),
    ("रु. 25,000", 25000.0),
    ("५ लाख", 500000.0),
]

AMOUNT_INVALID_CASES = [
    "157400",          # Digit run without commas
    "500000",          # Digit run without commas
    "25628",           # Digit run without commas
    "9876543210",      # Phone digits
    "864201948201948", # IMEI digits
    "30291827465",     # Account digits
    "INR",             # Currency without number
    "Rs.",             # Currency without number
]


@pytest.mark.parametrize("inp,expected_val", AMOUNT_KNOWN_PAIRS)
def test_find_amounts_valid_pairs(inp: str, expected_val: float):
    res = find_amounts(inp)
    assert len(res) == 1
    assert res[0].value == expected_val
    assert res[0].surface == inp


@pytest.mark.parametrize("inp", AMOUNT_INVALID_CASES)
def test_find_amounts_invalid(inp: str):
    res = find_amounts(inp)
    assert len(res) == 0, f"Bare digit run or token {inp} should not match as amount, got {res}"


# ---------------------------------------------------------------------------
# 10. find_accounts Tests (>= 8 valid, >= 8 invalid)
# ---------------------------------------------------------------------------

ACCOUNT_VALID_CASES = [
    ("Account 30291827465", "30291827465"),
    ("SBI A/c 693103413164", "693103413164"),
    ("HDFC acct 12345678901234", "12345678901234"),
    ("PNB account 1234567890123456", "1234567890123456"),
    ("khata no 95217729622", "95217729622"),
    ("खाता संख्या 12345678901", "12345678901"),
    ("ICICI Bank 693103413164", "693103413164"),
    ("Axis account 912345678901", "912345678901"),
]

ACCOUNT_INVALID_CASES = [
    "30291827465",                   # Bare 11 digits without context -> NOT matched
    "95217729622",                   # Bare 11 digits without context -> NOT matched
    "Phone 9876543210",              # Phone context
    "IMEI: 864201948201948",         # IMEI context
    "Account 12345",                 # 5 digits (min 9)
    "Account 1234567890123456789",   # 19 digits (max 18)
    "Some random text with account", # No digits
    "A/C with no numbers",           # No digits
]


@pytest.mark.parametrize("inp,expected_val", ACCOUNT_VALID_CASES)
def test_find_accounts_valid(inp: str, expected_val: str):
    res = find_accounts(inp)
    assert len(res) == 1
    assert res[0].value == expected_val


@pytest.mark.parametrize("inp", ACCOUNT_INVALID_CASES)
def test_find_accounts_invalid(inp: str):
    res = find_accounts(inp)
    assert len(res) == 0


# ---------------------------------------------------------------------------
# 11. Property Test: Embed Each Valid Value in a Sentence
# ---------------------------------------------------------------------------

def test_embed_valid_values_property():
    """Property test: embed each valid value in a sentence and require the exact span back."""
    sentence_templates = [
        ("The suspect provided {} during questioning.", "during questioning."),
        ("Investigation revealed {} at the scene.", "at the scene."),
        ("Recovered item was {} as documented.", "as documented."),
    ]

    chk = generate_verhoeff_check_digit("23456789012")
    items_to_test = [
        (find_phones, "+91-98765-43210"),
        (find_imeis, "490154203237518"),
        (find_pan, "ABCPE1234F"),
        (find_ifsc, "SBIN0001234"),
        (find_upi, "ravi@okhdfcbank"),
        (find_vehicle_plates, "DL-8C-AB-5198"),
        (find_amounts, "Rs. 1,57,400/-"),
        (find_accounts, "Account 30291827465"),
        (find_aadhaar, f"Aadhaar 23456789012{chk}"),
    ]

    for finder_fn, val in items_to_test:
        for prefix_tmpl, suffix in sentence_templates:
            prefix = prefix_tmpl.split("{}")[0]
            sentence = f"{prefix}{val} {suffix}"
            expected_start = len(prefix)
            # For account and aadhaar, finders span only the digits
            if finder_fn in (find_accounts, find_aadhaar):
                digits_only = val.split()[-1]
                expected_start = sentence.find(digits_only)
                expected_end = expected_start + len(digits_only)
                expected_surface = digits_only
            else:
                expected_end = expected_start + len(val)
                expected_surface = val

            candidates = finder_fn(sentence)
            assert len(candidates) >= 1, f"Failed to extract {val} from {sentence}"
            matching = [c for c in candidates if c.start == expected_start and c.end == expected_end]
            assert matching, f"Exact span [{expected_start}:{expected_end}] not found for {val} in '{sentence}'"
            c = matching[0]
            assert c.surface == expected_surface
            assert sentence[c.start:c.end] == c.surface
