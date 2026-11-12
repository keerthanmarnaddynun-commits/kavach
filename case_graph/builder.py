"""Deterministic cross-FIR and CSV case graph builder."""

from __future__ import annotations

from collections import Counter, defaultdict
import csv
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
import json
from pathlib import Path
import re
from typing import Any
import unicodedata

from case_graph.validate import ALLOWED_NODE_TYPES, ALLOWED_RELATION_TYPES

STRONG_ID_RELATIONS: dict[str, str] = {
    "OWNS_DEVICE": "PHONE",
    "CONTROLS_ACCOUNT": "ACCOUNT",
}

CONTRACT_RELATION_TYPES: frozenset[str] = frozenset(
    {
        "OWNS_DEVICE",
        "ASSOCIATED_IMEI",
        "COMMUNICATED_WITH",
        "CONTROLS_ACCOUNT",
        "TRANSFERRED_FUNDS",
    }
)

_DEVANAGARI_INDEPENDENT_VOWELS: dict[str, str] = {
    "अ": "a",
    "आ": "aa",
    "इ": "i",
    "ई": "ee",
    "उ": "u",
    "ऊ": "oo",
    "ऋ": "ri",
    "ए": "e",
    "ऐ": "ai",
    "ओ": "o",
    "औ": "au",
    "ऑ": "o",
    "ऍ": "e",
}

_DEVANAGARI_MATRAS: dict[str, str] = {
    "ा": "aa",
    "ि": "i",
    "ी": "ee",
    "ु": "u",
    "ू": "oo",
    "ृ": "ri",
    "े": "e",
    "ै": "ai",
    "ो": "o",
    "ौ": "au",
    "ॉ": "o",
    "ॅ": "e",
}

_DEVANAGARI_CONSONANTS: dict[str, str] = {
    "क": "k",
    "ख": "kh",
    "ग": "g",
    "घ": "gh",
    "ङ": "ng",
    "च": "ch",
    "छ": "chh",
    "ज": "j",
    "झ": "jh",
    "ञ": "ny",
    "ट": "t",
    "ठ": "th",
    "ड": "d",
    "ढ": "dh",
    "ण": "n",
    "त": "t",
    "थ": "th",
    "द": "d",
    "ध": "dh",
    "न": "n",
    "प": "p",
    "फ": "ph",
    "ब": "b",
    "भ": "bh",
    "म": "m",
    "य": "y",
    "र": "r",
    "ल": "l",
    "ळ": "l",
    "व": "v",
    "श": "sh",
    "ष": "sh",
    "स": "s",
    "ह": "h",
}

_DEVANAGARI_NUKTA_CONSONANTS: dict[str, str] = {
    "क": "q",
    "ख": "kh",
    "ग": "gh",
    "ज": "z",
    "ड": "r",
    "ढ": "rh",
    "फ": "f",
    "य": "y",
}

_DEVANAGARI_LABIALS: frozenset[str] = frozenset({"प", "फ", "ब", "भ", "म"})
_HALANT = "\u094d"
_NUKTA = "\u093c"
_ANUSVARA = "\u0902"
_CHANDRABINDU = "\u0901"
_VISARGA = "\u0903"


def _is_devanagari_char(ch: str) -> bool:
    return "\u0900" <= ch <= "\u097f"


def _script_kind(name: str) -> str:
    has_dev = any(_is_devanagari_char(c) for c in name)
    has_lat = any("a" <= c.lower() <= "z" for c in name)
    if has_dev and not has_lat:
        return "DEVANAGARI"
    if has_lat and not has_dev:
        return "ROMAN"
    if has_dev and has_lat:
        return "MIXED"
    return "OTHER"


def _transliterate_devanagari_word(word: str) -> str:
    """Transliterate one Devanagari word to Roman using standard Hindi rules."""
    n = len(word)
    i = 0
    out: list[str] = []

    while i < n:
        ch = word[i]

        # Independent vowels
        if ch in _DEVANAGARI_INDEPENDENT_VOWELS:
            out.append(_DEVANAGARI_INDEPENDENT_VOWELS[ch])
            i += 1
            continue

        # Standard 2-consonant conjuncts: क् + ष -> ksh, ज् + ञ -> gy
        if (
            i + 2 < n
            and word[i + 1] == _HALANT
            and ch in ("क", "ज")
            and ((ch == "क" and word[i + 2] == "ष") or (ch == "ज" and word[i + 2] == "ञ"))
        ):
            conj = "ksh" if ch == "क" else "gy"
            out.append(conj)
            i += 3
            if i < n and word[i] in _DEVANAGARI_MATRAS:
                out.append(_DEVANAGARI_MATRAS[word[i]])
                i += 1
            elif i < n and word[i] == _HALANT:
                i += 1
            elif i < n and word[i] not in (_ANUSVARA, _CHANDRABINDU, _VISARGA):
                out.append("a")
            continue

        # Consonants (with optional nukta)
        if ch in _DEVANAGARI_CONSONANTS:
            i += 1
            if i < n and word[i] == _NUKTA:
                rom = _DEVANAGARI_NUKTA_CONSONANTS.get(ch, _DEVANAGARI_CONSONANTS[ch])
                i += 1
            else:
                rom = _DEVANAGARI_CONSONANTS[ch]
            out.append(rom)

            if i < n and word[i] == _HALANT:
                i += 1
            elif i < n and word[i] in _DEVANAGARI_MATRAS:
                out.append(_DEVANAGARI_MATRAS[word[i]])
                i += 1
            elif i < n and (
                word[i] in _DEVANAGARI_CONSONANTS
                or word[i] in _DEVANAGARI_INDEPENDENT_VOWELS
                or word[i] in (_ANUSVARA, _CHANDRABINDU, _VISARGA)
            ):
                # Inherent schwa in non-final position.
                out.append("a")
            continue

        if ch == _ANUSVARA:
            nxt = word[i + 1] if i + 1 < n else ""
            out.append("m" if nxt in _DEVANAGARI_LABIALS else "n")
            i += 1
            continue

        if ch == _CHANDRABINDU:
            out.append("n")
            i += 1
            continue

        if ch == _VISARGA:
            out.append("h")
            i += 1
            continue

        if ch in _DEVANAGARI_MATRAS:
            out.append(_DEVANAGARI_MATRAS[ch])
            i += 1
            continue

        if "a" <= ch.lower() <= "z" or ch.isdigit():
            out.append(ch.lower())
        i += 1

    return "".join(out)


def devanagari_to_roman(text: str) -> str:
    """Transliterate Devanagari text to whitespace-joined Roman tokens."""
    norm = unicodedata.normalize("NFKC", str(text)).strip()
    tokens = re.findall(r"[\u0900-\u097fA-Za-z0-9]+", norm)
    return " ".join(_transliterate_devanagari_word(tok) for tok in tokens)


def _normalise_roman_word(word: str) -> str:
    w = re.sub(r"[^a-z]", "", unicodedata.normalize("NFKC", word).lower())
    # Standard orthographic equivalences without merging b and v.
    w = w.replace("ph", "f")
    w = w.replace("q", "k")
    w = w.replace("w", "v")
    w = w.replace("z", "j")
    w = w.replace("x", "ks")
    w = w.replace("ngh", "nh")
    # Handle plain 'c' outside 'ch'.
    chars: list[str] = []
    idx = 0
    while idx < len(w):
        if w[idx] == "c":
            if idx + 1 < len(w) and w[idx + 1] == "h":
                chars.append("ch")
                idx += 2
                continue
            if idx + 1 < len(w) and w[idx + 1] in ("e", "i", "y"):
                chars.append("s")
            else:
                chars.append("k")
        else:
            chars.append(w[idx])
        idx += 1
    return "".join(chars)


def _consonant_skeleton(roman_word: str) -> str:
    w = _normalise_roman_word(roman_word)
    for dg, code in (
        ("chh", "C"),
        ("ch", "C"),
        ("sh", "S"),
        ("kh", "K"),
        ("gh", "G"),
        ("jh", "J"),
        ("th", "T"),
        ("dh", "D"),
        ("bh", "B"),
    ):
        w = w.replace(dg, code)
    # Strip vowels only, keeping all consonants (b/B and v strictly separate).
    cons = [ch for ch in w if ch not in ("a", "e", "i", "o", "u")]
    # Collapse adjacent duplicate consonants.
    dedup: list[str] = []
    for ch in cons:
        if not dedup or dedup[-1] != ch:
            dedup.append(ch)
    return "".join(dedup)


def _vowel_norm_word(roman_word: str) -> str:
    w = _normalise_roman_word(roman_word)
    for src, dst in (
        ("aa", "a"),
        ("ee", "i"),
        ("ii", "i"),
        ("oo", "u"),
        ("uu", "u"),
    ):
        w = w.replace(src, dst)
    # Collapse adjacent duplicate characters.
    dedup: list[str] = []
    for ch in w:
        if not dedup or dedup[-1] != ch:
            dedup.append(ch)
    out = "".join(dedup)
    if len(out) > 4 and out.endswith("a") and out[-2] not in ("a", "e", "i", "o", "u"):
        out = out[:-1]
    return out


def _edit_distance(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        curr = [i]
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            curr.append(min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost))
        prev = curr
    return prev[-1]


def _cross_script_word_match(dev_word: str, rom_word: str) -> bool:
    t_rom = _transliterate_devanagari_word(dev_word)
    r_rom = _normalise_roman_word(rom_word)
    t_norm = _normalise_roman_word(t_rom)
    if not t_norm or not r_rom:
        return False

    # Initial vowel vs consonant check prevents mismatches like Aslam vs Salim.
    vowels = {"a", "e", "i", "o", "u"}
    if (t_norm[0] in vowels) != (r_rom[0] in vowels):
        return False

    sk1 = _consonant_skeleton(t_norm)
    sk2 = _consonant_skeleton(r_rom)
    if not sk1 or not sk2:
        return _vowel_norm_word(t_norm) == _vowel_norm_word(r_rom)

    # Strict b/B/v separation across both Devanagari and Roman.
    if (
        sk1.count("b") != sk2.count("b")
        or sk1.count("B") != sk2.count("B")
        or sk1.count("v") != sk2.count("v")
    ):
        return False
    if sk1[0] != sk2[0]:
        return False

    max_sk = max(len(sk1), len(sk2))
    sk_tol = 0 if max_sk <= 3 else 1
    if _edit_distance(sk1, sk2) > sk_tol:
        return False

    vn1 = _vowel_norm_word(t_norm)
    vn2 = _vowel_norm_word(r_rom)
    if not vn1 or not vn2:
        return False
    # Reject differing trailing explicit long/clear vowels (e.g. Raja vs Raju).
    if (
        vn1[-1] in ("i", "u", "e", "o")
        and vn2[-1] in ("a", "i", "u", "e", "o")
        and vn1[-1] != vn2[-1]
    ) or (
        vn2[-1] in ("i", "u", "e", "o")
        and vn1[-1] in ("a", "i", "u", "e", "o")
        and vn1[-1] != vn2[-1]
    ):
        return False

    vn_tol = max(1, max(len(vn1), len(vn2)) // 3)
    return _edit_distance(vn1, vn2) <= vn_tol


def cross_script_names_match(name_a: str, name_b: str) -> bool:
    """Return True iff one name is Devanagari, one is Roman, and tokens match."""
    sa = _script_kind(name_a)
    sb = _script_kind(name_b)
    if {sa, sb} != {"DEVANAGARI", "ROMAN"}:
        return False
    dev_name, rom_name = (name_a, name_b) if sa == "DEVANAGARI" else (name_b, name_a)
    dev_tokens = re.findall(
        r"[\u0900-\u097f]+", unicodedata.normalize("NFKC", dev_name)
    )
    rom_tokens = re.findall(r"[A-Za-z]+", unicodedata.normalize("NFKC", rom_name))
    if not dev_tokens or len(dev_tokens) != len(rom_tokens):
        return False
    return all(_cross_script_word_match(dw, rw) for dw, rw in zip(dev_tokens, rom_tokens))


def normalise_name(name: str) -> str:
    """Return case-folded, whitespace-collapsed NFKC form of a person name."""
    cleaned = unicodedata.normalize("NFKC", str(name)).strip()
    return " ".join(cleaned.split()).casefold()


def normalise_value(node_type: str, raw_value: str) -> str:
    """Normalise non-person identifier values while preserving leading digits."""
    s = unicodedata.normalize("NFKC", str(raw_value)).strip()
    if node_type == "PHONE":
        digits = re.sub(r"\D", "", s)
        if len(digits) == 12 and digits.startswith("91"):
            return digits[2:]
        if len(digits) == 11 and digits.startswith("0"):
            return digits[1:]
        return digits if digits else s
    if node_type in ("IMEI", "AADHAAR"):
        digits = re.sub(r"[\s-]", "", s)
        return digits
    if node_type == "ACCOUNT":
        # Keep leading zeros intact; only strip whitespace/hyphens.
        return re.sub(r"[\s-]", "", s)
    if node_type in ("PAN", "VEHICLE"):
        return re.sub(r"[\s-]", "", s).upper()
    if node_type == "UPI":
        return s.lower()
    return s


def _parse_paise(amount_str: Any) -> int:
    """Parse a decimal rupee string/number into exact integer paise."""
    d = Decimal(str(amount_str).strip())
    paise = (d * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(paise)


def _format_paise(paise: int) -> str:
    """Format integer paise as a 2-decimal rupee string."""
    sign = "-" if paise < 0 else ""
    abs_p = abs(paise)
    return f"{sign}{abs_p // 100}.{abs_p % 100:02d}"


def _time_sort_key(ts: str) -> tuple[int, Any, str]:
    """Return a comparable key for ISO-8601 timestamps with string fallback."""
    try:
        return (0, datetime.fromisoformat(ts), ts)
    except ValueError:
        return (1, ts, ts)


def _min_time(cur: str | None, candidate: str) -> str:
    if cur is None:
        return candidate
    return candidate if _time_sort_key(candidate) < _time_sort_key(cur) else cur


def _max_time(cur: str | None, candidate: str) -> str:
    if cur is None:
        return candidate
    return candidate if _time_sort_key(candidate) > _time_sort_key(cur) else cur


def _collect_fir_files(fir_dir: Path) -> list[Path]:
    """Return sorted FIR analysis JSON files in fir_dir."""
    analysis_files = sorted(fir_dir.glob("*.analysis.json"))
    if analysis_files:
        return analysis_files
    return sorted(p for p in fir_dir.iterdir() if p.is_file() and p.suffix == ".json")


def _extract_mentions(ent: dict[str, Any]) -> list[dict[str, Any]]:
    mentions: list[dict[str, Any]] = []
    for m in ent.get("mentions", []):
        span = list(m.get("char_span", []))
        mentions.append(
            {
                "char_span": span,
                "kind": m.get("kind", ""),
                "surface": m.get("surface", ""),
            }
        )
    mentions.sort(
        key=lambda m: (
            m["char_span"][0] if len(m["char_span"]) >= 1 else -1,
            m["char_span"][1] if len(m["char_span"]) >= 2 else -1,
            m["kind"],
            m["surface"],
        )
    )
    return mentions


def _choose_canonical_name(raw_names: list[str]) -> str:
    counts = Counter(raw_names)
    # Most frequent display string; break ties lexicographically for determinism.
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]


class _UnionFind:
    def __init__(self, n: int) -> None:
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            if ra < rb:
                self.parent[rb] = ra
            else:
                self.parent[ra] = rb


def _load_fir_documents(fir_files: list[Path]) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for path in fir_files:
        with path.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
        doc = payload["doc"] if isinstance(payload.get("doc"), dict) else payload
        docs.append(doc)
    docs.sort(key=lambda d: str(d.get("source_doc_id", "")))
    return docs


def _fathers_conflict(fathers_a: set[str], fathers_b: set[str]) -> bool:
    """Return True if both sides have father names and none match."""
    if not fathers_a or not fathers_b:
        return False
    norm_a = {normalise_name(f) for f in fathers_a if normalise_name(f)}
    norm_b = {normalise_name(f) for f in fathers_b if normalise_name(f)}
    if not norm_a or not norm_b:
        return False
    if norm_a & norm_b:
        return False
    for fa in fathers_a:
        for fb in fathers_b:
            if cross_script_names_match(fa, fb):
                return False
    return True


def _any_cross_script_match(names_a: set[str], names_b: set[str]) -> bool:
    return any(cross_script_names_match(na, nb) for na in names_a for nb in names_b)


def _merge_persons_and_collect_nodes(
    docs: list[dict[str, Any]],
) -> tuple[
    dict[str, dict[str, Any]],
    dict[tuple[str, str], str],
    int,
    int,
    dict[str, int],
    list[dict[str, Any]],
    int,
]:
    """Merge PERSON mentions across FIRs and collect all FIR non-person nodes."""
    person_records: list[dict[str, Any]] = []
    non_person_nodes: dict[str, dict[str, Any]] = {}
    local_non_person_id: dict[tuple[str, str], str] = {}

    for doc in docs:
        fir_id = str(doc["source_doc_id"])
        entities_by_id: dict[str, dict[str, Any]] = {
            str(e["id"]): e for e in doc.get("entities", [])
        }

        strong_ids_by_local_person: dict[str, set[tuple[str, str]]] = defaultdict(set)
        for rel in doc.get("relationships", []):
            rel_name = rel.get("relation")
            expected_tgt_type = STRONG_ID_RELATIONS.get(rel_name)
            if expected_tgt_type is None:
                continue
            src_ent = entities_by_id.get(str(rel.get("source")))
            tgt_ent = entities_by_id.get(str(rel.get("target")))
            if (
                src_ent is not None
                and tgt_ent is not None
                and src_ent.get("type") == "PERSON"
                and tgt_ent.get("type") == expected_tgt_type
            ):
                norm_val = normalise_value(expected_tgt_type, tgt_ent.get("value", ""))
                if norm_val:
                    strong_ids_by_local_person[str(src_ent["id"])].add(
                        (expected_tgt_type, norm_val)
                    )

        for ent in doc.get("entities", []):
            etype = str(ent["type"])
            eid = str(ent["id"])
            if etype not in ALLOWED_NODE_TYPES:
                raise ValueError(f"Unsupported entity type {etype!r} in {fir_id}")

            evidence_entry = {
                "char_span": list(ent.get("char_span", [])),
                "entity_id": eid,
                "fir_id": fir_id,
                "mentions": _extract_mentions(ent),
            }

            if etype == "PERSON":
                raw_cname = str(ent.get("canonical_name", "")).strip()
                raw_fathers: set[str] = set()
                if ent.get("father_name") and str(ent["father_name"]).strip():
                    raw_fathers.add(str(ent["father_name"]).strip())
                for men in evidence_entry["mentions"]:
                    if men["kind"] == "FATHER" and str(men["surface"]).strip():
                        raw_fathers.add(str(men["surface"]).strip())
                norm_fathers = {
                    normalise_name(fn) for fn in raw_fathers if normalise_name(fn)
                }
                roles = (
                    {str(ent["role"]).strip().upper()}
                    if ent.get("role") and str(ent["role"]).strip()
                    else set()
                )
                person_records.append(
                    {
                        "fir_id": fir_id,
                        "entity_id": eid,
                        "canonical_name": raw_cname,
                        "norm_name": normalise_name(raw_cname),
                        "raw_fathers": raw_fathers,
                        "norm_fathers": norm_fathers,
                        "roles": roles,
                        "is_suspect": "SUSPECT" in roles,
                        "entity": ent,
                        "evidence": evidence_entry,
                        "strong_ids": strong_ids_by_local_person.get(eid, set()),
                    }
                )
            else:
                norm_val = normalise_value(etype, ent.get("value", ""))
                node_id = f"{etype}:{norm_val}"
                local_non_person_id[(fir_id, eid)] = node_id
                if node_id not in non_person_nodes:
                    non_person_nodes[node_id] = {
                        "evidence_spans": [],
                        "id": node_id,
                        "source_files": set(),
                        "source_firs": set(),
                        "type": etype,
                        "value": norm_val,
                    }
                node = non_person_nodes[node_id]
                node["source_firs"].add(fir_id)
                node["evidence_spans"].append(evidence_entry)

    persons_before = len(person_records)
    person_records.sort(key=lambda r: (r["fir_id"], r["entity_id"]))

    uf = _UnionFind(persons_before)
    c_is_suspect = [rec["is_suspect"] for rec in person_records]
    c_norm_names = [
        {rec["norm_name"]} if rec["norm_name"] else set() for rec in person_records
    ]
    c_raw_names = [
        {rec["canonical_name"]} if rec["canonical_name"] else set()
        for rec in person_records
    ]
    c_raw_fathers = [set(rec["raw_fathers"]) for rec in person_records]
    c_norm_fathers = [set(rec["norm_fathers"]) for rec in person_records]
    c_strong_ids = [set(rec["strong_ids"]) for rec in person_records]
    c_anchor = list(range(persons_before))

    def _merge_clusters(ra: int, rb: int) -> None:
        if ra == rb:
            return
        keep, drop = (ra, rb) if ra < rb else (rb, ra)
        uf.union(keep, drop)
        c_is_suspect[keep] = c_is_suspect[keep] or c_is_suspect[drop]
        c_norm_names[keep].update(c_norm_names[drop])
        c_raw_names[keep].update(c_raw_names[drop])
        c_raw_fathers[keep].update(c_raw_fathers[drop])
        c_norm_fathers[keep].update(c_norm_fathers[drop])
        c_strong_ids[keep].update(c_strong_ids[drop])
        c_anchor[keep] = min(c_anchor[keep], c_anchor[drop])

    merges_by_rule: dict[str, int] = {"old_rule": 0, "rule_A": 0, "rule_B": 0}
    blocked_pairs: set[tuple[int, int]] = set()

    # Pass 1 (old_rule): same normalised name + shared strong ID.
    for i in range(persons_before):
        for j in range(i + 1, persons_before):
            ra, rb = uf.find(i), uf.find(j)
            if ra == rb:
                continue
            if (c_norm_names[ra] & c_norm_names[rb]) and (
                c_strong_ids[ra] & c_strong_ids[rb]
            ):
                if (
                    c_is_suspect[ra]
                    and c_is_suspect[rb]
                    and _fathers_conflict(c_raw_fathers[ra], c_raw_fathers[rb])
                ):
                    a1, a2 = c_anchor[ra], c_anchor[rb]
                    blocked_pairs.add((min(a1, a2), max(a1, a2)))
                    continue
                _merge_clusters(ra, rb)
                merges_by_rule["old_rule"] += 1

    # Pass 2 (rule_A, suspects): same normalised name + equal normalised father name.
    for i in range(persons_before):
        for j in range(i + 1, persons_before):
            ra, rb = uf.find(i), uf.find(j)
            if ra == rb:
                continue
            if not (c_is_suspect[ra] and c_is_suspect[rb]):
                continue
            if (c_norm_names[ra] & c_norm_names[rb]) and (
                c_norm_fathers[ra] & c_norm_fathers[rb]
            ):
                if _fathers_conflict(c_raw_fathers[ra], c_raw_fathers[rb]):
                    a1, a2 = c_anchor[ra], c_anchor[rb]
                    blocked_pairs.add((min(a1, a2), max(a1, a2)))
                    continue
                _merge_clusters(ra, rb)
                merges_by_rule["rule_A"] += 1

    # Pass 3 (rule_B, suspects): cross-script name match + shared strong ID.
    for i in range(persons_before):
        for j in range(i + 1, persons_before):
            ra, rb = uf.find(i), uf.find(j)
            if ra == rb:
                continue
            if not (c_is_suspect[ra] and c_is_suspect[rb]):
                continue
            if (c_strong_ids[ra] & c_strong_ids[rb]) and _any_cross_script_match(
                c_raw_names[ra], c_raw_names[rb]
            ):
                if _fathers_conflict(c_raw_fathers[ra], c_raw_fathers[rb]):
                    a1, a2 = c_anchor[ra], c_anchor[rb]
                    blocked_pairs.add((min(a1, a2), max(a1, a2)))
                    continue
                _merge_clusters(ra, rb)
                merges_by_rule["rule_B"] += 1

    clusters: dict[int, list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    for idx, rec in enumerate(person_records):
        clusters[uf.find(idx)].append((idx, rec))

    nodes: dict[str, dict[str, Any]] = {}
    for nid, n in non_person_nodes.items():
        nodes[nid] = n

    local_to_node_id: dict[tuple[str, str], str] = dict(local_non_person_id)
    used_person_ids: set[str] = set()
    node_anchor_idx: dict[str, int] = {}

    for root in sorted(clusters.keys()):
        indexed_members = sorted(
            clusters[root], key=lambda item: (item[1]["fir_id"], item[1]["entity_id"])
        )
        anchor = indexed_members[0][1]
        base_id = f"PERSON:{anchor['fir_id']}:{anchor['entity_id']}"
        node_id = base_id
        suffix = 2
        while node_id in used_person_ids:
            node_id = f"{base_id}#{suffix}"
            suffix += 1
        used_person_ids.add(node_id)
        node_anchor_idx[node_id] = min(item[0] for item in indexed_members)

        canonical_candidates: list[str] = []
        names: set[str] = set()
        aliases: set[str] = set()
        father_names: set[str] = set()
        roles: set[str] = set()
        source_firs: set[str] = set()
        evidence_spans: list[dict[str, Any]] = []

        for _, m in indexed_members:
            ent = m["entity"]
            source_firs.add(m["fir_id"])
            evidence_spans.append(m["evidence"])
            if m["canonical_name"]:
                canonical_candidates.append(m["canonical_name"])
                names.add(m["canonical_name"])
            for al in ent.get("aliases", []):
                if str(al).strip():
                    aliases.add(str(al).strip())
            if ent.get("father_name"):
                father_names.add(str(ent["father_name"]).strip())
            if ent.get("role"):
                roles.add(str(ent["role"]).strip())
            for men in m["evidence"]["mentions"]:
                kind = men["kind"]
                surf = str(men["surface"]).strip()
                if not surf:
                    continue
                if kind == "NAME":
                    names.add(surf)
                elif kind == "ALIAS":
                    aliases.add(surf)
                elif kind == "FATHER":
                    father_names.add(surf)
            local_to_node_id[(m["fir_id"], m["entity_id"])] = node_id

        evidence_spans.sort(
            key=lambda ev: (
                ev["fir_id"],
                ev["entity_id"],
                ev["char_span"][0] if len(ev["char_span"]) >= 1 else -1,
                ev["char_span"][1] if len(ev["char_span"]) >= 2 else -1,
            )
        )

        nodes[node_id] = {
            "aliases": sorted(aliases),
            "canonical_name": _choose_canonical_name(canonical_candidates) if canonical_candidates else "",
            "evidence_spans": evidence_spans,
            "father_names": sorted(father_names),
            "id": node_id,
            "names": sorted(names),
            "roles": sorted(roles),
            "source_firs": sorted(source_firs),
            "type": "PERSON",
        }

    # Suggested layer: SAME_AS_CANDIDATE star edges between unmerged suspect nodes.
    suspect_nodes = sorted(
        (
            n
            for n in nodes.values()
            if n["type"] == "PERSON" and "SUSPECT" in n.get("roles", [])
        ),
        key=lambda n: n["id"],
    )
    m_cnt = len(suspect_nodes)
    cand_uf = _UnionFind(m_cnt)
    cand_fathers = [set(n["father_names"]) for n in suspect_nodes]

    for i in range(m_cnt):
        ui = suspect_nodes[i]
        ui_raw = set(ui["names"])
        ui_norm = {normalise_name(x) for x in ui_raw if normalise_name(x)}
        for j in range(i + 1, m_cnt):
            uj = suspect_nodes[j]
            ri, rj = cand_uf.find(i), cand_uf.find(j)
            if ri == rj:
                continue
            uj_raw = set(uj["names"])
            uj_norm = {normalise_name(x) for x in uj_raw if normalise_name(x)}
            same_name = bool(ui_norm & uj_norm)
            cross_name = _any_cross_script_match(ui_raw, uj_raw)
            if not (same_name or cross_name):
                continue
            if _fathers_conflict(cand_fathers[ri], cand_fathers[rj]):
                a1 = node_anchor_idx[ui["id"]]
                a2 = node_anchor_idx[uj["id"]]
                blocked_pairs.add((min(a1, a2), max(a1, a2)))
                continue
            keep, drop = (ri, rj) if ri < rj else (rj, ri)
            cand_uf.union(keep, drop)
            cand_fathers[keep].update(cand_fathers[drop])

    cand_groups: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for idx, node in enumerate(suspect_nodes):
        cand_groups[cand_uf.find(idx)].append(node)

    candidate_edges: list[dict[str, Any]] = []
    for group in cand_groups.values():
        if len(group) < 2:
            continue
        group.sort(key=lambda n: n["id"])
        hub = group[0]
        hub_raw = set(hub["names"])
        hub_norm = {normalise_name(x) for x in hub_raw if normalise_name(x)}
        for member in group[1:]:
            mem_raw = set(member["names"])
            mem_norm = {normalise_name(x) for x in mem_raw if normalise_name(x)}
            reasons: list[str] = []
            if mem_norm & hub_norm:
                reasons.append("same_name")
            if _any_cross_script_match(mem_raw, hub_raw):
                reasons.append("cross_script_name")
            if not reasons:
                reasons.append("cross_script_name")
            candidate_edges.append(
                {
                    "reasons": sorted(reasons),
                    "relation": "SAME_AS_CANDIDATE",
                    "source": member["id"],
                    "source_kind": "RULE",
                    "target": hub["id"],
                }
            )

    persons_after = len(clusters)
    return (
        nodes,
        local_to_node_id,
        persons_before,
        persons_after,
        merges_by_rule,
        candidate_edges,
        len(blocked_pairs),
    )


def _ensure_non_person_node(
    nodes: dict[str, dict[str, Any]],
    node_type: str,
    raw_value: str,
    source_file: str,
) -> str:
    norm_val = normalise_value(node_type, raw_value)
    node_id = f"{node_type}:{norm_val}"
    if node_id not in nodes:
        nodes[node_id] = {
            "evidence_spans": [],
            "id": node_id,
            "source_files": set(),
            "source_firs": set(),
            "type": node_type,
            "value": norm_val,
        }
    nodes[node_id]["source_files"].add(source_file)
    return node_id


def _collect_fir_edges(
    docs: list[dict[str, Any]],
    local_to_node_id: dict[tuple[str, str], str],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}

    for doc in docs:
        fir_id = str(doc["source_doc_id"])
        for rel in doc.get("relationships", []):
            rel_type = str(rel["relation"])
            if rel_type not in CONTRACT_RELATION_TYPES:
                raise ValueError(f"Unsupported relation type {rel_type!r} in {fir_id}")

            src_key = (fir_id, str(rel["source"]))
            tgt_key = (fir_id, str(rel["target"]))
            if src_key not in local_to_node_id or tgt_key not in local_to_node_id:
                raise ValueError(
                    f"Broken entity reference in {fir_id} relationship: {rel!r}"
                )
            src_id = local_to_node_id[src_key]
            tgt_id = local_to_node_id[tgt_key]

            key = (src_id, tgt_id, rel_type)
            if key not in grouped:
                grouped[key] = {
                    "amounts_paise": [],
                    "evidence_spans": [],
                    "relation": rel_type,
                    "source": src_id,
                    "source_firs": set(),
                    "source_kind": "FIR",
                    "target": tgt_id,
                }
            entry = grouped[key]
            entry["source_firs"].add(fir_id)

            ev: dict[str, Any] = {"fir_id": fir_id}
            if "evidence_char_span" in rel and rel["evidence_char_span"] is not None:
                ev["evidence_char_span"] = list(rel["evidence_char_span"])
            if rel.get("trigger") is not None:
                ev["trigger"] = rel["trigger"]
            if rel.get("confidence") is not None:
                ev["confidence"] = rel["confidence"]
            if "amount" in rel and rel["amount"] is not None:
                paise = _parse_paise(rel["amount"])
                entry["amounts_paise"].append(paise)
                ev["amount_paise"] = paise
                ev["amount"] = _format_paise(paise)
            entry["evidence_spans"].append(ev)

    edges: list[dict[str, Any]] = []
    for entry in grouped.values():
        entry["evidence_spans"].sort(
            key=lambda ev: (
                ev["fir_id"],
                ev.get("evidence_char_span", [-1, -1])[0],
                ev.get("evidence_char_span", [-1, -1])[1],
                str(ev.get("trigger", "")),
            )
        )
        edge_dict: dict[str, Any] = {
            "evidence_spans": entry["evidence_spans"],
            "relation": entry["relation"],
            "source": entry["source"],
            "source_firs": sorted(entry["source_firs"]),
            "source_kind": "FIR",
            "target": entry["target"],
        }
        if entry["amounts_paise"]:
            total_paise = sum(entry["amounts_paise"])
            edge_dict["total_amount_paise"] = total_paise
            edge_dict["total_amount"] = _format_paise(total_paise)
        edges.append(edge_dict)

    return edges


def _collect_cdr_edges(
    cdr_path: Path,
    nodes: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], int, int]:
    comm_groups: dict[tuple[str, str], dict[str, Any]] = {}
    imei_groups: dict[tuple[str, str], dict[str, Any]] = {}

    rows_read = 0
    rows_skipped = 0

    with cdr_path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row_num, row in enumerate(reader, start=1):
            rows_read += 1
            raw_a = str(row.get("a_party", "")).strip()
            raw_b = str(row.get("b_party", "")).strip()
            norm_a = normalise_value("PHONE", raw_a)
            norm_b = normalise_value("PHONE", raw_b)

            if norm_a == norm_b:
                rows_skipped += 1
                continue

            node_a = _ensure_non_person_node(nodes, "PHONE", raw_a, "cdr.csv")
            node_b = _ensure_non_person_node(nodes, "PHONE", raw_b, "cdr.csv")

            src_comm, tgt_comm = sorted((node_a, node_b))
            call_type = str(row.get("call_type", "")).strip().upper()
            duration_str = str(row.get("duration_sec", "0")).strip()
            duration_sec = int(duration_str) if duration_str else 0
            start_time = str(row.get("start_time", "")).strip()

            ckey = (src_comm, tgt_comm)
            if ckey not in comm_groups:
                comm_groups[ckey] = {
                    "first_time": None,
                    "last_time": None,
                    "row_numbers": [],
                    "sms_count": 0,
                    "total_duration_sec": 0,
                    "voice_count": 0,
                }
            cg = comm_groups[ckey]
            if call_type == "VOICE":
                cg["voice_count"] += 1
            elif call_type == "SMS":
                cg["sms_count"] += 1
            cg["total_duration_sec"] += duration_sec
            if start_time:
                cg["first_time"] = _min_time(cg["first_time"], start_time)
                cg["last_time"] = _max_time(cg["last_time"], start_time)
            cg["row_numbers"].append(row_num)

            raw_imei = str(row.get("imei_a", "")).strip()
            if raw_imei:
                node_imei = _ensure_non_person_node(nodes, "IMEI", raw_imei, "cdr.csv")
                ikey = (node_a, node_imei)
                if ikey not in imei_groups:
                    imei_groups[ikey] = {
                        "first_time": None,
                        "last_time": None,
                        "row_count": 0,
                        "row_numbers": [],
                    }
                ig = imei_groups[ikey]
                ig["row_count"] += 1
                if start_time:
                    ig["first_time"] = _min_time(ig["first_time"], start_time)
                    ig["last_time"] = _max_time(ig["last_time"], start_time)
                ig["row_numbers"].append(row_num)

    edges: list[dict[str, Any]] = []
    for (src, tgt), cg in comm_groups.items():
        edges.append(
            {
                "first_time": cg["first_time"] or "",
                "last_time": cg["last_time"] or "",
                "relation": "COMMUNICATED_WITH",
                "row_numbers": sorted(cg["row_numbers"]),
                "sms_count": cg["sms_count"],
                "source": src,
                "source_file": "cdr.csv",
                "source_kind": "CSV",
                "target": tgt,
                "total_duration_sec": cg["total_duration_sec"],
                "voice_count": cg["voice_count"],
            }
        )

    for (src, tgt), ig in imei_groups.items():
        edges.append(
            {
                "first_time": ig["first_time"] or "",
                "last_time": ig["last_time"] or "",
                "relation": "ASSOCIATED_IMEI",
                "row_count": ig["row_count"],
                "row_numbers": sorted(ig["row_numbers"]),
                "source": src,
                "source_file": "cdr.csv",
                "source_kind": "CSV",
                "target": tgt,
            }
        )

    return edges, rows_read, rows_skipped


def _collect_bank_edges(
    bank_path: Path,
    nodes: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    bank_groups: dict[tuple[str, str], dict[str, Any]] = {}
    rows_read = 0

    with bank_path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row_num, row in enumerate(reader, start=1):
            rows_read += 1
            raw_from = str(row.get("from_acct", "")).strip()
            raw_to = str(row.get("to_acct", "")).strip()
            node_from = _ensure_non_person_node(nodes, "ACCOUNT", raw_from, "bank.csv")
            node_to = _ensure_non_person_node(nodes, "ACCOUNT", raw_to, "bank.csv")

            paise = _parse_paise(row.get("amount", "0"))
            mode = str(row.get("mode", "")).strip()
            dt = str(row.get("datetime", "")).strip()

            bkey = (node_from, node_to)
            if bkey not in bank_groups:
                bank_groups[bkey] = {
                    "first_time": None,
                    "last_time": None,
                    "modes": set(),
                    "row_numbers": [],
                    "total_amount_paise": 0,
                    "txn_count": 0,
                }
            bg = bank_groups[bkey]
            bg["txn_count"] += 1
            bg["total_amount_paise"] += paise
            if mode:
                bg["modes"].add(mode)
            if dt:
                bg["first_time"] = _min_time(bg["first_time"], dt)
                bg["last_time"] = _max_time(bg["last_time"], dt)
            bg["row_numbers"].append(row_num)

    edges: list[dict[str, Any]] = []
    for (src, tgt), bg in bank_groups.items():
        total_paise = bg["total_amount_paise"]
        edges.append(
            {
                "first_time": bg["first_time"] or "",
                "last_time": bg["last_time"] or "",
                "modes": sorted(bg["modes"]),
                "relation": "TRANSFERRED_FUNDS",
                "row_numbers": sorted(bg["row_numbers"]),
                "source": src,
                "source_file": "bank.csv",
                "source_kind": "CSV",
                "target": tgt,
                "total_amount": _format_paise(total_paise),
                "total_amount_paise": total_paise,
                "txn_count": bg["txn_count"],
            }
        )

    return edges, rows_read


def _finalise_nodes(nodes: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for nid in sorted(nodes.keys()):
        node = dict(nodes[nid])
        if node["type"] != "PERSON":
            node["source_firs"] = sorted(node["source_firs"])
            node["source_files"] = sorted(node["source_files"])
            node["evidence_spans"] = sorted(
                node["evidence_spans"],
                key=lambda ev: (
                    ev["fir_id"],
                    ev["entity_id"],
                    ev["char_span"][0] if len(ev["char_span"]) >= 1 else -1,
                    ev["char_span"][1] if len(ev["char_span"]) >= 2 else -1,
                ),
            )
        result.append(node)
    return result


def _build_stats(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    fir_files_read: int,
    persons_before: int,
    persons_after: int,
    merges_by_rule: dict[str, int],
    same_as_candidate_edges: int,
    blocked_by_father_conflict: int,
    cdr_rows_read: int,
    cdr_rows_skipped: int,
    bank_rows_read: int,
) -> dict[str, Any]:
    node_counts_by_type = Counter(n["type"] for n in nodes)
    contract_edges = [e for e in edges if e["relation"] in CONTRACT_RELATION_TYPES]
    edge_counts_by_type = Counter(e["relation"] for e in contract_edges)
    edge_counts_by_source_kind = Counter(e["source_kind"] for e in contract_edges)
    by_type_kind: dict[str, dict[str, int]] = defaultdict(dict)
    for rel in sorted(edge_counts_by_type.keys()):
        for kind in ("CSV", "FIR"):
            cnt = sum(
                1
                for e in contract_edges
                if e["relation"] == rel and e["source_kind"] == kind
            )
            if cnt:
                by_type_kind[rel][kind] = cnt

    return {
        "bank_rows_read": bank_rows_read,
        "blocked_by_father_conflict": blocked_by_father_conflict,
        "cdr_rows_read": cdr_rows_read,
        "cdr_rows_skipped": cdr_rows_skipped,
        "edge_counts_by_source_kind": {
            k: edge_counts_by_source_kind[k] for k in sorted(edge_counts_by_source_kind)
        },
        "edge_counts_by_type": {
            k: edge_counts_by_type[k] for k in sorted(edge_counts_by_type)
        },
        "edge_counts_by_type_and_source_kind": dict(sorted(by_type_kind.items())),
        "fir_files_read": fir_files_read,
        "merges_by_rule": {
            "old_rule": merges_by_rule.get("old_rule", 0),
            "rule_A": merges_by_rule.get("rule_A", 0),
            "rule_B": merges_by_rule.get("rule_B", 0),
        },
        "node_counts_by_type": {
            k: node_counts_by_type[k] for k in sorted(node_counts_by_type)
        },
        "persons_after_merge": persons_after,
        "persons_before_merge": persons_before,
        "same_as_candidate_edges": same_as_candidate_edges,
        "total_edges": len(edges),
        "total_nodes": len(nodes),
    }


def build_case_graph(
    fir_dir: str | Path,
    cdr_path: str | Path,
    bank_path: str | Path,
) -> dict[str, Any]:
    """Build a deterministic case graph and stats from FIR outputs, CDR, and Bank CSVs."""
    fir_dir_path = Path(fir_dir)
    cdr_file_path = Path(cdr_path)
    bank_file_path = Path(bank_path)

    fir_files = _collect_fir_files(fir_dir_path)
    docs = _load_fir_documents(fir_files)

    (
        nodes_map,
        local_to_node_id,
        persons_before,
        persons_after,
        merges_by_rule,
        candidate_edges,
        blocked_by_father_conflict,
    ) = _merge_persons_and_collect_nodes(docs)
    fir_edges = _collect_fir_edges(docs, local_to_node_id)
    cdr_edges, cdr_rows_read, cdr_rows_skipped = _collect_cdr_edges(
        cdr_file_path, nodes_map
    )
    bank_edges, bank_rows_read = _collect_bank_edges(bank_file_path, nodes_map)

    final_nodes = _finalise_nodes(nodes_map)
    all_edges = fir_edges + cdr_edges + bank_edges + candidate_edges
    all_edges.sort(
        key=lambda e: (e["source"], e["target"], e["relation"], e["source_kind"])
    )

    stats = _build_stats(
        nodes=final_nodes,
        edges=all_edges,
        fir_files_read=len(fir_files),
        persons_before=persons_before,
        persons_after=persons_after,
        merges_by_rule=merges_by_rule,
        same_as_candidate_edges=len(candidate_edges),
        blocked_by_father_conflict=blocked_by_father_conflict,
        cdr_rows_read=cdr_rows_read,
        cdr_rows_skipped=cdr_rows_skipped,
        bank_rows_read=bank_rows_read,
    )

    return {
        "edges": all_edges,
        "nodes": final_nodes,
        "stats": stats,
    }

