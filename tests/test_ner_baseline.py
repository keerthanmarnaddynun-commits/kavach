"""
Unit tests for Step 5b-1 NER baseline module.
Tests span postprocessing, mode transformations, evaluation harness integration,
and decoded word verification using hand-crafted span lists (no model downloads).
"""
from __future__ import annotations

import pytest

from ai_pipeline.ner_baseline import (
    decoded_word_check,
    evaluate,
    gold_for_mode,
    postprocess,
    preds_for_mode,
)


def test_trims_leading_space():
    """Verify postprocess trims leading and trailing whitespace on original text."""
    text = "He questioned  Vikram  at the station."
    # Original slice: text[13:23] == "  Vikram  "
    raw_spans = [
        {"type": "PERSON", "start": 13, "end": 23, "word": "  Vikram  ", "score": 0.95}
    ]
    processed = postprocess(text, raw_spans)
    assert len(processed) == 1
    sp = processed[0]
    assert sp["start"] == 15
    assert sp["end"] == 21
    assert sp["word"] == "Vikram"
    assert text[sp["start"]:sp["end"]] == "Vikram"


def test_merges_touching_word_pieces():
    """Verify postprocess merges ' B' + 'icky' into one span with right offsets."""
    text = "The suspect  Bicky escaped through the alley."
    # text[11:14] == "  B", text[14:18] == "icky"
    raw_spans = [
        {"type": "PERSON", "start": 11, "end": 14, "word": "  B", "score": 0.90},
        {"type": "PERSON", "start": 14, "end": 18, "word": "icky", "score": 0.94},
    ]
    processed = postprocess(text, raw_spans)
    assert len(processed) == 1
    sp = processed[0]
    assert sp["start"] == 13
    assert sp["end"] == 18
    assert sp["word"] == "Bicky"
    assert text[sp["start"]:sp["end"]] == "Bicky"


def test_does_not_merge_names_separated_by_space():
    """Verify postprocess does not merge two names separated by one space."""
    text = "Rahul Sharma and Amit Verma were seen together."
    raw_spans = [
        {"type": "PERSON", "start": 0, "end": 5, "word": "Rahul", "score": 0.99},
        {"type": "PERSON", "start": 6, "end": 12, "word": "Sharma", "score": 0.98},
    ]
    processed = postprocess(text, raw_spans)
    assert len(processed) == 2
    assert processed[0]["start"] == 0
    assert processed[0]["end"] == 5
    assert processed[0]["word"] == "Rahul"
    assert processed[1]["start"] == 6
    assert processed[1]["end"] == 12
    assert processed[1]["word"] == "Sharma"


def test_drops_all_whitespace_span():
    """Verify postprocess drops a span that contains only whitespace."""
    text = "Notice:      no suspect identified."
    raw_spans = [
        {"type": "PERSON", "start": 7, "end": 13, "word": "      ", "score": 0.40}
    ]
    processed = postprocess(text, raw_spans)
    assert processed == []


def test_output_sorted_and_non_overlapping():
    """Verify output spans are strictly sorted by start position and have no overlaps."""
    text = "Witnesses Amit, Rajesh, and Suresh reported the incident."
    raw_spans = [
        {"type": "PERSON", "start": 28, "end": 34, "word": "Suresh", "score": 0.95},
        {"type": "PERSON", "start": 16, "end": 22, "word": "Rajesh", "score": 0.96},
        {"type": "PERSON", "start": 16, "end": 20, "word": "Raje", "score": 0.88},
        {"type": "PERSON", "start": 10, "end": 14, "word": "Amit", "score": 0.97},
    ]
    processed = postprocess(text, raw_spans)
    assert len(processed) == 3
    assert [p["word"] for p in processed] == ["Amit", "Rajesh", "Suresh"]
    for i in range(len(processed) - 1):
        assert processed[i]["end"] <= processed[i + 1]["start"]


def test_person_only_removes_father_and_alias():
    """Verify PERSON_ONLY mode keeps PERSON gold and removes FATHER and ALIAS."""
    gold_mentions = [
        {"type": "PERSON", "start": 10, "end": 20, "text": "Kishore Kumar"},
        {"type": "ALIAS", "start": 25, "end": 30, "text": "Kalu"},
        {"type": "FATHER", "start": 35, "end": 45, "text": "Ram Prasad"},
        {"type": "PHONE", "start": 50, "end": 60, "text": "9876543210"},
    ]
    res = gold_for_mode(gold_mentions, "PERSON_ONLY")
    assert len(res) == 1
    assert res[0]["type"] == "PERSON"
    assert res[0]["text"] == "Kishore Kumar"


def test_all_names_maps_all_three_to_name():
    """Verify ALL_NAMES mode maps PERSON, ALIAS and FATHER to NAME and deduplicates positions."""
    gold_mentions = [
        {"type": "PERSON", "start": 10, "end": 20, "text": "Kishore Kumar"},
        {"type": "ALIAS", "start": 25, "end": 30, "text": "Kalu"},
        {"type": "FATHER", "start": 35, "end": 45, "text": "Ram Prasad"},
        # Duplicate span with identical start and end
        {"type": "ALIAS", "start": 10, "end": 20, "text": "Kishore Kumar"},
        {"type": "ACCOUNT", "start": 60, "end": 75, "text": "12345678901234"},
    ]
    res = gold_for_mode(gold_mentions, "ALL_NAMES")
    assert len(res) == 3
    assert all(m["type"] == "NAME" for m in res)
    spans = [(m["start"], m["end"]) for m in res]
    assert spans == [(10, 20), (25, 30), (35, 45)]


def test_end_to_end_evaluate_with_fake_predictions():
    """Verify evaluate end-to-end yields hand-computed precision, recall, and F1."""
    gold_by_doc = {
        "doc_01": [
            {"type": "PERSON", "start": 0, "end": 5, "text": "Rahul"},
            {"type": "PERSON", "start": 10, "end": 16, "text": "Suresh"},
            {"type": "FATHER", "start": 25, "end": 35, "text": "Ram Sharma"},
            {"type": "ALIAS", "start": 40, "end": 46, "text": "Chhotu"},
        ]
    }

    # Under PERSON_ONLY: gold has 2 mentions: (0, 5) and (10, 16)
    pred_by_doc_p = {
        "doc_01": [
            {"type": "PERSON", "start": 0, "end": 5, "word": "Rahul"},   # TP
            {"type": "PERSON", "start": 50, "end": 55, "word": "Karan"},  # FP
        ]
    }
    # Expected: TP=1, FP=1, FN=1 -> P=0.5, R=0.5, F1=0.5
    eval_p = evaluate(gold_by_doc, pred_by_doc_p, mode="PERSON_ONLY")
    assert eval_p["micro"]["strict"]["tp"] == 1
    assert eval_p["micro"]["strict"]["fp"] == 1
    assert eval_p["micro"]["strict"]["fn"] == 1
    assert eval_p["precision"] == 0.5
    assert eval_p["recall"] == 0.5
    assert eval_p["f1"] == 0.5

    # Under ALL_NAMES: gold has 4 mentions all mapped to NAME: (0, 5), (10, 16), (25, 35), (40, 46)
    pred_by_doc_a = {
        "doc_01": [
            {"type": "PERSON", "start": 0, "end": 5, "word": "Rahul"},         # TP
            {"type": "PERSON", "start": 25, "end": 35, "word": "Ram Sharma"},  # TP
            {"type": "PERSON", "start": 40, "end": 46, "word": "Chhotu"},      # TP
            {"type": "PERSON", "start": 80, "end": 85, "word": "Extra"},       # FP
        ]
    }
    # Expected: TP=3, FP=1, FN=1 -> P=3/4=0.75, R=3/4=0.75, F1=0.75
    eval_a = evaluate(gold_by_doc, pred_by_doc_a, mode="ALL_NAMES")
    assert eval_a["micro"]["strict"]["tp"] == 3
    assert eval_a["micro"]["strict"]["fp"] == 1
    assert eval_a["micro"]["strict"]["fn"] == 1
    assert eval_a["precision"] == 0.75
    assert eval_a["recall"] == 0.75
    assert eval_a["f1"] == 0.75


def test_decoded_word_check_counts_deliberately_damaged_word():
    """Verify decoded_word_check identifies altered words against original text slices."""
    text = "Vikram Sharma was spotted near the bank."
    raw_spans = [
        {"type": "PERSON", "start": 0, "end": 6, "word": "Vakram"},  # deliberately damaged vowel
        {"type": "PERSON", "start": 7, "end": 13, "word": "Sharma"},  # exact match
    ]
    count, examples = decoded_word_check(text, raw_spans)
    assert count == 1
    assert len(examples) == 1
    assert examples[0]["word"] == "Vakram"
    assert examples[0]["slice"] == "Vikram"
    assert examples[0]["start"] == 0
    assert examples[0]["end"] == 6

