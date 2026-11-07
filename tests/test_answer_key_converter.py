"""
Tests for FIR Answer Key to Contract 1 v1.1 converter.
"""

from __future__ import annotations

import glob
import json
from pathlib import Path
import sys
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from contracts.v1_1.validate import validate_ai_output, validate_graph
from data.synthetic.answer_key_to_contract import convert_fir

FIRS_DIR = REPO_ROOT / "data" / "synthetic" / "out" / "firs_v5"
CASE_DIR = REPO_ROOT / "data" / "synthetic" / "out" / "case_demo_v2"
CONTRACT_OUT_DIR = REPO_ROOT / "data" / "synthetic" / "out" / "firs_v5_contract"


@pytest.fixture(scope="session")
def truth_data():
    with open(CASE_DIR / "truth.json", "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="session")
def truth_lookups(truth_data):
    fathers = {
        p["person_id"]: p.get("father_name")
        for p in truth_data.get("people", [])
        if "person_id" in p
    }
    banks = {
        acc["account_number"]: acc.get("bank")
        for acc in truth_data.get("accounts", [])
        if "account_number" in acc and "bank" in acc
    }
    return fathers, banks


def test_all_100_firs_convert_and_validate():
    """All 100 FIR contract files exist and pass validate_ai_output."""
    contract_files = sorted(glob.glob(str(CONTRACT_OUT_DIR / "FIR_*.contract.json")))
    assert len(contract_files) == 100, f"Expected 100 contract files, found {len(contract_files)}"

    links_files = sorted(glob.glob(str(CONTRACT_OUT_DIR / "FIR_*.links.json")))
    assert len(links_files) == 100, f"Expected 100 links files, found {len(links_files)}"

    for cpath in contract_files:
        with open(cpath, "r", encoding="utf-8") as f:
            doc = json.load(f)
        validate_ai_output(doc)


def test_determinism(truth_lookups):
    """Conversion is deterministic: converting twice produces identical results."""
    fathers, banks = truth_lookups
    sample_key_path = FIRS_DIR / "FIR_01.json"
    with open(sample_key_path, "r", encoding="utf-8") as f:
        fir_data = json.load(f)

    c1, l1, s1 = convert_fir(fir_data, fathers, banks)
    c2, l2, s2 = convert_fir(fir_data, fathers, banks)

    assert c1 == c2
    assert l1 == l2
    assert s1 == s2


def test_each_mention_span_equals_text_slice_and_surface():
    """Every mention's char_span must exactly slice the raw FIR text to its surface."""
    contract_files = sorted(glob.glob(str(CONTRACT_OUT_DIR / "FIR_*.contract.json")))
    assert contract_files

    for cpath in contract_files:
        stem = Path(cpath).stem.replace(".contract", "")
        txt_path = FIRS_DIR / f"{stem}.txt"
        with open(txt_path, "r", encoding="utf-8") as f:
            raw_text = f.read()

        with open(cpath, "r", encoding="utf-8") as f:
            doc = json.load(f)

        for ent in doc["entities"]:
            # Entity span must equal first mention span
            assert ent["char_span"] == ent["mentions"][0]["char_span"]
            for m in ent["mentions"]:
                start, end = m["char_span"]
                assert raw_text[start:end] == m["surface"], (
                    f"In {stem}, mention {m} slice '{raw_text[start:end]}' != surface '{m['surface']}'"
                )


def test_every_original_mention_appears_exactly_once():
    """Every original PERSON, ALIAS, FATHER, PHONE, IMEI and ACCOUNT mention appears exactly once."""
    for fir_key_path in sorted(glob.glob(str(FIRS_DIR / "FIR_*.json"))):
        stem = Path(fir_key_path).stem
        contract_path = CONTRACT_OUT_DIR / f"{stem}.contract.json"

        with open(fir_key_path, "r", encoding="utf-8") as f:
            key_data = json.load(f)
        with open(contract_path, "r", encoding="utf-8") as f:
            contract_data = json.load(f)

        orig_mentions: list[tuple[int, int, str]] = []
        for e in key_data.get("entities", []):
            etype = e.get("type")
            erole = e.get("role")
            if etype in {"PERSON", "ALIAS", "PHONE", "IMEI", "ACCOUNT"} or erole == "FATHER":
                orig_mentions.append((e["char_span"][0], e["char_span"][1], e["surface"]))

        contract_mentions: list[tuple[int, int, str]] = []
        for ent in contract_data["entities"]:
            for m in ent["mentions"]:
                contract_mentions.append((m["char_span"][0], m["char_span"][1], m["surface"]))

        assert sorted(orig_mentions) == sorted(contract_mentions), (
            f"Mentions mismatch in {stem}: expected {len(orig_mentions)}, got {len(contract_mentions)}"
        )


def test_relation_count_equals_distinct_relations_in_key():
    """Relationship count in contract output equals distinct relations in answer key."""
    for fir_key_path in sorted(glob.glob(str(FIRS_DIR / "FIR_*.json"))):
        stem = Path(fir_key_path).stem
        contract_path = CONTRACT_OUT_DIR / f"{stem}.contract.json"

        with open(fir_key_path, "r", encoding="utf-8") as f:
            key_data = json.load(f)
        with open(contract_path, "r", encoding="utf-8") as f:
            contract_data = json.load(f)

        seen = set()
        for r in key_data.get("relationships", []):
            sig = (
                r.get("source_key"),
                r.get("target_key"),
                r.get("relation"),
                r.get("amount"),
                tuple(r.get("evidence_char_span") or []),
            )
            seen.add(sig)

        assert len(contract_data["relationships"]) == len(seen), (
            f"Relationship count mismatch in {stem}: expected {len(seen)}, got {len(contract_data['relationships'])}"
        )


def test_each_transfer_amount_equals_key_amount():
    """Each TRANSFERRED_FUNDS relation in contract matches the amount in the answer key."""
    for fir_key_path in sorted(glob.glob(str(FIRS_DIR / "FIR_*.json"))):
        stem = Path(fir_key_path).stem
        contract_path = CONTRACT_OUT_DIR / f"{stem}.contract.json"
        links_path = CONTRACT_OUT_DIR / f"{stem}.links.json"

        with open(fir_key_path, "r", encoding="utf-8") as f:
            key_data = json.load(f)
        with open(contract_path, "r", encoding="utf-8") as f:
            contract_data = json.load(f)
        with open(links_path, "r", encoding="utf-8") as f:
            links_data = json.load(f)

        key_transfers = [
            r for r in key_data.get("relationships", []) if r.get("relation") == "TRANSFERRED_FUNDS"
        ]
        contract_transfers = [
            r for r in contract_data.get("relationships", []) if r.get("relation") == "TRANSFERRED_FUNDS"
        ]

        assert len(key_transfers) == len(contract_transfers)

        for c_rel in contract_transfers:
            src_key = links_data[c_rel["source"]]["entity_key"]
            tgt_key = links_data[c_rel["target"]]["entity_key"]

            matching = [
                k_rel for k_rel in key_transfers
                if k_rel["source_key"] == src_key and k_rel["target_key"] == tgt_key
            ]
            assert matching, f"No matching transfer in key for {src_key} -> {tgt_key}"
            assert float(c_rel["amount"]) == float(matching[0]["amount"])


def test_suspect_father_name_equals_truth_json(truth_data):
    """Each suspect's father_name equals the father_name in truth.json for that person."""
    truth_fathers = {
        p["person_id"]: p.get("father_name")
        for p in truth_data.get("people", [])
        if "person_id" in p
    }

    for cpath in sorted(glob.glob(str(CONTRACT_OUT_DIR / "FIR_*.contract.json"))):
        stem = Path(cpath).stem.replace(".contract", "")
        links_path = CONTRACT_OUT_DIR / f"{stem}.links.json"

        with open(cpath, "r", encoding="utf-8") as f:
            contract_data = json.load(f)
        with open(links_path, "r", encoding="utf-8") as f:
            links_data = json.load(f)

        for ent in contract_data["entities"]:
            if ent.get("role") == "SUSPECT" and ent.get("father_name"):
                tid = links_data[ent["id"]].get("truth_id")
                assert tid in truth_fathers, f"Suspect {ent['id']} truth_id {tid} not in truth.json"
                assert ent["father_name"] == truth_fathers[tid], (
                    f"In {stem}, suspect {ent['id']} father_name '{ent['father_name']}' != truth '{truth_fathers[tid]}'"
                )


def test_no_truth_id_in_contract_files():
    """No truth_id property must exist anywhere in contract JSON files."""
    for cpath in sorted(glob.glob(str(CONTRACT_OUT_DIR / "FIR_*.contract.json"))):
        with open(cpath, "r", encoding="utf-8") as f:
            text = f.read()
        assert "truth_id" not in text, f"Found 'truth_id' in contract file {cpath}"


def test_backend_graph_compatibility():
    """Compatibility test: existing backend graph transform on golden FIR 45 and v1 sample."""
    try:
        from backend.database import GraphService
    except ImportError as e:
        pytest.skip(f"backend.database cannot be imported: {e}")

    service = GraphService()
    service.driver = None  # Do not attempt Neo4j DB persistence

    golden_ai_path = REPO_ROOT / "contracts" / "v1_1" / "examples" / "ai_golden_fir45.json"
    with open(golden_ai_path, "r", encoding="utf-8") as f:
        ai_golden = json.load(f)

    v1_sample_path = REPO_ROOT / "contracts" / "ai_output_schema.json"
    with open(v1_sample_path, "r", encoding="utf-8") as f:
        v1_sample = json.load(f)

    # 1. Transform golden FIR 45
    graph_golden = service.transform_to_render_schema(ai_golden)
    assert "summary" in graph_golden
    assert "elements" in graph_golden

    # Validation against Contract 2 v1.1 fails because v1 backend transform does not set schema_version
    with pytest.raises(ValueError) as excinfo:
        validate_graph(graph_golden)
    assert "schema_version" in str(excinfo.value)

    # Adding schema_version allows full validation
    graph_golden_v1_1 = dict(graph_golden)
    graph_golden_v1_1["summary"] = dict(graph_golden["summary"], schema_version="1.1")
    validate_graph(graph_golden_v1_1)

    # 2. Transform v1 sample
    graph_v1 = service.transform_to_render_schema(v1_sample)
    with pytest.raises(ValueError) as excinfo_v1:
        validate_graph(graph_v1)
    assert "schema_version" in str(excinfo_v1.value)

    graph_v1_v1_1 = dict(graph_v1)
    graph_v1_v1_1["summary"] = dict(graph_v1["summary"], schema_version="1.1")
    validate_graph(graph_v1_v1_1)

