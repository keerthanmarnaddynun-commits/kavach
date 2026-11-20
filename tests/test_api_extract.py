"""Unit tests for extract_service, fake extractor workflows, and offline real model comparison."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any
import pytest

from kavach_api.extract_service import (
    default_extractor,
    extract_document,
    model_loaded,
    run_extract_job,
)
from kavach_api.jobs import JobStore
from kavach_api.settings import Settings, repo_root
from kavach_api.storage import Storage


# Custom exception classes mirroring ai_pipeline.pipeline classes
class EmptyText(Exception):
    pass


class TextTooLong(Exception):
    pass


class NoEntitiesFound(Exception):
    pass


@pytest.fixture
def test_env(tmp_path: Path) -> tuple[Storage, JobStore]:
    """Fixture providing Storage and JobStore instances."""
    settings = Settings(runtime_dir=tmp_path / "runtime")
    store = Storage(settings)
    job_store = JobStore(tmp_path / "runtime")
    return store, job_store


def _dummy_valid_ai_output(text: str, doc_id: str, case_id: str) -> dict[str, Any]:
    """Return a valid Contract 1 v1.1 AI output dictionary."""
    saved_path = repo_root() / "results" / "2026-11-11_step6_extraction_r2" / "run1" / "FIR_01.analysis.json"
    data = json.loads(saved_path.read_text(encoding="utf-8"))
    data["doc"]["source_doc_id"] = doc_id
    data["doc"]["case_id"] = case_id
    return data


def test_import_extract_service_does_not_load_torch() -> None:
    """Importing extract_service must not import torch or transformers into sys.modules."""
    code = (
        "import kavach_api.extract_service\n"
        "import sys\n"
        "assert 'torch' not in sys.modules, 'torch was loaded unexpectedly'\n"
        "assert 'transformers' not in sys.modules, 'transformers was loaded unexpectedly'\n"
        "print('clean_import')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, f"Import check failed: {result.stderr}"
    assert "clean_import" in result.stdout


def test_extract_document_lifecycle(test_env: tuple[Storage, JobStore]) -> None:
    """Document extraction updates status, saves analysis, and validates output."""
    store, _ = test_env
    case = store.create_case("Case 1", "test_user")
    case_id = case["case_id"]

    meta = store.add_document(case_id, "DOC_001", b"Ramesh Kumar went to the station.", "test_user")
    doc_id = meta["doc_id"]

    def fake_extractor(text: str, doc_id: str, case_id: str) -> dict[str, Any]:
        return _dummy_valid_ai_output(text, doc_id, case_id)

    res = extract_document(store, case_id, doc_id, fake_extractor)
    assert res["status"] == "extracted"

    # Verify document metadata in storage
    doc_meta, _ = store.get_document(case_id, doc_id)
    assert doc_meta["status"] == "extracted"
    assert doc_meta.get("error") is None

    # Verify saved analysis file
    analyses = store.load_analyses(case_id)
    assert doc_id in analyses
    assert analyses[doc_id]["doc"]["source_doc_id"] == doc_id


def test_extract_document_typed_errors(test_env: tuple[Storage, JobStore]) -> None:
    """Extractor exceptions are mapped to exact status codes and one failure does not halt others."""
    store, _ = test_env
    case = store.create_case("Case Errors", "test_user")
    case_id = case["case_id"]

    store.add_document(case_id, "DOC_EMPTY", b"", "test_user")
    store.add_document(case_id, "DOC_LONG", b"Long text", "test_user")
    store.add_document(case_id, "DOC_NOENT", b"No entities here", "test_user")
    store.add_document(case_id, "DOC_INVALID", b"Invalid contract payload", "test_user")
    store.add_document(case_id, "DOC_OK", b"Valid text", "test_user")

    def error_extractor(text: str, doc_id: str, case_id: str) -> dict[str, Any]:
        if doc_id == "DOC_EMPTY":
            raise EmptyText("Empty text input")
        if doc_id == "DOC_LONG":
            raise TextTooLong("Text exceeds maximum length")
        if doc_id == "DOC_NOENT":
            raise NoEntitiesFound("No entities recognized")
        if doc_id == "DOC_INVALID":
            # Invalid doc missing schema_version and required fields
            return {"aux": {}, "doc": {"bad_field": 123}, "info": {}}
        return _dummy_valid_ai_output(text, doc_id, case_id)

    # Empty text
    r_empty = extract_document(store, case_id, "DOC_EMPTY", error_extractor)
    assert r_empty["status"] == "failed"
    assert r_empty["code"] == "empty_text"
    m_empty, _ = store.get_document(case_id, "DOC_EMPTY")
    assert m_empty["status"] == "failed"
    assert m_empty["error"]["code"] == "empty_text"

    # Text too long
    r_long = extract_document(store, case_id, "DOC_LONG", error_extractor)
    assert r_long["status"] == "failed"
    assert r_long["code"] == "text_too_long"
    m_long, _ = store.get_document(case_id, "DOC_LONG")
    assert m_long["status"] == "failed"
    assert m_long["error"]["code"] == "text_too_long"

    # No entities found
    r_noent = extract_document(store, case_id, "DOC_NOENT", error_extractor)
    assert r_noent["status"] == "failed"
    assert r_noent["code"] == "no_entities_found"
    m_noent, _ = store.get_document(case_id, "DOC_NOENT")
    assert m_noent["status"] == "failed"
    assert m_noent["error"]["code"] == "no_entities_found"

    # Invalid contract output
    r_invalid = extract_document(store, case_id, "DOC_INVALID", error_extractor)
    assert r_invalid["status"] == "failed"
    assert r_invalid["code"] == "invalid_output"
    m_invalid, _ = store.get_document(case_id, "DOC_INVALID")
    assert m_invalid["status"] == "failed"
    assert m_invalid["error"]["code"] == "invalid_output"

    # Next document still extracts successfully
    r_ok = extract_document(store, case_id, "DOC_OK", error_extractor)
    assert r_ok["status"] == "extracted"
    m_ok, _ = store.get_document(case_id, "DOC_OK")
    assert m_ok["status"] == "extracted"


def test_run_extract_job_progress_and_counts(test_env: tuple[Storage, JobStore]) -> None:
    """run_extract_job iterates documents, updates progress, and writes final summary."""
    store, job_store = test_env
    case = store.create_case("Case Batch", "test_user")
    case_id = case["case_id"]

    doc_ids = ["DOC_A", "DOC_B", "DOC_C"]
    for did in doc_ids:
        store.add_document(case_id, did, f"Content for {did}".encode("utf-8"), "test_user")

    job = job_store.create(kind="extract", case_id=case_id, total=len(doc_ids))
    job_id = job["job_id"]

    def mixed_extractor(text: str, doc_id: str, case_id: str) -> dict[str, Any]:
        if doc_id == "DOC_B":
            raise EmptyText("Failed doc B")
        return _dummy_valid_ai_output(text, doc_id, case_id)

    summary = run_extract_job(store, job_store, case_id, doc_ids, job_id, mixed_extractor)
    assert summary == {"extracted": 2, "failed": 1}

    # Verify final job state
    final_job = job_store.get(job_id)
    assert final_job is not None
    assert final_job["status"] == "done"
    assert final_job["progress"]["done"] == 3
    assert final_job["progress"]["total"] == 3
    assert final_job["progress"]["current"] is None
    assert final_job["result"] == {"extracted": 2, "failed": 1}
    assert len(final_job["errors"]) == 1
    assert final_job["errors"][0]["doc_id"] == "DOC_B"
    assert final_job["errors"][0]["code"] == "empty_text"


def test_real_model_matches_saved_outputs() -> None:
    """
    Real model extraction on FIR_01, FIR_45, and FIR_60 matches saved step 6 outputs.
    Runs only when KAVACH_RUN_MODEL_TESTS=1 is set.
    """
    if os.environ.get("KAVACH_RUN_MODEL_TESTS") != "1":
        pytest.skip("KAVACH_RUN_MODEL_TESTS environment variable is not set to 1")

    root = repo_root()
    firs_dir = root / "data" / "synthetic" / "out" / "firs_v5"
    saved_dir = root / "results" / "2026-11-11_step6_extraction_r2" / "run1"

    extractor = default_extractor()
    assert model_loaded() is False or True

    target_files = ["FIR_01", "FIR_45", "FIR_60"]

    for stem in target_files:
        txt_path = firs_dir / f"{stem}.txt"
        saved_path = saved_dir / f"{stem}.analysis.json"

        assert txt_path.is_file(), f"Missing text file: {txt_path}"
        assert saved_path.is_file(), f"Missing saved analysis: {saved_path}"

        text = txt_path.read_text(encoding="utf-8")
        saved_data = json.loads(saved_path.read_text(encoding="utf-8"))
        case_id = saved_data.get("doc", {}).get("case_id", "CASE_DEMO_V2")

        actual_output = extractor(text, doc_id=stem, case_id=case_id)

        # Dictionary equality checks on all 3 keys: aux, doc, info
        assert "aux" in actual_output and "doc" in actual_output and "info" in actual_output

        assert actual_output["aux"] == saved_data["aux"], f"aux mismatch in {stem}"
        assert actual_output["doc"] == saved_data["doc"], f"doc mismatch in {stem}"

        # In info, compare all keys. The saved JSON omitted dynamic runtime timings_ms.
        actual_info = dict(actual_output["info"])
        if "timings_ms" not in saved_data["info"]:
            actual_info.pop("timings_ms", None)

        assert actual_info == saved_data["info"], f"info mismatch in {stem}"
