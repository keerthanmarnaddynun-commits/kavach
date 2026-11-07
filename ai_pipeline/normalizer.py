"""
Length-preserving Unicode normalizer for Indic and English legal texts.
Provides 1:1 character replacements without altering character offsets.
"""

from __future__ import annotations

# Build translation dictionary for 1:1 single-character replacements
_TRANSLATION_TABLE: dict[int, str] = {}

# 1. Devanagari digits (U+0966 to U+096F) -> ASCII digits '0'-'9'
for _i in range(10):
    _TRANSLATION_TABLE[0x0966 + _i] = str(_i)

# 2. Arabic-Indic digits:
# Standard Arabic-Indic (U+0660 to U+0669) -> '0'-'9'
for _i in range(10):
    _TRANSLATION_TABLE[0x0660 + _i] = str(_i)

# Extended / Eastern Arabic-Indic / Persian / Urdu (U+06F0 to U+06F9) -> '0'-'9'
for _i in range(10):
    _TRANSLATION_TABLE[0x06F0 + _i] = str(_i)

# 3. Fullwidth digits (U+FF10 to U+FF19) -> '0'-'9'
for _i in range(10):
    _TRANSLATION_TABLE[0xFF10 + _i] = str(_i)

# 4. Unicode space variants -> ASCII space ' ' (U+0020)
_SPACE_VARIANTS = (
    0x00A0,  # NO-BREAK SPACE (NBSP)
    0x1680,  # OGHAM SPACE MARK
    0x2000,  # EN QUAD
    0x2001,  # EM QUAD
    0x2002,  # EN SPACE
    0x2003,  # EM SPACE
    0x2004,  # THREE-PER-EM SPACE
    0x2005,  # FOUR-PER-EM SPACE
    0x2006,  # SIX-PER-EM SPACE
    0x2007,  # FIGURE SPACE
    0x2008,  # PUNCTUATION SPACE
    0x2009,  # THIN SPACE
    0x200A,  # HAIR SPACE
    0x202F,  # NARROW NO-BREAK SPACE
    0x205F,  # MEDIUM MATHEMATICAL SPACE
    0x3000,  # IDEOGRAPHIC SPACE
)
for _cp in _SPACE_VARIANTS:
    _TRANSLATION_TABLE[_cp] = " "

# 5. Unicode dashes and minus -> ASCII hyphen-minus '-' (U+002D)
_DASH_VARIANTS = (
    0x2010,  # HYPHEN
    0x2011,  # NON-BREAKING HYPHEN
    0x2012,  # FIGURE DASH
    0x2013,  # EN DASH
    0x2014,  # EM DASH
    0x2015,  # HORIZONTAL BAR
    0x2212,  # MINUS SIGN
    0xFE58,  # SMALL EM DASH
    0xFE63,  # SMALL HYPHEN-MINUS
    0xFF0D,  # FULLWIDTH HYPHEN-MINUS
)
for _cp in _DASH_VARIANTS:
    _TRANSLATION_TABLE[_cp] = "-"

# 6. Curly quotes -> straight quotes
# Single curly quotes -> straight single quote "'" (U+0027)
_SINGLE_QUOTES = (
    0x2018,  # LEFT SINGLE QUOTATION MARK
    0x2019,  # RIGHT SINGLE QUOTATION MARK
    0x201A,  # SINGLE LOW-9 QUOTATION MARK
    0x201B,  # SINGLE HIGH-REVERSED-9 QUOTATION MARK
    0x2039,  # SINGLE LEFT-POINTING ANGLE QUOTATION MARK
    0x203A,  # SINGLE RIGHT-POINTING ANGLE QUOTATION MARK
    0x02BC,  # MODIFIER LETTER APOSTROPHE
    0x02BB,  # MODIFIER LETTER TURNED COMMA
)
for _cp in _SINGLE_QUOTES:
    _TRANSLATION_TABLE[_cp] = "'"

# Double curly quotes -> straight double quote '"' (U+0022)
_DOUBLE_QUOTES = (
    0x201C,  # LEFT DOUBLE QUOTATION MARK
    0x201D,  # RIGHT DOUBLE QUOTATION MARK
    0x201E,  # DOUBLE LOW-9 QUOTATION MARK
    0x201F,  # DOUBLE HIGH-REVERSED-9 QUOTATION MARK
    0x00AB,  # LEFT-POINTING DOUBLE ANGLE QUOTATION MARK
    0x00BB,  # RIGHT-POINTING DOUBLE ANGLE QUOTATION MARK
)
for _cp in _DOUBLE_QUOTES:
    _TRANSLATION_TABLE[_cp] = '"'


def normalize_text(text: str) -> str:
    """
    Length-preserving 1:1 character normalization for Indian and legal text.

    Guarantees len(normalize_text(text)) == len(text).
    Replaces:
    - Devanagari, Arabic-Indic and fullwidth digits with ASCII digits.
    - Unicode space variants with ASCII space (' ').
    - Unicode dashes and minus signs with ASCII hyphen ('-').
    - Curly/smart quotes with straight quotes (' and \").
    Performs NO NFC decomposition/composition, NO removals, and NO case modifications.
    """
    if not text:
        return text
    return text.translate(_TRANSLATION_TABLE)

