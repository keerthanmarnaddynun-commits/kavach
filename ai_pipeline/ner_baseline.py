"""
Step 5b-1: Named Entity Recognition (NER) baseline module.
Evaluates pre-trained multilingual and Indic NER models against synthetic FIR narratives.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys
import time
from typing import Any

# Ensure Hugging Face operates strictly offline with cached local weights
os.environ["HF_HUB_OFFLINE"] = "1"

from transformers import AutoModelForTokenClassification, AutoTokenizer, pipeline

from ai_pipeline.scoring import (
    Counts,
    load_doc_meta,
    load_gold_mentions,
    prf,
    score_mentions,
)

MODELS = ("Davlan/xlm-roberta-base-ner-hrl", "ai4bharat/IndicNER")

_PIPELINES: dict[str, Any] = {}


def get_pipeline(model_name: str) -> Any:
    """Load and cache token-classification pipeline on CPU using local files only."""
    global _PIPELINES
    if model_name not in _PIPELINES:
        tok = AutoTokenizer.from_pretrained(model_name, local_files_only=True)
        mod = AutoModelForTokenClassification.from_pretrained(model_name, local_files_only=True)
        pipe = pipeline(
            "token-classification",
            model=mod,
            tokenizer=tok,
            aggregation_strategy="simple",
            device=-1,
        )
        _PIPELINES[model_name] = pipe
    return _PIPELINES[model_name]


def run_model(
    model_name: str,
    texts: list[str],
    return_stride_count: bool = False,
) -> list[list[dict[str, Any]]] | tuple[list[list[dict[str, Any]]], int]:
    """
    Run cached token classification pipeline on texts.
    Returns a list (one per text) of raw spans {type, start, end, score, word}.
    Filters entity_group to PER (case-insensitive, including B-PER/I-PER).
    For inputs exceeding model maximum sequence length, uses stride=64.
    """
    pipe = get_pipeline(model_name)
    max_len = pipe.tokenizer.model_max_length

    all_raw_spans: list[list[dict[str, Any]]] = []
    stride_count = 0

    for text in texts:
        tokens = pipe.tokenizer(text, truncation=False, add_special_tokens=True)
        num_tokens = len(tokens["input_ids"])

        if num_tokens > max_len:
            stride_count += 1
            raw_entities = pipe(text, stride=64)
        else:
            raw_entities = pipe(text)

        text_spans: list[dict[str, Any]] = []
        for ent in raw_entities:
            grp = ent.get("entity_group") or ent.get("entity") or ""
            grp_clean = str(grp).strip().upper()
            if grp_clean in ("PER", "B-PER", "I-PER") or grp_clean.endswith("-PER") or grp_clean.endswith("_PER"):
                text_spans.append({
                    "type": "PERSON",
                    "start": int(ent["start"]),
                    "end": int(ent["end"]),
                    "score": float(ent.get("score", 1.0)),
                    "word": str(ent.get("word", "")),
                })
        all_raw_spans.append(text_spans)

    run_model.last_stride_count = stride_count  # type: ignore[attr-defined]

    if return_stride_count:
        return all_raw_spans, stride_count
    return all_raw_spans


def postprocess(text: str, spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Postprocess extracted NER spans:
    (a) trim leading and trailing whitespace of each span by adjusting start/end
        on the ORIGINAL text, drop spans that become empty.
    (b) merge spans whose trimmed boundaries touch exactly (end of one == start of next,
        gap of zero characters). Do NOT merge across a space.
    Result sorted by start, no overlaps.
    """
    if not spans:
        return []

    trimmed_spans: list[dict[str, Any]] = []
    for sp in spans:
        s = int(sp["start"])
        e = int(sp["end"])

        # (a) Trim leading and trailing whitespace on original text
        while s < e and text[s].isspace():
            s += 1
        while e > s and text[e - 1].isspace():
            e -= 1

        if s >= e:
            continue  # Drop spans that become empty

        new_sp = dict(sp)
        new_sp["start"] = s
        new_sp["end"] = e
        new_sp["word"] = text[s:e]
        trimmed_spans.append(new_sp)

    if not trimmed_spans:
        return []

    # Sort by start ascending, then end ascending
    trimmed_spans.sort(key=lambda x: (x["start"], x["end"]))

    merged: list[dict[str, Any]] = []
    curr = dict(trimmed_spans[0])
    curr_scores = [curr.get("score", 1.0)]

    for nxt in trimmed_spans[1:]:
        # (b) Merge spans whose trimmed boundaries touch exactly
        if nxt["start"] == curr["end"]:
            curr["end"] = nxt["end"]
            curr["word"] = text[curr["start"]:curr["end"]]
            if "score" in nxt:
                curr_scores.append(nxt["score"])
            curr["score"] = sum(curr_scores) / len(curr_scores)
        elif nxt["start"] < curr["end"]:
            # Overlapping spans: resolve overlap to maintain no overlaps
            if nxt["end"] > curr["end"]:
                curr["end"] = nxt["end"]
                curr["word"] = text[curr["start"]:curr["end"]]
                if "score" in nxt:
                    curr_scores.append(nxt["score"])
                curr["score"] = sum(curr_scores) / len(curr_scores)
            else:
                if "score" in nxt:
                    curr_scores.append(nxt["score"])
        else:
            # Gap > 0 characters: do NOT merge across a space
            merged.append(curr)
            curr = dict(nxt)
            curr_scores = [curr.get("score", 1.0)]

    merged.append(curr)
    return merged


def gold_for_mode(
    gold_mentions: dict[str, list[dict[str, Any]]] | list[dict[str, Any]],
    mode: str,
) -> dict[str, list[dict[str, Any]]] | list[dict[str, Any]]:
    """
    Filter and adapt gold mentions for the specified evaluation mode:
      - "PERSON_ONLY": keeps gold type PERSON only (drops ALIAS and FATHER).
      - "ALL_NAMES": relabels PERSON, ALIAS and FATHER all to "NAME"
        (a span that appears twice with the same positions stays one).
    """
    if mode not in ("PERSON_ONLY", "ALL_NAMES"):
        raise ValueError(f"mode must be 'PERSON_ONLY' or 'ALL_NAMES', got {mode!r}")

    if isinstance(gold_mentions, dict):
        return {
            doc_id: gold_for_mode(m_list, mode)  # type: ignore[return-value]
            for doc_id, m_list in gold_mentions.items()
        }

    out: list[dict[str, Any]] = []
    seen_spans: set[tuple[int, int]] = set()

    for m in gold_mentions:
        m_type = m.get("type")
        s = int(m.get("start", 0))
        e = int(m.get("end", 0))

        if mode == "PERSON_ONLY":
            if m_type == "PERSON":
                out.append(dict(m))
        elif mode == "ALL_NAMES":
            if m_type in ("PERSON", "ALIAS", "FATHER"):
                span_key = (s, e)
                if span_key not in seen_spans:
                    seen_spans.add(span_key)
                    new_m = dict(m)
                    new_m["type"] = "NAME"
                    out.append(new_m)

    return out


def preds_for_mode(
    pred_mentions: dict[str, list[dict[str, Any]]] | list[dict[str, Any]],
    mode: str,
) -> dict[str, list[dict[str, Any]]] | list[dict[str, Any]]:
    """
    Adapt predicted spans for evaluation mode:
      - "PERSON_ONLY": prediction type set to "PERSON"
      - "ALL_NAMES": prediction type set to "NAME"
    Deduplicates spans with identical (start, end).
    """
    if mode not in ("PERSON_ONLY", "ALL_NAMES"):
        raise ValueError(f"mode must be 'PERSON_ONLY' or 'ALL_NAMES', got {mode!r}")

    if isinstance(pred_mentions, dict):
        return {
            doc_id: preds_for_mode(m_list, mode)  # type: ignore[return-value]
            for doc_id, m_list in pred_mentions.items()
        }

    target_type = "PERSON" if mode == "PERSON_ONLY" else "NAME"
    out: list[dict[str, Any]] = []
    seen: set[tuple[int, int]] = set()

    for p in pred_mentions:
        s = int(p.get("start", 0))
        e = int(p.get("end", 0))
        span_key = (s, e)
        if span_key not in seen:
            seen.add(span_key)
            new_p = dict(p)
            new_p["type"] = target_type
            out.append(new_p)

    return out


def _enrich_scores(res: dict[str, Any]) -> None:
    """Recursively compute and assign precision, recall, f1 for strict/lenient Counts."""
    for k, v in list(res.items()):
        if isinstance(v, dict):
            if "strict" in v and "lenient" in v:
                for mode_key in ("strict", "lenient"):
                    counts = v[mode_key]
                    p, r, f = prf(counts)
                    counts["precision"] = p
                    counts["recall"] = r
                    counts["f1"] = f
            else:
                _enrich_scores(v)


def evaluate(
    gold_by_doc: dict[str, list[dict[str, Any]]],
    pred_by_doc: dict[str, list[dict[str, Any]]],
    meta: dict[str, dict[str, str]] | None = None,
    mode: str = "PERSON_ONLY",
    group_by: str | None = None,
) -> dict[str, Any]:
    """
    Evaluate predicted mentions against gold mentions.
    Uses score_mentions and prf from ai_pipeline.scoring.
    """
    g_mode = gold_for_mode(gold_by_doc, mode)
    p_mode = preds_for_mode(pred_by_doc, mode)

    res = score_mentions(g_mode, p_mode, meta=meta, group_by=group_by)
    _enrich_scores(res)

    if group_by is None:
        target_type = "PERSON" if mode == "PERSON_ONLY" else "NAME"
        target_entry = res.get(target_type) or res.get("micro")
        if target_entry and "strict" in target_entry:
            res["precision"] = target_entry["strict"]["precision"]
            res["recall"] = target_entry["strict"]["recall"]
            res["f1"] = target_entry["strict"]["f1"]

    return res


class DecodedWordCheckResult(int):
    """
    Result of decoded_word_check. Behaves as an int count and unpacks as (count, examples).
    """
    examples: list[dict[str, Any]]

    def __new__(cls, count: int, examples: list[dict[str, Any]]):
        obj = super().__new__(cls, count)
        obj.examples = examples
        return obj

    def __iter__(self):
        yield int(self)
        yield self.examples

    def __getitem__(self, idx: int):
        if idx == 0:
            return int(self)
        elif idx == 1:
            return self.examples
        raise IndexError(idx)

    def __len__(self) -> int:
        return 2


def decoded_word_check(
    text: str,
    raw_spans: list[dict[str, Any]],
) -> DecodedWordCheckResult:
    """
    Check whether pipeline decoded words differ from original text slices after stripping spaces.
    Returns number of differing spans and up to 5 examples.
    """
    diff_count = 0
    examples: list[dict[str, Any]] = []

    for sp in raw_spans:
        s = int(sp.get("start", 0))
        e = int(sp.get("end", 0))
        raw_word = str(sp.get("word", ""))
        orig_slice = text[s:e]

        w_clean = raw_word.replace("\u2581", " ").strip()
        s_clean = orig_slice.strip()

        if w_clean != s_clean:
            diff_count += 1
            if len(examples) < 5:
                examples.append({
                    "word": raw_word,
                    "slice": orig_slice,
                    "start": s,
                    "end": e,
                })

    return DecodedWordCheckResult(diff_count, examples)


def run_benchmark() -> None:
    """Run full evaluation on 100 FIRs and print required benchmark tables."""
    repo_root = Path(__file__).resolve().parent.parent
    firs_dir = repo_root / "data" / "synthetic" / "out" / "firs_v5"

    gold = load_gold_mentions(firs_dir)
    meta = load_doc_meta(firs_dir)
    doc_ids = sorted(gold.keys())
    texts = [firs_dir.joinpath(f"{d}.txt").read_text(encoding="utf-8") for d in doc_ids]

    results_table_1: list[dict[str, Any]] = []
    results_table_2: dict[str, Any] = {}
    word_checks: dict[str, dict[str, Any]] = {}
    stride_counts: dict[str, int] = {}
    run_times: dict[str, float] = {}

    for model_name in MODELS:
        print(f"Running inference for {model_name} on {len(texts)} FIRs...", file=sys.stderr)
        t0 = time.time()
        raw_preds, s_count = run_model(model_name, texts, return_stride_count=True)
        t_elapsed = time.time() - t0
        run_times[model_name] = t_elapsed
        stride_counts[model_name] = s_count

        post_preds = [postprocess(t, sp) for t, sp in zip(texts, raw_preds)]

        raw_by_doc = {d: sp for d, sp in zip(doc_ids, raw_preds)}
        post_by_doc = {d: sp for d, sp in zip(doc_ids, post_preds)}

        # Decoded word checks by language
        lang_counts: dict[str, int] = {"hinglish": 0, "hindi": 0, "english": 0}
        lang_examples: dict[str, list[dict[str, Any]]] = {"hinglish": [], "hindi": [], "english": []}

        for d, t, sp_list in zip(doc_ids, texts, raw_preds):
            lang = meta.get(d, {}).get("language", "unknown").lower()
            cnt, exs = decoded_word_check(t, sp_list)
            lang_counts[lang] = lang_counts.get(lang, 0) + cnt
            if len(lang_examples.get(lang, [])) < 5:
                lang_examples[lang].extend(exs[: 5 - len(lang_examples[lang])])

        word_checks[model_name] = {
            "counts": lang_counts,
            "examples": lang_examples,
        }

        # Table 1 evaluations
        for form_name, pred_map in [("RAW", raw_by_doc), ("POSTPROCESSED", post_by_doc)]:
            for mode_name in ["PERSON_ONLY", "ALL_NAMES"]:
                eval_res = evaluate(gold, pred_map, meta=meta, mode=mode_name)
                micro = eval_res["micro"]
                st = micro["strict"]
                lt = micro["lenient"]
                results_table_1.append({
                    "model": model_name,
                    "form": form_name,
                    "mode": mode_name,
                    "strict_p": st["precision"],
                    "strict_r": st["recall"],
                    "strict_f1": st["f1"],
                    "strict_tp": st["tp"],
                    "strict_fp": st["fp"],
                    "strict_fn": st["fn"],
                    "lenient_p": lt["precision"],
                    "lenient_r": lt["recall"],
                    "lenient_f1": lt["f1"],
                    "lenient_tp": lt["tp"],
                    "lenient_fp": lt["fp"],
                    "lenient_fn": lt["fn"],
                })

        # Table 2 evaluations: POSTPROCESSED ALL_NAMES by language and by split
        by_lang = evaluate(gold, post_by_doc, meta=meta, mode="ALL_NAMES", group_by="language")
        by_split = evaluate(gold, post_by_doc, meta=meta, mode="ALL_NAMES", group_by="split")
        results_table_2[model_name] = {
            "by_language": by_lang,
            "by_split": by_split,
        }

    # Print Formatted Output
    print("\n" + "=" * 120)
    print("TABLE 1: NER BASELINE OVERALL PERFORMANCE (MICRO OVER ALL 100 FIRS)")
    print("=" * 120)
    print(f"{'Model':<35} | {'Form':<13} | {'Mode':<11} | {'Strict P':<8} | {'Strict R':<8} | {'Strict F1':<9} | {'Strict TP':<9} | {'Strict FP':<9} | {'Strict FN':<9} | {'Lenient P':<9} | {'Lenient R':<9} | {'Lenient F1':<10} | {'Len TP':<6} | {'Len FP':<6} | {'Len FN':<6}")
    print("-" * 185)
    for r in results_table_1:
        sp = f"{r['strict_p']:.4f}" if r['strict_p'] is not None else "—"
        sr = f"{r['strict_r']:.4f}" if r['strict_r'] is not None else "—"
        sf = f"{r['strict_f1']:.4f}" if r['strict_f1'] is not None else "—"
        lp = f"{r['lenient_p']:.4f}" if r['lenient_p'] is not None else "—"
        lr = f"{r['lenient_r']:.4f}" if r['lenient_r'] is not None else "—"
        lf = f"{r['lenient_f1']:.4f}" if r['lenient_f1'] is not None else "—"
        print(f"{r['model']:<35} | {r['form']:<13} | {r['mode']:<11} | {sp:<8} | {sr:<8} | {sf:<9} | {r['strict_tp']:<9} | {r['strict_fp']:<9} | {r['strict_fn']:<9} | {lp:<9} | {lr:<9} | {lf:<10} | {r['lenient_tp']:<6} | {r['lenient_fp']:<6} | {r['lenient_fn']:<6}")

    print("\n" + "=" * 120)
    print("TABLE 2: POSTPROCESSED ALL_NAMES STRICT & LENIENT F1 BY LANGUAGE AND SPLIT")
    print("=" * 120)
    print(f"{'Model':<35} | {'Group Type':<10} | {'Category':<10} | {'Strict F1':<10} | {'Lenient F1':<10}")
    print("-" * 85)
    for model_name in MODELS:
        t2_data = results_table_2[model_name]
        for lang in ["hinglish", "hindi", "english"]:
            m_lang = t2_data["by_language"].get(lang, {}).get("micro", {})
            st_f1 = m_lang.get("strict", {}).get("f1")
            lt_f1 = m_lang.get("lenient", {}).get("f1")
            st_str = f"{st_f1:.4f}" if st_f1 is not None else "—"
            lt_str = f"{lt_f1:.4f}" if lt_f1 is not None else "—"
            print(f"{model_name:<35} | Language   | {lang:<10} | {st_str:<10} | {lt_str:<10}")
        for split in ["train", "dev", "test"]:
            m_split = t2_data["by_split"].get(split, {}).get("micro", {})
            st_f1 = m_split.get("strict", {}).get("f1")
            lt_f1 = m_split.get("lenient", {}).get("f1")
            st_str = f"{st_f1:.4f}" if st_f1 is not None else "—"
            lt_str = f"{lt_f1:.4f}" if lt_f1 is not None else "—"
            print(f"{model_name:<35} | Split      | {split:<10} | {st_str:<10} | {lt_str:<10}")

    print("\n" + "=" * 120)
    print("TABLE 3: DECODED WORD CHECK COUNTS AND EXAMPLES")
    print("=" * 120)
    for model_name in MODELS:
        print(f"\nModel: {model_name}")
        c_dict = word_checks[model_name]["counts"]
        ex_dict = word_checks[model_name]["examples"]
        for lang in ["hinglish", "hindi", "english"]:
            print(f"  Language: {lang} -> Mismatch Count: {c_dict.get(lang, 0)}")
            exs = ex_dict.get(lang, [])
            if exs:
                for i, ex in enumerate(exs, 1):
                    print(f"    Ex {i}: word={ex['word']!r} vs slice={ex['slice']!r} (offsets {ex['start']}:{ex['end']})")
            else:
                print("    (no mismatches)")

    print("\n" + "=" * 120)
    print("TABLE 4: STRIDE USAGE AND RUNTIME SUMMARY")
    print("=" * 120)
    for model_name in MODELS:
        print(f"Model: {model_name:<35} | Texts needing stride: {stride_counts[model_name]:<3} | Runtime: {run_times[model_name]:.2f}s")


if __name__ == "__main__":
    run_benchmark()

