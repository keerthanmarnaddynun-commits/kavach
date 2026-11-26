import React, { useState, useEffect, useMemo } from "react";
import { request } from "../api/client.js";
import { canAnalyze } from "../lib/roles.js";
import { validateBreakGroups, buildBreakViewModel, findBreakExamples } from "./breakHelpers.js";
import { saveHighlightIds } from "./graphHelpers.js";

export function Break({ caseId, user }) {
  const [people, setPeople] = useState([]);
  const [loadingPeople, setLoadingPeople] = useState(true);
  const [peopleError, setPeopleError] = useState(null);

  // Group selection state
  const [filterTextA, setFilterTextA] = useState("");
  const [filterTextB, setFilterTextB] = useState("");
  const [groupA, setGroupA] = useState([]);
  const [groupB, setGroupB] = useState([]);

  // Examples state
  const [examples, setExamples] = useState([]);
  const [loadingExamples, setLoadingExamples] = useState(false);

  // Break analysis execution state
  const [running, setRunning] = useState(false);
  const [serverError, setServerError] = useState(null);
  const [clientError, setClientError] = useState(null);
  const [resultData, setResultData] = useState(null);

  const isAnalyst = user && canAnalyze(user.role);

  // Load people for selection
  useEffect(() => {
    if (!caseId || !isAnalyst) return;
    setLoadingPeople(true);
    setPeopleError(null);

    request(`/cases/${caseId}/people`)
      .then((data) => {
        setPeople(data || []);
      })
      .catch((err) => {
        setPeopleError(err.message || "Failed to load case people");
      })
      .finally(() => {
        setLoadingPeople(false);
      });
  }, [caseId, isAnalyst]);

  // Lazily find examples once case individuals are loaded
  useEffect(() => {
    if (!caseId || !isAnalyst || people.length === 0) {
      setExamples([]);
      setLoadingExamples(false);
      return;
    }
    let cancelled = false;
    setLoadingExamples(true);

    findBreakExamples(caseId, people, request, () => cancelled)
      .then((found) => {
        if (!cancelled) {
          setExamples(found || []);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setExamples([]);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoadingExamples(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [caseId, isAnalyst, people]);

  function handleSelectExample(example) {
    if (!example) return;
    setClientError(null);
    setServerError(null);
    setGroupA(example.groupA || []);
    setGroupB(example.groupB || []);
    // Example buttons must only SELECT people: no analysis, no result shown.
    setResultData(null);
  }

  function handleClear() {
    setFilterTextA("");
    setFilterTextB("");
    setGroupA([]);
    setGroupB([]);
    setClientError(null);
    setServerError(null);
    setResultData(null);
  }

  function handleToggleA(personId) {
    setClientError(null);
    setGroupA((prev) =>
      prev.includes(personId) ? prev.filter((id) => id !== personId) : [...prev, personId]
    );
  }

  function handleToggleB(personId) {
    setClientError(null);
    setGroupB((prev) =>
      prev.includes(personId) ? prev.filter((id) => id !== personId) : [...prev, personId]
    );
  }

  async function handleRunBreak() {
    setClientError(null);
    setServerError(null);

    const val = validateBreakGroups(groupA, groupB);
    if (!val.valid) {
      setClientError(val.error);
      return;
    }

    setRunning(true);
    try {
      const res = await request(`/cases/${caseId}/break`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ group_a: groupA, group_b: groupB }),
      });
      setResultData(res);
    } catch (err) {
      setServerError(err.message || "Failed to execute break analysis");
    } finally {
      setRunning(false);
    }
  }

  const breakVm = useMemo(() => {
    return buildBreakViewModel(resultData);
  }, [resultData]);

  if (!isAnalyst) {
    return (
      <div style={{ padding: "16px", backgroundColor: "var(--surface)", border: "1px solid var(--border)" }}>
        Requires the analyst role
      </div>
    );
  }

  return (
    <BreakView
      caseId={caseId}
      people={people}
      loadingPeople={loadingPeople}
      peopleError={peopleError}
      filterTextA={filterTextA}
      setFilterTextA={setFilterTextA}
      filterTextB={filterTextB}
      setFilterTextB={setFilterTextB}
      groupA={groupA}
      groupB={groupB}
      onToggleA={handleToggleA}
      onToggleB={handleToggleB}
      onRunBreak={handleRunBreak}
      running={running}
      clientError={clientError}
      serverError={serverError}
      breakVm={breakVm}
      examples={examples}
      loadingExamples={loadingExamples}
      onSelectExample={handleSelectExample}
      onClear={handleClear}
    />
  );
}

export function BreakView({
  caseId,
  people = [],
  loadingPeople = false,
  peopleError = null,
  filterTextA = "",
  setFilterTextA,
  filterTextB = "",
  setFilterTextB,
  groupA = [],
  groupB = [],
  onToggleA,
  onToggleB,
  onRunBreak,
  onClear,
  running = false,
  clientError = null,
  serverError = null,
  breakVm = null,
  examples = [],
  loadingExamples = false,
  onSelectExample,
}) {
  const filteredA = useMemo(() => {
    const q = filterTextA.trim().toLowerCase();
    return people.filter((p) => {
      if (!q) return true;
      const name = (p.name || "").toLowerCase();
      const id = (p.id || p.person_id || "").toLowerCase();
      return name.includes(q) || id.includes(q);
    });
  }, [people, filterTextA]);

  const filteredB = useMemo(() => {
    const q = filterTextB.trim().toLowerCase();
    return people.filter((p) => {
      if (!q) return true;
      const name = (p.name || "").toLowerCase();
      const id = (p.id || p.person_id || "").toLowerCase();
      return name.includes(q) || id.includes(q);
    });
  }, [people, filterTextB]);

  return (
    <div>
      <div style={{ marginBottom: "16px" }}>
        <h3 style={{ margin: "0 0 6px 0" }}>Courier Break Analysis</h3>
        <p style={{ margin: 0, fontSize: "12px", color: "var(--muted)" }}>
          Identifies critical bridging contacts on the call layer between two selected investigator groups.
        </p>
      </div>

      {peopleError && (
        <div className="error-text" style={{ marginBottom: "12px" }}>
          {peopleError}
        </div>
      )}

      {loadingPeople && <div>Loading case individuals...</div>}

      {!loadingPeople && (
        <div>
          {/* Example Buttons */}
          {loadingExamples && (
            <div style={{ marginBottom: "12px", fontSize: "12px", color: "var(--muted)" }}>
              Finding examples...
            </div>
          )}
          {!loadingExamples && examples && examples.length > 0 && (
            <div style={{ display: "flex", gap: "8px", marginBottom: "12px", flexWrap: "wrap", alignItems: "center" }}>
              <span style={{ fontSize: "12px", fontWeight: "bold" }}>Try an example:</span>
              {examples.map((ex, idx) => (
                <button
                  key={idx}
                  type="button"
                  className="secondary"
                  style={{ fontSize: "11px", padding: "4px 8px" }}
                  onClick={() => onSelectExample && onSelectExample(ex)}
                >
                  {ex.label}
                </button>
              ))}
            </div>
          )}

          {/* Two Group Selectors */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px", marginBottom: "16px" }}>
            {/* Group A Box */}
            <div
              style={{
                backgroundColor: "var(--surface)",
                border: "1px solid var(--border)",
                padding: "12px",
                borderRadius: "2px",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
                <strong>Group A ({groupA.length} selected, max 200)</strong>
                <input
                  type="text"
                  placeholder="Filter Group A..."
                  value={filterTextA}
                  onChange={(e) => setFilterTextA && setFilterTextA(e.target.value)}
                  style={{ width: "150px", fontSize: "11px" }}
                />
              </div>

              <div
                style={{
                  maxHeight: "180px",
                  overflowY: "auto",
                  border: "1px solid var(--border)",
                  backgroundColor: "var(--bg)",
                  padding: "4px",
                }}
              >
                {filteredA.map((p) => {
                  const pid = p.id || p.person_id;
                  const isChecked = groupA.includes(pid);
                  return (
                    <label
                      key={pid}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "6px",
                        fontSize: "11px",
                        padding: "2px 4px",
                        cursor: "pointer",
                      }}
                    >
                      <input
                        type="checkbox"
                        checked={isChecked}
                        onChange={() => onToggleA && onToggleA(pid)}
                      />
                      <span><strong>{p.name}</strong></span>
                      <span className="mono" style={{ fontSize: "10px", color: "var(--muted)" }}>({pid})</span>
                    </label>
                  );
                })}
              </div>
            </div>

            {/* Group B Box */}
            <div
              style={{
                backgroundColor: "var(--surface)",
                border: "1px solid var(--border)",
                padding: "12px",
                borderRadius: "2px",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
                <strong>Group B ({groupB.length} selected, max 200)</strong>
                <input
                  type="text"
                  placeholder="Filter Group B..."
                  value={filterTextB}
                  onChange={(e) => setFilterTextB && setFilterTextB(e.target.value)}
                  style={{ width: "150px", fontSize: "11px" }}
                />
              </div>

              <div
                style={{
                  maxHeight: "180px",
                  overflowY: "auto",
                  border: "1px solid var(--border)",
                  backgroundColor: "var(--bg)",
                  padding: "4px",
                }}
              >
                {filteredB.map((p) => {
                  const pid = p.id || p.person_id;
                  const isChecked = groupB.includes(pid);
                  return (
                    <label
                      key={pid}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "6px",
                        fontSize: "11px",
                        padding: "2px 4px",
                        cursor: "pointer",
                      }}
                    >
                      <input
                        type="checkbox"
                        checked={isChecked}
                        onChange={() => onToggleB && onToggleB(pid)}
                      />
                      <span><strong>{p.name}</strong></span>
                      <span className="mono" style={{ fontSize: "10px", color: "var(--muted)" }}>({pid})</span>
                    </label>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Validation & Server Error Display */}
          {clientError && (
            <div className="error-text" style={{ marginBottom: "12px" }}>
              {clientError}
            </div>
          )}
          {serverError && (
            <div className="error-text" style={{ marginBottom: "12px" }}>
              {serverError}
            </div>
          )}

          <div style={{ marginBottom: "20px", display: "flex", gap: "10px" }}>
            <button
              type="button"
              className="primary"
              onClick={onRunBreak}
              disabled={running}
            >
              {running ? "Calculating Cut..." : "Run Break Analysis"}
            </button>
            <button
              type="button"
              className="secondary"
              onClick={onClear}
              disabled={running}
            >
              Clear
            </button>
          </div>
        </div>
      )}

      {/* Result Section */}
      {breakVm && (
        <div
          style={{
            backgroundColor: "var(--surface)",
            border: "1px solid var(--border)",
            padding: "16px",
            borderRadius: "2px",
          }}
        >
          {/* Verbatim Disclaimer */}
          {breakVm.disclaimer && (
            <div className="disclaimer-box" style={{ marginBottom: "12px" }}>
              {breakVm.disclaimer}
            </div>
          )}

          {/* Verbatim Note */}
          {breakVm.note && (
            <div
              style={{
                fontSize: "11px",
                color: "var(--muted)",
                marginBottom: "12px",
                padding: "4px 8px",
                backgroundColor: "var(--bg)",
                border: "1px solid var(--border)",
              }}
            >
              Note: {breakVm.note}
            </div>
          )}

          {/* Empty / Infinite cut message */}
          {breakVm.isEmptyCut ? (
            <div
              style={{
                padding: "12px",
                backgroundColor: "var(--bg)",
                border: "1px solid var(--border)",
                fontSize: "13px",
                color: "var(--text)",
              }}
            >
              {breakVm.emptyCutMessage}
            </div>
          ) : (
            <div>
              <div style={{ display: "flex", gap: "20px", marginBottom: "16px", flexWrap: "wrap", fontSize: "12px" }}>
                <span>
                  <strong>Finite Cut:</strong> {breakVm.finite ? "Yes" : "No"}
                </span>
                <span>
                  <strong>Cut Size:</strong> {breakVm.size}
                </span>
                <span>
                  <strong>Direct Link:</strong> {breakVm.directLink ? "Yes" : "No"}
                </span>
              </div>

              {/* Cut Persons Table */}
              <div style={{ marginBottom: "16px" }}>
                <h4 style={{ marginBottom: "6px" }}>Persons in Cut ({breakVm.cut.length})</h4>
                <table className="dense-table">
                  <thead>
                    <tr>
                      <th>Name</th>
                      <th>Person ID</th>
                      <th>Connects</th>
                      <th style={{ width: "120px" }}>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {breakVm.cut.map((person) => {
                      const details = breakVm.cutDetails?.[person.person_id];
                      const connectsPairs = details?.connects || [];
                      const hlIds = details?.highlight_ids || [person.person_id];
                      const hlParam = hlIds.length > 0 ? `&hl=${encodeURIComponent(hlIds.join(","))}` : "";
                      return (
                        <tr key={person.person_id}>
                          <td><strong>{person.name || "-"}</strong></td>
                          <td className="mono">{person.person_id}</td>
                          <td style={{ fontSize: "11px", whiteSpace: "pre-line" }}>
                            {connectsPairs.length > 0
                              ? connectsPairs.map((c) => c.pair_text).join("\n")
                              : "-"}
                          </td>
                          <td>
                            <a
                              href={`#/case/${caseId}/graph?select=${encodeURIComponent(person.person_id)}${hlParam}`}
                              className="table-link"
                              onClick={() => {
                                saveHighlightIds(hlIds);
                              }}
                            >
                              Show on Graph
                            </a>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
                <div style={{ fontSize: "11px", color: "var(--muted)", marginTop: "6px" }}>
                  Each person in the cut links the pairs shown; not every person links every member.
                </div>
              </div>

              {/* Unowned Bridging Phones */}
              {breakVm.bridgingPhones && breakVm.bridgingPhones.length > 0 && (
                <div style={{ marginBottom: "16px" }}>
                  <h4 style={{ marginBottom: "4px" }}>
                    phones with no stated owner: who holds this number?
                  </h4>
                  <ul style={{ margin: 0, paddingLeft: "16px", fontSize: "12px" }}>
                    {breakVm.bridgingPhones.map((ph, idx) => {
                      const phoneStr = typeof ph === "object" && ph !== null ? (ph.phone || ph.id || "") : String(ph);
                      const callsCount = typeof ph === "object" && ph !== null && ph.total_calls !== undefined ? ` (${ph.total_calls} calls)` : "";
                      return (
                        <li key={idx} className="mono">
                          {phoneStr}{callsCount}
                        </li>
                      );
                    })}
                  </ul>
                </div>
              )}

              {/* Show on graph button */}
              {breakVm.cut.length > 0 && (
                <div style={{ marginTop: "12px" }}>
                  {(() => {
                    const firstPerson = breakVm.cut[0];
                    const details = breakVm.cutDetails?.[firstPerson.person_id];
                    const hlIds = details?.highlight_ids || [firstPerson.person_id];
                    const hlParam = hlIds.length > 0 ? `&hl=${encodeURIComponent(hlIds.join(","))}` : "";
                    return (
                      <a
                        href={`#/case/${caseId}/graph?select=${encodeURIComponent(firstPerson.person_id)}${hlParam}`}
                        className="table-link"
                        style={{
                          display: "inline-block",
                          padding: "6px 12px",
                          backgroundColor: "var(--accent)",
                          color: "var(--surface)",
                          textDecoration: "none",
                          borderRadius: "2px",
                        }}
                        onClick={() => {
                          saveHighlightIds(hlIds);
                        }}
                      >
                        Show on graph
                      </a>
                    );
                  })()}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default Break;
