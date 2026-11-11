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


def test_short_name_merge_english_hinglish_devanagari():
    """Step 6c-3: Single first-name mention merges into unique fuller entity across EN/HG/HI."""
    # 1. English + confidence recomputation + flag + ID renumbering + mention sorting
    t_en = (
        "Accused Tarun Bedi used phone 9711002201. "
        "Later Tarun called from account 440011223344."
    )
    s_full = t_en.index("Tarun Bedi")
    s_short = t_en.index("Tarun", s_full + 10)
    raw_en = [
        {"type": "PERSON", "start": s_full, "end": s_full + 10, "score": 0.98, "word": "Tarun Bedi"},
        {"type": "PERSON", "start": s_short, "end": s_short + 5, "score": 0.86, "word": "Tarun"},
    ]
    doc_en, aux_en = assemble_entities(t_en, "DOC_SN_EN", raw_en)
    validate_ai_output(doc_en)
    assert aux_en["short_name_merges"] == 1
    assert aux_en["short_name_ambiguous"] == []
    persons_en = [e for e in doc_en["entities"] if e["type"] == "PERSON"]
    assert len(persons_en) == 1
    p_en = persons_en[0]
    assert p_en["canonical_name"] == "Tarun Bedi"
    assert "SHORT_NAME_MERGE" in p_en["flags"]
    assert [m["surface"] for m in p_en["mentions"]] == ["Tarun Bedi", "Tarun"]
    assert all(m["kind"] == "NAME" for m in p_en["mentions"])
    assert p_en["mentions"][0]["char_span"][0] < p_en["mentions"][1]["char_span"][0]
    assert abs(p_en["ai_confidence"] - 0.92) < 1e-6
    assert abs(p_en["confidence_breakdown"]["model"] - 0.92) < 1e-6
    assert [e["id"] for e in doc_en["entities"]] == ["ent_01", "ent_02", "ent_03"]

    # Determinism check
    doc_en2, aux_en2 = assemble_entities(t_en, "DOC_SN_EN", raw_en)
    assert doc_en == doc_en2
    assert aux_en == aux_en2

    # 2. Roman Hinglish with casefolding + honorific stripping
    t_hg = "Suspect Shri Harish Mehta ne mobile rakha. Baad mein shri harish bhag gaya."
    s_hm = t_hg.index("Shri Harish Mehta")
    s_hh = t_hg.index("shri harish")
    raw_hg = [
        {"type": "PERSON", "start": s_hm, "end": s_hm + len("Shri Harish Mehta"), "score": 0.96, "word": "Shri Harish Mehta"},
        {"type": "PERSON", "start": s_hh, "end": s_hh + len("shri harish"), "score": 0.90, "word": "shri harish"},
    ]
    doc_hg, aux_hg = assemble_entities(t_hg, "DOC_SN_HG", raw_hg)
    validate_ai_output(doc_hg)
    assert aux_hg["short_name_merges"] == 1
    persons_hg = [e for e in doc_hg["entities"] if e["type"] == "PERSON"]
    assert len(persons_hg) == 1
    assert persons_hg[0]["canonical_name"] == "Harish Mehta"
    assert "SHORT_NAME_MERGE" in persons_hg[0]["flags"]
    assert [m["char_span"][0] for m in persons_hg[0]["mentions"]] == sorted(
        m["char_span"][0] for m in persons_hg[0]["mentions"]
    )

    # 3. Devanagari short first name merges cleanly; earlier short mention updates char_span & IDs
    t_hi = "संदिग्ध प्रदीप बाजार गया और मोबाइल 9711002201 छोड़ा। बाद में आरोपी प्रदीप द्विवेदी पकड़ा गया।"
    s_hi_s = t_hi.index("प्रदीप")
    s_hi_f = t_hi.index("प्रदीप द्विवेदी")
    raw_hi = [
        {"type": "PERSON", "start": s_hi_s, "end": s_hi_s + len("प्रदीप"), "score": 0.88, "word": "प्रदीप"},
        {"type": "PERSON", "start": s_hi_f, "end": s_hi_f + len("प्रदीप द्विवेदी"), "score": 0.94, "word": "प्रदीप द्विवेदी"},
    ]
    doc_hi, aux_hi = assemble_entities(t_hi, "DOC_SN_HI", raw_hi)
    validate_ai_output(doc_hi)
    assert aux_hi["short_name_merges"] == 1
    assert [e["id"] for e in doc_hi["entities"]] == ["ent_01", "ent_02"]
    p_hi = doc_hi["entities"][0]
    assert p_hi["canonical_name"] == "प्रदीप द्विवेदी"
    assert p_hi["char_span"] == [s_hi_s, s_hi_s + len("प्रदीप")]
    assert [m["surface"] for m in p_hi["mentions"]] == ["प्रदीप", "प्रदीप द्विवेदी"]
    assert "SHORT_NAME_MERGE" in p_hi["flags"]


def test_short_name_ambiguous_when_two_fuller_share_first_token():
    """Step 6c-3: Two fuller names with the same first token do not merge and record ambiguity."""
    text = "Suspects Mahesh Kulkarni and Mahesh Saxena fled. Later Mahesh called."
    s1 = text.index("Mahesh Kulkarni")
    s2 = text.index("Mahesh Saxena")
    s3 = text.index("Mahesh called")
    raw = [
        {"type": "PERSON", "start": s1, "end": s1 + 15, "score": 0.95, "word": "Mahesh Kulkarni"},
        {"type": "PERSON", "start": s2, "end": s2 + 13, "score": 0.95, "word": "Mahesh Saxena"},
        {"type": "PERSON", "start": s3, "end": s3 + 6, "score": 0.91, "word": "Mahesh"},
    ]
    doc, aux = assemble_entities(text, "DOC_SN_AMB", raw)
    validate_ai_output(doc)
    assert aux["short_name_merges"] == 0
    assert len(aux["short_name_ambiguous"]) == 1
    persons = [e for e in doc["entities"] if e["type"] == "PERSON"]
    assert [p["canonical_name"] for p in persons] == ["Mahesh Kulkarni", "Mahesh Saxena", "Mahesh"]
    assert all("SHORT_NAME_MERGE" not in p["flags"] for p in persons)


def test_short_name_guards_lookalike_lastname_partial_alias_role_father():
    """Step 6c-3: Look-alike, last-name, partial, alias-of-other, conflicting role/father never merge."""
    # 1. Look-alike (differs by 1 letter), last-name-only, and partial token never merge
    t_look = "Suspect Parthiv Mehta fled. Later Parthil, Mehta, and Par were named."
    raw_look = []
    pos = 0
    for nm in ("Parthiv Mehta", "Parthil", "Mehta", "Par"):
        idx = t_look.index(nm, pos)
        raw_look.append({"type": "PERSON", "start": idx, "end": idx + len(nm), "score": 0.94, "word": nm})
        pos = idx + len(nm)
    doc_look, aux_look = assemble_entities(t_look, "DOC_SN_LOOK", raw_look)
    validate_ai_output(doc_look)
    assert aux_look["short_name_merges"] == 0
    assert aux_look["short_name_ambiguous"] == []
    assert [e["canonical_name"] for e in doc_look["entities"]] == ["Parthiv Mehta", "Parthil", "Mehta", "Par"]

    # 2. Single token equal to an alias of someone else does not merge
    t_alias = "Suspect Alok Bansal urf Piko escaped. Suspect Piko Nair arrived. Later Piko called."
    s_alok = t_alias.index("Alok Bansal")
    s_pn = t_alias.index("Piko Nair")
    s_p = t_alias.rindex("Piko")
    raw_alias = [
        {"type": "PERSON", "start": s_alok, "end": s_alok + len("Alok Bansal"), "score": 0.95, "word": "Alok Bansal"},
        {"type": "PERSON", "start": s_pn, "end": s_pn + len("Piko Nair"), "score": 0.95, "word": "Piko Nair"},
        {"type": "PERSON", "start": s_p, "end": s_p + len("Piko"), "score": 0.90, "word": "Piko"},
    ]
    doc_alias, aux_alias = assemble_entities(t_alias, "DOC_SN_ALIAS", raw_alias)
    validate_ai_output(doc_alias)
    assert aux_alias["short_name_merges"] == 0
    assert [e["canonical_name"] for e in doc_alias["entities"]] == ["Alok Bansal", "Piko Nair", "Piko"]

    # 3. Officer with same first name as suspect does not merge (OFFICER vs SUSPECT)
    t_role = "Inspector Ketan Deshpande questioned suspect Ketan at night."
    s_kd = t_role.index("Ketan Deshpande")
    s_k = t_role.index("Ketan", s_kd + 15)
    raw_role = [
        {"type": "PERSON", "start": s_kd, "end": s_kd + len("Ketan Deshpande"), "score": 0.96, "word": "Ketan Deshpande"},
        {"type": "PERSON", "start": s_k, "end": s_k + len("Ketan"), "score": 0.92, "word": "Ketan"},
    ]
    doc_role, aux_role = assemble_entities(t_role, "DOC_SN_ROLE", raw_role)
    validate_ai_output(doc_role)
    assert aux_role["short_name_merges"] == 0
    persons_role = [e for e in doc_role["entities"] if e["type"] == "PERSON"]
    assert [(p["canonical_name"], p["role"]) for p in persons_role] == [
        ("Ketan Deshpande", "OFFICER"),
        ("Ketan", "SUSPECT"),
    ]

    # 4. Conflicting father_name blocks merge
    t_fath = "Suspect Prashant Nair s/o Balram Trivedi arrived. Suspect Prashant s/o Jagdish Chauhan fled."
    s_pn2 = t_fath.index("Prashant Nair")
    s_p2 = t_fath.index("Prashant", s_pn2 + 13)
    raw_fath = [
        {"type": "PERSON", "start": s_pn2, "end": s_pn2 + len("Prashant Nair"), "score": 0.95, "word": "Prashant Nair"},
        {"type": "PERSON", "start": s_p2, "end": s_p2 + len("Prashant"), "score": 0.91, "word": "Prashant"},
    ]
    doc_fath, aux_fath = assemble_entities(t_fath, "DOC_SN_FATH", raw_fath)
    validate_ai_output(doc_fath)
    assert aux_fath["short_name_merges"] == 0
    assert [e["canonical_name"] for e in doc_fath["entities"]] == ["Prashant Nair", "Prashant"]

    # 5. Differing alias on short entity blocks merge
    t_ealias = "Suspect Nitin Saxena urf Kobo arrived. Later suspect Nitin urf Zorro fled."
    s_ns = t_ealias.index("Nitin Saxena")
    s_n = t_ealias.index("Nitin", s_ns + 12)
    raw_ea = [
        {"type": "PERSON", "start": s_ns, "end": s_ns + len("Nitin Saxena"), "score": 0.95, "word": "Nitin Saxena"},
        {"type": "PERSON", "start": s_n, "end": s_n + len("Nitin"), "score": 0.91, "word": "Nitin"},
    ]
    doc_ea, aux_ea = assemble_entities(t_ealias, "DOC_SN_EA", raw_ea)
    validate_ai_output(doc_ea)
    assert aux_ea["short_name_merges"] == 0
    assert [e["canonical_name"] for e in doc_ea["entities"]] == ["Nitin Saxena", "Nitin"]


