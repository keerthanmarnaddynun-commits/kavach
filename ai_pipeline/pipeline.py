"""
Step 6c: End-to-end NER, identifier, entity assembly, and hybrid relation pipeline.
Supports full offline transformer inference (Davlan XLM-R via ner_baseline),
injected raw spans for testing, and automatic degraded heuristic fallback.
"""
from __future__ import annotations

import hashlib
import os
import re
import time
from typing import Any

# Guarantee offline Hugging Face usage before importing ner_baseline
os.environ["HF_HUB_OFFLINE"] = "1"

from ai_pipeline import ner_baseline
from ai_pipeline.assemble import assemble_entities
from ai_pipeline.identifiers import find_all_identifiers
from ai_pipeline.names import extract_names
from ai_pipeline.relations import extract_relations_hybrid
from contracts.v1_1.validate import validate_ai_output

MAX_CHARS = 5000


class TextTooLong(Exception):
    """Raised when input text exceeds MAX_CHARS."""


class EmptyText(Exception):
    """Raised when input text is not a string, empty, or whitespace-only."""


class NoEntitiesFound(Exception):
    """Raised when pipeline processing yields zero entities."""


_STOP_LATIN: frozenset[str] = frozenset({
    "suspect", "accused", "complainant", "victim", "informant", "witness", "officer",
    "inspector", "duty", "investigating", "constable", "head", "shri", "sri", "shree",
    "smt", "mr", "mrs", "ms", "dr", "kumari", "police", "team", "wing", "station",
    "branch", "bank", "account", "mobile", "phone", "handset", "number", "calling",
    "connection", "syndicate", "member", "figure", "handler", "operator", "mule",
    "remitter", "beneficiary", "authorized", "signatory", "stewardship", "personal",
    "physical", "custody", "search", "upon", "the", "during", "from", "into", "under",
    "for", "with", "and", "co", "conspirator", "zabt", "zabti", "baramad", "case",
    "fir", "bns", "ipc", "cdr", "block", "lane", "sector", "house", "road", "near",
    "earlier", "later", "then", "today", "yesterday", "arrested", "apprehended",
    "booked", "recorded", "filed", "submitted", "seized", "recovered", "found",
    "caught", "this", "that", "here", "there", "monday", "tuesday", "wednesday",
    "thursday", "friday", "saturday", "sunday",
})

_STOP_DEVA: frozenset[str] = frozenset({
    "अभियुक्त", "सह-अभियुक्त", "आरोपी", "सह-आरोपी", "संदिग्ध", "वादी", "प्रार्थी",
    "शिकायतकर्ता", "पीड़ित", "पीड़िता", "गवाह", "साक्षी", "पंच", "निरीक्षक", "उप-निरीक्षक",
    "थाना", "प्रभारी", "थानाध्यक्ष", "आरक्षी", "विवेचक", "अधिकारी", "श्री", "श्रीमती",
    "श्रीमान", "उर्फ", "उर्फ़", "पुत्र", "पुत्री", "पत्नी", "आत्मज", "सुपुत्र", "निवासी",
    "ने", "को", "का", "की", "के", "से", "में", "पर", "द्वारा", "और", "भी", "यह", "वह",
    "था", "थे", "थी", "है", "हैं", "हुआ", "हुई", "किया", "गया", "गई", "जब्त", "जब्ती",
    "बरामद", "पुलिस", "मामले", "घटना", "तलाशी", "बैंक", "खाता", "रकम", "धनराशि",
    "फोन", "मोबाइल", "हैंडसेट", "नंबर", "सरगना", "सदस्य", "साथी", "संचालक", "प्रचालक",
})

_LATIN_BEFORE_RE = re.compile(
    r"(?=\b([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,}){1,2})"
    r"(?:\s+(?:\(\s*)?(?:(?i:urf|alias|aka|s/o|d/o|w/o)\b|(?i:a\.k\.a\.)(?!\w))|\s*@))"
)
_LATIN_AFTER_CUE_RE = re.compile(
    r"\b(suspect|accused|complainant|officer|inspector|shri|smt|mr|mrs)\.?\s+",
    re.IGNORECASE,
)
_LATIN_AFTER_NAME_RE = re.compile(r"([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,}){1,2})\b")

_DEVA_WORD = r"[\u0904-\u0939\u0958-\u0963\u0972-\u097f][\u0900-\u0939\u093c-\u094f\u0951-\u0963\u0970-\u097f]*"
_DEVA_BEFORE_RE = re.compile(
    rf"({_DEVA_WORD}(?:\s+{_DEVA_WORD}){{0,2}})"
    r"(?=\s+(?:उर्फ़|उर्फ|पुत्र)(?![\u0900-\u097f]))"
)
_DEVA_AFTER_RE = re.compile(
    rf"(?<![\u0900-\u097f])(?:श्रीमती|श्री)\.?\s+({_DEVA_WORD}(?:\s+{_DEVA_WORD}){{0,2}})"
)


def heuristic_person_spans(text: str) -> list[dict[str, Any]]:
    """
    Heuristic person extractor used in DEGRADED_NO_MODEL mode.
    Finds Latin 2-3 capitalized tokens (len >= 3) directly before alias/father cues
    or after role/honorific cues, plus Devanagari 1-3 word sequences directly before
    उर्फ/पुत्र or after श्री/श्रीमती, filtering out cue-only sequences.
    """
    if not text:
        return []

    spans: list[dict[str, Any]] = []

    # 1. Latin 2-3 tokens directly before alias or father cue
    for m in _LATIN_BEFORE_RE.finditer(text):
        s, e = m.start(1), m.end(1)
        parts = list(re.finditer(r"\S+", text[s:e]))
        while parts and parts[0].group(0).lower() in _STOP_LATIN:
            parts.pop(0)
        if 2 <= len(parts) <= 3 and not any(p.group(0).lower() in _STOP_LATIN for p in parts):
            ns, ne = s + parts[0].start(), s + parts[-1].end()
            spans.append({
                "type": "PERSON",
                "start": ns,
                "end": ne,
                "score": 0.5,
                "word": text[ns:ne],
            })

    # 2. Latin 2-3 tokens directly after role or honorific word
    for cm in _LATIN_AFTER_CUE_RE.finditer(text):
        nm = _LATIN_AFTER_NAME_RE.match(text, cm.end())
        if not nm:
            continue
        s, e = nm.start(1), nm.end(1)
        parts = list(re.finditer(r"\S+", text[s:e]))
        kept: list[re.Match[str]] = []
        for p in parts:
            if p.group(0).lower() in _STOP_LATIN:
                break
            kept.append(p)
        if 2 <= len(kept) <= 3:
            ns, ne = s + kept[0].start(), s + kept[-1].end()
            spans.append({
                "type": "PERSON",
                "start": ns,
                "end": ne,
                "score": 0.5,
                "word": text[ns:ne],
            })

    # 3. Devanagari 1-3 words directly before उर्फ or पुत्र
    for m in _DEVA_BEFORE_RE.finditer(text):
        s, e = m.start(1), m.end(1)
        parts = list(re.finditer(r"\S+", text[s:e]))
        while parts and parts[0].group(0) in _STOP_DEVA:
            parts.pop(0)
        while parts and parts[-1].group(0) in _STOP_DEVA:
            parts.pop()
        if 1 <= len(parts) <= 3:
            ns, ne = s + parts[0].start(), s + parts[-1].end()
            spans.append({
                "type": "PERSON",
                "start": ns,
                "end": ne,
                "score": 0.5,
                "word": text[ns:ne],
            })

    # 4. Devanagari 1-3 words directly after श्री or श्रीमती
    for m in _DEVA_AFTER_RE.finditer(text):
        s, e = m.start(1), m.end(1)
        parts = list(re.finditer(r"\S+", text[s:e]))
        kept = []
        for p in parts:
            if p.group(0) in _STOP_DEVA:
                break
            kept.append(p)
        if 1 <= len(kept) <= 3:
            ns, ne = s + kept[0].start(), s + kept[-1].end()
            spans.append({
                "type": "PERSON",
                "start": ns,
                "end": ne,
                "score": 0.5,
                "word": text[ns:ne],
            })

    return ner_baseline.postprocess(text, spans)


def analyze_text(
    text: str,
    doc_id: str = "DOC_001",
    case_id: str = "CASE_DEMO_V2",
    use_model: bool = True,
    raw_spans: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Run end-to-end FIR extraction and assembly pipeline:
    validation -> model (or heuristics) -> postprocess -> assemble -> relations -> validate_ai_output.
    Returns {"doc": ..., "aux": ..., "info": ...}.
    """
    if not isinstance(text, str) or not text.strip():
        raise EmptyText("Input text must be a non-empty string.")
    if len(text) > MAX_CHARS:
        raise TextTooLong(f"Input length {len(text)} exceeds MAX_CHARS={MAX_CHARS}.")

    t_start_total = time.perf_counter()
    warnings: list[str] = []
    default_model = ner_baseline.MODELS[0]

    # 1. Obtain raw person spans (injected, offline model, or degraded heuristic fallback)
    t0 = time.perf_counter()
    if raw_spans is not None:
        active_raw = raw_spans
        mode = "MODEL" if use_model else "DEGRADED_NO_MODEL"
        model_name: str | None = default_model if use_model else None
        if not use_model:
            warnings.append("Model disabled (use_model=False); persons come from provided spans.")
    elif not use_model:
        active_raw = heuristic_person_spans(text)
        mode = "DEGRADED_NO_MODEL"
        model_name = None
        warnings.append("DEGRADED_NO_MODEL mode: persons come from heuristics (use_model=False).")
    else:
        try:
            active_raw = ner_baseline.run_model(default_model, [text])[0]
            mode = "MODEL"
            model_name = default_model
        except Exception as exc:
            active_raw = heuristic_person_spans(text)
            mode = "DEGRADED_NO_MODEL"
            model_name = None
            warnings.append(
                f"Model unavailable ({exc}); persons come from heuristics (DEGRADED_NO_MODEL)."
            )
    t_model = (time.perf_counter() - t0) * 1000.0

    # 2. Postprocess model spans
    t0 = time.perf_counter()
    post_spans = ner_baseline.postprocess(text, active_raw)
    t_postprocess = (time.perf_counter() - t0) * 1000.0

    # 3. Extract names and Indian identifiers
    t0 = time.perf_counter()
    _ = extract_names(text, post_spans)
    _ = find_all_identifiers(text)
    t_names_ids = (time.perf_counter() - t0) * 1000.0

    # 4. Assemble Contract 1 v1.1 entities
    t0 = time.perf_counter()
    doc, aux = assemble_entities(text, doc_id, active_raw)
    doc["case_id"] = case_id
    doc["source_doc_id"] = doc_id
    t_assemble = (time.perf_counter() - t0) * 1000.0

    if not doc.get("entities"):
        raise NoEntitiesFound(f"No entities found in document {doc_id!r}.")

    # 5. Extract hybrid relationships
    t0 = time.perf_counter()
    doc["relationships"] = extract_relations_hybrid(text, doc, aux)
    t_relations = (time.perf_counter() - t0) * 1000.0

    # 6. Validate final Contract 1 v1.1 document
    t0 = time.perf_counter()
    try:
        validate_ai_output(doc)
    except Exception as exc:
        raise ValueError(str(exc)) from exc
    t_validate = (time.perf_counter() - t0) * 1000.0

    t_total = (time.perf_counter() - t_start_total) * 1000.0
    stage_max = max(t_model, t_postprocess, t_names_ids, t_assemble, t_relations, t_validate)
    t_total = max(t_total, stage_max)

    entities_by_type: dict[str, int] = {}
    for ent in doc["entities"]:
        et = ent["type"]
        entities_by_type[et] = entities_by_type.get(et, 0) + 1

    relations_by_label: dict[str, int] = {}
    rel_cue = 0
    rel_struct = 0
    for rel in doc["relationships"]:
        rl = rel["relation"]
        relations_by_label[rl] = relations_by_label.get(rl, 0) + 1
        if rel.get("trigger") == "STRUCTURE":
            rel_struct += 1
        else:
            rel_cue += 1

    info: dict[str, Any] = {
        "mode": mode,
        "model_name": model_name,
        "document_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "char_count": len(text),
        "timings_ms": {
            "model": round(t_model, 3),
            "postprocess": round(t_postprocess, 3),
            "names_identifiers": round(t_names_ids, 3),
            "assemble": round(t_assemble, 3),
            "relations": round(t_relations, 3),
            "validate": round(t_validate, 3),
            "total": round(t_total, 3),
        },
        "entities_by_type": entities_by_type,
        "relations_by_label": relations_by_label,
        "relations_by_origin": {"cue": rel_cue, "STRUCTURE": rel_struct},
        "amounts_count": len(aux.get("amounts", [])),
        "warnings": warnings,
    }

    return {"doc": doc, "aux": aux, "info": info}


def process_text(
    text: str,
    doc_id: str = "DOC_001",
    **kwargs: Any,
) -> dict[str, Any]:
    """Run analyze_text and return only the Contract 1 v1.1 document dict."""
    return analyze_text(text, doc_id=doc_id, **kwargs)["doc"]
