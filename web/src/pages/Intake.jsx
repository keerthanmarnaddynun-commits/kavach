import React, { useState, useEffect, useRef } from "react";
import { request, getToken } from "../api/client.js";
import { shortenHash } from "../lib/format.js";
import { canUpload, canAnalyze } from "../lib/roles.js";
import {
  reduceUploadResult,
  buildRowErrorViewModel,
  reduceJobProgress,
} from "./intakeReducers.js";
import { SSEParser } from "../api/sse.js";
import csvColsFixture from "../fixtures/csv_columns.json";

export function Intake({ caseId, user, onCaseUpdated }) {
  const [documents, setDocuments] = useState([]);
  const [filesInfo, setFilesInfo] = useState({});
  const [uploadError, setUploadError] = useState(null);
  const [rowErrors, setRowErrors] = useState(null);
  const [uploading, setUploading] = useState(false);

  // Document form state
  const [pastedName, setPastedName] = useState("");
  const [pastedText, setPastedText] = useState("");
  const fileInputRef = useRef(null);
  const cdrInputRef = useRef(null);
  const bankInputRef = useRef(null);

  // Background Job tracking
  const [activeJob, setActiveJob] = useState(null);
  const [jobProgress, setJobProgress] = useState(null);

  const userCanUpload = user && canUpload(user.role);
  const userCanAnalyze = user && canAnalyze(user.role);

  // Load documents and case files on mount or caseId change
  useEffect(() => {
    if (!caseId) return;

    request(`/cases/${caseId}`)
      .then((data) => {
        setDocuments(data.documents || []);
        setFilesInfo(data.files || {});
      })
      .catch((err) => setUploadError(err.message));
  }, [caseId]);

  // SSE streaming listener with polling fallback for active job
  useEffect(() => {
    if (!activeJob) return;

    let aborted = false;
    const controller = new AbortController();

    async function streamJobEvents() {
      try {
        const token = getToken();
        const headers = token ? { Authorization: `Bearer ${token}` } : {};
        const resp = await fetch(`/api/jobs/${activeJob}/events`, {
          headers,
          signal: controller.signal,
        });

        if (!resp.ok) {
          throw new Error("SSE connection failed");
        }

        const reader = resp.body.getReader();
        const decoder = new TextDecoder("utf-8");
        const parser = new SSEParser();

        while (!aborted) {
          const { done, value } = await reader.read();
          if (done) break;

          const textChunk = decoder.decode(value, { stream: true });
          const events = parser.feed(textChunk);

          for (const ev of events) {
            if (ev.event === "progress" && ev.data) {
              setJobProgress((prev) => reduceJobProgress(prev || {}, ev.data));
              if (ev.data.status === "done" || ev.data.status === "failed") {
                aborted = true;
                if (onCaseUpdated) onCaseUpdated();
                break;
              }
            }
          }
        }
      } catch {
        // Fallback to polling every 1 second
        if (aborted) return;
        const pollTimer = setInterval(async () => {
          if (aborted) {
            clearInterval(pollTimer);
            return;
          }
          try {
            const data = await request(`/jobs/${activeJob}`);
            setJobProgress((prev) => reduceJobProgress(prev || {}, data));
            if (data.status === "done" || data.status === "failed") {
              aborted = true;
              clearInterval(pollTimer);
              if (onCaseUpdated) onCaseUpdated();
            }
          } catch {
            clearInterval(pollTimer);
          }
        }, 1000);

        return () => clearInterval(pollTimer);
      }
    }

    streamJobEvents();

    return () => {
      aborted = true;
      controller.abort();
    };
  }, [activeJob, onCaseUpdated]);

  // Handle document upload (files and/or pasted text)
  async function handleDocumentUpload(e) {
    e.preventDefault();
    setUploadError(null);
    setRowErrors(null);
    setUploading(true);

    const formData = new FormData();
    const files = fileInputRef.current ? fileInputRef.current.files : [];

    for (let i = 0; i < files.length; i++) {
      formData.append("files", files[i]);
    }

    if (pastedText.trim()) {
      formData.append("text", pastedText.trim());
      if (pastedName.trim()) {
        formData.append("name", pastedName.trim());
      }
    }

    try {
      const res = await request(`/cases/${caseId}/documents`, {
        method: "POST",
        body: formData,
      });

      setPastedName("");
      setPastedText("");
      if (fileInputRef.current) fileInputRef.current.value = "";

      // Refresh documents
      const caseDetail = await request(`/cases/${caseId}`);
      setDocuments(caseDetail.documents || []);

      if (res && res.job_id) {
        setActiveJob(res.job_id);
        setJobProgress({ jobId: res.job_id, status: "queued", done: 0, total: 1, percent: 0 });
      }
    } catch (err) {
      setUploadError(err.message);
      if (err.details) {
        setRowErrors(err.details);
      }
    } finally {
      setUploading(false);
    }
  }

  // Handle CSV file upload (CDR or Bank)
  async function handleCsvUpload(kind, fileObj) {
    if (!fileObj) return;

    setUploadError(null);
    setRowErrors(null);
    setUploading(true);

    const formData = new FormData();
    formData.append("file", fileObj);

    try {
      await request(`/cases/${caseId}/${kind}`, {
        method: "POST",
        body: formData,
      });

      const caseDetail = await request(`/cases/${caseId}`);
      setFilesInfo(caseDetail.files || {});
      if (onCaseUpdated) onCaseUpdated();
    } catch (err) {
      setUploadError(err.message);
      if (err.details) {
        setRowErrors(err.details);
      }
    } finally {
      setUploading(false);
    }
  }

  // Handle case analyze trigger
  async function handleAnalyze() {
    setUploadError(null);
    try {
      const res = await request(`/cases/${caseId}/analyze`, {
        method: "POST",
      });
      if (res && res.job_id) {
        setActiveJob(res.job_id);
        setJobProgress({ jobId: res.job_id, status: "queued", done: 0, total: 1, percent: 0 });
      }
    } catch (err) {
      setUploadError(err.message);
    }
  }

  const rowErrorVm = buildRowErrorViewModel(rowErrors);
  const cdrColumns = (csvColsFixture && csvColsFixture.cdr) || [
    "a_party", "b_party", "imei_a", "imsi_a", "start_time", "duration_sec", "call_type", "tower_id", "lat", "lon"
  ];
  const bankColumns = (csvColsFixture && csvColsFixture.bank) || [
    "txn_id", "datetime", "from_acct", "to_acct", "amount", "mode", "ifsc", "narration"
  ];

  return (
    <div>
      <div className="disclaimer-box">
        <strong>Notice:</strong> Typed text only: no scanned images (no OCR).
      </div>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
        <h3>Case Intake: <span className="mono">{caseId}</span></h3>
        {userCanAnalyze && (
          <button type="button" className="primary" onClick={handleAnalyze} disabled={uploading}>
            Run Analysis
          </button>
        )}
      </div>

      {uploadError && (
        <div className="error-text" style={{ marginBottom: "12px", padding: "8px", border: "1px solid var(--danger)", borderRadius: "2px" }}>
          {uploadError}
        </div>
      )}

      {/* Row Error Table for CSV Failures */}
      {rowErrorVm.errors.length > 0 && (
        <div style={{ marginBottom: "16px" }}>
          <h4 style={{ color: "var(--danger)", marginBottom: "6px" }}>
            CSV Validation Errors ({rowErrorVm.displayedCount} of {rowErrorVm.totalCount} shown)
          </h4>
          <table className="dense-table">
            <thead>
              <tr>
                <th style={{ width: "60px" }}>Row</th>
                <th style={{ width: "120px" }}>Column</th>
                <th style={{ width: "140px" }}>Code</th>
                <th>Message</th>
              </tr>
            </thead>
            <tbody>
              {rowErrorVm.errors.map((e, idx) => (
                <tr key={idx}>
                  <td className="mono">{e.row}</td>
                  <td className="mono">{e.column}</td>
                  <td>{e.code}</td>
                  <td>{e.message}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Job Progress Indicator */}
      {jobProgress && (
        <div style={{ padding: "10px", backgroundColor: "var(--surface)", border: "1px solid var(--border)", marginBottom: "16px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: "11px", marginBottom: "4px" }}>
            <span>Job: <span className="mono">{jobProgress.jobId}</span> ({jobProgress.status})</span>
            <span>{jobProgress.done} / {jobProgress.total} ({jobProgress.percent}%)</span>
          </div>
          <div className="progress-container">
            <div className="progress-bar" style={{ width: `${jobProgress.percent}%` }} />
          </div>
          {jobProgress.current && (
            <div style={{ fontSize: "11px", color: "var(--muted)" }}>{jobProgress.current}</div>
          )}
        </div>
      )}

      {/* Upload Controls (Analysts & Admins only) */}
      {userCanUpload && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px", marginBottom: "20px" }}>
          {/* Documents Form */}
          <div style={{ backgroundColor: "var(--surface)", padding: "12px", border: "1px solid var(--border)", borderRadius: "2px" }}>
            <h4 style={{ marginBottom: "10px" }}>Upload FIR Documents</h4>
            <form onSubmit={handleDocumentUpload} style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
              <div>
                <label style={{ display: "block", fontSize: "11px", color: "var(--muted)", marginBottom: "2px" }}>
                  Select .txt files
                </label>
                <input type="file" multiple accept=".txt" ref={fileInputRef} disabled={uploading} />
              </div>
              <div>
                <label style={{ display: "block", fontSize: "11px", color: "var(--muted)", marginBottom: "2px" }}>
                  Or paste text
                </label>
                <input
                  type="text"
                  placeholder="Optional filename/title"
                  value={pastedName}
                  onChange={(e) => setPastedName(e.target.value)}
                  style={{ width: "100%", marginBottom: "4px" }}
                  disabled={uploading}
                />
                <textarea
                  rows={4}
                  placeholder="Paste FIR text here..."
                  value={pastedText}
                  onChange={(e) => setPastedText(e.target.value)}
                  style={{ width: "100%" }}
                  disabled={uploading}
                />
              </div>
              <button type="submit" className="primary" disabled={uploading}>
                {uploading ? "Uploading..." : "Upload Document(s)"}
              </button>
            </form>
          </div>

          {/* CSV Upload Section */}
          <div style={{ backgroundColor: "var(--surface)", padding: "12px", border: "1px solid var(--border)", borderRadius: "2px" }}>
            <h4 style={{ marginBottom: "10px" }}>Upload Call & Bank Records</h4>

            {/* CDR Upload */}
            <div style={{ marginBottom: "12px" }}>
              <strong>CDR CSV:</strong>
              <div style={{ fontSize: "10px", color: "var(--muted)", marginBottom: "4px" }}>
                Columns: <span className="mono">{cdrColumns.join(", ")}</span>
              </div>
              <input
                type="file"
                accept=".csv"
                ref={cdrInputRef}
                onChange={(e) => handleCsvUpload("cdr", e.target.files[0])}
                disabled={uploading}
              />
              {filesInfo.cdr && (
                <div style={{ fontSize: "11px", marginTop: "2px" }} className="mono">
                  Rows: {filesInfo.cdr.rows || filesInfo.cdr.row_count || 0} | Hash: {shortenHash(filesInfo.cdr.sha256, 8)}
                </div>
              )}
            </div>

            {/* Bank Upload */}
            <div>
              <strong>Bank Transactions CSV:</strong>
              <div style={{ fontSize: "10px", color: "var(--muted)", marginBottom: "4px" }}>
                Columns: <span className="mono">{bankColumns.join(", ")}</span>
              </div>
              <input
                type="file"
                accept=".csv"
                ref={bankInputRef}
                onChange={(e) => handleCsvUpload("bank", e.target.files[0])}
                disabled={uploading}
              />
              {filesInfo.bank && (
                <div style={{ fontSize: "11px", marginTop: "2px" }} className="mono">
                  Rows: {filesInfo.bank.rows || filesInfo.bank.row_count || 0} | Hash: {shortenHash(filesInfo.bank.sha256, 8)}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Documents Table */}
      <div>
        <h4 style={{ marginBottom: "8px" }}>Case Documents ({documents.length})</h4>
        {documents.length === 0 ? (
          <div style={{ padding: "12px", backgroundColor: "var(--surface)", border: "1px solid var(--border)", color: "var(--muted)" }}>
            No documents uploaded yet.
          </div>
        ) : (
          <table className="dense-table">
            <thead>
              <tr>
                <th style={{ width: "120px" }}>Doc ID</th>
                <th>Filename</th>
                <th style={{ width: "90px" }}>Status</th>
                <th style={{ width: "90px" }}>Characters</th>
                <th style={{ width: "120px" }}>Hash</th>
                <th style={{ width: "100px" }}>Error</th>
              </tr>
            </thead>
            <tbody>
              {documents.map((doc) => (
                <tr key={doc.doc_id}>
                  <td className="mono">{doc.doc_id}</td>
                  <td>{doc.filename || doc.name || "-"}</td>
                  <td>{doc.status || "uploaded"}</td>
                  <td className="mono">{doc.char_count || doc.characters || (doc.text ? doc.text.length : "-")}</td>
                  <td className="mono">{shortenHash(doc.sha256_raw || doc.document_hash, 12)}</td>
                  <td className="error-text">{doc.error_code || "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

export default Intake;
