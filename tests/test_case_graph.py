"""Tests for case_graph builder, validator, and real-data invariants."""

from __future__ import annotations

import copy
import csv
from decimal import Decimal
import json
from pathlib import Path

from case_graph.builder import build_case_graph
from case_graph.validate import validate_graph
from scripts.build_case_graph import main as cli_main

REPO_ROOT = Path(__file__).resolve().parents[1]
REAL_FIR_DIR = REPO_ROOT / "results" / "2026-11-11_step6_extraction_r2" / "run1"
REAL_CDR_PATH = REPO_ROOT / "data" / "synthetic" / "out" / "case_demo_v2" / "cdr.csv"
REAL_BANK_PATH = REPO_ROOT / "data" / "synthetic" / "out" / "case_demo_v2" / "bank.csv"


def _write_fir(
    fir_dir: Path,
    fir_id: str,
    entities: list[dict],
    relationships: list[dict],
) -> None:
    payload = {
        "doc": {
            "case_id": "CASE_TEST",
            "entities": entities,
            "relationships": relationships,
            "schema_version": "1.1",
            "source_doc_id": fir_id,
        }
    }
    (fir_dir / f"{fir_id}.analysis.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )


def _person(
    ent_id: str,
    name: str,
    aliases: list[str] | None = None,
    span: list[int] | None = None,
    role: str = "SUSPECT",
) -> dict:
    s = span or [0, len(name)]
    mentions = [{"char_span": s, "kind": "NAME", "surface": name}]
    for i, al in enumerate(aliases or []):
        mentions.append({"char_span": [100 + i, 105 + i], "kind": "ALIAS", "surface": al})
    out: dict = {
        "ai_confidence": 0.95,
        "canonical_name": name,
        "char_span": s,
        "mentions": mentions,
        "role": role,
        "type": "PERSON",
        "id": ent_id,
    }
    if aliases:
        out["aliases"] = list(aliases)
    return out


def _ident(ent_id: str, etype: str, value: str, span: list[int] | None = None) -> dict:
    s = span or [20, 30]
    return {
        "ai_confidence": 0.99,
        "char_span": s,
        "mentions": [{"char_span": s, "kind": "VALUE", "surface": value}],
        "type": etype,
        "value": value,
        "id": ent_id,
    }


def _write_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        writer.writerows(rows)


def _empty_csvs(tmp_path: Path) -> tuple[Path, Path]:
    cdr_path = tmp_path / "cdr.csv"
    bank_path = tmp_path / "bank.csv"
    _write_csv(
        cdr_path,
        [
            "a_party",
            "b_party",
            "imei_a",
            "imsi_a",
            "start_time",
            "duration_sec",
            "call_type",
            "tower_id",
            "lat",
            "lon",
        ],
        [],
    )
    _write_csv(
        bank_path,
        ["txn_id", "datetime", "from_acct", "to_acct", "amount", "mode", "ifsc", "narration"],
        [],
    )
    return cdr_path, bank_path


def test_person_merge_same_name_shared_phone_merges(tmp_path: Path) -> None:
    fir_dir = tmp_path / "firs"
    fir_dir.mkdir()
    cdr_path, bank_path = _empty_csvs(tmp_path)

    _write_fir(
        fir_dir,
        "FIR_01",
        [
            _person("ent_01", "Vikas Sharma", aliases=["Bicky"], span=[10, 22]),
            _ident("ent_02", "PHONE", "9876543210"),
        ],
        [
            {
                "relation": "OWNS_DEVICE",
                "source": "ent_01",
                "target": "ent_02",
                "evidence_char_span": [0, 40],
            }
        ],
    )
    _write_fir(
        fir_dir,
        "FIR_02",
        [
            _person("ent_01", "vikas  sharma", aliases=["Viku"], span=[50, 63]),
            _ident("ent_02", "PHONE", "+91-9876543210"),
        ],
        [
            {
                "relation": "OWNS_DEVICE",
                "source": "ent_01",
                "target": "ent_02",
                "evidence_char_span": [45, 90],
            }
        ],
    )

    graph = build_case_graph(fir_dir, cdr_path, bank_path)
    assert validate_graph(graph) == []

    persons = [n for n in graph["nodes"] if n["type"] == "PERSON"]
    assert len(persons) == 1
    assert graph["stats"]["persons_before_merge"] == 2
    assert graph["stats"]["persons_after_merge"] == 1
    assert set(persons[0]["aliases"]) == {"Bicky", "Viku"}
    assert persons[0]["source_firs"] == ["FIR_01", "FIR_02"]
    assert len(persons[0]["evidence_spans"]) == 2


def test_person_merge_same_name_without_shared_id_does_not_merge(tmp_path: Path) -> None:
    fir_dir = tmp_path / "firs"
    fir_dir.mkdir()
    cdr_path, bank_path = _empty_csvs(tmp_path)

    _write_fir(
        fir_dir,
        "FIR_01",
        [
            _person("ent_01", "Vikas Sharma"),
            _ident("ent_02", "PHONE", "9876543210"),
        ],
        [{"relation": "OWNS_DEVICE", "source": "ent_01", "target": "ent_02", "evidence_char_span": [0, 20]}],
    )
    _write_fir(
        fir_dir,
        "FIR_02",
        [
            _person("ent_01", "Vikas Sharma"),
            _ident("ent_02", "PHONE", "9111111111"),
        ],
        [{"relation": "OWNS_DEVICE", "source": "ent_01", "target": "ent_02", "evidence_char_span": [0, 20]}],
    )

    graph = build_case_graph(fir_dir, cdr_path, bank_path)
    assert validate_graph(graph) == []
    persons = [n for n in graph["nodes"] if n["type"] == "PERSON"]
    assert len(persons) == 2
    assert graph["stats"]["persons_before_merge"] == 2
    assert graph["stats"]["persons_after_merge"] == 2


def test_person_merge_different_and_similar_names_stay_separate_on_shared_phone(
    tmp_path: Path,
) -> None:
    fir_dir = tmp_path / "firs"
    fir_dir.mkdir()
    cdr_path, bank_path = _empty_csvs(tmp_path)

    _write_fir(
        fir_dir,
        "FIR_01",
        [
            _person("ent_01", "Vikas Sharma"),
            _ident("ent_02", "PHONE", "9876543210"),
        ],
        [{"relation": "OWNS_DEVICE", "source": "ent_01", "target": "ent_02", "evidence_char_span": [0, 20]}],
    )
    _write_fir(
        fir_dir,
        "FIR_02",
        [
            _person("ent_01", "Bikas Sharma"),
            _ident("ent_02", "PHONE", "9876543210"),
        ],
        [{"relation": "OWNS_DEVICE", "source": "ent_01", "target": "ent_02", "evidence_char_span": [0, 20]}],
    )

    graph = build_case_graph(fir_dir, cdr_path, bank_path)
    assert validate_graph(graph) == []

    persons = [n for n in graph["nodes"] if n["type"] == "PERSON"]
    phones = [n for n in graph["nodes"] if n["type"] == "PHONE"]
    assert len(persons) == 2
    assert len(phones) == 1
    assert phones[0]["id"] == "PHONE:9876543210"

    owns_edges = [e for e in graph["edges"] if e["relation"] == "OWNS_DEVICE"]
    assert len(owns_edges) == 2
    assert {e["source"] for e in owns_edges} == {p["id"] for p in persons}
    assert {e["target"] for e in owns_edges} == {"PHONE:9876543210"}


def test_cdr_aggregation_symmetric_pairs_and_imei_direction(tmp_path: Path) -> None:
    fir_dir = tmp_path / "firs"
    fir_dir.mkdir()
    cdr_path, bank_path = _empty_csvs(tmp_path)

    _write_csv(
        cdr_path,
        [
            "a_party",
            "b_party",
            "imei_a",
            "imsi_a",
            "start_time",
            "duration_sec",
            "call_type",
            "tower_id",
            "lat",
            "lon",
        ],
        [
            ["9800000002", "9800000001", "111111111111111", "1", "2026-01-01T10:00:00", "45", "VOICE", "T1", "0", "0"],
            ["9800000001", "9800000002", "222222222222222", "2", "2026-01-01T08:00:00", "0", "SMS", "T2", "0", "0"],
            ["9800000002", "9800000001", "111111111111111", "1", "2026-01-01T12:30:00", "55", "VOICE", "T1", "0", "0"],
            ["9800000001", "9800000001", "222222222222222", "2", "2026-01-01T13:00:00", "10", "VOICE", "T1", "0", "0"],
        ],
    )

    graph = build_case_graph(fir_dir, cdr_path, bank_path)
    assert validate_graph(graph) == []
    assert graph["stats"]["cdr_rows_read"] == 4
    assert graph["stats"]["cdr_rows_skipped"] == 1

    comm_edges = [e for e in graph["edges"] if e["relation"] == "COMMUNICATED_WITH"]
    assert len(comm_edges) == 1
    ce = comm_edges[0]
    assert ce["source"] == "PHONE:9800000001"
    assert ce["target"] == "PHONE:9800000002"
    assert ce["source_kind"] == "CSV"
    assert ce["source_file"] == "cdr.csv"
    assert ce["voice_count"] == 2
    assert ce["sms_count"] == 1
    assert ce["total_duration_sec"] == 100
    assert ce["first_time"] == "2026-01-01T08:00:00"
    assert ce["last_time"] == "2026-01-01T12:30:00"
    assert ce["row_numbers"] == [1, 2, 3]

    imei_edges = [e for e in graph["edges"] if e["relation"] == "ASSOCIATED_IMEI"]
    assert len(imei_edges) == 2
    by_src = {e["source"]: e for e in imei_edges}
    assert by_src["PHONE:9800000002"]["target"] == "IMEI:111111111111111"
    assert by_src["PHONE:9800000002"]["row_count"] == 2
    assert by_src["PHONE:9800000002"]["row_numbers"] == [1, 3]
    assert by_src["PHONE:9800000001"]["target"] == "IMEI:222222222222222"
    assert by_src["PHONE:9800000001"]["row_count"] == 1
    assert by_src["PHONE:9800000001"]["row_numbers"] == [2]


def test_bank_aggregation_exact_paise_direction_and_leading_zeros(tmp_path: Path) -> None:
    fir_dir = tmp_path / "firs"
    fir_dir.mkdir()
    cdr_path, bank_path = _empty_csvs(tmp_path)

    _write_csv(
        bank_path,
        ["txn_id", "datetime", "from_acct", "to_acct", "amount", "mode", "ifsc", "narration"],
        [
            ["TX1", "2026-01-02T09:00:00", "00123456789", "000987654321", "0.10", "UPI", "SBIN0000001", "n1"],
            ["TX2", "2026-01-02T11:00:00", "00123456789", "000987654321", "0.20", "IMPS", "SBIN0000001", "n2"],
            ["TX3", "2026-01-02T12:00:00", "000987654321", "00123456789", "100.05", "NEFT", "HDFC0000001", "n3"],
        ],
    )

    graph = build_case_graph(fir_dir, cdr_path, bank_path)
    assert validate_graph(graph) == []

    acct_nodes = {n["id"]: n for n in graph["nodes"] if n["type"] == "ACCOUNT"}
    assert "ACCOUNT:00123456789" in acct_nodes
    assert "ACCOUNT:000987654321" in acct_nodes
    assert acct_nodes["ACCOUNT:00123456789"]["value"] == "00123456789"

    tx_edges = [e for e in graph["edges"] if e["relation"] == "TRANSFERRED_FUNDS"]
    assert len(tx_edges) == 2
    by_pair = {(e["source"], e["target"]): e for e in tx_edges}

    fwd = by_pair[("ACCOUNT:00123456789", "ACCOUNT:000987654321")]
    assert fwd["txn_count"] == 2
    assert fwd["total_amount_paise"] == 30
    assert fwd["total_amount"] == "0.30"
    assert fwd["modes"] == ["IMPS", "UPI"]
    assert fwd["first_time"] == "2026-01-02T09:00:00"
    assert fwd["last_time"] == "2026-01-02T11:00:00"
    assert fwd["source_file"] == "bank.csv"
    assert fwd["row_numbers"] == [1, 2]

    rev = by_pair[("ACCOUNT:000987654321", "ACCOUNT:00123456789")]
    assert rev["txn_count"] == 1
    assert rev["total_amount_paise"] == 10005
    assert rev["total_amount"] == "100.05"
    assert rev["modes"] == ["NEFT"]
    assert rev["row_numbers"] == [3]


def test_validator_catches_dangling_and_duplicate_edges() -> None:
    base = {
        "nodes": [
            {"id": "PHONE:9800000001", "type": "PHONE"},
            {"id": "PHONE:9800000002", "type": "PHONE"},
        ],
        "edges": [
            {
                "source": "PHONE:9800000001",
                "target": "PHONE:9800000002",
                "relation": "COMMUNICATED_WITH",
                "source_kind": "CSV",
                "row_numbers": [1],
            }
        ],
    }
    assert validate_graph(base) == []

    dangling = copy.deepcopy(base)
    dangling["edges"].append(
        {
            "source": "PHONE:9800000001",
            "target": "IMEI:999999999999999",
            "relation": "ASSOCIATED_IMEI",
            "source_kind": "FIR",
        }
    )
    errs_dangling = validate_graph(dangling)
    assert any("dangling" in e.lower() for e in errs_dangling)

    dup = copy.deepcopy(base)
    dup["edges"].append(copy.deepcopy(base["edges"][0]))
    errs_dup = validate_graph(dup)
    assert any("duplicate" in e.lower() for e in errs_dup)


def test_deterministic_builds_identical_json(tmp_path: Path) -> None:
    fir_dir = tmp_path / "firs"
    fir_dir.mkdir()
    cdr_path, bank_path = _empty_csvs(tmp_path)

    _write_fir(
        fir_dir,
        "FIR_01",
        [
            _person("ent_01", "Ramesh Chand", aliases=["Ramu"]),
            _ident("ent_02", "PHONE", "9800000001"),
        ],
        [{"relation": "OWNS_DEVICE", "source": "ent_01", "target": "ent_02", "evidence_char_span": [0, 20]}],
    )
    _write_csv(
        cdr_path,
        ["a_party", "b_party", "imei_a", "imsi_a", "start_time", "duration_sec", "call_type", "tower_id", "lat", "lon"],
        [["9800000001", "9800000002", "111111111111111", "1", "2026-01-01T00:00:00", "10", "VOICE", "T1", "0", "0"]],
    )
    _write_csv(
        bank_path,
        ["txn_id", "datetime", "from_acct", "to_acct", "amount", "mode", "ifsc", "narration"],
        [["TX1", "2026-01-01T00:00:00", "0011223344", "9988776655", "50.25", "UPI", "SBIN0000001", "test"]],
    )

    g1 = build_case_graph(fir_dir, cdr_path, bank_path)
    g2 = build_case_graph(fir_dir, cdr_path, bank_path)
    j1 = json.dumps(g1, indent=2, sort_keys=True, ensure_ascii=False)
    j2 = json.dumps(g2, indent=2, sort_keys=True, ensure_ascii=False)
    assert j1 == j2


def test_cli_refuses_existing_output_dir(tmp_path: Path) -> None:
    fir_dir = tmp_path / "firs"
    fir_dir.mkdir()
    cdr_path, bank_path = _empty_csvs(tmp_path)
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    rc = cli_main(
        [
            "--fir-dir",
            str(fir_dir),
            "--cdr",
            str(cdr_path),
            "--bank",
            str(bank_path),
            "--out-dir",
            str(out_dir),
        ]
    )
    assert rc != 0


def test_real_files_invariants_and_determinism() -> None:
    g1 = build_case_graph(REAL_FIR_DIR, REAL_CDR_PATH, REAL_BANK_PATH)
    g2 = build_case_graph(REAL_FIR_DIR, REAL_CDR_PATH, REAL_BANK_PATH)

    assert validate_graph(g1) == []
    assert json.dumps(g1, indent=2, sort_keys=True, ensure_ascii=False) == json.dumps(
        g2, indent=2, sort_keys=True, ensure_ascii=False
    )

    stats = g1["stats"]
    cdr_comm_edges = [
        e
        for e in g1["edges"]
        if e["relation"] == "COMMUNICATED_WITH" and e["source_kind"] == "CSV"
    ]
    assert (
        sum(e["voice_count"] + e["sms_count"] for e in cdr_comm_edges)
        + stats["cdr_rows_skipped"]
        == stats["cdr_rows_read"]
    )

    bank_edges = [
        e
        for e in g1["edges"]
        if e["relation"] == "TRANSFERRED_FUNDS" and e["source_kind"] == "CSV"
    ]
    assert sum(e["txn_count"] for e in bank_edges) == stats["bank_rows_read"]

    expected_paise = 0
    with REAL_BANK_PATH.open("r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            expected_paise += int((Decimal(row["amount"].strip()) * 100))

    assert sum(e["total_amount_paise"] for e in bank_edges) == expected_paise


def test_case_graph_source_never_mentions_truth() -> None:
    case_graph_dir = REPO_ROOT / "case_graph"
    for py_file in case_graph_dir.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8").lower()
        assert "truth" not in content


def test_validator_accepts_same_as_candidate_rule_edge() -> None:
    graph = {
        "nodes": [
            {"id": "PERSON:FIR_01:ent_01", "type": "PERSON"},
            {"id": "PERSON:FIR_02:ent_01", "type": "PERSON"},
        ],
        "edges": [
            {
                "source": "PERSON:FIR_02:ent_01",
                "target": "PERSON:FIR_01:ent_01",
                "relation": "SAME_AS_CANDIDATE",
                "source_kind": "RULE",
                "reasons": ["same_name"],
            }
        ],
    }
    assert validate_graph(graph) == []


