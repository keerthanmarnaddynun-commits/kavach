"""Analysis service for building and caching deterministic case graphs."""
from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
import tempfile
import threading
from typing import Any

from case_graph.builder import build_case_graph
from kavach_api.storage import Storage, _atomic_write_json

logger = logging.getLogger(__name__)

EMPTY_CDR_HEADER = "a_party,b_party,imei_a,imsi_a,start_time,duration_sec,call_type,tower_id,lat,lon\n"
EMPTY_BANK_HEADER = "txn_id,datetime,from_acct,to_acct,amount,mode,ifsc,narration\n"


class AnalysisError(Exception):
    """Base exception for analysis service operations."""


class NothingToAnalyzeError(AnalysisError):
    """Raised when neither analyses nor CSV files exist for a case."""


def _compute_file_sha256(path: Path) -> str:
    """Compute SHA-256 of a file's contents."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def compute_case_fingerprint(store: Storage, case_id: str) -> tuple[str, str]:
    """
    Compute input fingerprint and document_hash for a case.
    Returns (fingerprint, document_hash).
    """
    cdir = store.case_dir(case_id)
    analyses_dir = cdir / "analyses"

    input_entries: list[tuple[str, str]] = []

    if analyses_dir.exists():
        for p in sorted(analyses_dir.glob("*.analysis.json")):
            input_entries.append((f"analyses/{p.name}", _compute_file_sha256(p)))

    cdr_path = store.csv_path(case_id, "cdr")
    if cdr_path.is_file():
        input_entries.append(("cdr.csv", _compute_file_sha256(cdr_path)))

    bank_path = store.csv_path(case_id, "bank")
    if bank_path.is_file():
        input_entries.append(("bank.csv", _compute_file_sha256(bank_path)))

    if not input_entries:
        raise NothingToAnalyzeError(f"No analyses or CSV files found for case {case_id}")

    input_entries.sort(key=lambda x: x[0])
    lines = [f"{name}\t{digest}" for name, digest in input_entries]
    fingerprint = hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()

    # document_hash: sha256 of sorted list of all input hashes joined by newline
    sorted_digests = sorted(digest for _, digest in input_entries)
    document_hash = hashlib.sha256("\n".join(sorted_digests).encode("utf-8")).hexdigest()

    return fingerprint, document_hash


def build_graph(store: Storage, case_id: str) -> dict[str, Any]:
    """
    Build or retrieve cached case graph from case analyses and CSV files.
    Saves derived/graph.json and derived/fingerprint.json upon creation.
    """
    with store.case_lock(case_id):
        cdir = store.case_dir(case_id)
        analyses_dir = cdir / "analyses"
        cdr_path = store.csv_path(case_id, "cdr")
        bank_path = store.csv_path(case_id, "bank")

        has_analyses = analyses_dir.exists() and any(analyses_dir.glob("*.analysis.json"))
        has_cdr = cdr_path.is_file()
        has_bank = bank_path.is_file()

        if not has_analyses and not has_cdr and not has_bank:
            raise NothingToAnalyzeError(f"Case {case_id} has no analyses or CSV files to analyze")

        fingerprint, doc_hash = compute_case_fingerprint(store, case_id)

        derived_dir = cdir / "derived"
        derived_dir.mkdir(exist_ok=True)
        graph_path = derived_dir / "graph.json"
        fp_path = derived_dir / "fingerprint.json"

        # Check cache
        if fp_path.is_file() and graph_path.is_file():
            try:
                cached_fp = json.loads(fp_path.read_text(encoding="utf-8"))
                if cached_fp.get("fingerprint") == fingerprint:
                    return json.loads(graph_path.read_text(encoding="utf-8"))
            except Exception:
                pass

        # Prepare CSV inputs for builder
        temp_dir: tempfile.TemporaryDirectory | None = None
        try:
            actual_cdr = cdr_path
            actual_bank = bank_path

            if not has_cdr or not has_bank:
                temp_dir = tempfile.TemporaryDirectory()
                td_path = Path(temp_dir.name)
                if not has_cdr:
                    actual_cdr = td_path / "dummy_cdr.csv"
                    actual_cdr.write_text(EMPTY_CDR_HEADER, encoding="utf-8")
                if not has_bank:
                    actual_bank = td_path / "dummy_bank.csv"
                    actual_bank.write_text(EMPTY_BANK_HEADER, encoding="utf-8")

            analyses_input_dir = analyses_dir if has_analyses else td_path / "empty_analyses"
            if not has_analyses:
                analyses_input_dir.mkdir(exist_ok=True)

            graph = build_case_graph(analyses_input_dir, actual_cdr, actual_bank)
            graph["document_hash"] = doc_hash
            graph["fingerprint"] = fingerprint

            _atomic_write_json(graph_path, graph)
            _atomic_write_json(
                fp_path,
                {
                    "fingerprint": fingerprint,
                    "document_hash": doc_hash,
                },
            )
            return graph
        finally:
            if temp_dir is not None:
                try:
                    temp_dir.cleanup()
                except Exception:
                    pass
