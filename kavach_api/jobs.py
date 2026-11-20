"""Job management and worker runner for KAVACH asynchronous tasks."""
from __future__ import annotations

from dataclasses import dataclass, field
import datetime
import json
import logging
import os
from pathlib import Path
import queue
import re
import secrets
import threading
import time
from typing import Any, Callable, Mapping, Sequence

logger = logging.getLogger(__name__)

JOB_ID_PATTERN = re.compile(r"^J-[0-9a-f]{12}\Z")
VALID_KINDS = frozenset({"extract", "analyze"})
VALID_STATUSES = frozenset({"queued", "running", "done", "failed"})


class JobError(Exception):
    """Base exception for job store operations."""


class InvalidJobIdError(JobError):
    """Raised when a job_id does not match the required pattern."""


class JobNotFoundError(JobError):
    """Raised when a job file does not exist."""


def validate_job_id(job_id: str) -> str:
    """Validate job identifier against ^J-[0-9a-f]{12}\\Z."""
    if not isinstance(job_id, str) or not JOB_ID_PATTERN.fullmatch(job_id):
        raise InvalidJobIdError(f"Invalid job_id format: {job_id!r}")
    return job_id


def _now_iso() -> str:
    """Return current UTC timestamp in ISO 8601 format."""
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _atomic_write_json(path: Path, data: Any) -> None:
    """Write JSON data atomically using a temporary file in the same directory."""
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


class JobStore:
    """Filesystem-backed store for asynchronous jobs."""

    def __init__(self, runtime_dir: str | Path) -> None:
        self.runtime_dir = Path(runtime_dir).resolve()
        self.jobs_dir = self.runtime_dir / "jobs"
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def create(self, kind: str, case_id: str, total: int = 0) -> dict[str, Any]:
        """Create a new job entry with status 'queued'."""
        if kind not in VALID_KINDS:
            raise ValueError(f"Invalid job kind '{kind}', must be one of {sorted(VALID_KINDS)}")

        job_id = f"J-{secrets.token_hex(6)}"
        now = _now_iso()
        record: dict[str, Any] = {
            "job_id": job_id,
            "kind": kind,
            "case_id": case_id,
            "status": "queued",
            "created_at": now,
            "updated_at": now,
            "progress": {
                "done": 0,
                "total": int(total),
                "current": None,
            },
            "errors": [],
            "result": {},
        }

        path = self.jobs_dir / f"{job_id}.json"
        with self._lock:
            _atomic_write_json(path, record)
        return record

    def get(self, job_id: str) -> dict[str, Any] | None:
        """Retrieve job record by job_id, or None if not found."""
        validate_job_id(job_id)
        path = self.jobs_dir / f"{job_id}.json"
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def update(self, job_id: str, **fields: Any) -> dict[str, Any]:
        """Atomically update fields of an existing job."""
        validate_job_id(job_id)
        path = self.jobs_dir / f"{job_id}.json"

        with self._lock:
            if not path.is_file():
                raise JobNotFoundError(f"Job not found: {job_id}")

            data = json.loads(path.read_text(encoding="utf-8"))
            data["updated_at"] = _now_iso()

            for key, val in fields.items():
                if key == "progress" and isinstance(val, dict):
                    data.setdefault("progress", {}).update(val)
                elif key == "status":
                    if val not in VALID_STATUSES:
                        raise ValueError(f"Invalid status '{val}', must be in {sorted(VALID_STATUSES)}")
                    data["status"] = val
                elif key == "errors" and isinstance(val, list):
                    data["errors"] = val
                else:
                    data[key] = val

            _atomic_write_json(path, data)
            return data

    def list_for_case(self, case_id: str) -> list[dict[str, Any]]:
        """List all jobs associated with a given case_id, sorted by created_at."""
        jobs: list[dict[str, Any]] = []
        if not self.jobs_dir.exists():
            return jobs

        for path in self.jobs_dir.glob("J-*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if data.get("case_id") == case_id:
                    jobs.append(data)
            except Exception:
                continue

        jobs.sort(key=lambda j: j.get("created_at", ""))
        return jobs


class JobRunner:
    """Single worker thread background job runner with task queue."""

    def __init__(self, job_store: JobStore | None = None) -> None:
        self.job_store = job_store
        self._queue: queue.Queue[tuple[Callable[[], Any], str] | None] = queue.Queue()
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker_thread.start()

    def _worker_loop(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                self._queue.task_done()
                break

            fn, job_id = item
            try:
                fn()
            except Exception:
                logger.exception("Job %s encountered unhandled error", job_id)
                if self.job_store is not None:
                    try:
                        self.job_store.update(
                            job_id,
                            status="failed",
                            errors=[{"doc_id": "", "code": "job_error", "message": "Internal job error"}],
                        )
                    except Exception:
                        pass
            finally:
                self._queue.task_done()

    def submit(self, fn: Callable[[], Any], job_id: str) -> None:
        """Submit a task to the worker queue."""
        self._queue.put((fn, job_id))

    def queue_length(self) -> int:
        """Return the number of pending tasks in the queue."""
        return self._queue.qsize()

    def shutdown(self, wait: bool = True) -> None:
        """Stop worker thread and wait for completion if wait is True."""
        self._queue.put(None)
        if wait:
            self._worker_thread.join(timeout=10.0)
