"""
Indian identifier finders, checksum validators, and extraction dataclasses.
Provides span-preserving extractors for Indian mobiles, IMEIs, Aadhaar, PAN,
IFSC, UPI, vehicle registration plates, amounts, and bank accounts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any

from ai_pipeline.normalizer import normalize_text


@dataclass
class Candidate:
    """Represents an extracted identifier candidate."""

    type: str
    value: Any
    start: int
    end: int
    surface: str
    valid: bool = True
    flags: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Checksum & Masking Helpers
# ---------------------------------------------------------------------------

def luhn_valid(s: str) -> bool:
    """Verify Luhn (mod-10) checksum for a digit string."""
    digits = [int(c) for c in s if c.isdigit()]
    if not digits:
        return False
    checksum = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d = d * 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


_VERHOEFF_D = [
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

_VERHOEFF_P = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
    [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
    [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
    [9, 4, 5, 3, 1, 2, 6, 8, 7, 0],
    [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5],
    [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
]

_VERHOEFF_INV = [0, 4, 3, 2, 1, 5, 6, 7, 8, 9]


def verhoeff_valid(s: str) -> bool:
    """Verify Verhoeff checksum algorithm for a digit string."""
    digits = [int(c) for c in s if c.isdigit()]
    if not digits:
        return False
    c = 0
    for i, item in enumerate(reversed(digits)):
        c = _VERHOEFF_D[c][_VERHOEFF_P[i % 8][item]]
    return c == 0


def mask_aadhaar(value: str) -> str:
    """
    Mask the first 8 digits of an Aadhaar number with 'X', preserving last 4 digits
    and formatting delimiters.
    """
    digits = [c for c in value if c.isdigit()]
    if len(digits) != 12:
        return value

    digit_idx = 0
    res: list[str] = []
    for c in value:
        if c.isdigit():
            if digit_idx < 8:
                res.append("X")
            else:
                res.append(c)
            digit_idx += 1
        else:
            res.append(c)
    return "".join(res)


# ---------------------------------------------------------------------------
# State and Union Territory Codes
# ---------------------------------------------------------------------------

INDIAN_STATE_UT_CODES: set[str] = {
    "AN", "AP", "AR", "AS", "BR", "CH", "CG", "DD", "DL", "DN",
    "GA", "GJ", "HP", "HR", "JH", "JK", "KA", "KL", "LA", "LD",
    "MH", "ML", "MN", "MP", "MZ", "NL", "OD", "OR", "PB", "PY",
    "RJ", "SK", "TN", "TR", "TS", "UA", "UK", "UP", "WB",
}

PAN_VALID_4TH_CHAR: set[str] = {"P", "C", "H", "F", "A", "T", "B", "L", "J", "G"}


# ---------------------------------------------------------------------------
# Compiled Regular Expressions
# ---------------------------------------------------------------------------

# 1. Phone: 10-digit Indian mobiles starting 6-9, optional +91 or 0 prefix, optional 5-5 grouping
_PHONE_RE = re.compile(
    r"(?<![A-Za-z0-9+])(?:\+91[- ]?|0[- ]?)?[6-9](?:(?:\d{4}[- ]\d{5})|\d{9})(?!\d)"
)

# 2. IMEI: Exactly 15 digits
_IMEI_RE = re.compile(r"(?<!\d)\d{15}(?!\d)")

# 3. Aadhaar: 12 digits, first 2-9, plain or 4-4-4
_AADHAAR_RE = re.compile(r"(?<!\d)([2-9]\d{3}[- ]\d{4}[- ]\d{4}|[2-9]\d{11})(?!\d)")
_AADHAAR_CONTEXT_RE = re.compile(r"(?:aadhaar|aadhar|uid|आधार)", re.IGNORECASE)

# 4. PAN: 5 letters, 4 digits, 1 letter
_PAN_RE = re.compile(r"\b([A-Za-z]{5}[0-9]{4}[A-Za-z])\b")

# 5. IFSC: 4 letters, '0', 6 alphanumeric
_IFSC_RE = re.compile(r"\b([A-Za-z]{4}0[A-Za-z0-9]{6})\b")

# 6. UPI: Handle without space before '@', domain without dot
_UPI_RE = re.compile(r"(?<![\w.-])([a-zA-Z0-9._-]+@[a-zA-Z0-9_-]+)(?!\.[a-zA-Z0-9])\b")

# 7. Vehicle Registration Plates
_VEHICLE_RE = re.compile(
    r"\b([A-Za-z]{2})[- ]?(\d{1,2}[A-Za-z]?)[- ]?([A-Za-z]{1,2})[- ]?(\d{1,4})\b"
)

# 8. Amounts: Currency tokens, lakh/crore, comma grouped numbers
_CURR_PREFIX = r"(?:\b(?:INR|Rs\.?|Rupees?|रुपये|रु\.?)\s*|₹\s*)"
_LAKH_CRORE = r"\d+(?:\.\d+)?\s*(?:lakhs?|lacs?|crores?|cr|लाख|करोड़|करोड)\b"
_COMMA_NUM = r"\d{1,3}(?:,\d{2,3})+(?:\.\d+)?"
_CURR_NUM = r"\d{1,3}(?:,\d{2,3})*(?:\.\d+)?"

_AMOUNT_RE = re.compile(
    rf"(?:{_CURR_PREFIX}(?:{_LAKH_CRORE}|{_CURR_NUM})(?:\s*/-)?|\b(?:{_LAKH_CRORE}|{_COMMA_NUM})(?:\s*/-)?)",
    re.IGNORECASE,
)

# 9. Accounts: 9-18 digit runs preceded by context word within 20 chars
_ACCOUNT_DIGITS_RE = re.compile(r"(?<!\d)(\d{9,18})(?!\d)")
_ACCOUNT_CONTEXT_RE = re.compile(r"(?:account|a/c|acct|khata|खाता|sbi|hdfc|icici|pnb|axis)", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Finder Implementations
# ---------------------------------------------------------------------------

def find_phones(text: str) -> list[Candidate]:
    """Find 10-digit Indian mobile numbers with original text spans."""
    norm = normalize_text(text)
    candidates: list[Candidate] = []
    for m in _PHONE_RE.finditer(norm):
        start, end = m.span()
        surface = text[start:end]
        digits = re.sub(r"\D", "", norm[start:end])
        if len(digits) == 12 and digits.startswith("91"):
            value = digits[2:]
        elif len(digits) == 11 and digits.startswith("0"):
            value = digits[1:]
        else:
            value = digits

        if len(value) == 10 and value[0] in "6789":
            candidates.append(
                Candidate(
                    type="PHONE",
                    value=value,
                    start=start,
                    end=end,
                    surface=surface,
                    valid=True,
                    flags=[],
                )
            )
    candidates.sort(key=lambda c: c.start)
    return candidates


def find_imeis(text: str) -> list[Candidate]:
    """Find 15-digit IMEIs with Luhn validation."""
    norm = normalize_text(text)
    candidates: list[Candidate] = []
    for m in _IMEI_RE.finditer(norm):
        start, end = m.span()
        surface = text[start:end]
        value = norm[start:end]
        is_valid = luhn_valid(value)
        flags = [] if is_valid else ["CHECKSUM_INVALID"]
        candidates.append(
            Candidate(
                type="IMEI",
                value=value,
                start=start,
                end=end,
                surface=surface,
                valid=is_valid,
                flags=flags,
            )
        )
    candidates.sort(key=lambda c: c.start)
    return candidates


def find_aadhaar(text: str) -> list[Candidate]:
    """Find 12-digit Indian Aadhaar numbers using context or 4-4-4 grouping + Verhoeff."""
    norm = normalize_text(text)
    candidates: list[Candidate] = []
    for m in _AADHAAR_RE.finditer(norm):
        matched_str = m.group(1)
        digits = re.sub(r"\D", "", matched_str)
        is_grouped = bool(re.match(r"^[2-9]\d{3}[- ]\d{4}[- ]\d{4}$", matched_str))

        window_start = max(0, m.start() - 25)
        window = norm[window_start:m.start()]
        has_context = bool(_AADHAAR_CONTEXT_RE.search(window))
        is_verhoeff = verhoeff_valid(digits)

        # Return only if context within 25 chars, or (4-4-4 grouping and Verhoeff passes)
        if has_context or (is_grouped and is_verhoeff):
            start = m.start()
            end = m.end()
            surface = text[start:end]
            flags = [] if is_verhoeff else ["CHECKSUM_INVALID"]
            candidates.append(
                Candidate(
                    type="AADHAAR",
                    value=digits,
                    start=start,
                    end=end,
                    surface=surface,
                    valid=is_verhoeff,
                    flags=flags,
                )
            )
    candidates.sort(key=lambda c: c.start)
    return candidates


def find_pan(text: str) -> list[Candidate]:
    """Find Permanent Account Numbers (PAN) and validate 4th holder character."""
    norm = normalize_text(text)
    candidates: list[Candidate] = []
    for m in _PAN_RE.finditer(norm):
        start, end = m.span()
        surface = text[start:end]
        value = surface.upper()
        is_valid = value[3] in PAN_VALID_4TH_CHAR
        flags = [] if is_valid else ["BAD_HOLDER_TYPE"]
        candidates.append(
            Candidate(
                type="PAN",
                value=value,
                start=start,
                end=end,
                surface=surface,
                valid=is_valid,
                flags=flags,
            )
        )
    candidates.sort(key=lambda c: c.start)
    return candidates


def find_ifsc(text: str) -> list[Candidate]:
    """Find Indian Financial System Code (IFSC) tokens."""
    norm = normalize_text(text)
    candidates: list[Candidate] = []
    for m in _IFSC_RE.finditer(norm):
        start, end = m.span()
        surface = text[start:end]
        value = surface.upper()
        candidates.append(
            Candidate(
                type="IFSC",
                value=value,
                start=start,
                end=end,
                surface=surface,
                valid=True,
                flags=[],
            )
        )
    candidates.sort(key=lambda c: c.start)
    return candidates


def find_upi(text: str) -> list[Candidate]:
    """Find Unified Payments Interface (UPI) VPAs, excluding emails andspaced handles."""
    norm = normalize_text(text)
    candidates: list[Candidate] = []
    for m in _UPI_RE.finditer(norm):
        start, end = m.span()
        surface = text[start:end]
        candidates.append(
            Candidate(
                type="UPI",
                value=surface,
                start=start,
                end=end,
                surface=surface,
                valid=True,
                flags=[],
            )
        )
    candidates.sort(key=lambda c: c.start)
    return candidates


def find_vehicle_plates(text: str) -> list[Candidate]:
    """Find Indian motor vehicle registration plates."""
    norm = normalize_text(text)
    candidates: list[Candidate] = []
    for m in _VEHICLE_RE.finditer(norm):
        start, end = m.span()
        surface = text[start:end]
        state_code = m.group(1).upper()
        clean_value = re.sub(r"[- ]", "", norm[start:end]).upper()
        is_valid_state = state_code in INDIAN_STATE_UT_CODES
        flags = [] if is_valid_state else ["UNKNOWN_STATE"]
        candidates.append(
            Candidate(
                type="VEHICLE",
                value=clean_value,
                start=start,
                end=end,
                surface=surface,
                valid=is_valid_state,
                flags=flags,
            )
        )
    candidates.sort(key=lambda c: c.start)
    return candidates


def _parse_amount_value(norm_surface: str) -> float:
    s = norm_surface.strip()
    m_lakh = re.search(r"([\d.]+)\s*(?:lakhs?|lacs?|लाख)", s, re.IGNORECASE)
    if m_lakh:
        return float(m_lakh.group(1)) * 100000.0

    m_crore = re.search(r"([\d.]+)\s*(?:crores?|cr|करोड़|करोड)", s, re.IGNORECASE)
    if m_crore:
        return float(m_crore.group(1)) * 10000000.0

    cleaned = re.sub(r"(?i)(?:INR|Rs\.?|Rupees?|रुपये|रु\.?|₹|/-)", "", s).strip()
    cleaned = cleaned.replace(",", "")
    return float(cleaned)


def find_amounts(text: str) -> list[Candidate]:
    """Find monetary amounts, supporting Indian comma grouping, currency symbols, and lakh/crore."""
    norm = normalize_text(text)
    candidates: list[Candidate] = []
    for m in _AMOUNT_RE.finditer(norm):
        start, end = m.span()
        surface = text[start:end]
        norm_matched = norm[start:end]
        try:
            val = _parse_amount_value(norm_matched)
        except Exception:
            continue
        candidates.append(
            Candidate(
                type="AMOUNT",
                value=val,
                start=start,
                end=end,
                surface=surface,
                valid=True,
                flags=[],
            )
        )
    candidates.sort(key=lambda c: c.start)
    return candidates


def find_accounts(text: str) -> list[Candidate]:
    """Find bank account numbers (9-18 digits) accompanied by context within 20 chars."""
    norm = normalize_text(text)
    candidates: list[Candidate] = []
    for m in _ACCOUNT_DIGITS_RE.finditer(norm):
        start, end = m.span()
        window_start = max(0, start - 20)
        window = norm[window_start:start]
        if _ACCOUNT_CONTEXT_RE.search(window):
            surface = text[start:end]
            value = norm[start:end]
            candidates.append(
                Candidate(
                    type="ACCOUNT",
                    value=value,
                    start=start,
                    end=end,
                    surface=surface,
                    valid=True,
                    flags=[],
                )
            )
    candidates.sort(key=lambda c: c.start)
    return candidates
