"""Dump API fixture shapes for the frontend."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient

from kavach_api.app import create_app
from kavach_api.ingest import REQUIRED_BANK_COLUMNS, REQUIRED_CDR_COLUMNS
from kavach_api.settings import load_settings
from scripts.create_user import create_user
from scripts.load_demo_case import load_demo_case

FIXTURES_DIR = REPO_ROOT / "web" / "src" / "fixtures"


def sanitize(obj: Any) -> Any:
    """Sanitize data: drop *_at keys, cut long lists to 5, cut long strings to 800 chars."""
    if isinstance(obj, dict):
        new_dict = {}
        was_cut = False
        for k, v in sorted(obj.items()):
            if k.endswith("_at"):
                continue
            if isinstance(v, list) and len(v) > 5:
                v = v[:5]
                was_cut = True
            elif isinstance(v, str) and len(v) > 800:
                v = v[:800]
                was_cut = True
            new_dict[k] = sanitize(v)
        if was_cut:
            new_dict["_truncated"] = True
        return new_dict
    elif isinstance(obj, list):
        items = obj[:5] if len(obj) > 5 else obj
        return [sanitize(item) for item in items]
    elif isinstance(obj, str):
        if len(obj) > 800:
            return obj[:800]
        return obj
    return obj


def dump_fixtures(out_dir: Path | None = None) -> list[str]:
    target_dir = out_dir or FIXTURES_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    # Use a deterministic token generator so running twice yields identical outputs
    token_counter = 0

    def deterministic_hex(nbytes=None):
        nonlocal token_counter
        token_counter += 1
        h = f"{token_counter:04x}" * 16
        length = (nbytes or 8) * 2
        return h[:length]

    def deterministic_bytes(nbytes=16):
        return b"\xaa" * nbytes

    temp_runtime = tempfile.mkdtemp(prefix="kavach_dump_")
    saved_files: list[str] = []

    try:
        with patch("secrets.token_hex", side_effect=deterministic_hex), \
             patch("secrets.token_bytes", side_effect=deterministic_bytes):

            settings = load_settings(
                {
                    "KAVACH_RUNTIME_DIR": temp_runtime,
                    "KAVACH_PBKDF2_ITERATIONS": "1000",
                }
            )

            # Pre-create users
            create_user(settings, "viewer_user", "viewer", "ViewerPassword123!")
            create_user(settings, "analyst_user", "analyst", "AnalystPassword123!")

            # Load demo case
            demo_res = load_demo_case(settings=settings)
            case_id = demo_res["case_id"]

            app = create_app(settings)
            client = TestClient(app)

            # 1. Health
            r_health = client.get("/api/health")
            health_data = sanitize(r_health.json())

            # 2. Login
            r_login = client.post(
                "/api/auth/login",
                json={"username": "viewer_user", "password": "ViewerPassword123!"},
            )
            login_data = r_login.json()
            viewer_token = login_data.get("access_token", "")
            login_data["access_token"] = "REDACTED"
            login_data = sanitize(login_data)
            viewer_h = {"Authorization": f"Bearer {viewer_token}"}

            r_login_an = client.post(
                "/api/auth/login",
                json={"username": "analyst_user", "password": "AnalystPassword123!"},
            )
            analyst_token = r_login_an.json().get("access_token", "")
            analyst_h = {"Authorization": f"Bearer {analyst_token}"}

            # 3. Cases
            r_cases = client.get("/api/cases", headers=viewer_h)
            cases_data = sanitize(r_cases.json())

            # 4. Case Detail
            r_case_det = client.get(f"/api/cases/{case_id}", headers=viewer_h)
            case_detail_data = sanitize(r_case_det.json())

            # 5. Graph
            r_graph = client.get(f"/api/cases/{case_id}/graph", headers=viewer_h)
            graph_data = sanitize(r_graph.json())

            # 6. Leads
            r_leads = client.get(f"/api/cases/{case_id}/leads", headers=viewer_h)
            leads_data = sanitize(r_leads.json())

            # 7. People
            r_people = client.get(f"/api/cases/{case_id}/people", headers=viewer_h)
            people_data = sanitize(r_people.json())

            # 8. Node Detail (PERSON with FIR evidence)
            target_node_id = None
            full_graph = r_graph.json()
            for n in full_graph.get("nodes", []):
                ndata = n.get("data", {})
                if ndata.get("type") == "PERSON" and ndata.get("fir_evidence"):
                    target_node_id = ndata.get("id")
                    break
            if not target_node_id:
                for n in full_graph.get("nodes", []):
                    ndata = n.get("data", {})
                    if ndata.get("type") == "PERSON":
                        target_node_id = ndata.get("id")
                        break
            r_node = client.get(f"/api/cases/{case_id}/nodes/{target_node_id}", headers=viewer_h)
            node_detail_data = sanitize(r_node.json())

            # 9. Edge Detail (one FIR edge and one CSV edge)
            fir_edge_id = None
            csv_edge_id = None
            for e in full_graph.get("edges", []):
                edata = e.get("data", {})
                if edata.get("fir_evidence") and not fir_edge_id:
                    fir_edge_id = edata.get("id")
                if edata.get("csv_evidence") and not csv_edge_id:
                    csv_edge_id = edata.get("id")
                if fir_edge_id and csv_edge_id:
                    break

            r_edge_fir = client.get(f"/api/cases/{case_id}/edges/{fir_edge_id}", headers=viewer_h) if fir_edge_id else None
            r_edge_csv = client.get(f"/api/cases/{case_id}/edges/{csv_edge_id}", headers=viewer_h) if csv_edge_id else None

            edge_fir_data = sanitize(r_edge_fir.json()) if r_edge_fir else {}
            edge_csv_data = sanitize(r_edge_csv.json()) if r_edge_csv else {}

            combined_edge_detail = {
                "fir_edge": edge_fir_data,
                "csv_edge": edge_csv_data,
            }

            # 10. Document
            r_doc = client.get(f"/api/cases/{case_id}/documents/FIR_01", headers=viewer_h)
            doc_data = sanitize(r_doc.json())

            # 11. Rows
            r_rows = client.get(f"/api/cases/{case_id}/rows?file=cdr&rows=1,2,3", headers=viewer_h)
            rows_data = sanitize(r_rows.json())
            r_rows_bank = client.get(f"/api/cases/{case_id}/rows?file=bank&rows=1,2,3", headers=viewer_h)
            rows_bank_data = sanitize(r_rows_bank.json())

            # 12. Timeline day
            r_tl_day = client.get(f"/api/cases/{case_id}/timeline?bucket=day", headers=viewer_h)
            timeline_day_data = sanitize(r_tl_day.json())
            r_tl_hour = client.get(f"/api/cases/{case_id}/timeline?bucket=hour", headers=viewer_h)
            timeline_hour_data = sanitize(r_tl_hour.json())

            # 13. Break result
            p_list = r_people.json()
            p1 = p_list[0]["id"] if len(p_list) > 0 else "P1"
            p2 = p_list[1]["id"] if len(p_list) > 1 else "P2"
            r_break = client.post(
                f"/api/cases/{case_id}/break",
                json={"group_a": [p1], "group_b": [p2]},
                headers=analyst_h,
            )
            break_data = sanitize(r_break.json())

            # 14. Job
            job = app.state.job_store.create(kind="extract", case_id=case_id, total=1)
            job_id = job["job_id"]
            app.state.job_store.update(
                job_id,
                status="done",
                progress={"current": "completed", "done": 1, "total": 1},
                result={"documents": 1},
            )
            r_job = client.get(f"/api/jobs/{job_id}", headers=viewer_h)
            job_data = sanitize(r_job.json())

            # 15. CSV Columns
            csv_cols_data = {
                "bank": sorted(REQUIRED_BANK_COLUMNS),
                "cdr": sorted(REQUIRED_CDR_COLUMNS),
            }

            fixture_map: dict[str, Any] = {
                "health": health_data,
                "login": login_data,
                "cases": cases_data,
                "case_detail": case_detail_data,
                "graph": graph_data,
                "leads": leads_data,
                "people": people_data,
                "node_detail": node_detail_data,
                "edge_detail": combined_edge_detail,
                "edge_detail_fir": edge_fir_data,
                "edge_detail_csv": edge_csv_data,
                "document": doc_data,
                "rows": rows_data,
                "rows_bank": rows_bank_data,
                "timeline_day": timeline_day_data,
                "timeline_hour": timeline_hour_data,
                "break_result": break_data,
                "job": job_data,
                "csv_columns": csv_cols_data,
            }

            for name, data in fixture_map.items():
                fpath = target_dir / f"{name}.json"
                content = json.dumps(data, indent=2, sort_keys=True) + "\n"
                fpath.write_text(content, encoding="utf-8")
                saved_files.append(fpath.name)

    finally:
        shutil.rmtree(temp_runtime, ignore_errors=True)

    print(f"Dumped {len(saved_files)} fixture files to {target_dir}")
    return saved_files


def main() -> None:
    dump_fixtures()


if __name__ == "__main__":
    main()


