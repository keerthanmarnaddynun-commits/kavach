#!/usr/bin/env python3
"""Read-only timing script for KAVACH case processing.

Extracts timing records from backend runtime files (case metadata, document
meta JSONs, CSV files metadata, job records, and audit log entries) to report
upload timestamps, stage durations, and total end-to-end processing time.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent


def parse_iso(ts_str: str | None) -> datetime | None:
    """Safely parse an ISO 8601 string into a timezone-aware datetime."""
    if not ts_str:
        return None
    try:
        # Normalize trailing Z to UTC offset
        normalized = ts_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def format_duration(seconds: float | None) -> str:
    """Format duration in seconds into human-readable string."""
    if seconds is None:
        return "N/A"
    if seconds < 0:
        return "0.00 s"
    if seconds < 60:
        return f"{seconds:.2f} s"
    mins, secs = divmod(seconds, 60)
    if mins < 60:
        return f"{int(mins)}m {secs:.1f}s"
    hours, mins = divmod(mins, 60)
    return f"{int(hours)}h {int(mins)}m {secs:.0f}s"


def find_latest_case(cases_dir: Path) -> str | None:
    """Find the most recently created or modified case ID."""
    if not cases_dir.exists():
        return None

    candidate_cases = []
    for cdir in cases_dir.iterdir():
        if not cdir.is_dir() or not cdir.name.startswith("C-"):
            continue
        case_json_path = cdir / "case.json"
        dt = None
        if case_json_path.is_file():
            try:
                data = json.loads(case_json_path.read_text(encoding="utf-8"))
                dt = parse_iso(data.get("created_at"))
            except Exception:
                pass
        if dt is None:
            try:
                mtime = cdir.stat().st_mtime
                dt = datetime.fromtimestamp(mtime, tz=timezone.utc)
            except Exception:
                continue
        candidate_cases.append((dt, cdir.name))

    if not candidate_cases:
        return None

    candidate_cases.sort(key=lambda x: x[0], reverse=True)
    return candidate_cases[0][1]


def load_audit_events_for_case(audit_path: Path, case_id: str) -> list[dict[str, Any]]:
    """Read all audit log entries for a given case_id."""
    events: list[dict[str, Any]] = []
    if not audit_path.is_file():
        return events

    try:
        with open(audit_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if entry.get("case_id") == case_id:
                        events.append(entry)
                except Exception:
                    continue
    except Exception:
        pass

    events.sort(key=lambda e: e.get("ts", ""))
    return events


def inspect_case_timing(case_id: str, runtime_dir: Path) -> dict[str, Any]:
    """Inspect and compile all timing records for the given case_id."""
    case_dir = runtime_dir / "cases" / case_id
    if not case_dir.is_dir():
        raise FileNotFoundError(f"Case directory not found: {case_dir}")

    # 1. Case info
    case_json_path = case_dir / "case.json"
    case_meta: dict[str, Any] = {}
    if case_json_path.is_file():
        try:
            case_meta = json.loads(case_json_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    case_name = case_meta.get("name", "Unknown")
    case_created_ts = case_meta.get("created_at")
    case_created_dt = parse_iso(case_created_ts)

    # 2. Document upload timestamps
    docs_dir = case_dir / "documents"
    doc_uploads: list[tuple[datetime, str, str]] = []  # (dt, doc_id, source)
    if docs_dir.is_dir():
        for mpath in docs_dir.glob("*.meta.json"):
            try:
                mdata = json.loads(mpath.read_text(encoding="utf-8"))
                ts = mdata.get("uploaded_at")
                dt = parse_iso(ts)
                doc_id = mdata.get("doc_id", mpath.stem.replace(".meta", ""))
                if dt:
                    doc_uploads.append((dt, doc_id, f"documents/{mpath.name} uploaded_at"))
            except Exception:
                continue

    # 3. CSV file upload timestamps
    files_json_path = case_dir / "files.json"
    csv_uploads: list[tuple[datetime, str, str]] = []  # (dt, kind, source)
    if files_json_path.is_file():
        try:
            fdata = json.loads(files_json_path.read_text(encoding="utf-8"))
            for kind in ("cdr", "bank"):
                if kind in fdata and isinstance(fdata[kind], dict):
                    ts = fdata[kind].get("uploaded_at")
                    dt = parse_iso(ts)
                    if dt:
                        csv_uploads.append((dt, kind, f"files.json {kind}.uploaded_at"))
        except Exception:
            pass

    # 4. Audit events
    audit_path = runtime_dir / "audit.log"
    audit_events = load_audit_events_for_case(audit_path, case_id)

    # Correlate upload events from audit log
    for e in audit_events:
        action = e.get("action")
        ts = e.get("ts")
        dt = parse_iso(ts)
        if not dt:
            continue
        detail = e.get("detail", {})
        if action == "document_uploaded":
            doc_id = detail.get("doc_id", "doc")
            doc_uploads.append((dt, doc_id, "audit.log document_uploaded"))
        elif action == "file_uploaded":
            kind = detail.get("file_type", "csv")
            csv_uploads.append((dt, kind, "audit.log file_uploaded"))
        elif action == "demo_loaded":
            doc_uploads.append((dt, "demo_batch", "audit.log demo_loaded"))

    # Determine earliest upload timestamp
    all_upload_dts = [item[0] for item in doc_uploads + csv_uploads]
    if case_created_dt:
        all_upload_dts.append(case_created_dt)

    earliest_upload_dt = min(all_upload_dts) if all_upload_dts else None
    earliest_source = "N/A"
    if earliest_upload_dt:
        for dt, name, src in doc_uploads:
            if dt == earliest_upload_dt:
                earliest_source = f"{src} ({name})"
                break
        else:
            for dt, name, src in csv_uploads:
                if dt == earliest_upload_dt:
                    earliest_source = f"{src} ({name})"
                    break
            else:
                if earliest_upload_dt == case_created_dt:
                    earliest_source = "case.json created_at"

    # 5. Job records for this case
    jobs_dir = runtime_dir / "jobs"
    case_jobs: list[dict[str, Any]] = []
    if jobs_dir.is_dir():
        for jpath in jobs_dir.glob("J-*.json"):
            try:
                jdata = json.loads(jpath.read_text(encoding="utf-8"))
                if jdata.get("case_id") == case_id:
                    case_jobs.append(jdata)
            except Exception:
                continue

    case_jobs.sort(key=lambda j: j.get("created_at", ""))

    # Compile stage timeline
    stages: list[dict[str, Any]] = []
    used_timestamps: list[dict[str, str]] = []

    # Map audit log job events
    audit_job_started = {
        e.get("detail", {}).get("job_id"): (parse_iso(e.get("ts")), e.get("ts"))
        for e in audit_events
        if e.get("action") == "job_started" and e.get("detail", {}).get("job_id")
    }
    audit_job_finished = {
        e.get("detail", {}).get("job_id"): (parse_iso(e.get("ts")), e.get("ts"))
        for e in audit_events
        if e.get("action") == "job_finished" and e.get("detail", {}).get("job_id")
    }

    if case_jobs:
        for idx, job in enumerate(case_jobs, start=1):
            jid = job.get("job_id", f"J-{idx}")
            kind = job.get("kind", "unknown")
            status = job.get("status", "unknown")

            # Determine start
            start_dt = None
            start_source = ""
            if jid in audit_job_started and audit_job_started[jid][0]:
                start_dt = audit_job_started[jid][0]
                start_source = f"audit.log action=job_started ({audit_job_started[jid][1]})"
            else:
                start_ts = job.get("created_at")
                start_dt = parse_iso(start_ts)
                start_source = f"jobs/{jid}.json created_at ({start_ts})"

            # Determine finish
            finish_dt = None
            finish_source = ""
            if jid in audit_job_finished and audit_job_finished[jid][0]:
                finish_dt = audit_job_finished[jid][0]
                finish_source = f"audit.log action=job_finished ({audit_job_finished[jid][1]})"
            elif status in ("done", "failed"):
                finish_ts = job.get("updated_at")
                finish_dt = parse_iso(finish_ts)
                finish_source = f"jobs/{jid}.json updated_at ({finish_ts})"

            duration = None
            if start_dt and finish_dt:
                duration = max(0.0, (finish_dt - start_dt).total_seconds())

            stages.append({
                "stage_num": idx,
                "job_id": jid,
                "kind": kind,
                "status": status,
                "start_dt": start_dt,
                "start_source": start_source,
                "finish_dt": finish_dt,
                "finish_source": finish_source,
                "duration_sec": duration,
                "progress": job.get("progress"),
                "errors": job.get("errors", []),
            })

    # 6. Results ready timestamp
    # Look for the last finished stage, or derived files
    results_ready_dt: datetime | None = None
    results_ready_source = ""

    # Check finished stages
    for stg in reversed(stages):
        if stg["finish_dt"] and stg["status"] == "done":
            results_ready_dt = stg["finish_dt"]
            results_ready_source = stg["finish_source"]
            break

    # Also check derived files (leads.json, graph.json)
    derived_dir = case_dir / "derived"
    derived_timestamps: list[tuple[datetime, str]] = []
    if derived_dir.is_dir():
        for dfile in ["graph.json", "leads.json", "fingerprint.json"]:
            p = derived_dir / dfile
            if p.is_file():
                try:
                    # check mtime
                    mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
                    derived_timestamps.append((mtime, f"derived/{dfile} mtime"))
                except Exception:
                    pass

    # If no stage finish time was found, use derived files or audit log
    if not results_ready_dt and derived_timestamps:
        latest_derived = max(derived_timestamps, key=lambda x: x[0])
        results_ready_dt = latest_derived[0]
        results_ready_source = latest_derived[1]

    # If demo_loaded was the sole audit event
    demo_events = [e for e in audit_events if e.get("action") == "demo_loaded"]
    if not results_ready_dt and demo_events:
        ts = demo_events[-1].get("ts")
        results_ready_dt = parse_iso(ts)
        results_ready_source = f"audit.log action=demo_loaded ({ts})"

    # Calculate total duration
    total_duration_sec = None
    if earliest_upload_dt and results_ready_dt:
        total_duration_sec = max(0.0, (results_ready_dt - earliest_upload_dt).total_seconds())

    return {
        "case_id": case_id,
        "case_name": case_name,
        "runtime_dir": str(runtime_dir),
        "earliest_upload": {
            "dt": earliest_upload_dt,
            "iso": earliest_upload_dt.isoformat() if earliest_upload_dt else "N/A",
            "source": earliest_source,
        },
        "doc_count": len(doc_uploads),
        "csv_count": len(csv_uploads),
        "stages": stages,
        "results_ready": {
            "dt": results_ready_dt,
            "iso": results_ready_dt.isoformat() if results_ready_dt else "N/A",
            "source": results_ready_source,
        },
        "total_duration_sec": total_duration_sec,
        "has_job_records": len(stages) > 0,
        "audit_event_count": len(audit_events),
    }


def print_timing_report(info: dict[str, Any]) -> None:
    """Print readable timing report to stdout."""
    print("=" * 72)
    print("KAVACH Case Processing Timing Report")
    print("=" * 72)
    print(f"Case ID:        {info['case_id']}")
    print(f"Case Name:      {info['case_name']}")
    print(f"Runtime Dir:    {info['runtime_dir']}")
    print()

    print("--- 1. UPLOAD TIMELINE ---")
    upload_info = info["earliest_upload"]
    print(f"First Upload:   {upload_info['iso']}")
    print(f"Source Used:    {upload_info['source']}")
    print(f"Items Tracked:  {info['doc_count']} documents, {info['csv_count']} CSV files")
    print()

    print("--- 2. STAGE EXECUTION & DURATION ---")
    if not info["has_job_records"]:
        print("Note: Per-stage job records (runtime/jobs/*.json) were not found for this case.")
        print("      (e.g. Case was initialized via demo loader or historical job files were cleared)")
    else:
        for stg in info["stages"]:
            print(f"Stage {stg['stage_num']} [{stg['kind']}]:")
            print(f"  Job ID:       {stg['job_id']}")
            print(f"  Status:       {stg['status']}")
            start_iso = stg['start_dt'].isoformat() if stg['start_dt'] else "N/A"
            finish_iso = stg['finish_dt'].isoformat() if stg['finish_dt'] else "N/A"
            print(f"  Started:      {start_iso}  [{stg['start_source']}]")
            print(f"  Finished:     {finish_iso}  [{stg['finish_source']}]")
            print(f"  Duration:     {format_duration(stg['duration_sec'])}")
            if stg.get("progress"):
                prog = stg["progress"]
                print(f"  Progress:     {prog.get('done', 0)} / {prog.get('total', 0)}")
            print()

    print("--- 3. END-TO-END SUMMARY ---")
    rr = info["results_ready"]
    print(f"First Upload:   {upload_info['iso']}")
    print(f"Results Ready:  {rr['iso']}")
    print(f"Source Used:    {rr['source']}")
    print(f"Total Pipeline: {format_duration(info['total_duration_sec'])}")
    print("=" * 72)


def main() -> None:
    parser = argparse.ArgumentParser(description="Report timing and stage durations for a KAVACH case.")
    parser.add_argument(
        "--case-id",
        "-c",
        default=None,
        help="Target case ID (e.g. C-927fc7de12). If omitted, picks the latest case.",
    )
    parser.add_argument(
        "--runtime-dir",
        "-r",
        default=None,
        help="Path to KAVACH runtime directory (defaults to runtime/ or KAVACH_RUNTIME_DIR)",
    )
    args = parser.parse_args()

    runtime_dir_str = args.runtime_dir or os.environ.get("KAVACH_RUNTIME_DIR", str(REPO_ROOT / "runtime"))
    runtime_dir = Path(runtime_dir_str).resolve()

    if not runtime_dir.is_dir():
        print(f"Error: Runtime directory does not exist: {runtime_dir}", file=sys.stderr)
        sys.exit(1)

    case_id = args.case_id
    if not case_id:
        case_id = find_latest_case(runtime_dir / "cases")
        if not case_id:
            print(f"Error: No cases found in {runtime_dir / 'cases'}", file=sys.stderr)
            sys.exit(1)
        print(f"Auto-selected latest case: {case_id}")

    try:
        report = inspect_case_timing(case_id, runtime_dir)
        print_timing_report(report)
    except Exception as exc:
        print(f"Error inspecting case timing: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
