import React, { useState, useEffect } from "react";
import { getToken, clearToken, request } from "./api/client.js";
import { shortenHash, copyToClipboard } from "./lib/format.js";
import { Login } from "./pages/Login.jsx";
import { CaseRail } from "./components/CaseRail.jsx";
import { Intake } from "./pages/Intake.jsx";

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

  // Load cases list helper
  function loadCases() {
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
  }

  useEffect(() => {
    loadCases();
  }, [user, activeCaseId]);

  // Load active case details
  function loadActiveCase() {
    if (user && activeCaseId) {
      request(`/cases/${activeCaseId}`)
        .then((data) => {
          setActiveCase(data);
        })
        .catch(() => {});
    }
  }

  useEffect(() => {
    loadActiveCase();
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
          <CaseRail
            cases={cases}
            activeCaseId={activeCaseId}
            user={user}
            onCaseCreated={(newCase) => {
              loadCases();
              setActiveCaseId(newCase.case_id);
            }}
          />
        )}

        {/* Content Pane */}
        <main className="main-content">
          {isLogin ? (
            <Login onLoginSuccess={() => (window.location.hash = "#/cases")} />
          ) : (
            <CaseContentView
              caseId={activeCaseId}
              subPage={subPage}
              user={user}
              activeCase={activeCase}
              onCaseUpdated={() => {
                loadCases();
                loadActiveCase();
              }}
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

function CaseContentView({ caseId, subPage, user, activeCase, onCaseUpdated }) {
  if (!caseId) {
    return <div>Select a case from the rail to inspect.</div>;
  }

  if (subPage === "intake") {
    return <Intake caseId={caseId} user={user} onCaseUpdated={onCaseUpdated} />;
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
