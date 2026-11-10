"""
Unit tests for Step 6b-1: ai_pipeline/assemble.py.
Uses short hand-written Roman and Devanagari texts with hand-made raw spans (no model loaded).
"""
from __future__ import annotations

from ai_pipeline.assemble import assemble_entities
from contracts.v1_1.validate import validate_ai_output


def test_same_phone_two_ways_merged():
    """Same 10-digit phone in different surface formats merges into one PHONE entity with two mentions."""
    text = "Caller dialed 98765 43210 and later called from +91 9876543210."
    doc, aux = assemble_entities(text, "DOC_PHONE", [])
    phones = [e for e in doc["entities"] if e["type"] == "PHONE"]
    assert len(phones) == 1
    assert phones[0]["value"] == "9876543210"
    assert len(phones[0]["mentions"]) == 2
    assert [m["surface"] for m in phones[0]["mentions"]] == ["98765 43210", "+91 9876543210"]
    assert all(m["kind"] == "VALUE" for m in phones[0]["mentions"])
    for m in phones[0]["mentions"]:
        s, e = m["char_span"]
        assert text[s:e] == m["surface"]


def test_same_name_twice_merged():
    """Repeated mentions of the exact same normalized person name merge into one PERSON entity."""
    text = "Accused Rohan Verma fled. Later Shri Rohan Verma surrendered."
    s1 = text.index("Rohan Verma")
    s2 = text.index("Shri Rohan Verma")
    raw = [
        {"type": "PERSON", "start": s1, "end": s1 + 11, "score": 0.96, "word": "Rohan Verma"},
        {"type": "PERSON", "start": s2, "end": s2 + 16, "score": 0.92, "word": "Shri Rohan Verma"},
    ]
    doc, _ = assemble_entities(text, "DOC_DUP_NAME", raw)
    persons = [e for e in doc["entities"] if e["type"] == "PERSON"]
    assert len(persons) == 1
    assert persons[0]["canonical_name"] == "Rohan Verma"
    assert len(persons[0]["mentions"]) == 2
    assert all(m["kind"] == "NAME" for m in persons[0]["mentions"])
    assert abs(persons[0]["ai_confidence"] - 0.94) < 1e-6


def test_vikas_and_bikas_stay_two_entities():
    """Similar names like Vikas Sharma and Bikas Sharma are NOT merged."""
    text = "Suspects Vikas Sharma and Bikas Sharma were spotted together."
    s1 = text.index("Vikas Sharma")
    s2 = text.index("Bikas Sharma")
    raw = [
        {"type": "PERSON", "start": s1, "end": s1 + 12, "score": 0.95, "word": "Vikas Sharma"},
        {"type": "PERSON", "start": s2, "end": s2 + 12, "score": 0.95, "word": "Bikas Sharma"},
    ]
    doc, _ = assemble_entities(text, "DOC_TWO_PERSONS", raw)
    persons = [e for e in doc["entities"] if e["type"] == "PERSON"]
    assert [p["canonical_name"] for p in persons] == ["Vikas Sharma", "Bikas Sharma"]


def test_alias_attaches_to_preceding_person_and_orphan_dropped():
    """Alias attaches to nearest preceding person in the same sentence; orphan alias is dropped."""
    text = (
        "Inspector Arun and suspect Mohan Das urf Raju @ Bunty @ Raju escaped. "
        "Witnesses heard alias Shadow next morning."
    )
    s_arun = text.index("Arun")
    s_mohan = text.index("Mohan Das")
    raw = [
        {"type": "PERSON", "start": s_arun, "end": s_arun + 4, "score": 0.9, "word": "Arun"},
        {"type": "PERSON", "start": s_mohan, "end": s_mohan + 9, "score": 0.95, "word": "Mohan Das"},
    ]
    doc, aux = assemble_entities(text, "DOC_ALIAS", raw)
    persons = {p["canonical_name"]: p for p in doc["entities"] if p["type"] == "PERSON"}
    assert "aliases" not in persons["Arun"]
    mohan = persons["Mohan Das"]
    assert mohan["aliases"] == ["Raju", "Bunty"]
    alias_mentions = [m for m in mohan["mentions"] if m["kind"] == "ALIAS"]
    assert [m["surface"] for m in alias_mentions] == ["Raju", "Bunty", "Raju"]
    assert "RULE_ALIAS" in mohan["flags"]
    assert aux["dropped"]["alias_no_owner"] == 1


def test_father_attaches_no_extra_entity_and_orphan_dropped():
    """Father cue attaches to preceding SUSPECT as father_name and FATHER mention with no extra entity."""
    text = "Officer Vikram noted report. Suspect Kiran Pal s/o Ramesh Lal fled."
    s_vik = text.index("Vikram")
    s_kir = text.index("Kiran Pal")
    raw = [
        {"type": "PERSON", "start": s_vik, "end": s_vik + 6, "score": 0.91, "word": "Vikram"},
        {"type": "PERSON", "start": s_kir, "end": s_kir + 9, "score": 0.93, "word": "Kiran Pal"},
    ]
    doc, aux = assemble_entities(text, "DOC_FATHER", raw)
    persons = [e for e in doc["entities"] if e["type"] == "PERSON"]
    assert len(persons) == 2
    assert [p["canonical_name"] for p in persons] == ["Vikram", "Kiran Pal"]
    kiran = persons[1]
    assert kiran["father_name"] == "Ramesh Lal"
    father_mentions = [m for m in kiran["mentions"] if m["kind"] == "FATHER"]
    assert len(father_mentions) == 1
    assert father_mentions[0]["surface"] == "Ramesh Lal"
    assert "RULE_FATHER" in kiran["flags"]

    # Orphan father when only OFFICER precedes it
    text_orphan = "SI Vikram s/o Suresh Lal investigated."
    s_o = text_orphan.index("Vikram")
    doc_o, aux_o = assemble_entities(
        text_orphan,
        "DOC_FATHER_ORPHAN",
        [{"type": "PERSON", "start": s_o, "end": s_o + 6, "score": 0.9, "word": "Vikram"}],
    )
    assert len(doc_o["entities"]) == 1
    assert "father_name" not in doc_o["entities"][0]
    assert aux_o["dropped"]["father_no_owner"] == 1


def test_officer_role():
    """Officer cue sets role OFFICER on the person entity."""
    text = "Sub-Inspector Deepak Kulkarni seized the phone."
    s = text.index("Deepak Kulkarni")
    raw = [{"type": "PERSON", "start": s, "end": s + 15, "score": 0.97, "word": "Deepak Kulkarni"}]
    doc, _ = assemble_entities(text, "DOC_OFFICER", raw)
    assert doc["entities"][0]["role"] == "OFFICER"


def test_amounts_and_ifsc_in_aux_not_entities():
    """Monetary amounts and IFSC codes go into aux lists and are excluded from entities."""
    text = "Suspect Meera sent Rs. 45,000/- via IFSC SBIN0001234 and later paid ₹ 5,000."
    s = text.index("Meera")
    raw = [{"type": "PERSON", "start": s, "end": s + 5, "score": 0.95, "word": "Meera"}]
    doc, aux = assemble_entities(text, "DOC_AUX", raw)

    assert len(doc["entities"]) == 1
    assert doc["entities"][0]["type"] == "PERSON"
    assert len(aux["amounts"]) == 2
    assert [a["value"] for a in aux["amounts"]] == [45000.0, 5000.0]
    for amt in aux["amounts"]:
        assert text[amt["start"]:amt["end"]] == amt["surface"]

    assert len(aux["ifsc"]) == 1
    assert aux["ifsc"][0]["value"] == "SBIN0001234"
    s_i, e_i = aux["ifsc"][0]["start"], aux["ifsc"][0]["end"]
    assert text[s_i:e_i] == "SBIN0001234"


def test_bank_detection_within_25_chars():
    """ACCOUNT gets bank field only when SBI/HDFC/ICICI/PNB/Axis/Kotak appears within 25 chars before span."""
    text = (
        "Money transferred from HDFC account 123456789012 "
        "to generic account 987654321098 at Kotak branch; "
        "and Axis bank account 555666777888."
    )
    doc, _ = assemble_entities(text, "DOC_BANK", [])
    accounts = {e["value"]: e for e in doc["entities"] if e["type"] == "ACCOUNT"}
    assert accounts["123456789012"]["bank"] == "HDFC"
    assert accounts["123456789012"]["confidence_breakdown"]["context"] == 1.0
    assert "bank" not in accounts["987654321098"]
    assert accounts["555666777888"]["bank"] == "Axis"


def test_ids_sequential_mentions_valid_and_deterministic():
    """Entity ids are sequential by first mention, spans match text, validates, and is deterministic."""
    text = (
        "Phone 9811122233 called suspect Rajesh Tiwari (alias Pappu). "
        "Vehicle DL-01-AB-1234 and PAN ABCDE1234F were noted; Rajesh Tiwari called 9811122233."
    )
    r1 = text.index("Rajesh Tiwari")
    r2 = text.rindex("Rajesh Tiwari")
    raw = [
        {"type": "PERSON", "start": r1, "end": r1 + 13, "score": 0.99, "word": "Rajesh Tiwari"},
        {"type": "PERSON", "start": r2, "end": r2 + 13, "score": 0.97, "word": "Rajesh Tiwari"},
    ]
    doc1, aux1 = assemble_entities(text, "DOC_SEQ", raw)
    doc2, aux2 = assemble_entities(text, "DOC_SEQ", raw)
    assert doc1 == doc2
    assert aux1 == aux2
    assert doc1["schema_version"] == "1.1"
    assert doc1["case_id"] == "CASE_DEMO_V2"
    assert doc1["source_doc_id"] == "DOC_SEQ"
    assert doc1["relationships"] == []

    # Validate against Contract 1 v1.1 schema
    validate_ai_output(doc1)

    expected_types = ["PHONE", "PERSON", "VEHICLE", "PAN"]
    assert [e["type"] for e in doc1["entities"]] == expected_types
    assert [e["id"] for e in doc1["entities"]] == ["ent_01", "ent_02", "ent_03", "ent_04"]

    for ent in doc1["entities"]:
        starts = [m["char_span"][0] for m in ent["mentions"]]
        assert starts == sorted(starts)
        assert ent["char_span"] == ent["mentions"][0]["char_span"]
        for m in ent["mentions"]:
            ms, me = m["char_span"]
            assert text[ms:me] == m["surface"]


def test_identifier_and_person_confidence_rules():
    """Verify valid=0.99, CHECKSUM_INVALID=0.6, other invalid=0.9, and PERSON mean/fallback score."""
    # Invalid Luhn IMEI (0.6), unknown state XX01AB1234 (0.9), valid phone (0.99), unscored person (0.9)
    text = "Accused Anoop used IMEI 123456789012345, vehicle XX-01-AB-1234, phone 9876543210."
    s_p = text.index("Anoop")
    raw_no_score = [{"type": "PERSON", "start": s_p, "end": s_p + 5, "word": "Anoop"}]
    doc, _ = assemble_entities(text, "DOC_CONF", raw_no_score)
    by_type = {e["type"]: e for e in doc["entities"]}

    assert by_type["PERSON"]["ai_confidence"] == 0.9
    assert by_type["PERSON"]["confidence_breakdown"] == {"model": None, "validator": None, "context": None}

    assert by_type["IMEI"]["ai_confidence"] == 0.6
    assert "CHECKSUM_INVALID" in by_type["IMEI"]["flags"]
    assert by_type["IMEI"]["confidence_breakdown"]["validator"] == 0.6

    assert by_type["VEHICLE"]["ai_confidence"] == 0.9
    assert "UNKNOWN_STATE" in by_type["VEHICLE"]["flags"]

    assert by_type["PHONE"]["ai_confidence"] == 0.99
    validate_ai_output(doc)


def test_devanagari_text_assembly():
    """End-to-end assembly on Devanagari text with honorifics, urf, पुत्र, officer, and rupees."""
    text = (
        "थाना प्रभारी श्री सुरेश यादव ने अभियुक्त मोहन लाल उर्फ कल्लू पुत्र रमेश चंद्र से "
        "₹ 15,000 और मोबाइल ९८७६५४३२१० बरामद किया।"
    )
    s1 = text.index("श्री सुरेश यादव")
    s2 = text.index("मोहन लाल")
    raw = [
        {"type": "PERSON", "start": s1, "end": s1 + len("श्री सुरेश यादव"), "score": 0.98, "word": "श्री सुरेश यादव"},
        {"type": "PERSON", "start": s2, "end": s2 + len("मोहन लाल"), "score": 0.96, "word": "मोहन लाल"},
    ]
    doc, aux = assemble_entities(text, "DOC_HI", raw)
    validate_ai_output(doc)

    persons = [e for e in doc["entities"] if e["type"] == "PERSON"]
    assert len(persons) == 2
    assert persons[0]["canonical_name"] == "सुरेश यादव"
    assert persons[0]["role"] == "OFFICER"

    assert persons[1]["canonical_name"] == "मोहन लाल"
    assert persons[1]["role"] == "SUSPECT"
    assert persons[1]["aliases"] == ["कल्लू"]
    assert persons[1]["father_name"] == "रमेश चंद्र"

    phones = [e for e in doc["entities"] if e["type"] == "PHONE"]
    assert len(phones) == 1
    assert phones[0]["value"] == "9876543210"
    assert len(aux["amounts"]) == 1
    assert aux["amounts"][0]["value"] == 15000.0


def test_empty_text_returns_empty_entities():
    """Empty input text returns entities == [] without throwing validation error."""
    doc, aux = assemble_entities("", "DOC_EMPTY", [])
    assert doc == {
        "schema_version": "1.1",
        "case_id": "CASE_DEMO_V2",
        "source_doc_id": "DOC_EMPTY",
        "entities": [],
        "relationships": [],
    }
    assert aux == {"amounts": [], "ifsc": [], "dropped": {"alias_no_owner": 0, "father_no_owner": 0}}

