"""
Tests for length-preserving normalizer (ai_pipeline/normalizer.py).
"""

from __future__ import annotations

import sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai_pipeline.normalizer import normalize_text


def test_devanagari_digits():
    """Devanagari digits ०-९ map 1:1 to ASCII 0-9."""
    inp = "०१२३४५६७८९"
    expected = "0123456789"
    out = normalize_text(inp)
    assert out == expected
    assert len(out) == len(inp)


def test_arabic_indic_digits():
    """Standard and extended Arabic-Indic digits map 1:1 to ASCII 0-9."""
    # Standard Arabic-Indic
    inp_std = "٠١٢٣٤٥٦٧٨٩"
    expected = "0123456789"
    out_std = normalize_text(inp_std)
    assert out_std == expected
    assert len(out_std) == len(inp_std)

    # Extended / Eastern Arabic-Indic (Perso-Arabic / Urdu)
    inp_ext = "۰۱۲۳۴۵۶۷۸۹"
    out_ext = normalize_text(inp_ext)
    assert out_ext == expected
    assert len(out_ext) == len(inp_ext)


def test_fullwidth_digits():
    """Fullwidth digits ０-９ map 1:1 to ASCII 0-9."""
    inp = "０１２３４５６７８９"
    expected = "0123456789"
    out = normalize_text(inp)
    assert out == expected
    assert len(out) == len(inp)


def test_unicode_space_variants():
    """Unicode space variants (NBSP, thin space, narrow NBSP, en/em space) map to ASCII ' '."""
    spaces = [
        "\u00A0",  # NBSP
        "\u2009",  # THIN SPACE
        "\u202F",  # NARROW NO-BREAK SPACE
        "\u2002",  # EN SPACE
        "\u2003",  # EM SPACE
        "\u2007",  # FIGURE SPACE
        "\u2008",  # PUNCTUATION SPACE
        "\u3000",  # IDEOGRAPHIC SPACE
    ]
    inp = "".join(f"A{sp}B" for sp in spaces)
    out = normalize_text(inp)
    assert len(out) == len(inp)
    for i in range(1, len(inp), 3):
        assert out[i] == " "


def test_unicode_dashes_and_minus():
    """Unicode dashes and minus signs map to ASCII '-'."""
    dashes = [
        "\u2010",  # HYPHEN
        "\u2011",  # NON-BREAKING HYPHEN
        "\u2012",  # FIGURE DASH
        "\u2013",  # EN DASH
        "\u2014",  # EM DASH
        "\u2015",  # HORIZONTAL BAR
        "\u2212",  # MINUS SIGN
    ]
    inp = "".join(f"X{d}Y" for d in dashes)
    out = normalize_text(inp)
    assert len(out) == len(inp)
    for i in range(1, len(inp), 3):
        assert out[i] == "-"


def test_curly_quotes():
    """Smart/curly single and double quotes map to straight quotes."""
    inp = "‘single’ and “double” quotes, plus ‚low’ and „double-low”"
    expected = "'single' and \"double\" quotes, plus 'low' and \"double-low\""
    out = normalize_text(inp)
    assert out == expected
    assert len(out) == len(inp)


def test_length_preserving_property():
    """Normalizer strictly preserves character length across diverse complex texts."""
    samples = [
        "",
        "Plain ASCII 123",
        "FIR No. ४५/२०२६ ki investigation: ‘suspect’ Vikas Kumar @ Bicky.",
        "Transfer amount: INR ५,००,०००.०० into SBI A/c ३०२९१८२७४६५.",
        "Mobile: +91\u00A098765\u200943210, IMEI: 864201948201948 \u2014 recovered.",
        "Mixed: ٠١٢\u202f३४५\u2013۶۷۸\u2014901 ‘quote’ “double”.",
    ]
    for s in samples:
        norm = normalize_text(s)
        assert len(norm) == len(s), f"Length changed for {s!r}: {len(s)} -> {len(norm)}"


def test_untouched_text():
    """Normalizer does not touch ASCII letters, casing, accents, or Indic letters."""
    hindi_text = "थाना सेक्टर 42 में अभियुक्त विकास कुमार उर्फ बिक्की के खिलाफ मामला दर्ज हुआ।"
    norm = normalize_text(hindi_text)
    # 42 becomes 42, Hindi characters stay identical
    assert norm == hindi_text
    assert len(norm) == len(hindi_text)

