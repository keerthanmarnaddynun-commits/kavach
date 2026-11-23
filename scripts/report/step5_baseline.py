"""
Step 5a: Baseline evaluation and reporting script.
Evaluates RULES and NAIVE extractors against synthetic FIR texts and contract ground truth.
Documents evaluation results in docs/RESULTS.md under <!-- STEP5A:BEGIN --> ... <!-- STEP5A:END -->.
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
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai_pipeline.identifiers import find_all_identifiers
from scripts.check_results_docs import ALL_BANNED
from ai_pipeline.scoring import (
    _load_contract_docs,
    load_doc_meta,
    load_gold_mentions,
    prf,
    score_mentions,
    score_relations,
)


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


def run_naive_extractor(text: str) -> list[dict[str, Any]]:
    """Plain regexes on raw text returning all unconstrained matches."""
    patterns = {
        "PHONE": re.compile(r"(?<!\d)\d{10}(?!\d)"),
        "IMEI": re.compile(r"(?<!\d)\d{15}(?!\d)"),
        "ACCOUNT": re.compile(r"(?<!\d)\d{9,18}(?!\d)"),
        "AMOUNT": re.compile(r"(?:Rs\.?|INR|₹)\s*[\d,]+"),
    }
    mentions = []
    for t, rx in patterns.items():
        for m in rx.finditer(text):
            mentions.append({
                "type": t,
                "start": m.start(),
                "end": m.end(),
                "text": text[m.start():m.end()],
            })
    return mentions


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
    Assert for every table value in Tables A to D that it equals the corresponding
    metrics.json value (rounded to four decimals); abort on any mismatch.
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
        ext, etype, sp, sr, sf1, lp, lr, lf1, stp, sfp, sfn = row
        ext_key = "rules" if ext == "RULES" else "naive"
        st = metrics[f"{ext_key}_evaluation"]["overall"][etype]["strict"]
        lt = metrics[f"{ext_key}_evaluation"]["overall"][etype]["lenient"]

        expected_sp = round(st["precision"], 4) if st["precision"] is not None else None
        expected_sr = round(st["recall"], 4) if st["recall"] is not None else None
        expected_sf1 = round(st["f1"], 4) if st["f1"] is not None else None
        expected_lp = round(lt["precision"], 4) if lt["precision"] is not None else None
        expected_lr = round(lt["recall"], 4) if lt["recall"] is not None else None
        expected_lf1 = round(lt["f1"], 4) if lt["f1"] is not None else None

        assert float(sp) == expected_sp, f"Table A strict P mismatch for {ext} {etype}: {sp} != {expected_sp}"
        assert float(sr) == expected_sr, f"Table A strict R mismatch for {ext} {etype}: {sr} != {expected_sr}"
        assert float(sf1) == expected_sf1, f"Table A strict F1 mismatch for {ext} {etype}: {sf1} != {expected_sf1}"
        assert float(lp) == expected_lp, f"Table A lenient P mismatch for {ext} {etype}: {lp} != {expected_lp}"
        assert float(lr) == expected_lr, f"Table A lenient R mismatch for {ext} {etype}: {lr} != {expected_lr}"
        assert float(lf1) == expected_lf1, f"Table A lenient F1 mismatch for {ext} {etype}: {lf1} != {expected_lf1}"
        assert int(stp) == st["tp"], f"Table A strict TP mismatch for {ext} {etype}: {stp} != {st['tp']}"
        assert int(sfp) == st["fp"], f"Table A strict FP mismatch for {ext} {etype}: {sfp} != {st['fp']}"
        assert int(sfn) == st["fn"], f"Table A strict FN mismatch for {ext} {etype}: {sfn} != {st['fn']}"

    # Assert Table B: Strict F1 by Entity Type Across Dataset Partition Splits
    rows_b = extract_table_rows("Table B:")
    for row in rows_b:
        ext, etype, f_tr, f_dv, f_ts, f_ov = row
        ext_key = "rules" if ext == "RULES" else "naive"
        b_sp = metrics[f"{ext_key}_evaluation"]["by_split"]
        expected_tr = round(b_sp["train"][etype]["strict"]["f1"], 4)
        expected_dv = round(b_sp["dev"][etype]["strict"]["f1"], 4)
        expected_ts = round(b_sp["test"][etype]["strict"]["f1"], 4)
        expected_ov = round(metrics[f"{ext_key}_evaluation"]["overall"][etype]["strict"]["f1"], 4)

        assert float(f_tr) == expected_tr, f"Table B train F1 mismatch for {ext} {etype}: {f_tr} != {expected_tr}"
        assert float(f_dv) == expected_dv, f"Table B dev F1 mismatch for {ext} {etype}: {f_dv} != {expected_dv}"
        assert float(f_ts) == expected_ts, f"Table B test F1 mismatch for {ext} {etype}: {f_ts} != {expected_ts}"
        assert float(f_ov) == expected_ov, f"Table B overall F1 mismatch for {ext} {etype}: {f_ov} != {expected_ov}"

    # Assert Table C: Strict F1 by Entity Type Across Narrative Languages
    rows_c = extract_table_rows("Table C:")
    for row in rows_c:
        ext, etype, f_hg, f_hi, f_en, f_ov = row
        ext_key = "rules" if ext == "RULES" else "naive"
        b_lg = metrics[f"{ext_key}_evaluation"]["by_language"]
        expected_hg = round(b_lg["hinglish"][etype]["strict"]["f1"], 4)
        expected_hi = round(b_lg["hindi"][etype]["strict"]["f1"], 4)
        expected_en = round(b_lg["english"][etype]["strict"]["f1"], 4)
        expected_ov = round(metrics[f"{ext_key}_evaluation"]["overall"][etype]["strict"]["f1"], 4)

        assert float(f_hg) == expected_hg, f"Table C hinglish F1 mismatch for {ext} {etype}: {f_hg} != {expected_hg}"
        assert float(f_hi) == expected_hi, f"Table C hindi F1 mismatch for {ext} {etype}: {f_hi} != {expected_hi}"
        assert float(f_en) == expected_en, f"Table C english F1 mismatch for {ext} {etype}: {f_en} != {expected_en}"
        assert float(f_ov) == expected_ov, f"Table C overall F1 mismatch for {ext} {etype}: {f_ov} != {expected_ov}"

    # Assert Table D: Evaluation Harness Checks
    rows_d = extract_table_rows("Table D:")
    hc = metrics["harness_checks"]

    # Row 0: Reference Mentions | Gold Predictions
    assert int(rows_d[0][2]) == hc["gold_mentions"]["tp"]
    assert int(rows_d[0][3]) == hc["gold_mentions"]["fp"]
    assert int(rows_d[0][4]) == hc["gold_mentions"]["fn"]
    assert float(rows_d[0][5]) == round(hc["gold_mentions"]["precision"], 4)
    assert float(rows_d[0][6]) == round(hc["gold_mentions"]["recall"], 4)
    assert float(rows_d[0][7]) == round(hc["gold_mentions"]["f1"], 4)

    # Row 1: Reference Mentions | Empty Predictions
    assert int(rows_d[1][2]) == hc["empty_mentions"]["tp"]
    assert int(rows_d[1][3]) == hc["empty_mentions"]["fp"]
    assert int(rows_d[1][4]) == hc["empty_mentions"]["fn"]
    assert rows_d[1][5] == "—"
    assert float(rows_d[1][6]) == round(hc["empty_mentions"]["recall"], 4)
    assert rows_d[1][7] == "—"

    # Row 2: Contract Relations | Gold Predictions
    assert int(rows_d[2][2]) == hc["gold_relations"]["tp"]
    assert int(rows_d[2][3]) == hc["gold_relations"]["fp"]
    assert int(rows_d[2][4]) == hc["gold_relations"]["fn"]
    assert float(rows_d[2][5]) == round(hc["gold_relations"]["precision"], 4)
    assert float(rows_d[2][6]) == round(hc["gold_relations"]["recall"], 4)
    assert float(rows_d[2][7]) == round(hc["gold_relations"]["f1"], 4)

    # Row 3: Contract Relations | Empty Predictions
    assert int(rows_d[3][2]) == hc["empty_relations"]["tp"]
    assert int(rows_d[3][3]) == hc["empty_relations"]["fp"]
    assert int(rows_d[3][4]) == hc["empty_relations"]["fn"]
    assert rows_d[3][5] == "—"
    assert float(rows_d[3][6]) == round(hc["empty_relations"]["recall"], 4)
    assert rows_d[3][7] == "—"


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
                # Validate the accumulated table
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
    """Build the complete Markdown section for Step 5a."""
    hashes = metrics["input_hashes"]
    rules_overall = metrics["rules_evaluation"]["overall"]
    naive_overall = metrics["naive_evaluation"]["overall"]
    target_types = ["PHONE", "IMEI", "ACCOUNT", "AMOUNT"]

    # Table A rows
    table_a_rows = []
    for t in target_types:
        r_st = rules_overall[t]["strict"]
        r_lt = rules_overall[t]["lenient"]
        r_p_s, r_r_s, r_f_s = r_st["precision"], r_st["recall"], r_st["f1"]
        r_p_l, r_r_l, r_f_l = r_lt["precision"], r_lt["recall"], r_lt["f1"]
        table_a_rows.append(
            f"| RULES | {t} | {r_p_s:.4f} | {r_r_s:.4f} | {r_f_s:.4f} | {r_p_l:.4f} | {r_r_l:.4f} | {r_f_l:.4f} | {r_st['tp']} | {r_st['fp']} | {r_st['fn']} |"
        )
    for t in target_types:
        n_st = naive_overall[t]["strict"]
        n_lt = naive_overall[t]["lenient"]
        n_p_s, n_r_s, n_f_s = n_st["precision"], n_st["recall"], n_st["f1"]
        n_p_l, n_r_l, n_f_l = n_lt["precision"], n_lt["recall"], n_lt["f1"]
        table_a_rows.append(
            f"| NAIVE | {t} | {n_p_s:.4f} | {n_r_s:.4f} | {n_f_s:.4f} | {n_p_l:.4f} | {n_r_l:.4f} | {n_f_l:.4f} | {n_st['tp']} | {n_st['fp']} | {n_st['fn']} |"
        )
    table_a_body = "\n".join(table_a_rows)

    # Table B rows (by split)
    table_b_rows = []
    rules_splits = metrics["rules_evaluation"]["by_split"]
    naive_splits = metrics["naive_evaluation"]["by_split"]
    for t in target_types:
        f_tr = rules_splits["train"][t]["strict"]["f1"]
        f_dv = rules_splits["dev"][t]["strict"]["f1"]
        f_ts = rules_splits["test"][t]["strict"]["f1"]
        f_ov = rules_overall[t]["strict"]["f1"]
        table_b_rows.append(f"| RULES | {t} | {f_tr:.4f} | {f_dv:.4f} | {f_ts:.4f} | {f_ov:.4f} |")
    for t in target_types:
        f_tr = naive_splits["train"][t]["strict"]["f1"]
        f_dv = naive_splits["dev"][t]["strict"]["f1"]
        f_ts = naive_splits["test"][t]["strict"]["f1"]
        f_ov = naive_overall[t]["strict"]["f1"]
        table_b_rows.append(f"| NAIVE | {t} | {f_tr:.4f} | {f_dv:.4f} | {f_ts:.4f} | {f_ov:.4f} |")
    table_b_body = "\n".join(table_b_rows)

    # Table C rows (by language)
    table_c_rows = []
    rules_langs = metrics["rules_evaluation"]["by_language"]
    naive_langs = metrics["naive_evaluation"]["by_language"]
    for t in target_types:
        f_hg = rules_langs["hinglish"][t]["strict"]["f1"]
        f_hi = rules_langs["hindi"][t]["strict"]["f1"]
        f_en = rules_langs["english"][t]["strict"]["f1"]
        f_ov = rules_overall[t]["strict"]["f1"]
        table_c_rows.append(f"| RULES | {t} | {f_hg:.4f} | {f_hi:.4f} | {f_en:.4f} | {f_ov:.4f} |")
    for t in target_types:
        f_hg = naive_langs["hinglish"][t]["strict"]["f1"]
        f_hi = naive_langs["hindi"][t]["strict"]["f1"]
        f_en = naive_langs["english"][t]["strict"]["f1"]
        f_ov = naive_overall[t]["strict"]["f1"]
        table_c_rows.append(f"| NAIVE | {t} | {f_hg:.4f} | {f_hi:.4f} | {f_en:.4f} | {f_ov:.4f} |")
    table_c_body = "\n".join(table_c_rows)

    # Table D rows (Harness checks)
    hc = metrics["harness_checks"]
    table_d_body = "\n".join([
        f"| Reference Mentions | Gold Predictions | {hc['gold_mentions']['tp']} | {hc['gold_mentions']['fp']} | {hc['gold_mentions']['fn']} | {hc['gold_mentions']['precision']:.4f} | {hc['gold_mentions']['recall']:.4f} | {hc['gold_mentions']['f1']:.4f} |",
        f"| Reference Mentions | Empty Predictions | {hc['empty_mentions']['tp']} | {hc['empty_mentions']['fp']} | {hc['empty_mentions']['fn']} | — | {hc['empty_mentions']['recall']:.4f} | — |",
        f"| Contract Relations | Gold Predictions | {hc['gold_relations']['tp']} | {hc['gold_relations']['fp']} | {hc['gold_relations']['fn']} | {hc['gold_relations']['precision']:.4f} | {hc['gold_relations']['recall']:.4f} | {hc['gold_relations']['f1']:.4f} |",
        f"| Contract Relations | Empty Predictions | {hc['empty_relations']['tp']} | {hc['empty_relations']['fp']} | {hc['empty_relations']['fn']} | — | {hc['empty_relations']['recall']:.4f} | — |",
    ])

    # Table E rows (Input hashes)
    table_e_body = "\n".join([
        f"| `ai_pipeline/scoring.py` | `{hashes['scoring_py']}` | Mention and relational scoring harness |",
        f"| `ai_pipeline/identifiers.py` | `{hashes['identifiers_py']}` | Precedence-based identifier extraction |",
        f"| `ai_pipeline/validators.py` | `{hashes['validators_py']}` | Pattern finders and checksum validators |",
        f"| `ai_pipeline/normalizer.py` | `{hashes['normalizer_py']}` | Length-preserving Unicode normalization |",
        f"| `tests/test_scoring.py` | `{hashes['test_scoring_py']}` | Scoring test suite |",
        f"| `data/synthetic/out/firs_v5/index.json` | `{hashes['firs_v5_index_json']}` | Corpus split and language index |",
        f"| `firs_v5 (narratives & keys)` | `{hashes['firs_v5_combined']}` | Combined hash across all FIR text and JSON files |",
        f"| `firs_v5_contract (contracts)` | `{hashes['firs_v5_contract_combined']}` | Combined hash across all contract files |",
    ])

    # Test list rows
    test_rows = []
    for item in pytest_tests:
        test_rows.append(f"| `{item['test_name']}` | {item['description']} | **{item['outcome']}** |")
    test_table_body = "\n".join(test_rows)

    # Key Numbers lines via get_metric_by_path
    key_numbers_specs = [
        ("dataset_counts.total_firs", "total documents"),
        ("dataset_counts.total_gold_mentions", "total ground truth mentions"),
        ("dataset_counts.total_gold_relations", "total ground truth relations"),
        ("harness_checks.gold_mentions.f1", "reference mention F1"),
        ("harness_checks.empty_mentions.recall", "empty mention recall"),
        ("harness_checks.gold_relations.f1", "reference relation F1"),
        ("rules_evaluation.overall.PHONE.strict.f1", "RULES PHONE strict F1"),
        ("rules_evaluation.overall.ACCOUNT.strict.f1", "RULES ACCOUNT strict F1"),
        ("naive_evaluation.overall.ACCOUNT.strict.f1", "NAIVE ACCOUNT strict F1"),
        ("naive_evaluation.overall.AMOUNT.lenient.f1", "NAIVE AMOUNT lenient F1"),
    ]
    key_numbers_lines = [
        format_key_number_line(metrics, path, label)
        for path, label in key_numbers_specs
    ]
    key_numbers_body = "\n".join(f"  {line}" for line in key_numbers_lines)

    section = f"""<!-- STEP5A:BEGIN -->
## Step 5a: Identifier Baseline and Scoring Evaluation

### Results Card
- **Purpose**: Baseline evaluation of Indian identifier extraction against synthetic First Information Report narrative texts and relational ground truth using strict and lenient scoring metrics.
- **Exact Command**: `python scripts/report/step5_baseline.py --run-id {run_id}`
- **Exact Pytest Command**: `{pytest_cmd}`
- **Input Files**:
  - `ai_pipeline/scoring.py` (SHA-256: `{hashes['scoring_py']}`)
  - `ai_pipeline/identifiers.py` (SHA-256: `{hashes['identifiers_py']}`)
  - `ai_pipeline/validators.py` (SHA-256: `{hashes['validators_py']}`)
  - `ai_pipeline/normalizer.py` (SHA-256: `{hashes['normalizer_py']}`)
  - `tests/test_scoring.py` (SHA-256: `{hashes['test_scoring_py']}`)
  - `data/synthetic/out/firs_v5/index.json` (SHA-256: `{hashes['firs_v5_index_json']}`)
  - Combined `firs_v5` texts and answer keys (SHA-256: `{hashes['firs_v5_combined']}`)
  - Combined `firs_v5_contract` documents (SHA-256: `{hashes['firs_v5_contract_combined']}`)
- **Output Files**:
  - `metrics.json` (SHA-256: `{output_hashes['metrics_json']}`)
  - `pytest_raw.txt` (SHA-256: `{output_hashes['pytest_raw_txt']}`)
  - `SHA256SUMS.txt` (SHA-256: `{output_hashes['sha256sums_txt']}`)
- **Key Numbers**:
{key_numbers_body}
- **Environment**: Python {metrics['meta']['python_version_short']}

### Tables

#### Table A: Overall Performance by Extractor and Type
| Extractor | Entity Type | Strict P | Strict R | Strict F1 | Lenient P | Lenient R | Lenient F1 | Strict TP | Strict FP | Strict FN |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
{table_a_body}

#### Table B: Strict F1 by Entity Type Across Dataset Partition Splits
| Extractor | Entity Type | Train Split Strict F1 | Dev Split Strict F1 | Test Split Strict F1 | Overall Strict F1 |
| :--- | :--- | :--- | :--- | :--- | :--- |
{table_b_body}

#### Table C: Strict F1 by Entity Type Across Narrative Languages
| Extractor | Entity Type | Hinglish Strict F1 | Hindi Strict F1 | English Strict F1 | Overall Strict F1 |
| :--- | :--- | :--- | :--- | :--- | :--- |
{table_c_body}

#### Table D: Evaluation Harness Checks
| Evaluation Suite | Condition Tested | Strict TP | Strict FP | Strict FN | Precision | Recall | F1 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
{table_d_body}

#### Table E: Input Hashes
| Component File | SHA-256 Digest | Evaluation Role |
| :--- | :--- | :--- |
{table_e_body}

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
- RULES = rule-based disambiguation pipeline applying length-preserving normalization, pattern finders, checksum validation, and precedence resolution
- NAIVE = baseline regex patterns evaluated without boundary resolution or precedence: PHONE `(?<!\\d)\\d{{10}}(?!\\d)`, IMEI `(?<!\\d)\\d{{15}}(?!\\d)`, ACCOUNT `(?<!\\d)\\d{{9,18}}(?!\\d)`, AMOUNT `(?:Rs\\.?|INR|₹)\\s*[\\d,]+`

### Design Decisions
- Disambiguation precedence hierarchy: Extraction conflicts between overlapping entity patterns are resolved via fixed precedence ordering to favor specialized identifiers over ambiguous digit sequences.
- Length-preserving normalization: Multilingual and script variations are converted using one-to-one character substitutions to maintain character span offsets against raw document text.
- Dual-mode evaluation harness: Performance is assessed under strict boundary requirements alongside lenient span overlap to isolate boundary clipping from complete extraction omissions.
- Negative baseline comparison: Unfiltered naive regular expressions are evaluated alongside prioritized extraction to demonstrate penalty handling on conflicting matches.

### Caveats
- RULES patterns were tuned while reading these same FIR texts, so its scores are development scores
- the generated FIRs come from templates
- NAIVE exists to show that the scorer reacts to errors
- the gold has no vehicle labels
- person names are not scored here because no model has run

### What This Does Not Show
- Machine learning generalization: These evaluations assess rule-based pattern matching and do not reflect the statistical generalization of neural language models.
- Complex linguistic ambiguity: Template narratives do not encompass the syntactical irregularities, handwriting transcriptions, or informal shorthand typical of raw station entries.
- Unstructured relationship inference: Relational benchmarks evaluate schema consistency but do not test open-domain relation extraction across unconstrained prose.
- Operational runtime latency: Evaluation focuses exclusively on extraction accuracy without profiling real-time stream throughput or memory scaling.
<!-- STEP5A:END -->"""

    validate_markdown_tables_and_rules(section)
    assert_tables_match_metrics(section, metrics)
    return section


def main() -> None:
    parser = argparse.ArgumentParser(description="Step 5a baseline evaluation and reporting.")
    parser.add_argument("--run-id", default="step5a_baseline", help="Identifier for evaluation results run")
    args = parser.parse_args()

    today_str = datetime.date.today().strftime("%Y-%m-%d")
    results_dir_name = f"{today_str}_{args.run_id}"
    results_dir = REPO_ROOT / "results" / results_dir_name

    # 1. Stop with an error if results folder already exists
    if results_dir.exists():
        print(f"ERROR: Destination folder '{results_dir}' already exists. Aborting to avoid overwrite.", file=sys.stderr)
        sys.exit(1)

    results_dir.mkdir(parents=True, exist_ok=False)

    # 2. Run pytest on tests/test_scoring.py and save raw output
    pytest_raw_file = results_dir / "pytest_raw.txt"
    pytest_cmd = "python -m pytest -v tests/test_scoring.py"
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-v", "tests/test_scoring.py"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    raw_output = proc.stdout + ("\n" + proc.stderr if proc.stderr else "")
    pytest_raw_file.write_text(raw_output, encoding="utf-8")

    # 3. Compute everything from files
    firs_dir = REPO_ROOT / "data" / "synthetic" / "out" / "firs_v5"
    contract_dir = REPO_ROOT / "data" / "synthetic" / "out" / "firs_v5_contract"

    gold_mentions = load_gold_mentions(firs_dir)
    doc_meta = load_doc_meta(firs_dir)
    gold_contracts = _load_contract_docs(contract_dir)

    # Extractors
    pred_rules: dict[str, list[dict[str, Any]]] = {}
    pred_naive: dict[str, list[dict[str, Any]]] = {}

    target_types = ("PHONE", "IMEI", "ACCOUNT", "AMOUNT")

    for doc_id in sorted(gold_mentions.keys()):
        txt_path = firs_dir / f"{doc_id}.txt"
        with open(txt_path, "r", encoding="utf-8") as f:
            text = f.read()

        cands = find_all_identifiers(text)
        pred_rules[doc_id] = [
            {"type": c.type, "start": c.start, "end": c.end, "text": c.surface}
            for c in cands
            if c.type in target_types
        ]

        pred_naive[doc_id] = run_naive_extractor(text)

    # Score mentions
    rules_overall = score_mentions(gold_mentions, pred_rules)
    rules_by_split = score_mentions(gold_mentions, pred_rules, meta=doc_meta, group_by="split")
    rules_by_lang = score_mentions(gold_mentions, pred_rules, meta=doc_meta, group_by="language")

    naive_overall = score_mentions(gold_mentions, pred_naive)
    naive_by_split = score_mentions(gold_mentions, pred_naive, meta=doc_meta, group_by="split")
    naive_by_lang = score_mentions(gold_mentions, pred_naive, meta=doc_meta, group_by="language")

    # Serializer helper for score dicts
    def format_score_dict(sd: dict[str, Any]) -> dict[str, Any]:
        out = {}
        for k, v in sd.items():
            if k == "micro" or k in target_types:
                out[k] = {
                    "strict": {
                        "tp": v["strict"]["tp"],
                        "fp": v["strict"]["fp"],
                        "fn": v["strict"]["fn"],
                        "precision": prf(v["strict"])[0],
                        "recall": prf(v["strict"])[1],
                        "f1": prf(v["strict"])[2],
                    },
                    "lenient": {
                        "tp": v["lenient"]["tp"],
                        "fp": v["lenient"]["fp"],
                        "fn": v["lenient"]["fn"],
                        "precision": prf(v["lenient"])[0],
                        "recall": prf(v["lenient"])[1],
                        "f1": prf(v["lenient"])[2],
                    },
                }
        return out

    # Harness checks
    res_gm = score_mentions(gold_mentions, gold_mentions)
    p_gm, r_gm, f1_gm = prf(res_gm["micro"]["strict"])

    empty_m = {did: [] for did in gold_mentions}
    res_em = score_mentions(gold_mentions, empty_m)
    p_em, r_em, f1_em = prf(res_em["micro"]["strict"])

    res_gr = score_relations(gold_contracts, gold_contracts)
    p_gr, r_gr, f1_gr = prf(res_gr["relations"]["micro"])

    empty_c = {did: {"source_doc_id": did, "entities": [], "relationships": []} for did in gold_contracts}
    res_er = score_relations(gold_contracts, empty_c)
    p_er, r_er, f1_er = prf(res_er["relations"]["micro"])

    # Hashes
    firs_v5_files = [
        p for p in firs_dir.iterdir()
        if p.is_file() and p.name.startswith("FIR_") and (p.name.endswith(".txt") or p.name.endswith(".json"))
    ]
    firs_v5_combined_hash = compute_combined_sha256(firs_v5_files)

    contract_files = [
        p for p in contract_dir.iterdir()
        if p.is_file() and p.name.startswith("FIR_")
    ]
    contract_combined_hash = compute_combined_sha256(contract_files)

    input_hashes = {
        "scoring_py": compute_sha256(REPO_ROOT / "ai_pipeline" / "scoring.py"),
        "identifiers_py": compute_sha256(REPO_ROOT / "ai_pipeline" / "identifiers.py"),
        "validators_py": compute_sha256(REPO_ROOT / "ai_pipeline" / "validators.py"),
        "normalizer_py": compute_sha256(REPO_ROOT / "ai_pipeline" / "normalizer.py"),
        "test_scoring_py": compute_sha256(REPO_ROOT / "tests" / "test_scoring.py"),
        "firs_v5_index_json": compute_sha256(firs_dir / "index.json"),
        "firs_v5_combined": firs_v5_combined_hash,
        "firs_v5_contract_combined": contract_combined_hash,
    }

    # Dataset counts
    gold_type_counts: dict[str, int] = {}
    for m_list in gold_mentions.values():
        for m in m_list:
            t = m["type"]
            gold_type_counts[t] = gold_type_counts.get(t, 0) + 1

    metrics: dict[str, Any] = {
        "meta": {
            "run_id": args.run_id,
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "python_version": sys.version,
            "python_version_short": platform.python_version(),
            "command": f"python scripts/report/step5_baseline.py --run-id {args.run_id}",
            "pytest_command": pytest_cmd,
        },
        "input_hashes": input_hashes,
        "dataset_counts": {
            "total_firs": len(gold_mentions),
            "total_gold_mentions": sum(len(ml) for ml in gold_mentions.values()),
            "gold_mentions_by_type": gold_type_counts,
            "total_gold_relations": sum(len(d.get("relationships", [])) for d in gold_contracts.values()),
            "total_gold_entities": sum(len(d.get("entities", [])) for d in gold_contracts.values()),
        },
        "harness_checks": {
            "gold_mentions": {
                "tp": res_gm["micro"]["strict"]["tp"],
                "fp": res_gm["micro"]["strict"]["fp"],
                "fn": res_gm["micro"]["strict"]["fn"],
                "precision": p_gm,
                "recall": r_gm,
                "f1": f1_gm,
            },
            "empty_mentions": {
                "tp": res_em["micro"]["strict"]["tp"],
                "fp": res_em["micro"]["strict"]["fp"],
                "fn": res_em["micro"]["strict"]["fn"],
                "precision": p_em,
                "recall": r_em,
                "f1": f1_em,
            },
            "gold_relations": {
                "tp": res_gr["relations"]["micro"]["tp"],
                "fp": res_gr["relations"]["micro"]["fp"],
                "fn": res_gr["relations"]["micro"]["fn"],
                "precision": p_gr,
                "recall": r_gr,
                "f1": f1_gr,
            },
            "empty_relations": {
                "tp": res_er["relations"]["micro"]["tp"],
                "fp": res_er["relations"]["micro"]["fp"],
                "fn": res_er["relations"]["micro"]["fn"],
                "precision": p_er,
                "recall": r_er,
                "f1": f1_er,
            },
        },
        "rules_evaluation": {
            "overall": format_score_dict(rules_overall),
            "by_split": {s: format_score_dict(sd) for s, sd in rules_by_split.items()},
            "by_language": {l: format_score_dict(sd) for l, sd in rules_by_lang.items()},
        },
        "naive_evaluation": {
            "overall": format_score_dict(naive_overall),
            "by_split": {s: format_score_dict(sd) for s, sd in naive_by_split.items()},
            "by_language": {l: format_score_dict(sd) for l, sd in naive_by_lang.items()},
        },
    }

    # Write metrics.json
    metrics_file = results_dir / "metrics.json"
    with open(metrics_file, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)

    # 4. Write SHA256SUMS.txt
    files_to_hash = [pytest_raw_file, metrics_file]
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
    for fp in [pytest_raw_file, metrics_file, sha256sums_path]:
        os.chmod(fp, stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)

    # 5. Build and insert markdown block in docs/RESULTS.md
    test_file = REPO_ROOT / "tests" / "test_scoring.py"
    docstrings = extract_test_docstrings(test_file)
    pytest_tests = parse_pytest_results(raw_output, docstrings)

    step5a_md = build_markdown_section(
        run_id=args.run_id,
        metrics=metrics,
        output_hashes=output_hashes,
        pytest_tests=pytest_tests,
        pytest_cmd=pytest_cmd,
    )

    docs_file = REPO_ROOT / "docs" / "RESULTS.md"
    existing_doc = docs_file.read_text(encoding="utf-8")

    # Check for STEP1 and STEP2 hashes before modification
    m1_before = re.search(r"<!-- STEP1:BEGIN -->.*?<!-- STEP1:END -->", existing_doc, re.DOTALL)
    m2_before = re.search(r"<!-- STEP2:BEGIN -->.*?<!-- STEP2:END -->", existing_doc, re.DOTALL)
    step1_hash_before = hashlib.sha256(m1_before.group(0).encode("utf-8")).hexdigest() if m1_before else None
    step2_hash_before = hashlib.sha256(m2_before.group(0).encode("utf-8")).hexdigest() if m2_before else None

    marker_pattern = re.compile(r"<!-- STEP5A:BEGIN -->.*?<!-- STEP5A:END -->", re.DOTALL)
    if marker_pattern.search(existing_doc):
        new_doc = marker_pattern.sub(lambda _: step5a_md, existing_doc)
    else:
        if "<!-- STEP2:END -->" in existing_doc:
            parts = existing_doc.split("<!-- STEP2:END -->")
            new_doc = parts[0] + "<!-- STEP2:END -->\n\n" + step5a_md + parts[1].lstrip("\n")
        else:
            new_doc = existing_doc.rstrip() + "\n\n" + step5a_md + "\n"

    # Verify STEP1 and STEP2 blocks remain identical
    m1_after = re.search(r"<!-- STEP1:BEGIN -->.*?<!-- STEP1:END -->", new_doc, re.DOTALL)
    m2_after = re.search(r"<!-- STEP2:BEGIN -->.*?<!-- STEP2:END -->", new_doc, re.DOTALL)
    step1_hash_after = hashlib.sha256(m1_after.group(0).encode("utf-8")).hexdigest() if m1_after else None
    step2_hash_after = hashlib.sha256(m2_after.group(0).encode("utf-8")).hexdigest() if m2_after else None

    if step1_hash_before != step1_hash_after:
        raise ValueError("FATAL: STEP1 block changed during RESULTS.md update!")
    if step2_hash_before != step2_hash_after:
        raise ValueError("FATAL: STEP2 block changed during RESULTS.md update!")

    docs_file.write_text(new_doc, encoding="utf-8")
    print(f"Step 5a baseline completed successfully.")
    print(f"New folder: {results_dir}")
    print(f"STEP1 hash: {step1_hash_before}")
    print(f"STEP2 hash: {step2_hash_before}")


if __name__ == "__main__":
    main()
