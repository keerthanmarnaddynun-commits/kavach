"""Unit tests for kavach_api settings and storage modules."""
from __future__ import annotations

import concurrent.futures
import hashlib
from pathlib import Path
import pytest

from kavach_api.settings import (
    Settings,
    load_settings,
    repo_root,
    DEFAULT_CORS_ORIGINS,
    DEFAULT_JWT_TTL_MINUTES,
    DEFAULT_PBKDF2_ITERATIONS,
    DEFAULT_MAX_UPLOAD_BYTES,
)
from kavach_api.storage import (
    Store,
    InvalidIdError,
    DuplicateDocument,
    CaseNotFoundError,
    DocumentNotFoundError,
    StorageError,
    validate_case_id,
    validate_doc_id,
    safe_stem,
)


def test_settings_defaults():
    """Settings load defaults when environment is empty."""
    s = load_settings(env={})
    assert s.runtime_dir == repo_root() / "runtime"
    assert s.cors_origins == DEFAULT_CORS_ORIGINS
    assert s.jwt_ttl_minutes == DEFAULT_JWT_TTL_MINUTES
    assert s.pbkdf2_iterations == DEFAULT_PBKDF2_ITERATIONS
    assert s.max_upload_bytes == DEFAULT_MAX_UPLOAD_BYTES


def test_settings_env_overrides(tmp_path):
    """Settings properly parse environment variable overrides."""
    env = {
        "KAVACH_RUNTIME_DIR": str(tmp_path / "custom_runtime"),
        "KAVACH_CORS_ORIGINS": "http://example.com, https://test.local",
        "KAVACH_JWT_TTL_MIN": "120",
        "KAVACH_PBKDF2_ITERATIONS": "50000",
        "KAVACH_MAX_UPLOAD_BYTES": "10485760",
    }
    s = load_settings(env=env)
    assert s.runtime_dir == (tmp_path / "custom_runtime").resolve()
    assert s.cors_origins == ("http://example.com", "https://test.local")
    assert s.jwt_ttl_minutes == 120
    assert s.pbkdf2_iterations == 50000
    assert s.max_upload_bytes == 10485760


def test_id_validation_rejects_invalid_patterns():
    """ID validators reject path traversals, malformed patterns, unicode, and casing."""
    invalid_cases = [
        "../x",
        "C-1",
        "C-012345678",        # too short (9 chars)
        "C-0123456789a",      # too long (11 chars)
        "C-012345678G",       # non-hex char
        "C-ABCDEF0123",       # uppercase hex
        "/etc/passwd",        # absolute path
        "C-01234\u04306789",  # cyrillic look-alike 'a'
        "",
        None,
    ]
    for cid in invalid_cases:
        with pytest.raises(InvalidIdError):
            validate_case_id(cid)  # type: ignore

    invalid_docs = [
        "../bad",
        "DOC/1",
        "with space",
        "a" * 41,             # length > 40
        "unicode_नाम",
        "",
        None,
    ]
    for did in invalid_docs:
        with pytest.raises(InvalidIdError):
            validate_doc_id(did)  # type: ignore


def test_case_lifecycle(tmp_path):
    """Test create, get, list cases in storage."""
    settings = Settings(runtime_dir=tmp_path)
    store = Store(settings)

    assert store.list_cases() == []

    c1 = store.create_case(name="Case Alpha", created_by="officer1", synthetic=False)
    assert c1["case_id"].startswith("C-")
    assert len(c1["case_id"]) == 12
    assert c1["name"] == "Case Alpha"
    assert c1["created_by"] == "officer1"
    assert not c1["synthetic"]

    c1_read = store.get_case(c1["case_id"])
    assert c1_read["case_id"] == c1["case_id"]
    assert c1_read["name"] == "Case Alpha"

    cases_list = store.list_cases()
    assert len(cases_list) == 1
    assert cases_list[0]["case_id"] == c1["case_id"]
    assert cases_list[0]["counts"]["documents"] == 0
    assert not cases_list[0]["analyzed"]


def test_document_store_exact_bytes_and_crlf_hindi(tmp_path):
    """Document store keeps exact characters including Hindi text with CRLF line endings."""
    settings = Settings(runtime_dir=tmp_path)
    store = Store(settings)
    case = store.create_case("Hindi Case", "analyst")
    cid = case["case_id"]

    # Hindi text with CRLF line endings and a UTF-8 BOM
    raw_text = "प्रथम सूचना रिपोर्ट\r\nधारा 420 भा.दं.सं.\r\nआरोपी: विकास कुमार"
    raw_bytes = b"\xef\xbb\xbf" + raw_text.encode("utf-8")

    meta = store.add_document(cid, "FIR_hindi.txt", raw_bytes, "analyst")
    assert meta["doc_id"] == "FIR_hindi"
    assert meta["chars"] == len(raw_text)

    # Read back document
    read_meta, read_text = store.get_document(cid, meta["doc_id"])
    assert read_meta["doc_id"] == meta["doc_id"]
    assert read_text == raw_text

    # sha256_text must equal the hash of the bytes on disk
    doc_path = store.case_dir(cid) / "documents" / f"{meta['doc_id']}.txt"
    disk_bytes = doc_path.read_bytes()
    assert hashlib.sha256(disk_bytes).hexdigest() == meta["sha256_text"]
    assert disk_bytes == raw_text.encode("utf-8")


def test_duplicate_document_rejection(tmp_path):
    """Uploading identical raw bytes in the same case raises DuplicateDocument with existing doc_id."""
    settings = Settings(runtime_dir=tmp_path)
    store = Store(settings)
    case = store.create_case("Dup Test", "analyst")
    cid = case["case_id"]

    raw = b"Sample FIR text payload"
    meta1 = store.add_document(cid, "doc1.txt", raw, "analyst")

    with pytest.raises(DuplicateDocument) as exc_info:
        store.add_document(cid, "doc2_different_name.txt", raw, "analyst")
    assert exc_info.value.doc_id == meta1["doc_id"]


def test_doc_id_generation_odd_filenames(tmp_path):
    """Odd filenames (spaces, unicode, .., very long) fall back to DOC-0001 or clean stem."""
    settings = Settings(runtime_dir=tmp_path)
    store = Store(settings)
    case = store.create_case("Naming Test", "analyst")
    cid = case["case_id"]

    # Space in name -> safe_stem empty -> DOC-0001
    m1 = store.add_document(cid, "my test file.txt", b"content 1", "user")
    assert m1["doc_id"] == "DOC-0001"

    # Unicode in stem -> safe_stem empty -> DOC-0002
    m2 = store.add_document(cid, "जांच_रिपोर्ट.txt", b"content 2", "user")
    assert m2["doc_id"] == "DOC-0002"

    # Relative dots -> safe_stem empty -> DOC-0003
    m3 = store.add_document(cid, "..txt", b"content 3", "user")
    assert m3["doc_id"] == "DOC-0003"

    # Very long name (>40 chars) -> safe_stem empty -> DOC-0004
    long_name = ("a" * 45) + ".txt"
    m4 = store.add_document(cid, long_name, b"content 4", "user")
    assert m4["doc_id"] == "DOC-0004"

    # Normal name
    m5 = store.add_document(cid, "FIR_01.txt", b"content 5", "user")
    assert m5["doc_id"] == "FIR_01"

    # Duplicate name with different content -> appends -2
    m6 = store.add_document(cid, "FIR_01.txt", b"content 6 (diff)", "user")
    assert m6["doc_id"] == "FIR_01-2"


def test_atomic_write_leaves_no_temp_file(tmp_path):
    """Atomic write completes without leaving temporary files in directory."""
    settings = Settings(runtime_dir=tmp_path)
    store = Store(settings)
    case = store.create_case("Atomic Case", "user")
    cid = case["case_id"]

    cdir = store.case_dir(cid)
    store.add_document(cid, "test.txt", b"Atomic test content", "user")

    # Check for temporary files in case dir and subdirs
    for p in cdir.rglob("*.tmp*"):
        assert not p.exists() or not p.is_file()


def test_concurrent_document_addition(tmp_path):
    """Two concurrent threads adding documents to the same case never produce identical doc ids."""
    settings = Settings(runtime_dir=tmp_path)
    store = Store(settings)
    case = store.create_case("Concurrency Case", "user")
    cid = case["case_id"]

    doc_ids = []

    def add_doc(idx: int):
        content = f"Unique content for thread {idx}".encode("utf-8")
        filename = f"concurrent_doc.txt"  # same filename -> test collision resolution
        m = store.add_document(cid, filename, content, "user")
        return m["doc_id"]

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(add_doc, i) for i in range(20)]
        for f in concurrent.futures.as_completed(futures):
            doc_ids.append(f.result())

    assert len(doc_ids) == 20
    assert len(set(doc_ids)) == 20


def test_case_directory_never_outside_runtime_dir(tmp_path):
    """Store prevents case directory escape outside runtime_dir."""
    settings = Settings(runtime_dir=tmp_path)
    store = Store(settings)

    with pytest.raises(InvalidIdError):
        store.case_dir("../../etc")

    with pytest.raises(InvalidIdError):
        store.case_dir("C-123456789g")


def test_csv_and_analysis_storage(tmp_path):
    """CSV saving, files_info, analysis saving and loading work as expected."""
    settings = Settings(runtime_dir=tmp_path)
    store = Store(settings)
    case = store.create_case("CSV Case", "analyst")
    cid = case["case_id"]

    # Save CDR
    cdr_data = b"a_party,b_party\n9999999999,8888888888\n"
    store.save_csv(cid, "cdr", cdr_data, report={"rows": 1, "columns": ["a_party", "b_party"]})

    finfo = store.files_info(cid)
    assert finfo["cdr"]["rows"] == 1
    assert finfo["cdr"]["sha256"] == hashlib.sha256(cdr_data).hexdigest()
    assert finfo["bank"] is None

    # CSV path
    assert store.csv_path(cid, "cdr").exists()
    assert store.csv_path(cid, "cdr").read_bytes() == cdr_data

    # Save and load analysis
    analysis_data = {"doc": {"entities": []}, "aux": {}, "info": {"status": "ok"}}
    store.save_analysis(cid, "DOC-0001", analysis_data)
    loaded = store.load_analyses(cid)
    assert "DOC-0001" in loaded
    assert loaded["DOC-0001"]["info"]["status"] == "ok"

    # Set document status
    store.add_document(cid, "doc1.txt", b"text doc", "analyst")
    store.set_document_status(cid, "doc1", "extracted")
    meta, _ = store.get_document(cid, "doc1")
    assert meta["status"] == "extracted"

    # Derived path
    dpath = store.derived_path(cid, "graph.json")
    assert dpath.name == "graph.json"
    with pytest.raises(StorageError):
        store.derived_path(cid, "../outside.json")
