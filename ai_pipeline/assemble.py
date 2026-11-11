"""
Step 6b-1: Entity assembly into Contract 1 v1.1 format.
Combines postprocessed NER person/alias/father/role spans with resolved Indian identifiers
into deduplicated entities, validated against contracts/v1_1/ai_output_schema.json.
"""
from __future__ import annotations

import re
from typing import Any

from ai_pipeline.identifiers import find_all_identifiers
from ai_pipeline.names import extract_names, strip_honorific
from ai_pipeline.ner_baseline import postprocess
from ai_pipeline.validators import Candidate
from contracts.v1_1.validate import validate_ai_output

_ID_ENTITY_TYPES: frozenset[str] = frozenset({
    "PHONE", "IMEI", "ACCOUNT", "AADHAAR", "PAN", "UPI", "VEHICLE",
})

_BANK_CANONICAL: dict[str, str] = {
    "sbi": "SBI",
    "hdfc": "HDFC",
    "icici": "ICICI",
    "pnb": "PNB",
    "axis": "Axis",
    "kotak": "Kotak",
}
_BANK_RE = re.compile(r"\b(SBI|HDFC|ICICI|PNB|Axis|Kotak)\b", re.IGNORECASE)

_ABBREV_DOTS_RE = re.compile(
    r"\b(?:a\.k\.a\.|Mr\.|Mrs\.|Ms\.|Dr\.|Sh\.|Smt\.|Shri\.|Sri\.|Shree\.|Kumari\.)",
    re.IGNORECASE,
)
_SENT_BOUNDARY_RE = re.compile(r"[.!?।\u0965\n]")


def _normalize_person_key(surface: str) -> str:
    """Normalize a person name for exact entity merging (honorific stripped, whitespace collapsed, casefold)."""
    ns, ne = strip_honorific(surface, 0, len(surface))
    stripped = surface[ns:ne] if ns < ne else surface
    return " ".join(stripped.split()).casefold()


def _same_sentence(text: str, prev_end: int, next_start: int) -> bool:
    """Return True if no sentence boundary separates text[prev_end:next_start]."""
    if prev_end > next_start:
        return False
    between = text[prev_end:next_start]
    cleaned = _ABBREV_DOTS_RE.sub("", between)
    cleaned = re.sub(r"\d\.\d", "", cleaned)
    return not bool(_SENT_BOUNDARY_RE.search(cleaned))


def _detect_bank(text: str, start: int) -> str | None:
    """Return canonical bank name if SBI/HDFC/ICICI/PNB/Axis/Kotak appears within 25 chars before start."""
    window = text[max(0, start - 25):start]
    matches = list(_BANK_RE.finditer(window))
    if not matches:
        return None
    return _BANK_CANONICAL[matches[-1].group(1).lower()]


def _identifier_confidence(cand: Candidate) -> float:
    """Compute identifier confidence from validator flags."""
    if cand.valid:
        return 0.99
    if "CHECKSUM_INVALID" in cand.flags:
        return 0.6
    return 0.9


def _raw_overlap_score(
    start: int,
    end: int,
    raw_spans: list[dict[str, Any]],
) -> float | None:
    """Return max score among raw spans overlapping [start, end), or None if no scored overlap."""
    scores: list[float] = []
    for rsp in raw_spans:
        if "score" not in rsp or rsp["score"] is None:
            continue
        rs = int(rsp["start"])
        re_ = int(rsp["end"])
        if min(end, re_) > max(start, rs):
            scores.append(float(rsp["score"]))
    return max(scores) if scores else None


def _dedup_flags(flags: list[str]) -> list[str]:
    """Return flags de-duplicated in encounter order."""
    seen: set[str] = set()
    out: list[str] = []
    for fl in flags:
        if fl not in seen:
            seen.add(fl)
            out.append(fl)
    return out


def _preview_alias_and_father_attachments(
    text: str,
    name_spans: list[dict[str, Any]],
    person_mentions_order: list[dict[str, Any]],
) -> tuple[dict[str, set[str]], dict[str, set[str]], dict[str, set[str]]]:
    """Resolve provisional ALIAS/FATHER owners prior to Pass 2 so merge checks remain side-effect free."""
    alias_owners: dict[str, set[str]] = {}
    prov_aliases: dict[str, set[str]] = {}
    prov_fathers: dict[str, set[str]] = {}

    for sp in name_spans:
        sp_type = sp["type"]
        if sp_type == "ALIAS":
            owner_pm = None
            for pm in person_mentions_order:
                if pm["end"] <= sp["start"] and _same_sentence(text, pm["end"], sp["start"]):
                    owner_pm = pm
            norm_alias = _normalize_person_key(sp["surface"])
            owner_key = owner_pm["entity_key"] if owner_pm is not None else "__ORPHAN__"
            if norm_alias:
                alias_owners.setdefault(norm_alias, set()).add(owner_key)
            if owner_pm is not None and norm_alias:
                prov_aliases.setdefault(owner_key, set()).add(norm_alias)

        elif sp_type == "FATHER":
            owner_pm = None
            for pm in person_mentions_order:
                if pm["end"] <= sp["start"] and pm["role"] == "SUSPECT":
                    owner_pm = pm
            if owner_pm is not None:
                norm_father = _normalize_person_key(sp["surface"])
                if norm_father:
                    prov_fathers.setdefault(owner_pm["entity_key"], set()).add(norm_father)

    return alias_owners, prov_aliases, prov_fathers


def _merge_short_person_names(
    text: str,
    raw_spans: list[dict[str, Any]],
    name_spans: list[dict[str, Any]],
    person_groups: dict[str, dict[str, Any]],
    person_mentions_order: list[dict[str, Any]],
) -> tuple[int, list[dict[str, Any]]]:
    """
    Conservatively merge 1-token PERSON entities into a unique >=2-token PERSON entity
    sharing the exact same first token, same role, and no alias/father conflicts.
    """
    alias_owners, prov_aliases, prov_fathers = _preview_alias_and_father_attachments(
        text, name_spans, person_mentions_order
    )

    fuller_by_first: dict[str, list[str]] = {}
    short_keys: list[str] = []
    for key, grp in person_groups.items():
        toks = _normalize_person_key(grp["canonical_name"]).split()
        if len(toks) >= 2:
            fuller_by_first.setdefault(toks[0], []).append(key)
        elif len(toks) == 1:
            short_keys.append(key)

    merges = 0
    ambiguous: list[dict[str, Any]] = []

    for e_key in short_keys:
        e_grp = person_groups[e_key]
        tok = _normalize_person_key(e_grp["canonical_name"]).split()[0]

        # Aliases of other people (or unowned aliases) are never merged as first names
        if any(owner != e_key for owner in alias_owners.get(tok, ())):
            continue

        cands = fuller_by_first.get(tok, [])
        if not cands:
            continue

        if len(cands) >= 2:
            ambiguous.append({
                "short_name": e_grp["canonical_name"],
                "token": tok,
                "candidates": [person_groups[k]["canonical_name"] for k in cands],
            })
            continue

        f_key = cands[0]
        f_grp = person_groups[f_key]

        # Roles must match cleanly across entities and mentions (OFFICER/COMPLAINANT/WITNESS stay separate from SUSPECT)
        if e_grp["role"] != f_grp["role"] or any(
            pm["role"] != f_grp["role"] for pm in person_mentions_order if pm["entity_key"] == e_key
        ):
            continue

        # Short entity must not introduce an alias or father that differs from fuller entity
        if not prov_fathers.get(e_key, set()).issubset(prov_fathers.get(f_key, set())):
            continue
        if not prov_aliases.get(e_key, set()).issubset(prov_aliases.get(f_key, set())):
            continue

        f_grp["mentions"].extend(e_grp["mentions"])
        f_grp["mentions"].sort(key=lambda m: (m["char_span"][0], m["char_span"][1]))
        f_grp["scores"] = [
            sc
            for m in f_grp["mentions"]
            if m["kind"] == "NAME"
            for sc in (_raw_overlap_score(m["char_span"][0], m["char_span"][1], raw_spans),)
            if sc is not None
        ]
        f_grp["flags"].append("SHORT_NAME_MERGE")

        for pm in person_mentions_order:
            if pm["entity_key"] == e_key:
                pm["entity_key"] = f_key
                pm["role"] = f_grp["role"]

        del person_groups[e_key]
        merges += 1

    return merges, ambiguous


def assemble_entities(
    text: str,
    doc_id: str,
    raw_spans: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Assemble extracted person/alias/father spans and Indian identifiers into a Contract 1 v1.1
    document with entities sorted by first mention and relationships left empty.
    Returns (doc, aux).
    """
    if text == "":
        return (
            {
                "schema_version": "1.1",
                "case_id": "CASE_DEMO_V2",
                "source_doc_id": doc_id,
                "entities": [],
                "relationships": [],
            },
            {
                "amounts": [],
                "ifsc": [],
                "dropped": {"alias_no_owner": 0, "father_no_owner": 0},
            },
        )

    post_spans = postprocess(text, raw_spans)
    name_spans = extract_names(text, post_spans)
    id_candidates = find_all_identifiers(text)

    person_groups: dict[str, dict[str, Any]] = {}
    person_mentions_order: list[dict[str, Any]] = []

    # Pass 1: Group PERSON mentions by normalized name
    for sp in name_spans:
        if sp["type"] != "PERSON":
            continue
        key = _normalize_person_key(sp["surface"])
        if not key:
            continue

        if key not in person_groups:
            person_groups[key] = {
                "type": "PERSON",
                "canonical_name": sp["surface"],
                "role": sp["role"],
                "aliases": [],
                "father_name": None,
                "mentions": [],
                "scores": [],
                "flags": [],
            }

        grp = person_groups[key]
        grp["mentions"].append({
            "char_span": [sp["start"], sp["end"]],
            "surface": sp["surface"],
            "kind": "NAME",
        })
        sc = _raw_overlap_score(sp["start"], sp["end"], raw_spans)
        if sc is not None:
            grp["scores"].append(sc)

        person_mentions_order.append({
            "entity_key": key,
            "start": sp["start"],
            "end": sp["end"],
            "role": sp["role"],
        })

    # Pass 1b: Conservative short-name merge before attaching aliases and fathers
    short_name_merges, short_name_ambiguous = _merge_short_person_names(
        text, raw_spans, name_spans, person_groups, person_mentions_order
    )

    # Pass 2: Attach ALIAS and FATHER spans to nearest valid preceding person mention
    dropped_counts = {"alias_no_owner": 0, "father_no_owner": 0}
    for sp in name_spans:
        sp_type = sp["type"]
        if sp_type == "ALIAS":
            owner_pm = None
            for pm in person_mentions_order:
                if pm["end"] <= sp["start"] and _same_sentence(text, pm["end"], sp["start"]):
                    owner_pm = pm
            if owner_pm is None:
                dropped_counts["alias_no_owner"] += 1
                continue

            grp = person_groups[owner_pm["entity_key"]]
            grp["mentions"].append({
                "char_span": [sp["start"], sp["end"]],
                "surface": sp["surface"],
                "kind": "ALIAS",
            })
            if sp["surface"] not in grp["aliases"]:
                grp["aliases"].append(sp["surface"])
            grp["flags"].append("RULE_ALIAS")

        elif sp_type == "FATHER":
            owner_pm = None
            for pm in person_mentions_order:
                if pm["end"] <= sp["start"] and pm["role"] == "SUSPECT":
                    owner_pm = pm
            if owner_pm is None:
                dropped_counts["father_no_owner"] += 1
                continue

            grp = person_groups[owner_pm["entity_key"]]
            grp["mentions"].append({
                "char_span": [sp["start"], sp["end"]],
                "surface": sp["surface"],
                "kind": "FATHER",
            })
            if grp["father_name"] is None:
                grp["father_name"] = sp["surface"]
            grp["flags"].append("RULE_FATHER")

    # Pass 3: Group identifier entities and populate aux for AMOUNT and IFSC
    id_groups: dict[tuple[str, str], dict[str, Any]] = {}
    amounts_aux: list[dict[str, Any]] = []
    ifsc_aux: list[dict[str, Any]] = []

    for cand in id_candidates:
        if cand.type == "AMOUNT":
            amounts_aux.append({
                "value": float(cand.value),
                "start": cand.start,
                "end": cand.end,
                "surface": cand.surface,
            })
            continue

        if cand.type == "IFSC":
            ifsc_aux.append({
                "value": str(cand.value),
                "start": cand.start,
                "end": cand.end,
                "surface": cand.surface,
            })
            continue

        if cand.type not in _ID_ENTITY_TYPES:
            continue

        norm_val = str(cand.value)
        g_key = (cand.type, norm_val)
        if g_key not in id_groups:
            id_groups[g_key] = {
                "type": cand.type,
                "value": norm_val,
                "bank": None,
                "mentions": [],
                "confs": [],
                "flags": [],
            }

        grp = id_groups[g_key]
        grp["mentions"].append({
            "char_span": [cand.start, cand.end],
            "surface": cand.surface,
            "kind": "VALUE",
        })
        grp["confs"].append(_identifier_confidence(cand))
        grp["flags"].extend(cand.flags)

        if cand.type == "ACCOUNT" and grp["bank"] is None:
            detected_bank = _detect_bank(text, cand.start)
            if detected_bank is not None:
                grp["bank"] = detected_bank
                grp["flags"].append("BANK_CONTEXT")

    # Build final entities (unsorted by id, sorted by first mention)
    assembled: list[dict[str, Any]] = []

    for grp in person_groups.values():
        mentions = sorted(grp["mentions"], key=lambda m: (m["char_span"][0], m["char_span"][1]))
        scores = grp["scores"]
        if scores:
            mean_score = max(0.0, min(1.0, sum(scores) / len(scores)))
            ai_conf = round(mean_score, 6)
            model_bd: float | None = ai_conf
        else:
            ai_conf = 0.9
            model_bd = None

        ent: dict[str, Any] = {
            "type": "PERSON",
            "char_span": list(mentions[0]["char_span"]),
            "mentions": mentions,
            "canonical_name": grp["canonical_name"],
            "role": grp["role"],
            "ai_confidence": ai_conf,
            "confidence_breakdown": {
                "model": model_bd,
                "validator": None,
                "context": None,
            },
            "flags": _dedup_flags(grp["flags"]),
        }
        if grp["aliases"]:
            ent["aliases"] = grp["aliases"]
        if grp["father_name"] is not None:
            ent["father_name"] = grp["father_name"]
        assembled.append(ent)

    for grp in id_groups.values():
        mentions = sorted(grp["mentions"], key=lambda m: (m["char_span"][0], m["char_span"][1]))
        confs = grp["confs"]
        ai_conf = round(sum(confs) / len(confs), 6) if confs else 0.9
        context_bd: float | None = 1.0 if (grp["type"] == "ACCOUNT" and grp["bank"] is not None) else None

        ent = {
            "type": grp["type"],
            "char_span": list(mentions[0]["char_span"]),
            "mentions": mentions,
            "value": grp["value"],
            "ai_confidence": ai_conf,
            "confidence_breakdown": {
                "model": None,
                "validator": ai_conf,
                "context": context_bd,
            },
            "flags": _dedup_flags(grp["flags"]),
        }
        if grp["bank"] is not None:
            ent["bank"] = grp["bank"]
        assembled.append(ent)

    # Order entities by first mention span (min start, then end, then type)
    assembled.sort(key=lambda e: (e["char_span"][0], e["char_span"][1], e["type"]))

    entities: list[dict[str, Any]] = []
    for idx, ent in enumerate(assembled, start=1):
        ent_with_id = {"id": f"ent_{idx:02d}", **ent}
        entities.append(ent_with_id)

    doc: dict[str, Any] = {
        "schema_version": "1.1",
        "case_id": "CASE_DEMO_V2",
        "source_doc_id": doc_id,
        "entities": entities,
        "relationships": [],
    }
    aux: dict[str, Any] = {
        "amounts": amounts_aux,
        "ifsc": ifsc_aux,
        "dropped": dropped_counts,
        "short_name_merges": short_name_merges,
        "short_name_ambiguous": short_name_ambiguous,
    }

    if entities:
        validate_ai_output(doc)

    return doc, aux

