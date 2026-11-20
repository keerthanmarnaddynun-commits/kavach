"""Loader for the reference demo case using stored synthetic records and saved analyses."""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from kavach_api.analysis_service import build_graph
from kavach_api.audit import AuditLog
from kavach_api.ingest import validate_bank, validate_cdr
from kavach_api.leads import build_leads
from kavach_api.settings import Settings, load_settings
from kavach_api.storage import Storage, _atomic_write_json

logger = logging.getLogger(__name__)

DEMO_CASE_NAME = "Demo (synthetic case_demo_v2)"


def load_demo_case(settings: Settings | None = None) -> dict[str, Any]:
    """
    Load demo case using the same service functions as the HTTP path.
    Refuses to run if a case with name 'Demo (synthetic case_demo_v2)' already exists.
    """
    if settings is None:
        settings = load_settings()

    settings.runtime_dir.mkdir(parents=True, exist_ok=True)
    store = Storage(settings)
    audit_log = AuditLog(settings.runtime_dir / "audit.log")

    # 1. Refuse if case already exists
    existing_cases = store.list_cases()
    for c in existing_cases:
        if c.get("name") == DEMO_CASE_NAME:
            raise RuntimeError(
                f"Case with name {DEMO_CASE_NAME!r} already exists: {c['case_id']}"
            )

    # 2. Create case
    case = store.create_case(name=DEMO_CASE_NAME, created_by="system", synthetic=True)
    case_id = case["case_id"]

    # 3. Store 100 FIR text files from firs_v5
    firs_dir = REPO_ROOT / "data" / "synthetic" / "out" / "firs_v5"
    if not firs_dir.exists():
        raise FileNotFoundError(f"FIR directory missing: {firs_dir}")

    fir_files = sorted(firs_dir.glob("FIR_*.txt"))
    if not fir_files:
        raise FileNotFoundError(f"No FIR text files found in {firs_dir}")

    doc_metas: dict[str, dict[str, Any]] = {}
    for fpath in fir_files:
        raw_bytes = fpath.read_bytes()
        meta = store.add_document(
            case_id=case_id,
            filename=fpath.name,
            raw_bytes=raw_bytes,
            uploaded_by="system",
        )
        doc_metas[meta["doc_id"]] = meta

    # 4. Store saved analyses from results/2026-11-11_step6_extraction_r2/run1/
    analyses_dir = REPO_ROOT / "results" / "2026-11-11_step6_extraction_r2" / "run1"
    if not analyses_dir.exists():
        raise FileNotFoundError(f"Analyses directory missing: {analyses_dir}")

    analysis_files = sorted(analyses_dir.glob("*.analysis.json"))
    for apath in analysis_files:
        stem = apath.name[:-len(".analysis.json")]
        if stem not in doc_metas:
            continue

        analysis = json.loads(apath.read_text(encoding="utf-8"))

        # Verify recorded source_doc_id matches
        recorded_id = (
            analysis.get("doc", {}).get("source_doc_id")
            or analysis.get("aux", {}).get("source_doc_id")
        )
        if recorded_id and recorded_id != stem:
            raise ValueError(
                f"Analysis source doc mismatch: file stem {stem} != recorded {recorded_id}"
            )

        store.save_analysis(case_id, stem, analysis)
        store.set_document_status(case_id, stem, status="extracted")

    # 5. Store CDR and Bank CSV files from case_demo_v2
    demo_csv_dir = REPO_ROOT / "data" / "synthetic" / "out" / "case_demo_v2"
    cdr_path = demo_csv_dir / "cdr.csv"
    bank_path = demo_csv_dir / "bank.csv"

    if not cdr_path.is_file() or not bank_path.is_file():
        raise FileNotFoundError(f"Demo CSV files missing in {demo_csv_dir}")

    cdr_bytes = cdr_path.read_bytes()
    cdr_report = validate_cdr(cdr_bytes, settings)
    if not cdr_report.ok:
        raise ValueError(f"Demo CDR CSV failed validation: {cdr_report.errors[:5]}")
    store.save_csv(
        case_id,
        "cdr",
        cdr_bytes,
        {
            "rows": cdr_report.rows,
            "columns": cdr_report.columns,
            "sha256": hashlib.sha256(cdr_bytes).hexdigest(),
        },
    )

    bank_bytes = bank_path.read_bytes()
    bank_report = validate_bank(bank_bytes, settings)
    if not bank_report.ok:
        raise ValueError(f"Demo Bank CSV failed validation: {bank_report.errors[:5]}")
    store.save_csv(
        case_id,
        "bank",
        bank_bytes,
        {
            "rows": bank_report.rows,
            "columns": bank_report.columns,
            "sha256": hashlib.sha256(bank_bytes).hexdigest(),
        },
    )

    # 6. Build graph and leads
    build_graph(store, case_id)
    build_leads(store, case_id)

    # 7. Mark case analyzed
    cdir = store.case_dir(case_id)
    meta_path = cdir / "case.json"
    if meta_path.is_file():
        meta_dict = json.loads(meta_path.read_text(encoding="utf-8"))
        meta_dict["analyzed"] = True
        _atomic_write_json(meta_path, meta_dict)

    # 8. Record audit log entry
    audit_log.append(
        actor="system",
        role="system",
        action="demo_loaded",
        case_id=case_id,
        detail={
            "case_id": case_id,
            "name": DEMO_CASE_NAME,
            "documents": len(fir_files),
            "cdr_rows": cdr_report.rows,
            "bank_rows": bank_report.rows,
        },
    )

    return {
        "case_id": case_id,
        "name": DEMO_CASE_NAME,
        "documents": len(fir_files),
        "cdr_rows": cdr_report.rows,
        "bank_rows": bank_report.rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Load reference demo case into KAVACH")
    parser.add_argument(
        "--runtime-dir",
        default=None,
        help="Custom runtime directory path",
    )
    args = parser.parse_args()

    custom_env = None
    if args.runtime_dir:
        custom_env = {"KAVACH_RUNTIME_DIR": args.runtime_dir}
    settings = load_settings(custom_env)

    result = load_demo_case(settings)
    print(
        f"Demo case loaded successfully: {result['name']} (ID: {result['case_id']}) with "
        f"{result['documents']} documents, {result['cdr_rows']} CDR rows, {result['bank_rows']} Bank rows."
    )


if __name__ == "__main__":
    main()
