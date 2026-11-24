import React, { useState } from "react";
import { canUpload } from "../lib/roles.js";
import { request } from "../api/client.js";
import { getStoredSidebarCollapsed, setStoredSidebarCollapsed } from "../pages/graphHelpers.js";

export function CaseRail({ cases = [], activeCaseId, user, onCaseCreated, defaultCollapsed }) {
  const [creating, setCreating] = useState(false);
  const [newCaseName, setNewCaseName] = useState("");
  const [isSynthetic, setIsSynthetic] = useState(false);
  const [createError, setCreateError] = useState(null);

  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    if (typeof defaultCollapsed === "boolean") return defaultCollapsed;
    return getStoredSidebarCollapsed();
  });

  function toggleSidebar() {
    const next = !sidebarCollapsed;
    setSidebarCollapsed(next);
    setStoredSidebarCollapsed(next);
    if (typeof window !== "undefined") {
      setTimeout(() => {
        window.dispatchEvent(new Event("resize"));
      }, 0);
    }
  }

  async function handleCreateCase(e) {
    e.preventDefault();
    if (!newCaseName.trim()) return;

    setCreateError(null);
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
      setCreateError(err.message || "Failed to create case");
    }
  }

  const userCanCreate = user && canUpload(user.role);

  return (
    <aside
      className={`case-rail ${sidebarCollapsed ? "collapsed" : ""}`}
      style={{
        width: sidebarCollapsed ? "48px" : "200px",
        minWidth: sidebarCollapsed ? "48px" : "200px",
        maxWidth: sidebarCollapsed ? "48px" : "200px",
        flexShrink: 0,
      }}
    >
      <div
        className="case-rail-header"
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: sidebarCollapsed ? "center" : "space-between",
          padding: sidebarCollapsed ? "8px 4px" : "8px 10px",
        }}
      >
        {!sidebarCollapsed && <strong>Cases</strong>}
        <div style={{ display: "flex", alignItems: "center", gap: "4px" }}>
          {!sidebarCollapsed && userCanCreate && (
            <button
              type="button"
              onClick={() => setCreating(!creating)}
              style={{ fontSize: "11px", padding: "2px 6px" }}
            >
              {creating ? "Cancel" : "+ New"}
            </button>
          )}
          <button
            type="button"
            className="sidebar-toggle-btn"
            aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
            title={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
            onClick={toggleSidebar}
            style={{
              padding: "2px 6px",
              fontSize: "11px",
              cursor: "pointer",
            }}
          >
            {sidebarCollapsed ? "▶" : "◀"}
          </button>
        </div>
      </div>

      {!sidebarCollapsed && creating && (
        <form onSubmit={handleCreateCase} style={{ padding: "8px 10px", borderBottom: "1px solid var(--border)" }}>
          {createError && (
            <div className="error-text" style={{ marginBottom: "6px", fontSize: "11px" }}>
              {createError}
            </div>
          )}
          <label htmlFor="new-case-name" style={{ display: "block", fontSize: "11px", marginBottom: "2px" }}>
            Case Name
          </label>
          <input
            id="new-case-name"
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
        <nav
          className="case-rail-nav"
          style={{
            padding: sidebarCollapsed ? "8px 0" : "8px 0",
            display: "flex",
            flexDirection: "column",
          }}
        >
          <a
            href={`#/case/${activeCaseId}/overview`}
            className={typeof window !== "undefined" && window.location.hash.includes("/overview") ? "active" : ""}
            title="Overview & Leads"
            style={{ textAlign: sidebarCollapsed ? "center" : "left", padding: sidebarCollapsed ? "6px 0" : "5px 12px" }}
          >
            {sidebarCollapsed ? "O" : "Overview & Leads"}
          </a>
          <a
            href={`#/case/${activeCaseId}/intake`}
            className={typeof window !== "undefined" && window.location.hash.includes("/intake") ? "active" : ""}
            title="Intake"
            style={{ textAlign: sidebarCollapsed ? "center" : "left", padding: sidebarCollapsed ? "6px 0" : "5px 12px" }}
          >
            {sidebarCollapsed ? "I" : "Intake"}
          </a>
          <a
            href={`#/case/${activeCaseId}/graph`}
            className={typeof window !== "undefined" && window.location.hash.includes("/graph") ? "active" : ""}
            title="Network Graph"
            style={{ textAlign: sidebarCollapsed ? "center" : "left", padding: sidebarCollapsed ? "6px 0" : "5px 12px" }}
          >
            {sidebarCollapsed ? "G" : "Network Graph"}
          </a>
          <a
            href={`#/case/${activeCaseId}/people`}
            className={typeof window !== "undefined" && window.location.hash.includes("/people") ? "active" : ""}
            title="People"
            style={{ textAlign: sidebarCollapsed ? "center" : "left", padding: sidebarCollapsed ? "6px 0" : "5px 12px" }}
          >
            {sidebarCollapsed ? "P" : "People"}
          </a>
          <a
            href={`#/case/${activeCaseId}/break`}
            className={typeof window !== "undefined" && window.location.hash.includes("/break") ? "active" : ""}
            title="Break Analysis"
            style={{ textAlign: sidebarCollapsed ? "center" : "left", padding: sidebarCollapsed ? "6px 0" : "5px 12px" }}
          >
            {sidebarCollapsed ? "B" : "Break Analysis"}
          </a>
          <a
            href={`#/case/${activeCaseId}/timeline`}
            className={typeof window !== "undefined" && window.location.hash.includes("/timeline") ? "active" : ""}
            title="Timeline"
            style={{ textAlign: sidebarCollapsed ? "center" : "left", padding: sidebarCollapsed ? "6px 0" : "5px 12px" }}
          >
            {sidebarCollapsed ? "T" : "Timeline"}
          </a>
          <a
            href={`#/case/${activeCaseId}/dossier`}
            className={typeof window !== "undefined" && window.location.hash.includes("/dossier") ? "active" : ""}
            title="Dossier"
            style={{ textAlign: sidebarCollapsed ? "center" : "left", padding: sidebarCollapsed ? "6px 0" : "5px 12px" }}
          >
            {sidebarCollapsed ? "D" : "Dossier"}
          </a>
        </nav>
      )}

      {/* Case List */}
      <ul className="case-list" style={{ listStyle: "none", margin: 0, padding: 0 }}>
        {cases.map((c) => {
          const isActive = c.case_id === activeCaseId;
          const docCnt = c.counts ? c.counts.documents : 0;
          const cdrCnt = c.counts ? c.counts.cdr_rows : 0;
          const bankCnt = c.counts ? c.counts.bank_rows : 0;

          return (
            <li key={c.case_id} style={{ margin: 0, padding: 0 }}>
              <button
                type="button"
                className={`case-item ${isActive ? "active" : ""}`}
                style={{
                  width: "100%",
                  textAlign: sidebarCollapsed ? "center" : "left",
                  background: "none",
                  border: "none",
                  cursor: "pointer",
                  display: "block",
                  padding: sidebarCollapsed ? "8px 4px" : "8px 10px",
                }}
                title={`${c.name || c.case_id} (${c.case_id})`}
                onClick={() => {
                  window.location.hash = `#/case/${c.case_id}/overview`;
                }}
              >
                {sidebarCollapsed ? (
                  <div style={{ fontWeight: 600, fontSize: "11px" }}>
                    {c.name ? c.name.slice(0, 2).toUpperCase() : (c.case_id ? c.case_id.slice(0, 2) : "C")}
                  </div>
                ) : (
                  <>
                    <div className="case-item-title">{c.name}</div>
                    <div className="case-item-meta">
                      {c.synthetic ? "synthetic | " : ""}
                      {c.analyzed ? "analyzed" : "not analyzed"}
                    </div>
                    <div className="case-item-meta mono">
                      Docs: {docCnt} | CDR: {cdrCnt} | Bank: {bankCnt}
                    </div>
                  </>
                )}
              </button>
            </li>
          );
        })}
      </ul>
    </aside>
  );
}

export default CaseRail;
