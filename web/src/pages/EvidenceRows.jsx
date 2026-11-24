import React, { useState, useEffect, useMemo } from "react";
import { request } from "../api/client.js";
import { Table } from "../components/Table.jsx";
import { shortenHash, copyToClipboard } from "../lib/format.js";
import {
  parseRowsQuery,
  parseHighlightQuery,
  isExactOrNormalizedMatch,
  getEvidenceHighlightState,
} from "./evidenceHelpers.js";

export function EvidenceRows({ caseId, fileKind, route }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [errorText, setErrorText] = useState(null);
  const [copyStatus, setCopyStatus] = useState(false);
  const [currentMatchIdx, setCurrentMatchIdx] = useState(0);

  const queryInfo = useMemo(() => {
    return parseRowsQuery(route || (typeof window !== "undefined" ? window.location.hash : ""));
  }, [route]);

  const highlightTarget = useMemo(() => {
    return parseHighlightQuery(route || (typeof window !== "undefined" ? window.location.hash : ""));
  }, [route]);

  useEffect(() => {
    if (!caseId || !fileKind) return;
    setLoading(true);
    setErrorText(null);

    const rowsParam = queryInfo.rowNumbers.join(",");
    const queryStr = rowsParam ? `?file=${fileKind}&rows=${rowsParam}` : `?file=${fileKind}&rows=1,2,3`;

    request(`/cases/${caseId}/rows${queryStr}`)
      .then((res) => {
        setData(res);
      })
      .catch((err) => {
        setErrorText(err.message || "Failed to load rows");
      })
      .finally(() => {
        setLoading(false);
      });
  }, [caseId, fileKind, queryInfo.rowNumbers]);

  async function handleCopyHash() {
    if (!data || !data.sha256) return;
    const ok = await copyToClipboard(data.sha256);
    if (ok) {
      setCopyStatus(true);
      setTimeout(() => setCopyStatus(false), 2000);
    }
  }

  const rows = (data && data.rows) || [];

  const highlightState = useMemo(() => {
    return getEvidenceHighlightState({
      rows,
      highlightTarget,
      storedRowRefs: queryInfo.rowNumbers,
      fileKind,
    });
  }, [rows, highlightTarget, queryInfo.rowNumbers, fileKind]);

  // Reset active match index when target or rows change
  useEffect(() => {
    setCurrentMatchIdx(0);
  }, [highlightTarget, rows]);

  // Auto-scroll to active match (first match on load, or next match on button click)
  useEffect(() => {
    if (highlightState.highlightedRowIndices.length === 0 || rows.length === 0) return;
    const targetRow = rows[highlightState.highlightedRowIndices[currentMatchIdx]];
    if (!targetRow) return;
    const el = document.getElementById(`csv-row-${targetRow.row}`);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [currentMatchIdx, highlightState.highlightedRowIndices, rows]);

  function handleNextMatch() {
    if (highlightState.highlightedRowIndices.length <= 1) return;
    setCurrentMatchIdx((prev) => (prev + 1) % highlightState.highlightedRowIndices.length);
  }

  const getRowProps = (row) => ({
    id: `csv-row-${row.row}`,
    className: highlightState.highlightedRowSet.has(row.row) ? "highlighted-row" : "",
  });

  // Dynamically determine table columns from first row
  const columns = useMemo(() => {
    if (rows.length === 0) return [];
    const first = rows[0] || {};
    const keys = Object.keys(first);

    // Row number column first
    const cols = [
      {
        key: "row",
        header: "Data Row #",
        isNumeric: true,
        align: "right",
        headerStyle: { width: "85px" },
        render: (r) => <span className="mono">{r}</span>,
      },
    ];

    for (const k of keys) {
      if (k === "row") continue;
      const isId = [
        "a_party",
        "b_party",
        "imei_a",
        "imsi_a",
        "from_acct",
        "to_acct",
        "txn_id",
        "ifsc",
        "tower_id",
      ].includes(k);
      const isNum = ["amount", "duration_sec", "lat", "lon"].includes(k);

      cols.push({
        key: k,
        header: k.replace(/_/g, " ").toUpperCase(),
        isIdentifier: isId,
        isNumeric: isNum,
        align: isNum ? "right" : "left",
        render: (val) => {
          const isCellMatched = highlightTarget && isExactOrNormalizedMatch(val, highlightTarget);
          const cellContent = val !== null && val !== undefined ? String(val) : "-";
          return (
            <span className={isId ? "mono" : ""}>
              {isCellMatched ? (
                <mark
                  style={{
                    backgroundColor: "var(--accent-weak)",
                    color: "var(--accent)",
                    fontWeight: "700",
                    padding: "1px 4px",
                    borderRadius: "2px",
                  }}
                >
                  {cellContent}
                </mark>
              ) : (
                cellContent
              )}
            </span>
          );
        },
      });
    }

    return cols;
  }, [rows, highlightTarget]);

  return (
    <EvidenceRowsView
      caseId={caseId}
      fileKind={fileKind}
      data={data}
      rows={rows}
      columns={columns}
      loading={loading}
      errorText={errorText}
      queryInfo={queryInfo}
      copyStatus={copyStatus}
      handleCopyHash={handleCopyHash}
      highlightTarget={highlightTarget}
      highlightState={highlightState}
      currentMatchIdx={currentMatchIdx}
      handleNextMatch={handleNextMatch}
      getRowProps={getRowProps}
    />
  );
}

export function EvidenceRowsView({
  caseId,
  fileKind,
  data,
  rows = [],
  columns = [],
  loading = false,
  errorText = null,
  queryInfo = { isOverLimit: false, totalRequested: 0 },
  copyStatus = false,
  handleCopyHash,
  highlightTarget = "",
  highlightState = {
    bannerType: "none",
    bannerText: "",
    highlightedRowIndices: [],
    highlightedRowSet: new Set(),
    isEvidenceMode: false,
    matchCount: 0,
  },
  currentMatchIdx = 0,
  handleNextMatch,
  getRowProps,
}) {
  return (
    <div>
      {/* File Header Bar */}
      <div
        style={{
          padding: "10px 14px",
          backgroundColor: "var(--surface)",
          border: "1px solid var(--border)",
          marginBottom: "12px",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          fontSize: "12px",
          flexWrap: "wrap",
          gap: "10px",
        }}
      >
        <div style={{ display: "flex", gap: "16px", alignItems: "center" }}>
          <span>
            File: <strong>{data ? data.file || fileKind : fileKind}</strong>
          </span>
          <span>
            Rows Returned: <strong>{rows.length}</strong> (data rows, header excluded)
          </span>
          {data && data.sha256 && (
            <span>
              File Hash:{" "}
              <span className="mono" title={data.sha256}>
                {shortenHash(data.sha256, 12)}
              </span>
              {handleCopyHash && (
                <button
                  type="button"
                  className="copy-btn"
                  onClick={handleCopyHash}
                  style={{ marginLeft: "4px" }}
                >
                  {copyStatus ? "Copied" : "Copy"}
                </button>
              )}
            </span>
          )}
        </div>

        <div>
          <span style={{ color: "var(--muted)" }}>
            Case: <span className="mono">{caseId}</span>
          </span>
        </div>
      </div>

      {/* Highlight Banner or No-Match Note */}
      {highlightTarget && !loading && highlightState && highlightState.bannerType !== "none" && (
        highlightState.bannerType === "no_matches" ? (
          <div
            className="no-match-note"
            style={{
              padding: "8px 12px",
              backgroundColor: "var(--bg)",
              border: "1px solid var(--border)",
              borderRadius: "2px",
              marginBottom: "12px",
              fontSize: "12px",
              color: "var(--muted)",
            }}
          >
            No matching row found for <span className="mono">{highlightTarget}</span>.
          </div>
        ) : (
          <div
            className="highlight-banner"
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              padding: "8px 12px",
              backgroundColor: "var(--highlight)",
              border: "1px solid var(--highlight-border)",
              borderRadius: "2px",
              marginBottom: "12px",
              fontSize: "12px",
            }}
          >
            <div>
              <strong>{highlightState.matchCount}</strong>{" "}
              {highlightState.isEvidenceMode ? "evidence" : "matching"} row
              {highlightState.matchCount === 1 ? "" : "s"} highlighted for{" "}
              <span className="mono" style={{ fontWeight: "600" }}>{highlightTarget}</span>
              {highlightState.matchCount > 1 && (
                <span style={{ color: "var(--muted)", marginLeft: "8px", fontSize: "11px" }}>
                  (match {currentMatchIdx + 1} of {highlightState.matchCount})
                </span>
              )}
            </div>
            {highlightState.matchCount > 1 && (
              <button
                type="button"
                className="next-match-btn"
                onClick={handleNextMatch}
                style={{
                  padding: "3px 10px",
                  fontSize: "11px",
                  cursor: "pointer",
                  backgroundColor: "var(--surface)",
                  border: "1px solid var(--border)",
                  borderRadius: "2px",
                }}
              >
                Next match ▼
              </button>
            )}
          </div>
        )
      )}

      {/* Message if over 200 rows requested */}
      {queryInfo && queryInfo.isOverLimit && (
        <div
          style={{
            padding: "8px 12px",
            backgroundColor: "var(--bg)",
            border: "1px solid var(--border)",
            marginBottom: "12px",
            fontSize: "11px",
            color: "var(--muted)",
          }}
        >
          Notice: {queryInfo.totalRequested} rows were requested. The server returns at most 200 rows per query; the first 200 requested rows are shown below.
        </div>
      )}

      {errorText && (
        <div className="error-text" style={{ marginBottom: "12px" }}>
          {errorText}
        </div>
      )}

      {loading && <div>Loading raw records...</div>}

      {!loading && (
        <Table
          columns={columns}
          data={rows}
          keyField="row"
          initialSortKey="row"
          initialSortDir="asc"
          emptyMessage="No rows found for the requested query."
          getRowProps={getRowProps}
        />
      )}
    </div>
  );
}

export default EvidenceRows;
