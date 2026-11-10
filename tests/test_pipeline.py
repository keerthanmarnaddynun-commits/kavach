"""
Unit tests for Step 6c: ai_pipeline/pipeline.py.
Uses short hand-written Roman Hinglish, Devanagari Hindi, and English texts
with injected raw_spans or use_model=False (no ML model loaded).
"""
from __future__ import annotations

import hashlib
import pytest

from ai_pipeline import ner_baseline
from ai_pipeline.pipeline import (
    EmptyText,
    MAX_CHARS,
    NoEntitiesFound,
    TextTooLong,
    analyze_text,
    heuristic_person_spans,
    process_text,
)
from contracts.v1_1.validate import validate_ai_output


def _make_raw(text: str, names: list[str]) -> list[dict]:
    spans = []
    pos = {}
    for name in names:
        idx = text.find(name, pos.get(name, 0))
        assert idx != -1, f"Name {name!r} not found in text"
        spans.append({
            "type": "PERSON",
            "start": idx,
            "end": idx + len(name),
            "score": 0.96,
            "word": name,
        })
        pos[name] = idx + len(name)
    return spans


def test_end_to_end_english_hinglish_devanagari_with_raw_spans():
    """English, Roman Hinglish, and Devanagari texts pass validate_ai_output with sensible entities and relations."""
    samples = [
        (
            "Suspect Arun Kumar owned mobile 9811122233. "
            "Accused Arun Kumar remitted Rs. 15,000/- to bank account 112233445566.",
            ["Arun Kumar", "Arun Kumar"],
            "DOC_EN",
            "CASE_EN",
        ),
        (
            "Accused Kiran Das ke paas se phone 9811122233 baramad hua. "
            "Kiran Das ne Rs. 12,000/- account 112233445566 mein credit karwaya.",
            ["Kiran Das", "Kiran Das"],
            "DOC_HG",
            "CASE_HG",
        ),
        (
            "आरोपी अरुण वर्मा के पास से मोबाइल ९८१११२२२३३ बरामद हुआ। "
            "अभियुक्त अरुण वर्मा ने रकम ₹ 8,500 खाता 112233445566 में प्रेषित की।",
            ["अरुण वर्मा", "अरुण वर्मा"],
            "DOC_HI",
            "CASE_HI",
        ),
    ]

    for text, names, doc_id, case_id in samples:
        raw = _make_raw(text, names)
        res = analyze_text(text, doc_id=doc_id, case_id=case_id, raw_spans=raw)
        doc, info = res["doc"], res["info"]
        validate_ai_output(doc)

        assert doc["source_doc_id"] == doc_id
        assert doc["case_id"] == case_id
        ent_types = {e["type"] for e in doc["entities"]}
        assert {"PERSON", "PHONE", "ACCOUNT"}.issubset(ent_types)
        rel_types = {r["relation"] for r in doc["relationships"]}
        assert {"OWNS_DEVICE", "TRANSFERRED_FUNDS"}.issubset(rel_types)
        assert info["mode"] == "MODEL"
        assert info["model_name"] == ner_baseline.MODELS[0]
        assert info["amounts_count"] == 1


def test_deterministic_and_process_text():
    """Repeated calls produce identical doc and aux outputs, and process_text returns doc only."""
    text = "Suspect Arun Kumar used phone 9811122233 and handset IMEI 351234567890123."
    raw = _make_raw(text, ["Arun Kumar"])
    res1 = analyze_text(text, doc_id="DOC_DET", case_id="CASE_DET", raw_spans=raw)
    res2 = analyze_text(text, doc_id="DOC_DET", case_id="CASE_DET", raw_spans=raw)
    assert res1["doc"] == res2["doc"]
    assert res1["aux"] == res2["aux"]
    assert res1["info"]["document_hash"] == res2["info"]["document_hash"]

    doc_only = process_text(text, doc_id="DOC_DET", case_id="CASE_DET", raw_spans=raw)
    assert doc_only == res1["doc"]


def test_text_length_boundary_5000_vs_5001():
    """5000 characters is accepted; 5001 characters raises TextTooLong."""
    base = "Suspect Arun Kumar called phone 9811122233. "
    pad_len_5000 = MAX_CHARS - len(base)
    text_5000 = base + ("x" * pad_len_5000)
    assert len(text_5000) == 5000
    raw = _make_raw(text_5000, ["Arun Kumar"])
    res = analyze_text(text_5000, doc_id="DOC_5000", raw_spans=raw)
    assert res["info"]["char_count"] == 5000

    text_5001 = base + ("x" * (pad_len_5000 + 1))
    assert len(text_5001) == 5001
    with pytest.raises(TextTooLong):
        analyze_text(text_5001, doc_id="DOC_5001", raw_spans=raw)


def test_empty_text_exceptions():
    """Empty string, whitespace-only string, and non-string raise EmptyText."""
    for bad in ("", "   ", "\n\t  ", 42):
        with pytest.raises(EmptyText):
            analyze_text(bad)  # type: ignore[arg-type]


def test_no_entities_found_exception():
    """Text containing neither identifiers nor names raises NoEntitiesFound."""
    with pytest.raises(NoEntitiesFound):
        analyze_text("This is a generic weather update with no entities.", use_model=False)


def test_document_hash_and_timings_and_metadata():
    """Verify document_hash matches sha256, timings_ms has all keys with total >= max stage, and ids propagate."""
    text = "Suspect Mohit Sharma used mobile 9822233344."
    raw = _make_raw(text, ["Mohit Sharma"])
    res = analyze_text(text, doc_id="FIR_CUSTOM", case_id="CASE_99", raw_spans=raw)
    info = res["info"]

    expected_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert info["document_hash"] == expected_hash
    assert info["char_count"] == len(text)
    assert res["doc"]["source_doc_id"] == "FIR_CUSTOM"
    assert res["doc"]["case_id"] == "CASE_99"

    timings = info["timings_ms"]
    expected_keys = {
        "model", "postprocess", "names_identifiers",
        "assemble", "relations", "validate", "total",
    }
    assert set(timings.keys()) == expected_keys
    assert all(isinstance(v, float) and v >= 0.0 for v in timings.values())
    max_stage = max(timings[k] for k in expected_keys - {"total"})
    assert timings["total"] >= max_stage


def test_degraded_mode_without_model():
    """use_model=False sets DEGRADED_NO_MODEL, emits heuristic warning, and finds ids + cue person."""
    text = "Accused Arun Kumar urf Kallu used mobile 9811122233 and bank account 112233445566."
    res = analyze_text(text, doc_id="DOC_DEG", use_model=False)
    info = res["info"]
    doc = res["doc"]

    assert info["mode"] == "DEGRADED_NO_MODEL"
    assert info["model_name"] is None
    assert any("heuristics" in w.lower() for w in info["warnings"])
    ent_types = {e["type"] for e in doc["entities"]}
    assert {"PERSON", "PHONE", "ACCOUNT"}.issubset(ent_types)
    persons = [e for e in doc["entities"] if e["type"] == "PERSON"]
    assert persons[0]["canonical_name"] == "Arun Kumar"
    assert persons[0]["aliases"] == ["Kallu"]


def test_model_failure_falls_back_to_degraded(monkeypatch):
    """If offline model raises an error, pipeline falls back cleanly to DEGRADED_NO_MODEL with warning."""
    def _boom(*args, **kwargs):
        raise RuntimeError("offline cache missing")

    monkeypatch.setattr(ner_baseline, "run_model", _boom)
    text = "Suspect Arun Kumar carried mobile 9811122233."
    res = analyze_text(text, doc_id="DOC_FALLBACK", use_model=True)
    assert res["info"]["mode"] == "DEGRADED_NO_MODEL"
    assert res["info"]["model_name"] is None
    assert any("offline cache missing" in w and "heuristics" in w.lower() for w in res["info"]["warnings"])
    assert any(e["type"] == "PERSON" and e["canonical_name"] == "Arun Kumar" for e in res["doc"]["entities"])


def test_heuristic_person_spans_examples_and_plain_text():
    """heuristic_person_spans catches Latin before urf, after Shri, Devanagari before उर्फ, and ignores plain text."""
    s1 = heuristic_person_spans("Arun Kumar urf Kallu escaped.")
    assert [sp["word"] for sp in s1] == ["Arun Kumar"]

    s2 = heuristic_person_spans("Notice was served to Shri Rajesh Verma yesterday.")
    assert [sp["word"] for sp in s2] == ["Rajesh Verma"]

    s3 = heuristic_person_spans("अभियुक्त अरुण वर्मा उर्फ गोलू फरार हो गया।")
    assert [sp["word"] for sp in s3] == ["अरुण वर्मा"]

    s4 = heuristic_person_spans("श्री सुरेश यादव ने बयान दर्ज किया।")
    assert [sp["word"] for sp in s4] == ["सुरेश यादव"]

    # Plain sentences without cues return []
    assert heuristic_person_spans("This is a plain sentence with no cues.") == []
    assert heuristic_person_spans("यह एक सामान्य वाक्य है।") == []
    assert heuristic_person_spans("Accused ran away swiftly.") == []

