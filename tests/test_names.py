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

