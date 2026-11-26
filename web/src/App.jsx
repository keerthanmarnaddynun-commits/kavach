import React, { useState, useEffect, useCallback } from "react";
import { getToken, clearToken, request, setUnauthorizedHandler } from "./api/client.js";
import { formatCaseFingerprint, copyToClipboard } from "./lib/format.js";
import { getLimitations } from "./pages/overviewHelpers.js";
import { Login } from "./pages/Login.jsx";
import { CaseRail } from "./components/CaseRail.jsx";
import { Intake } from "./pages/Intake.jsx";
import { Overview } from "./pages/Overview.jsx";
import { People } from "./pages/People.jsx";
import { Graph } from "./pages/Graph.jsx";
import { EvidenceDoc } from "./pages/EvidenceDoc.jsx";
import { EvidenceRows } from "./pages/EvidenceRows.jsx";
import { Break } from "./pages/Break.jsx";
import { Timeline } from "./pages/Timeline.jsx";
import { TimelineInsights } from "./pages/TimelineInsights.jsx";
import { Dossier } from "./pages/Dossier.jsx";

export function App() {
  const [route, setRoute] = useState(() => window.location.hash || "#/cases");
  const [user, setUser] = useState(null);
  const [cases, setCases] = useState([]);
  const [casesError, setCasesError] = useState(null);
  const [activeCaseId, setActiveCaseId] = useState(null);
  const [activeCase, setActiveCase] = useState(null);
  const [activeCaseError, setActiveCaseError] = useState(null);
  const [activeCaseLeads, setActiveCaseLeads] = useState(null);
  const [showLimits, setShowLimits] = useState(false);
  const [copyStatus, setCopyStatus] = useState(false);

  // Register 401 unauthorized handler to clear session
  useEffect(() => {
    setUnauthorizedHandler(() => {
      clearToken();
      setUser(null);
      setCases([]);
      setActiveCaseId(null);
      setActiveCase(null);
      setActiveCaseLeads(null);
      window.location.hash = "#/login";
    });
  }, []);

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
  const subRoutePath = caseMatch && caseMatch[2] ? caseMatch[2] : "overview";
  const subPage = subRoutePath.split("?")[0].split("/")[0];

  // Set document title dynamically
  useEffect(() => {
    if (typeof document === "undefined") return;
    if (isLogin) {
      document.title = "KAVACH - Login";
    } else if (routeCaseId) {
      const pageTitle = subPage ? subPage.charAt(0).toUpperCase() + subPage.slice(1) : "Overview";
      document.title = `KAVACH - ${routeCaseId} [${pageTitle}]`;
    } else {
      document.title = "KAVACH - Cases";
    }
  }, [isLogin, routeCaseId, subPage]);

  useEffect(() => {
    if (routeCaseId && routeCaseId !== activeCaseId) {
      setActiveCaseId(routeCaseId);
    }
  }, [routeCaseId, activeCaseId]);

  // Sync default route #/cases to active case overview once loaded
  useEffect(() => {
    if (activeCaseId && (route === "#/cases" || route === "#/" || !route)) {
      window.location.hash = `#/case/${activeCaseId}/overview`;
    }
  }, [activeCaseId, route]);

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
  const loadCases = useCallback(() => {
    if (user) {
      setCasesError(null);
      request("/cases")
        .then((data) => {
          setCases(data || []);
          if (!activeCaseId && data && data.length > 0) {
            setActiveCaseId(data[0].case_id);
          }
        })
        .catch((err) => {
          setCasesError(err.message || "Failed to load cases");
        });
    }
  }, [user, activeCaseId]);

  useEffect(() => {
    loadCases();
  }, [loadCases]);

  // Load active case details and leads if analyzed
  const loadActiveCase = useCallback(() => {
    if (user && activeCaseId) {
      setActiveCaseError(null);
      request(`/cases/${activeCaseId}`)
        .then((data) => {
          setActiveCase(data);
          if (data && data.case && data.case.analyzed) {
            request(`/cases/${activeCaseId}/leads`)
              .then((leads) => setActiveCaseLeads(leads))
              .catch(() => setActiveCaseLeads(null));
          } else {
            setActiveCaseLeads(null);
          }
        })
        .catch((err) => {
          setActiveCaseError(err.message || "Failed to load case details");
        });
    }
  }, [user, activeCaseId]);

  useEffect(() => {
    loadActiveCase();
  }, [loadActiveCase]);

  const handleCaseUpdated = useCallback(() => {
    loadCases();
    loadActiveCase();
  }, [loadCases, loadActiveCase]);

  function handleLogout() {
    clearToken();
    setUser(null);
    setCases([]);
    setActiveCaseId(null);
    setActiveCase(null);
    setActiveCaseLeads(null);
    window.location.hash = "#/login";
  }

  const isAnalyzed = Boolean(activeCase && activeCase.case && activeCase.case.analyzed);
  const docHash = activeCaseLeads ? activeCaseLeads.document_hash : "";
  const displayFingerprint = formatCaseFingerprint(isAnalyzed, docHash);

  async function handleCopyHash() {
    if (!isAnalyzed || !docHash) return;
    const ok = await copyToClipboard(docHash);
    if (ok) {
      setCopyStatus(true);
      setTimeout(() => setCopyStatus(false), 2000);
    }
  }

  const limitsList = getLimitations(isAnalyzed, activeCaseLeads ? activeCaseLeads.limitations : null);

  return (
    <div className="app-container">
      {/* Status Bar */}
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
                <span className="mono" title={docHash || "not analyzed"}>
                  {displayFingerprint}
                </span>
                {isAnalyzed && docHash && (
                  <button
                    type="button"
                    className="copy-btn"
                    onClick={handleCopyHash}
                    title="Copy full fingerprint"
                  >
                    {copyStatus ? "Copied" : "Copy"}
                  </button>
                )}
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

      {/* Main Workspace Layout */}
      <div className="workspace">
        {/* Case Rail */}
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
        <main className={`main-content ${subPage === "graph" ? "graph-view" : ""}`}>
          {casesError && (
            <div className="error-text" style={{ marginBottom: "12px" }}>
              {casesError}
            </div>
          )}
          {activeCaseError && (
            <div className="error-text" style={{ marginBottom: "12px" }}>
              {activeCaseError}
            </div>
          )}

          {isLogin ? (
            <Login onLoginSuccess={() => (window.location.hash = "#/cases")} />
          ) : (
            <ErrorBoundary>
              <CaseContentView
                caseId={activeCaseId}
                route={route}
                subPage={subPage}
                user={user}
                activeCase={activeCase}
                onCaseUpdated={handleCaseUpdated}
                onLimitsLoaded={(limits) => {
                  if (limits && activeCaseLeads) {
                    // Leads loaded via Overview
                  }
                }}
              />
            </ErrorBoundary>
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
            backgroundColor: "var(--modal-backdrop)",
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
              <button type="button" onClick={() => setShowLimits(false)}>
                Close
              </button>
            </div>
            <ul style={{ paddingLeft: "20px", fontSize: "12px", lineHeight: "1.6" }}>
              {limitsList.map((limit, idx) => (
                <li key={idx}>{limit}</li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}

function CaseContentView({ caseId, route, subPage, user, activeCase, onCaseUpdated }) {
  if (!caseId) {
    return <div>Select a case from the rail to inspect.</div>;
  }

  // Evidence document route: #/case/<id>/evidence/doc/<doc_id>
  const docMatch = route.match(/^#\/case\/[^/]+\/evidence\/doc\/(.+)$/);
  if (docMatch) {
    const docId = docMatch[1].split("?")[0];
    return <EvidenceDoc caseId={caseId} docId={docId} route={route} />;
  }

  // Evidence rows route: #/case/<id>/evidence/rows/<file>?...
  const rowsMatch = route.match(/^#\/case\/[^/]+\/evidence\/rows\/([^?]+)(?:\?(.*))?$/);
  if (rowsMatch) {
    const fileKind = rowsMatch[1];
    return <EvidenceRows caseId={caseId} fileKind={fileKind} route={route} />;
  }

  // Timeline insights route: #/case/<id>/timeline/insights
  const insightsMatch = route.match(/^#\/case\/[^/]+\/timeline\/insights(?:\?(.*))?$/);
  if (insightsMatch) {
    return <TimelineInsights caseId={caseId} route={route} />;
  }

  if (subPage === "intake") {
    return <Intake caseId={caseId} user={user} onCaseUpdated={onCaseUpdated} />;
  }

  if (subPage === "people") {
    return <People caseId={caseId} />;
  }

  if (subPage === "graph") {
    return <Graph caseId={caseId} route={route} />;
  }

  if (subPage === "break") {
    return <Break caseId={caseId} user={user} />;
  }

  if (subPage === "timeline") {
    return <Timeline caseId={caseId} />;
  }

  if (subPage === "dossier") {
    return <Dossier caseId={caseId} user={user} />;
  }

  if (subPage === "overview" || !subPage) {
    return <Overview caseId={caseId} activeCase={activeCase} />;
  }

  // 404 Not Found Page for unknown subpage routes
  return (
    <div style={{ padding: "24px", backgroundColor: "var(--surface)", border: "1px solid var(--border)", borderRadius: "2px" }}>
      <h3 style={{ marginBottom: "8px" }}>Page Not Found (404)</h3>
      <p style={{ color: "var(--muted)", marginBottom: "16px" }}>
        The requested page <span className="mono">{subPage}</span> does not exist in this case.
      </p>
      <a href={`#/case/${caseId}/overview`} className="table-link">
        Return to Overview
      </a>
    </div>
  );
}

export function ErrorBoundaryFallback({ error, onRetry }) {
  return (
    <div style={{ padding: "16px", color: "var(--danger)" }}>
      <h4 style={{ marginBottom: "8px" }}>View rendering error</h4>
      <pre style={{ fontSize: "11px", whiteSpace: "pre-wrap" }}>
        {error?.message || String(error)}
      </pre>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          style={{ marginTop: "8px" }}
        >
          Retry
        </button>
      )}
    </div>
  );
}

export class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error("ErrorBoundary caught error:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <ErrorBoundaryFallback
          error={this.state.error}
          onRetry={() => this.setState({ hasError: false, error: null })}
        />
      );
    }
    return this.props.children;
  }
}

export default App;
