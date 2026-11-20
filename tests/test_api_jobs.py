"""Unit tests for JobStore and JobRunner."""
from __future__ import annotations

from pathlib import Path
import threading
import time
import pytest

from kavach_api.jobs import (
    InvalidJobIdError,
    JobNotFoundError,
    JobRunner,
    JobStore,
    validate_job_id,
)


@pytest.fixture
def temp_job_store(tmp_path: Path) -> JobStore:
    """Fixture providing JobStore with temporary runtime directory."""
    return JobStore(tmp_path / "runtime")


def test_validate_job_id() -> None:
    """Job ID validation strictly matches ^J-[0-9a-f]{12}\\Z."""
    valid_id = "J-0123456789ab"
    assert validate_job_id(valid_id) == valid_id

    # Rejects trailing newline
    with pytest.raises(InvalidJobIdError):
        validate_job_id("J-0123456789ab\n")

    # Rejects invalid lengths or characters
    with pytest.raises(InvalidJobIdError):
        validate_job_id("J-012345")
    with pytest.raises(InvalidJobIdError):
        validate_job_id("J-0123456789abxyz")
    with pytest.raises(InvalidJobIdError):
        validate_job_id("C-0123456789ab")


def test_job_store_lifecycle(temp_job_store: JobStore) -> None:
    """Job creation, retrieval, updates, and filtering for a case."""
    case_id = "C-0123456789"
    job = temp_job_store.create(kind="extract", case_id=case_id, total=5)
    job_id = job["job_id"]

    assert job["kind"] == "extract"
    assert job["case_id"] == case_id
    assert job["status"] == "queued"
    assert job["progress"]["total"] == 5
    assert job["progress"]["done"] == 0
    assert job["progress"]["current"] is None

    # Fetch
    fetched = temp_job_store.get(job_id)
    assert fetched is not None
    assert fetched["job_id"] == job_id

    # Update status and progress
    updated = temp_job_store.update(
        job_id,
        status="running",
        progress={"done": 2, "current": "DOC_002"},
    )
    assert updated["status"] == "running"
    assert updated["progress"]["done"] == 2
    assert updated["progress"]["current"] == "DOC_002"

    # Non-existent job
    assert temp_job_store.get("J-ffffffffffff") is None
    with pytest.raises(JobNotFoundError):
        temp_job_store.update("J-ffffffffffff", status="done")

    # Invalid status
    with pytest.raises(ValueError):
        temp_job_store.update(job_id, status="invalid_status")


def test_job_store_list_for_case(temp_job_store: JobStore) -> None:
    """Jobs list filters by case_id."""
    c1 = "C-1111111111"
    c2 = "C-2222222222"

    j1 = temp_job_store.create(kind="extract", case_id=c1, total=1)
    j2 = temp_job_store.create(kind="analyze", case_id=c1, total=2)
    j3 = temp_job_store.create(kind="extract", case_id=c2, total=3)

    c1_jobs = temp_job_store.list_for_case(c1)
    assert len(c1_jobs) == 2
    c1_ids = [j["job_id"] for j in c1_jobs]
    assert j1["job_id"] in c1_ids
    assert j2["job_id"] in c1_ids

    c2_jobs = temp_job_store.list_for_case(c2)
    assert len(c2_jobs) == 1
    assert c2_jobs[0]["job_id"] == j3["job_id"]


def test_job_runner_execution_and_queue_length(temp_job_store: JobStore) -> None:
    """JobRunner executes submitted tasks sequentially and tracks queue length."""
    runner = JobRunner(job_store=temp_job_store)
    executed = []
    done_event = threading.Event()

    def task() -> None:
        executed.append("task_done")
        done_event.set()

    runner.submit(task, "J-000000000001")
    assert done_event.wait(timeout=5.0) is True
    assert executed == ["task_done"]

    runner.shutdown(wait=True)
    assert runner.queue_length() == 0


def test_job_runner_survives_exception(temp_job_store: JobStore) -> None:
    """JobRunner catches task exceptions, marks job failed, and processes subsequent tasks."""
    runner = JobRunner(job_store=temp_job_store)

    job1 = temp_job_store.create(kind="extract", case_id="C-1111111111", total=1)
    job2 = temp_job_store.create(kind="extract", case_id="C-1111111111", total=1)

    event2 = threading.Event()
    results = []

    def task1_failing() -> None:
        raise RuntimeError("Deliberate failure in task 1")

    def task2_success() -> None:
        results.append("task2_ok")
        event2.set()

    runner.submit(task1_failing, job1["job_id"])
    runner.submit(task2_success, job2["job_id"])

    assert event2.wait(timeout=5.0) is True
    assert results == ["task2_ok"]

    # Check that job1 was marked failed in job_store
    j1_record = temp_job_store.get(job1["job_id"])
    assert j1_record is not None
    assert j1_record["status"] == "failed"

    runner.shutdown(wait=True)
