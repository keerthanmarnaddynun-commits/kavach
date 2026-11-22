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

    # Use deterministic token generator so running twice yields identical outputs
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

            # 5. Full Graph
            r_graph = client.get(f"/api/cases/{case_id}/graph", headers=viewer_h)
            full_graph = r_graph.json()
            graph_nodes = full_graph.get("elements", {}).get("nodes", [])
            graph_edges = full_graph.get("elements", {}).get("edges", [])

            # (d) Subgraph: walk edges collecting end points until 12 nodes are collected
            collected_node_ids: set[str] = set()
            for e in graph_edges:
                src = e.get("data", {}).get("source")
                tgt = e.get("data", {}).get("target")
                if src and tgt:
                    needed = {src, tgt} - collected_node_ids
                    if len(collected_node_ids) + len(needed) <= 12:
                        collected_node_ids.update(needed)
                    if len(collected_node_ids) == 12:
                        break

            if len(collected_node_ids) < 12:
                for n in graph_nodes:
                    nid = n.get("data", {}).get("id")
                    if nid and nid not in collected_node_ids:
                        collected_node_ids.add(nid)
                        if len(collected_node_ids) == 12:
                            break

            node_map = {n.get("data", {}).get("id"): n for n in graph_nodes}
            final_nodes = [node_map[nid] for nid in sorted(collected_node_ids) if nid in node_map]
            final_edges = [
                e for e in graph_edges
                if e.get("data", {}).get("source") in collected_node_ids
                and e.get("data", {}).get("target") in collected_node_ids
            ]

            graph_data = {
                "elements": {
                    "edges": final_edges,
                    "nodes": final_nodes,
                },
                "summary": full_graph.get("summary", {}),
            }

            # 6. Leads
            r_leads = client.get(f"/api/cases/{case_id}/leads", headers=viewer_h)
            leads_raw = r_leads.json()
            leads_data = sanitize(leads_raw)

            # 7. People
            r_people = client.get(f"/api/cases/{case_id}/people", headers=viewer_h)
            people_data = sanitize(r_people.json())

            # (a) node_detail = real /nodes/<id> for first PERSON node (graph order) with fir_evidence
            node_detail_data = None
            for n in graph_nodes:
                ndata = n.get("data", {})
                if ndata.get("type") == "PERSON":
                    nid = ndata.get("id")
                    res = client.get(f"/api/cases/{case_id}/nodes/{nid}", headers=viewer_h)
                    if res.status_code == 200:
                        cand = res.json()
                        if cand.get("fir_evidence") and len(cand["fir_evidence"]) > 0:
                            node_detail_data = sanitize(cand)
                            break

            # (b) edge_detail_fir and edge_detail_csv
            edge_fir_data = None
            edge_csv_data = None
            for e in graph_edges:
                eid = e.get("data", {}).get("id")
                if not eid:
                    continue
                res = client.get(f"/api/cases/{case_id}/edges/{eid}", headers=viewer_h)
                if res.status_code == 200:
                    cand = res.json()
                    if not edge_fir_data and cand.get("fir_evidence") and len(cand["fir_evidence"]) > 0:
                        edge_fir_data = sanitize(cand)
                    if not edge_csv_data and cand.get("csv_evidence") and len(cand["csv_evidence"]) > 0:
                        edge_csv_data = sanitize(cand)
                    if edge_fir_data and edge_csv_data:
                        break

            # (f) Fail with clear message if node_detail, edge_detail_fir, or edge_detail_csv is invalid/empty
            if not node_detail_data or "error" in node_detail_data or not node_detail_data.get("fir_evidence"):
                raise RuntimeError(f"node_detail is invalid, empty, or missing fir_evidence: {node_detail_data}")
            if not edge_fir_data or "error" in edge_fir_data or not edge_fir_data.get("fir_evidence"):
                raise RuntimeError(f"edge_detail_fir is invalid, empty, or missing fir_evidence: {edge_fir_data}")
            if not edge_csv_data or "error" in edge_csv_data or not edge_csv_data.get("csv_evidence"):
                raise RuntimeError(f"edge_detail_csv is invalid, empty, or missing csv_evidence: {edge_csv_data}")

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

            # (c) break_result = real break between two persons giving finite: true and non-empty cut
            break_data = None
            priority_lead_persons = [p["person_id"] for p in leads_raw.get("priority_leads", []) if "person_id" in p]
            people_raw = r_people.json()
            all_person_ids = priority_lead_persons + [p["id"] for p in people_raw if p["id"] not in priority_lead_persons]

            pairs_tried = 0
            for i in range(len(all_person_ids)):
                for j in range(i + 1, len(all_person_ids)):
                    if pairs_tried >= 60:
                        break
                    pairs_tried += 1
                    pa = all_person_ids[i]
                    pb = all_person_ids[j]
                    r_brk = client.post(
                        f"/api/cases/{case_id}/break",
                        json={"group_a": [pa], "group_b": [pb]},
                        headers=analyst_h,
                    )
                    if r_brk.status_code == 200:
                        cand = r_brk.json()
                        if cand.get("finite") is True and len(cand.get("cut", [])) > 0:
                            break_data = sanitize(cand)
                            break
                if break_data or pairs_tried >= 60:
                    break

            if not break_data:
                pa = all_person_ids[0] if all_person_ids else "P1"
                pb = all_person_ids[1] if len(all_person_ids) > 1 else "P2"
                r_brk = client.post(
                    f"/api/cases/{case_id}/break",
                    json={"group_a": [pa], "group_b": [pb]},
                    headers=analyst_h,
                )
                break_data = sanitize(r_brk.json())

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
                "edge_detail": edge_fir_data,
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

            # (e) Write every fixture file as bytes with \n line endings
            for name, data in fixture_map.items():
                fpath = target_dir / f"{name}.json"
                content = json.dumps(data, indent=2, sort_keys=True) + "\n"
                content = content.replace("\r\n", "\n")
                fpath.write_bytes(content.encode("utf-8"))
                saved_files.append(fpath.name)

    finally:
        shutil.rmtree(temp_runtime, ignore_errors=True)

    print(f"Dumped {len(saved_files)} fixture files to {target_dir}")
    return saved_files


def main() -> None:
    dump_fixtures()


if __name__ == "__main__":
    main()
