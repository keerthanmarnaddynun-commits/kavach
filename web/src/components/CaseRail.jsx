import React, { useState } from "react";
import { canUpload } from "../lib/roles.js";
import { request } from "../api/client.js";

export function CaseRail({ cases, activeCaseId, user, onCaseCreated }) {
  const [creating, setCreating] = useState(false);
  const [newCaseName, setNewCaseName] = useState("");
  const [isSynthetic, setIsSynthetic] = useState(false);

  async function handleCreateCase(e) {
    e.preventDefault();
    if (!newCaseName.trim()) return;

    try {
      const res = await request("/cases", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: newCaseName.trim(), synthetic: isSynthetic }),
      });
      setCreating(false);
      setNewCaseName("");
      setIsSynthetic(false);
      if (onCaseCreated) {
        onCaseCreated(res);
      }
      window.location.hash = `#/case/${res.case_id}/intake`;
    } catch (err) {
      alert(err.message || "Failed to create case");
    }
  }

  const userCanCreate = user && canUpload(user.role);

  return (
    <aside className="case-rail">
      <div className="case-rail-header">
        <strong>Cases</strong>
        {userCanCreate && (
          <button type="button" onClick={() => setCreating(!creating)}>
            {creating ? "Cancel" : "+ New"}
          </button>
        )}
      </div>

      {creating && (
        <form onSubmit={handleCreateCase} style={{ padding: "8px 10px", borderBottom: "1px solid var(--border)" }}>
          <input
            type="text"
            placeholder="Case name"
            style={{ width: "100%", marginBottom: "6px" }}
            value={newCaseName}
            onChange={(e) => setNewCaseName(e.target.value)}
            required
            autoFocus
          />
          <div style={{ display: "flex", alignItems: "center", gap: "6px", marginBottom: "6px", fontSize: "11px" }}>
            <input
              type="checkbox"
              id="synthetic-check"
              checked={isSynthetic}
              onChange={(e) => setIsSynthetic(e.target.checked)}
            />
            <label htmlFor="synthetic-check">Synthetic</label>
          </div>
          <button type="submit" className="primary" style={{ width: "100%", fontSize: "11px" }}>
            Create Case
          </button>
        </form>
      )}

      {/* Navigation for active case */}
      {activeCaseId && (
        <nav className="case-rail-nav">
          <a
            href={`#/case/${activeCaseId}/overview`}
            className={window.location.hash.includes("/overview") ? "active" : ""}
          >
            Overview & Leads
          </a>
          <a
            href={`#/case/${activeCaseId}/intake`}
            className={window.location.hash.includes("/intake") ? "active" : ""}
          >
            Intake
          </a>
          <a
            href={`#/case/${activeCaseId}/graph`}
            className={window.location.hash.includes("/graph") ? "active" : ""}
          >
            Network Graph
          </a>
          <a
            href={`#/case/${activeCaseId}/people`}
            className={window.location.hash.includes("/people") ? "active" : ""}
          >
            People
          </a>
          <a
            href={`#/case/${activeCaseId}/break`}
            className={window.location.hash.includes("/break") ? "active" : ""}
          >
            Break Analysis
          </a>
          <a
            href={`#/case/${activeCaseId}/timeline`}
            className={window.location.hash.includes("/timeline") ? "active" : ""}
          >
            Timeline
          </a>
        </nav>
      )}

      {/* Case List */}
      <ul className="case-list">
        {cases.map((c) => {
          const isActive = c.case_id === activeCaseId;
          const docCnt = c.counts ? c.counts.documents : 0;
          const cdrCnt = c.counts ? c.counts.cdr_rows : 0;
          const bankCnt = c.counts ? c.counts.bank_rows : 0;

          return (
            <li
              key={c.case_id}
              className={`case-item ${isActive ? "active" : ""}`}
              onClick={() => {
                window.location.hash = `#/case/${c.case_id}/overview`;
              }}
            >
              <div className="case-item-title">{c.name}</div>
              <div className="case-item-meta">
                {c.synthetic ? "synthetic | " : ""}
                {c.analyzed ? "analyzed" : "not analyzed"}
              </div>
              <div className="case-item-meta mono">
                Docs: {docCnt} | CDR: {cdrCnt} | Bank: {bankCnt}
              </div>
            </li>
          );
        })}
      </ul>
    </aside>
  );
}

export default CaseRail;
