"""Tests for suspect person merging rules, candidate links, and merge evaluation."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from case_graph.builder import build_case_graph
from case_graph.validate import validate_graph
from scripts.eval_person_merge import evaluate_person_merge, main as eval_main

REPO_ROOT = Path(__file__).resolve().parents[1]


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
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _person(
    ent_id: str,
    name: str,
    father: str | None = None,
    role: str = "SUSPECT",
    span: list[int] | None = None,
) -> dict:
    s = span or [0, len(name)]
    mentions = [{"char_span": s, "kind": "NAME", "surface": name}]
    if father:
        mentions.append({"char_span": [50, 50 + len(father)], "kind": "FATHER", "surface": father})
    out: dict = {
        "ai_confidence": 0.95,
        "canonical_name": name,
        "char_span": s,
        "mentions": mentions,
        "role": role,
        "type": "PERSON",
        "id": ent_id,
    }
    if father:
        out["father_name"] = father
    return out


def _phone(ent_id: str, value: str) -> dict:
    return {
        "ai_confidence": 0.99,
        "char_span": [100, 110],
        "mentions": [{"char_span": [100, 110], "kind": "VALUE", "surface": value}],
        "type": "PHONE",
        "value": value,
        "id": ent_id,
    }


def test_rule_a_same_name_same_father_merges_and_different_father_blocks(
    tmp_path: Path,
) -> None:
    fir_dir = tmp_path / "firs"
    fir_dir.mkdir()
    cdr_path, bank_path = _empty_csvs(tmp_path)

    _write_fir(fir_dir, "FIR_01", [_person("ent_01", "Ramesh Chand", father="Mohan Lal")], [])
    _write_fir(fir_dir, "FIR_02", [_person("ent_01", "ramesh chand", father="mohan lal")], [])
    _write_fir(fir_dir, "FIR_03", [_person("ent_01", "Ramesh Chand", father="Sohan Lal")], [])

    graph = build_case_graph(fir_dir, cdr_path, bank_path)
    assert validate_graph(graph) == []

    persons = [n for n in graph["nodes"] if n["type"] == "PERSON"]
    assert len(persons) == 2
    assert graph["stats"]["merges_by_rule"]["rule_A"] == 1
    assert graph["stats"]["blocked_by_father_conflict"] >= 1
    assert graph["stats"]["same_as_candidate_edges"] == 0


def test_non_suspect_keeps_old_rule_only(tmp_path: Path) -> None:
    fir_dir = tmp_path / "firs"
    fir_dir.mkdir()
    cdr_path, bank_path = _empty_csvs(tmp_path)

    _write_fir(
        fir_dir,
        "FIR_01",
        [_person("ent_01", "Ramesh Chand", father="Mohan Lal", role="OFFICER")],
        [],
    )
    _write_fir(
        fir_dir,
        "FIR_02",
        [_person("ent_01", "Ramesh Chand", father="Mohan Lal", role="OFFICER")],
        [],
    )

    graph = build_case_graph(fir_dir, cdr_path, bank_path)
    assert validate_graph(graph) == []
    persons = [n for n in graph["nodes"] if n["type"] == "PERSON"]
    assert len(persons) == 2
    assert graph["stats"]["merges_by_rule"]["rule_A"] == 0


def test_rule_b_cross_script_with_and_without_strong_id(tmp_path: Path) -> None:
    fir_dir = tmp_path / "firs"
    fir_dir.mkdir()
    cdr_path, bank_path = _empty_csvs(tmp_path)

    _write_fir(
        fir_dir,
        "FIR_01",
        [_person("ent_01", "Vikas Sharma"), _phone("ent_02", "9876543210")],
        [{"relation": "OWNS_DEVICE", "source": "ent_01", "target": "ent_02", "evidence_char_span": [0, 20]}],
    )
    _write_fir(
        fir_dir,
        "FIR_02",
        [_person("ent_01", "विकास शर्मा"), _phone("ent_02", "9876543210")],
        [{"relation": "OWNS_DEVICE", "source": "ent_01", "target": "ent_02", "evidence_char_span": [0, 20]}],
    )

    g_merged = build_case_graph(fir_dir, cdr_path, bank_path)
    assert validate_graph(g_merged) == []
    assert g_merged["stats"]["persons_after_merge"] == 1
    assert g_merged["stats"]["merges_by_rule"]["rule_B"] == 1

    # Without a shared strong ID: does not merge, creates cross-script candidate link.
    fir_dir_2 = tmp_path / "firs2"
    fir_dir_2.mkdir()
    _write_fir(fir_dir_2, "FIR_01", [_person("ent_01", "Vikas Sharma")], [])
    _write_fir(fir_dir_2, "FIR_02", [_person("ent_01", "विकास शर्मा")], [])

    g_unmerged = build_case_graph(fir_dir_2, cdr_path, bank_path)
    assert validate_graph(g_unmerged) == []
    assert g_unmerged["stats"]["persons_after_merge"] == 2
    assert g_unmerged["stats"]["merges_by_rule"]["rule_B"] == 0
    assert g_unmerged["stats"]["same_as_candidate_edges"] == 1
    cand = [e for e in g_unmerged["edges"] if e["relation"] == "SAME_AS_CANDIDATE"]
    assert cand[0]["reasons"] == ["cross_script_name"]


def test_vikas_and_bikas_stay_apart_in_both_scripts(tmp_path: Path) -> None:
    fir_dir = tmp_path / "firs"
    fir_dir.mkdir()
    cdr_path, bank_path = _empty_csvs(tmp_path)

    shared_phone = "9876543210"
    _write_fir(
        fir_dir,
        "FIR_01",
        [_person("ent_01", "Vikas Sharma"), _phone("ent_02", shared_phone)],
        [{"relation": "OWNS_DEVICE", "source": "ent_01", "target": "ent_02", "evidence_char_span": [0, 20]}],
    )
    _write_fir(
        fir_dir,
        "FIR_02",
        [_person("ent_01", "Bikas Sharma"), _phone("ent_02", shared_phone)],
        [{"relation": "OWNS_DEVICE", "source": "ent_01", "target": "ent_02", "evidence_char_span": [0, 20]}],
    )
    _write_fir(
        fir_dir,
        "FIR_03",
        [_person("ent_01", "विकास शर्मा"), _phone("ent_02", shared_phone)],
        [{"relation": "OWNS_DEVICE", "source": "ent_01", "target": "ent_02", "evidence_char_span": [0, 20]}],
    )
    _write_fir(
        fir_dir,
        "FIR_04",
        [_person("ent_01", "बिकास शर्मा"), _phone("ent_02", shared_phone)],
        [{"relation": "OWNS_DEVICE", "source": "ent_01", "target": "ent_02", "evidence_char_span": [0, 20]}],
    )

    graph = build_case_graph(fir_dir, cdr_path, bank_path)
    assert validate_graph(graph) == []
    # Vikas+विकास merge (1) and Bikas+बिकास merge (1) => 2 PERSON nodes, never 1.
    persons = [n for n in graph["nodes"] if n["type"] == "PERSON"]
    assert len(persons) == 2
    assert graph["stats"]["merges_by_rule"]["rule_B"] == 2
    assert graph["stats"]["same_as_candidate_edges"] == 0


def test_shared_phone_different_names_stay_separate(tmp_path: Path) -> None:
    fir_dir = tmp_path / "firs"
    fir_dir.mkdir()
    cdr_path, bank_path = _empty_csvs(tmp_path)

    _write_fir(
        fir_dir,
        "FIR_01",
        [_person("ent_01", "Amit Tomar"), _phone("ent_02", "9999999999")],
        [{"relation": "OWNS_DEVICE", "source": "ent_01", "target": "ent_02", "evidence_char_span": [0, 20]}],
    )
    _write_fir(
        fir_dir,
        "FIR_02",
        [_person("ent_01", "Deepak Chauhan"), _phone("ent_02", "9999999999")],
        [{"relation": "OWNS_DEVICE", "source": "ent_01", "target": "ent_02", "evidence_char_span": [0, 20]}],
    )

    graph = build_case_graph(fir_dir, cdr_path, bank_path)
    assert validate_graph(graph) == []
    assert graph["stats"]["persons_after_merge"] == 2
    assert graph["stats"]["same_as_candidate_edges"] == 0


def test_father_conflict_blocks_candidate_link_and_merge(tmp_path: Path) -> None:
    fir_dir = tmp_path / "firs"
    fir_dir.mkdir()
    cdr_path, bank_path = _empty_csvs(tmp_path)

    _write_fir(
        fir_dir,
        "FIR_01",
        [_person("ent_01", "Suresh Pal", father="Hari Pal"), _phone("ent_02", "9811111111")],
        [{"relation": "OWNS_DEVICE", "source": "ent_01", "target": "ent_02", "evidence_char_span": [0, 20]}],
    )
    _write_fir(
        fir_dir,
        "FIR_02",
        [_person("ent_01", "Suresh Pal", father="Ram Pal"), _phone("ent_02", "9811111111")],
        [{"relation": "OWNS_DEVICE", "source": "ent_01", "target": "ent_02", "evidence_char_span": [0, 20]}],
    )

    graph = build_case_graph(fir_dir, cdr_path, bank_path)
    assert validate_graph(graph) == []
    assert graph["stats"]["persons_after_merge"] == 2
    assert graph["stats"]["same_as_candidate_edges"] == 0
    assert graph["stats"]["blocked_by_father_conflict"] == 1


def test_same_as_candidate_star_shape_stats_and_determinism(tmp_path: Path) -> None:
    fir_dir = tmp_path / "firs"
    fir_dir.mkdir()
    cdr_path, bank_path = _empty_csvs(tmp_path)

    _write_fir(fir_dir, "FIR_01", [_person("ent_01", "Anand Verma")], [])
    _write_fir(fir_dir, "FIR_02", [_person("ent_01", "Anand Verma")], [])
    _write_fir(fir_dir, "FIR_03", [_person("ent_01", "आनंद वर्मा")], [])

    g1 = build_case_graph(fir_dir, cdr_path, bank_path)
    g2 = build_case_graph(fir_dir, cdr_path, bank_path)
    assert validate_graph(g1) == []
    assert json.dumps(g1, indent=2, sort_keys=True, ensure_ascii=False) == json.dumps(
        g2, indent=2, sort_keys=True, ensure_ascii=False
    )

    cand = [e for e in g1["edges"] if e["relation"] == "SAME_AS_CANDIDATE"]
    assert len(cand) == 2
    assert {e["target"] for e in cand} == {"PERSON:FIR_01:ent_01"}
    assert {e["source"] for e in cand} == {"PERSON:FIR_02:ent_01", "PERSON:FIR_03:ent_01"}
    assert all(e["source_kind"] == "RULE" for e in cand)

    stats = g1["stats"]
    assert stats["same_as_candidate_edges"] == 2
    assert "SAME_AS_CANDIDATE" not in stats["edge_counts_by_type"]
    assert "RULE" not in stats["edge_counts_by_source_kind"]
    assert sum(stats["edge_counts_by_type"].values()) == 0
    assert stats["total_edges"] == 2


def test_eval_person_merge_tiny_handmade_graph(tmp_path: Path) -> None:
    ak_dir = tmp_path / "ak"
    ak_dir.mkdir()

    def write_ak(fir_id: str, split: str, entities: list[dict]) -> None:
        (ak_dir / f"{fir_id}.json").write_text(
            json.dumps({"source_doc_id": fir_id, "split": split, "entities": entities}),
            encoding="utf-8",
        )

    write_ak(
        "FIR_01",
        "train",
        [
            {"type": "PERSON", "role": "SUSPECT", "truth_id": "T_A", "char_span": [0, 10]},
            {"type": "PERSON", "role": "FATHER", "truth_id": None, "char_span": [20, 30]},
        ],
    )
    write_ak(
        "FIR_02",
        "dev",
        [{"type": "PERSON", "role": "SUSPECT", "truth_id": "T_A", "char_span": [0, 10]}],
    )
    write_ak(
        "FIR_03",
        "test",
        [{"type": "PERSON", "role": "SUSPECT", "truth_id": "T_B", "char_span": [0, 10]}],
    )
    write_ak(
        "FIR_04",
        "test",
        [{"type": "PERSON", "role": "SUSPECT", "truth_id": "T_C", "char_span": [0, 10]}],
    )

    graph = {
        "nodes": [
            {
                "id": "PERSON:FIR_01:ent_01",
                "type": "PERSON",
                "roles": ["SUSPECT"],
                "evidence_spans": [
                    {
                        "fir_id": "FIR_01",
                        "entity_id": "ent_01",
                        "char_span": [0, 10],
                        "mentions": [
                            {"kind": "NAME", "char_span": [0, 10], "surface": "A"},
                            {"kind": "FATHER", "char_span": [20, 30], "surface": "F"},
                        ],
                    },
                    {
                        "fir_id": "FIR_02",
                        "entity_id": "ent_01",
                        "char_span": [0, 10],
                        "mentions": [{"kind": "NAME", "char_span": [0, 10], "surface": "A"}],
                    },
                ],
            },
            {
                "id": "PERSON:FIR_03:ent_01",
                "type": "PERSON",
                "roles": ["SUSPECT"],
                "evidence_spans": [
                    {
                        "fir_id": "FIR_03",
                        "entity_id": "ent_01",
                        "char_span": [0, 10],
                        "mentions": [{"kind": "NAME", "char_span": [0, 10], "surface": "B"}],
                    },
                    {
                        "fir_id": "FIR_04",
                        "entity_id": "ent_01",
                        "char_span": [0, 10],
                        "mentions": [{"kind": "NAME", "char_span": [0, 10], "surface": "C"}],
                    },
                ],
            },
        ],
        "edges": [
            {
                "source": "PERSON:FIR_03:ent_01",
                "target": "PERSON:FIR_01:ent_01",
                "relation": "SAME_AS_CANDIDATE",
                "source_kind": "RULE",
                "reasons": ["same_name"],
            }
        ],
    }

    report = evaluate_person_merge(graph, ak_dir)
    ov = report["overall"]
    assert ov["real_people"] == 3
    assert ov["nodes"] == 2
    assert ov["nodes_per_real_person"] == {"min": 1, "median": 1, "max": 1}
    assert ov["wrong_merge_nodes"] == 1
    assert ov["same_person_pairs_merged"] == 1
    assert ov["same_person_pairs_not_merged"] == 0
    assert ov["same_as_candidate_same_person"] == 0
    assert ov["same_as_candidate_different_people"] == 1

    assert report["by_split"]["train"]["real_people"] == 1
    assert report["by_split"]["dev"]["real_people"] == 1
    assert report["by_split"]["test"]["real_people"] == 2
    assert report["by_split"]["test"]["wrong_merge_nodes"] == 1

    graph_path = tmp_path / "graph.json"
    out_path = tmp_path / "eval.json"
    graph_path.write_text(json.dumps(graph), encoding="utf-8")
    assert eval_main([str(graph_path), str(ak_dir), str(out_path)]) == 0
    assert out_path.exists()


def test_case_graph_source_still_contains_no_truth() -> None:
    for py_file in (REPO_ROOT / "case_graph").rglob("*.py"):
        assert "truth" not in py_file.read_text(encoding="utf-8").lower()

