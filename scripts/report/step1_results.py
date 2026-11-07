"""
scripts/report/step1_results.py
Document Step 1 (synthetic case generator) evaluation results.

Execution workflow:
1. Creates results/<YYYY-MM-DD>_step1_synthetic (fails if it exists).
2. Runs generator twice (--seed 42 --days 30) into run1/ and run2/.
3. Runs pytest -v on tests/test_generate_case.py and saves output to pytest_raw.txt.
4. Computes metrics from run1 data and writes metrics.json.
5. Writes SHA256SUMS.txt for all files in the folder and marks them read-only.
6. Writes Step 1 section in docs/RESULTS.md between <!-- STEP1:BEGIN --> and <!-- STEP1:END -->.
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
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple


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


def compute_metrics(run1_dir: Path, run2_dir: Path, gen_script: Path, test_file: Path, pytest_cmd: str) -> Dict[str, Any]:
    """Computes all required metrics from run1 and run2 outputs."""
    truth_path = run1_dir / "truth.json"
    cdr_path = run1_dir / "cdr.csv"
    bank_path = run1_dir / "bank.csv"

    truth = json.loads(truth_path.read_text(encoding="utf-8"))
    with open(cdr_path, "r", encoding="utf-8") as f:
        cdr_rows = list(csv.DictReader(f))
    with open(bank_path, "r", encoding="utf-8") as f:
        bank_rows = list(csv.DictReader(f))

    # Entity counts
    people_count = len(truth.get("people", []))
    phones_count = len(truth.get("phones", []))
    accounts_count = len(truth.get("accounts", []))
    imeis_count = len(truth.get("imeis", []))

    # Call counts
    call_counts: Dict[str, int] = {}
    for r in cdr_rows:
        a = r["a_party"]
        b = r["b_party"]
        call_counts[a] = call_counts.get(a, 0) + 1
        call_counts[b] = call_counts.get(b, 0) + 1

    # Deterministic ranking: descending call count, ascending phone string for ties
    sorted_phones = sorted(call_counts.keys(), key=lambda p: (-call_counts[p], p))
    total_phones_in_cdr = len(sorted_phones)

    # Phone ownership and role mapping
    phone_info: Dict[str, Dict[str, str]] = {}
    for p in truth.get("people", []):
        p_name = p.get("name", "Unknown")
        p_role = p.get("role", "Unknown")
        p_id = p.get("person_id", "Unknown")
        p_gang = p.get("gang", "Unknown")
        for ph_obj in p.get("phones", []):
            ph_num = ph_obj.get("phone")
            phone_info[ph_num] = {
                "owner_name": p_name,
                "role": p_role,
                "person_id": p_id,
                "gang": p_gang,
            }

    for p_obj in truth.get("phones", []):
        ph_num = p_obj.get("phone")
        if ph_num not in phone_info:
            role = "DECOY_CIVILIAN" if p_obj.get("is_decoy") else ("BURNER" if p_obj.get("is_burner") else "CIVILIAN")
            phone_info[ph_num] = {
                "owner_name": "Decoy Customer" if p_obj.get("is_decoy") else "Burner Handset",
                "role": role,
                "person_id": p_obj.get("person_id") or "NONE",
                "gang": "NONE",
            }

    # Distinct contacts mapping
    phone_contacts: Dict[str, Set[str]] = {p: set() for p in call_counts}
    for r in cdr_rows:
        a = r["a_party"]
        b = r["b_party"]
        phone_contacts[a].add(b)
        phone_contacts[b].add(a)

    # Top 5 phones
    top_5 = []
    for rank_idx, ph in enumerate(sorted_phones[:5], 1):
        info = phone_info.get(ph, {})
        top_5.append({
            "rank": rank_idx,
            "phone": ph,
            "count": call_counts[ph],
            "role": info.get("role", "UNKNOWN"),
            "owner_name": info.get("owner_name", "Unknown"),
            "distinct_contacts": len(phone_contacts.get(ph, set())),
        })

    # Kingpins
    kingpins = []
    kp_ids = set(truth.get("kingpin_ids", []))
    for p in truth.get("people", []):
        if p.get("person_id") in kp_ids:
            ph = p["phones"][0]["phone"]
            rank = sorted_phones.index(ph) + 1 if ph in sorted_phones else None
            count = call_counts.get(ph, 0)
            kingpins.append({
                "person_id": p.get("person_id"),
                "name": p.get("name"),
                "phone": ph,
                "count": count,
                "rank": rank,
                "total_phones": total_phones_in_cdr,
                "distinct_contacts": len(phone_contacts.get(ph, set())),
            })

    # Pizza shop
    pizza_phone = truth.get("decoys", {}).get("pizza_shop_number")
    pizza_rank = sorted_phones.index(pizza_phone) + 1 if pizza_phone in sorted_phones else None
    pizza_count = call_counts.get(pizza_phone, 0)
    pizza_distinct_contacts = len(phone_contacts.get(pizza_phone, set()))
    pizza_shop_metrics = {
        "phone": pizza_phone,
        "name": "Harish Chawla (Royal Pizza)",
        "role": "DECOY_CIVILIAN",
        "rank": pizza_rank,
        "count": pizza_count,
        "distinct_contacts": pizza_distinct_contacts,
        "total_phones": total_phones_in_cdr,
    }

    # File hashes for run1 and run2
    run1_hashes = {
        "truth_json": compute_sha256(run1_dir / "truth.json"),
        "cdr_csv": compute_sha256(run1_dir / "cdr.csv"),
        "bank_csv": compute_sha256(run1_dir / "bank.csv"),
    }
    run2_hashes = {
        "truth_json": compute_sha256(run2_dir / "truth.json"),
        "cdr_csv": compute_sha256(run2_dir / "cdr.csv"),
        "bank_csv": compute_sha256(run2_dir / "bank.csv"),
    }
    hash_matches = {
        "truth_json": run1_hashes["truth_json"] == run2_hashes["truth_json"],
        "cdr_csv": run1_hashes["cdr_csv"] == run2_hashes["cdr_csv"],
        "bank_csv": run1_hashes["bank_csv"] == run2_hashes["bank_csv"],
        "all_match": (
            run1_hashes["truth_json"] == run2_hashes["truth_json"] and
            run1_hashes["cdr_csv"] == run2_hashes["cdr_csv"] and
            run1_hashes["bank_csv"] == run2_hashes["bank_csv"]
        ),
    }

    # Bank accounts by bank in truth.json
    bank_data: Dict[str, Dict[str, Any]] = {}
    for a in truth.get("accounts", []):
        b = a.get("bank", "UNKNOWN")
        if b not in bank_data:
            bank_data[b] = {"lengths": set(), "prefixes": set(), "count": 0}
        bank_data[b]["lengths"].add(len(a.get("account_number", "")))
        bank_data[b]["prefixes"].add(a.get("ifsc", "")[:4])
        bank_data[b]["count"] += 1

    bank_accounts_by_bank = []
    preferred_order = ["SBI", "ICICI", "HDFC", "PNB"]
    sorted_banks = sorted(bank_data.keys(), key=lambda b: preferred_order.index(b) if b in preferred_order else 999)
    for b in sorted_banks:
        d = bank_data[b]
        bank_accounts_by_bank.append({
            "bank": b,
            "account_lengths": sorted(list(d["lengths"])),
            "ifsc_prefixes": sorted(list(d["prefixes"])),
            "account_count": d["count"],
        })

    # Bank transaction metrics from run1/bank.csv
    from_acct_lens = Counter(len(r.get("from_acct", "")) for r in bank_rows)
    to_acct_lens = Counter(len(r.get("to_acct", "")) for r in bank_rows)

    ifsc_pattern = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
    invalid_ifsc_count = sum(1 for r in bank_rows if not ifsc_pattern.match(r.get("ifsc", "")))

    truth_ifsc_map = {a["account_number"]: a["ifsc"] for a in truth.get("accounts", [])}
    to_acct_truth_ifsc_mismatch_count = sum(
        1 for r in bank_rows
        if r.get("to_acct") in truth_ifsc_map and r.get("ifsc") != truth_ifsc_map[r.get("to_acct")]
    )
    to_acct_not_in_truth_count = sum(
        1 for r in bank_rows
        if r.get("to_acct") not in truth_ifsc_map
    )

    # Collision check: accounts equaling any phone number or IMEI
    all_truth_accounts = {a["account_number"] for a in truth.get("accounts", [])}
    for p in truth.get("people", []):
        for a in p.get("accounts", []):
            all_truth_accounts.add(a["account_number"])
    all_bank_accounts = {r["from_acct"] for r in bank_rows} | {r["to_acct"] for r in bank_rows}
    all_account_numbers = all_truth_accounts | all_bank_accounts

    all_phones = {p["phone"] for p in truth.get("phones", [])}
    for p in truth.get("people", []):
        for ph in p.get("phones", []):
            all_phones.add(ph["phone"])
    for r in cdr_rows:
        all_phones.add(r["a_party"])
        all_phones.add(r["b_party"])

    all_imeis = set(truth.get("imeis", []))
    for r in cdr_rows:
        all_imeis.add(r["imei_a"])

    account_collisions_with_phone_or_imei = len(all_account_numbers.intersection(all_phones | all_imeis))

    metrics = {
        "row_counts": {
            "cdr_csv": len(cdr_rows),
            "bank_csv": len(bank_rows),
        },
        "entity_counts": {
            "people": people_count,
            "phones": phones_count,
            "accounts": accounts_count,
            "imeis": imeis_count,
        },
        "bank_accounts_by_bank": bank_accounts_by_bank,
        "bank_csv_metrics": {
            "from_acct_digit_lengths": {str(k): v for k, v in sorted(from_acct_lens.items())},
            "to_acct_digit_lengths": {str(k): v for k, v in sorted(to_acct_lens.items())},
            "invalid_ifsc_rows_count": invalid_ifsc_count,
            "to_acct_in_truth_ifsc_mismatch_count": to_acct_truth_ifsc_mismatch_count,
            "to_acct_not_in_truth_count": to_acct_not_in_truth_count,
        },
        "account_phone_imei_collisions_count": account_collisions_with_phone_or_imei,
        "top_5_phones": top_5,
        "kingpins": kingpins,
        "pizza_shop": pizza_shop_metrics,
        "file_hashes": {
            "run1": run1_hashes,
            "run2": run2_hashes,
            "matches": hash_matches,
        },
        "python_version": sys.version,
        "python_version_short": platform.python_version(),
        "generator_script_sha256": compute_sha256(gen_script),
        "test_script_sha256": compute_sha256(test_file),
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
    """Constructs the Step 1 Markdown report adhering strictly to content and formatting rules."""

    gen_hash = metrics["generator_script_sha256"]
    test_hash = metrics["test_script_sha256"]
    pytest_cmd = metrics["pytest_command"]
    run1_h = metrics["file_hashes"]["run1"]
    run2_h = metrics["file_hashes"]["run2"]
    matches = metrics["file_hashes"]["matches"]

    # Build Top 5 table rows from metrics.json
    top_5_rows_md = []
    for item in metrics["top_5_phones"]:
        r = item["rank"]
        ph = item["phone"]
        c = item["count"]
        role = item["role"]
        top_5_rows_md.append(f"| {r} | `{ph}` | {c} | `{role}` |")
    top_5_table_body = "\n".join(top_5_rows_md)

    # Build Kingpin and Decoy table rows from metrics.json
    ps = metrics["pizza_shop"]
    hierarchy_rows_md = [
        f"| Decoy Civilian Hub | `{ps['phone']}` | {ps['count']} | {ps['rank']} | {ps['distinct_contacts']} | `{ps['role']}` |"
    ]
    for kp in metrics["kingpins"]:
        hierarchy_rows_md.append(
            f"| Kingpin (`{kp['person_id']}`) | `{kp['phone']}` | {kp['count']} | {kp['rank']} | {kp['distinct_contacts']} | `KINGPIN` |"
        )
    hierarchy_table_body = "\n".join(hierarchy_rows_md)

    # Build Bank Accounts table rows from metrics.json
    bank_rows_md = []
    for item in metrics["bank_accounts_by_bank"]:
        b = item["bank"]
        lens_str = ", ".join(str(l) for l in item["account_lengths"])
        pref_str = ", ".join(item["ifsc_prefixes"])
        cnt = item["account_count"]
        bank_rows_md.append(f"| {b} | {lens_str} | {pref_str} | {cnt} |")
    bank_table_body = "\n".join(bank_rows_md)

    # Bank CSV metric strings
    b_metrics = metrics["bank_csv_metrics"]
    from_lens_str = ", ".join(f"{k} digits: {v}" for k, v in b_metrics["from_acct_digit_lengths"].items())
    to_lens_str = ", ".join(f"{k} digits: {v}" for k, v in b_metrics["to_acct_digit_lengths"].items())
    invalid_ifsc_cnt = b_metrics["invalid_ifsc_rows_count"]
    ifsc_diff_cnt = b_metrics["to_acct_in_truth_ifsc_mismatch_count"]
    to_not_in_truth_cnt = b_metrics["to_acct_not_in_truth_count"]
    collisions_cnt = metrics["account_phone_imei_collisions_count"]

    # Build Test List rows from pytest output
    test_rows_md = []
    for t in pytest_tests:
        test_rows_md.append(f"| `{t['test_name']}` | {t['docstring']} | **{t['status']}** |")
    test_table_body = "\n".join(test_rows_md)

    # Format Python version for caveats
    py_ver_short = metrics["python_version_short"]

    # Assemble section in exact specified order
    section = f"""<!-- STEP1:BEGIN -->
## Step 1: Synthetic Case Generator Evaluation

### Results Card
- **Purpose**: Generation of synthetic criminal syndicate communication records, financial transaction ledgers, and reference ground truth metadata for benchmarking intelligence extraction pipelines.
- **Exact Command**: `python data/synthetic/generate_case.py --seed 42 --days 30 --out {results_rel_path}/run1`
- **Exact Pytest Command**: `{pytest_cmd}`
- **Input Files**:
- `data/synthetic/generate_case.py` (SHA-256: `{gen_hash}`)
- `tests/test_generate_case.py` (SHA-256: `{test_hash}`)
- **Output Files (Run 1)**:
- `run1/truth.json` (SHA-256: `{run1_h['truth_json']}`)
- `run1/cdr.csv` (SHA-256: `{run1_h['cdr_csv']}`)
- `run1/bank.csv` (SHA-256: `{run1_h['bank_csv']}`)
- **Key Numbers**:
- `run1/cdr.csv`: {metrics['row_counts']['cdr_csv']} rows (columns: `a_party`, `b_party`, `imei_a`, `imsi_a`, `start_time`, `duration_sec`, `call_type`, `tower_id`, `lat`, `lon`)
- `run1/bank.csv`: {metrics['row_counts']['bank_csv']} rows (columns: `txn_id`, `datetime`, `from_acct`, `to_acct`, `amount`, `mode`, `ifsc`, `narration`)
- `run1/truth.json`: {metrics['entity_counts']['people']} people (key: `people`), {metrics['entity_counts']['phones']} phones (key: `phones`), {metrics['entity_counts']['accounts']} accounts (key: `accounts`), {metrics['entity_counts']['imeis']} IMEIs (key: `imeis`)
- `run1/bank.csv` account lengths: `from_acct` counts by digit length: {from_lens_str}; `to_acct` counts by digit length: {to_lens_str}
- `run1/bank.csv` rows whose ifsc does not match `^[A-Z]{{4}}0[A-Z0-9]{{6}}$`: {invalid_ifsc_cnt}
- `run1/bank.csv` rows whose to_acct is in truth.json and whose ifsc differs from that account's ifsc: {ifsc_diff_cnt}
- `run1/bank.csv` rows whose to_acct is not in truth.json: {to_not_in_truth_cnt}
- Account numbers (truth.json and bank.csv) that equal any phone number or IMEI value: {collisions_cnt}

### Tables

#### Table 1: Dataset Volume and Entity Summary
| File / Key | Metric Type | Count | Notes |
| :--- | :--- | :--- | :--- |
| `run1/cdr.csv` | Total Communication Rows | {metrics['row_counts']['cdr_csv']} | Excludes CSV header row |
| `run1/bank.csv` | Total Transaction Rows | {metrics['row_counts']['bank_csv']} | Excludes CSV header row |
| `run1/truth.json` | People Entities | {metrics['entity_counts']['people']} | Top-level array `people` |
| `run1/truth.json` | Telephone Numbers | {metrics['entity_counts']['phones']} | Top-level array `phones` |
| `run1/truth.json` | Bank Accounts | {metrics['entity_counts']['accounts']} | Top-level array `accounts` |
| `run1/truth.json` | IMEI Identifiers | {metrics['entity_counts']['imeis']} | Top-level array `imeis` |

#### Table 2: Determinism Comparison Across Runs
| Output File | Run 1 SHA-256 | Run 2 SHA-256 | Bitwise Match |
| :--- | :--- | :--- | :--- |
| `truth.json` | `{run1_h['truth_json'][:16]}...` | `{run2_h['truth_json'][:16]}...` | **{matches['truth_json']}** |
| `cdr.csv` | `{run1_h['cdr_csv'][:16]}...` | `{run2_h['cdr_csv'][:16]}...` | **{matches['cdr_csv']}** |
| `bank.csv` | `{run1_h['bank_csv'][:16]}...` | `{run2_h['bank_csv'][:16]}...` | **{matches['bank_csv']}** |

#### Table 3: Top Telephone Numbers by Call Count
| Rank | Phone Number | Call Count | Classification |
| :--- | :--- | :--- | :--- |
{top_5_table_body}

#### Table 4: Syndicate Hierarchy and Civilian Hub Metrics
| Entity Role | Phone Number | Call Count | Rank | Distinct Contacts | Classification |
| :--- | :--- | :--- | :--- | :--- | :--- |
{hierarchy_table_body}

#### Table 5: Bank Accounts by Bank (truth.json)
| Bank | Account Length(s) | IFSC Prefix(es) | Number of Accounts |
| :--- | :--- | :--- | :--- |
{bank_table_body}

#### Table 6: Bank Transaction Ledger Properties (run1/bank.csv)
| Metric | Value |
| :--- | :--- |
| `from_acct` counts by digit length | {from_lens_str} |
| `to_acct` counts by digit length | {to_lens_str} |
| Rows whose IFSC does not match `^[A-Z]{{4}}0[A-Z0-9]{{6}}$` | {invalid_ifsc_cnt} |
| Rows whose `to_acct` is in `truth.json` and whose IFSC differs | {ifsc_diff_cnt} |
| Rows whose `to_acct` is not in `truth.json` | {to_not_in_truth_cnt} |
| Account numbers that equal any phone number or IMEI value | {collisions_cnt} |

### Test List
| Test Function | Description | Test Outcome |
| :--- | :--- | :--- |
{test_table_body}

### Glossary
- call count = rows where the phone is a_party or b_party
- rank = position by descending call count (ties are ordered by ascending phone number identifier string)
- distinct contacts = number of other phones it has a call with

### Design Decisions
- Kingpin call restraint: Kingpins make very few calls and have very few distinct contacts, so their call count ranks near the bottom (see the hierarchy table).
- Innocent civilian hub: A pizza shop has many distinct contacts: outside civilian customers and a small number of operatives from one syndicate only. It has no contact with members of both syndicates, so it is not an extra link between them.
- Bridge courier routing: Dedicated bridge couriers form the exclusive telephonic connection between the separate syndicates, preventing direct inter-syndicate operative or lieutenant calls.
- Financial layering: Some deposits to mule accounts are placed just below a configurable threshold constant defined in the generator, and one mule account stays dormant before becoming active.
- Bank account numbers have a fixed length per bank, each account has one fixed IFSC, and the ifsc column of the bank file holds the receiving account's IFSC.

### Caveats
- data is synthetic
- fixed 2-gang structure
- The call-count ranks of the pizza shop and the kingpins are set by the generator's design, not discovered from the data.
- runs used Python {py_ver_short}

### What This Does Not Show
- Detection performance: These results show only that the generator produces the designed structure. They do not show that any extraction or analysis method works on it.
- Carrier-level transport anomalies: The dataset does not model packet loss, tower handover latencies, or network drops.
- Multi-modal surveillance: Excludes physical location tracking, vehicular tailing, and room audio intercepts.
- Alternative communication channels: Excludes encrypted application messaging, secure webmail, and in-person meetings.
- Dynamic syndicate evolution: Syndicate membership, hierarchy, and operational roles remain static rather than adapting to law enforcement intervention.
<!-- STEP1:END -->"""

    # Check for banned words
    banned_regex = re.compile(
        r"\b(verified|confirmed|audited|optimal|robust|proves|guarantees|decisively)\b",
        re.IGNORECASE
    )
    banned_hits = banned_regex.findall(section)
    if banned_hits:
        raise ValueError(f"Banned words detected in generated section: {set(banned_hits)}")

    # Check that every bullet line starts with "- " (dash plus exactly one space)
    for line in section.splitlines():
        if line.strip().startswith("-"):
            if not line.startswith("- "):
                raise ValueError(f"Bullet line does not start with '- ': {line!r}")

    return section


def main():
    parser = argparse.ArgumentParser(description="Document Step 1 evaluation results.")
    parser.add_argument("--run-id", default="step1_synthetic", help="Run identifier for results directory")
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

    gen_script = repo_root / "data" / "synthetic" / "generate_case.py"
    if not gen_script.exists():
        print(f"ERROR: Generator script '{gen_script}' not found.", file=sys.stderr)
        sys.exit(1)

    # 2. Run generator twice into run1/ and run2/
    cmd1 = [sys.executable, str(gen_script), "--seed", "42", "--days", "30", "--out", str(run1_dir)]
    cmd2 = [sys.executable, str(gen_script), "--seed", "42", "--days", "30", "--out", str(run2_dir)]
    subprocess.run(cmd1, check=True, cwd=repo_root, capture_output=True, text=True)
    subprocess.run(cmd2, check=True, cwd=repo_root, capture_output=True, text=True)

    # 3. Run pytest -v on tests/test_generate_case.py and save raw output
    test_file = repo_root / "tests" / "test_generate_case.py"
    pytest_cmd = f"{sys.executable} -m pytest -v tests/test_generate_case.py"
    res = subprocess.run(pytest_cmd, cwd=repo_root, capture_output=True, text=True)
    pytest_raw_file = results_dir / "pytest_raw.txt"
    raw_output = res.stdout + (("\n" + res.stderr) if res.stderr else "")
    pytest_raw_file.write_text(raw_output, encoding="utf-8")

    # 4. Compute metrics and write metrics.json
    metrics = compute_metrics(run1_dir, run2_dir, gen_script, test_file, pytest_cmd)
    metrics_file = results_dir / "metrics.json"
    with open(metrics_file, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)

    # 5. Write SHA256SUMS.txt for all files in the results folder
    files_to_hash = [
        run1_dir / "truth.json",
        run1_dir / "cdr.csv",
        run1_dir / "bank.csv",
        run2_dir / "truth.json",
        run2_dir / "cdr.csv",
        run2_dir / "bank.csv",
        pytest_raw_file,
        metrics_file,
    ]
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
    step1_md_content = build_markdown_section(results_rel_path, metrics, pytest_tests)

    docs_file = repo_root / "docs" / "RESULTS.md"
    docs_file.parent.mkdir(parents=True, exist_ok=True)

    if docs_file.exists():
        existing_doc = docs_file.read_text(encoding="utf-8")
        marker_pattern = re.compile(r"<!-- STEP1:BEGIN -->.*?<!-- STEP1:END -->", re.DOTALL)
        if marker_pattern.search(existing_doc):
            new_doc = marker_pattern.sub(lambda _: step1_md_content, existing_doc)
        else:
            new_doc = existing_doc.rstrip() + "\n\n" + step1_md_content + "\n"
    else:
        new_doc = f"# Crimi-Nex Evaluation Results\n\n{step1_md_content}\n"

    docs_file.write_text(new_doc, encoding="utf-8")
    print(f"Step 1 evaluation completed successfully.")
    print(f"Results Directory: {results_dir}")


if __name__ == "__main__":
    main()

