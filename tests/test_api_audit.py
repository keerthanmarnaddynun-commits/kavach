"""Unit tests for kavach_api audit log module."""
from __future__ import annotations

import concurrent.futures
import json
from pathlib import Path
import pytest

from kavach_api.audit import AuditLog, GENESIS_PREV_HASH


def test_audit_empty_log(tmp_path):
    """Empty audit log verifies as valid with 0 entries."""
    log_file = tmp_path / "audit.log.jsonl"
    audit = AuditLog(log_file)
    ok, count, bad_idx = audit.verify()
    assert ok is True
    assert count == 0
    assert bad_idx is None
    assert audit.read() == []


def test_audit_sequential_append_and_verify(tmp_path):
    """Sequential audit log appends construct a valid hash chain."""
    log_file = tmp_path / "audit.log.jsonl"
    audit = AuditLog(log_file)

    e1 = audit.append("user1", "analyst", "case_created", case_id="C-0123456789", detail={"name": "Alpha"})
    assert e1["seq"] == 1
    assert e1["prev_hash"] == GENESIS_PREV_HASH

    e2 = audit.append("user2", "viewer", "case_opened", case_id="C-0123456789")
    assert e2["seq"] == 2
    assert e2["prev_hash"] == e1["hash"]

    e3 = audit.append("admin", "admin", "user_created", detail={"username": "new_user"})
    assert e3["seq"] == 3
    assert e3["prev_hash"] == e2["hash"]

    ok, count, bad_idx = audit.verify()
    assert ok is True
    assert count == 3
    assert bad_idx is None

    # Test pagination
    read_all = audit.read(limit=10, offset=0)
    assert len(read_all) == 3
    read_slice = audit.read(limit=1, offset=1)
    assert len(read_slice) == 1
    assert read_slice[0]["seq"] == 2


def test_tampering_one_character_in_middle_fails_verify(tmp_path):
    """Tampering with a single character in a middle entry breaks verification at that index."""
    log_file = tmp_path / "audit.log.jsonl"
    audit = AuditLog(log_file)

    for i in range(5):
        audit.append(f"user_{i}", "analyst", "action_test", detail={"index": i})

    ok, count, bad_idx = audit.verify()
    assert ok is True
    assert count == 5

    # Modify line 2 (the 3rd entry, index 2)
    lines = log_file.read_text(encoding="utf-8").splitlines()
    entry = json.loads(lines[2])
    entry["detail"]["index"] = 999  # Tamper payload
    lines[2] = json.dumps(entry, sort_keys=True, separators=(",", ":"))
    log_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    ok, checked, bad_idx = audit.verify()
    assert ok is False
    assert bad_idx == 2


def test_deleting_middle_line_fails_verify(tmp_path):
    """Deleting an entry in the middle breaks sequential numbering and hash chaining."""
    log_file = tmp_path / "audit.log.jsonl"
    audit = AuditLog(log_file)

    for i in range(5):
        audit.append(f"user_{i}", "analyst", "action_test", detail={"index": i})

    # Delete line index 2
    lines = log_file.read_text(encoding="utf-8").splitlines()
    del lines[2]
    log_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    ok, checked, bad_idx = audit.verify()
    assert ok is False
    assert bad_idx == 2


def test_concurrent_multithreaded_appends(tmp_path):
    """8 concurrent threads appending entries produce strictly sequential 1..N entries and a valid chain."""
    log_file = tmp_path / "audit.log.jsonl"
    audit = AuditLog(log_file)

    n_threads = 8
    n_per_thread = 25
    total = n_threads * n_per_thread

    def worker(worker_id: int):
        for i in range(n_per_thread):
            audit.append(f"worker_{worker_id}", "analyst", "log_entry", detail={"msg": i})

    with concurrent.futures.ThreadPoolExecutor(max_workers=n_threads) as executor:
        futures = [executor.submit(worker, i) for i in range(n_threads)]
        concurrent.futures.wait(futures)

    ok, count, bad_idx = audit.verify()
    assert ok is True
    assert count == total
    assert bad_idx is None

    entries = audit.read(limit=total + 10, offset=0)
    assert len(entries) == total
    seqs = [e["seq"] for e in entries]
    assert seqs == list(range(1, total + 1))
