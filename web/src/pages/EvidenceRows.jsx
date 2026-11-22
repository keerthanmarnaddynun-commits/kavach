import React, { useState, useEffect, useMemo } from "react";
import { request } from "../api/client.js";
import { Table } from "../components/Table.jsx";
import { shortenHash, copyToClipboard } from "../lib/format.js";
import { parseRowsQuery } from "./evidenceHelpers.js";

export function EvidenceRows({ caseId, fileKind, route }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [errorText, setErrorText] = useState(null);
  const [copyStatus, setCopyStatus] = useState(false);

  const queryInfo = useMemo(() => {
    return parseRowsQuery(route || (typeof window !== "undefined" ? window.location.hash : ""));
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

  // Dynamically determine table columns from first row
  const columns = useMemo(() => {
    if (rows.length === 0) return [];
    const first = rows[0] || {};
    const keys = Object.keys(first);

    // Row number column first
    const cols = [
      {
        key: "row",
        header: "Row #",
        isNumeric: true,
        align: "right",
        headerStyle: { width: "70px" },
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
        render: (val) => (
          <span className={isId ? "mono" : ""}>
            {val !== null && val !== undefined ? String(val) : "-"}
          </span>
        ),
      });
    }

    return cols;
  }, [rows]);

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
            Rows Returned: <strong>{rows.length}</strong>
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
        />
      )}
    </div>
  );
}

export default EvidenceRows;
