import React, { useState, useEffect, useMemo, useRef } from "react";
import { request } from "../api/client.js";
import { SvgBarChart } from "./Timeline.jsx";
import {
  computeBarLayout,
  formatPaise,
  getGraphNodeId,
  getCachedInsightView,
  setCachedInsightView,
  filterInsightsByView,
  alignDailyBuckets,
  getChartAnnotations,
} from "./timelineHelpers.js";

export function TimelineInsights({ caseId, initialData = null, initialTimelineData = null }) {
  const [data, setData] = useState(() => initialData || null);
  const [timelineData, setTimelineData] = useState(() => initialTimelineData || null);
  const [loading, setLoading] = useState(() => !initialData);
  const [errorText, setErrorText] = useState(null);

  const [selectedView, setSelectedView] = useState(() => getCachedInsightView(caseId));
  const [highlightedInsightId, setHighlightedInsightId] = useState(null);

  const chartsRef = useRef(null);
  const cardRefs = useRef(new Map());

  // Keep view selection in module cache
  useEffect(() => {
    if (caseId) {
      setCachedInsightView(caseId, selectedView);
    }
  }, [caseId, selectedView]);

  useEffect(() => {
    if (!caseId || initialData) return;
    setLoading(true);
    setErrorText(null);

    Promise.all([
      request(`/cases/${caseId}/timeline?bucket=day`),
      request(`/cases/${caseId}/timeline/insights`),
    ])
      .then(([tlRes, insRes]) => {
        setTimelineData(tlRes);
        setData(insRes);
      })
      .catch((err) => {
        setErrorText(err.message || "Failed to load timeline insights");
      })
      .finally(() => {
        setLoading(false);
      });
  }, [caseId]);

  const allInsights = (data && data.insights) || [];
  const visibleInsights = useMemo(
    () => filterInsightsByView(allInsights, selectedView),
    [allInsights, selectedView]
  );

  const rawCalls = (timelineData && timelineData.calls) || [];
  const rawTransfers = (timelineData && timelineData.transfers) || [];
  const { alignedCalls, alignedTransfers } = useMemo(
    () => alignDailyBuckets(rawCalls, rawTransfers),
    [rawCalls, rawTransfers]
  );

  const callsLayout = useMemo(() => computeBarLayout(alignedCalls, "count", 640, 160), [alignedCalls]);
  const transfersLayout = useMemo(
    () => computeBarLayout(alignedTransfers, "count", 640, 160),
    [alignedTransfers]
  );

  const callAnnotations = useMemo(
    () => getChartAnnotations(visibleInsights, "calls"),
    [visibleInsights]
  );
  const transferAnnotations = useMemo(
    () => getChartAnnotations(visibleInsights, "transfers"),
    [visibleInsights]
  );

  function handleSelectInsight(id) {
    setHighlightedInsightId(id);
    const cardEl = cardRefs.current.get(id);
    if (cardEl && typeof cardEl.scrollIntoView === "function") {
      cardEl.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }

  function handleCardClick(id) {
    setHighlightedInsightId(id);
    if (chartsRef.current && typeof chartsRef.current.scrollIntoView === "function") {
      chartsRef.current.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }

  const disclaimerText =
    "Decision support derived only from the uploaded records. Not findings of guilt and not proof.";

  return (
    <div>
      {/* Back to Timeline link */}
      <div className="insights-no-print" style={{ marginBottom: "12px" }}>
        <a
          href={`#/case/${caseId}/timeline`}
          className="table-link back-link"
          style={{ fontSize: "12px", display: "inline-flex", alignItems: "center", gap: "4px" }}
        >
          &larr; Back to Timeline
        </a>
      </div>

      {/* Print-only Report Header */}
      <div
        className="insights-print-only"
        style={{
          marginBottom: "16px",
          borderBottom: "1px solid var(--border)",
          paddingBottom: "10px",
        }}
      >
        <h2 style={{ margin: "0 0 6px 0" }}>Activity Timeline Insights Report</h2>
        <div
          style={{
            fontSize: "11px",
            display: "flex",
            gap: "16px",
            color: "var(--muted)",
            marginBottom: "6px",
          }}
        >
          <span>
            <strong>Case ID:</strong> {caseId}
          </span>
          <span>
            <strong>Generated:</strong>{" "}
            {data?.generated_at ? new Date(data.generated_at).toLocaleString() : new Date().toLocaleString()}
          </span>
          <span>
            <strong>Selected View:</strong> {selectedView}
          </span>
        </div>
        <p style={{ margin: 0, fontSize: "11px", fontStyle: "italic", color: "var(--muted)" }}>
          {disclaimerText}
        </p>
      </div>

      {/* Screen Header */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          marginBottom: "12px",
        }}
      >
        <div>
          <h3 style={{ margin: "0 0 4px 0" }}>Activity Timeline Insights</h3>
          <p style={{ margin: 0, fontSize: "12px", color: "var(--muted)" }}>{disclaimerText}</p>
        </div>

        {/* Download PDF button */}
        <button
          type="button"
          className="insights-no-print"
          onClick={() => window.print()}
          style={{ fontSize: "11px", padding: "4px 10px" }}
        >
          Download PDF
        </button>
      </div>

      {/* View Switch */}
      <div
        className="insights-no-print"
        style={{ display: "flex", alignItems: "center", gap: "6px", marginBottom: "16px" }}
        role="tablist"
        aria-label="Filter insights chart view"
      >
        <span style={{ fontSize: "11px", color: "var(--muted)", marginRight: "4px" }}>View:</span>
        <button
          type="button"
          role="tab"
          aria-selected={selectedView === "Both"}
          className={selectedView === "Both" ? "primary" : ""}
          onClick={() => setSelectedView("Both")}
          style={{ fontSize: "11px", padding: "4px 10px" }}
        >
          Both
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={selectedView === "Calls only"}
          className={selectedView === "Calls only" ? "primary" : ""}
          onClick={() => setSelectedView("Calls only")}
          style={{ fontSize: "11px", padding: "4px 10px" }}
        >
          Calls only
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={selectedView === "Transfers only"}
          className={selectedView === "Transfers only" ? "primary" : ""}
          onClick={() => setSelectedView("Transfers only")}
          style={{ fontSize: "11px", padding: "4px 10px" }}
        >
          Transfers only
        </button>
      </div>

      {errorText && (
        <div className="error-text" style={{ marginBottom: "12px" }}>
          {errorText}
        </div>
      )}

      {loading && <div>Loading insights...</div>}

      {!loading && (
        <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
          {/* Daily Charts */}
          <div ref={chartsRef} style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
            {/* Calls Chart */}
            {(selectedView === "Both" || selectedView === "Calls only") && (
              <div
                style={{
                  backgroundColor: "var(--surface)",
                  border: "1px solid var(--border)",
                  padding: "14px",
                  borderRadius: "2px",
                }}
              >
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    marginBottom: "8px",
                  }}
                >
                  <strong>Calls Volume (Daily)</strong>
                  <span style={{ fontSize: "11px", color: "var(--muted)" }}>
                    {callAnnotations.length} insight{callAnnotations.length === 1 ? "" : "s"} marked
                  </span>
                </div>
                <SvgBarChart
                  layout={callsLayout}
                  unit="calls"
                  annotations={callAnnotations}
                  selectedAnnotationId={highlightedInsightId}
                  onSelectAnnotation={handleSelectInsight}
                />
              </div>
            )}

            {/* Transfers Chart */}
            {(selectedView === "Both" || selectedView === "Transfers only") && (
              <div
                style={{
                  backgroundColor: "var(--surface)",
                  border: "1px solid var(--border)",
                  padding: "14px",
                  borderRadius: "2px",
                }}
              >
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    marginBottom: "8px",
                  }}
                >
                  <strong>Transfers Volume (Daily)</strong>
                  <span style={{ fontSize: "11px", color: "var(--muted)" }}>
                    {transferAnnotations.length} insight{transferAnnotations.length === 1 ? "" : "s"} marked
                  </span>
                </div>
                <SvgBarChart
                  layout={transfersLayout}
                  unit="transfers"
                  annotations={transferAnnotations}
                  selectedAnnotationId={highlightedInsightId}
                  onSelectAnnotation={handleSelectInsight}
                />
              </div>
            )}
          </div>

          {/* Insight Cards */}
          <div>
            <h4 style={{ margin: "0 0 10px 0" }}>Patterns Worth a Look ({visibleInsights.length})</h4>

            {data?.reason ? (
              <div
                style={{
                  padding: "14px",
                  backgroundColor: "var(--surface)",
                  border: "1px solid var(--border)",
                  borderRadius: "2px",
                  fontSize: "12px",
                  color: "var(--muted)",
                }}
              >
                {data.reason === "not enough days to judge"
                  ? "not enough days to judge"
                  : data.reason}
              </div>
            ) : allInsights.length === 0 ? (
              <div
                style={{
                  padding: "14px",
                  backgroundColor: "var(--surface)",
                  border: "1px solid var(--border)",
                  borderRadius: "2px",
                  fontSize: "12px",
                  color: "var(--muted)",
                }}
              >
                <div style={{ marginBottom: data?.summary ? "8px" : "0" }}>
                  No unusual patterns found in the uploaded records.
                </div>
                {data?.summary && (
                  <div style={{ fontSize: "11px", color: "var(--muted)", display: "flex", flexDirection: "column", gap: "2px" }}>
                    {data.summary.busiest_call_day && (
                      <div>
                        {`Busiest call day: ${data.summary.busiest_call_day.date}, ${data.summary.busiest_call_day.count} calls (${data.summary.busiest_call_day.ratio}x a typical day).`}
                      </div>
                    )}
                    {data.summary.busiest_transfer_day && (
                      <div>
                        {`Busiest transfer day: ${data.summary.busiest_transfer_day.date}, ${data.summary.busiest_transfer_day.count} transfers (${data.summary.busiest_transfer_day.ratio}x a typical day).`}
                      </div>
                    )}
                  </div>
                )}
              </div>
            ) : visibleInsights.length === 0 ? (
              <div
                style={{
                  padding: "14px",
                  backgroundColor: "var(--surface)",
                  border: "1px solid var(--border)",
                  borderRadius: "2px",
                  fontSize: "12px",
                  color: "var(--muted)",
                }}
              >
                No unusual patterns found for {selectedView.toLowerCase()}.
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
                {visibleInsights.map((ins) => {
                  const isHighlighted = highlightedInsightId === ins.id;
                  return (
                    <div
                      key={ins.id}
                      ref={(el) => {
                        if (el) cardRefs.current.set(ins.id, el);
                        else cardRefs.current.delete(ins.id);
                      }}
                      tabIndex={0}
                      role="button"
                      aria-label={`Insight card ${ins.number}: ${ins.headline}`}
                      onClick={() => handleCardClick(ins.id)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          handleCardClick(ins.id);
                        }
                      }}
                      style={{
                        padding: "12px 14px",
                        backgroundColor: isHighlighted ? "var(--highlight)" : "var(--surface)",
                        border: isHighlighted
                          ? "1px solid var(--highlight-border)"
                          : "1px solid var(--border)",
                        borderRadius: "2px",
                        cursor: "pointer",
                        display: "flex",
                        gap: "12px",
                        alignItems: "flex-start",
                      }}
                    >
                      <div
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          justifyContent: "center",
                          width: "22px",
                          height: "22px",
                          borderRadius: "9999px",
                          backgroundColor: "var(--surface)",
                          border: "1.5px solid var(--text)",
                          fontWeight: "bold",
                          fontSize: "11px",
                          flexShrink: 0,
                        }}
                      >
                        {ins.number}
                      </div>
                      <div style={{ flex: 1 }}>
                        <div style={{ fontWeight: 600, fontSize: "13px", marginBottom: "4px" }}>
                          {ins.headline}
                        </div>
                        <div
                          style={{
                            fontSize: "12px",
                            color: "var(--muted)",
                            marginBottom: "6px",
                          }}
                        >
                          {ins.why}
                        </div>
                        {ins.identifiers && ins.identifiers.length > 0 && (
                          <div style={{ display: "flex", flexWrap: "wrap", gap: "8px" }}>
                            {ins.identifiers.map((ident, iIdx) => {
                              const rawId = ident.id;
                              const selectId =
                                getGraphNodeId(ident.type.toUpperCase(), rawId) || rawId;
                              return (
                                <a
                                  key={iIdx}
                                  href={`#/case/${caseId}/graph?select=${encodeURIComponent(selectId)}&firstfir=1`}
                                  className="table-link"
                                  style={{ fontSize: "11px" }}
                                  onClick={(e) => e.stopPropagation()}
                                >
                                  {ident.type.toUpperCase()}: {rawId}
                                </a>
                              );
                            })}
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Collapsed Rules Used Section */}
          <details
            className="rules-details"
            style={{
              border: "1px solid var(--border)",
              padding: "10px 14px",
              borderRadius: "2px",
              backgroundColor: "var(--surface)",
            }}
          >
            <summary style={{ cursor: "pointer", fontWeight: 600, fontSize: "12px" }}>
              Rules used
            </summary>
            <div style={{ marginTop: "10px", fontSize: "11px", color: "var(--muted)" }}>
              <ul style={{ margin: "0", paddingLeft: "20px", display: "flex", flexDirection: "column", gap: "6px" }}>
                <li>
                  <strong>Minimum active days:</strong>{" "}
                  {data?.rules?.min_active_days ?? 7} active days required; fewer active days returns &quot;not enough days to judge&quot;.
                </li>
                <li>
                  <strong>Call spike:</strong> Daily call count &ge; max(
                  {(data?.rules?.call_spike_multiplier ?? 3.0).toFixed(0)}&times; median daily calls, median +{" "}
                  {(data?.rules?.call_spike_mad_multiplier ?? 3.0).toFixed(0)}&times; MAD) and &ge;{" "}
                  {data?.rules?.min_call_events ?? 10} calls.
                </li>
                <li>
                  <strong>Transfer spike:</strong> Daily transfer count &ge; max(
                  {(data?.rules?.transfer_spike_multiplier ?? 3.0).toFixed(0)}&times; median, median +{" "}
                  {(data?.rules?.transfer_spike_mad_multiplier ?? 3.0).toFixed(0)}&times; MAD) and &ge;{" "}
                  {data?.rules?.min_transfer_events ?? 10} transfers, OR daily transfer amount &ge;{" "}
                  {(data?.rules?.transfer_amount_multiplier ?? 3.0).toFixed(0)}&times; median daily amount and &ge; Rs.{" "}
                  {((data?.rules?.min_transfer_amount_paise ?? 5000000) / 100).toLocaleString()}.
                </li>
                <li>
                  <strong>Call-then-transfer correlation:</strong> Call spike on day D followed by transfer spike on days D to D+
                  {data?.rules?.call_then_transfer_window_days ?? 2}.
                </li>
                <li>
                  <strong>New and busy identifier:</strong> Identifier first seen within{" "}
                  {data?.rules?.new_busy_day_window ?? 3} days before or on a spike day, accounting for &ge;{" "}
                  {((data?.rules?.new_busy_volume_share ?? 0.2) * 100).toFixed(0)}% and &ge;{" "}
                  {data?.rules?.new_busy_min_events ?? 5} events of that spike day&apos;s volume.
                </li>
              </ul>
            </div>
          </details>
        </div>
      )}
    </div>
  );
}

export default TimelineInsights;
