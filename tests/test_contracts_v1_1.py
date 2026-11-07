"""
Tests for Contracts v1.1 schemas and validation.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from contracts.v1_1.validate import validate_ai_output, validate_graph

BASE_DIR = Path(__file__).resolve().parent.parent
EXAMPLES_DIR = BASE_DIR / "contracts" / "v1_1" / "examples"


@pytest.fixture
def golden_ai():
    with open(EXAMPLES_DIR / "ai_golden_fir45.json", "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def golden_graph():
    with open(EXAMPLES_DIR / "graph_golden_fir45.json", "r", encoding="utf-8") as f:
        return json.load(f)


def test_golden_ai_output_validates(golden_ai):
    """Golden AI output example for FIR 45 validates successfully."""
    validate_ai_output(golden_ai)


def test_golden_graph_validates(golden_graph):
    """Golden Graph render example for FIR 45 validates successfully."""
    validate_graph(golden_graph)


def test_fail_unknown_relation_label(golden_ai, golden_graph):
    """Unknown relation label must fail validation."""
    ai_doc = copy.deepcopy(golden_ai)
    ai_doc["relationships"][0]["relation"] = "ASSOCIATED_WITH_SUSPECT"
    with pytest.raises(ValueError):
        validate_ai_output(ai_doc)

    graph_doc = copy.deepcopy(golden_graph)
    graph_doc["elements"]["edges"][0]["data"]["label"] = "ASSOCIATED_WITH_SUSPECT"
    with pytest.raises(ValueError):
        validate_graph(graph_doc)


def test_fail_unknown_entity_type(golden_ai, golden_graph):
    """Unknown entity type must fail validation."""
    ai_doc = copy.deepcopy(golden_ai)
    ai_doc["entities"][0]["type"] = "ORGANIZATION"
    with pytest.raises(ValueError):
        validate_ai_output(ai_doc)

    graph_doc = copy.deepcopy(golden_graph)
    graph_doc["elements"]["nodes"][0]["data"]["type"] = "ORGANIZATION"
    with pytest.raises(ValueError):
        validate_graph(graph_doc)


def test_fail_missing_ai_confidence(golden_ai):
    """Missing ai_confidence on entity must fail validation."""
    ai_doc = copy.deepcopy(golden_ai)
    del ai_doc["entities"][0]["ai_confidence"]
    with pytest.raises(ValueError):
        validate_ai_output(ai_doc)


def test_fail_confidence_in_place_of_ai_confidence(golden_ai):
    """'confidence' in place of 'ai_confidence' must fail validation."""
    ai_doc = copy.deepcopy(golden_ai)
    del ai_doc["entities"][0]["ai_confidence"]
    ai_doc["entities"][0]["confidence"] = 0.94
    with pytest.raises(ValueError):
        validate_ai_output(ai_doc)


def test_fail_person_without_canonical_name(golden_ai):
    """PERSON entity without canonical_name must fail validation."""
    ai_doc = copy.deepcopy(golden_ai)
    del ai_doc["entities"][0]["canonical_name"]
    with pytest.raises(ValueError):
        validate_ai_output(ai_doc)


def test_fail_non_person_without_value(golden_ai):
    """Non-person entity without value must fail validation."""
    ai_doc = copy.deepcopy(golden_ai)
    del ai_doc["entities"][2]["value"]  # ent_03 PHONE
    with pytest.raises(ValueError):
        validate_ai_output(ai_doc)


def test_fail_missing_relation_endpoint(golden_ai, golden_graph):
    """Relation referencing a non-existent entity/node endpoint must fail validation."""
    ai_doc = copy.deepcopy(golden_ai)
    ai_doc["relationships"][0]["target"] = "ent_999"
    with pytest.raises(ValueError):
        validate_ai_output(ai_doc)

    graph_doc = copy.deepcopy(golden_graph)
    graph_doc["elements"]["edges"][0]["data"]["target"] = "ent_999"
    with pytest.raises(ValueError):
        validate_graph(graph_doc)


def test_fail_wrong_type_pair(golden_ai, golden_graph):
    """Relation between incompatible entity/node types must fail validation."""
    ai_doc = copy.deepcopy(golden_ai)
    # OWNS_DEVICE requires PERSON -> PHONE; swap to PHONE -> PERSON
    ai_doc["relationships"][0]["source"] = "ent_03"
    ai_doc["relationships"][0]["target"] = "ent_01"
    with pytest.raises(ValueError):
        validate_ai_output(ai_doc)

    graph_doc = copy.deepcopy(golden_graph)
    graph_doc["elements"]["edges"][0]["data"]["source"] = "ent_03"
    graph_doc["elements"]["edges"][0]["data"]["target"] = "ent_01"
    with pytest.raises(ValueError):
        validate_graph(graph_doc)


def test_fail_start_gte_end_span(golden_ai):
    """Entity or mention span where start >= end must fail validation."""
    ai_doc1 = copy.deepcopy(golden_ai)
    ai_doc1["entities"][0]["char_span"] = [84, 73]
    ai_doc1["entities"][0]["mentions"][0]["char_span"] = [84, 73]
    with pytest.raises(ValueError):
        validate_ai_output(ai_doc1)

    ai_doc2 = copy.deepcopy(golden_ai)
    ai_doc2["entities"][0]["char_span"] = [73, 73]
    ai_doc2["entities"][0]["mentions"][0]["char_span"] = [73, 73]
    with pytest.raises(ValueError):
        validate_ai_output(ai_doc2)


def test_fail_char_span_different_from_first_mention(golden_ai):
    """Entity char_span differing from first mention char_span must fail validation."""
    ai_doc = copy.deepcopy(golden_ai)
    ai_doc["entities"][0]["char_span"] = [73, 84]
    ai_doc["entities"][0]["mentions"][0]["char_span"] = [73, 85]
    with pytest.raises(ValueError):
        validate_ai_output(ai_doc)


def test_fail_duplicate_ids(golden_ai, golden_graph):
    """Duplicate entity or node IDs must fail validation."""
    ai_doc = copy.deepcopy(golden_ai)
    ai_doc["entities"][1]["id"] = "ent_01"
    with pytest.raises(ValueError):
        validate_ai_output(ai_doc)

    graph_doc = copy.deepcopy(golden_graph)
    graph_doc["elements"]["nodes"][1]["data"]["id"] = "ent_01"
    with pytest.raises(ValueError):
        validate_graph(graph_doc)


def test_fail_negative_amount(golden_ai):
    """Negative amount on relationship must fail validation."""
    ai_doc = copy.deepcopy(golden_ai)
    ai_doc["relationships"][5]["amount"] = -500.0
    with pytest.raises(ValueError):
        validate_ai_output(ai_doc)


def test_fail_ai_confidence_over_one(golden_ai):
    """ai_confidence greater than 1.0 (e.g., 1.5) must fail validation."""
    ai_doc = copy.deepcopy(golden_ai)
    ai_doc["entities"][0]["ai_confidence"] = 1.5
    with pytest.raises(ValueError):
        validate_ai_output(ai_doc)


def test_fail_total_nodes_mismatch(golden_graph):
    """summary.total_nodes mismatch with elements.nodes count must fail validation."""
    graph_doc = copy.deepcopy(golden_graph)
    graph_doc["summary"]["total_nodes"] = 99
    with pytest.raises(ValueError):
        validate_graph(graph_doc)


def test_fail_kingpin_id_not_in_nodes(golden_graph):
    """summary.kingpin_node_id not existing in nodes must fail validation."""
    graph_doc = copy.deepcopy(golden_graph)
    graph_doc["summary"]["kingpin_node_id"] = "ent_nonexistent"
    with pytest.raises(ValueError):
        validate_graph(graph_doc)


def test_fail_sixty_three_char_document_hash(golden_graph):
    """63-character document_hash must fail validation."""
    graph_doc = copy.deepcopy(golden_graph)
    graph_doc["summary"]["document_hash"] = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b85"
    assert len(graph_doc["summary"]["document_hash"]) == 63
    with pytest.raises(ValueError):
        validate_graph(graph_doc)
