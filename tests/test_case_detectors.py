"""Unit tests for case detectors: mule, burner, min vertex cut, and role chips."""

from __future__ import annotations

import csv
from datetime import datetime
import itertools
import json
import math
from pathlib import Path

import networkx as nx
import numpy as np
import pytest

from case_detectors.burner import detect_burners
from case_detectors.cut import articulation_persons, detect_communities, min_vertex_cut
from case_detectors.mule import detect_mules
from case_detectors.roles import assign_role_chips
from scripts.eval_detectors import evaluate_detectors
from scripts.run_detectors import run_detectors


def test_mule_features_hand_made_bank_table(tmp_path):
    """mule features on hand-made bank table: fan-in, passthrough, dwell, structuring band edges."""
    bank_csv = tmp_path / "bank.csv"
    # Band: threshold 50000, band 0.10 -> [45000, 50000)
    # Test edge amounts for structuring:
    # 45000.00 -> INCLUDED
    # 44999.99 -> EXCLUDED
    # 49999.99 -> INCLUDED
    # 50000.00 -> EXCLUDED
    rows = [
        "txn_id,datetime,from_acct,to_acct,amount,mode,ifsc,narration",
        # Credit 1: from S1 to MULE, amount 45000.00 (inclusive lower bound) at 10:00
        "TXN01,2026-01-01T10:00:00,ACC_S1,ACC_MULE,45000.00,IMPS,IFSC01,Deposit 1",
        # Credit 2: from S2 to MULE, amount 44999.99 (just below lower bound) at 11:00
        "TXN02,2026-01-01T11:00:00,ACC_S2,ACC_MULE,44999.99,IMPS,IFSC01,Deposit 2",
        # Credit 3: from S3 to MULE, amount 49999.99 (just below threshold) at 12:00
        "TXN03,2026-01-01T12:00:00,ACC_S3,ACC_MULE,49999.99,IMPS,IFSC01,Deposit 3",
        # Credit 4: from S4 to MULE, amount 50000.00 (exclusive upper bound) at 13:00
        "TXN04,2026-01-01T13:00:00,ACC_S4,ACC_MULE,50000.00,IMPS,IFSC01,Deposit 4",
        # Debit: from MULE to OUT1, at 14:00, amount 189999.98 (entire balance)
        "TXN05,2026-01-01T14:00:00,ACC_MULE,ACC_OUT1,189999.98,NEFT,IFSC02,Outward",
    ]
    bank_csv.write_text("\n".join(rows), encoding="utf-8")

    leads = detect_mules(bank_csv)
    mule_lead = next(lead for lead in leads if lead["id"] == "ACC_MULE")
    feat = mule_lead["features"]

    # fan-in: 4 distinct senders (S1, S2, S3, S4)
    assert feat["fan_in"] == 4
    assert feat["fan_out"] == 1
    # passthrough: total in = 18999998 paise, total out = 18999998 paise -> 1.0
    assert pytest.approx(feat["passthrough"], 1e-6) == 1.0

    # Dwell hours:
    # Credit 1 (10:00 -> 14:00): 4 hours
    # Credit 2 (11:00 -> 14:00): 3 hours
    # Credit 3 (12:00 -> 14:00): 2 hours
    # Credit 4 (13:00 -> 14:00): 1 hour
    # Median dwell = median(4, 3, 2, 1) = 2.5 hours
    assert pytest.approx(feat["median_dwell_hours"], 1e-4) == 2.5
    expected_dwell_score = 1.0 / (1.0 + 2.5 / 24.0)
    assert pytest.approx(feat["dwell_score"], 1e-6) == expected_dwell_score

    # Structuring share:
    # 45000.00 (included) and 49999.99 (included) -> 2 out of 4 credits = 0.50
    # 44999.99 is below band, 50000.00 is at threshold -> excluded
    assert pytest.approx(feat["structuring_share"], 1e-6) == 0.50


def test_mule_score_ordering_toy_example(tmp_path):
    """mule score ordering on a toy example with one obvious mule."""
    bank_csv = tmp_path / "bank.csv"
    rows = [
        "txn_id,datetime,from_acct,to_acct,amount,mode,ifsc,narration",
        # Obvious mule receives from 3 senders just under 50k, forwards within 2 hours
        "T1,2026-01-01T10:00:00,S1,MULE,48000.00,IMPS,IFSC,Dep1",
        "T2,2026-01-01T10:30:00,S2,MULE,49000.00,IMPS,IFSC,Dep2",
        "T3,2026-01-01T11:00:00,S3,MULE,47500.00,IMPS,IFSC,Dep3",
        "T4,2026-01-01T12:00:00,MULE,TARGET,144500.00,NEFT,IFSC,Fwd",
        # Normal civilian account receives salary once, spends slowly
        "T5,2026-01-01T09:00:00,EMPLOYER,CIVILIAN,50000.00,NEFT,IFSC,Salary",
        "T6,2026-01-15T15:00:00,CIVILIAN,GROCERY,5000.00,UPI,IFSC,Food",
    ]
    bank_csv.write_text("\n".join(rows), encoding="utf-8")

    leads = detect_mules(bank_csv)
    assert leads[0]["id"] == "MULE"
    assert leads[0]["score"] > leads[1]["score"]


def test_burner_features_hand_made_cdr(tmp_path):
    """burner features on a hand-made CDR."""
    cdr_csv = tmp_path / "cdr.csv"
    # Observation window: Jan 1 to Jan 31 (30 days)
    # Phone B active from Jan 21 00:00 to Jan 24 00:00 (lifespan = 3.0 days)
    # late_activation = 20.0 / 30.0 = 2/3
    # calls only with C1 (8 calls) and C2 (2 calls) -> total 10 calls, top2_share = 1.0
    # IMEI hopping: IMEI_HOP shared by B and OTHER_PHONE as a_party
    rows = [
        "a_party,b_party,imei_a,imsi_a,start_time,duration_sec,call_type,tower_id,lat,lon",
        "P_BASELINE,P_EXT,IM1,IMSI1,2026-01-01T00:00:00,60,VOICE,T1,28.0,77.0",
        "BURNER,C1,IMEI_HOP,IMSI2,2026-01-21T00:00:00,60,VOICE,T1,28.0,77.0",
        "BURNER,C1,IMEI_HOP,IMSI2,2026-01-22T12:00:00,60,VOICE,T1,28.0,77.0",
        "BURNER,C2,IMEI_HOP,IMSI2,2026-01-24T00:00:00,60,VOICE,T1,28.0,77.0",
        "OTHER,P_EXT,IMEI_HOP,IMSI3,2026-01-25T00:00:00,60,VOICE,T1,28.0,77.0",
        "P_BASELINE,P_EXT,IM1,IMSI1,2026-01-31T00:00:00,60,VOICE,T1,28.0,77.0",
    ]
    cdr_csv.write_text("\n".join(rows), encoding="utf-8")

    leads = detect_burners(cdr_csv)
    b_lead = next(l for l in leads if l["id"] == "BURNER")
    feat = b_lead["features"]

    assert pytest.approx(feat["observation_days"], 1e-4) == 30.0
    assert pytest.approx(feat["first_seen_day"], 1e-4) == 20.0
    assert pytest.approx(feat["lifespan_days"], 1e-4) == 3.0
    assert pytest.approx(feat["late_activation"], 1e-4) == (20.0 / 30.0)
    assert pytest.approx(feat["short_lifespan"], 1e-4) == (1.0 - 3.0 / 30.0)
    assert feat["distinct_contacts"] == 2
    assert pytest.approx(feat["top2_share"], 1e-6) == 1.0
    assert feat["imei_hop"] == 1


def test_burner_score_ordering_toy_example(tmp_path):
    """burner ordering on a toy example."""
    cdr_csv = tmp_path / "cdr.csv"
    rows = [
        "a_party,b_party,imei_a,imsi_a,start_time,duration_sec,call_type,tower_id,lat,lon",
        # Persistent regular phone
        "REGULAR,CONTACT,IM1,IMSI1,2026-01-01T10:00:00,60,VOICE,T1,28.0,77.0",
        "REGULAR,CONTACT,IM1,IMSI1,2026-01-10T10:00:00,60,VOICE,T1,28.0,77.0",
        "REGULAR,CONTACT,IM1,IMSI1,2026-01-20T10:00:00,60,VOICE,T1,28.0,77.0",
        "REGULAR,CONTACT,IM1,IMSI1,2026-01-30T10:00:00,60,VOICE,T1,28.0,77.0",
        # Burner phone active only on day 28-29
        "BURNER,CONTACT,IM2,IMSI2,2026-01-28T10:00:00,60,VOICE,T1,28.0,77.0",
        "BURNER,CONTACT,IM2,IMSI2,2026-01-29T10:00:00,60,VOICE,T1,28.0,77.0",
    ]
    cdr_csv.write_text("\n".join(rows), encoding="utf-8")

    leads = detect_burners(cdr_csv)
    assert leads[0]["id"] == "BURNER"
    assert leads[0]["score"] > leads[1]["score"]


def test_min_vertex_cut_equals_brute_force_on_random_graphs():
    """min_vertex_cut equals a brute-force search over person subsets on at least 5 small random graphs."""
    for seed in (101, 102, 103, 104, 105):
        rng = np.random.RandomState(seed)
        # 8 nodes: 0, 1 in group_a; 6, 7 in group_b; 2, 3, 4, 5 candidate arrestable persons
        G_raw = nx.erdos_renyi_graph(n=8, p=0.45, seed=seed)

        nodes = []
        for i in range(8):
            ntype = "PERSON" if 2 <= i <= 5 else ("GROUP_A" if i < 2 else "GROUP_B")
            nodes.append({"id": f"N{i}", "type": ntype})

        edges = [{"source": f"N{u}", "target": f"N{v}"} for u, v in G_raw.edges()]
        graph_data = {"edges": edges, "nodes": nodes}

        group_a = ["N0", "N1"]
        group_b = ["N6", "N7"]

        cut_res = min_vertex_cut(graph_data, group_a, group_b, arrestable_types=("PERSON",))

        # Build undirected graph for brute force check
        G_check = nx.Graph()
        for e in edges:
            G_check.add_edge(e["source"], e["target"])

        # Check if connected initially
        has_path = any(
            nx.has_path(G_check, a, b)
            for a in group_a
            for b in group_b
            if a in G_check and b in G_check
        )

        arrestable_nodes = [f"N{i}" for i in range(2, 6) if f"N{i}" in G_check]

        if not has_path:
            assert cut_res["finite"] is True
            assert cut_res["size"] == 0
            assert cut_res["cut"] == []
            continue

        # Brute force search for minimum subset of arrestable nodes that disconnects group_a from group_b
        brute_force_min_size = None
        for k in range(len(arrestable_nodes) + 1):
            for subset in itertools.combinations(arrestable_nodes, k):
                G_sub = G_check.copy()
                G_sub.remove_nodes_from(subset)
                path_remains = any(
                    nx.has_path(G_sub, a, b)
                    for a in group_a
                    for b in group_b
                    if a in G_sub and b in G_sub
                )
                if not path_remains:
                    brute_force_min_size = k
                    break
            if brute_force_min_size is not None:
                break

        if brute_force_min_size is None:
            # Person-free path exists
            assert cut_res["finite"] is False
        else:
            assert cut_res["finite"] is True
            assert cut_res["size"] == brute_force_min_size
            # Verify the cut returned actually disconnects
            G_sub = G_check.copy()
            G_sub.remove_nodes_from(cut_res["cut"])
            assert not any(
                nx.has_path(G_sub, a, b)
                for a in group_a
                for b in group_b
                if a in G_sub and b in G_sub
            )


def test_cut_returns_finite_false_when_person_free_path_exists():
    """cut returns finite False when a person-free path exists."""
    graph = {
        "nodes": [
            {"id": "PERSON:A", "type": "PERSON"},
            {"id": "PERSON:B", "type": "PERSON"},
            {"id": "PHONE:P1", "type": "PHONE"},
            {"id": "PHONE:P2", "type": "PHONE"},
        ],
        "edges": [
            {"source": "PERSON:A", "target": "PHONE:P1"},
            {"source": "PHONE:P1", "target": "PHONE:P2"},
            {"source": "PHONE:P2", "target": "PERSON:B"},
        ],
    }
    # Path A -> P1 -> P2 -> B has NO arrestable person on it
    res = min_vertex_cut(graph, ["PERSON:A"], ["PERSON:B"], arrestable_types=("PERSON",))
    assert res["finite"] is False


def test_terminals_never_in_cut():
    """terminals are never in the cut."""
    graph = {
        "nodes": [
            {"id": "PERSON:A", "type": "PERSON"},
            {"id": "PERSON:MID", "type": "PERSON"},
            {"id": "PERSON:B", "type": "PERSON"},
        ],
        "edges": [
            {"source": "PERSON:A", "target": "PERSON:MID"},
            {"source": "PERSON:MID", "target": "PERSON:B"},
        ],
    }
    res = min_vertex_cut(graph, ["PERSON:A"], ["PERSON:B"], arrestable_types=("PERSON",))
    assert res["finite"] is True
    assert res["size"] == 1
    assert res["cut"] == ["PERSON:MID"]
    assert "PERSON:A" not in res["cut"]
    assert "PERSON:B" not in res["cut"]


def test_empty_group_returns_skipped():
    """empty group returns skipped."""
    graph = {
        "nodes": [{"id": "PERSON:A", "type": "PERSON"}],
        "edges": [],
    }
    res1 = min_vertex_cut(graph, [], ["PERSON:A"])
    assert res1 == {"skipped": "empty_group"}

    res2 = min_vertex_cut(graph, ["PERSON:A"], ["NON_EXISTENT"])
    assert res2 == {"skipped": "empty_group"}


def test_articulation_persons_agrees_with_networkx():
    """articulation_persons agrees with networkx on a small graph."""
    graph = {
        "nodes": [
            {"id": "PERSON:P1", "type": "PERSON"},
            {"id": "PERSON:P2", "type": "PERSON"},
            {"id": "PHONE:PH1", "type": "PHONE"},
            {"id": "PHONE:PH2", "type": "PHONE"},
        ],
        "edges": [
            {"source": "PHONE:PH1", "target": "PERSON:P1"},
            {"source": "PERSON:P1", "target": "PERSON:P2"},
            {"source": "PERSON:P2", "target": "PHONE:PH2"},
        ],
    }
    # G is path PH1 - P1 - P2 - PH2
    # Articulation points of G are P1 and P2
    arts = articulation_persons(graph)
    art_ids = [item["node_id"] for item in arts]
    assert art_ids == ["PERSON:P1", "PERSON:P2"]
    # P1 splits graph into PH1 (size 1) and P2-PH2 (size 2)
    p1_item = next(it for it in arts if it["node_id"] == "PERSON:P1")
    assert p1_item["component_sizes"] == [2, 1]


def test_role_chips_rules():
    """role chips follow the rules and use strictly lead/chip wording."""
    persons = ["PERSON:P1", "PERSON:P2", "PERSON:P3", "PERSON:P4", "PERSON:P5"]
    financial_rank = {"PERSON:P1": 1, "PERSON:P2": 4, "PERSON:P3": 5, "PERSON:P5": 10}
    cut_members = {"PERSON:P2"}
    # 0.70 is flagged, 0.69 is not flagged
    mule_accounts = {"ACC_MULE_1": 0.70, "ACC_MULE_LOW": 0.69}
    burner_phones = {"PH_BURNER_1": 0.70, "PH_BURNER_LOW": 0.69}

    owner_maps = {
        "controlled_accounts": {
            "PERSON:P3": ["ACC_MULE_1"],
            "PERSON:P5": ["ACC_MULE_LOW"],
        },
        "owned_phones": {
            "PERSON:P4": ["PH_BURNER_1"],
            "PERSON:P5": ["PH_BURNER_LOW"],
        },
    }

    chips = assign_role_chips(
        person_nodes=persons,
        financial_rank=financial_rank,
        cut_members=cut_members,
        mule_accounts_flagged=mule_accounts,
        burner_phones_flagged=burner_phones,
        owner_maps=owner_maps,
        mule_min_score=0.70,
        burner_min_score=0.70,
    )

    # P1 has financial rank 1 <= 3 -> PRIORITY_LEAD_MONEY
    assert any(c["chip"] == "PRIORITY_LEAD_MONEY" for c in chips["PERSON:P1"])

    # P2 is cut member -> CUT_MEMBER
    assert any(c["chip"] == "CUT_MEMBER" for c in chips["PERSON:P2"])

    # P3 controls flagged mule (score 0.70) -> MULE_OWNER
    assert any(c["chip"] == "MULE_OWNER" for c in chips["PERSON:P3"])

    # P4 owns flagged burner (score 0.70) -> BURNER_USER
    assert any(c["chip"] == "BURNER_USER" for c in chips["PERSON:P4"])

    # P5 controls 0.69 mule and 0.69 burner -> NOT flagged
    assert not any(c["chip"] == "MULE_OWNER" for c in chips["PERSON:P5"])
    assert not any(c["chip"] == "BURNER_USER" for c in chips["PERSON:P5"])

    # Check forbidden words: guilty, arrest
    for pid, chip_list in chips.items():
        for item in chip_list:
            text = (item["chip"] + " " + item["reason"]).lower()
            assert "guilty" not in text
            assert "arrest" not in text
            assert "truth" not in text


def test_outputs_identical_across_two_runs(tmp_path):
    """outputs identical across two runs."""
    case_dir = tmp_path / "case_det"
    case_dir.mkdir()
    (case_dir / "bank.csv").write_text(
        "txn_id,datetime,from_acct,to_acct,amount,mode,ifsc,narration\n"
        "T1,2026-01-01T10:00:00,A1,A2,500.00,UPI,IFSC,Food\n",
        encoding="utf-8",
    )
    (case_dir / "cdr.csv").write_text(
        "a_party,b_party,imei_a,imsi_a,start_time,duration_sec,call_type,tower_id,lat,lon\n"
        "9876543210,9123456789,IM1,IMS1,2026-01-01T10:00:00,60,VOICE,T1,28.0,77.0\n",
        encoding="utf-8",
    )

    m1 = detect_mules(case_dir / "bank.csv")
    m2 = detect_mules(case_dir / "bank.csv")
    assert m1 == m2

    b1 = detect_burners(case_dir / "cdr.csv")
    b2 = detect_burners(case_dir / "cdr.csv")
    assert b1 == b2


def test_scripts_refuse_existing_output_folder(tmp_path):
    """scripts refuse an existing output folder."""
    case_dir = tmp_path / "case_input"
    case_dir.mkdir()
    (case_dir / "bank.csv").write_text("txn_id,datetime,from_acct,to_acct,amount,mode,ifsc,narration\n", encoding="utf-8")
    (case_dir / "cdr.csv").write_text("a_party,b_party,imei_a,imsi_a,start_time,duration_sec,call_type,tower_id,lat,lon\n", encoding="utf-8")

    out_dir = tmp_path / "existing_out"
    out_dir.mkdir()

    with pytest.raises(FileExistsError):
        run_detectors(case_dir, out_dir)


def test_no_truth_in_case_detectors_and_config():
    """the word 'truth' appears nowhere in case_detectors/ sources or config/detector_defaults.json."""
    repo_root = Path(__file__).resolve().parents[1]
    for py_file in (repo_root / "case_detectors").glob("*.py"):
        content = py_file.read_text(encoding="utf-8").lower()
        assert "truth" not in content, f"Word 'truth' found in {py_file}"

    config_path = repo_root / "config" / "detector_defaults.json"
    if config_path.exists():
        cfg_txt = config_path.read_text(encoding="utf-8").lower()
        assert "truth" not in cfg_txt, f"Word 'truth' found in {config_path}"


def test_detectors_read_only_csv_files(tmp_path):
    """detectors read nothing but the two CSV files (test with a temp dir containing only cdr.csv and bank.csv)."""
    case_dir = tmp_path / "isolated_case"
    case_dir.mkdir()

    bank_csv = case_dir / "bank.csv"
    cdr_csv = case_dir / "cdr.csv"

    bank_csv.write_text(
        "txn_id,datetime,from_acct,to_acct,amount,mode,ifsc,narration\n"
        "T1,2026-01-01T10:00:00,A1,A2,1000.00,UPI,IFSC,Test\n",
        encoding="utf-8",
    )
    cdr_csv.write_text(
        "a_party,b_party,imei_a,imsi_a,start_time,duration_sec,call_type,tower_id,lat,lon\n"
        "9876543210,9123456789,IM1,IMS1,2026-01-01T10:00:00,30,VOICE,T1,28.0,77.0\n",
        encoding="utf-8",
    )

    # Verify no other files exist in directory
    assert set(p.name for p in case_dir.iterdir()) == {"bank.csv", "cdr.csv"}

    mules = detect_mules(bank_csv)
    burners = detect_burners(cdr_csv)

    assert len(mules) == 2
    assert len(burners) == 2
