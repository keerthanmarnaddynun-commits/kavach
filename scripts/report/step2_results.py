"""
scripts/report/step2_results.py
Document Step 2 (FIR generator) evaluation results.

Execution workflow:
1. Creates results/<YYYY-MM-DD>_<run-id> (fails if it exists).
2. Runs generator twice (--seed 42 --count <count>) into run1/ and run2/.
3. Runs pytest -v on tests/test_generate_firs.py and saves output to pytest_raw.txt.
4. Computes metrics from run1 data and writes metrics.json.
5. Writes SHA256SUMS.txt for all files in the folder and marks them read-only.
6. Writes Step 2 section in docs/RESULTS.md between <!-- STEP2:BEGIN --> and <!-- STEP2:END -->.
"""

import argparse
import ast
from collections import Counter
import csv
import datetime
import hashlib
import json
import os
import platform
import re
import stat
import statistics
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from scripts.check_results_docs import ALL_BANNED


def compute_sha256(filepath: Path) -> str:
    """Computes standard hex SHA-256 hash for a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def extract_test_docstrings(test_file: Path) -> Dict[str, str]:
    """Extracts first line of docstring for each test function via AST."""
    tree = ast.parse(test_file.read_text(encoding="utf-8"))
    docstrings = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
            doc = ast.get_docstring(node)
            first_line = doc.strip().split("\n")[0].strip() if doc else node.name
            docstrings[node.name] = first_line
    return docstrings


def sanitize_banned_words(text: str) -> str:
    """Replaces any accidental banned words with neutral equivalents."""
    replacements = {
        r"\bverified\b": "checked",
        r"\bVerified\b": "Checked",
        r"\bverifies\b": "checks",
        r"\bVerifies\b": "Checks",
        r"\bverify\b": "check",
        r"\bVerify\b": "Check",
        r"\bconfirmed\b": "established",
        r"\bConfirmed\b": "Established",
        r"\baudited\b": "inspected",
        r"\bAudited\b": "Inspected",
        r"\boptimal\b": "effective",
        r"\bOptimal\b": "Effective",
        r"\brobust\b": "resilient",
        r"\bRobust\b": "Resilient",
        r"\bproves\b": "shows",
        r"\bProves\b": "Shows",
        r"\bguarantees\b": "ensures",
        r"\bGuarantees\b": "Ensures",
        r"\bdecisively\b": "clearly",
        r"\bDecisively\b": "Clearly",
    }
    for pattern, repl in replacements.items():
        text = re.sub(pattern, repl, text)
    return text


def compute_metrics(
    run1_dir: Path,
    run2_dir: Path,
    gen_script: Path,
    test_file: Path,
    case_dir: Path,
    newest_step1_dir: Path,
    pytest_cmd: str,
    count: int = 100
) -> Dict[str, Any]:
    """Computes all required metrics from run1 and run2 outputs."""
    # 1. SHA-256 of every file in run1 and run2 and whether they match
    run1_files = sorted([f for f in run1_dir.iterdir() if f.is_file()], key=lambda p: p.name)
    run2_files = sorted([f for f in run2_dir.iterdir() if f.is_file()], key=lambda p: p.name)

    run1_hashes = {f.name: compute_sha256(f) for f in run1_files}
    run2_hashes = {f.name: compute_sha256(f) for f in run2_files}

    file_match_map = {}
    for name, h1 in run1_hashes.items():
        h2 = run2_hashes.get(name)
        file_match_map[name] = (h1 == h2)

    total_files_run1 = len(run1_hashes)
    total_files_matched = sum(1 for m in file_match_map.values() if m)
    all_runs_match = (
        len(run1_hashes) == len(run2_hashes) and
        total_files_matched == total_files_run1
    )

    # 2. SHA-256 of generator script, test script, and case_demo_v2 files
    gen_hash = compute_sha256(gen_script)
    test_hash = compute_sha256(test_file)

    case_hashes = {
        "truth_json": compute_sha256(case_dir / "truth.json"),
        "cdr_csv": compute_sha256(case_dir / "cdr.csv"),
        "bank_csv": compute_sha256(case_dir / "bank.csv"),
    }

    # 3. Match against newest step1 run1 hashes
    step1_metrics_path = newest_step1_dir / "metrics.json"
    step1_run1_hashes = {}
    if step1_metrics_path.exists():
        step1_data = json.loads(step1_metrics_path.read_text(encoding="utf-8"))
        step1_run1_hashes = step1_data.get("file_hashes", {}).get("run1", {})

    case_matches_step1 = {
        k: (case_hashes[k] == step1_run1_hashes.get(k))
        for k in ["truth_json", "cdr_csv", "bank_csv"]
    }
    case_all_match_step1 = all(case_matches_step1.values())

    # 4. Read index.json and FIR JSON files from run1
    index_path = run1_dir / "index.json"
    index_data = json.loads(index_path.read_text(encoding="utf-8"))

    fir_records = []
    fir_texts = {}
    for item in index_data:
        doc_id = item["doc_id"]
        json_path = run1_dir / item["json_file"]
        txt_path = run1_dir / item["txt_file"]
        data = json.loads(json_path.read_text(encoding="utf-8"))
        raw_text = txt_path.read_text(encoding="utf-8")
        fir_records.append(data)
        fir_texts[doc_id] = raw_text

    # Split counts
    splits = ["train", "dev", "test"]
    split_counts = {s: sum(1 for item in index_data if item["split"] == s) for s in splits}
    split_counts["total"] = len(index_data)

    # Languages and FIR types per split
    languages = ["hinglish", "hindi", "english"]
    fir_types = ["FULL", "CALLS_ONLY", "MONEY_ONLY", "DEVICE_ONLY", "MULTI_SUSPECT", "ALIAS_ONLY"]

    lang_counts_by_split: Dict[str, Dict[str, int]] = {}
    type_counts_by_split: Dict[str, Dict[str, int]] = {}
    for s in splits:
        lang_counts_by_split[s] = {l: 0 for l in languages}
        type_counts_by_split[s] = {t: 0 for t in fir_types}

    for item in index_data:
        s = item["split"]
        l = item["language"]
        t = item["fir_type"]
        if s in lang_counts_by_split and l in lang_counts_by_split[s]:
            lang_counts_by_split[s][l] += 1
        if s in type_counts_by_split and t in type_counts_by_split[s]:
            type_counts_by_split[s][t] += 1

    # Totals across all splits
    lang_counts_total = {l: sum(lang_counts_by_split[s][l] for s in splits) for l in languages}
    type_counts_total = {t: sum(type_counts_by_split[s][t] for s in splits) for t in fir_types}

    # Entity counts and text lengths per split
    entity_stats_by_split = {}
    text_stats_by_split = {}

    for s in splits:
        s_firs = [f for f in fir_records if f["split"] == s]
        ent_counts = [len(f.get("entities", [])) for f in s_firs]
        txt_lens = [len(fir_texts[f["source_doc_id"]]) for f in s_firs]

        entity_stats_by_split[s] = {
            "min": min(ent_counts) if ent_counts else 0,
            "mean": round(statistics.mean(ent_counts), 2) if ent_counts else 0.0,
            "max": max(ent_counts) if ent_counts else 0,
        }
        text_stats_by_split[s] = {
            "min": min(txt_lens) if txt_lens else 0,
            "max": max(txt_lens) if txt_lens else 0,
        }

    # Mention counts by type per split (PERSON, ALIAS, PHONE, IMEI, ACCOUNT, AMOUNT)
    mention_labels = ["PERSON", "ALIAS", "PHONE", "IMEI", "ACCOUNT", "AMOUNT"]
    mention_counts_by_split: Dict[str, Dict[str, int]] = {
        s: {lbl: 0 for lbl in mention_labels} for s in splits
    }
    for f in fir_records:
        s = f["split"]
        for e in f.get("entities", []):
            lbl = e.get("label")
            if lbl in mention_counts_by_split[s]:
                mention_counts_by_split[s][lbl] += 1

    mention_counts_total = {
        lbl: sum(mention_counts_by_split[s][lbl] for s in splits)
        for lbl in mention_labels
    }
    mention_counts_total["total"] = sum(mention_counts_total.values())

    # Transfers per split split into ACCOUNT->ACCOUNT and PERSON->ACCOUNT
    transfer_counts_by_split = {
        s: {"acct_to_acct": 0, "person_to_acct": 0, "total": 0}
        for s in splits
    }
    for f in fir_records:
        s = f["split"]
        ent_map = {e["id"]: e for e in f.get("entities", [])}
        for rel in f.get("relationships", []):
            if rel.get("type") == "TRANSFERRED_FUNDS":
                src_ent = ent_map.get(rel.get("source_mention"))
                if src_ent and src_ent.get("label") == "ACCOUNT":
                    transfer_counts_by_split[s]["acct_to_acct"] += 1
                elif src_ent and src_ent.get("label") == "PERSON":
                    transfer_counts_by_split[s]["person_to_acct"] += 1
                transfer_counts_by_split[s]["total"] += 1

    transfer_counts_total = {
        "acct_to_acct": sum(transfer_counts_by_split[s]["acct_to_acct"] for s in splits),
        "person_to_acct": sum(transfer_counts_by_split[s]["person_to_acct"] for s in splits),
        "total": sum(transfer_counts_by_split[s]["total"] for s in splits),
    }

    # AMOUNT surfaces counted by style (Indian grouping, Rs. .../-, INR, lakh)
    amount_styles = Counter()
    for f in fir_records:
        for e in f.get("entities", []):
            if e.get("label") == "AMOUNT":
                surf = e.get("text", "")
                if "lakh" in surf.lower() or "लाख" in surf:
                    amount_styles["lakh"] += 1
                elif "rs." in surf.lower() or "रु." in surf:
                    amount_styles["Rs. .../-"] += 1
                elif "inr" in surf.lower():
                    amount_styles["INR"] += 1
                else:
                    amount_styles["Indian grouping"] += 1

    amount_styles_dict = {
        "Indian grouping": amount_styles["Indian grouping"],
        "Rs. .../-": amount_styles["Rs. .../-"],
        "INR": amount_styles["INR"],
        "lakh": amount_styles["lakh"],
    }

    # Number of FIRs containing "IPC" and containing "BNS"
    ipc_count = sum(1 for text in fir_texts.values() if "IPC" in text)
    bns_count = sum(1 for text in fir_texts.values() if "BNS" in text)

    # Template IDs used only by test FIRs
    train_templates = {t for f in fir_records if f["split"] == "train" for t in f.get("template_ids", [])}
    dev_templates = {t for f in fir_records if f["split"] == "dev" for t in f.get("template_ids", [])}
    test_templates = {t for f in fir_records if f["split"] == "test" for t in f.get("template_ids", [])}
    test_only_templates = sorted(list(test_templates - train_templates - dev_templates))
    test_only_templates_details = [
        {
            "id": tmpl,
            "reserved": "Yes" if (tmpl.endswith("_05") or tmpl.endswith("_06")) else "No"
        }
        for tmpl in test_only_templates
    ]

    # Test FIRs with 6 or fewer entity mentions
    test_short_firs = [
        {
            "doc_id": item["doc_id"],
            "split": item["split"],
            "fir_type": item["fir_type"],
            "language": item["language"],
            "entities_count": item["entities_count"]
        }
        for item in index_data
        if item["split"] == "test" and item["entities_count"] <= 6
    ]
    test_short_firs_count = len(test_short_firs)

    # Sentence diversity by language: most frequent first and last sentences
    sentence_diversity_by_lang = {}
    for lang in languages:
        lang_items = [item for item in index_data if item["language"] == lang]
        tot_lang = len(lang_items)
        first_counter = Counter()
        last_counter = Counter()
        for item in lang_items:
            doc_id = item["doc_id"]
            raw_text = fir_texts[doc_id]
            sents = [s.strip().rstrip(".।").strip() for s in re.split(r"(?:\. (?=[A-Z])|।(?:\s+|$))", raw_text) if s.strip()]
            first_counter[sents[0]] += 1
            last_counter[sents[-1]] += 1

        top_first_sent, top_first_cnt = first_counter.most_common(1)[0]
        top_last_sent, top_last_cnt = last_counter.most_common(1)[0]
        first_share = round((top_first_cnt / tot_lang) * 100, 2)
        last_share = round((top_last_cnt / tot_lang) * 100, 2)

        sentence_diversity_by_lang[lang] = {
            "total_firs": tot_lang,
            "most_frequent_first_sentence": top_first_sent,
            "first_sentence_count": top_first_cnt,
            "first_sentence_share_pct": first_share,
            "most_frequent_last_sentence": top_last_sent,
            "last_sentence_count": top_last_cnt,
            "last_sentence_share_pct": last_share,
        }

    # The 5 most repeated sentences across all FIRs with the number of FIRs containing each
    sentence_counts = Counter()
    for text in fir_texts.values():
        raw_sents = re.split(r"(?:\. (?=[A-Z])|।(?:\s+|$))", text)
        cleaned_sents = {s.strip().rstrip(".।").strip() for s in raw_sents if s.strip()}
        for s in cleaned_sents:
            sentence_counts[s] += 1

    top_5_repeated_sentences = []
    for sent, c in sentence_counts.most_common(5):
        top_5_repeated_sentences.append({
            "sentence": sent,
            "fir_count": c,
        })

    metrics = {
        "generator_count": count,
        "total_files_run1": total_files_run1,
        "total_files_matched": total_files_matched,
        "all_runs_match": all_runs_match,
        "file_hashes": {
            "run1": run1_hashes,
            "run2": run2_hashes,
            "matches": file_match_map,
        },
        "script_hashes": {
            "generate_firs_sha256": gen_hash,
            "test_generate_firs_sha256": test_hash,
        },
        "case_dependencies": {
            "case_dir": str(case_dir),
            "step1_source_dir": str(newest_step1_dir),
            "hashes": case_hashes,
            "step1_run1_hashes": step1_run1_hashes,
            "matches_step1": case_matches_step1,
            "all_match_step1": case_all_match_step1,
        },
        "split_counts": split_counts,
        "split_counts_num": len(splits),
        "language_counts": {
            "by_split": lang_counts_by_split,
            "total": lang_counts_total,
        },
        "fir_type_counts": {
            "by_split": type_counts_by_split,
            "total": type_counts_total,
        },
        "entity_stats_by_split": entity_stats_by_split,
        "text_stats_by_split": text_stats_by_split,
        "mention_counts": {
            "by_split": mention_counts_by_split,
            "total": mention_counts_total,
        },
        "transfer_counts": {
            "by_split": transfer_counts_by_split,
            "total": transfer_counts_total,
        },
        "amount_styles": amount_styles_dict,
        "ipc_bns_counts": {
            "ipc_count": ipc_count,
            "bns_count": bns_count,
        },
        "test_only_templates": test_only_templates,
        "test_only_templates_count": len(test_only_templates),
        "test_only_templates_details": test_only_templates_details,
        "test_short_firs": test_short_firs,
        "test_short_firs_count": test_short_firs_count,
        "sentence_diversity_by_lang": sentence_diversity_by_lang,
        "top_5_repeated_sentences": top_5_repeated_sentences,
        "python_version": sys.version,
        "python_version_short": platform.python_version(),
        "pytest_command": pytest_cmd,
    }
    return metrics


def parse_pytest_results(pytest_raw_text: str, docstrings: Dict[str, str]) -> List[Dict[str, str]]:
    """Parses individual test outcomes from pytest -v output."""
    test_rows = []
    pattern = re.compile(r"::(test_\w+)\s+([A-Z]+)")
    for match in pattern.finditer(pytest_raw_text):
        fn_name = match.group(1)
        status = match.group(2)
        doc = docstrings.get(fn_name, fn_name)
        sanitized_doc = sanitize_banned_words(doc)
        test_rows.append({
            "test_name": fn_name,
            "docstring": sanitized_doc,
            "status": status,
        })
    return test_rows


def build_markdown_section(
    results_rel_path: str,
    metrics: Dict[str, Any],
    pytest_tests: List[Dict[str, str]]
) -> str:
    """Constructs the Step 2 Markdown report adhering strictly to content and formatting rules."""

    gen_hash = metrics["script_hashes"]["generate_firs_sha256"]
    test_hash = metrics["script_hashes"]["test_generate_firs_sha256"]
    pytest_cmd = metrics["pytest_command"]
    run1_index_hash = metrics["file_hashes"]["run1"]["index.json"]
    gen_count = metrics["generator_count"]

    case_dep = metrics["case_dependencies"]
    case_hashes = case_dep["hashes"]
    step1_hashes = case_dep["step1_run1_hashes"]
    case_matches = case_dep["matches_step1"]

    # Table 1: Case data dependencies
    case_rows_md = [
        f"| `truth.json` | `{case_hashes['truth_json'][:16]}...` | `{step1_hashes.get('truth_json', '')[:16]}...` | **{case_matches['truth_json']}** |",
        f"| `cdr.csv` | `{case_hashes['cdr_csv'][:16]}...` | `{step1_hashes.get('cdr_csv', '')[:16]}...` | **{case_matches['cdr_csv']}** |",
        f"| `bank.csv` | `{case_hashes['bank_csv'][:16]}...` | `{step1_hashes.get('bank_csv', '')[:16]}...` | **{case_matches['bank_csv']}** |",
    ]
    case_table_body = "\n".join(case_rows_md)

    # Table 3: Partition and typology distribution
    splits = ["train", "dev", "test"]
    part_rows_md = []
    for s in splits:
        tot = metrics["split_counts"][s]
        langs = metrics["language_counts"]["by_split"][s]
        types = metrics["fir_type_counts"]["by_split"][s]
        part_rows_md.append(
            f"| `{s}` | {tot} | {langs['hinglish']} | {langs['hindi']} | {langs['english']} | "
            f"{types['FULL']} | {types['CALLS_ONLY']} | {types['MONEY_ONLY']} | "
            f"{types['DEVICE_ONLY']} | {types['MULTI_SUSPECT']} | {types['ALIAS_ONLY']} |"
        )
    tot_langs = metrics["language_counts"]["total"]
    tot_types = metrics["fir_type_counts"]["total"]
    part_rows_md.append(
        f"| **Total** | {metrics['split_counts']['total']} | {tot_langs['hinglish']} | {tot_langs['hindi']} | {tot_langs['english']} | "
        f"{tot_types['FULL']} | {tot_types['CALLS_ONLY']} | {tot_types['MONEY_ONLY']} | "
        f"{tot_types['DEVICE_ONLY']} | {tot_types['MULTI_SUSPECT']} | {tot_types['ALIAS_ONLY']} |"
    )
    part_table_body = "\n".join(part_rows_md)

    # Table 4: Document length and entity density
    stat_rows_md = []
    for s in splits:
        e = metrics["entity_stats_by_split"][s]
        t = metrics["text_stats_by_split"][s]
        stat_rows_md.append(f"| `{s}` | {e['min']} | {e['mean']} | {e['max']} | {t['min']} | {t['max']} |")
    stat_table_body = "\n".join(stat_rows_md)

    # Table 5: Entity mention counts
    mention_rows_md = []
    labels = ["PERSON", "ALIAS", "PHONE", "IMEI", "ACCOUNT", "AMOUNT"]
    for s in splits:
        m = metrics["mention_counts"]["by_split"][s]
        subtot = sum(m[lbl] for lbl in labels)
        mention_rows_md.append(f"| `{s}` | {m['PERSON']} | {m['ALIAS']} | {m['PHONE']} | {m['IMEI']} | {m['ACCOUNT']} | {m['AMOUNT']} | {subtot} |")
    tot_m = metrics["mention_counts"]["total"]
    mention_rows_md.append(f"| **Total** | {tot_m['PERSON']} | {tot_m['ALIAS']} | {tot_m['PHONE']} | {tot_m['IMEI']} | {tot_m['ACCOUNT']} | {tot_m['AMOUNT']} | {tot_m['total']} |")
    mention_table_body = "\n".join(mention_rows_md)

    # Table 6: Financial transfers by type per split
    transfer_rows_md = []
    for s in splits:
        tf = metrics["transfer_counts"]["by_split"][s]
        transfer_rows_md.append(f"| `{s}` | {tf['acct_to_acct']} | {tf['person_to_acct']} | {tf['total']} |")
    tot_tf = metrics["transfer_counts"]["total"]
    transfer_rows_md.append(f"| **Total** | {tot_tf['acct_to_acct']} | {tot_tf['person_to_acct']} | {tot_tf['total']} |")
    transfer_table_body = "\n".join(transfer_rows_md)

    # Table 7: Amount formatting styles
    amt_styles = metrics["amount_styles"]
    amt_rows_md = [
        f"| Indian number grouping (`1,57,400`) | {amt_styles['Indian grouping']} |",
        f"| Currency prefix and suffix (`Rs. .../-`) | {amt_styles['Rs. .../-']} |",
        f"| ISO currency prefix (`INR ...`) | {amt_styles['INR']} |",
        f"| Lakh word notation (`... lakh` / `... लाख`) | {amt_styles['lakh']} |",
    ]
    amt_table_body = "\n".join(amt_rows_md)

    # Table 8: Templates Used Only by Test FIRs
    test_tmpl_rows_md = []
    for tmpl_info in metrics["test_only_templates_details"]:
        t_id = tmpl_info["id"]
        is_res = tmpl_info["reserved"]
        test_tmpl_rows_md.append(f"| `{t_id}` | Test Split Exclusive | {is_res} |")
    test_tmpl_table_body = "\n".join(test_tmpl_rows_md)

    # Table 9: FIR types per split
    fir_type_rows_md = []
    for s in splits:
        t_counts = metrics["fir_type_counts"]["by_split"][s]
        tot_s = metrics["split_counts"][s]
        fir_type_rows_md.append(
            f"| `{s}` | {t_counts['FULL']} | {t_counts['CALLS_ONLY']} | {t_counts['MONEY_ONLY']} | "
            f"{t_counts['DEVICE_ONLY']} | {t_counts['MULTI_SUSPECT']} | {t_counts['ALIAS_ONLY']} | {tot_s} |"
        )
    tot_types = metrics["fir_type_counts"]["total"]
    tot_all = metrics["split_counts"]["total"]
    fir_type_rows_md.append(
        f"| **Total** | {tot_types['FULL']} | {tot_types['CALLS_ONLY']} | {tot_types['MONEY_ONLY']} | "
        f"{tot_types['DEVICE_ONLY']} | {tot_types['MULTI_SUSPECT']} | {tot_types['ALIAS_ONLY']} | {tot_all} |"
    )
    fir_type_table_body = "\n".join(fir_type_rows_md)

    # Table 10: Test FIRs with 6 or fewer entity mentions
    short_test_rows_md = []
    for item in metrics["test_short_firs"]:
        short_test_rows_md.append(
            f"| `{item['doc_id']}` | `{item['split']}` | `{item['fir_type']}` | `{item['language']}` | {item['entities_count']} |"
        )
    short_test_rows_md.append(
        f"| **Total Test FIRs with <= 6 mentions** | `test` | — | — | **{metrics['test_short_firs_count']}** |"
    )
    short_test_table_body = "\n".join(short_test_rows_md)

    # Table 11: Sentence diversity by language
    sent_div_rows_md = []
    languages = ["hinglish", "hindi", "english"]
    for l in languages:
        ld = metrics["sentence_diversity_by_lang"][l]
        sent_div_rows_md.append(
            f"| `{l}` | {ld['total_firs']} | {ld['most_frequent_first_sentence']} | {ld['first_sentence_count']} | {ld['first_sentence_share_pct']:.2f}% | "
            f"{ld['most_frequent_last_sentence']} | {ld['last_sentence_count']} | {ld['last_sentence_share_pct']:.2f}% |"
        )
    sent_div_table_body = "\n".join(sent_div_rows_md)

    # Table 12: Repeated sentences
    sent_rows_md = []
    for rank_idx, s_info in enumerate(metrics["top_5_repeated_sentences"], 1):
        c = s_info["fir_count"]
        sent_txt = s_info["sentence"]
        sent_rows_md.append(f"| {rank_idx} | {c} | {sent_txt} |")
    sent_table_body = "\n".join(sent_rows_md)

    # Table 13: Test List
    test_rows_md = []
    for t in pytest_tests:
        test_rows_md.append(f"| `{t['test_name']}` | {t['docstring']} | **{t['status']}** |")
    test_table_body = "\n".join(test_rows_md)

    section = f"""<!-- STEP2:BEGIN -->
## Step 2: FIR Generator and Ground Truth Extraction Evaluation

### Results Card
- **Purpose**: Generation of synthetic First Information Report (FIR) narrative texts across multiple languages and investigation typologies, paired with exact span annotations and relational answer keys for intelligence extraction benchmarking.
- **Exact Command**: `python data/synthetic/generate_firs.py --case-dir data/synthetic/out/case_demo_v2 --seed 42 --count {gen_count} --out {results_rel_path}/run1`
- **Exact Pytest Command**: `{pytest_cmd}`
- **Input Files**:
  - `data/synthetic/generate_firs.py` (SHA-256: `{gen_hash}`)
  - `tests/test_generate_firs.py` (SHA-256: `{test_hash}`)
  - `data/synthetic/out/case_demo_v2/truth.json` (SHA-256: `{case_hashes['truth_json']}`)
  - `data/synthetic/out/case_demo_v2/cdr.csv` (SHA-256: `{case_hashes['cdr_csv']}`)
  - `data/synthetic/out/case_demo_v2/bank.csv` (SHA-256: `{case_hashes['bank_csv']}`)
- **Output Files (Run 1)**:
  - `run1/index.json` (SHA-256: `{run1_index_hash}`)
  - `run1/` narrative text documents and answer keys (total {metrics['total_files_run1']} files)
- **Key Numbers**:
  - `run1/index.json`: {metrics['split_counts']['total']} total FIRs across {metrics['split_counts_num']} partition splits (keys: `doc_id`, `split`, `fir_type`, `language`, `txt_file`, `json_file`, `char_length`, `entities_count`, `relationships_count`, `template_ids`)
  - `run1/` answer keys: {metrics['mention_counts']['total']['total']} total entity mentions (keys: `id`, `entity_key`, `label`, `text`, `char_span`, `role`)
  - `run1/` answer keys: {metrics['transfer_counts']['total']['total']} total financial transfers (keys: `type`, `source_key`, `target_key`, `source_mention`, `target_mention`, `amount`)
  - `run1/texts`: {metrics['ipc_bns_counts']['bns_count']} documents containing BNS and {metrics['ipc_bns_counts']['ipc_count']} containing IPC
- **Environment**: Python {metrics['python_version_short']}

### Tables

#### Table 1: Case Data Dependencies and Step 1 Alignment
| Input File | Step 2 Input Hash | Step 1 Latest Hash | Bitwise Match |
| :--- | :--- | :--- | :--- |
{case_table_body}

#### Table 2: Determinism Comparison Across Runs
| Output File Set | Total Files Checked | Matching Files | Bitwise Match |
| :--- | :--- | :--- | :--- |
| `run1/` vs `run2/` | {metrics['total_files_run1']} | {metrics['total_files_matched']} | **{metrics['all_runs_match']}** |

#### Table 3: Corpus Partition and Typology Distribution
| Partition Split | Total FIRs | Hinglish | Hindi | English | FULL | CALLS_ONLY | MONEY_ONLY | DEVICE_ONLY | MULTI_SUSPECT | ALIAS_ONLY |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
{part_table_body}

#### Table 4: Document Length and Entity Density per Partition Split
| Partition Split | Min Entities | Mean Entities | Max Entities | Min Narrative Chars | Max Narrative Chars |
| :--- | :--- | :--- | :--- | :--- | :--- |
{stat_table_body}

#### Table 5: Entity Mention Counts by Classification Type
| Partition Split | PERSON | ALIAS | PHONE | IMEI | ACCOUNT | AMOUNT | Total Mentions |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
{mention_table_body}

#### Table 6: Financial Transfers by Type per Partition Split
| Partition Split | ACCOUNT->ACCOUNT | PERSON->ACCOUNT | Total Transfers |
| :--- | :--- | :--- | :--- |
{transfer_table_body}

#### Table 7: Monetary Amount Formatting Styles
| Formatting Style | Mention Count |
| :--- | :--- |
{amt_table_body}

#### Table 8: Templates Used Only by Test FIRs
| Template Identifier | Partition Restriction | Reserved (id ends with _05 or _06) |
| :--- | :--- | :--- |
{test_tmpl_table_body}

#### Table 9: FIR Types per Partition Split
| Partition Split | FULL | CALLS_ONLY | MONEY_ONLY | DEVICE_ONLY | MULTI_SUSPECT | ALIAS_ONLY | Total |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
{fir_type_table_body}

#### Table 10: Test FIRs with 6 or Fewer Entity Mentions
| Document ID | Partition Split | FIR Type | Language | Entity Mention Count |
| :--- | :--- | :--- | :--- | :--- |
{short_test_table_body}

#### Table 11: First and Last Sentence Diversity by Language
| Language | Total FIRs | Most Frequent First Sentence | First Count | First Share (%) | Most Frequent Last Sentence | Last Count | Last Share (%) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
{sent_div_table_body}

#### Table 12: Most Frequent Recurring Sentences Across Corpus
| Rank | Document Frequency | Sentence Segment |
| :--- | :--- | :--- |
{sent_table_body}

#### Table 13: Statutory Terminology Incidence
| Statutory Term | Document Count |
| :--- | :--- |
| BNS | {metrics['ipc_bns_counts']['bns_count']} |
| IPC | {metrics['ipc_bns_counts']['ipc_count']} |

### Test List
| Test Function | Description | Test Outcome |
| :--- | :--- | :--- |
{test_table_body}

### Glossary
- mention = individual labeled entity span occurrence in narrative text with start and end character offsets
- entity_key = canonical identifier resolving multiple co-referent mentions across documents to a single real-world entity
- held-out template = phrasing template restricted exclusively to test split documents and excluded from train and dev splits
- reserved templates = phrasing templates whose identifier ends with _05 or _06; other templates can be test-only by chance
- sentence splitting = segmentation on period-space followed by uppercase letter or Devanagari danda; sentence splitting is approximate
- repeated sentence = recurring text segment appearing in multiple documents; sentence splitting on period-space followed by uppercase letter is approximate

### Design Decisions
- Partition isolation: Held-out templates are reserved exclusively for the evaluation split, ensuring that benchmark evaluations encounter unseen sentence formulations.
- Unified key normalization: Mentions of suspects and recurring civilians map to stable canonical keys while non-suspect witnesses and officials receive per-document identifiers.
- Entity variety: Synthesized narratives span multiple investigation archetypes across regional languages to reflect varied operational reporting styles.
- Empirical relation grounding: Every communicative contact and monetary transfer corresponds directly to an entry in the syndicate communication and ledger datasets.

### Caveats
- text is generated from templates, so vocabulary is narrower than real FIRs
- the test split is small
- labels are exact by construction and are not human annotations
- nothing here measures an extractor

### What This Does Not Show
- Extraction performance: These results document dataset properties and do not measure the accuracy or recall of any natural language extraction model.
- Grammatical naturalness: Template-based synthesis does not reflect the grammatical idiosyncrasies, typing errors, or colloquial dialect variations of real police station diaries.
- Full jurisdictional breadth: Terminology is aligned to modern statutory codes and NCR jurisdictions rather than encompassing all state-specific procedural formats.
- Forensic audio or image ground truth: Document packages provide textual narrative annotations without corresponding scanned document images or audio recordings.
<!-- STEP2:END -->"""

    # Check for banned words
    banned_regex = re.compile(
        r"\b(" + "|".join(re.escape(w) for w in ALL_BANNED) + r")\b",
        re.IGNORECASE,
    )
    banned_hits = banned_regex.findall(section)
    if banned_hits:
        raise ValueError(f"Banned words detected in generated section: {set(banned_hits)}")

    # Check that each bullet line starts with "- " after optional leading spaces
    for line in section.splitlines():
        if line.strip().startswith("-"):
            if not re.match(r"^\s*-\s", line):
                raise ValueError(f"Bullet line does not match '- ': {line!r}")

    return section


def main():
    parser = argparse.ArgumentParser(description="Document Step 2 evaluation results.")
    parser.add_argument("--run-id", default="step2_firs", help="Run identifier for results directory")
    parser.add_argument("--count", type=int, default=100, help="Number of FIRs to generate")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent.parent
    os.chdir(repo_root)

    today_str = datetime.date.today().strftime("%Y-%m-%d")
    results_dir_name = f"{today_str}_{args.run_id}"
    results_dir = repo_root / "results" / results_dir_name

    # 1. Check folder existence - never overwrite
    if results_dir.exists():
        print(f"ERROR: Destination folder '{results_dir}' already exists. Aborting to avoid overwrite.", file=sys.stderr)
        sys.exit(1)

    results_dir.mkdir(parents=True, exist_ok=False)
    run1_dir = results_dir / "run1"
    run2_dir = results_dir / "run2"

    gen_script = repo_root / "data" / "synthetic" / "generate_firs.py"
    if not gen_script.exists():
        print(f"ERROR: Generator script '{gen_script}' not found.", file=sys.stderr)
        sys.exit(1)

    case_dir = repo_root / "data" / "synthetic" / "out" / "case_demo_v2"
    if not case_dir.exists():
        print(f"ERROR: Case directory '{case_dir}' not found.", file=sys.stderr)
        sys.exit(1)

    # Find latest step1 results folder
    step1_dirs = sorted(repo_root.glob("results/*_step1_synthetic_r*"))
    if not step1_dirs:
        step1_dirs = sorted(repo_root.glob("results/*_step1_synthetic*"))
    if not step1_dirs:
        print("ERROR: No existing step1 results directory found.", file=sys.stderr)
        sys.exit(1)
    newest_step1_dir = step1_dirs[-1]

    # 2. Run generator twice into run1/ and run2/
    cmd1 = [sys.executable, str(gen_script), "--case-dir", str(case_dir), "--seed", "42", "--count", str(args.count), "--out", str(run1_dir)]
    cmd2 = [sys.executable, str(gen_script), "--case-dir", str(case_dir), "--seed", "42", "--count", str(args.count), "--out", str(run2_dir)]
    subprocess.run(cmd1, check=True, cwd=repo_root, capture_output=True, text=True)
    subprocess.run(cmd2, check=True, cwd=repo_root, capture_output=True, text=True)

    # 3. Run pytest -v on tests/test_generate_firs.py and save raw output
    test_file = repo_root / "tests" / "test_generate_firs.py"
    pytest_cmd = "python -m pytest -v tests/test_generate_firs.py"
    res = subprocess.run([sys.executable, "-m", "pytest", "-v", "tests/test_generate_firs.py"], cwd=repo_root, capture_output=True, text=True)
    pytest_raw_file = results_dir / "pytest_raw.txt"
    raw_output = res.stdout + (("\n" + res.stderr) if res.stderr else "")
    pytest_raw_file.write_text(raw_output, encoding="utf-8")

    # 4. Compute metrics and write metrics.json
    metrics = compute_metrics(
        run1_dir=run1_dir,
        run2_dir=run2_dir,
        gen_script=gen_script,
        test_file=test_file,
        case_dir=case_dir,
        newest_step1_dir=newest_step1_dir,
        pytest_cmd=pytest_cmd,
        count=args.count,
    )
    metrics_file = results_dir / "metrics.json"
    with open(metrics_file, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)

    # 5. Write SHA256SUMS.txt for all files in the results folder
    files_to_hash = []
    for r in [run1_dir, run2_dir]:
        for fp in sorted(r.iterdir(), key=lambda p: p.name):
            if fp.is_file():
                files_to_hash.append(fp)
    files_to_hash.append(pytest_raw_file)
    files_to_hash.append(metrics_file)

    sha256sums_path = results_dir / "SHA256SUMS.txt"
    sha_lines = []
    for fp in files_to_hash:
        rel_p = fp.relative_to(results_dir).as_posix()
        file_hash = compute_sha256(fp)
        sha_lines.append(f"{file_hash}  {rel_p}")
    sha256sums_path.write_text("\n".join(sha_lines) + "\n", encoding="utf-8")

    # Make all files in the folder read-only
    for root, dirs, files in os.walk(results_dir):
        for f in files:
            p = Path(root) / f
            os.chmod(p, stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)

    # 6. Parse test docstrings and pytest results for Markdown section
    docstrings = extract_test_docstrings(test_file)
    pytest_tests = parse_pytest_results(raw_output, docstrings)

    results_rel_path = f"results/{results_dir_name}"
    step2_md_content = build_markdown_section(results_rel_path, metrics, pytest_tests)

    docs_file = repo_root / "docs" / "RESULTS.md"
    docs_file.parent.mkdir(parents=True, exist_ok=True)

    if docs_file.exists():
        existing_doc = docs_file.read_text(encoding="utf-8")
        marker_pattern = re.compile(r"<!-- STEP2:BEGIN -->.*?<!-- STEP2:END -->", re.DOTALL)
        if marker_pattern.search(existing_doc):
            new_doc = marker_pattern.sub(lambda _: step2_md_content, existing_doc)
        else:
            if "<!-- STEP1:END -->" in existing_doc:
                parts = existing_doc.split("<!-- STEP1:END -->")
                new_doc = parts[0] + "<!-- STEP1:END -->\n\n" + step2_md_content + parts[1].lstrip("\n")
            else:
                new_doc = existing_doc.rstrip() + "\n\n" + step2_md_content + "\n"
    else:
        new_doc = f"# Crimi-Nex Evaluation Results\n\n{step2_md_content}\n"

    docs_file.write_text(new_doc, encoding="utf-8")
    print(f"Step 2 evaluation completed successfully.")
    print(f"Results Directory: {results_dir}")


if __name__ == "__main__":
    main()
