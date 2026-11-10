"""
Unit tests for Step 6b-2: ai_pipeline/relations.py.
Uses short hand-written English, Roman Hinglish, and Devanagari texts built through
assemble_entities with hand-made raw spans (no model loaded).
"""
from __future__ import annotations

from ai_pipeline.assemble import assemble_entities
from ai_pipeline.relations import extract_relations, split_sentences
from contracts.v1_1.validate import validate_ai_output


def _build_and_extract(text: str, names: list[str], doc_id: str = "TEST_REL"):
    """Helper to run assemble_entities + extract_relations from hand-made person spans."""
    raw_spans = []
    search_from = {}
    for name in names:
        start_pos = search_from.get(name, 0)
        idx = text.find(name, start_pos)
        assert idx != -1, f"Name {name!r} not found in text from offset {start_pos}"
        raw_spans.append({
            "type": "PERSON",
            "start": idx,
            "end": idx + len(name),
            "score": 0.95,
            "word": name,
        })
        search_from[name] = idx + len(name)

    doc, aux = assemble_entities(text, doc_id, raw_spans)
    rels = extract_relations(text, doc, aux)
    doc["relationships"] = rels
    validate_ai_output(doc)
    return doc, aux, rels


def test_five_relations_english():
    """All five relation types extracted cleanly in English and pass schema validation."""
    text = (
        "Police arrested suspect Arun Kumar at the spot. "
        "Accused Arun Kumar was found in possession of mobile 9811122233. "
        "Handset 9811122233 was paired with device IMEI 351234567890123. "
        "CDR records showed mobile 9811122233 called 9822233344 repeatedly. "
        "Suspect Arun Kumar remitted Rs. 15,000/- to bank account 112233445566. "
        "Account 112233445566 was strictly controlled by Mohit Sharma."
    )
    doc, _, rels = _build_and_extract(
        text, ["Arun Kumar", "Arun Kumar", "Arun Kumar", "Mohit Sharma"], "DOC_EN"
    )
    by_type = {r["relation"]: r for r in rels}
    assert set(by_type.keys()) == {
        "OWNS_DEVICE",
        "ASSOCIATED_IMEI",
        "COMMUNICATED_WITH",
        "TRANSFERRED_FUNDS",
        "CONTROLS_ACCOUNT",
    }
    assert by_type["TRANSFERRED_FUNDS"]["amount"] == 15000.0
    assert all(r["confidence"] == 0.9 for r in rels)
    assert all(len(r["evidence_char_span"]) == 2 and r["trigger"] for r in rels)


def test_five_relations_hinglish():
    """All five relation types extracted cleanly in Roman Hinglish."""
    text = (
        "Accused Kiran Das ke paas se mobile 9811122233 baramad hua. "
        "Zabt shuda SIM 9811122233 handset IMEI 351234567890123 ke slot mein operational tha. "
        "CDR se pata chala ki phone 9811122233 ne mobile 9822233344 par calls kiye. "
        "Suspect Kiran Das ne rashi Rs. 22,500.50/- account 112233445566 mein credit karwaya. "
        "Yeh khata 112233445566 suspect Deepak Patel dwara operate kiya jata hai."
    )
    doc, _, rels = _build_and_extract(
        text, ["Kiran Das", "Kiran Das", "Deepak Patel"], "DOC_HG"
    )
    rel_types = {r["relation"] for r in rels}
    assert rel_types == {
        "OWNS_DEVICE",
        "ASSOCIATED_IMEI",
        "COMMUNICATED_WITH",
        "TRANSFERRED_FUNDS",
        "CONTROLS_ACCOUNT",
    }
    tf = [r for r in rels if r["relation"] == "TRANSFERRED_FUNDS"][0]
    assert tf["amount"] == 22500.50


def test_five_relations_devanagari():
    """All five relation types extracted cleanly in Devanagari Hindi."""
    text = (
        "तलाशी पर आरोपी अरुण वर्मा के पास से मोबाइल ९८१११२२२३३ बरामद हुआ। "
        "बरामद फोन ९८१११२२२३३ का हार्डवेयर पहचान क्रमांक ३५१२३४५६७८९०१२३ दर्ज किया गया। "
        "सीडीआर के अनुसार फोन ९८१११२२२३३ ने नंबर ९८२२२३३३४४ पर कॉल किया। "
        "अभियुक्त अरुण वर्मा ने रकम ₹ 12,000 खाता 112233445566 में प्रेषित की। "
        "खाता 112233445566 का संचालन आरोपी मोहित सिंह द्वारा किया जाता है।"
    )
    doc, _, rels = _build_and_extract(
        text, ["अरुण वर्मा", "अरुण वर्मा", "मोहित सिंह"], "DOC_HI"
    )
    rel_types = {r["relation"] for r in rels}
    assert rel_types == {
        "OWNS_DEVICE",
        "ASSOCIATED_IMEI",
        "COMMUNICATED_WITH",
        "TRANSFERRED_FUNDS",
        "CONTROLS_ACCOUNT",
    }
    tf = [r for r in rels if r["relation"] == "TRANSFERRED_FUNDS"][0]
    assert tf["amount"] == 12000.0


def test_communicated_with_direction():
    """Grammar decides caller->receiver direction; symmetric cues prefer suspect-linked phone else first."""
    # Reverse passive English: p2 -> p1
    t_rev_en = "Mobile 9811122233 received calls from 9822233344."
    d1, _, r1 = _build_and_extract(t_rev_en, [], "DOC_DIR1")
    e1 = {e["id"]: e["value"] for e in d1["entities"]}
    c1 = [r for r in r1 if r["relation"] == "COMMUNICATED_WITH"][0]
    assert (e1[c1["source"]], e1[c1["target"]]) == ("9822233344", "9811122233")

    # Reverse passive Devanagari: p2 -> p1
    t_rev_hi = "नंबर ९८१११२२२३३ पर ९८२२२३३३४४ द्वारा कॉल किया गया।"
    d2, _, r2 = _build_and_extract(t_rev_hi, [], "DOC_DIR2")
    e2 = {e["id"]: e["value"] for e in d2["entities"]}
    c2 = [r for r in r2 if r["relation"] == "COMMUNICATED_WITH"][0]
    assert (e2[c2["source"]], e2[c2["target"]]) == ("9822233344", "9811122233")

    # Forward active English: p1 -> p2
    t_fwd = "Mobile 9811122233 called 9822233344 five times."
    d3, _, r3 = _build_and_extract(t_fwd, [], "DOC_DIR3")
    e3 = {e["id"]: e["value"] for e in d3["entities"]}
    c3 = [r for r in r3 if r["relation"] == "COMMUNICATED_WITH"][0]
    assert (e3[c3["source"]], e3[c3["target"]]) == ("9811122233", "9822233344")

    # Symmetric cue fallback: phone already linked to suspect is source even if mentioned second
    t_sym = (
        "Suspect Arun Kumar used phone 9822233344. "
        "CDR logs showed sessions between 9811122233 and 9822233344."
    )
    d4, _, r4 = _build_and_extract(t_sym, ["Arun Kumar"], "DOC_DIR4")
    e4 = {e["id"]: e.get("value") for e in d4["entities"]}
    c4 = [r for r in r4 if r["relation"] == "COMMUNICATED_WITH"][0]
    assert (e4[c4["source"]], e4[c4["target"]]) == ("9822233344", "9811122233")


def test_person_and_account_transfers_with_amounts():
    """Supports both PERSON->ACCOUNT and ACCOUNT->ACCOUNT transfers with nearest amount."""
    t_pa = "Accused Rohan Das deposited Rs. 18,400.50/- into account 112233445566."
    d_pa, _, r_pa = _build_and_extract(t_pa, ["Rohan Das"], "DOC_PA")
    e_pa = {e["id"]: e for e in d_pa["entities"]}
    tf_pa = [r for r in r_pa if r["relation"] == "TRANSFERRED_FUNDS"][0]
    assert e_pa[tf_pa["source"]]["type"] == "PERSON"
    assert e_pa[tf_pa["target"]]["value"] == "112233445566"
    assert tf_pa["amount"] == 18400.5

    t_aa = "Origin account 112233445566 transferred Rs. 9,999/- to destination account 998877665544."
    d_aa, _, r_aa = _build_and_extract(t_aa, [], "DOC_AA")
    e_aa = {e["id"]: e for e in d_aa["entities"]}
    tf_aa = [r for r in r_aa if r["relation"] == "TRANSFERRED_FUNDS"][0]
    assert e_aa[tf_aa["source"]]["value"] == "112233445566"
    assert e_aa[tf_aa["target"]]["value"] == "998877665544"
    assert tf_aa["amount"] == 9999.0


def test_cash_recovery_gives_no_transfer():
    """Cash recovery or seizure sentences must NEVER emit TRANSFERRED_FUNDS."""
    text = (
        "During search, cash Rs. 45,000/- was recovered from suspect Arun Kumar near account 112233445566. "
        "तलाशी के दौरान नकद राशि ₹ 10,000 खाता 112233445566 के पास से बरामद हुई।"
    )
    _, _, rels = _build_and_extract(text, ["Arun Kumar"], "DOC_CASH")
    assert not any(r["relation"] == "TRANSFERRED_FUNDS" for r in rels)


def test_officer_never_owns_or_controls():
    """Non-suspect roles like OFFICER can never be source of OWNS_DEVICE, CONTROLS_ACCOUNT, or TRANSFERRED_FUNDS."""
    text = (
        "Sub-Inspector Vikram Joshi seized mobile 9811122233 and operated account 112233445566 "
        "and deposited Rs. 5,000/- into account 112233445566."
    )
    _, _, rels = _build_and_extract(text, ["Vikram Joshi"], "DOC_OFF")
    assert rels == []


def test_carry_forward_two_sentence_window():
    """Carries forward most recent suspect from previous 2 sentences with confidence 0.5; stops after 2 sentences."""
    text = (
        "Police apprehended suspect Arun Kumar at the gate. "
        "A search memo was prepared on the spot. "
        "Uske paas se phone 9811122233 baramad hua. "
        "Later on another day, a neutral note appeared. "
        "Finally phone 9822233344 was recovered."
    )
    doc, _, rels = _build_and_extract(text, ["Arun Kumar"], "DOC_CF")
    e_map = {e["id"]: e for e in doc["entities"]}
    owns = [r for r in rels if r["relation"] == "OWNS_DEVICE"]
    # First phone (2 sentences after Arun Kumar) matches with conf=0.5; second phone (4 sentences away) does not
    assert len(owns) == 1
    assert e_map[owns[0]["target"]]["value"] == "9811122233"
    assert owns[0]["confidence"] == 0.5


def test_two_suspects_choose_nearer():
    """When two suspects appear in the same sentence, chooses the one nearer to the phone/trigger."""
    text = (
        "Accused Arun Kumar spoke briefly while co-accused Mohit Sharma "
        "was found in possession of mobile 9811122233."
    )
    doc, _, rels = _build_and_extract(text, ["Arun Kumar", "Mohit Sharma"], "DOC_TWO_S")
    e_map = {e["id"]: e for e in doc["entities"]}
    owns = [r for r in rels if r["relation"] == "OWNS_DEVICE"]
    assert len(owns) == 1
    assert e_map[owns[0]["source"]]["canonical_name"] == "Mohit Sharma"


def test_sentence_splitting_abbreviations_initials_numbers():
    """Sentence splitter does not break abbreviations, initials, or numbers, and splits on real boundaries."""
    text = (
        "FIR No. 12/2026 u/s 318(4) BNS was registered by Dy.SP A. K. Verma for Rs. 1,50,000/- today. "
        "Accused Kiran Das transferred 20,144.99 later। दूसरा वाक्य यहाँ है।"
    )
    sents = split_sentences(text)
    assert len(sents) == 3
    assert sents[0][2].startswith("FIR No. 12/2026 u/s 318(4) BNS")
    assert sents[0][2].endswith("Rs. 1,50,000/- today.")
    assert sents[1][2] == "Accused Kiran Das transferred 20,144.99 later।"
    assert sents[2][2] == "दूसरा वाक्य यहाँ है।"
    for s, e, st in sents:
        assert text[s:e] == st


def test_deterministic_no_duplicates_and_valid():
    """Repeated cues/pairs produce no duplicate relationships and extraction is deterministic."""
    text = (
        "Accused Arun Kumar owned phone 9811122233. "
        "Accused Arun Kumar was found in possession of mobile 9811122233. "
        "Mobile 9811122233 paired with IMEI 351234567890123."
    )
    doc, aux, rels1 = _build_and_extract(text, ["Arun Kumar", "Arun Kumar"], "DOC_DET")
    rels2 = extract_relations(text, doc, aux)
    assert rels1 == rels2
    triples = [(r["source"], r["target"], r["relation"]) for r in rels1]
    assert len(triples) == len(set(triples))
    assert len(rels1) == 2

