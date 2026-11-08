"""
Tests for scoring library (Step 5a-1).
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai_pipeline.scoring import (
    Counts,
    load_doc_meta,
    load_gold_mentions,
    prf,
    score_mentions,
    score_relations,
)

FIRS_DIR = REPO_ROOT / "data" / "synthetic" / "out" / "firs_v5"
CONTRACT_DIR = REPO_ROOT / "data" / "synthetic" / "out" / "firs_v5_contract"


# ---------------------------------------------------------------------------
# 1. PRF and Mention Scoring Unit Tests
# ---------------------------------------------------------------------------

def test_perfect_predictions_give_one():
    """Perfect predictions give 1.0 everywhere (precision, recall, f1)."""
    gold = {"doc_1": [{"type": "PHONE", "start": 0, "end": 10, "text": "9876543210"}]}
    pred = {"doc_1": [{"type": "PHONE", "start": 0, "end": 10, "text": "9876543210"}]}
    res = score_mentions(gold, pred)

    p_s, r_s, f1_s = prf(res["PHONE"]["strict"])
    assert p_s == 1.0
    assert r_s == 1.0
    assert f1_s == 1.0

    p_l, r_l, f1_l = prf(res["PHONE"]["lenient"])
    assert p_l == 1.0
    assert r_l == 1.0
    assert f1_l == 1.0

    # Micro totals also 1.0
    p_m, r_m, f1_m = prf(res["micro"]["strict"])
    assert p_m == 1.0
    assert r_m == 1.0
    assert f1_m == 1.0


def test_empty_predictions_give_recall_zero_and_precision_none():
    """Empty predictions give recall 0 and precision None."""
    gold = {"doc_1": [{"type": "PHONE", "start": 0, "end": 10, "text": "9876543210"}]}
    pred = {"doc_1": []}
    res = score_mentions(gold, pred)

    p_s, r_s, f1_s = prf(res["PHONE"]["strict"])
    assert r_s == 0.0
    assert p_s is None
    assert f1_s is None

    p_l, r_l, f1_l = prf(res["PHONE"]["lenient"])
    assert r_l == 0.0
    assert p_l is None
    assert f1_l is None


def test_span_shifted_by_one_character_strict_miss_lenient_hit():
    """A span shifted by one character is a strict miss but a lenient hit."""
    gold = {"doc_1": [{"type": "PHONE", "start": 10, "end": 20, "text": "9876543210"}]}
    pred = {"doc_1": [{"type": "PHONE", "start": 11, "end": 20, "text": "876543210"}]}
    res = score_mentions(gold, pred)

    # Strict: 0 TP, 1 FP, 1 FN
    strict = res["PHONE"]["strict"]
    assert strict.tp == 0
    assert strict.fp == 1
    assert strict.fn == 1
    p_s, r_s, f1_s = prf(strict)
    assert p_s == 0.0
    assert r_s == 0.0
    assert f1_s == 0.0

    # Lenient: 1 TP, 0 FP, 0 FN
    lenient = res["PHONE"]["lenient"]
    assert lenient.tp == 1
    assert lenient.fp == 0
    assert lenient.fn == 0
    p_l, r_l, f1_l = prf(lenient)
    assert p_l == 1.0
    assert r_l == 1.0
    assert f1_l == 1.0


def test_wrong_type_is_fp_and_fn():
    """Wrong type is both an FP and an FN."""
    gold = {"doc_1": [{"type": "PHONE", "start": 0, "end": 10, "text": "9876543210"}]}
    pred = {"doc_1": [{"type": "ACCOUNT", "start": 0, "end": 10, "text": "9876543210"}]}
    res = score_mentions(gold, pred)

    phone_cnt = res["PHONE"]["strict"]
    assert phone_cnt.tp == 0
    assert phone_cnt.fp == 0
    assert phone_cnt.fn == 1

    acct_cnt = res["ACCOUNT"]["strict"]
    assert acct_cnt.tp == 0
    assert acct_cnt.fp == 1
    assert acct_cnt.fn == 0

    micro_cnt = res["micro"]["strict"]
    assert micro_cnt.tp == 0
    assert micro_cnt.fp == 1
    assert micro_cnt.fn == 1


def test_duplicate_prediction_is_one_tp_plus_one_fp():
    """Duplicate prediction is one TP plus one FP."""
    gold = {"doc_1": [{"type": "PHONE", "start": 0, "end": 10, "text": "9876543210"}]}
    pred = {
        "doc_1": [
            {"type": "PHONE", "start": 0, "end": 10, "text": "9876543210"},
            {"type": "PHONE", "start": 0, "end": 10, "text": "9876543210"},
        ]
    }
    res = score_mentions(gold, pred)

    strict = res["PHONE"]["strict"]
    assert strict.tp == 1
    assert strict.fp == 1
    assert strict.fn == 0

    lenient = res["PHONE"]["lenient"]
    assert lenient.tp == 1
    assert lenient.fp == 1
    assert lenient.fn == 0


def test_three_gold_two_correct_one_extra_precision_and_recall_two_thirds():
    """A 3-gold 2-correct 1-extra example gives exact precision 2/3 and recall 2/3."""
    gold = {
        "doc_1": [
            {"type": "PHONE", "start": 0, "end": 10, "text": "9876543210"},
            {"type": "PHONE", "start": 20, "end": 30, "text": "9876543211"},
            {"type": "PHONE", "start": 40, "end": 50, "text": "9876543212"},
        ]
    }
    pred = {
        "doc_1": [
            {"type": "PHONE", "start": 0, "end": 10, "text": "9876543210"},
            {"type": "PHONE", "start": 20, "end": 30, "text": "9876543211"},
            {"type": "PHONE", "start": 60, "end": 70, "text": "9876543213"},
        ]
    }
    res = score_mentions(gold, pred)

    strict = res["PHONE"]["strict"]
    assert strict.tp == 2
    assert strict.fp == 1
    assert strict.fn == 1

    p, r, f1 = prf(strict)
    assert p == 2 / 3
    assert r == 2 / 3
    assert f1 == 2 / 3


def test_group_by_split_and_language_add_up_to_overall():
    """group_by split and language add up to the overall totals."""
    gold = load_gold_mentions(FIRS_DIR)
    meta = load_doc_meta(FIRS_DIR)

    # Pred: duplicate gold but mutate doc FIR_01 and FIR_02
    pred = {doc_id: [dict(m) for m in mentions] for doc_id, mentions in gold.items()}
    pred["FIR_01"].pop(0)  # drop 1 -> +1 FN
    pred["FIR_02"].append({"type": "PHONE", "start": 9999, "end": 10009, "text": "9876543210"})  # extra -> +1 FP

    overall = score_mentions(gold, pred)
    by_split = score_mentions(gold, pred, meta=meta, group_by="split")
    by_lang = score_mentions(gold, pred, meta=meta, group_by="language")

    for mode in ["strict", "lenient"]:
        for metric in ["tp", "fp", "fn"]:
            sum_split = sum(by_split[s]["micro"][mode][metric] for s in by_split)
            sum_lang = sum(by_lang[l]["micro"][mode][metric] for l in by_lang)
            expected = overall["micro"][mode][metric]
            assert sum_split == expected, f"Split sum {sum_split} != overall {expected} for {mode}.{metric}"
            assert sum_lang == expected, f"Lang sum {sum_lang} != overall {expected} for {mode}.{metric}"


# ---------------------------------------------------------------------------
# 2. Relation Scoring Unit Tests
# ---------------------------------------------------------------------------

def test_relations_gold_used_as_predictions_gives_one():
    """Relations: gold used as predictions gives 1.0 everywhere."""
    res = score_relations(CONTRACT_DIR, CONTRACT_DIR)

    # Relations micro
    p_r, r_r, f1_r = prf(res["relations"]["micro"])
    assert p_r == 1.0
    assert r_r == 1.0
    assert f1_r == 1.0
    assert res["relations"]["micro"].tp == 312
    assert res["relations"]["micro"].fp == 0
    assert res["relations"]["micro"].fn == 0

    # Entities micro
    p_e, r_e, f1_e = prf(res["entities"]["micro"])
    assert p_e == 1.0
    assert r_e == 1.0
    assert f1_e == 1.0
    assert res["entities"]["micro"].tp == 550
    assert res["entities"]["micro"].fp == 0
    assert res["entities"]["micro"].fn == 0

    # Per label 1.0
    for lbl, cnt in res["relations"]["by_label"].items():
        p, r, f = prf(cnt)
        assert p == 1.0
        assert r == 1.0
        assert f == 1.0


def test_relations_dropping_one_relation_lowers_recall():
    """Dropping one relation lowers recall."""
    gold_contracts = load_contract_dict_helper(CONTRACT_DIR)
    pred_contracts = copy.deepcopy(gold_contracts)

    # Drop the first relation from the first doc that has one
    dropped_label = None
    for d in pred_contracts.values():
        if d.get("relationships"):
            dropped = d["relationships"].pop(0)
            dropped_label = dropped.get("relation") or dropped.get("type")
            break
    assert dropped_label is not None

    res = score_relations(gold_contracts, pred_contracts)
    micro = res["relations"]["micro"]
    assert micro.fp == 0
    assert micro.fn == 1
    p, r, f1 = prf(micro)
    assert p == 1.0
    assert r == (312 - 1) / 312
    assert r < 1.0


def test_relations_wrong_label_gives_fp_and_fn():
    """Wrong label gives FP and FN."""
    gold_contracts = load_contract_dict_helper(CONTRACT_DIR)
    single_gold = {"FIR_01": gold_contracts["FIR_01"]}
    single_pred = copy.deepcopy(single_gold)

    orig_label = single_pred["FIR_01"]["relationships"][0]["relation"]
    tampered_label = "CONTROLS_ACCOUNT" if orig_label != "CONTROLS_ACCOUNT" else "OWNS_DEVICE"
    single_pred["FIR_01"]["relationships"][0]["relation"] = tampered_label

    res = score_relations(single_gold, single_pred)
    assert res["relations"]["micro"].fp >= 1
    assert res["relations"]["micro"].fn >= 1
    assert res["relations"]["by_label"][tampered_label].fp >= 1
    assert res["relations"]["by_label"][orig_label].fn >= 1


def test_relations_swapped_source_and_target_is_wrong():
    """Swapped source and target is wrong."""
    gold_contracts = load_contract_dict_helper(CONTRACT_DIR)
    single_gold = {"FIR_01": gold_contracts["FIR_01"]}
    single_pred = copy.deepcopy(single_gold)

    r0 = single_pred["FIR_01"]["relationships"][0]
    r0["source"], r0["target"] = r0["target"], r0["source"]

    res = score_relations(single_gold, single_pred)
    assert res["relations"]["micro"].fp >= 1
    assert res["relations"]["micro"].fn >= 1


def test_relations_wrong_amount_is_wrong():
    """Wrong amount on TRANSFERRED_FUNDS is wrong."""
    gold_contracts = load_contract_dict_helper(CONTRACT_DIR)
    target_doc = None
    for did, d in gold_contracts.items():
        for r in d.get("relationships", []):
            if r.get("relation") == "TRANSFERRED_FUNDS" and r.get("amount") is not None:
                target_doc = did
                break
        if target_doc:
            break
    assert target_doc is not None

    single_gold = {target_doc: gold_contracts[target_doc]}
    single_pred = copy.deepcopy(single_gold)
    for r in single_pred[target_doc]["relationships"]:
        if r.get("relation") == "TRANSFERRED_FUNDS" and r.get("amount") is not None:
            r["amount"] = float(r["amount"]) + 50.0

    res = score_relations(single_gold, single_pred)
    tf_counts = res["relations"]["by_label"]["TRANSFERRED_FUNDS"]
    assert tf_counts.fp >= 1
    assert tf_counts.fn >= 1


def test_entity_alignment_one_to_one():
    """Entity alignment is strictly one-to-one."""
    gold_doc = {
        "source_doc_id": "doc_align",
        "entities": [
            {
                "id": "g1",
                "type": "PERSON",
                "mentions": [{"char_span": [0, 10], "surface": "John Doe", "kind": "NAME"}],
            }
        ],
        "relationships": [],
    }
    pred_doc = {
        "source_doc_id": "doc_align",
        "entities": [
            {
                "id": "p1",
                "type": "PERSON",
                "mentions": [{"char_span": [0, 10], "surface": "John Doe", "kind": "NAME"}],
            },
            {
                "id": "p2",
                "type": "PERSON",
                "mentions": [{"char_span": [0, 10], "surface": "John Doe", "kind": "NAME"}],
            },
        ],
        "relationships": [],
    }

    res = score_relations({"doc_align": gold_doc}, {"doc_align": pred_doc})
    person_cnt = res["entities"]["by_type"]["PERSON"]
    # Exactly one matches TP, the other duplicate is FP
    assert person_cnt.tp == 1
    assert person_cnt.fp == 1
    assert person_cnt.fn == 0


def test_load_gold_mentions_total_and_counts():
    """load_gold_mentions on firs_v5 returns 1235 mentions in total minus nothing silently dropped."""
    gold = load_gold_mentions(FIRS_DIR)
    assert len(gold) == 100

    total_mentions = sum(len(m_list) for m_list in gold.values())
    assert total_mentions == 1235

    type_counts = {}
    for m_list in gold.values():
        for m in m_list:
            t = m["type"]
            type_counts[t] = type_counts.get(t, 0) + 1

    expected_counts = {
        "PERSON": 383,
        "ALIAS": 155,
        "FATHER": 127,
        "AMOUNT": 107,
        "ACCOUNT": 134,
        "PHONE": 255,
        "IMEI": 74,
    }
    assert type_counts == expected_counts
    assert sum(expected_counts.values()) == 1235


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def load_contract_dict_helper(dir_path: Path) -> dict[str, dict]:
    """Helper to load all contract json files into memory."""
    import json
    res = {}
    for f in sorted(dir_path.glob("*.contract.json")):
        with open(f, "r", encoding="utf-8") as fp:
            d = json.load(fp)
        res[d["source_doc_id"]] = d
    return res

