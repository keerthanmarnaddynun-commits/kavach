"""
Unit tests for Step 6a: ai_pipeline/names.py
Tests honorific stripping, alias cues, father cues, role cues,
model span replacement by alias, honorific-only span dropping,
idempotency, ordering, and surface matching without loading any ML model.
"""
import pytest
from ai_pipeline.names import (
    HONORIFICS,
    STOPWORDS,
    strip_honorific,
    find_aliases,
    find_fathers,
    role_for,
    extract_names,
)


def test_honorific_stripping_with_and_without_dot():
    """Test each honorific in Roman and Devanagari, with and without dot."""
    for hon in HONORIFICS:
        # Without dot
        text1 = f"{hon} Rajesh Kumar"
        s1, e1 = 0, len(text1)
        ns1, ne1 = strip_honorific(text1, s1, e1)
        assert text1[ns1:ne1] == "Rajesh Kumar", f"Failed for {hon} without dot: got {text1[ns1:ne1]!r}"

        # With dot
        text2 = f"{hon}. Rajesh Kumar"
        s2, e2 = 0, len(text2)
        ns2, ne2 = strip_honorific(text2, s2, e2)
        assert text2[ns2:ne2] == "Rajesh Kumar", f"Failed for {hon} with dot: got {text2[ns2:ne2]!r}"


def test_alias_cues():
    """Test alias extraction including @ chains, (alias X), and Devanagari उर्फ."""
    # @ chains: urf A @ B @ C
    text1 = "Accused Suresh urf Amar @ Bunty @ Chintu s/o Ramesh"
    aliases1 = find_aliases(text1)
    surfaces1 = [a["surface"] for a in aliases1]
    assert surfaces1 == ["Amar", "Bunty", "Chintu"]
    for a in aliases1:
        assert a["type"] == "ALIAS"
        assert text1[a["start"]:a["end"]] == a["surface"]

    # Parenthesized alias: (alias X)
    text2 = "Accused Suresh (alias Kali) s/o Ramesh"
    aliases2 = find_aliases(text2)
    assert len(aliases2) == 1
    assert aliases2[0]["surface"] == "Kali"
    assert aliases2[0]["type"] == "ALIAS"
    assert text2[aliases2[0]["start"]:aliases2[0]["end"]] == "Kali"

    # Devanagari उर्फ
    text3 = "अभियुक्त राहुल उर्फ गोलू पुत्र रमेश"
    aliases3 = find_aliases(text3)
    assert len(aliases3) == 1
    assert aliases3[0]["surface"] == "गोलू"
    assert aliases3[0]["type"] == "ALIAS"
    assert text3[aliases3[0]["start"]:aliases3[0]["end"]] == "गोलू"


def test_father_cues():
    """Test father cues with Shri, d/o, w/o, पुत्र."""
    # with Shri
    text1 = "Rohan s/o Shri Suresh Lal r/o Delhi"
    fathers1 = find_fathers(text1)
    assert len(fathers1) == 1
    assert fathers1[0]["surface"] == "Suresh Lal"
    assert fathers1[0]["type"] == "FATHER"
    assert text1[fathers1[0]["start"]:fathers1[0]["end"]] == "Suresh Lal"

    # d/o
    text2 = "Pooja d/o Sita Devi r/o Mumbai"
    fathers2 = find_fathers(text2)
    assert len(fathers2) == 1
    assert fathers2[0]["surface"] == "Sita Devi"
    assert fathers2[0]["type"] == "FATHER"
    assert text2[fathers2[0]["start"]:fathers2[0]["end"]] == "Sita Devi"

    # w/o
    text3 = "Anita w/o Smt. Sunita Sharma r/o Pune"
    fathers3 = find_fathers(text3)
    assert len(fathers3) == 1
    assert fathers3[0]["surface"] == "Sunita Sharma"
    assert fathers3[0]["type"] == "FATHER"
    assert text3[fathers3[0]["start"]:fathers3[0]["end"]] == "Sunita Sharma"

    # पुत्र
    text4 = "रोहन पुत्र श्री रमेश चंद्र निवासी जयपुर"
    fathers4 = find_fathers(text4)
    assert len(fathers4) == 1
    assert fathers4[0]["surface"] == "रमेश चंद्र"
    assert fathers4[0]["type"] == "FATHER"
    assert text4[fathers4[0]["start"]:fathers4[0]["end"]] == "रमेश चंद्र"


def test_role_cues():
    """Test role assignment for OFFICER, COMPLAINANT, WITNESS, SUSPECT in Roman and Devanagari."""
    # OFFICER
    t_off1 = "Investigating officer IO SI Ramesh Kumar registered the FIR"
    assert role_for(t_off1, 28, 40) == "OFFICER"
    t_off2 = "मामले की जांच विवेचक उप-निरीक्षक सुरेश कुमार द्वारा की गई"
    assert role_for(t_off2, 33, 44) == "OFFICER"

    # COMPLAINANT
    t_comp1 = "Complainant victim Rajesh Kumar approached the police station"
    assert role_for(t_comp1, 19, 31) == "COMPLAINANT"
    t_comp2 = "शिकायतकर्ता वादी प्रार्थी रमेश यादव ने सूचना दी"
    assert role_for(t_comp2, 25, 34) == "COMPLAINANT"

    # WITNESS
    t_wit1 = "Independent witness Mahesh Gupta was present at the spot"
    assert role_for(t_wit1, 20, 32) == "WITNESS"
    t_wit2 = "घटना के समय साक्षी पंच गवाह दिनेश सिंह मौजूद थे"
    assert role_for(t_wit2, 24, 34) == "WITNESS"

    # SUSPECT
    t_susp1 = "During patrolling suspect accused Vijay Kumar was spotted"
    assert role_for(t_susp1, 34, 45) == "SUSPECT"
    t_susp2 = "अभियुक्त रोहन वर्मा मौके से फरार हो गया"
    assert role_for(t_susp2, 9, 19) == "SUSPECT"


def test_model_span_replaced_by_alias():
    """Test that a model span is replaced by an overlapping cue-based alias."""
    text = "The accused was identified as alias Pandit near the market."
    # Model returns incomplete span "Pand"
    pand_start = text.find("Pandit")
    pand_end = pand_start + 4  # "Pand"
    model_spans = [
        {"type": "PER", "start": pand_start, "end": pand_end, "word": "Pand"}
    ]
    res = extract_names(text, model_spans)
    assert len(res) == 1
    assert res[0]["surface"] == "Pandit"
    assert res[0]["type"] == "ALIAS"
    assert res[0]["start"] == pand_start
    assert res[0]["end"] == pand_start + len("Pandit")


def test_honorific_only_span_dropped():
    """Test that spans containing only an honorific or empty after stripping are dropped."""
    text = "Shri was seen near the corner with Mr. and Smt."
    model_spans = [
        {"type": "PER", "start": 0, "end": 4, "word": "Shri"},
        {"type": "PER", "start": 35, "end": 38, "word": "Mr."},
        {"type": "PER", "start": 43, "end": 47, "word": "Smt."},
    ]
    res = extract_names(text, model_spans)
    assert len(res) == 0


def test_no_overlap_sorted_idempotent():
    """Test that extract_names produces non-overlapping, sorted spans and is idempotent."""
    text = (
        "Complainant Anita Devi filed report. IO SI Ramesh Kumar arrested "
        "accused Rohan urf Kallu @ Billa s/o Shri Suresh Lal."
    )
    # Simulate various model spans, some with honorifics, some overlapping
    model_spans = [
        {"type": "PER", "start": 12, "end": 22, "word": "Anita Devi"},
        {"type": "PER", "start": 40, "end": 55, "word": "SI Ramesh Kumar"},
        {"type": "PER", "start": 73, "end": 78, "word": "Rohan"},
        {"type": "PER", "start": 83, "end": 88, "word": "Kallu"},
        {"type": "PER", "start": 91, "end": 96, "word": "Billa"},
        {"type": "PER", "start": 105, "end": 120, "word": "Shri Suresh Lal"},
    ]
    res1 = extract_names(text, model_spans)

    # Check sorted
    starts = [sp["start"] for sp in res1]
    assert starts == sorted(starts)

    # Check non-overlapping
    for i in range(len(res1) - 1):
        assert res1[i]["end"] <= res1[i + 1]["start"], (
            f"Overlap found between {res1[i]} and {res1[i+1]}"
        )

    # Check idempotency
    res2 = extract_names(text, res1)
    assert res1 == res2


def test_spans_match_original_text():
    """Test that all returned spans have text[start:end] == surface and STOPWORDS are dropped."""
    text = "Zabt officer IO Ramesh Patel seized the vehicle from accused Vikas."
    model_spans = [
        {"type": "PER", "start": 0, "end": 4, "word": "Zabt"},  # in STOPWORDS
        {"type": "PER", "start": 16, "end": 28, "word": "Ramesh Patel"},
        {"type": "PER", "start": 61, "end": 66, "word": "Vikas"},
    ]
    res = extract_names(text, model_spans)
    surfaces = [sp["surface"] for sp in res]
    assert "Zabt" not in surfaces
    assert "Ramesh Patel" in surfaces
    assert "Vikas" in surfaces

    for sp in res:
        assert text[sp["start"]:sp["end"]] == sp["surface"]


def test_cue_trim_trailing_alias():
    """Trailing cue 'alias' (case-insensitive) is trimmed with exact offsets."""
    text = "Suspect Arun Verma alias fled from the spot."
    start = text.index("Arun Verma alias")
    end = start + len("Arun Verma alias")
    res = extract_names(text, [{"type": "PER", "start": start, "end": end, "word": "Arun Verma alias"}])
    assert len(res) == 1
    assert res[0]["type"] == "PERSON"
    assert res[0]["surface"] == "Arun Verma"
    assert text[res[0]["start"]:res[0]["end"]] == "Arun Verma"


def test_cue_trim_leading_urf():
    """Leading cue 'urf' is trimmed cleanly on the original text."""
    text = "Suspect urf (Arun Singh) fled from the spot."
    start = text.index("urf (Arun Singh)")
    end = start + len("urf (Arun Singh)")
    res = extract_names(text, [{"type": "PER", "start": start, "end": end, "word": "urf (Arun Singh)"}])
    assert len(res) == 1
    assert res[0]["type"] == "PERSON"
    assert res[0]["surface"] == "Arun Singh"
    assert text[res[0]["start"]:res[0]["end"]] == "Arun Singh"


def test_cue_trim_devanagari_trailing_urf():
    """Devanagari trailing उर्फ and उर्फ़ are trimmed with exact offsets."""
    for cue in ("उर्फ", "उर्फ़"):
        text = f"व्यक्ति मोहन शर्मा {cue} ने बताया"
        raw = f"मोहन शर्मा {cue}"
        start = text.index(raw)
        end = start + len(raw)
        res = extract_names(text, [{"type": "PER", "start": start, "end": end, "word": raw}])
        assert len(res) == 1
        assert res[0]["type"] == "PERSON"
        assert res[0]["surface"] == "मोहन शर्मा"
        assert text[res[0]["start"]:res[0]["end"]] == "मोहन शर्मा"


def test_cue_trim_both_ends():
    """Multiple cue tokens and edge symbols on both ends are trimmed repeatedly."""
    text = "Accused @ (Arun Kumar) aka ran away; witness r/o (Meera Nair) s/o spoke."
    s1 = text.index("@ (Arun Kumar) aka")
    e1 = s1 + len("@ (Arun Kumar) aka")
    s2 = text.index("r/o (Meera Nair) s/o")
    e2 = s2 + len("r/o (Meera Nair) s/o")
    res = extract_names(
        text,
        [
            {"type": "PER", "start": s1, "end": e1, "word": text[s1:e1]},
            {"type": "PER", "start": s2, "end": e2, "word": text[s2:e2]},
        ],
    )
    assert [sp["surface"] for sp in res] == ["Arun Kumar", "Meera Nair"]
    for sp in res:
        assert sp["type"] == "PERSON"
        assert text[sp["start"]:sp["end"]] == sp["surface"]


def test_cue_only_span_dropped():
    """Spans consisting solely of cue tokens (like 'alias' or 'son of') are dropped."""
    text = "He was called alias and son of around the area."
    s1 = text.index("alias")
    s2 = text.index("son of")
    res = extract_names(
        text,
        [
            {"type": "PER", "start": s1, "end": s1 + 5, "word": "alias"},
            {"type": "PER", "start": s2, "end": s2 + 6, "word": "son of"},
        ],
    )
    assert res == []


def test_whole_token_boundary_not_trimmed():
    """Names containing 'son' or 'of' inside another word are NOT trimmed."""
    text = "Complainant Robson and witness Sonia Offerman reported."
    s1 = text.index("Robson")
    s2 = text.index("Sonia Offerman")
    res = extract_names(
        text,
        [
            {"type": "PER", "start": s1, "end": s1 + len("Robson"), "word": "Robson"},
            {"type": "PER", "start": s2, "end": s2 + len("Sonia Offerman"), "word": "Sonia Offerman"},
        ],
    )
    assert [sp["surface"] for sp in res] == ["Robson", "Sonia Offerman"]
    for sp in res:
        assert text[sp["start"]:sp["end"]] == sp["surface"]


def test_cue_trim_idempotent_and_valid_offsets():
    """Trimmed extract_names output is idempotent and offsets always slice the original text."""
    from ai_pipeline.names import CUE_TOKENS

    assert isinstance(CUE_TOKENS, tuple)
    text = "Witness @ Sonia Offerman a.k.a. and accused Robson alias ran away."
    s1 = text.index("@ Sonia Offerman a.k.a.")
    s2 = text.index("Robson alias")
    res1 = extract_names(
        text,
        [
            {"type": "PER", "start": s1, "end": s1 + len("@ Sonia Offerman a.k.a."), "word": text[s1:s1 + len("@ Sonia Offerman a.k.a.")]},
            {"type": "PER", "start": s2, "end": s2 + len("Robson alias"), "word": text[s2:s2 + len("Robson alias")]},
        ],
    )
    assert [sp["surface"] for sp in res1] == ["Sonia Offerman", "Robson"]
    for sp in res1:
        assert text[sp["start"]:sp["end"]] == sp["surface"]
    assert extract_names(text, res1) == res1


def test_alias_stops_at_location_words_and_numbers():
    """Step 6c-2: Aliases stop before location stopwords and standalone numbers in Roman/Devanagari."""
    cases = [
        ("Suspect Mahesh Kulkarni urf Minto Sector 12 dwara pakda gaya.", ["Minto"]),
        ("Accused Prashant Tiwari alias Kobo 45 resides nearby.", ["Kobo"]),
        ("Suspect Alok Bansal aka Tiko Colony 9 was questioned.", ["Tiko"]),
        ("Suspect Harish Mehta urf Zorro Nagar went missing.", ["Zorro"]),
        ("Suspect Nitin Verma alias Piko Road near Chowk.", ["Piko"]),
        ("Accused Sanjay Kapoor urf Gopo Thana area case.", ["Gopo"]),
        ("आरोपी प्रदीप मिश्रा उर्फ़ मिंटो सेक्टर १२ से पकड़ा गया।", ["मिंटो"]),
        ("आरोपी विनोद गुप्ता उर्फ गोपू १२ बाजार के पास मिला।", ["गोपू"]),
        ("अभियुक्त हरीश यादव उर्फ़ टोनी नगर और उर्फ़ मोंटी गांव निवासी।", ["टोनी", "मोंटी"]),
    ]
    for text, expected in cases:
        aliases = find_aliases(text)
        assert [a["surface"] for a in aliases] == expected, f"Failed for {text!r}: {aliases}"
        for a in aliases:
            assert text[a["start"]:a["end"]] == a["surface"]
        extracted = extract_names(text, [])
        ext_aliases = [sp["surface"] for sp in extracted if sp["type"] == "ALIAS"]
        assert ext_aliases == expected, f"extract_names failed for {text!r}: {extracted}"



