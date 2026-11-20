"""Storage layer for KAVACH cases, documents, analyses and CSV files."""
from __future__ import annotations

import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import threading
import time
from typing import Any, Mapping

from kavach_api.settings import Settings


CASE_ID_PATTERN = re.compile(r"^C-[0-9a-f]{10}$")
DOC_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


class StorageError(Exception):
    """Base exception for storage operations."""


class InvalidIdError(StorageError):
    """Raised when a case_id or doc_id fails validation."""


class DuplicateDocument(StorageError):
    """Raised when an uploaded document matches an existing document's raw bytes hash."""
    def __init__(self, doc_id: str, message: str | None = None):
        self.doc_id = doc_id
        super().__init__(message or f"Document with identical content already exists with id {doc_id}")


class CaseNotFoundError(StorageError):
    """Raised when a case does not exist."""


class DocumentNotFoundError(StorageError):
    """Raised when a document does not exist in a case."""


def validate_case_id(case_id: str) -> str:
    """Validate case identifier against ^C-[0-9a-f]{10}$."""
    if not isinstance(case_id, str) or not CASE_ID_PATTERN.match(case_id):
        raise InvalidIdError(f"Invalid case_id format: {case_id!r}")
    return case_id


def validate_doc_id(doc_id: str) -> str:
    """Validate document identifier against ^[A-Za-z0-9_-]{1,40}$."""
    if not isinstance(doc_id, str) or not DOC_ID_PATTERN.match(doc_id):
        raise InvalidIdError(f"Invalid doc_id format: {doc_id!r}")
    return doc_id


def safe_stem(filename: str) -> str:
    """Return clean stem if it matches ^[A-Za-z0-9_-]{1,40}$, else empty string."""
    if not filename:
        return ""
    stem = Path(filename).stem
    if DOC_ID_PATTERN.match(stem):
        return stem
    return ""


def _now_iso() -> str:
    """Return current UTC timestamp in ISO 8601 format."""
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _atomic_write_json(path: Path, data: Any) -> None:
    """Atomically write JSON data using temp file and os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(f"{path.suffix}.tmp_{secrets.token_hex(4)}")
    try:
        content = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        temp_path.write_text(content, encoding="utf-8")
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    """Atomically write binary bytes using temp file and os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(f"{path.suffix}.tmp_{secrets.token_hex(4)}")
    try:
        temp_path.write_bytes(data)
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


class Store:
    """Filesystem storage manager for cases, documents, and derived artifacts."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.runtime_dir = settings.runtime_dir
        self._case_locks: dict[str, threading.RLock] = {}
        self._global_lock = threading.Lock()

    def case_lock(self, case_id: str) -> threading.RLock:
        """Return re-entrant lock for a given case_id."""
        cid = validate_case_id(case_id)
        with self._global_lock:
            if cid not in self._case_locks:
                self._case_locks[cid] = threading.RLock()
            return self._case_locks[cid]

    @property
    def cases_dir(self) -> Path:
        """Return base cases directory under runtime."""
        return self.runtime_dir / "cases"

    def case_dir(self, case_id: str) -> Path:
        """Return validated case directory, preventing path traversal."""
        cid = validate_case_id(case_id)
        target = (self.cases_dir / cid).resolve()
        base = self.cases_dir.resolve()
        # Verify target is strictly within base
        if target != base and base not in target.parents:
            raise InvalidIdError(f"Case directory escape detected: {case_id}")
        return target

    def create_case(self, name: str, created_by: str, synthetic: bool = False) -> dict[str, Any]:
        """Create a new case directory and write case.json and files.json."""
        with self._global_lock:
            # Generate unique case id
            for _ in range(50):
                cid = f"C-{secrets.token_hex(5)}"
                c_dir = self.cases_dir / cid
                if not c_dir.exists():
                    break
            else:
                raise StorageError("Failed to generate unique case_id")

        cdir = self.case_dir(cid)
        cdir.mkdir(parents=True, exist_ok=False)
        (cdir / "documents").mkdir(exist_ok=True)
        (cdir / "analyses").mkdir(exist_ok=True)
        (cdir / "derived").mkdir(exist_ok=True)

        case_info = {
            "case_id": cid,
            "name": name,
            "created_at": _now_iso(),
            "created_by": created_by,
            "synthetic": bool(synthetic),
        }
        _atomic_write_json(cdir / "case.json", case_info)
        _atomic_write_json(cdir / "files.json", {"cdr": None, "bank": None})
        return case_info

    def get_case(self, case_id: str) -> dict[str, Any]:
        """Load and return case information."""
        cdir = self.case_dir(case_id)
        case_file = cdir / "case.json"
        if not case_file.is_file():
            raise CaseNotFoundError(f"Case not found: {case_id}")
        data = json.loads(case_file.read_text(encoding="utf-8"))
        return data

    def list_cases(self) -> list[dict[str, Any]]:
        """List all cases with summary statistics."""
        if not self.cases_dir.exists():
            return []

        results = []
        for p in sorted(self.cases_dir.iterdir()):
            if not p.is_dir():
                continue
            case_file = p / "case.json"
            if not case_file.is_file():
                continue
            try:
                cdata = json.loads(case_file.read_text(encoding="utf-8"))
            except Exception:
                continue

            # Compute counts
            docs_dir = p / "documents"
            doc_count = len(list(docs_dir.glob("*.meta.json"))) if docs_dir.exists() else 0

            cdr_rows = 0
            bank_rows = 0
            files_file = p / "files.json"
            if files_file.is_file():
                try:
                    fdata = json.loads(files_file.read_text(encoding="utf-8"))
                    if fdata.get("cdr"):
                        cdr_rows = fdata["cdr"].get("rows", 0)
                    if fdata.get("bank"):
                        bank_rows = fdata["bank"].get("rows", 0)
                except Exception:
                    pass

            analyzed = (p / "derived" / "graph.json").is_file()

            results.append({
                "case_id": cdata["case_id"],
                "name": cdata.get("name", ""),
                "created_at": cdata.get("created_at", ""),
                "synthetic": cdata.get("synthetic", False),
                "counts": {
                    "documents": doc_count,
                    "cdr_rows": cdr_rows,
                    "bank_rows": bank_rows,
                },
                "analyzed": analyzed,
            })
        return results

    def add_document(
        self,
        case_id: str,
        filename: str,
        raw_bytes: bytes,
        uploaded_by: str,
    ) -> dict[str, Any]:
        """
        Store a document decoded with utf-8-sig as UTF-8 bytes.
        Check for duplicates by sha256_raw.
        """
        with self.case_lock(case_id):
            cdir = self.case_dir(case_id)
            if not (cdir / "case.json").is_file():
                raise CaseNotFoundError(f"Case not found: {case_id}")

            docs_dir = cdir / "documents"
            docs_dir.mkdir(exist_ok=True)

            # 1. Decode text
            text = raw_bytes.decode("utf-8-sig")
            text_bytes = text.encode("utf-8")
            sha256_raw = hashlib.sha256(raw_bytes).hexdigest()
            sha256_text = hashlib.sha256(text_bytes).hexdigest()

            # 2. Duplicate check against existing documents in this case
            existing_metas = self.list_documents(case_id)
            for m in existing_metas:
                if m.get("sha256_raw") == sha256_raw:
                    raise DuplicateDocument(
                        doc_id=m["doc_id"],
                        message=f"Document with identical content already exists as {m['doc_id']}",
                    )

            # 3. Determine doc_id
            existing_ids = {m["doc_id"] for m in existing_metas}
            stem = safe_stem(filename)

            if stem:
                if stem not in existing_ids:
                    doc_id = stem
                else:
                    counter = 2
                    while f"{stem}-{counter}" in existing_ids:
                        counter += 1
                    doc_id = f"{stem}-{counter}"
            else:
                # Fallback to DOC-0001, DOC-0002...
                counter = 1
                while f"DOC-{counter:04d}" in existing_ids:
                    counter += 1
                doc_id = f"DOC-{counter:04d}"

            # 4. Save document text as bytes and write metadata
            doc_txt_path = docs_dir / f"{doc_id}.txt"
            _atomic_write_bytes(doc_txt_path, text_bytes)

            meta = {
                "doc_id": doc_id,
                "filename": filename,
                "sha256_raw": sha256_raw,
                "sha256_text": sha256_text,
                "chars": len(text),
                "uploaded_at": _now_iso(),
                "uploaded_by": uploaded_by,
                "status": "uploaded",
                "error": None,
            }
            meta_path = docs_dir / f"{doc_id}.meta.json"
            _atomic_write_json(meta_path, meta)
            return meta

    def get_document(self, case_id: str, doc_id: str) -> tuple[dict[str, Any], str]:
        """Return (meta_dict, text) for a document."""
        cdir = self.case_dir(case_id)
        did = validate_doc_id(doc_id)
        meta_file = cdir / "documents" / f"{did}.meta.json"
        txt_file = cdir / "documents" / f"{did}.txt"

        if not meta_file.is_file() or not txt_file.is_file():
            raise DocumentNotFoundError(f"Document not found: {did} in case {case_id}")

        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        text = txt_file.read_bytes().decode("utf-8")
        return meta, text

    def list_documents(self, case_id: str) -> list[dict[str, Any]]:
        """List all document metadata in upload order or name order."""
        cdir = self.case_dir(case_id)
        docs_dir = cdir / "documents"
        if not docs_dir.exists():
            return []

        metas = []
        for p in docs_dir.glob("*.meta.json"):
            try:
                m = json.loads(p.read_text(encoding="utf-8"))
                metas.append(m)
            except Exception:
                continue

        metas.sort(key=lambda m: (m.get("uploaded_at", ""), m.get("doc_id", "")))
        return metas

    def set_document_status(
        self,
        case_id: str,
        doc_id: str,
        status: str,
        error: dict[str, Any] | str | None = None,
    ) -> None:
        """Update status and optional error in document metadata."""
        with self.case_lock(case_id):
            cdir = self.case_dir(case_id)
            did = validate_doc_id(doc_id)
            meta_file = cdir / "documents" / f"{did}.meta.json"
            if not meta_file.is_file():
                raise DocumentNotFoundError(f"Document not found: {did} in case {case_id}")

            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            meta["status"] = status
            meta["error"] = error
            _atomic_write_json(meta_file, meta)

    def save_analysis(self, case_id: str, doc_id: str, analysis: dict[str, Any]) -> None:
        """Save extractor output for a document."""
        with self.case_lock(case_id):
            cdir = self.case_dir(case_id)
            did = validate_doc_id(doc_id)
            analyses_dir = cdir / "analyses"
            analyses_dir.mkdir(exist_ok=True)
            out_file = analyses_dir / f"{did}.analysis.json"
            _atomic_write_json(out_file, analysis)

    def load_analyses(self, case_id: str) -> dict[str, dict[str, Any]]:
        """Load all analyses for a case, keyed by doc_id."""
        cdir = self.case_dir(case_id)
        analyses_dir = cdir / "analyses"
        if not analyses_dir.exists():
            return {}

        results = {}
        for p in sorted(analyses_dir.glob("*.analysis.json")):
            stem = p.name[:-len(".analysis.json")]
            try:
                results[stem] = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
        return results

    def save_csv(
        self,
        case_id: str,
        kind: str,
        raw_bytes: bytes,
        report: dict[str, Any] | None = None,
    ) -> None:
        """Save CDR or bank CSV upload as bytes and update files.json."""
        if kind not in ("cdr", "bank"):
            raise StorageError(f"Invalid CSV kind: {kind!r}, must be 'cdr' or 'bank'")

        with self.case_lock(case_id):
            cdir = self.case_dir(case_id)
            if not (cdir / "case.json").is_file():
                raise CaseNotFoundError(f"Case not found: {case_id}")

            csv_file = cdir / f"{kind}.csv"
            _atomic_write_bytes(csv_file, raw_bytes)

            sha256 = hashlib.sha256(raw_bytes).hexdigest()
            rows = report.get("rows", 0) if report else 0
            columns = report.get("columns", []) if report else []

            files_file = cdir / "files.json"
            files_data = {"cdr": None, "bank": None}
            if files_file.is_file():
                try:
                    files_data = json.loads(files_file.read_text(encoding="utf-8"))
                except Exception:
                    pass

            files_data[kind] = {
                "sha256": sha256,
                "rows": rows,
                "columns": columns,
                "uploaded_at": _now_iso(),
            }
            _atomic_write_json(files_file, files_data)

    def csv_path(self, case_id: str, kind: str) -> Path:
        """Return path to saved CSV file."""
        if kind not in ("cdr", "bank"):
            raise StorageError(f"Invalid CSV kind: {kind!r}")
        cdir = self.case_dir(case_id)
        return cdir / f"{kind}.csv"

    def files_info(self, case_id: str) -> dict[str, Any]:
        """Return information about uploaded CDR and bank files."""
        cdir = self.case_dir(case_id)
        files_file = cdir / "files.json"
        if not files_file.is_file():
            return {"cdr": None, "bank": None}
        try:
            return json.loads(files_file.read_text(encoding="utf-8"))
        except Exception:
            return {"cdr": None, "bank": None}

    def derived_path(self, case_id: str, name: str) -> Path:
        """Return path to a derived artifact (e.g. graph.json), preventing traversal."""
        cdir = self.case_dir(case_id)
        # Validate name is a safe single filename
        if not re.match(r"^[A-Za-z0-9_.-]{1,50}$", name) or ".." in name:
            raise StorageError(f"Invalid derived file name: {name!r}")
        derived_dir = cdir / "derived"
        derived_dir.mkdir(exist_ok=True)
        target = (derived_dir / name).resolve()
        if derived_dir.resolve() not in target.parents:
            raise StorageError(f"Derived path escape detected: {name}")
        return target
