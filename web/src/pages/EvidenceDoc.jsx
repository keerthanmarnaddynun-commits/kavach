import React from "react";

export function EvidenceDoc({ caseId, docId }) {
  return (
    <div>
      <h3>Evidence Document: <span className="mono">{docId || "FIR_01"}</span></h3>
      <p style={{ color: "var(--muted)", fontSize: "12px" }}>
        Case: <span className="mono">{caseId}</span>. Full document viewer with highlighted spans and hash details.
      </p>
    </div>
  );
}

export default EvidenceDoc;
