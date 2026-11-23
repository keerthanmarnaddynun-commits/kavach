"""Tests for atomic file operations and Windows replace retry logic."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import threading
import time
from typing import Any

import pytest

from kavach_api.atomic import replace_with_retry
from kavach_api.jobs import JobStore, _atomic_write_json as jobs_atomic_write_json
from kavach_api.storage import _atomic_write_json as storage_atomic_write_json


def test_replace_with_retry_permission_error_twice_succeeds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """(a) Patched os.replace raising PermissionError twice then working:
    the target holds the new content, exactly 3 calls.
    """
    src = tmp_path / "src.txt"
    dst = tmp_path / "dst.txt"
    src.write_text("new content", encoding="utf-8")
    dst.write_text("old content", encoding="utf-8")

    real_replace = os.replace
    call_count = 0

    def fake_replace(s: Any, d: Any) -> None:
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            raise PermissionError("[WinError 5] Access is denied")
        real_replace(s, d)

    monkeypatch.setattr(os, "replace", fake_replace)
    replace_with_retry(src, dst, attempts=5, delay=0.001)

    assert call_count == 3
    assert dst.read_text(encoding="utf-8") == "new content"
    assert not src.exists()


def test_atomic_write_json_always_raising_reraises_and_cleans_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """(b) Always raising: error re-raised after exactly attempts calls
    and no .tmp_ file is left in the folder (go through jobs._atomic_write_json).
    """
    target = tmp_path / "job.json"
    target.write_text("{}", encoding="utf-8")

    call_count = 0

    def fake_replace(s: Any, d: Any) -> None:
        nonlocal call_count
        call_count += 1
        raise PermissionError("[WinError 5] Access is denied")

    monkeypatch.setattr(os, "replace", fake_replace)
    monkeypatch.setattr(time, "sleep", lambda _s: None)

    with pytest.raises(PermissionError):
        jobs_atomic_write_json(target, {"status": "in_progress"})

    # Default attempts is 20
    assert call_count == 20
    tmp_files = list(tmp_path.glob("*.tmp_*"))
    assert tmp_files == []


def test_replace_with_retry_other_oserror_raised_immediately(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """(c) OSError that is not a PermissionError is raised at once (1 call)."""
    src = tmp_path / "src.txt"
    dst = tmp_path / "dst.txt"
    src.write_text("content", encoding="utf-8")

    call_count = 0

    def fake_replace(s: Any, d: Any) -> None:
        nonlocal call_count
        call_count += 1
        raise OSError("Disk quota exceeded")

    monkeypatch.setattr(os, "replace", fake_replace)
    with pytest.raises(OSError) as exc_info:
        replace_with_retry(src, dst, attempts=10, delay=0.001)

    assert not isinstance(exc_info.value, PermissionError)
    assert call_count == 1


def test_jobstore_stress_concurrent_update_and_get(tmp_path: Path) -> None:
    """(d) Stress: one thread calls JobStore.update 300 times on one job
    while another thread calls JobStore.get for the same job in a loop
    until the writer is done; no exception in either thread and the last
    read equals the last write.
    """
    store = JobStore(tmp_path)
    job = store.create(kind="analyze", case_id="C-0123456789", total=300)
    job_id = job["job_id"]

    writer_errors: list[Exception] = []
    reader_errors: list[Exception] = []
    stop_reader = threading.Event()
    last_read: dict[str, Any] | None = None

    def writer() -> None:
        try:
            for i in range(1, 301):
                store.update(job_id, progress={"done": i, "total": 300})
        except Exception as exc:
            writer_errors.append(exc)
        finally:
            stop_reader.set()

    def reader() -> None:
        nonlocal last_read
        try:
            while not stop_reader.is_set():
                res = store.get(job_id)
                if res is not None:
                    last_read = res
            res = store.get(job_id)
            if res is not None:
                last_read = res
        except Exception as exc:
            reader_errors.append(exc)

    t_writer = threading.Thread(target=writer)
    t_reader = threading.Thread(target=reader)

    t_reader.start()
    t_writer.start()

    t_writer.join(timeout=15.0)
    t_reader.join(timeout=15.0)

    assert not writer_errors, f"Writer failed: {writer_errors}"
    assert not reader_errors, f"Reader failed: {reader_errors}"
    assert last_read is not None
    assert last_read["progress"]["done"] == 300


def test_storage_stress_concurrent_write_and_read(tmp_path: Path) -> None:
    """(e) The same for storage JSON write vs read of one file."""
    target_file = tmp_path / "storage_file.json"
    storage_atomic_write_json(target_file, {"count": 0})

    writer_errors: list[Exception] = []
    reader_errors: list[Exception] = []
    stop_reader = threading.Event()
    last_read: dict[str, Any] | None = None

    def writer() -> None:
        try:
            for i in range(1, 301):
                storage_atomic_write_json(target_file, {"count": i})
        except Exception as exc:
            writer_errors.append(exc)
        finally:
            stop_reader.set()

    def reader() -> None:
        nonlocal last_read
        try:
            while not stop_reader.is_set():
                if target_file.is_file():
                    try:
                        content = json.loads(target_file.read_text(encoding="utf-8"))
                        last_read = content
                    except Exception:
                        pass
            if target_file.is_file():
                last_read = json.loads(target_file.read_text(encoding="utf-8"))
        except Exception as exc:
            reader_errors.append(exc)

    t_writer = threading.Thread(target=writer)
    t_reader = threading.Thread(target=reader)

    t_reader.start()
    t_writer.start()

    t_writer.join(timeout=15.0)
    t_reader.join(timeout=15.0)

    assert not writer_errors, f"Writer failed: {writer_errors}"
    assert not reader_errors, f"Reader failed: {reader_errors}"
    assert last_read is not None
    assert last_read["count"] == 300
