"""Unit tests for LLM-authored FIR converter and validator using inline fixtures."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import pytest

from llm_firs.convert import parse_file, parse_text
from scripts.convert_llm_firs import convert_all_firs


BRIEF_EXAMPLE = """LANG: hinglish
Aaj subah 10 baje shikayatkarta [[PERSON:P2:C|Sunita Devi]] thane aayi aur boli ki online fraud hua hai. Usne bataya ki usne [[AMOUNT:A1|Rs. 85,000/-]] PNB account [[ACCOUNT:AC1|4521003298761]] mein transfer kiye the, jo [[PERSON:P1:S|Mohit Sharma]] s/o [[FATHER:P1|Dinesh Sharma]] ke naam par chalta hai. Sadar Bazar se Mohit ko pakda gaya to uske paas se mobile [[PHONE:PH1|9811234567]] mila, IMEI [[IMEI:IM1|356938035643809]]. FIR No. 214/2026 u/s 318(4) BNS darj hui, IO SI [[PERSON:P3:O|Anil Yadav]] ko saunpi gayi.
---
REL: OWNS_DEVICE P1 PH1
REL: ASSOCIATED_IMEI PH1 IM1
REL: CONTROLS_ACCOUNT P1 AC1
REL: TRANSFERRED_FUNDS P2 AC1 85000
"""


def test_brief_example_round_trip():
    """Spans slice the clean text back to the exact tagged surface."""
    res = parse_text(BRIEF_EXAMPLE, stem="H_01")
    assert res.is_valid is True
    assert len(res.errors) == 0

    clean_text = res.clean_text
    assert "[[PERSON:" not in clean_text
    assert "Sunita Devi" in clean_text

    for ent in res.entities:
        start = ent["start"]
        end = ent["end"]
        sliced = clean_text[start:end]
        assert sliced == ent["surface"], f"Span mismatch: '{sliced}' vs '{ent['surface']}'"


# Error fixtures
@pytest.mark.parametrize(
    "fixture_text,expected_err",
    [
        # Missing or unknown LANG
        ("Language: hinglish\nFoo\n---\n", "missing_or_unknown_lang_line"),
        ("LANG: french\nFoo\n---\n", "missing_or_unknown_lang_line"),
        # Missing separator line
        ("LANG: english\nNo separator here", "missing_separator_line"),
        # Unbalanced or nested tags
        ("LANG: english\nHello [[PERSON:P1:S|Mohit\n---\n", "unbalanced_or_nested_tags"),
        ("LANG: english\nHello [[PERSON:P1:S|[[ALIAS:P1|Bicky]] Mohit]]\n---\n", "unbalanced_or_nested_tags"),
        ("LANG: english\nHello Mohit]]\n---\n", "unbalanced_or_nested_tags"),
        # Unknown tag type
        ("LANG: english\nHello [[UNKNOWN:U1|Foo]]\n---\n", "unknown_tag_type"),
        # Invalid person role
        ("LANG: english\nHello [[PERSON:P1:X|Mohit]]\n---\n", "invalid_person_role"),
        ("LANG: english\nHello [[PERSON:P1|Mohit]]\n---\n", "invalid_person_role"),
        # Orphan alias or father
        ("LANG: english\nHello [[ALIAS:P99|Tiger]]\n---\n", "orphan_alias_or_father"),
        ("LANG: english\nHello [[FATHER:P99|Gopal]]\n---\n", "orphan_alias_or_father"),
        # Duplicate key different type
        ("LANG: english\n[[PHONE:K1|9811234567]] and [[ACCOUNT:K1|1234567890]]\n---\n", "duplicate_key_different_type"),
        # Ambiguous touching tags
        ("LANG: english\n[[PERSON:P1:S|Mohit]][[PHONE:PH1|9811234567]]\n---\n", "ambiguous_tag_spans"),
        # Invalid REL syntax
        ("LANG: english\n[[PERSON:P1:S|Mohit]]\n---\nNOT_REL: FOO\n", "invalid_rel_syntax"),
        ("LANG: english\n[[PERSON:P1:S|Mohit]]\n---\nREL: OWNS_DEVICE P1\n", "invalid_rel_syntax"),
        # Unknown REL type
        ("LANG: english\n[[PERSON:P1:S|Mohit]] [[PHONE:PH1|9811234567]]\n---\nREL: BORROWS_DEVICE P1 PH1\n", "unknown_rel_type"),
        # REL key not in text
        ("LANG: english\n[[PERSON:P1:S|Mohit]]\n---\nREL: OWNS_DEVICE P1 PH_MISSING\n", "rel_key_not_in_text"),
        # REL endpoints wrong type
        ("LANG: english\n[[PERSON:P1:S|Mohit]] [[ACCOUNT:AC1|1234567890]]\n---\nREL: OWNS_DEVICE P1 AC1\n", "invalid_rel_endpoints"),
        ("LANG: english\n[[PHONE:PH1|9811234567]] [[ACCOUNT:AC1|1234567890]]\n---\nREL: CONTROLS_ACCOUNT PH1 AC1\n", "invalid_rel_endpoints"),
        # Missing transfer amount
        ("LANG: english\n[[PERSON:P1:S|Mohit]] [[ACCOUNT:AC1|1234567890]]\n---\nREL: TRANSFERRED_FUNDS P1 AC1\n", "missing_transfer_amount"),
        ("LANG: english\n[[PERSON:P1:S|Mohit]] [[ACCOUNT:AC1|1234567890]]\n---\nREL: TRANSFERRED_FUNDS P1 AC1 non_num\n", "missing_transfer_amount"),
        # Empty clean text
        ("LANG: english\n\n---\n", "empty_clean_text"),
        # Clean text too long
        ("LANG: english\n" + ("A" * 5001) + "\n---\n", "clean_text_too_long"),
        # Empty tag text
        ("LANG: english\nHello [[PERSON:P1:S|]]\n---\n", "empty_tag_text"),
    ],
)
def test_error_classes(fixture_text, expected_err):
    """Each error class has a failing fixture."""
    res = parse_text(fixture_text, stem="test_err")
    assert res.is_valid is False
    assert any(expected_err in err for err in res.errors), f"Expected {expected_err} in {res.errors}"


# Warning fixtures
def test_warning_classes():
    """Each warning class has a passing fixture that lists it."""
    # 1. lang_stem_mismatch
    res = parse_text("LANG: hindi\nText [[PERSON:P1:S|Mohit]]\n---\n", stem="E_01")
    assert res.is_valid is True
    assert any(w["type"] == "lang_stem_mismatch" for w in res.warnings)

    # 2. phone_normalisation_warning
    res = parse_text("LANG: english\nCall [[PHONE:PH1|12345]]\n---\n", stem="E_01")
    assert res.is_valid is True
    assert any(w["type"] == "phone_normalisation_warning" for w in res.warnings)

    # 3. imei_luhn_warning
    res = parse_text("LANG: english\nDevice [[IMEI:IM1|123456789012345]]\n---\n", stem="E_01")
    assert res.is_valid is True
    assert any(w["type"] == "imei_luhn_warning" for w in res.warnings)

    # 4. aadhaar_warning
    res = parse_text("LANG: english\nAadhaar [[AADHAAR:AD1|1234]]\n---\n", stem="E_01")
    assert res.is_valid is True
    assert any(w["type"] == "aadhaar_warning" for w in res.warnings)

    # 5. pan_warning
    res = parse_text("LANG: english\nPAN [[PAN:PN1|INVALIDPAN]]\n---\n", stem="E_01")
    assert res.is_valid is True
    assert any(w["type"] == "pan_warning" for w in res.warnings)

    # 6. ifsc_warning
    res = parse_text("LANG: english\nIFSC [[IFSC:IF1|SBIN123]]\n---\n", stem="E_01")
    assert res.is_valid is True
    assert any(w["type"] == "ifsc_warning" for w in res.warnings)

    # 7. account_warning
    res = parse_text("LANG: english\nAccount [[ACCOUNT:AC1|12345]]\n---\n", stem="E_01")
    assert res.is_valid is True
    assert any(w["type"] == "account_warning" for w in res.warnings)

    # 8. amount_warning
    res = parse_text("LANG: english\nAmount [[AMOUNT:A1|lots of money]]\n---\n", stem="E_01")
    assert res.is_valid is True
    assert any(w["type"] == "amount_warning" for w in res.warnings)

    # 9. possible_unlabelled_identifier
    res = parse_text("LANG: english\nCall 9876543210 for details\n---\n", stem="E_01")
    assert res.is_valid is True
    assert any(w["type"] == "possible_unlabelled_identifier" for w in res.warnings)

    # 10. rel_amount_mismatch
    text = (
        "LANG: english\n"
        "Sent [[AMOUNT:A1|Rs. 50,000]] from [[PERSON:P1:S|Mohit]] to [[ACCOUNT:AC1|1234567890]]\n"
        "---\n"
        "REL: TRANSFERRED_FUNDS P1 AC1 99999\n"
    )
    res = parse_text(text, stem="E_01")
    assert res.is_valid is True
    assert any(w["type"] == "rel_amount_mismatch" for w in res.warnings)

    # 11. unused_key
    text = "LANG: english\nPerson [[PERSON:P1:S|Mohit]] and [[PERSON:P2:O|Inspector]]\n---\n"
    res = parse_text(text, stem="E_01")
    assert res.is_valid is True
    assert any(w["type"] == "unused_key" for w in res.warnings)


def test_alias_and_father_share_person_key_without_error():
    """ALIAS and FATHER share the person key without error."""
    text = (
        "LANG: hinglish\n"
        "Aaropi [[PERSON:P1:S|Pappu Meena]] urf [[ALIAS:P1|Tiger]] s/o [[FATHER:P1|Gopal Meena]]\n"
        "---\n"
    )
    res = parse_text(text, stem="H_04")
    assert res.is_valid is True
    assert len(res.errors) == 0

    ent_types = [e["type"] for e in res.entities]
    assert "PERSON" in ent_types
    assert "ALIAS" in ent_types

    p1 = next(e for e in res.entities if e["surface"] == "Pappu Meena")
    assert p1["aliases"] == ["Tiger"]


def test_devanagari_example():
    """Devanagari Hindi text converts and validates cleanly."""
    text = (
        "LANG: hindi\n"
        "आरोपी [[PERSON:P1:S|राकेश पांडेय]] उर्फ [[ALIAS:P1|राका]] पुत्र [[FATHER:P1|श्यामलाल पांडेय]] "
        "ने मोबाइल [[PHONE:PH1|9936012345]] से फोन किया।\n"
        "---\n"
        "REL: OWNS_DEVICE P1 PH1\n"
    )
    res = parse_text(text, stem="D_01")
    assert res.is_valid is True
    assert len(res.errors) == 0
    assert res.language == "hindi"
    for e in res.entities:
        assert res.clean_text[e["start"]:e["end"]] == e["surface"]


def test_crlf_and_bom_give_identical_outputs_to_lf():
    """CRLF and BOM inputs give identical outputs to the LF input."""
    base = BRIEF_EXAMPLE
    crlf_version = base.replace("\n", "\r\n")
    bom_version = "\ufeff" + base

    res_lf = parse_text(base, stem="test")
    res_crlf = parse_text(crlf_version, stem="test")
    res_bom = parse_text(bom_version, stem="test")

    dict_lf = res_lf.to_gold_dict()
    dict_crlf = res_crlf.to_gold_dict()
    dict_bom = res_bom.to_gold_dict()

    assert dict_lf == dict_crlf
    assert dict_lf == dict_bom


def test_output_identical_across_two_runs():
    """output identical across two runs."""
    res1 = parse_text(BRIEF_EXAMPLE, stem="H_01").to_gold_dict()
    res2 = parse_text(BRIEF_EXAMPLE, stem="H_01").to_gold_dict()
    assert json.dumps(res1, sort_keys=True) == json.dumps(res2, sort_keys=True)


def test_script_refuses_existing_output_folder(tmp_path):
    """script refuses an existing output folder."""
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "H_01.txt").write_text(BRIEF_EXAMPLE, encoding="utf-8")

    out_dir = tmp_path / "converted"
    out_dir.mkdir()

    with pytest.raises(FileExistsError):
        convert_all_firs(raw_dir=raw_dir, out_dir=out_dir)


def test_script_does_not_modify_raw_files(tmp_path):
    """script does not modify raw files (compare hashes before and after)."""
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    f1 = raw_dir / "H_01.txt"
    f1.write_text(BRIEF_EXAMPLE, encoding="utf-8")

    h_before = hashlib.sha256(f1.read_bytes()).hexdigest()
    out_dir = tmp_path / "out"

    convert_all_firs(raw_dir=raw_dir, out_dir=out_dir)

    h_after = hashlib.sha256(f1.read_bytes()).hexdigest()
    assert h_before == h_after


def test_converted_json_loaded_by_scoring_gold_loader(tmp_path):
    """the converted JSON of a valid fixture can be loaded by the existing scoring gold loader."""
    from ai_pipeline.scoring import load_gold_mentions

    res = parse_text(BRIEF_EXAMPLE, stem="FIR_01")
    gold_dict = res.to_gold_dict()

    json_file = tmp_path / "FIR_01.json"
    json_file.write_text(json.dumps(gold_dict, indent=2), encoding="utf-8")

    loaded = load_gold_mentions(tmp_path)
    assert "FIR_01" in loaded
    mentions = loaded["FIR_01"]
    assert len(mentions) == len(gold_dict["entities"])

    mention_types = {m["type"] for m in mentions}
    assert "PERSON" in mention_types
    assert "FATHER" in mention_types
    assert "PHONE" in mention_types
