"""
Step 6a: Name-role rule layer.
Implements cue-based alias extraction, father extraction, honorific stripping,
and investigative role assignment.
"""
from __future__ import annotations

import re
from typing import Any

# Roman and Devanagari honorifics
HONORIFICS = (
    "Shri", "Sri", "Shree", "Smt", "Sh", "Mr", "Mrs", "Ms", "Dr", "Kumari",
    "श्री", "श्रीमती", "श्रीमान"
)

# Common FIR sentence-starter words derived strictly from train and dev false positives
STOPWORDS = frozenset({"Zabt", "Zabti", "जब्त", "जब्ती"})

_SORTED_HONORIFICS = sorted(HONORIFICS, key=len, reverse=True)
_HONORIFICS_REGEX = re.compile(
    r"^(?:" + "|".join(re.escape(h) for h in _SORTED_HONORIFICS) + r")(?:\.?(?:\s+|$))",
    re.IGNORECASE,
)

_ALIAS_CUES_REGEX = re.compile(
    r"(?:\b(?:urf|alias|aka|a\.k\.a\.|known\s+as)\b|@|उर्फ़|उर्फ)",
    re.IGNORECASE,
)

_ALIAS_PAREN_REGEX = re.compile(
    r"\(\s*(?:alias|urf|aka|a\.k\.a\.)\s+([^\)]+)\)",
    re.IGNORECASE,
)

_FATHER_CUES_REGEX = re.compile(
    r"(?:\b(?:s/o|d/o|w/o|c/o|son\s+of|daughter\s+of|wife\s+of|care\s+of)\b|आत्मज|सुपुत्र|पुत्र|सुपुत्री|पुत्री|पत्नी|पिता)[:\.]?\s*",
    re.IGNORECASE,
)

_STOP_ALIAS = frozenset({
    "s/o", "d/o", "w/o", "c/o", "r/o", "so", "do", "wo", "co", "ro",
    "son", "daughter", "wife", "resident",
    "ko", "ne", "ke", "ki", "se", "mein", "par", "aur", "bhi", "and", "also",
    "at", "was", "is", "were", "who", "has", "had",
    "को", "ने", "के", "की", "से", "में", "पर", "और", "भी",
    "आत्मज", "सुपुत्र", "पुत्र", "सुपुत्री", "पुत्री", "पत्नी", "पिता", "निवासी"
})

_STOP_FATHER = frozenset({
    "r/o", "ro", "resident", "was", "is", "were", "who", "has", "had",
    "ko", "ne", "ke", "ki", "se", "mein", "par", "aur", "bhi", "and", "at",
    "को", "ने", "के", "की", "से", "में", "पर", "और", "भी", "निवासी"
})

_ROLE_CUE_PATTERNS = [
    (
        re.compile(
            r"\b(?:complainant|informant|victim|shikayatkarta)\b|शिकायतकर्ता|वादी|प्रार्थी|पीड़ित|पीड़िता|फरियादी",
            re.IGNORECASE,
        ),
        "COMPLAINANT",
    ),
    (
        re.compile(
            r"\b(?:witness|pancha|panch\s+witness|public\s+witness|independent\s+witness|gawah)\b|पंच|गवाह|साक्षी|चश्मदीद|स्वतंत्र\s+गवाह",
            re.IGNORECASE,
        ),
        "WITNESS",
    ),
    (
        re.compile(
            r"\b(?:sub-inspector|sub\s+inspector|inspector|si|asi|io|sho|head\s+constable|hc|constable|duty\s+officer|investigating\s+officer|police\s+officer|officer-in-charge|dy\.?sp|dsp)\b|उप-निरीक्षक|उप\s+निरीक्षक|थाना\s+प्रभारी|विवेचक|आरक्षी|निरीक्षक|कांस्टेबल|हेड\s+कांस्टेबल|पुलिस\s+अधिकारी|जांच\s+अधिकारी|थानाध्यक्ष|सब\s+इंस्पेक्टर|इंस्पेक्टर",
            re.IGNORECASE,
        ),
        "OFFICER",
    ),
    (
        re.compile(
            r"\b(?:suspect|accused|co-accused)\b|अभियुक्त|सह-अभियुक्त|संदिग्ध",
            re.IGNORECASE,
        ),
        "SUSPECT",
    ),
]


def strip_honorific(text: str, start: int, end: int) -> tuple[int, int]:
    """
    Adjust (start, end) on original text to strip leading honorific and trailing whitespace.
    Returns (start, end) on the original text.
    """
    sub = text[start:end]
    m = _HONORIFICS_REGEX.match(sub)
    if m:
        new_start = start + m.end()
        while new_start < end and text[new_start].isspace():
            new_start += 1
        return new_start, end
    return start, end


def find_aliases(text: str) -> list[dict[str, Any]]:
    """
    Extract alias spans based on cue words (urf, alias, aka, a.k.a., known as, @, उर्फ, उर्फ़, '(alias X)').
    Returns alias spans only (cue excluded), chains like 'urf A @ B @ C' give three spans.
    """
    spans: list[dict[str, Any]] = []

    # 1. Parenthesized alias forms: (alias X)
    for pm in _ALIAS_PAREN_REGEX.finditer(text):
        inside_txt = pm.group(1)
        start_inside = pm.start(1)
        stripped = inside_txt.strip()
        s_off = inside_txt.find(stripped)
        a_s = start_inside + s_off
        a_e = a_s + len(stripped)
        if a_s < a_e:
            spans.append({
                "type": "ALIAS",
                "role": None,
                "start": a_s,
                "end": a_e,
                "surface": text[a_s:a_e],
            })

    # 2. General cue patterns
    for m in _ALIAS_CUES_REGEX.finditer(text):
        pos = m.end()
        tokens = []
        cur = pos
        while cur < len(text) and len(tokens) < 2:
            while cur < len(text) and text[cur].isspace():
                cur += 1
            if cur >= len(text):
                break
            # Stop if encountering another alias cue (e.g. '@' or 'urf')
            if text[cur] == "@" or _ALIAS_CUES_REGEX.match(text[cur:]):
                break
            tok_m = re.match(r"[A-Za-z\u0900-\u097F]+(?:/[A-Za-z]+)?", text[cur:])
            if not tok_m:
                break
            tok_str = tok_m.group(0)
            if tok_str.lower() in _STOP_ALIAS:
                break
            # Must be capitalized Latin or Devanagari word
            if re.match(r"^[A-Z][a-zA-Z\'-]*$", tok_str) or re.match(r"^[\u0900-\u097F]+$", tok_str):
                tokens.append((cur, cur + len(tok_str), tok_str))
                cur += len(tok_str)
            else:
                break

        if len(tokens) in (1, 2):
            s_tok = tokens[0][0]
            e_tok = tokens[-1][1]
            spans.append({
                "type": "ALIAS",
                "role": None,
                "start": s_tok,
                "end": e_tok,
                "surface": text[s_tok:e_tok],
            })

    # Sort and remove duplicate positions
    spans.sort(key=lambda x: (x["start"], x["end"]))
    unique_spans: list[dict[str, Any]] = []
    seen = set()
    for sp in spans:
        key = (sp["start"], sp["end"])
        if key not in seen:
            seen.add(key)
            unique_spans.append(sp)

    return unique_spans


def find_fathers(text: str) -> list[dict[str, Any]]:
    """
    Extract father spans based on cues (s/o, d/o, w/o, c/o, son of, daughter of, wife of, पुत्र, पुत्री, पत्नी, पिता).
    Optional honorific stripped; extracts 2 to 3 name tokens. Excludes cue and honorific.
    """
    spans: list[dict[str, Any]] = []

    for m in _FATHER_CUES_REGEX.finditer(text):
        pos = m.end()
        hon_m = _HONORIFICS_REGEX.match(text[pos:])
        if hon_m:
            pos += hon_m.end()

        tokens = []
        cur = pos
        while cur < len(text) and len(tokens) < 3:
            while cur < len(text) and text[cur].isspace():
                cur += 1
            if cur >= len(text):
                break
            tok_m = re.match(r"[A-Za-z\u0900-\u097F]+(?:/[A-Za-z]+)?", text[cur:])
            if not tok_m:
                break
            tok_str = tok_m.group(0)
            if tok_str.lower() in _STOP_FATHER:
                break
            if re.match(r"^[A-Z][a-zA-Z\'-]*$", tok_str) or re.match(r"^[\u0900-\u097F]+$", tok_str):
                tokens.append((cur, cur + len(tok_str), tok_str))
                cur += len(tok_str)
            else:
                break

        if len(tokens) in (2, 3):
            s_tok = tokens[0][0]
            e_tok = tokens[-1][1]
            spans.append({
                "type": "FATHER",
                "role": "FATHER",
                "start": s_tok,
                "end": e_tok,
                "surface": text[s_tok:e_tok],
            })

    # Deduplicate spans
    spans.sort(key=lambda x: (x["start"], x["end"]))
    unique_spans: list[dict[str, Any]] = []
    seen = set()
    for sp in spans:
        key = (sp["start"], sp["end"])
        if key not in seen:
            seen.add(key)
            unique_spans.append(sp)

    return unique_spans


def role_for(text: str, start: int, end: int) -> str:
    """
    Determine person role by examining 60 characters before and 25 characters after span.
    Returns OFFICER, COMPLAINANT, WITNESS, or default SUSPECT.
    """
    pre = text[max(0, start - 60):start]
    post = text[end:min(len(text), end + 25)]

    # Look for nearest cue in pre context
    best_pre_role = None
    best_pre_pos = -1
    for pat, role in _ROLE_CUE_PATTERNS:
        for m in pat.finditer(pre):
            if m.end() > best_pre_pos:
                best_pre_pos = m.end()
                best_pre_role = role
    if best_pre_role:
        return best_pre_role

    # Look for nearest cue in post context
    best_post_role = None
    best_post_pos = len(post) + 1
    for pat, role in _ROLE_CUE_PATTERNS:
        m = pat.search(post)
        if m and m.start() < best_post_pos:
            best_post_pos = m.start()
            best_post_role = role
    if best_post_role:
        return best_post_role

    return "SUSPECT"


def extract_names(
    text: str,
    model_spans: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Extract structured names from text and post-processed model spans:
    - strip honorifics
    - drop spans that are only an honorific or that fall in STOPWORDS
    - cue-based alias and father spans REPLACE any model span they overlap
    - remaining spans are assigned PERSON with role_for
    Output sorted, non-overlapping, text[start:end] == surface.
    """
    alias_spans = find_aliases(text)
    father_spans = find_fathers(text)
    rule_spans = alias_spans + father_spans

    remaining_model: list[dict[str, Any]] = []
    for sp in model_spans:
        s = int(sp["start"])
        e = int(sp["end"])
        ns, ne = strip_honorific(text, s, e)
        if ns >= ne:
            continue  # Drop honorific-only / empty

        surf = text[ns:ne].strip()
        if not surf:
            continue
        if surf in STOPWORDS or surf.lower() in {w.lower() for w in STOPWORDS} or surf in HONORIFICS:
            continue

        # Check if overlaps with any cue-based rule span (alias or father)
        if any(min(ne, rsp["end"]) > max(ns, rsp["start"]) for rsp in rule_spans):
            continue  # Replaced by rule span

        remaining_model.append({
            "type": "PERSON",
            "role": role_for(text, ns, ne),
            "start": ns,
            "end": ne,
            "surface": text[ns:ne],
        })

    all_spans = rule_spans + remaining_model
    all_spans.sort(key=lambda x: (x["start"], x["end"]))

    # Resolve any remaining overlaps (favoring rule spans, then earlier start)
    type_priority = {"ALIAS": 3, "FATHER": 2, "PERSON": 1}
    dedup: list[dict[str, Any]] = []
    for sp in all_spans:
        if not dedup:
            dedup.append(sp)
            continue

        prev = dedup[-1]
        if sp["start"] < prev["end"]:
            # Overlap: keep the higher priority type or longer span
            prev_p = type_priority.get(prev.get("type", ""), 0)
            curr_p = type_priority.get(sp.get("type", ""), 0)
            if curr_p > prev_p:
                dedup[-1] = sp
            elif curr_p == prev_p:
                if (sp["end"] - sp["start"]) > (prev["end"] - prev["start"]):
                    dedup[-1] = sp
        else:
            dedup.append(sp)

    return dedup
