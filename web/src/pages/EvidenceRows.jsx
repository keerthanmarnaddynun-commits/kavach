import React from "react";

export function EvidenceRows({ caseId, fileKind, rowsParam }) {
  return (
    <div>
      <h3>Evidence CSV Rows: <span className="mono">{fileKind || "cdr"}</span></h3>
      <p style={{ color: "var(--muted)", fontSize: "12px" }}>
        Case: <span className="mono">{caseId}</span> | Requested rows: <span className="mono">{rowsParam || "none"}</span>
      </p>
    </div>
  );
}

export default EvidenceRows;
