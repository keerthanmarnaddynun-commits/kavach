"""Extraction service wrapping the AI pipeline extractor."""
from __future__ import annotations

import logging
import os
from pathlib import Path
import threading
from typing import Any, Callable, Sequence

from contracts.v1_1.validate import validate_ai_output
from kavach_api.jobs import JobStore
from kavach_api.storage import Storage

logger = logging.getLogger(__name__)

_MODEL_LOADED = False
_EXTRACTOR_LOCK = threading.Lock()
_PIPELINE_ANALYZE_FN: Callable[..., dict[str, Any]] | None = None


def model_loaded() -> bool:
    """Return True if the default AI model extractor has been imported and initialized."""
    return _MODEL_LOADED


def default_extractor() -> Callable[..., dict[str, Any]]:
    """
    Return a thread-safe callable that lazily imports the frozen AI pipeline
    with HF_HUB_OFFLINE=1 and serializes invocations with a lock.
    """
    def _extractor(text: str, doc_id: str = "DOC_001", case_id: str = "CASE_DEMO_V2") -> dict[str, Any]:
        global _MODEL_LOADED, _PIPELINE_ANALYZE_FN
        with _EXTRACTOR_LOCK:
            if _PIPELINE_ANALYZE_FN is None:
                os.environ["HF_HUB_OFFLINE"] = "1"
                import ai_pipeline.pipeline as pipeline_mod
                _PIPELINE_ANALYZE_FN = pipeline_mod.analyze_text
                _MODEL_LOADED = True
            return _PIPELINE_ANALYZE_FN(text, doc_id=doc_id, case_id=case_id)

    return _extractor


def extract_document(
    store: Storage,
    case_id: str,
    doc_id: str,
    extractor: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Extract structured entities and relations from a stored document.
    Saves analysis on success, updates document status, and catches typed extractor errors.
    """
    if extractor is None:
        extractor = default_extractor()

    try:
        _meta, text = store.get_document(case_id, doc_id)
    except Exception:
        logger.exception("Failed to retrieve document %s in case %s", doc_id, case_id)
        code = "document_not_found"
        msg = "Extraction failed"
        try:
            store.set_document_status(case_id, doc_id, "failed", error={"code": code, "message": msg})
        except Exception:
            pass
        return {"status": "failed", "doc_id": doc_id, "code": code, "message": msg}

    try:
        result = extractor(text, doc_id=doc_id, case_id=case_id)
    except Exception as exc:
        logger.exception("Extraction execution error on doc %s in case %s", doc_id, case_id)
        exc_name = type(exc).__name__
        if exc_name == "EmptyText":
            code = "empty_text"
            msg = "empty_text"
        elif exc_name == "TextTooLong":
            code = "text_too_long"
            msg = "text_too_long"
        elif exc_name == "NoEntitiesFound":
            code = "no_entities_found"
            msg = "no_entities_found"
        else:
            code = "extraction_error"
            msg = "Extraction failed"
        store.set_document_status(case_id, doc_id, "failed", error={"code": code, "message": msg})
        return {"status": "failed", "doc_id": doc_id, "code": code, "message": msg}

    if not isinstance(result, dict) or "doc" not in result:
        logger.error("Extractor result for doc %s lacks 'doc' key", doc_id)
        code = "invalid_output"
        msg = "Extraction failed"
        store.set_document_status(case_id, doc_id, "failed", error={"code": code, "message": msg})
        return {"status": "failed", "doc_id": doc_id, "code": code, "message": msg}

    try:
        validate_ai_output(result["doc"])
    except Exception as val_exc:
        logger.exception("Contract validation failed on doc %s", doc_id)
        code = "invalid_output"
        msg = f"Contract validation failed: {val_exc}"[:200]
        store.set_document_status(case_id, doc_id, "failed", error={"code": code, "message": msg})
        return {"status": "failed", "doc_id": doc_id, "code": code, "message": msg}

    store.save_analysis(case_id, doc_id, result)
    store.set_document_status(case_id, doc_id, "extracted", error=None)
    return {"status": "extracted", "doc_id": doc_id, "result": result}


def run_extract_job(
    store: Storage,
    job_store: JobStore,
    case_id: str,
    doc_ids: Sequence[str],
    job_id: str,
    extractor: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, int]:
    """
    Process listed documents in order, updating job progress after each,
    and finish with a summary {'extracted': int, 'failed': int}.
    """
    if extractor is None:
        extractor = default_extractor()

    total = len(doc_ids)
    job_store.update(job_id, status="running", progress={"done": 0, "total": total, "current": None})

    extracted_count = 0
    failed_count = 0
    job_errors: list[dict[str, Any]] = []

    for i, doc_id in enumerate(doc_ids):
        job_store.update(job_id, progress={"done": i, "total": total, "current": doc_id})
        res = extract_document(store, case_id, doc_id, extractor)
        if res.get("status") == "extracted":
            extracted_count += 1
        else:
            failed_count += 1
            job_errors.append(
                {
                    "doc_id": doc_id,
                    "code": res.get("code", "unknown_error"),
                    "message": res.get("message", "Extraction failed"),
                }
            )
        job_store.update(
            job_id,
            progress={"done": i + 1, "total": total, "current": doc_id},
            errors=job_errors,
        )

    summary = {"extracted": extracted_count, "failed": failed_count}
    job_store.update(
        job_id,
        status="done",
        progress={"done": total, "total": total, "current": None},
        result=summary,
    )
    return summary
