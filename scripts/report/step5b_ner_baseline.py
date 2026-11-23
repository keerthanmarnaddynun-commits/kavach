"""
Step 5b-2: Off-the-shelf NER baseline reporting script.
Evaluates Davlan/xlm-roberta-base-ner-hrl and ai4bharat/IndicNER against synthetic FIR narratives.
Documents evaluation results in docs/RESULTS.md under <!-- STEP5B:BEGIN --> ... <!-- STEP5B:END -->.
"""

from __future__ import annotations

import argparse
import ast
import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import stat
import subprocess
import sys
import time
from typing import Any

# Ensure Hugging Face operates strictly offline
os.environ["HF_HUB_OFFLINE"] = "1"

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import torch
import transformers

from scripts.check_results_docs import ALL_BANNED

from ai_pipeline.ner_baseline import (
    MODELS,
    decoded_word_check,
    evaluate,
    get_pipeline,
    load_doc_meta,
    load_gold_mentions,
    postprocess,
    run_model,
)

MODEL_SLUGS = {
    "Davlan/xlm-roberta-base-ner-hrl": "davlan_xlm_roberta_base_ner_hrl",
    "ai4bharat/IndicNER": "ai4bharat_indicner",
}


def compute_sha256(filepath: Path) -> str:
    """Compute standard SHA-256 hex digest for a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def compute_combined_sha256(files: list[Path]) -> str:
    """Compute combined SHA-256 over a sorted list of name:sha256 lines."""
    lines = []
    for fp in sorted(files, key=lambda p: p.name):
        file_hash = compute_sha256(fp)
        lines.append(f"{fp.name}:{file_hash}\n")
    combined_str = "".join(lines)
    return hashlib.sha256(combined_str.encode("utf-8")).hexdigest()


def extract_test_docstrings(test_filepath: Path) -> dict[str, str]:
    """Parse test function docstrings from python test file."""
    docstrings: dict[str, str] = {}
    with open(test_filepath, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read())
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
            doc = ast.get_docstring(node) or node.name
            docstrings[node.name] = doc.strip().split("\n")[0]
    return docstrings


def parse_pytest_results(pytest_output: str, docstrings: dict[str, str]) -> list[dict[str, str]]:
    """Parse test names and outcomes from raw pytest output."""
    results = []
    pattern = re.compile(r"::(test_\w+)(\[[^\]]*\])?\s+(PASSED|FAILED|SKIPPED|ERROR)")
    for match in pattern.finditer(pytest_output):
        func_name = match.group(1)
        param = match.group(2) or ""
        outcome = match.group(3)

        full_test_name = f"{func_name}{param}"
        base_desc = docstrings.get(func_name, func_name)
        if param:
            desc = f"{base_desc} {param}"
        else:
            desc = base_desc

        results.append({
            "test_name": full_test_name,
            "description": desc,
            "outcome": outcome,
        })
    return results


def get_metric_by_path(metrics: dict[str, Any], path: str) -> tuple[str, Any]:
    """
    Walk metrics dict step by step using dot notation.
    Returns (path, value).
    Aborts with ValueError naming the path if any step does not exist.
    """
    parts = path.split(".")
    curr = metrics
    for step in parts:
        if isinstance(curr, dict) and step in curr:
            curr = curr[step]
        else:
            raise ValueError(f"Metric path step {step!r} not found in path {path!r}")
    return path, curr


def format_key_number_line(metrics: dict[str, Any], path: str, label: str) -> str:
    """Format single Key Numbers line using get_metric_by_path."""
    metric_path, val = get_metric_by_path(metrics, path)
    if isinstance(val, float):
        val_str = f"{val:.4f}"
    else:
        val_str = str(val)
    return f"- `metrics.json` (`{metric_path}`): {val_str} {label}"


def assert_tables_match_metrics(section_md: str, metrics: dict[str, Any]) -> None:
    """
    Assert for every table value in Tables A to G that it equals the corresponding
    metrics.json value (rounded to four decimals or exact int); abort on any mismatch.
    """
    def extract_table_rows(table_header_keyword: str) -> list[list[str]]:
        lines = section_md.splitlines()
        table_lines = []
        found = False
        for line in lines:
            if table_header_keyword in line:
                found = True
                continue
            if found:
                if line.strip().startswith("|"):
                    table_lines.append(line.strip())
                elif table_lines:
                    break
        if len(table_lines) < 3:
            raise ValueError(f"Table {table_header_keyword!r} not found or has fewer than 3 lines.")
        rows = []
        for line in table_lines[2:]:  # Skip header and separator rows
            cells = [c.strip() for c in line.split("|")[1:-1]]
            rows.append(cells)
        return rows

    # Assert Table A: Overall Performance by Extractor and Type
    rows_a = extract_table_rows("Table A:")
    for row in rows_a:
        model, form, mode, sp, sr, sf1, stp, sfp, sfn, lp, lr, lf1, ltp, lfp, lfn = row
        slug = MODEL_SLUGS[model]
        m_entry = metrics["models"][slug]["overall"][form][mode]
        st = m_entry["strict"]
        lt = m_entry["lenient"]

        assert float(sp) == round(st["precision"], 4), f"Table A strict P mismatch for {model} {form} {mode}"
        assert float(sr) == round(st["recall"], 4), f"Table A strict R mismatch for {model} {form} {mode}"
        assert float(sf1) == round(st["f1"], 4), f"Table A strict F1 mismatch for {model} {form} {mode}"
        assert int(stp) == st["tp"], f"Table A strict TP mismatch for {model} {form} {mode}"
        assert int(sfp) == st["fp"], f"Table A strict FP mismatch for {model} {form} {mode}"
        assert int(sfn) == st["fn"], f"Table A strict FN mismatch for {model} {form} {mode}"

        assert float(lp) == round(lt["precision"], 4), f"Table A lenient P mismatch for {model} {form} {mode}"
        assert float(lr) == round(lt["recall"], 4), f"Table A lenient R mismatch for {model} {form} {mode}"
        assert float(lf1) == round(lt["f1"], 4), f"Table A lenient F1 mismatch for {model} {form} {mode}"
        assert int(ltp) == lt["tp"], f"Table A lenient TP mismatch for {model} {form} {mode}"
        assert int(lfp) == lt["fp"], f"Table A lenient FP mismatch for {model} {form} {mode}"
        assert int(lfn) == lt["fn"], f"Table A lenient FN mismatch for {model} {form} {mode}"

    # Assert Table B: Strict and Lenient F1 by Language and Split
    rows_b = extract_table_rows("Table B:")
    for row in rows_b:
        model, group_type, cat, sf1, lf1 = row
        slug = MODEL_SLUGS[model]
        sub = "by_language" if group_type == "Language" else "by_split"
        b_entry = metrics["models"][slug]["postprocessed_all_names"][sub][cat]
        assert float(sf1) == round(b_entry["strict"]["f1"], 4), f"Table B strict F1 mismatch for {model} {cat}"
        assert float(lf1) == round(b_entry["lenient"]["f1"], 4), f"Table B lenient F1 mismatch for {model} {cat}"

    # Assert Table C: Decoded Word Check
    rows_c = extract_table_rows("Table C:")
    for row in rows_c:
        model, lang, total_spans, mismatches, _ = row
        slug = MODEL_SLUGS[model]
        c_entry = metrics["models"][slug]["decoded_word_check"]["by_language"][lang]
        assert int(total_spans) == c_entry["total_spans"], f"Table C total spans mismatch for {model} {lang}"
        assert int(mismatches) == c_entry["mismatches"], f"Table C mismatches mismatch for {model} {lang}"

    # Assert Table D: Misses by Gold Type
    rows_d = extract_table_rows("Table D:")
    for row in rows_d:
        model, g_type, tot, s_hit, l_only, missed, s_plus_l, l_tp = row
        slug = MODEL_SLUGS[model]
        d_entry = metrics["models"][slug]["gold_classification"][g_type]
        assert int(tot) == d_entry["total"], f"Table D total mismatch for {model} {g_type}"
        assert int(s_hit) == d_entry["strict_hit"], f"Table D strict hit mismatch for {model} {g_type}"
        assert int(l_only) == d_entry["lenient_only"], f"Table D lenient only mismatch for {model} {g_type}"
        assert int(missed) == d_entry["missed"], f"Table D missed mismatch for {model} {g_type}"
        assert int(s_plus_l) == d_entry["strict_plus_lenient"], f"Table D strict+lenient mismatch for {model} {g_type}"
        if g_type == "TOTAL":
            assert int(l_tp) == d_entry["lenient_tp"], f"Table D lenient TP mismatch for {model}"
        else:
            assert l_tp == "—", f"Table D lenient TP placeholder mismatch for {model} {g_type}"

    # Assert Table F: Stride and Runtime
    rows_f = extract_table_rows("Table F:")
    for row in rows_f:
        model, texts_eval, texts_stride, max_len, stride_param, rt = row
        slug = MODEL_SLUGS[model]
        f_entry = metrics["stride_and_runtime"][slug]
        assert int(texts_eval) == metrics["dataset_counts"]["total_firs"]
        assert int(texts_stride) == f_entry["texts_needing_stride"]
        assert int(max_len) == f_entry["max_length"]
        assert int(stride_param) == f_entry["stride_value"]
        assert float(rt) == round(f_entry["runtime_seconds"], 2)


def validate_markdown_tables_and_rules(content: str) -> None:
    """Assert table column counts match, check forbidden words, and enforce prose rules."""
    for w in ALL_BANNED:
        if re.search(rf"\b{re.escape(w)}\b", content, re.IGNORECASE):
            raise ValueError(f"Forbidden word {w!r} found in generated markdown.")

    # Validate table column counts
    table_lines: list[str] = []
    in_table = False
    for line in content.splitlines():
        trimmed = line.strip()
        if trimmed.startswith("|") and trimmed.endswith("|"):
            in_table = True
            table_lines.append(trimmed)
        else:
            if in_table:
                col_counts = [len([c for c in tl.split("|")[1:-1]]) for tl in table_lines]
                if len(set(col_counts)) > 1:
                    raise ValueError(f"Table column count mismatch: observed counts {set(col_counts)} in table:\n" + "\n".join(table_lines))
                table_lines = []
                in_table = False

    if in_table and table_lines:
        col_counts = [len([c for c in tl.split("|")[1:-1]]) for tl in table_lines]
        if len(set(col_counts)) > 1:
            raise ValueError(f"Table column count mismatch: observed counts {set(col_counts)} in table:\n" + "\n".join(table_lines))

    # Validate bullet indentation
    for line in content.splitlines():
        if line.strip().startswith("-"):
            if not re.match(r"^(?:  )*-\s", line):
                raise ValueError(f"Bullet indentation error (must be '- ' with optional two-space indentation): {line!r}")


def build_markdown_section(
    run_id: str,
    metrics: dict[str, Any],
    output_hashes: dict[str, str],
    pytest_tests: list[dict[str, str]],
    pytest_cmd: str,
) -> str:
    """Build the complete Markdown section for Step 5b."""
    hashes = metrics["input_hashes"]

    # Table A: Overall Performance
    table_a_rows = []
    for model_name in MODELS:
        slug = MODEL_SLUGS[model_name]
        m_overall = metrics["models"][slug]["overall"]
        for form_name in ["RAW", "POSTPROCESSED"]:
            for mode_name in ["PERSON_ONLY", "ALL_NAMES"]:
                st = m_overall[form_name][mode_name]["strict"]
                lt = m_overall[form_name][mode_name]["lenient"]
                sp, sr, sf1 = st["precision"], st["recall"], st["f1"]
                lp, lr, lf1 = lt["precision"], lt["recall"], lt["f1"]
                table_a_rows.append(
                    f"| {model_name} | {form_name} | {mode_name} | {sp:.4f} | {sr:.4f} | {sf1:.4f} | {st['tp']} | {st['fp']} | {st['fn']} | {lp:.4f} | {lr:.4f} | {lf1:.4f} | {lt['tp']} | {lt['fp']} | {lt['fn']} |"
                )
    table_a_body = "\n".join(table_a_rows)

    # Table B: Language and Split Performance
    table_b_rows = []
    for model_name in MODELS:
        slug = MODEL_SLUGS[model_name]
        b_data = metrics["models"][slug]["postprocessed_all_names"]
        for lang in ["hinglish", "hindi", "english"]:
            st_f1 = b_data["by_language"][lang]["strict"]["f1"]
            lt_f1 = b_data["by_language"][lang]["lenient"]["f1"]
            table_b_rows.append(f"| {model_name} | Language | {lang} | {st_f1:.4f} | {lt_f1:.4f} |")
        for split in ["train", "dev", "test"]:
            st_f1 = b_data["by_split"][split]["strict"]["f1"]
            lt_f1 = b_data["by_split"][split]["lenient"]["f1"]
            table_b_rows.append(f"| {model_name} | Split | {split} | {st_f1:.4f} | {lt_f1:.4f} |")
    table_b_body = "\n".join(table_b_rows)

    # Table C: Decoded Word Check
    table_c_rows = []
    for model_name in MODELS:
        slug = MODEL_SLUGS[model_name]
        dw = metrics["models"][slug]["decoded_word_check"]["by_language"]
        for lang in ["hinglish", "hindi", "english"]:
            tot = dw[lang]["total_spans"]
            mismatches = dw[lang]["mismatches"]
            exs = dw[lang]["examples"]
            if exs:
                ex_strs = []
                for ex in exs[:2]:
                    w_disp = ex['word'].replace('|', '/')
                    s_disp = ex['slice'].replace('|', '/')
                    ex_strs.append(f"`{w_disp}` vs `{s_disp}` ({ex['start']}:{ex['end']})")
                ex_cell = "; ".join(ex_strs)
            else:
                ex_cell = "None"
            table_c_rows.append(f"| {model_name} | {lang} | {tot} | {mismatches} | {ex_cell} |")
    table_c_body = "\n".join(table_c_rows)

    # Table D: Misses by Gold Type
    table_d_rows = []
    for model_name in MODELS:
        slug = MODEL_SLUGS[model_name]
        gc = metrics["models"][slug]["gold_classification"]
        for t in ["PERSON", "ALIAS", "FATHER"]:
            d = gc[t]
            table_d_rows.append(
                f"| {model_name} | {t} | {d['total']} | {d['strict_hit']} | {d['lenient_only']} | {d['missed']} | {d['strict_plus_lenient']} | — |"
            )
        tot = gc["TOTAL"]
        table_d_rows.append(
            f"| {model_name} | TOTAL | {tot['total']} | {tot['strict_hit']} | {tot['lenient_only']} | {tot['missed']} | {tot['strict_plus_lenient']} | {tot['lenient_tp']} |"
        )
    table_d_body = "\n".join(table_d_rows)

    # Table E: Error Examples
    table_e_rows = []
    for model_name in MODELS:
        slug = MODEL_SLUGS[model_name]
        errs = metrics["models"][slug]["error_examples"]
        for ex in errs["strict_miss_lenient_hit"]:
            g_disp = ex['gold_text'].replace('|', '/')
            p_disp = ex['pred_text'].replace('|', '/')
            table_e_rows.append(f"| {model_name} | STRICT_MISS_LENIENT_HIT | `{ex['doc_id']}` | NAME | `{g_disp}` | `{p_disp}` |")
        for ex in errs["missed"]:
            g_disp = ex['gold_text'].replace('|', '/')
            table_e_rows.append(f"| {model_name} | MISSED | `{ex['doc_id']}` | {ex['gold_type']} | `{g_disp}` | — |")
        for ex in errs["false_positive"]:
            p_disp = ex['pred_text'].replace('|', '/')
            table_e_rows.append(f"| {model_name} | FALSE_POSITIVE | `{ex['doc_id']}` | — | — | `{p_disp}` |")
    table_e_body = "\n".join(table_e_rows)

    # Table F: Stride and Runtime Summary
    table_f_rows = []
    tot_firs = metrics["dataset_counts"]["total_firs"]
    for model_name in MODELS:
        slug = MODEL_SLUGS[model_name]
        sr = metrics["stride_and_runtime"][slug]
        table_f_rows.append(
            f"| {model_name} | {tot_firs} | {sr['texts_needing_stride']} | {sr['max_length']} | {sr['stride_value']} | {sr['runtime_seconds']:.2f} |"
        )
    table_f_body = "\n".join(table_f_rows)

    # Table G: Input Hashes
    table_g_body = "\n".join([
        f"| `ai_pipeline/ner_baseline.py` | `{hashes['ner_baseline_py']}` | NER pipeline, post-processing, and evaluation harness |",
        f"| `ai_pipeline/scoring.py` | `{hashes['scoring_py']}` | Mention and relational scoring functions |",
        f"| `tests/test_ner_baseline.py` | `{hashes['test_ner_baseline_py']}` | NER unit test suite |",
        f"| `data/synthetic/out/firs_v5/index.json` | `{hashes['firs_v5_index_json']}` | Corpus partition and metadata index |",
        f"| `firs_v5 (narratives & keys)` | `{hashes['firs_v5_combined']}` | Combined SHA-256 digest of corpus files |",
    ])

    # Test List Table
    test_rows = []
    for item in pytest_tests:
        test_rows.append(f"| `{item['test_name']}` | {item['description']} | **{item['outcome']}** |")
    test_table_body = "\n".join(test_rows)

    # Key Numbers Lines
    key_numbers_specs = [
        ("determinism.davlan_xlm_roberta_base_ner_hrl.match", "XLM-R determinism match between runs"),
        ("determinism.ai4bharat_indicner.match", "IndicNER determinism match between runs"),
        ("stride_and_runtime.ai4bharat_indicner.texts_needing_stride", "IndicNER texts requiring fast tokenizer stride"),
        ("models.davlan_xlm_roberta_base_ner_hrl.overall.POSTPROCESSED.ALL_NAMES.strict.f1", "XLM-R postprocessed ALL_NAMES strict F1"),
        ("models.davlan_xlm_roberta_base_ner_hrl.overall.POSTPROCESSED.ALL_NAMES.lenient.f1", "XLM-R postprocessed ALL_NAMES lenient F1"),
        ("models.ai4bharat_indicner.overall.POSTPROCESSED.ALL_NAMES.strict.f1", "IndicNER postprocessed ALL_NAMES strict F1"),
        ("models.ai4bharat_indicner.overall.POSTPROCESSED.ALL_NAMES.lenient.f1", "IndicNER postprocessed ALL_NAMES lenient F1"),
        ("models.davlan_xlm_roberta_base_ner_hrl.gold_classification.ALIAS.missed", "XLM-R missed alias count"),
        ("models.ai4bharat_indicner.decoded_word_check.by_language.hindi.mismatches", "IndicNER Hindi decoded word vowel mismatches"),
        ("models.davlan_xlm_roberta_base_ner_hrl.decoded_word_check.by_language.hindi.mismatches", "XLM-R Hindi decoded word vowel mismatches"),
    ]
    key_numbers_lines = [
        format_key_number_line(metrics, path, label)
        for path, label in key_numbers_specs
    ]
    key_numbers_body = "\n".join(f"  {line}" for line in key_numbers_lines)

    section = f"""<!-- STEP5B:BEGIN -->
## Step 5b: Off-the-Shelf NER Baseline Evaluation

### Results Card
- **Purpose**: Baseline evaluation of pre-trained multilingual and Indic Named Entity Recognition models against synthetic First Information Report narratives and ground truth name entities.
- **Exact Command**: `python scripts/report/step5b_ner_baseline.py --run-id {run_id}`
- **Exact Pytest Command**: `{pytest_cmd}`
- **Input Files**:
  - `ai_pipeline/ner_baseline.py` (SHA-256: `{hashes['ner_baseline_py']}`)
  - `ai_pipeline/scoring.py` (SHA-256: `{hashes['scoring_py']}`)
  - `tests/test_ner_baseline.py` (SHA-256: `{hashes['test_ner_baseline_py']}`)
  - `data/synthetic/out/firs_v5/index.json` (SHA-256: `{hashes['firs_v5_index_json']}`)
  - Combined `firs_v5` texts and answer keys (SHA-256: `{hashes['firs_v5_combined']}`)
- **Output Files**:
  - `metrics.json` (SHA-256: `{output_hashes['metrics_json']}`)
  - `pytest_raw.txt` (SHA-256: `{output_hashes['pytest_raw_txt']}`)
  - `raw_davlan_xlm_roberta_base_ner_hrl_run1.json` (SHA-256: `{output_hashes['raw_davlan_xlm_roberta_base_ner_hrl_run1_json']}`)
  - `raw_davlan_xlm_roberta_base_ner_hrl_run2.json` (SHA-256: `{output_hashes['raw_davlan_xlm_roberta_base_ner_hrl_run2_json']}`)
  - `raw_ai4bharat_indicner_run1.json` (SHA-256: `{output_hashes['raw_ai4bharat_indicner_run1_json']}`)
  - `raw_ai4bharat_indicner_run2.json` (SHA-256: `{output_hashes['raw_ai4bharat_indicner_run2_json']}`)
  - `SHA256SUMS.txt` (SHA-256: `{output_hashes['sha256sums_txt']}`)
- **Key Numbers**:
{key_numbers_body}
- **Environment**: Python {metrics['meta']['python_version_short']}, PyTorch {metrics['meta']['torch_version']}, Transformers {metrics['meta']['transformers_version']}

### Tables

#### Table A: Overall Performance by Extractor and Type
| Model | Form | Mode | Strict P | Strict R | Strict F1 | Strict TP | Strict FP | Strict FN | Lenient P | Lenient R | Lenient F1 | Len TP | Len FP | Len FN |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
{table_a_body}

#### Table B: Strict and Lenient F1 by Language and Split
| Model | Group Type | Category | Strict F1 | Lenient F1 |
| :--- | :--- | :--- | :--- | :--- |
{table_b_body}

#### Table C: Decoded Word Check with Examples
| Model | Language | Total Spans | Mismatches | First Error Examples |
| :--- | :--- | :--- | :--- | :--- |
{table_c_body}

#### Table D: Misses by Gold Type
| Model | Gold Type | Total Mentions | Strict Hit (TP) | Lenient Only | Missed (FN) | Strict + Lenient | Lenient TP |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
{table_d_body}

#### Table E: Error Examples
| Model | Error Category | Document ID | Gold Type | Gold Text | Predicted Text |
| :--- | :--- | :--- | :--- | :--- | :--- |
{table_e_body}

#### Table F: Stride and Runtime Summary
| Model | Texts Evaluated | Texts Needing Stride | Model Max Length | Stride Parameter | Runtime Seconds |
| :--- | :--- | :--- | :--- | :--- | :--- |
{table_f_body}

#### Table G: Input Hashes
| Component File | SHA-256 Digest | Evaluation Role |
| :--- | :--- | :--- |
{table_g_body}

### Test List
| Test Function | Description | Test Outcome |
| :--- | :--- | :--- |
{test_table_body}

### Glossary
- strict = evaluation matching criterion requiring exact identity of entity category and character boundary offsets
- lenient = evaluation matching criterion requiring matching entity category and character overlap resolved greedily by shared span length
- precision = ratio of true positive extractions to total predicted extractions
- recall = ratio of true positive extractions to total reference ground truth extractions
- F1 = harmonic mean of precision and recall providing a balanced performance metric
- TP = true positive extraction matching reference ground truth under the active criterion
- FP = false positive extraction predicted by the extractor without corresponding ground truth match
- FN = false negative extraction present in ground truth that was omitted by the extractor
- RAW = direct predictions from Hugging Face token-classification pipeline prior to boundary adjustment
- POSTPROCESSED = predictions refined by whitespace boundary trimming and zero-gap fragment merging
- PERSON_ONLY = evaluation mode restricting reference and prediction entities to primary person names
- ALL_NAMES = evaluation mode unifying person names, aliases, and paternal references under a common name category
- STRICT_HIT = gold mention whose start and end character boundaries match a predicted mention exactly
- LENIENT_ONLY = gold mention whose span overlaps a predicted mention but whose character boundaries differ
- MISSED = gold mention having no character overlap with any predicted mention
- One-to-one matching note: total of STRICT_HIT plus LENIENT_ONLY can differ from lenient TP because greedy bipartite matching pairs each prediction with at most one gold mention

### Design Decisions
- Two-stage evaluation: Evaluating both unadjusted pipeline outputs and postprocessed spans isolates tokenization boundary artifacts from underlying entity detection capability.
- Offline execution boundary: Pipeline initialization enforces offline execution constraints using cached model weights to guarantee reproducible evaluation without external network dependencies.
- Zero-gap token piece fusion: Boundary postprocessing joins touching subword fragments while preserving whitespace boundaries between distinct names.
- Unified name category benchmark: Evaluating suspect names, aliases, and paternal references under a shared category tests open-domain name extraction where fine-grained legal roles cannot be distinguished by off-the-shelf NER models.

### Caveats
- the models are used off the shelf without any training on our data
- the FIR texts come from templates
- the post-processing steps were designed after seeing raw model output
- runtime is a single measurement and varies between runs
- the gold name labels come from the generator
- the models cannot tell suspects, fathers and aliases apart

### What This Does Not Show
- Domain fine-tuning potential: Results reflect pre-trained performance rather than the ceiling achievable after task-specific fine-tuning on Indian police narratives.
- Fine-grained role classification: Off-the-shelf NER extractors do not assign investigative roles such as suspect, complainant, or witness.
- Cross-lingual coreference resolution: Benchmarks evaluate mention extraction within single documents and do not resolve aliases across multiple case narratives.
- Production throughput under concurrency: Single-thread CPU latency measurements do not evaluate batch inference scaling across distributed serving workers.
<!-- STEP5B:END -->"""

    validate_markdown_tables_and_rules(section)
    assert_tables_match_metrics(section, metrics)
    return section


def main() -> None:
    parser = argparse.ArgumentParser(description="Step 5b NER baseline evaluation and reporting.")
    parser.add_argument("--run-id", default="step5b_ner_baseline", help="Identifier for evaluation results run")
    args = parser.parse_args()

    today_str = datetime.date.today().strftime("%Y-%m-%d")
    results_dir_name = f"{today_str}_{args.run_id}"
    results_dir = REPO_ROOT / "results" / results_dir_name

    # 1. Stop with an error if results folder already exists
    if results_dir.exists():
        print(f"ERROR: Destination folder '{results_dir}' already exists. Aborting to avoid overwrite.", file=sys.stderr)
        sys.exit(1)

    results_dir.mkdir(parents=True, exist_ok=False)

    # 2. Run pytest on tests/test_ner_baseline.py and save raw output
    pytest_raw_file = results_dir / "pytest_raw.txt"
    pytest_cmd = "python -m pytest -v tests/test_ner_baseline.py"
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-v", "tests/test_ner_baseline.py"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    raw_output = proc.stdout + ("\n" + proc.stderr if proc.stderr else "")
    pytest_raw_file.write_text(raw_output, encoding="utf-8")

    # 3. For each model, run twice on all 100 FIRs and save raw spans
    firs_dir = REPO_ROOT / "data" / "synthetic" / "out" / "firs_v5"
    gold = load_gold_mentions(firs_dir)
    meta = load_doc_meta(firs_dir)
    doc_ids = sorted(gold.keys())
    texts = [firs_dir.joinpath(f"{d}.txt").read_text(encoding="utf-8") for d in doc_ids]

    determinism_data: dict[str, Any] = {}
    stride_and_runtime_data: dict[str, Any] = {}
    raw_span_files: list[Path] = []

    for model_name in MODELS:
        slug = MODEL_SLUGS[model_name]
        pipe = get_pipeline(model_name)
        max_len = pipe.tokenizer.model_max_length

        stride_docs = []
        for d in doc_ids:
            t = firs_dir.joinpath(f"{d}.txt").read_text(encoding="utf-8")
            tok_count = len(pipe.tokenizer(t, truncation=False, add_special_tokens=True)["input_ids"])
            if tok_count > max_len:
                stride_docs.append(d)

        # Run 1
        t0 = time.time()
        spans_r1 = run_model(model_name, texts)
        runtime_r1 = time.time() - t0
        run1_by_doc = {d: sp for d, sp in zip(doc_ids, spans_r1)}
        run1_file = results_dir / f"raw_{slug}_run1.json"
        with open(run1_file, "w", encoding="utf-8") as f:
            json.dump(run1_by_doc, f, indent=2, sort_keys=True)
        raw_span_files.append(run1_file)

        # Run 2
        spans_r2 = run_model(model_name, texts)
        run2_by_doc = {d: sp for d, sp in zip(doc_ids, spans_r2)}
        run2_file = results_dir / f"raw_{slug}_run2.json"
        with open(run2_file, "w", encoding="utf-8") as f:
            json.dump(run2_by_doc, f, indent=2, sort_keys=True)
        raw_span_files.append(run2_file)

        h1 = compute_sha256(run1_file)
        h2 = compute_sha256(run2_file)
        determinism_data[slug] = {
            "model_name": model_name,
            "run1_sha256": h1,
            "run2_sha256": h2,
            "match": (h1 == h2),
        }
        stride_and_runtime_data[slug] = {
            "model_name": model_name,
            "texts_needing_stride": len(stride_docs),
            "texts_with_stride": stride_docs,
            "runtime_seconds": runtime_r1,
            "max_length": max_len,
            "stride_value": 64,
        }

    # 4. Compute metrics ONLY by reloading saved run1 files
    models_metrics: dict[str, Any] = {}
    for model_name in MODELS:
        slug = MODEL_SLUGS[model_name]
        run1_file = results_dir / f"raw_{slug}_run1.json"
        with open(run1_file, "r", encoding="utf-8") as f:
            raw_by_doc = json.load(f)

        post_by_doc = {
            d: postprocess(firs_dir.joinpath(f"{d}.txt").read_text(encoding="utf-8"), spans)
            for d, spans in raw_by_doc.items()
        }

        # Overall evaluations
        overall_metrics: dict[str, Any] = {}
        for form_name, pred_map in [("RAW", raw_by_doc), ("POSTPROCESSED", post_by_doc)]:
            overall_metrics[form_name] = {}
            for mode_name in ["PERSON_ONLY", "ALL_NAMES"]:
                eval_res = evaluate(gold, pred_map, meta=meta, mode=mode_name)
                overall_metrics[form_name][mode_name] = {
                    "strict": eval_res["micro"]["strict"],
                    "lenient": eval_res["micro"]["lenient"],
                }

        # Language and Split evaluations under POSTPROCESSED ALL_NAMES
        eval_lang = evaluate(gold, post_by_doc, meta=meta, mode="ALL_NAMES", group_by="language")
        eval_split = evaluate(gold, post_by_doc, meta=meta, mode="ALL_NAMES", group_by="split")
        post_all_names_metrics = {
            "by_language": {
                lang: {
                    "strict": eval_lang[lang]["micro"]["strict"],
                    "lenient": eval_lang[lang]["micro"]["lenient"],
                }
                for lang in ["hinglish", "hindi", "english"]
            },
            "by_split": {
                split: {
                    "strict": eval_split[split]["micro"]["strict"],
                    "lenient": eval_split[split]["micro"]["lenient"],
                }
                for split in ["train", "dev", "test"]
            },
        }

        # Decoded word check per language
        decoded_check_by_lang: dict[str, Any] = {}
        for lang in ["hinglish", "hindi", "english"]:
            lang_docs = [d for d in doc_ids if meta[d]["language"].lower() == lang]
            total_spans = sum(len(raw_by_doc[d]) for d in lang_docs)
            mismatches = 0
            lang_exs = []
            for d in lang_docs:
                text = firs_dir.joinpath(f"{d}.txt").read_text(encoding="utf-8")
                cnt, exs = decoded_word_check(text, raw_by_doc[d])
                mismatches += cnt
                if len(lang_exs) < 5:
                    lang_exs.extend(exs[: 5 - len(lang_exs)])
            decoded_check_by_lang[lang] = {
                "total_spans": total_spans,
                "mismatches": mismatches,
                "examples": lang_exs,
            }

        # Gold classification under POSTPROCESSED ALL_NAMES
        gold_counts = {
            "PERSON": {"total": 0, "strict_hit": 0, "lenient_only": 0, "missed": 0, "strict_plus_lenient": 0},
            "ALIAS": {"total": 0, "strict_hit": 0, "lenient_only": 0, "missed": 0, "strict_plus_lenient": 0},
            "FATHER": {"total": 0, "strict_hit": 0, "lenient_only": 0, "missed": 0, "strict_plus_lenient": 0},
        }
        strict_miss_lenient_hits = []
        missed_examples = []

        for d in doc_ids:
            p_list = post_by_doc[d]
            for g in gold[d]:
                orig_t = g["type"]
                if orig_t not in ("PERSON", "ALIAS", "FATHER"):
                    continue
                gold_counts[orig_t]["total"] += 1
                gs, ge = g["start"], g["end"]

                exact_preds = [p for p in p_list if p["start"] == gs and p["end"] == ge]
                if exact_preds:
                    gold_counts[orig_t]["strict_hit"] += 1
                else:
                    ov_preds = [p for p in p_list if min(p["end"], ge) > max(p["start"], gs)]
                    if ov_preds:
                        gold_counts[orig_t]["lenient_only"] += 1
                        if len(strict_miss_lenient_hits) < 5:
                            best_p = max(ov_preds, key=lambda p: min(p["end"], ge) - max(p["start"], gs))
                            strict_miss_lenient_hits.append({
                                "doc_id": d,
                                "gold_text": g["text"],
                                "pred_text": best_p["word"],
                            })
                    else:
                        gold_counts[orig_t]["missed"] += 1
                        if len(missed_examples) < 5:
                            missed_examples.append({
                                "doc_id": d,
                                "gold_type": orig_t,
                                "gold_text": g["text"],
                            })

        # False positive examples (first 5 in doc order with zero overlap with any gold name)
        fp_examples = []
        for d in doc_ids:
            g_spans = [(m["start"], m["end"]) for m in gold[d] if m["type"] in ("PERSON", "ALIAS", "FATHER")]
            for p in post_by_doc[d]:
                if not any(min(p["end"], ge) > max(p["start"], gs) for gs, ge in g_spans):
                    if len(fp_examples) < 5:
                        fp_examples.append({
                            "doc_id": d,
                            "pred_text": p["word"],
                        })

        total_g_mentions = sum(gold_counts[t]["total"] for t in ("PERSON", "ALIAS", "FATHER"))
        total_strict_hits = sum(gold_counts[t]["strict_hit"] for t in ("PERSON", "ALIAS", "FATHER"))
        total_lenient_only = sum(gold_counts[t]["lenient_only"] for t in ("PERSON", "ALIAS", "FATHER"))
        total_missed = sum(gold_counts[t]["missed"] for t in ("PERSON", "ALIAS", "FATHER"))
        total_strict_plus_lenient = total_strict_hits + total_lenient_only

        st_tp = overall_metrics["POSTPROCESSED"]["ALL_NAMES"]["strict"]["tp"]
        lt_tp = overall_metrics["POSTPROCESSED"]["ALL_NAMES"]["lenient"]["tp"]
        assert total_strict_hits == st_tp, f"Total strict hits ({total_strict_hits}) != score_mentions strict TP ({st_tp})"

        for t in ("PERSON", "ALIAS", "FATHER"):
            gold_counts[t]["strict_plus_lenient"] = gold_counts[t]["strict_hit"] + gold_counts[t]["lenient_only"]

        gold_counts["TOTAL"] = {
            "total": total_g_mentions,
            "strict_hit": total_strict_hits,
            "lenient_only": total_lenient_only,
            "missed": total_missed,
            "strict_plus_lenient": total_strict_plus_lenient,
            "lenient_tp": lt_tp,
        }

        models_metrics[slug] = {
            "model_name": model_name,
            "overall": overall_metrics,
            "postprocessed_all_names": post_all_names_metrics,
            "decoded_word_check": {"by_language": decoded_check_by_lang},
            "gold_classification": gold_counts,
            "error_examples": {
                "strict_miss_lenient_hit": strict_miss_lenient_hits,
                "missed": missed_examples,
                "false_positive": fp_examples,
            },
        }

    # Combined corpus files hash
    firs_v5_files = [
        p for p in firs_dir.iterdir()
        if p.is_file() and p.name.startswith("FIR_") and (p.name.endswith(".txt") or p.name.endswith(".json"))
    ]
    firs_v5_combined_hash = compute_combined_sha256(firs_v5_files)

    input_hashes = {
        "ner_baseline_py": compute_sha256(REPO_ROOT / "ai_pipeline" / "ner_baseline.py"),
        "scoring_py": compute_sha256(REPO_ROOT / "ai_pipeline" / "scoring.py"),
        "test_ner_baseline_py": compute_sha256(REPO_ROOT / "tests" / "test_ner_baseline.py"),
        "firs_v5_index_json": compute_sha256(firs_dir / "index.json"),
        "firs_v5_combined": firs_v5_combined_hash,
    }

    metrics: dict[str, Any] = {
        "meta": {
            "run_id": args.run_id,
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "python_version": sys.version,
            "python_version_short": platform.python_version(),
            "torch_version": torch.__version__,
            "transformers_version": transformers.__version__,
            "command": f"python scripts/report/step5b_ner_baseline.py --run-id {args.run_id}",
            "pytest_command": pytest_cmd,
        },
        "input_hashes": input_hashes,
        "dataset_counts": {
            "total_firs": len(gold),
            "total_gold_mentions": sum(len(ml) for ml in gold.values()),
        },
        "determinism": determinism_data,
        "stride_and_runtime": stride_and_runtime_data,
        "models": models_metrics,
    }

    # Write metrics.json
    metrics_file = results_dir / "metrics.json"
    with open(metrics_file, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)

    # 5. Write SHA256SUMS.txt
    files_to_hash = [pytest_raw_file, metrics_file] + raw_span_files
    sha_lines = []
    output_hashes = {}
    for fp in files_to_hash:
        file_hash = compute_sha256(fp)
        rel_p = fp.name
        sha_lines.append(f"{file_hash}  {rel_p}")
        output_hashes[fp.name.replace(".", "_")] = file_hash

    sha256sums_path = results_dir / "SHA256SUMS.txt"
    sha256sums_path.write_text("\n".join(sha_lines) + "\n", encoding="utf-8")
    output_hashes["sha256sums_txt"] = compute_sha256(sha256sums_path)

    # Make all output files read-only
    for fp in files_to_hash + [sha256sums_path]:
        os.chmod(fp, stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)

    # 6. Build and insert markdown block in docs/RESULTS.md
    test_file = REPO_ROOT / "tests" / "test_ner_baseline.py"
    docstrings = extract_test_docstrings(test_file)
    pytest_tests = parse_pytest_results(raw_output, docstrings)

    step5b_md = build_markdown_section(
        run_id=args.run_id,
        metrics=metrics,
        output_hashes=output_hashes,
        pytest_tests=pytest_tests,
        pytest_cmd=pytest_cmd,
    )

    docs_file = REPO_ROOT / "docs" / "RESULTS.md"
    existing_doc = docs_file.read_text(encoding="utf-8")

    m1_before = re.search(r"<!-- STEP1:BEGIN -->.*?<!-- STEP1:END -->", existing_doc, re.DOTALL)
    m2_before = re.search(r"<!-- STEP2:BEGIN -->.*?<!-- STEP2:END -->", existing_doc, re.DOTALL)
    m5a_before = re.search(r"<!-- STEP5A:BEGIN -->.*?<!-- STEP5A:END -->", existing_doc, re.DOTALL)
    step1_hash_before = hashlib.sha256(m1_before.group(0).encode("utf-8")).hexdigest() if m1_before else None
    step2_hash_before = hashlib.sha256(m2_before.group(0).encode("utf-8")).hexdigest() if m2_before else None
    step5a_hash_before = hashlib.sha256(m5a_before.group(0).encode("utf-8")).hexdigest() if m5a_before else None

    marker_pattern = re.compile(r"<!-- STEP5B:BEGIN -->.*?<!-- STEP5B:END -->", re.DOTALL)
    if marker_pattern.search(existing_doc):
        new_doc = marker_pattern.sub(lambda _: step5b_md, existing_doc)
    else:
        if "<!-- STEP5A:END -->" in existing_doc:
            parts = existing_doc.split("<!-- STEP5A:END -->")
            new_doc = parts[0] + "<!-- STEP5A:END -->\n\n" + step5b_md + parts[1].lstrip("\n")
        else:
            new_doc = existing_doc.rstrip() + "\n\n" + step5b_md + "\n"

    m1_after = re.search(r"<!-- STEP1:BEGIN -->.*?<!-- STEP1:END -->", new_doc, re.DOTALL)
    m2_after = re.search(r"<!-- STEP2:BEGIN -->.*?<!-- STEP2:END -->", new_doc, re.DOTALL)
    m5a_after = re.search(r"<!-- STEP5A:BEGIN -->.*?<!-- STEP5A:END -->", new_doc, re.DOTALL)
    step1_hash_after = hashlib.sha256(m1_after.group(0).encode("utf-8")).hexdigest() if m1_after else None
    step2_hash_after = hashlib.sha256(m2_after.group(0).encode("utf-8")).hexdigest() if m2_after else None
    step5a_hash_after = hashlib.sha256(m5a_after.group(0).encode("utf-8")).hexdigest() if m5a_after else None

    if step1_hash_before != step1_hash_after:
        raise ValueError("FATAL: STEP1 block changed during RESULTS.md update!")
    if step2_hash_before != step2_hash_after:
        raise ValueError("FATAL: STEP2 block changed during RESULTS.md update!")
    if step5a_hash_before != step5a_hash_after:
        raise ValueError("FATAL: STEP5A block changed during RESULTS.md update!")

    docs_file.write_text(new_doc, encoding="utf-8")
    print(f"Step 5b baseline completed successfully.")
    print(f"New folder: {results_dir}")
    print(f"STEP1 hash: {step1_hash_before}")
    print(f"STEP2 hash: {step2_hash_before}")
    print(f"STEP5A hash: {step5a_hash_before}")


if __name__ == "__main__":
    main()

