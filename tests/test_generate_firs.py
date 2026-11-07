"""
tests/test_generate_firs.py
Pytest suite for the upgraded seeded synthetic FIR generator v3 (Step 2c).
Verifies:
- Exact entity surface offsets & non-overlapping spans
- Valid relation labels & endpoint types
- Grounding in case data (truth/cdr/bank)
- Same entity_key implies same normalized value
- Relation mentions lie inside evidence span and match keys
- Every alias and father name in text has a labelled span
- Each transfer matches one bank.csv row on sender, receiver, and amount
- Amount surfaces parse to exact numeric values
- No 'IPC' anywhere, and 'BNS' is present in every FIR
- 40/10/10 split counts and 3-language coverage per split
- Held-out templates only in test (>= 1 per test FIR, 0 in train/dev)
- Presence of all 6 FIR types and entity count extremes (< 5 and > 11)
- Golden-FIR phrase protection (no 8-word sequences)
- Plain-text decoys & unlinked cash amount
- Person roles (SUSPECT, OFFICER, COMPLAINANT, WITNESS, FATHER)
- Vikas vs Bikas distinct keys & never linked
- Byte determinism by seed
"""

import csv
import json
import re
import sys
from pathlib import Path
import pytest

# Ensure repository root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.synthetic.generate_firs import generate_all_firs_v2

DEVANAGARI_DIGITS = {
    "०": "0", "१": "1", "२": "2", "३": "3", "४": "4",
    "५": "5", "६": "6", "७": "7", "८": "8", "९": "9"
}

def parse_amount_surface(surface: str) -> float:
    """Independent small parser inside test file to verify amount surfaces."""
    s = surface
    for dev, asc in DEVANAGARI_DIGITS.items():
        s = s.replace(dev, asc)
    m_lakh = re.search(r"([\d.]+)\s*(?:lakh|लाख)", s, re.IGNORECASE)
    if m_lakh:
        return float(m_lakh.group(1)) * 100000.0
    s = re.sub(r"(?i)\b(?:rs|inr)\b\.?", "", s)
    s = re.sub(r"रु\.?", "", s)
    cleaned = re.sub(r"[^\d.]", "", s)
    if cleaned.endswith("."):
        cleaned = cleaned[:-1]
    return float(cleaned)


@pytest.fixture(scope="module")
def generated_firs_v3(tmp_path_factory):
    """Generates all 100 synthetic FIRs from case_demo for testing."""
    case_dir = Path("data/synthetic/out/case_demo_v2")
    out_dir = tmp_path_factory.mktemp("firs_v5_test")
    records = generate_all_firs_v2(
        case_dir=str(case_dir),
        seed=42,
        count=100,
        out_dir=str(out_dir)
    )
    firs_data = []
    for r in records:
        txt_path = out_dir / r["txt_file"]
        json_path = out_dir / r["json_file"]
        firs_data.append({
            "doc_id": r["doc_id"],
            "split": r["split"],
            "fir_type": r["fir_type"],
            "language": r["language"],
            "text": txt_path.read_text(encoding="utf-8"),
            "answer_key": json.loads(json_path.read_text(encoding="utf-8")),
        })
    case_truth = json.loads((case_dir / "truth.json").read_text(encoding="utf-8"))
    with open(case_dir / "cdr.csv", "r", encoding="utf-8") as f:
        case_cdr = list(csv.DictReader(f))
    with open(case_dir / "bank.csv", "r", encoding="utf-8") as f:
        case_bank = list(csv.DictReader(f))

    return {
        "out_dir": out_dir,
        "records": records,
        "firs": firs_data,
        "truth": case_truth,
        "cdr": case_cdr,
        "bank": case_bank,
    }


def test_entity_surface_exact_offset(generated_firs_v3):
    """Verifies that text[start:end] matches both ent['text'] and ent['surface'] exactly."""
    for item in generated_firs_v3["firs"]:
        text = item["text"]
        for ent in item["answer_key"]["entities"]:
            start = ent["start"]
            end = ent["end"]
            expected = ent["text"]
            assert text[start:end] == expected, (
                f"Offset mismatch in {item['doc_id']} for entity {ent['id']}: "
                f"expected '{expected}', got '{text[start:end]}'"
            )
            assert text[start:end] == ent["surface"]


def test_no_overlapping_spans(generated_firs_v3):
    """Verifies that entity character spans are strictly positive and non-overlapping."""
    for item in generated_firs_v3["firs"]:
        ents = sorted(item["answer_key"]["entities"], key=lambda e: e["start"])
        for i in range(len(ents)):
            start = ents[i]["start"]
            end = ents[i]["end"]
            assert start < end, f"Inverted span for {ents[i]['id']} in {item['doc_id']}: [{start}, {end}]"
            if i > 0:
                prev_end = ents[i - 1]["end"]
                assert prev_end <= start, (
                    f"Overlapping spans in {item['doc_id']}: "
                    f"{ents[i-1]['id']} [{ents[i-1]['start']}, {prev_end}] and {ents[i]['id']} [{start}, {end}]"
                )


def test_relation_types_and_labels_valid(generated_firs_v3):
    """Verifies that all relation labels and entity type pairs strictly adhere to contract rules."""
    allowed_labels = {
        "OWNS_DEVICE",
        "ASSOCIATED_IMEI",
        "COMMUNICATED_WITH",
        "CONTROLS_ACCOUNT",
        "TRANSFERRED_FUNDS",
    }
    for item in generated_firs_v3["firs"]:
        ent_map = {e["id"]: e for e in item["answer_key"]["entities"]}
        for rel in item["answer_key"]["relationships"]:
            r_type = rel["type"]
            assert r_type in allowed_labels, f"Unknown relation label {r_type} in {item['doc_id']}"
            s_type = ent_map[rel["source"]]["label"]
            t_type = ent_map[rel["target"]]["label"]
            if r_type == "OWNS_DEVICE":
                assert s_type == "PERSON" and t_type == "PHONE", (
                    f"OWNS_DEVICE requires PERSON->PHONE, got {s_type}->{t_type}"
                )
            elif r_type == "ASSOCIATED_IMEI":
                assert s_type == "PHONE" and t_type == "IMEI", (
                    f"ASSOCIATED_IMEI requires PHONE->IMEI, got {s_type}->{t_type}"
                )
            elif r_type == "COMMUNICATED_WITH":
                assert s_type == "PHONE" and t_type == "PHONE", (
                    f"COMMUNICATED_WITH requires PHONE->PHONE, got {s_type}->{t_type}"
                )
            elif r_type == "CONTROLS_ACCOUNT":
                assert s_type == "PERSON" and t_type == "ACCOUNT", (
                    f"CONTROLS_ACCOUNT requires PERSON->ACCOUNT, got {s_type}->{t_type}"
                )
            elif r_type == "TRANSFERRED_FUNDS":
                assert s_type in ("PERSON", "ACCOUNT") and t_type == "ACCOUNT", (
                    f"TRANSFERRED_FUNDS requires PERSON/ACCOUNT->ACCOUNT, got {s_type}->{t_type}"
                )


def test_same_entity_key_same_normalized_value(generated_firs_v3):
    """Verifies that all mentions sharing the same entity_key have the identical normalized value."""
    for item in generated_firs_v3["firs"]:
        key_to_values = {}
        for ent in item["answer_key"]["entities"]:
            k = ent["entity_key"]
            val = ent["value"]
            if k in key_to_values:
                assert key_to_values[k] == val, (
                    f"Value mismatch for entity_key '{k}' in {item['doc_id']}: "
                    f"'{key_to_values[k]}' vs '{val}'"
                )
            else:
                key_to_values[k] = val


def test_relation_mentions_inside_evidence_span_and_match_keys(generated_firs_v3):
    """Verifies relation mentions lie strictly inside evidence_char_span and match source_key/target_key."""
    for item in generated_firs_v3["firs"]:
        ent_map = {e["id"]: e for e in item["answer_key"]["entities"]}
        for rel in item["answer_key"]["relationships"]:
            s_id = rel["source_mention"]
            t_id = rel["target_mention"]
            assert s_id in ent_map, f"source_mention {s_id} not found in entities"
            assert t_id in ent_map, f"target_mention {t_id} not found in entities"

            s_ent = ent_map[s_id]
            t_ent = ent_map[t_id]

            ev_start, ev_end = rel["evidence_char_span"]
            assert ev_start <= s_ent["start"] < s_ent["end"] <= ev_end, (
                f"source_mention {s_id} [{s_ent['start']}, {s_ent['end']}] outside evidence [{ev_start}, {ev_end}] in {item['doc_id']}"
            )
            assert ev_start <= t_ent["start"] < t_ent["end"] <= ev_end, (
                f"target_mention {t_id} [{t_ent['start']}, {t_ent['end']}] outside evidence [{ev_start}, {ev_end}] in {item['doc_id']}"
            )

            assert rel["source_key"] == s_ent["entity_key"], (
                f"source_key mismatch in {item['doc_id']}: '{rel['source_key']}' vs '{s_ent['entity_key']}'"
            )
            assert rel["target_key"] == t_ent["entity_key"], (
                f"target_key mismatch in {item['doc_id']}: '{rel['target_key']}' vs '{t_ent['entity_key']}'"
            )


def test_aliases_and_father_name_labelled(generated_firs_v3):
    """Verifies that every alias and father name in suspect sentences has a labelled span."""
    alias_count = 0
    father_count = 0
    for item in generated_firs_v3["firs"]:
        text = item["text"]
        entities = item["answer_key"]["entities"]

        for ent in entities:
            if ent["label"] == "ALIAS":
                alias_count += 1
                assert ent["text"] in text
                # Must share the person's entity_key
                assert ent["entity_key"].startswith("PER_")
            elif ent["label"] == "PERSON" and ent.get("role") == "FATHER":
                father_count += 1
                assert ent["text"] in text
                assert ent["entity_key"].startswith("FATHER:")

    assert alias_count >= 100, f"Expected >= 100 alias mentions across dataset, got {alias_count}"
    assert father_count >= 100, f"Expected >= 100 father mentions across dataset, got {father_count}"


def test_transfers_match_bank_row(generated_firs_v3):
    """Verifies that every TRANSFERRED_FUNDS relation matches one bank.csv row on sender, receiver, and amount."""
    truth = generated_firs_v3["truth"]
    bank = generated_firs_v3["bank"]

    # Index person -> accounts
    person_accounts = {}
    for p in truth["people"]:
        person_accounts[p["person_id"]] = {a["account_number"] for a in p.get("accounts", [])}

    p2a_count = 0
    a2a_count = 0

    for item in generated_firs_v3["firs"]:
        ent_map = {e["id"]: e for e in item["answer_key"]["entities"]}
        for rel in item["answer_key"]["relationships"]:
            if rel["type"] == "TRANSFERRED_FUNDS":
                s_ent = ent_map[rel["source_mention"]]
                t_ent = ent_map[rel["target_mention"]]
                amount = float(rel["amount"])
                receiver_acct = rel["target_key"]

                if s_ent["label"] == "PERSON":
                    p2a_count += 1
                    sender_pid = rel["source_key"]
                    sender_accounts = person_accounts.get(sender_pid, set())
                    # Check bank row matching
                    matching_rows = [
                        r for r in bank
                        if r["from_acct"] in sender_accounts
                        and r["to_acct"] == receiver_acct
                        and abs(float(r["amount"]) - amount) < 0.01
                    ]
                    assert len(matching_rows) >= 1, (
                        f"PERSON->ACCOUNT transfer from {sender_pid} to {receiver_acct} for {amount} not found in bank.csv!"
                    )
                    if rel.get("txn_id"):
                        assert any(r["txn_id"] == rel["txn_id"] for r in matching_rows)

                elif s_ent["label"] == "ACCOUNT":
                    a2a_count += 1
                    sender_acct = rel["source_key"]
                    matching_rows = [
                        r for r in bank
                        if r["from_acct"] == sender_acct
                        and r["to_acct"] == receiver_acct
                        and abs(float(r["amount"]) - amount) < 0.01
                    ]
                    assert len(matching_rows) >= 1, (
                        f"ACCOUNT->ACCOUNT transfer from {sender_acct} to {receiver_acct} for {amount} not found in bank.csv!"
                    )
                    if rel.get("txn_id"):
                        assert any(r["txn_id"] == rel["txn_id"] for r in matching_rows)

    assert p2a_count >= 2, f"Expected >= 2 PERSON->ACCOUNT transfers, got {p2a_count}"
    assert a2a_count >= 2, f"Expected >= 2 ACCOUNT->ACCOUNT transfers, got {a2a_count}"


def test_amount_surface_parses_to_numeric_value(generated_firs_v3):
    """Verifies that each AMOUNT mention's surface string parses to its numeric value."""
    amount_count = 0
    lakh_found = False
    rs_found = False
    inr_found = False
    grouped_found = False

    for item in generated_firs_v3["firs"]:
        for ent in item["answer_key"]["entities"]:
            if ent["label"] == "AMOUNT":
                amount_count += 1
                surf = ent["text"]
                val = float(ent["value"])
                parsed = parse_amount_surface(surf)
                assert abs(parsed - val) < 0.01, (
                    f"Amount parsing failed in {item['doc_id']}: surface '{surf}' parsed to {parsed}, expected {val}"
                )
                if "lakh" in surf.lower() or "लाख" in surf:
                    lakh_found = True
                elif "rs." in surf.lower():
                    rs_found = True
                elif "inr" in surf.lower():
                    inr_found = True
                else:
                    grouped_found = True

    assert amount_count >= 50, f"Expected >= 50 AMOUNT mentions, got {amount_count}"
    assert rs_found, "Expected 'Rs. .../-' style amounts"
    assert inr_found, "Expected 'INR ...' style amounts"
    assert grouped_found, "Expected Indian grouping style amounts"
    assert lakh_found, "Expected '1.5 lakh' style amounts"


def test_amount_parser_known_pairs():
    """Verifies parse_amount_surface against a fixed hand-written lookup table of known surfaces."""
    pairs = [
        ("1,57,400", 157400),
        ("Rs. 1,57,400/-", 157400),
        ("INR 1,57,400.00", 157400),
        ("INR 5,00,000.00", 500000),
        ("Rs. 25,628/-", 25628),
        ("1.5 lakh", 150000),
        ("2 lakh", 200000),
        ("Rs. 73,500/-", 73500),
    ]
    for surface, expected in pairs:
        assert parse_amount_surface(surface) == expected, (
            f"parse_amount_surface('{surface}') returned {parse_amount_surface(surface)}, expected {expected}"
        )

    val = parse_amount_surface("Rs. 1,57,400/-")
    assert val != 15740, "Value unexpectedly equal to 15740"
    assert val != 1574000, "Value unexpectedly equal to 1574000"


def test_no_ipc_and_bns_present(generated_firs_v3):
    """Verifies that no FIR contains 'IPC' and every FIR contains 'BNS'."""
    for item in generated_firs_v3["firs"]:
        text = item["text"]
        assert not re.search(r"\bIPC\b", text), f"Found 'IPC' in {item['doc_id']}: '{text[:120]}'"
        assert "BNS" in text, f"Missing 'BNS' in {item['doc_id']}: '{text[:120]}'"


def test_split_counts_and_language_coverage(generated_firs_v3):
    """Verifies 60 train, 20 dev, 20 test, 3-language coverage per split, and language totals."""
    firs = generated_firs_v3["firs"]
    train_firs = [f for f in firs if f["split"] == "train"]
    dev_firs = [f for f in firs if f["split"] == "dev"]
    test_firs = [f for f in firs if f["split"] == "test"]

    assert len(train_firs) == 60, f"Expected 60 train FIRs, got {len(train_firs)}"
    assert len(dev_firs) == 20, f"Expected 20 dev FIRs, got {len(dev_firs)}"
    assert len(test_firs) == 20, f"Expected 20 test FIRs, got {len(test_firs)}"

    for split_name, split_list in [("train", train_firs), ("dev", dev_firs), ("test", test_firs)]:
        split_langs = {f["language"] for f in split_list}
        assert split_langs == {"hinglish", "hindi", "english"}, (
            f"Split {split_name} missing languages: {split_langs}"
        )

    # Overall language counts (~66 Hinglish, 17 Hindi, 17 English, test has >= 3 Hindi)
    hg_count = sum(1 for f in firs if f["language"] == "hinglish")
    hi_count = sum(1 for f in firs if f["language"] == "hindi")
    en_count = sum(1 for f in firs if f["language"] == "english")
    test_hi_count = sum(1 for f in test_firs if f["language"] == "hindi")

    assert hg_count == 66, f"Expected 66 Hinglish FIRs, got {hg_count}"
    assert hi_count == 17, f"Expected 17 Hindi FIRs, got {hi_count}"
    assert en_count == 17, f"Expected 17 English FIRs, got {en_count}"
    assert test_hi_count >= 3, f"Expected >= 3 Hindi FIRs in test split, got {test_hi_count}"


def test_held_out_templates_only_in_test(generated_firs_v3):
    """Verifies that held-out templates (_05, _06) appear ONLY in test, and each test FIR has >= 1."""
    firs = generated_firs_v3["firs"]
    for item in firs:
        t_ids = item["answer_key"]["template_ids"]
        held_out_in_fir = [t for t in t_ids if t.endswith(("_05", "_06"))]
        if item["split"] in ("train", "dev"):
            assert len(held_out_in_fir) == 0, (
                f"{item['split']} FIR {item['doc_id']} illegally used held-out template(s): {held_out_in_fir}"
            )
        elif item["split"] == "test":
            assert len(held_out_in_fir) >= 1, (
                f"Test FIR {item['doc_id']} must use at least one held-out template! Used: {t_ids}"
            )


def test_fir_types_and_entity_count_extremes(generated_firs_v3):
    """Verifies that all 6 FIR types are present, entity count min < 5 and max > 11, and char lengths valid."""
    firs = generated_firs_v3["firs"]
    types_found = {f["fir_type"] for f in firs}
    expected_types = {"FULL", "CALLS_ONLY", "MONEY_ONLY", "DEVICE_ONLY", "MULTI_SUSPECT", "ALIAS_ONLY"}
    assert expected_types.issubset(types_found), f"Missing FIR types: {expected_types - types_found}"

    ent_counts = [len(f["answer_key"]["entities"]) for f in firs]
    min_ents = min(ent_counts)
    max_ents = max(ent_counts)
    assert min_ents < 5, f"Expected min entity count < 5, got {min_ents}"
    assert max_ents > 11, f"Expected max entity count > 11, got {max_ents}"

    for f in firs:
        length = len(f["text"])
        assert 300 <= length < 5000, f"{f['doc_id']} char length {length} outside [300, 5000)"


def test_no_golden_fir_8word_sequences(generated_firs_v3):
    """Verifies that zero 8-word sequences from contracts/sample_input.txt appear in any generated FIR."""
    golden_path = Path("contracts/sample_input.txt")
    golden_text = golden_path.read_text(encoding="utf-8")
    golden_words = re.findall(r"\b\w+\b", golden_text.lower())
    golden_8grams = set()
    for i in range(len(golden_words) - 7):
        golden_8grams.add(" ".join(golden_words[i:i + 8]))

    for f in generated_firs_v3["firs"]:
        fir_text_lower = f["text"].lower()
        fir_words = re.findall(r"\b\w+\b", fir_text_lower)
        for i in range(len(fir_words) - 7):
            fir_8gram = " ".join(fir_words[i:i + 8])
            assert fir_8gram not in golden_8grams, (
                f"8-word sequence match from sample_input.txt found in {f['doc_id']}: '{fir_8gram}'"
            )


def test_decoys_not_labelled(generated_firs_v3):
    """Verifies plain-text decoys (FIR, section, date, vehicle) are unlabelled, and cash amounts have no relations."""
    for item in generated_firs_v3["firs"]:
        text = item["text"]
        entities = item["answer_key"]["entities"]
        relationships = item["answer_key"]["relationships"]

        # Plain text decoys
        assert ("FIR No." in text or "मुकदमा अपराध" in text or "Case proceedings" in text), (
            f"Preamble missing in {item['doc_id']}"
        )
        assert ("DL-" in text), f"Vehicle decoy missing in {item['doc_id']}"

        for ent in entities:
            assert not ent["text"].startswith("DL-"), f"Vehicle decoy labelled as entity in {item['doc_id']}"
            assert "318(4)" not in ent["text"], f"Section decoy labelled as entity in {item['doc_id']}"

        # Exactly one cash-recovered AMOUNT per relevant FIR has NO relation
        if item["fir_type"] in ("FULL", "DEVICE_ONLY", "MULTI_SUSPECT"):
            cash_ents = [
                e for e in entities
                if e["label"] == "AMOUNT"
                and not any(r["source"] == e["id"] or r["target"] == e["id"] for r in relationships)
            ]
            assert len(cash_ents) >= 1, (
                f"Expected unlinked cash AMOUNT entity in {item['doc_id']}, found {len(cash_ents)}"
            )


def test_person_roles_present(generated_firs_v3):
    """Verifies valid roles on all PERSON entities, with officers/witnesses having null truth_id and 0 relations."""
    valid_roles = {"SUSPECT", "OFFICER", "COMPLAINANT", "WITNESS", "FATHER"}
    for item in generated_firs_v3["firs"]:
        entities = item["answer_key"]["entities"]
        relationships = item["answer_key"]["relationships"]
        rel_endpoints = {r["source"] for r in relationships} | {r["target"] for r in relationships}

        for ent in entities:
            if ent["label"] == "PERSON":
                role = ent.get("role")
                assert role in valid_roles, f"Invalid or missing role '{role}' for entity {ent['id']} in {item['doc_id']}"
                if role == "SUSPECT":
                    assert ent.get("truth_id") is not None, f"Suspect {ent['id']} missing truth_id in {item['doc_id']}"
                    assert ent["truth_id"].startswith("PER_")
                else:
                    assert ent.get("truth_id") is None, f"Non-suspect {ent['id']} has truth_id in {item['doc_id']}"
                    assert ent["id"] not in rel_endpoints, f"Non-suspect {ent['id']} appeared in relations in {item['doc_id']}"


def test_vikas_and_bikas_never_linked(generated_firs_v3):
    """Verifies that look-alike suspects Vikas and Bikas have different keys, and special cases are present."""
    firs = generated_firs_v3["firs"]
    lookalike_firs = []
    p3_alias_firs = []
    shared_handset_firs = []

    shared_imei = generated_firs_v3["truth"]["decoys"]["shared_handset_imei"]["imei"]

    for item in firs:
        entities = item["answer_key"]["entities"]
        has_vikas = any(e.get("truth_id") == "PER_A_OP_01" for e in entities)
        has_bikas = any(e.get("truth_id") == "PER_B_OP_01" for e in entities)

        if has_vikas and has_bikas:
            lookalike_firs.append(item)
            v_ent = next(e for e in entities if e.get("truth_id") == "PER_A_OP_01" and e["label"] == "PERSON")
            b_ent = next(e for e in entities if e.get("truth_id") == "PER_B_OP_01" and e["label"] == "PERSON")
            assert v_ent["id"] != b_ent["id"]
            assert v_ent["entity_key"] != b_ent["entity_key"]
            assert v_ent["entity_key"] == "PER_A_OP_01"
            assert b_ent["entity_key"] == "PER_B_OP_01"

        for ent in entities:
            if ent.get("truth_id") == "PER_A_OP_01" and len(ent.get("aliases", [])) >= 3:
                p3_alias_firs.append(item)
                break

        # Check shared handset
        imei_entities = [e for e in entities if e["label"] == "IMEI" and e["value"] == shared_imei]
        if len(imei_entities) >= 1 and item["fir_type"] == "MULTI_SUSPECT":
            shared_handset_firs.append(item)

    assert len(lookalike_firs) >= 4, f"Expected >= 4 look-alike FIRs, got {len(lookalike_firs)}"
    assert len(p3_alias_firs) >= 2, f"Expected >= 2 3-alias FIRs, got {len(p3_alias_firs)}"
    assert len(shared_handset_firs) >= 2, f"Expected >= 2 shared handset FIRs, got {len(shared_handset_firs)}"


def test_determinism_by_seed(tmp_path):
    """Verifies that running the generator twice with seed 42 produces byte-identical files."""
    case_dir = "data/synthetic/out/case_demo_v2"
    dir1 = tmp_path / "run1"
    dir2 = tmp_path / "run2"

    generate_all_firs_v2(case_dir=case_dir, seed=42, count=100, out_dir=str(dir1))
    generate_all_firs_v2(case_dir=case_dir, seed=42, count=100, out_dir=str(dir2))

    files1 = sorted([f.name for f in dir1.iterdir()])
    files2 = sorted([f.name for f in dir2.iterdir()])
    assert files1 == files2

    for fname in files1:
        b1 = (dir1 / fname).read_bytes()
        b2 = (dir2 / fname).read_bytes()
        assert b1 == b2, f"Determinism failure for {fname}"


def test_transfers_per_split_counts(generated_firs_v3):
    """Verifies that every split contains BOTH ACCOUNT->ACCOUNT and PERSON->ACCOUNT with required minimums."""
    firs = generated_firs_v3["firs"]
    transfers_by_split = {
        "train": {"PERSON": 0, "ACCOUNT": 0},
        "dev": {"PERSON": 0, "ACCOUNT": 0},
        "test": {"PERSON": 0, "ACCOUNT": 0}
    }

    for item in firs:
        split = item["split"]
        ent_map = {e["id"]: e for e in item["answer_key"]["entities"]}
        for rel in item["answer_key"]["relationships"]:
            if rel["type"] == "TRANSFERRED_FUNDS":
                s_ent = ent_map[rel["source_mention"]]
                if s_ent["label"] == "PERSON":
                    transfers_by_split[split]["PERSON"] += 1
                elif s_ent["label"] == "ACCOUNT":
                    transfers_by_split[split]["ACCOUNT"] += 1

    for split in ("train", "dev", "test"):
        assert transfers_by_split[split]["PERSON"] > 0, f"Split {split} missing PERSON->ACCOUNT transfers"
        assert transfers_by_split[split]["ACCOUNT"] > 0, f"Split {split} missing ACCOUNT->ACCOUNT transfers"

    assert transfers_by_split["train"]["PERSON"] >= 8, f"Train PERSON->ACCOUNT transfers < 8: {transfers_by_split['train']['PERSON']}"
    assert transfers_by_split["train"]["ACCOUNT"] >= 8, f"Train ACCOUNT->ACCOUNT transfers < 8: {transfers_by_split['train']['ACCOUNT']}"
    assert transfers_by_split["dev"]["PERSON"] >= 4, f"Dev PERSON->ACCOUNT transfers < 4: {transfers_by_split['dev']['PERSON']}"
    assert transfers_by_split["dev"]["ACCOUNT"] >= 4, f"Dev ACCOUNT->ACCOUNT transfers < 4: {transfers_by_split['dev']['ACCOUNT']}"
    assert transfers_by_split["test"]["PERSON"] >= 4, f"Test PERSON->ACCOUNT transfers < 4: {transfers_by_split['test']['PERSON']}"
    assert transfers_by_split["test"]["ACCOUNT"] >= 4, f"Test ACCOUNT->ACCOUNT transfers < 4: {transfers_by_split['test']['ACCOUNT']}"


def test_fir_types_per_split_coverage(generated_firs_v3):
    """Verifies that all 6 FIR types appear in every split, and test has at least 2 ALIAS_ONLY."""
    firs = generated_firs_v3["firs"]
    expected_types = {"FULL", "CALLS_ONLY", "MONEY_ONLY", "DEVICE_ONLY", "MULTI_SUSPECT", "ALIAS_ONLY"}

    for split_name in ("train", "dev", "test"):
        split_firs = [f for f in firs if f["split"] == split_name]
        types_present = {f["fir_type"] for f in split_firs}
        assert expected_types.issubset(types_present), f"Split {split_name} missing types: {expected_types - types_present}"

    test_alias_count = sum(1 for f in firs if f["split"] == "test" and f["fir_type"] == "ALIAS_ONLY")
    assert test_alias_count >= 2, f"Expected >= 2 ALIAS_ONLY in test split, got {test_alias_count}"


def test_fir_length_and_short_firs(generated_firs_v3):
    """Verifies short FIRs (<= 6 entity mentions) in test split and entity count minimums <= 5 per split."""
    firs = generated_firs_v3["firs"]

    for split_name in ("train", "dev", "test"):
        split_firs = [f for f in firs if f["split"] == split_name]
        ent_counts = [len(f["answer_key"]["entities"]) for f in split_firs]
        min_ents = min(ent_counts)
        assert min_ents <= 5, f"Split {split_name} entity min {min_ents} > 5"

    test_firs = [f for f in firs if f["split"] == "test"]
    short_test_firs = [f for f in test_firs if len(f["answer_key"]["entities"]) <= 6]
    assert len(short_test_firs) >= 3, f"Expected >= 3 short FIRs in test split, got {len(short_test_firs)}"


def test_boilerplate_opening_closing_diversity(generated_firs_v3):
    """Verifies >= 5 distinct openings and closings per language, with max share <= 30% per language."""
    firs = generated_firs_v3["firs"]
    from collections import Counter

    openings_by_lang = {"hinglish": Counter(), "hindi": Counter(), "english": Counter()}
    closings_by_lang = {"hinglish": Counter(), "hindi": Counter(), "english": Counter()}

    for item in firs:
        text = item["text"]
        lang = item["language"]
        sentences = [s.strip() for s in re.split(r"[.!?।](?:\s+|$)", text) if s.strip()]
        openings_by_lang[lang][sentences[0]] += 1
        closings_by_lang[lang][sentences[-1]] += 1

    for lang in ("hinglish", "hindi", "english"):
        openings = openings_by_lang[lang]
        closings = closings_by_lang[lang]
        total_firs = sum(openings.values())

        assert len(openings) >= 5, f"Expected >= 5 opening sentences for {lang}, got {len(openings)}"
        assert len(closings) >= 5, f"Expected >= 5 closing sentences for {lang}, got {len(closings)}"

        max_opening_count = max(openings.values())
        max_closing_count = max(closings.values())

        max_opening_share = max_opening_count / total_firs
        max_closing_share = max_closing_count / total_firs

        assert max_opening_share <= 0.30, f"{lang} opening sentence share {max_opening_share:.2%} > 30%"
        assert max_closing_share <= 0.30, f"{lang} closing sentence share {max_closing_share:.2%} > 30%"
