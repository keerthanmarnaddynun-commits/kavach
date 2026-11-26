"""Unit tests for timeline insights module and endpoint."""
from __future__ import annotations

from pathlib import Path
import pytest
from starlette.testclient import TestClient

from kavach_api.app import create_app
from kavach_api.insights import (
    compute_timeline_insights,
    RULES,
    MIN_ACTIVE_DAYS,
    MIN_CALL_EVENTS,
    MIN_TRANSFER_EVENTS,
    MIN_TRANSFER_AMOUNT_PAISE,
)
from kavach_api.security import create_token
from kavach_api.settings import Settings, repo_root
from kavach_api.storage import Storage


def _make_dummy_store(tmp_path: Path) -> Storage:
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    settings = Settings(runtime_dir=runtime_dir)
    return Storage(settings)


def test_fewer_than_7_active_days(tmp_path: Path):
    store = _make_dummy_store(tmp_path)
    # Only 5 days
    tl_data = {
        "calls": [{"t": f"2026-03-0{i}", "count": 20, "voice": 20, "sms": 0} for i in range(1, 6)],
        "transfers": [],
        "first_seen": [],
        "first_seen_accounts": [],
        "first_seen_imeis": [],
    }
    res = compute_timeline_insights(store, "C-test", timeline_data=tl_data)
    assert res["count"] == 0
    assert res["reason"] == "not enough days to judge"
    assert res["insights"] == []
    assert res["rules"]["min_active_days"] == 7


def test_empty_case(tmp_path: Path):
    store = _make_dummy_store(tmp_path)
    tl_data = {
        "calls": [],
        "transfers": [],
        "first_seen": [],
        "first_seen_accounts": [],
        "first_seen_imeis": [],
    }
    res = compute_timeline_insights(store, "C-test", timeline_data=tl_data)
    assert res["count"] == 0
    assert res["reason"] == "not enough days to judge"
    assert res["insights"] == []


def test_call_spike_detected(tmp_path: Path):
    store = _make_dummy_store(tmp_path)
    # 9 days of 10 calls, 1 day of 50 calls
    calls = [{"t": f"2026-03-{i:02d}", "count": 10, "voice": 10, "sms": 0} for i in range(1, 10)]
    calls.append({"t": "2026-03-10", "count": 50, "voice": 50, "sms": 0})
    tl_data = {
        "calls": calls,
        "transfers": [],
        "first_seen": [],
        "first_seen_accounts": [],
        "first_seen_imeis": [],
    }
    res = compute_timeline_insights(store, "C-test", timeline_data=tl_data)
    assert res["reason"] is None
    assert res["count"] == 1
    spike = res["insights"][0]
    assert spike["kind"] == "call_spike"
    assert spike["chart"] == "calls"
    assert spike["days"] == ["2026-03-10"]
    assert "worth a look" in spike["headline"]
    assert "50 calls on 2026-03-10" in spike["why"]


def test_no_spike_normal_variation(tmp_path: Path):
    store = _make_dummy_store(tmp_path)
    # 10 days with counts 10 to 12
    calls = [{"t": f"2026-03-{i:02d}", "count": 10 + (i % 3), "voice": 10, "sms": 0} for i in range(1, 11)]
    tl_data = {
        "calls": calls,
        "transfers": [],
        "first_seen": [],
        "first_seen_accounts": [],
        "first_seen_imeis": [],
    }
    res = compute_timeline_insights(store, "C-test", timeline_data=tl_data)
    assert res["reason"] is None
    assert res["count"] == 0
    assert res["insights"] == []
    assert res["summary"]["busiest_call_day"]["count"] == 12
    assert res["summary"]["busiest_call_day"]["ratio"] >= 1.0


def test_summary_busiest_days(tmp_path: Path):
    store = _make_dummy_store(tmp_path)
    calls = [{"t": f"2026-03-{i:02d}", "count": 10, "voice": 10, "sms": 0} for i in range(1, 10)]
    calls.append({"t": "2026-03-10", "count": 25, "voice": 25, "sms": 0})
    transfers = [{"t": f"2026-03-{i:02d}", "count": 5, "paise": 50000} for i in range(1, 10)]
    transfers.append({"t": "2026-03-10", "count": 12, "paise": 120000})

    tl_data = {
        "calls": calls,
        "transfers": transfers,
        "first_seen": [],
        "first_seen_accounts": [],
        "first_seen_imeis": [],
    }
    res = compute_timeline_insights(store, "C-test", timeline_data=tl_data)
    assert "summary" in res
    assert res["summary"]["busiest_call_day"]["date"] == "2026-03-10"
    assert res["summary"]["busiest_call_day"]["count"] == 25
    assert res["summary"]["busiest_call_day"]["ratio"] == 2.5
    assert res["summary"]["busiest_transfer_day"]["date"] == "2026-03-10"
    assert res["summary"]["busiest_transfer_day"]["count"] == 12
    assert res["summary"]["busiest_transfer_day"]["ratio"] == 2.4


def test_below_min_events(tmp_path: Path):
    store = _make_dummy_store(tmp_path)
    # Median is 1 call, spike day has 4 calls (4 >= 3 * 1, but < MIN_CALL_EVENTS of 10)
    calls = [{"t": f"2026-03-{i:02d}", "count": 1, "voice": 1, "sms": 0} for i in range(1, 10)]
    calls.append({"t": "2026-03-10", "count": 4, "voice": 4, "sms": 0})
    tl_data = {
        "calls": calls,
        "transfers": [],
        "first_seen": [],
        "first_seen_accounts": [],
        "first_seen_imeis": [],
    }
    res = compute_timeline_insights(store, "C-test", timeline_data=tl_data)
    assert res["reason"] is None
    assert res["count"] == 0
    assert res["insights"] == []


def test_transfer_spike_count_and_amount(tmp_path: Path):
    store = _make_dummy_store(tmp_path)
    # 8 days baseline: 10 transfers, 100,000 paise (Rs 1,000)
    transfers = [
        {"t": f"2026-03-{i:02d}", "count": 10, "paise": 100000}
        for i in range(1, 9)
    ]
    # Day 9: high count (40 transfers, 100,000 paise)
    transfers.append({"t": "2026-03-09", "count": 40, "paise": 100000})
    # Day 10: normal count (10 transfers), high amount (10,000,000 paise = Rs 100,000 >= 50,000)
    transfers.append({"t": "2026-03-10", "count": 10, "paise": 10000000})

    tl_data = {
        "calls": [],
        "transfers": transfers,
        "first_seen": [],
        "first_seen_accounts": [],
        "first_seen_imeis": [],
    }
    res = compute_timeline_insights(store, "C-test", timeline_data=tl_data)
    assert res["reason"] is None
    assert res["count"] == 2
    kinds = [ins["kind"] for ins in res["insights"]]
    assert kinds == ["transfer_spike", "transfer_spike"]
    assert res["insights"][0]["days"] == ["2026-03-09"]
    assert res["insights"][1]["days"] == ["2026-03-10"]


def test_call_then_transfer_pair_within_2_days(tmp_path: Path):
    store = _make_dummy_store(tmp_path)
    # 7 baseline days
    calls = [{"t": f"2026-03-{i:02d}", "count": 10, "voice": 10, "sms": 0} for i in range(1, 8)]
    # Call spike on 2026-03-08 (50 calls)
    calls.append({"t": "2026-03-08", "count": 50, "voice": 50, "sms": 0})

    transfers = [{"t": f"2026-03-{i:02d}", "count": 10, "paise": 100000} for i in range(1, 8)]
    # Transfer spike on 2026-03-10 (40 transfers, 2 days after call spike)
    transfers.append({"t": "2026-03-10", "count": 40, "paise": 100000})

    tl_data = {
        "calls": calls,
        "transfers": transfers,
        "first_seen": [],
        "first_seen_accounts": [],
        "first_seen_imeis": [],
    }
    res = compute_timeline_insights(store, "C-test", timeline_data=tl_data)
    assert res["reason"] is None
    kinds = [ins["kind"] for ins in res["insights"]]
    assert "call_spike" in kinds
    assert "transfer_spike" in kinds
    assert "call_then_transfer" in kinds

    ct = [ins for ins in res["insights"] if ins["kind"] == "call_then_transfer"][0]
    assert ct["chart"] == "both"
    assert ct["days"] == ["2026-03-08", "2026-03-10"]
    assert "worth a look" in ct["headline"]
    assert "2 days later" in ct["why"]


def test_new_and_busy_share_rule(tmp_path: Path):
    store = _make_dummy_store(tmp_path)
    # 7 baseline days of 10 calls
    calls = [{"t": f"2026-03-{i:02d}", "count": 10, "voice": 10, "sms": 0} for i in range(1, 8)]
    # Spike on 2026-03-08: 100 calls
    calls.append({"t": "2026-03-08", "count": 100, "voice": 100, "sms": 0})

    # Phone first seen 2 days before spike (2026-03-06)
    first_seen_phones = [
        {"phone": "+919876543210", "t": "2026-03-06 10:00:00"},
        {"phone": "+919111111111", "t": "2026-03-07 10:00:00"},
    ]

    # Daily phone counts:
    # +919876543210 has 25 calls on spike day (25% >= 20% and 25 >= 5) -> triggers
    # +919111111111 has 4 calls on spike day (4% < 20% and 4 < 5) -> does not trigger
    daily_phones = {
        "2026-03-08": {
            "+919876543210": 25,
            "+919111111111": 4,
        }
    }
    daily_counts = (daily_phones, {}, {})

    tl_data = {
        "calls": calls,
        "transfers": [],
        "first_seen": first_seen_phones,
        "first_seen_accounts": [],
        "first_seen_imeis": [],
    }

    res = compute_timeline_insights(
        store, "C-test", timeline_data=tl_data, daily_counts=daily_counts
    )
    assert res["reason"] is None
    nb_insights = [ins for ins in res["insights"] if ins["kind"] == "new_and_busy"]
    assert len(nb_insights) == 1
    nb = nb_insights[0]
    assert nb["chart"] == "calls"
    assert nb["identifiers"][0]["id"] == "+919876543210"
    assert nb["links"][0] == "PHONE:+919876543210"
    assert "worth a look" in nb["headline"]
    assert "25.0%" in nb["why"]


def test_endpoint_timeline_insights(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    settings = Settings(
        runtime_dir=runtime_dir,
        pbkdf2_iterations=1000,
        login_fail_limit=5,
        login_fail_window_seconds=300,
    )
    app = create_app(settings)

    with TestClient(app) as client:
        store: Storage = app.state.store
        secret = app.state.secret

        app.state.user_store.create_user("viewer_user", "ViewerSecret123!", "viewer")
        viewer_token = create_token(secret, "viewer_user", "viewer", 3600)
        viewer_headers = {"Authorization": f"Bearer {viewer_token}"}

        case = store.create_case("Demo Read Case", "analyst", synthetic=True)
        case_id = case["case_id"]

        root = repo_root()
        cdr_src = root / "data" / "synthetic" / "out" / "case_demo_v2" / "cdr.csv"
        bank_src = root / "data" / "synthetic" / "out" / "case_demo_v2" / "bank.csv"
        if cdr_src.is_file():
            store.save_csv(case_id, "cdr", cdr_src.read_bytes())
        if bank_src.is_file():
            store.save_csv(case_id, "bank", bank_src.read_bytes())

        resp = client.get(f"/api/cases/{case_id}/timeline/insights", headers=viewer_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["case_id"] == case_id
        assert "rules" in data
        assert "insights" in data
        assert isinstance(data["count"], int)
        assert data["count"] == len(data["insights"])


def test_insights_scenario_determinism_and_rules(tmp_path: Path):
    from scripts.make_insights_scenario import generate_insights_scenario

    dir1 = tmp_path / "scenario_1"
    dir2 = tmp_path / "scenario_2"

    res1 = generate_insights_scenario(out_dir=dir1, seed=42)
    res2 = generate_insights_scenario(out_dir=dir2, seed=42)

    assert res1["cdr_rows"] == res2["cdr_rows"]
    assert res1["bank_rows"] == res2["bank_rows"]
    assert res1["fir_count"] == res2["fir_count"]

    # Verify exact byte match across generated files
    for name in ["cdr.csv", "bank.csv", "README.md"]:
        assert (dir1 / name).read_bytes() == (dir2 / name).read_bytes()

    assert (dir1 / "firs" / "FIR_101.txt").read_bytes() == (dir2 / "firs" / "FIR_101.txt").read_bytes()
    assert (dir1 / "analyses" / "FIR_101.analysis.json").read_bytes() == (dir2 / "analyses" / "FIR_101.analysis.json").read_bytes()

    # Now load into a dummy store and verify compute_timeline_insights produces all kinds
    store = _make_dummy_store(tmp_path)
    case = store.create_case("Insights Scenario Test", "analyst", synthetic=True)
    case_id = case["case_id"]

    store.save_csv(case_id, "cdr", (dir1 / "cdr.csv").read_bytes())
    store.save_csv(case_id, "bank", (dir1 / "bank.csv").read_bytes())

    res = compute_timeline_insights(store, case_id)
    assert res["reason"] is None
    assert 6 <= res["count"] <= 9
    assert res["count"] == len(res["insights"])

    kinds = {ins["kind"] for ins in res["insights"]}
    assert "call_spike" in kinds
    assert "transfer_spike" in kinds
    assert "call_then_transfer" in kinds
    assert "new_and_busy" in kinds

    call_spikes = [ins for ins in res["insights"] if ins["kind"] == "call_spike"]
    transfer_spikes = [ins for ins in res["insights"] if ins["kind"] == "transfer_spike"]
    correlations = [ins for ins in res["insights"] if ins["kind"] == "call_then_transfer"]
    new_busy = [ins for ins in res["insights"] if ins["kind"] == "new_and_busy"]

    assert len(call_spikes) == 2
    assert len(transfer_spikes) == 2
    assert len(correlations) == 2
    assert len(new_busy) == 3

