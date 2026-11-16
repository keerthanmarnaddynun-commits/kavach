"""Parser, validator, and converter for LLM-authored FIR files."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import json
from pathlib import Path
import re
from typing import Any

# Allowed tag types and roles
VALID_TAG_TYPES = {
    "AADHAAR",
    "ACCOUNT",
    "ALIAS",
    "AMOUNT",
    "FATHER",
    "IFSC",
    "IMEI",
    "PAN",
    "PERSON",
    "PHONE",
    "UPI",
    "VEHICLE",
}

ROLE_MAP = {
    "C": "COMPLAINANT",
    "O": "OFFICER",
    "S": "SUSPECT",
    "W": "WITNESS",
}

VALID_REL_TYPES = {
    "ASSOCIATED_IMEI": {("PHONE", "IMEI")},
    "COMMUNICATED_WITH": {("PHONE", "PHONE")},
    "CONTROLS_ACCOUNT": {("PERSON", "ACCOUNT")},
    "OWNS_DEVICE": {("PERSON", "PHONE")},
    "TRANSFERRED_FUNDS": {("PERSON", "ACCOUNT"), ("ACCOUNT", "ACCOUNT")},
}


def luhn_check(digits_str: str) -> bool:
    """Validate 15-digit IMEI with Luhn algorithm."""
    digits = [int(c) for c in digits_str if c.isdigit()]
    if len(digits) != 15:
        return False
    total = 0
    for idx, d in enumerate(reversed(digits)):
        if idx % 2 == 1:
            doubled = d * 2
            total += (doubled - 9) if doubled > 9 else doubled
        else:
            total += d
    return total % 10 == 0


def parse_amount_value(text: str) -> float | None:
    """Parse numeric amount from natural language currency text."""
    cleaned = text.replace(",", "").strip()
    m_lakh = re.search(r"(\d+(?:\.\d+)?)\s*(?:lakh|लाख)", cleaned, re.IGNORECASE)
    if m_lakh:
        return float(m_lakh.group(1)) * 100000.0
    m_crore = re.search(r"(\d+(?:\.\d+)?)\s*(?:crore|करोड़)", cleaned, re.IGNORECASE)
    if m_crore:
        return float(m_crore.group(1)) * 10000000.0
    m = re.search(r"(\d+(?:\.\d+)?)", cleaned)
    if m:
        return float(m.group(1))
    return None


def normalize_phone_value(surface: str) -> str | None:
    """Normalize phone number to 10 digits starting with 6-9."""
    cleaned = re.sub(r"[\s\-\n\r]", "", surface)
    if cleaned.startswith("+91"):
        cleaned = cleaned[3:]
    elif cleaned.startswith("91") and len(cleaned) == 12:
        cleaned = cleaned[2:]
    elif cleaned.startswith("0") and len(cleaned) == 11:
        cleaned = cleaned[1:]
    if re.match(r"^[6-9]\d{9}$", cleaned):
        return cleaned
    return None


def levenshtein_dist(s1: str, s2: str) -> int:
    """Compute Levenshtein edit distance between two strings."""
    if len(s1) < len(s2):
        return levenshtein_dist(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        curr = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = prev[j + 1] + 1
            deletions = curr[j] + 1
            substitutions = prev[j] + (c1 != c2)
            curr.append(min(insertions, deletions, substitutions))
        prev = curr
    return prev[-1]


@dataclass
class ParseResult:
    clean_text: str = ""
    entities: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    is_valid: bool = True
    language: str = ""
    raw_hash: str = ""
    relationships: list[dict[str, Any]] = field(default_factory=list)
    stem: str = ""
    warnings: list[dict[str, Any]] = field(default_factory=list)

    def to_gold_dict(self, doc_id: str | None = None) -> dict[str, Any]:
        """Convert valid parse result to standard answer-key JSON format."""
        stem_id = doc_id or self.stem
        return {
            "entities": self.entities,
            "fir_type": "LLM_AUTHORED",
            "language": self.language,
            "relationships": self.relationships,
            "source_doc_id": stem_id,
            "split": "llm_heldout",
        }


def parse_text(raw_content: str, stem: str = "") -> ParseResult:
    """Parse raw FIR text with inline tags and relations block.

    Args:
        raw_content: Raw file content string.
        stem: File stem identifier (e.g. 'H_01').

    Returns:
        ParseResult containing clean text, entities, relationships, errors, and warnings.
    """
    res = ParseResult(stem=stem)
    content = raw_content.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    lines = content.split("\n")

    # 1. LANG header check
    if not lines or not re.match(r"^LANG:\s*(hinglish|english|hindi)\s*$", lines[0], re.IGNORECASE):
        res.errors.append("missing_or_unknown_lang_line")
        res.is_valid = False
        return res

    lang = re.match(r"^LANG:\s*(hinglish|english|hindi)\s*$", lines[0], re.IGNORECASE).group(1).lower()
    res.language = lang

    # Warning: lang stem mismatch
    if stem:
        if (stem.startswith("H_") and lang != "hinglish") or \
           (stem.startswith("E_") and lang != "english") or \
           (stem.startswith("D_") and lang != "hindi"):
            res.warnings.append({
                "detail": f"stem prefix does not match language: {stem} vs {lang}",
                "type": "lang_stem_mismatch",
            })

    # 2. Separator line check
    sep_idx = -1
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            sep_idx = idx
            break

    if sep_idx == -1:
        res.errors.append("missing_separator_line")
        res.is_valid = False
        return res

    body_lines = lines[1:sep_idx]
    rel_lines = lines[sep_idx + 1:]
    raw_body = "\n".join(body_lines)

    # 3. Check unbalanced or nested tags
    # Valid tag shape: [[HEADER|SURFACE]]
    tag_positions: list[tuple[int, int, str, str]] = []
    pos = 0
    has_unbalanced = False

    while pos < len(raw_body):
        open_idx = raw_body.find("[[", pos)
        if open_idx == -1:
            if "]]" in raw_body[pos:]:
                has_unbalanced = True
            break
        if "]]" in raw_body[pos:open_idx]:
            has_unbalanced = True
            break
        close_idx = raw_body.find("]]", open_idx + 2)
        if close_idx == -1:
            has_unbalanced = True
            break
        # Nested check
        next_open = raw_body.find("[[", open_idx + 2)
        if next_open != -1 and next_open < close_idx:
            has_unbalanced = True
            break

        inner = raw_body[open_idx + 2 : close_idx]
        if "|" not in inner:
            has_unbalanced = True
            break

        header, surface = inner.split("|", 1)
        tag_positions.append((open_idx, close_idx + 2, header, surface))
        pos = close_idx + 2

    if has_unbalanced:
        res.errors.append("unbalanced_or_nested_tags")
        res.is_valid = False
        return res

    # Check ambiguous / touching tags without separator
    for i in range(len(tag_positions) - 1):
        prev_end = tag_positions[i][1]
        next_start = tag_positions[i + 1][0]
        if prev_end == next_start:
            # Touching tags: [[A|foo]][[B|bar]] -> spans may be ambiguous
            res.errors.append("ambiguous_tag_spans")

    # 4. Parse headers and build clean text
    clean_parts: list[str] = []
    last_idx = 0
    clean_offset = 0

    key_types: dict[str, str] = {}
    person_keys: set[str] = set()
    person_names: dict[str, str] = {}
    person_aliases: dict[str, list[str]] = {}
    defined_keys: set[str] = set()
    amounts_parsed: dict[str, float] = {}

    raw_entities: list[dict[str, Any]] = []

    for open_idx, close_idx, header, surface in tag_positions:
        clean_parts.append(raw_body[last_idx:open_idx])
        clean_offset += (open_idx - last_idx)

        hdr_parts = header.split(":")
        tag_type = hdr_parts[0]

        if tag_type not in VALID_TAG_TYPES:
            res.errors.append(f"unknown_tag_type: {tag_type}")
            last_idx = close_idx
            continue

        if not surface:
            res.errors.append("empty_tag_text")

        key = hdr_parts[1] if len(hdr_parts) > 1 else ""
        if not key:
            res.errors.append("missing_tag_key")
        defined_keys.add(key)

        role = None
        if tag_type == "PERSON":
            if len(hdr_parts) < 3 or hdr_parts[2] not in ROLE_MAP:
                res.errors.append(f"invalid_person_role: {header}")
            else:
                role = ROLE_MAP[hdr_parts[2]]
                person_keys.add(key)
                if key not in person_names and surface:
                    person_names[key] = surface
                if key not in person_aliases:
                    person_aliases[key] = []
        elif tag_type == "ALIAS":
            if key not in person_aliases:
                person_aliases[key] = []
            if surface:
                person_aliases[key].append(surface)

        # Check duplicate key across different types (ALIAS/FATHER sharing person key is allowed)
        if key in key_types:
            existing_type = key_types[key]
            if existing_type != tag_type:
                if not (existing_type == "PERSON" and tag_type in ("ALIAS", "FATHER")):
                    res.errors.append(
                        f"duplicate_key_different_type: {key} defined as {existing_type} and {tag_type}"
                    )
        else:
            if tag_type not in ("ALIAS", "FATHER"):
                key_types[key] = tag_type
            else:
                # If ALIAS or FATHER encountered before PERSON
                pass

        start = clean_offset
        end = clean_offset + len(surface)
        clean_parts.append(surface)
        clean_offset += len(surface)
        last_idx = close_idx

        raw_entities.append({
            "key": key,
            "raw_role": hdr_parts[2] if tag_type == "PERSON" and len(hdr_parts) > 2 else None,
            "role": role,
            "span": (start, end),
            "surface": surface,
            "type": tag_type,
        })

    clean_parts.append(raw_body[last_idx:])
    full_clean = "".join(clean_parts)

    # Strip only leading and trailing blank lines
    clean_text = full_clean.strip("\n")
    leading_stripped = len(full_clean) - len(full_clean.lstrip("\n"))

    if not clean_text:
        res.errors.append("empty_clean_text")
    if len(clean_text) > 5000:
        res.errors.append("clean_text_too_long")

    res.clean_text = clean_text

    # Check orphan ALIAS or FATHER
    for ent in raw_entities:
        if ent["type"] in ("ALIAS", "FATHER"):
            if ent["key"] not in person_keys:
                res.errors.append(
                    f"orphan_alias_or_father: {ent['type']} key '{ent['key']}' has no matching PERSON tag"
                )

    # Build final entity dictionaries with exact string offsets
    entities: list[dict[str, Any]] = []
    key_to_first_mention: dict[str, str] = {}

    for i, ent in enumerate(raw_entities, start=1):
        eid = f"E{i}"
        tag_type = ent["type"]
        key = ent["key"]
        surface = ent["surface"]
        start = ent["span"][0] - leading_stripped
        end = ent["span"][1] - leading_stripped

        if key not in key_to_first_mention and tag_type not in ("ALIAS", "FATHER"):
            key_to_first_mention[key] = eid
        elif tag_type == "PERSON" and key not in key_to_first_mention:
            key_to_first_mention[key] = eid

        # Value normalization
        val: Any = surface
        if tag_type == "PHONE":
            norm_ph = normalize_phone_value(surface)
            if norm_ph:
                val = norm_ph
            else:
                res.warnings.append({
                    "key": key,
                    "surface": surface,
                    "type": "phone_normalisation_warning",
                })
        elif tag_type == "IMEI":
            imei_digits = re.sub(r"\D", "", surface)
            val = imei_digits
            if len(imei_digits) != 15 or not luhn_check(imei_digits):
                res.warnings.append({
                    "key": key,
                    "surface": surface,
                    "type": "imei_luhn_warning",
                })
        elif tag_type == "AADHAAR":
            aadhaar_digits = re.sub(r"\D", "", surface)
            val = aadhaar_digits
            if len(aadhaar_digits) != 12:
                res.warnings.append({
                    "key": key,
                    "surface": surface,
                    "type": "aadhaar_warning",
                })
        elif tag_type == "PAN":
            pan_clean = surface.strip().upper()
            val = pan_clean
            if not re.match(r"^[A-Z]{5}[0-9]{4}[A-Z]$", pan_clean):
                res.warnings.append({
                    "key": key,
                    "surface": surface,
                    "type": "pan_warning",
                })
        elif tag_type == "IFSC":
            ifsc_clean = surface.strip().upper()
            val = ifsc_clean
            if not re.match(r"^[A-Z]{4}0[A-Z0-9]{6}$", ifsc_clean):
                res.warnings.append({
                    "key": key,
                    "surface": surface,
                    "type": "ifsc_warning",
                })
        elif tag_type == "ACCOUNT":
            acct_digits = re.sub(r"\D", "", surface)
            val = acct_digits
            if not (9 <= len(acct_digits) <= 18):
                res.warnings.append({
                    "key": key,
                    "surface": surface,
                    "type": "account_warning",
                })
        elif tag_type == "AMOUNT":
            amt_num = parse_amount_value(surface)
            if amt_num is None:
                res.warnings.append({
                    "key": key,
                    "surface": surface,
                    "type": "amount_warning",
                })
            else:
                val = amt_num
                amounts_parsed[key] = amt_num
        elif tag_type == "PERSON":
            val = person_names.get(key, surface)

        # Structure entity dict
        ent_dict: dict[str, Any] = {
            "aliases": person_aliases.get(key, []) if tag_type == "PERSON" else [],
            "char_span": [start, end],
            "end": end,
            "entity_key": f"FATHER:{key}" if tag_type == "FATHER" else key,
            "id": eid,
            "label": "PERSON" if tag_type in ("PERSON", "FATHER") else tag_type,
            "role": "FATHER" if tag_type == "FATHER" else ent["role"],
            "start": start,
            "surface": surface,
            "text": surface,
            "truth_id": None,
            "type": "PERSON" if tag_type in ("PERSON", "FATHER") else tag_type,
            "value": val,
        }
        if tag_type == "FATHER":
            ent_dict["person_key"] = key
            ent_dict["suspect_key"] = key

        entities.append(ent_dict)

    res.entities = entities

    # Check untagged / possible unlabelled identifiers in clean_text
    id_patterns = [
        re.compile(r"(?:\+91[\s\-]?)?[6-9]\d{9}\b"),
        re.compile(r"\b\d{4}\s\d{4}\s\d{4}\b"),
        re.compile(r"\b\d{12}\b"),
        re.compile(r"\b\d{15}\b"),
    ]
    for pat in id_patterns:
        for m in pat.finditer(clean_text):
            ms, me = m.start(), m.end()
            # check if overlaps with any entity
            overlaps = any(not (me <= e["start"] or ms >= e["end"]) for e in entities)
            if not overlaps:
                res.warnings.append({
                    "offset": ms,
                    "surface": m.group(0),
                    "type": "possible_unlabelled_identifier",
                })

    # 5. Parse REL lines
    used_keys: set[str] = set()
    relationships: list[dict[str, Any]] = []

    for rl in rel_lines:
        line_clean = rl.strip()
        if not line_clean or line_clean.startswith("#"):
            continue

        if not line_clean.startswith("REL:"):
            res.errors.append(f"invalid_rel_syntax: {line_clean}")
            continue

        tokens = line_clean[4:].strip().split()
        if len(tokens) < 3:
            res.errors.append(f"invalid_rel_syntax: {line_clean}")
            continue

        rel_type, src_key, tgt_key = tokens[0], tokens[1], tokens[2]
        used_keys.add(src_key)
        used_keys.add(tgt_key)

        if rel_type not in VALID_REL_TYPES:
            res.errors.append(f"unknown_rel_type: {rel_type}")
            continue

        if src_key not in defined_keys or tgt_key not in defined_keys:
            res.errors.append(f"rel_key_not_in_text: {src_key} or {tgt_key} not defined in text")
            continue

        src_type = "PERSON" if src_key in person_keys else key_types.get(src_key)
        tgt_type = "PERSON" if tgt_key in person_keys else key_types.get(tgt_key)

        if (src_type, tgt_type) not in VALID_REL_TYPES[rel_type]:
            res.errors.append(
                f"invalid_rel_endpoints: {rel_type} expects {VALID_REL_TYPES[rel_type]}, got ({src_type}, {tgt_type})"
            )
            continue

        amt_val: float | None = None
        if rel_type == "TRANSFERRED_FUNDS":
            if len(tokens) < 4:
                res.errors.append(f"missing_transfer_amount: {line_clean}")
                continue
            amt_str = tokens[3]
            try:
                amt_val = float(amt_str)
            except ValueError:
                res.errors.append(f"missing_transfer_amount: non-numeric amount '{amt_str}'")
                continue

            if amounts_parsed and not any(abs(amt_val - a) < 0.01 for a in amounts_parsed.values()):
                res.warnings.append({
                    "rel_amount": amt_val,
                    "tag_amounts": sorted(amounts_parsed.values()),
                    "type": "rel_amount_mismatch",
                })

        src_mention = key_to_first_mention.get(src_key)
        tgt_mention = key_to_first_mention.get(tgt_key)

        relationships.append({
            "amount": amt_val,
            "relation": rel_type,
            "source": src_mention,
            "source_key": src_key,
            "source_mention": src_mention,
            "target": tgt_mention,
            "target_key": tgt_key,
            "target_mention": tgt_mention,
            "type": rel_type,
        })

    res.relationships = relationships

    # Warning: unused keys
    unused = sorted(defined_keys - used_keys)
    if unused:
        res.warnings.append({
            "keys": unused,
            "type": "unused_key",
        })

    if res.errors:
        res.is_valid = False

    return res


def parse_file(path: str | Path) -> ParseResult:
    """Read and parse an LLM-authored raw FIR text file.

    Args:
        path: Path to the raw text file.

    Returns:
        ParseResult instance.
    """
    p = Path(path)
    content = p.read_text(encoding="utf-8")
    return parse_text(content, stem=p.stem)
