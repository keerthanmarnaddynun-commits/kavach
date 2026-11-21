import React, { useState, useEffect } from "react";
import { getToken, clearToken, request } from "./api/client.js";
import { shortenHash, copyToClipboard } from "./lib/format.js";
import { canUpload, canAnalyze, canBreak } from "./lib/roles.js";

const DEFAULT_LIMITS = [
  "Relation extraction from FIR text measured F1 0.32 on an independent held-out set.",
  "Identifiers (phone, Aadhaar, PAN, UPI, vehicle) were strong; IFSC codes are not extracted.",
  "There is no OCR (typed text only).",
  "CDR and bank CSV files must use the exact required column names.",
  "All tuning data was synthetic.",
  "The 0.70 chip threshold was chosen after looking at one case and is labelled not evaluated.",
  "Break results ignore unobserved links on the call layer.",
  "The audit hash chain is unkeyed.",
  "The login limiter counts failures per user name.",
];

export function App() {
  const [route, setRoute] = useState(() => window.location.hash || "#/cases");
  const [user, setUser] = useState(null);
  const [cases, setCases] = useState([]);
  const [activeCaseId, setActiveCaseId] = useState(null);
  const [activeCase, setActiveCase] = useState(null);
  const [showLimits, setShowLimits] = useState(false);
  const [copyStatus, setCopyStatus] = useState(false);

  // Hash route listener
  useEffect(() => {
    function handleHashChange() {
      setRoute(window.location.hash || "#/cases");
    }
    window.addEventListener("hashchange", handleHashChange);
    return () => window.removeEventListener("hashchange", handleHashChange);
  }, []);

  // Parse current route
  const isLogin = route.startsWith("#/login");
  const caseMatch = route.match(/^#\/case\/([^/]+)(?:\/(.*))?$/);
  const routeCaseId = caseMatch ? caseMatch[1] : null;
  const subPage = caseMatch && caseMatch[2] ? caseMatch[2].split("?")[0] : "overview";

  useEffect(() => {
    if (routeCaseId && routeCaseId !== activeCaseId) {
      setActiveCaseId(routeCaseId);
    }
  }, [routeCaseId, activeCaseId]);

  // Auth me check on load
  useEffect(() => {
    const token = getToken();
    if (!token && !isLogin) {
      window.location.hash = "#/login";
      return;
    }
    if (token) {
      request("/auth/me")
        .then((userData) => {
          setUser(userData);
        })
        .catch(() => {
          clearToken();
          setUser(null);
          window.location.hash = "#/login";
        });
    }
  }, [isLogin]);

  // Load cases list
  useEffect(() => {
    if (user) {
      request("/cases")
        .then((data) => {
          setCases(data || []);
          if (!activeCaseId && data && data.length > 0) {
            setActiveCaseId(data[0].case_id);
          }
        })
        .catch(() => {});
    }
  }, [user, activeCaseId]);

  // Load active case details
  useEffect(() => {
    if (user && activeCaseId) {
      request(`/cases/${activeCaseId}`)
        .then((data) => {
          setActiveCase(data);
        })
        .catch(() => {});
    }
  }, [user, activeCaseId]);

  function handleLogout() {
    clearToken();
    setUser(null);
    window.location.hash = "#/login";
  }

  async function handleCopyHash(hash) {
    const ok = await copyToClipboard(hash);
    if (ok) {
      setCopyStatus(true);
      setTimeout(() => setCopyStatus(false), 2000);
    }
  }

  const caseFingerprint = activeCase && activeCase.case ? activeCase.case.case_id : activeCaseId || "";
  const shortFingerprint = shortenHash(caseFingerprint, 12);

  return (
    <div className="app-container">
      {/* 28px Status Bar */}
      <header className="status-bar">
        <div className="status-bar-left">
          <span className="status-brand">KAVACH</span>
          {activeCaseId && (
            <>
              <span className="status-item">
                <span>Case:</span>
                <span className="mono">{activeCaseId}</span>
              </span>
              <span className="status-item">
                <span>Hash:</span>
                <span className="mono" title={caseFingerprint}>{shortFingerprint}</span>
                <button
                  type="button"
                  className="copy-btn"
                  onClick={() => handleCopyHash(caseFingerprint)}
                  title="Copy full fingerprint"
                >
                  {copyStatus ? "Copied" : "Copy"}
                </button>
              </span>
            </>
          )}
        </div>
        <div className="status-bar-right">
          {user ? (
            <>
              <span className="status-item">
                <span>{user.username}</span>
                <span className="role-chip">{user.role}</span>
              </span>
              <button type="button" onClick={handleLogout}>
                Logout
              </button>
            </>
          ) : (
            <a href="#/login">Login</a>
          )}
        </div>
      </header>

      {/* Main Layout Area */}
      <div className="workspace">
        {/* 200px Case Rail */}
        {!isLogin && (
          <aside className="case-rail">
            <div className="case-rail-header">
              <strong>Cases</strong>
              {user && canUpload(user.role) && (
                <button
                  type="button"
                  onClick={() => {
                    const name = window.prompt("New case name:");
                    if (name) {
                      request("/cases", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ name }),
                      }).then((created) => {
                        window.location.hash = `#/case/${created.case_id}/intake`;
                      });
                    }
                  }}
                >
                  + New
                </button>
              )}
            </div>

            {/* Navigation links for active case */}
            {activeCaseId && (
              <nav className="case-rail-nav">
                <a
                  href={`#/case/${activeCaseId}/overview`}
                  className={subPage === "overview" ? "active" : ""}
                >
                  Overview & Leads
                </a>
                <a
                  href={`#/case/${activeCaseId}/intake`}
                  className={subPage === "intake" ? "active" : ""}
                >
                  Intake
                </a>
                <a
                  href={`#/case/${activeCaseId}/graph`}
                  className={subPage === "graph" ? "active" : ""}
                >
                  Network Graph
                </a>
                <a
                  href={`#/case/${activeCaseId}/people`}
                  className={subPage === "people" ? "active" : ""}
                >
                  People
                </a>
                <a
                  href={`#/case/${activeCaseId}/break`}
                  className={subPage === "break" ? "active" : ""}
                >
                  Break Analysis
                </a>
                <a
                  href={`#/case/${activeCaseId}/timeline`}
                  className={subPage === "timeline" ? "active" : ""}
                >
                  Timeline
                </a>
              </nav>
            )}

            {/* Case List */}
            <ul className="case-list">
              {cases.map((c) => (
                <li
                  key={c.case_id}
                  className={`case-item ${c.case_id === activeCaseId ? "active" : ""}`}
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
                    Docs: {c.counts ? c.counts.documents : 0} | CDR: {c.counts ? c.counts.cdr_rows : 0} | Bank: {c.counts ? c.counts.bank_rows : 0}
                  </div>
                </li>
              ))}
            </ul>
          </aside>
        )}

        {/* Content Pane */}
        <main className="main-content">
          {isLogin ? (
            <LoginPage onLoginSuccess={() => (window.location.hash = "#/cases")} />
          ) : (
            <CaseContentView
              caseId={activeCaseId}
              subPage={subPage}
              user={user}
              activeCase={activeCase}
            />
          )}
        </main>
      </div>

      {/* Footer & Limits Modal */}
      <footer className="app-footer">
        <div>KAVACH Decision Support System</div>
        <div>
          <button type="button" onClick={() => setShowLimits(true)}>
            System Limits
          </button>
        </div>
      </footer>

      {showLimits && (
        <div
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: "rgba(0,0,0,0.4)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 1000,
          }}
          onClick={() => setShowLimits(false)}
        >
          <div
            style={{
              backgroundColor: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: "2px",
              padding: "16px",
              maxWidth: "600px",
              width: "90%",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "12px" }}>
              <strong>System Limitations</strong>
              <button type="button" onClick={() => setShowLimits(false)}>Close</button>
            </div>
            <ul style={{ paddingLeft: "20px", fontSize: "12px", lineHeight: "1.6" }}>
              {DEFAULT_LIMITS.map((limit, idx) => (
                <li key={idx}>{limit}</li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}

function LoginPage({ onLoginSuccess }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [errorMsg, setErrorMsg] = useState("");

  async function handleSubmit(e) {
    e.preventDefault();
    setErrorMsg("");
    try {
      const res = await request("/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      if (res && res.access_token) {
        setToken(res.access_token);
        onLoginSuccess();
      }
    } catch (err) {
      setErrorMsg(err.message || "Login failed");
    }
  }

  return (
    <div style={{ maxWidth: "320px", margin: "60px auto" }}>
      <h2 style={{ marginBottom: "16px" }}>Login to KAVACH</h2>
      {errorMsg && <div className="error-text" style={{ marginBottom: "12px" }}>{errorMsg}</div>}
      <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
        <div>
          <label style={{ display: "block", marginBottom: "4px" }}>User Name</label>
          <input
            type="text"
            style={{ width: "100%" }}
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
            autoFocus
          />
        </div>
        <div>
          <label style={{ display: "block", marginBottom: "4px" }}>Password</label>
          <input
            type="password"
            style={{ width: "100%" }}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </div>
        <button type="submit" className="primary" style={{ marginTop: "8px" }}>
          Login
        </button>
      </form>
    </div>
  );
}

function CaseContentView({ caseId, subPage, user, activeCase }) {
  if (!caseId) {
    return <div>Select a case from the rail to inspect.</div>;
  }

  return (
    <div>
      <div className="disclaimer-box">
        Decision-support leads only. Financial ranking by money flow; structural centrality metrics are provided for structural explanation only.
      </div>
      <h3>Case: {activeCase && activeCase.case ? activeCase.case.name : caseId}</h3>
      <p style={{ marginTop: "8px", color: "var(--muted)" }}>
        Page: <strong>{subPage}</strong>. Active investigator view.
      </p>
    </div>
  );
}

export default App;
