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


# ---------------------------------------------------------------------------
# Step 6b-3: Hybrid Extractor Fallback Tests (no lexicon cue words)
# ---------------------------------------------------------------------------

from ai_pipeline.relations import extract_relations_hybrid


def _build_hybrid(text: str, names: list[str], doc_id: str = "TEST_HYB"):
    """Helper to run assemble_entities + extract_relations (cue) and extract_relations_hybrid."""
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
    cue_rels = extract_relations(text, doc, aux)
    hyb_rels = extract_relations_hybrid(text, doc, aux)
    doc["relationships"] = hyb_rels
    validate_ai_output(doc)
    return doc, aux, cue_rels, hyb_rels


def test_hybrid_fallback_ownership_person_plus_phone():
    """Structural fallback infers OWNS_DEVICE from one suspect + one phone with zero cue words."""
    text = "Suspect Arun Kumar and mobile number 9811122233 appeared in the report."
    doc, _, cue_rels, hyb_rels = _build_hybrid(text, ["Arun Kumar"], "HYB_OWN")
    assert cue_rels == []
    assert len(hyb_rels) == 1
    rel = hyb_rels[0]
    e_map = {e["id"]: e for e in doc["entities"]}
    assert rel["relation"] == "OWNS_DEVICE"
    assert e_map[rel["source"]]["canonical_name"] == "Arun Kumar"
    assert e_map[rel["target"]]["value"] == "9811122233"
    assert rel["confidence"] == 0.6
    assert rel["trigger"] == "STRUCTURE"


def test_hybrid_fallback_calls_between_two_phones():
    """Structural fallback infers COMMUNICATED_WITH from two distinct phones without suspect or cue."""
    text = "Logs listed phone 9811122233 together with phone 9822233344 yesterday."
    doc, _, cue_rels, hyb_rels = _build_hybrid(text, [], "HYB_COMM")
    assert cue_rels == []
    assert len(hyb_rels) == 1
    rel = hyb_rels[0]
    e_map = {e["id"]: e for e in doc["entities"]}
    assert rel["relation"] == "COMMUNICATED_WITH"
    assert e_map[rel["source"]]["value"] == "9811122233"
    assert e_map[rel["target"]]["value"] == "9822233344"
    assert rel["confidence"] == 0.6
    assert rel["trigger"] == "STRUCTURE"


def test_hybrid_fallback_account_to_account_with_amount():
    """Two distinct accounts and an amount without cue words trigger ACCOUNT->ACCOUNT TRANSFERRED_FUNDS."""
    text = "Statement showed bank account 112233445566, bank account 998877665544, and sum ₹ 14,500."
    doc, _, cue_rels, hyb_rels = _build_hybrid(text, [], "HYB_AA")
    assert cue_rels == []
    assert len(hyb_rels) == 1
    rel = hyb_rels[0]
    e_map = {e["id"]: e for e in doc["entities"]}
    assert rel["relation"] == "TRANSFERRED_FUNDS"
    assert e_map[rel["source"]]["value"] == "112233445566"
    assert e_map[rel["target"]]["value"] == "998877665544"
    assert rel["amount"] == 14500.0
    assert rel["confidence"] == 0.6
    assert rel["trigger"] == "STRUCTURE"


def test_hybrid_fallback_person_account_with_and_without_amount():
    """One suspect + one account yields TRANSFERRED_FUNDS when amount present, CONTROLS_ACCOUNT otherwise."""
    text_with_amt = "Accused Arun Kumar with bank account 112233445566 for sum Rs. 9,500/- appeared in audit."
    d1, _, c1, h1 = _build_hybrid(text_with_amt, ["Arun Kumar"], "HYB_PA_AMT")
    assert c1 == []
    assert len(h1) == 1
    assert h1[0]["relation"] == "TRANSFERRED_FUNDS"
    assert h1[0]["amount"] == 9500.0
    assert h1[0]["confidence"] == 0.6
    assert h1[0]["trigger"] == "STRUCTURE"

    text_no_amt = "Suspect Mohit Sharma and account 112233445566 appeared in KYC sheet."
    d2, _, c2, h2 = _build_hybrid(text_no_amt, ["Mohit Sharma"], "HYB_PA_NOAMT")
    assert c2 == []
    assert len(h2) == 1
    assert h2[0]["relation"] == "CONTROLS_ACCOUNT"
    assert "amount" not in h2[0]
    assert h2[0]["confidence"] == 0.6
    assert h2[0]["trigger"] == "STRUCTURE"


def test_hybrid_cash_recovery_gives_no_relation():
    """Cash recovery with an amount (and even suspect/account) produces no relation."""
    t1 = "During search, cash Rs. 25,000/- was recovered from suspect Arun Kumar near bank account 112233445566."
    _, _, _, h1 = _build_hybrid(t1, ["Arun Kumar"], "HYB_CASH1")
    assert h1 == []

    t2 = "तलाशी में नकद राशि ₹ 15,000 बरामद हुई आरोपी अरुण वर्मा से।"
    _, _, _, h2 = _build_hybrid(t2, ["अरुण वर्मा"], "HYB_CASH2")
    assert h2 == []


def test_hybrid_two_suspects_ambiguous_no_fallback():
    """Two distinct suspects in one sentence do not produce a fallback owner or controller."""
    text = (
        "Suspects Arun Kumar and Mohit Sharma stood beside mobile 9811122233. "
        "Accused Arun Kumar and Mohit Sharma with bank account 112233445566 for sum Rs. 5,000/- appeared."
    )
    _, _, c_rels, h_rels = _build_hybrid(
        text, ["Arun Kumar", "Mohit Sharma", "Arun Kumar", "Mohit Sharma"], "HYB_AMBIG"
    )
    assert c_rels == []
    assert h_rels == []


def test_hybrid_officer_never_owns_or_controls():
    """Officers, complainants, and witnesses never act as fallback sources."""
    text = "Sub-Inspector Vikram Joshi noted phone 9811122233 and bank account 112233445566 for Rs. 5,000/-."
    _, _, _, h_rels = _build_hybrid(text, ["Vikram Joshi"], "HYB_OFF")
    assert h_rels == []


def test_cue_version_regression_three_texts():
    """extract_relations produces identical deterministic output across three fixed English/Hinglish/Hindi texts."""
    samples = [
        (
            "Suspect Arun Kumar was found in possession of mobile 9811122233. "
            "Handset 9811122233 paired with IMEI 351234567890123. "
            "CDR showed mobile 9811122233 called 9822233344.",
            ["Arun Kumar"],
            "REG_EN",
            {("Arun Kumar", "9811122233", "OWNS_DEVICE"), ("9811122233", "351234567890123", "ASSOCIATED_IMEI"), ("9811122233", "9822233344", "COMMUNICATED_WITH")},
        ),
        (
            "Accused Kiran Das ne sum Rs. 10,000/- bank account 112233445566 mein credit karwaya. "
            "Ukt khata 112233445566 suspect Deepak Patel dwara operate kiya jata hai.",
            ["Kiran Das", "Deepak Patel"],
            "REG_HG",
            {("Kiran Das", "112233445566", "TRANSFERRED_FUNDS"), ("Deepak Patel", "112233445566", "CONTROLS_ACCOUNT")},
        ),
        (
            "आरोपी अरुण वर्मा के पास से मोबाइल ९८१११२२२३३ बरामद हुआ। "
            "अभियुक्त अरुण वर्मा ने रकम ₹ 8,000 खाता 112233445566 में प्रेषित की।",
            ["अरुण वर्मा", "अरुण वर्मा"],
            "REG_HI",
            {("अरुण वर्मा", "9811122233", "OWNS_DEVICE"), ("अरुण वर्मा", "112233445566", "TRANSFERRED_FUNDS")},
        ),
    ]
    for text, names, doc_id, expected in samples:
        doc, aux, cue1, _ = _build_hybrid(text, names, doc_id)
        cue2 = extract_relations(text, doc, aux)
        assert cue1 == cue2
        e_map = {e["id"]: e.get("canonical_name") or e.get("value") for e in doc["entities"]}
        got = {(e_map[r["source"]], e_map[r["target"]], r["relation"]) for r in cue1}
        assert got == expected


def test_hybrid_cue_wins_deterministic_and_no_duplicates():
    """Cue-based relations win over fallback, output is deterministic, valid, and duplicate-free."""
    text = (
        "Accused Arun Kumar remitted Rs. 5,000/- to bank account 112233445566. "
        "Later suspect Arun Kumar and bank account 112233445566 appeared in KYC sheet. "
        "Suspect Arun Kumar and mobile number 9811122233 were noted. "
        "Again suspect Arun Kumar and mobile number 9811122233 were listed."
    )
    doc, aux, _, h1 = _build_hybrid(
        text, ["Arun Kumar", "Arun Kumar", "Arun Kumar", "Arun Kumar"], "HYB_DUP"
    )
    h2 = extract_relations_hybrid(text, doc, aux)
    assert h1 == h2

    pairs = [(r["source"], r["target"]) for r in h1]
    assert len(pairs) == len(set(pairs))
    by_rel = {r["relation"]: r for r in h1}
    assert by_rel["TRANSFERRED_FUNDS"]["confidence"] == 0.9
    assert by_rel["TRANSFERRED_FUNDS"]["trigger"] == "remitted"
    assert by_rel["OWNS_DEVICE"]["confidence"] == 0.6
    assert by_rel["OWNS_DEVICE"]["trigger"] == "STRUCTURE"


def test_hybrid_anaphoric_owner_cross_sentence_and_guards():
    """Step 6c-2: Rule 2(a) resolves prior suspect via anaphoric possession cues; officers never match."""
    # Hinglish across single soft-wrapped newline and sentence boundary (no cue-lexicon trigger)
    t_hg = (
        "Police ne suspect Mahesh Kulkarni ko Sector 8 mein dekha.\n"
        "Isi dauran mobile 9711002201 uske paas mila."
    )
    d_hg, _, c_hg, h_hg = _build_hybrid(t_hg, ["Mahesh Kulkarni"], "HYB_ANA_OWN_HG")
    assert c_hg == []
    assert len(h_hg) == 1
    e_hg = {e["id"]: e for e in d_hg["entities"]}
    assert h_hg[0]["relation"] == "OWNS_DEVICE"
    assert e_hg[h_hg[0]["source"]]["canonical_name"] == "Mahesh Kulkarni"
    assert e_hg[h_hg[0]["target"]]["value"] == "9711002201"
    assert h_hg[0]["trigger"] == "ANAPHORA"
    assert h_hg[0]["confidence"] == 0.6

    # English cross-sentence anaphora ('from him') without CUE ownership verb
    t_en = (
        "Accused Prashant Tiwari waited outside the gate. "
        "Phone 9711002202 came from him later."
    )
    d_en, _, c_en, h_en = _build_hybrid(t_en, ["Prashant Tiwari"], "HYB_ANA_OWN_EN")
    assert c_en == []
    assert len(h_en) == 1
    e_en = {e["id"]: e for e in d_en["entities"]}
    assert h_en[0]["relation"] == "OWNS_DEVICE"
    assert e_en[h_en[0]["source"]]["canonical_name"] == "Prashant Tiwari"
    assert e_en[h_en[0]["target"]]["value"] == "9711002202"
    assert h_en[0]["trigger"] == "ANAPHORA"
    assert h_en[0]["confidence"] == 0.6

    # Devanagari cross-sentence anaphora ('उसके पास') without CUE ownership verb
    t_hi = (
        "आरोपी प्रदीप मिश्रा बाजार के पास खड़ा था। "
        "मोबाइल ९७११००२२०३ उसके पास मिला।"
    )
    d_hi, _, c_hi, h_hi = _build_hybrid(t_hi, ["प्रदीप मिश्रा"], "HYB_ANA_OWN_HI")
    assert c_hi == []
    assert len(h_hi) == 1
    e_hi = {e["id"]: e for e in d_hi["entities"]}
    assert h_hi[0]["relation"] == "OWNS_DEVICE"
    assert e_hi[h_hi[0]["source"]]["canonical_name"] == "प्रदीप मिश्रा"
    assert e_hi[h_hi[0]["target"]]["value"] == "9711002203"
    assert h_hi[0]["trigger"] == "ANAPHORA"
    assert h_hi[0]["confidence"] == 0.6

    # Officer guard & missing antecedent guard
    t_off = (
        "Inspector Deshmukh inspected the counter. "
        "Mobile 9711002201 came from him."
    )
    _, _, _, h_off = _build_hybrid(t_off, ["Deshmukh"], "HYB_ANA_OFF")
    assert h_off == []

    t_none = "A sealed envelope lay inside. Mobile 9711002201 came from him."
    _, _, _, h_none = _build_hybrid(t_none, [], "HYB_ANA_NONE")
    assert h_none == []


def test_hybrid_demonstrative_phone_and_ambiguity_guard():
    """Step 6c-2: Rule 2(b) resolves demonstrative phone to unique prior phone, skipping when ambiguous."""
    t_ok = (
        "Handset 9711002201 was seized at the spot.\n"
        "CDR records revealed ki this device se phone 9711002202 par contact hua."
    )
    doc, _, cue_rels, hyb_rels = _build_hybrid(t_ok, [], "HYB_DEM_OK")
    assert cue_rels == []
    assert len(hyb_rels) == 1
    e_map = {e["id"]: e for e in doc["entities"]}
    assert hyb_rels[0]["relation"] == "COMMUNICATED_WITH"
    assert e_map[hyb_rels[0]["source"]]["value"] == "9711002201"
    assert e_map[hyb_rels[0]["target"]]["value"] == "9711002202"
    assert hyb_rels[0]["trigger"] == "ANAPHORA"
    assert hyb_rels[0]["confidence"] == 0.6

    # Ambiguous when two distinct phones appeared across previous two sentences
    t_amb = (
        "Police spotted phone 9711002201 near the gate. "
        "Another officer logged mobile 9711002203 at the desk. "
        "CDR analysis showed this device made contact with 9711002202."
    )
    _, _, c_amb, h_amb = _build_hybrid(t_amb, [], "HYB_DEM_AMB")
    assert c_amb == []
    assert h_amb == []

    # Missing prior phone gives nothing
    t_no_ant = "Analysis showed the said number contacted 9711002202 at night."
    _, _, _, h_no_ant = _build_hybrid(t_no_ant, [], "HYB_DEM_NONE")
    assert h_no_ant == []


def test_hybrid_two_suspect_money_clauses_and_role_guards():
    """Step 6c-2: Rule 2(c) assigns sender/controller in 2-suspect money sentences across EN/HG/HI."""
    # English two-suspect money clause (both transfer and control roles)
    t_en = (
        "Victim deposed that suspect Mahesh Kulkarni remitted Rs. 45,000/- "
        "into bank account 440011223344 under control of accused Prashant Tiwari."
    )
    d_en, _, _, h_en = _build_hybrid(
        t_en, ["Mahesh Kulkarni", "Prashant Tiwari"], "HYB_2S_EN"
    )
    e_en = {e["id"]: e for e in d_en["entities"]}
    rels_en = {
        (r["relation"], e_en[r["source"]]["canonical_name"], e_en[r["target"]]["value"]): r
        for r in h_en
    }
    assert ("TRANSFERRED_FUNDS", "Mahesh Kulkarni", "440011223344") in rels_en
    assert rels_en[("TRANSFERRED_FUNDS", "Mahesh Kulkarni", "440011223344")]["amount"] == 45000.0
    assert ("CONTROLS_ACCOUNT", "Prashant Tiwari", "440011223344") in rels_en
    assert len(h_en) == len({(r["source"], r["target"], r["relation"]) for r in h_en})

    # Hinglish with soft line wrap + prior-sentence full name shortened prefix
    t_hg = (
        "Accused Alok Bansal ne gang join kiya aur Mahesh Kulkarni ke sath kaam kiya.\n"
        "Mahesh ne account\n"
        "550011223344 mein Rs. 80,000/- transfer kiye jo mastermind Prashant Tiwari dwara operate hota hai."
    )
    d_hg, _, _, h_hg = _build_hybrid(
        t_hg, ["Alok Bansal", "Mahesh Kulkarni", "Prashant Tiwari"], "HYB_2S_HG"
    )
    e_hg = {e["id"]: e for e in d_hg["entities"]}
    rels_hg = {
        (r["relation"], e_hg[r["source"]]["canonical_name"], e_hg[r["target"]]["value"]): r
        for r in h_hg
    }
    assert ("TRANSFERRED_FUNDS", "Mahesh Kulkarni", "550011223344") in rels_hg
    assert rels_hg[("TRANSFERRED_FUNDS", "Mahesh Kulkarni", "550011223344")]["amount"] == 80000.0
    assert ("CONTROLS_ACCOUNT", "Prashant Tiwari", "550011223344") in rels_hg

    # Devanagari SOV two-suspect sentence
    t_hi = (
        "आरोपी प्रदीप मिश्रा ने खाता 440011223344 में ₹ 25,000 ट्रांसफर किए "
        "जिसका मुख्य संचालक आरोपी विनोद गुप्ता द्वारा संचालन किया जाता है।"
    )
    d_hi, _, _, h_hi = _build_hybrid(
        t_hi, ["प्रदीप मिश्रा", "विनोद गुप्ता"], "HYB_2S_HI"
    )
    e_hi = {e["id"]: e for e in d_hi["entities"]}
    rels_hi = {
        (r["relation"], e_hi[r["source"]]["canonical_name"], e_hi[r["target"]]["value"]): r
        for r in h_hi
    }
    assert ("TRANSFERRED_FUNDS", "प्रदीप मिश्रा", "440011223344") in rels_hi
    assert rels_hi[("TRANSFERRED_FUNDS", "प्रदीप मिश्रा", "440011223344")]["amount"] == 25000.0
    assert ("CONTROLS_ACCOUNT", "विनोद गुप्ता", "440011223344") in rels_hi

    # Ambiguity preserved when neither role cue exists, and cash recovery stays empty
    t_amb = "Accused Mahesh Kulkarni and Prashant Tiwari discussed bank account 440011223344 with Rs. 12,000/-."
    _, _, _, h_amb = _build_hybrid(t_amb, ["Mahesh Kulkarni", "Prashant Tiwari"], "HYB_2S_AMB")
    assert h_amb == []

    t_cash = "Cash Rs. 30,000/- was recovered from Mahesh Kulkarni and Prashant Tiwari near account 440011223344."
    _, _, _, h_cash = _build_hybrid(t_cash, ["Mahesh Kulkarni", "Prashant Tiwari"], "HYB_2S_CASH")
    assert h_cash == []

    # Officer guard: officer near control/transfer cue must not become controller/sender
    t_off = (
        "Suspect Mahesh Kulkarni transferred Rs. 15,000/- into account 440011223344 "
        "operated by Inspector Deshmukh and suspect Prashant Tiwari."
    )
    d_off, _, _, h_off = _build_hybrid(
        t_off, ["Mahesh Kulkarni", "Deshmukh", "Prashant Tiwari"], "HYB_2S_OFF"
    )
    e_off = {e["id"]: e for e in d_off["entities"]}
    for r in h_off:
        assert e_off[r["source"]]["role"] == "SUSPECT"
        assert e_off[r["source"]]["canonical_name"] != "Deshmukh"


def test_cue_only_extract_relations_unchanged_and_no_duplicates():
    """Step 6c-2: Verify extract_relations (cue-only) behavior is unchanged across EN/HG/HI."""
    fixed_cases = [
        (
            "Suspect Mahesh Kulkarni owned mobile 9711002201. "
            "Accused Mahesh Kulkarni remitted Rs. 5,000/- to bank account 440011223344.",
            ["Mahesh Kulkarni", "Mahesh Kulkarni"],
            {("OWNS_DEVICE", "Mahesh Kulkarni", "9711002201"), ("TRANSFERRED_FUNDS", "Mahesh Kulkarni", "440011223344")},
        ),
        (
            "Handset 9711002201 was paired with device IMEI 861234567890123. "
            "Account 440011223344 was controlled by Prashant Tiwari.",
            ["Prashant Tiwari"],
            {("ASSOCIATED_IMEI", "9711002201", "861234567890123"), ("CONTROLS_ACCOUNT", "Prashant Tiwari", "440011223344")},
        ),
        (
            "आरोपी प्रदीप मिश्रा ने रकम ₹ 10,000 खाता 440011223344 में प्रेषित की।",
            ["प्रदीप मिश्रा"],
            {("TRANSFERRED_FUNDS", "प्रदीप मिश्रा", "440011223344")},
        ),
    ]
    for idx, (txt, names, expected_triples) in enumerate(fixed_cases):
        doc, aux, cue_rels, hyb_rels = _build_hybrid(txt, names, f"CUE_FIXED_{idx}")
        e_map = {e["id"]: e for e in doc["entities"]}
        cue_triples = {
            (
                r["relation"],
                e_map[r["source"]].get("canonical_name") or e_map[r["source"]].get("value"),
                e_map[r["target"]].get("canonical_name") or e_map[r["target"]].get("value"),
            )
            for r in cue_rels
        }
        assert cue_triples == expected_triples
        assert len({(r["source"], r["target"], r["relation"]) for r in hyb_rels}) == len(hyb_rels)



