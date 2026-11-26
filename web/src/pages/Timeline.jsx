import React, { useState, useEffect, useMemo } from "react";
import { request } from "../api/client.js";
import { Table } from "../components/Table.jsx";
import { computeBarLayout, formatPaise, getGraphNodeId, selectExampleRows } from "./timelineHelpers.js";

export function Timeline({ caseId }) {
  const [bucket, setBucket] = useState("day");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [errorText, setErrorText] = useState(null);
  const [activeTab, setActiveTab] = useState("phones");
  const [insightsCount, setInsightsCount] = useState(0);

  useEffect(() => {
    if (!caseId) return;
    setLoading(true);
    setErrorText(null);

    request(`/cases/${caseId}/timeline?bucket=${bucket}`)
      .then((res) => {
        setData(res);
      })
      .catch((err) => {
        setErrorText(err.message || "Failed to load timeline");
      })
      .finally(() => {
        setLoading(false);
      });
  }, [caseId, bucket]);

  useEffect(() => {
    if (!caseId) return;
    request(`/cases/${caseId}/timeline/insights`)
      .then((res) => {
        if (res && typeof res.count === "number") {
          setInsightsCount(res.count);
        }
      })
      .catch(() => {
        setInsightsCount(0);
      });
  }, [caseId]);

  return (
    <TimelineView
      caseId={caseId}
      bucket={bucket}
      setBucket={setBucket}
      data={data}
      loading={loading}
      errorText={errorText}
      activeTab={activeTab}
      setActiveTab={setActiveTab}
      insightsCount={insightsCount}
    />
  );
}

export function TimelineView({
  caseId,
  bucket = "day",
  setBucket,
  data = null,
  loading = false,
  errorText = null,
  activeTab,
  setActiveTab,
  insightsCount = 0,
}) {
  const [localTab, setLocalTab] = useState(activeTab || "phones");
  const currentTab = activeTab || localTab;
  const handleTabChange = (tab) => {
    setLocalTab(tab);
    if (setActiveTab) setActiveTab(tab);
  };

  const [focusedCall, setFocusedCall] = useState(null);
  const [focusedTransfer, setFocusedTransfer] = useState(null);

  const calls = (data && data.calls) || [];
  const transfers = (data && data.transfers) || [];
  const firstSeenPhones = (data && data.first_seen) || [];
  const firstSeenAccounts = (data && data.first_seen_accounts) || [];
  const firstSeenImeis = (data && data.first_seen_imeis) || [];

  const callsLayout = computeBarLayout(calls, "count", 640, 160);
  const transfersLayout = computeBarLayout(transfers, "count", 640, 160);

  const phoneMarkers = useMemo(() => selectExampleRows(firstSeenPhones), [firstSeenPhones]);
  const accountMarkers = useMemo(() => selectExampleRows(firstSeenAccounts), [firstSeenAccounts]);
  const imeiMarkers = useMemo(() => selectExampleRows(firstSeenImeis), [firstSeenImeis]);

  const currentMarkers =
    currentTab === "phones" ? phoneMarkers : currentTab === "accounts" ? accountMarkers : imeiMarkers;
  const hasAnyMarker = Object.keys(currentMarkers).length > 0;

  const firstSeenPhoneColumns = [
    {
      key: "phone",
      header: "Phone Number",
      isIdentifier: true,
      headerStyle: { width: "200px" },
      render: (val) => {
        if (!val) return "-";
        const nodeId = getGraphNodeId("PHONE", val);
        const marker = phoneMarkers[val];
        return (
          <span style={{ display: "inline-flex", alignItems: "center" }}>
            {caseId && nodeId ? (
              <a href={`#/case/${caseId}/graph?select=${encodeURIComponent(nodeId)}&firstfir=1`}>
                {val}
              </a>
            ) : (
              val
            )}
            {marker && <ExampleTag category={marker} />}
          </span>
        );
      },
    },
    {
      key: "t",
      header: "First Seen Timestamp",
      headerStyle: { width: "240px" },
      render: (t) => <span className="mono">{t}</span>,
    },
  ];

  const firstSeenAccountColumns = [
    {
      key: "account",
      header: "Account Number",
      isIdentifier: true,
      headerStyle: { width: "200px" },
      render: (val) => {
        if (!val) return "-";
        const nodeId = getGraphNodeId("ACCOUNT", val);
        const marker = accountMarkers[val];
        return (
          <span style={{ display: "inline-flex", alignItems: "center" }}>
            {caseId && nodeId ? (
              <a href={`#/case/${caseId}/graph?select=${encodeURIComponent(nodeId)}&firstfir=1`}>
                {val}
              </a>
            ) : (
              val
            )}
            {marker && <ExampleTag category={marker} />}
          </span>
        );
      },
    },
    {
      key: "t",
      header: "First Seen Timestamp",
      headerStyle: { width: "240px" },
      render: (t) => <span className="mono">{t}</span>,
    },
  ];

  const firstSeenImeiColumns = [
    {
      key: "imei",
      header: "IMEI",
      isIdentifier: true,
      headerStyle: { width: "200px" },
      render: (val) => {
        if (!val) return "-";
        const nodeId = getGraphNodeId("IMEI", val);
        const marker = imeiMarkers[val];
        return (
          <span style={{ display: "inline-flex", alignItems: "center" }}>
            {caseId && nodeId ? (
              <a href={`#/case/${caseId}/graph?select=${encodeURIComponent(nodeId)}&firstfir=1`}>
                {val}
              </a>
            ) : (
              val
            )}
            {marker && <ExampleTag category={marker} />}
          </span>
        );
      },
    },
    {
      key: "t",
      header: "First Seen Timestamp",
      headerStyle: { width: "240px" },
      render: (t) => <span className="mono">{t}</span>,
    },
  ];

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
        <div>
          <h3 style={{ margin: "0 0 4px 0" }}>Activity Timeline</h3>
          <p style={{ margin: 0, fontSize: "12px", color: "var(--muted)" }}>
            Observed call and financial transaction volume over time.
          </p>
        </div>

        {/* Header Controls: Insights and Aggregation */}
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          {/* Insights Button */}
          <a
            href={`#/case/${caseId}/timeline/insights`}
            className="insights-link-btn"
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "6px",
              fontSize: "11px",
              padding: "4px 8px",
              textDecoration: "none",
              border: "1px solid var(--border)",
              borderRadius: "2px",
              backgroundColor: "var(--surface)",
              color: "var(--text)",
            }}
          >
            <span>Insights</span>
            {insightsCount > 0 && (
              <span
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  justifyContent: "center",
                  minWidth: "16px",
                  height: "16px",
                  padding: "0 4px",
                  borderRadius: "9999px",
                  backgroundColor: "var(--badge-danger-bg)",
                  color: "var(--badge-danger-text)",
                  fontSize: "10px",
                  fontWeight: "bold",
                  lineHeight: 1,
                }}
              >
                {insightsCount}
              </span>
            )}
          </a>

          {/* Day / Hour Toggle */}
          <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
            <span style={{ fontSize: "11px", color: "var(--muted)" }}>Aggregation:</span>
            <button
              type="button"
              className={bucket === "day" ? "primary" : ""}
              onClick={() => setBucket && setBucket("day")}
              style={{ fontSize: "11px", padding: "4px 8px" }}
            >
              Day
            </button>
            <button
              type="button"
              className={bucket === "hour" ? "primary" : ""}
              onClick={() => setBucket && setBucket("hour")}
              style={{ fontSize: "11px", padding: "4px 8px" }}
            >
              Hour
            </button>
          </div>
        </div>
      </div>

      {errorText && (
        <div className="error-text" style={{ marginBottom: "12px" }}>
          {errorText}
        </div>
      )}

      {loading && <div>Loading timeline records...</div>}

      {!loading && (
        <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
          {/* Calls Bar Chart */}
          <div
            style={{
              backgroundColor: "var(--surface)",
              border: "1px solid var(--border)",
              padding: "14px",
              borderRadius: "2px",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
              <strong>Calls Volume ({calls.length} {bucket}s)</strong>
              <div style={{ fontSize: "11px", color: "var(--muted)" }}>
                {focusedCall ? (
                  <span>
                    <strong>{focusedCall.label}:</strong> {focusedCall.value} calls
                    {focusedCall.raw?.voice !== undefined && ` (${focusedCall.raw.voice} voice, ${focusedCall.raw.sms} SMS)`}
                  </span>
                ) : (
                  <span>Focus or click on a bar to view exact counts</span>
                )}
              </div>
            </div>

            <SvgBarChart
              layout={callsLayout}
              focusedItem={focusedCall}
              onFocusItem={setFocusedCall}
              unit="calls"
            />
          </div>

          {/* Transfers Bar Chart */}
          <div
            style={{
              backgroundColor: "var(--surface)",
              border: "1px solid var(--border)",
              padding: "14px",
              borderRadius: "2px",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
              <strong>Transfers Volume ({transfers.length} {bucket}s)</strong>
              <div style={{ fontSize: "11px", color: "var(--muted)" }}>
                {focusedTransfer ? (
                  <span>
                    <strong>{focusedTransfer.label}:</strong> {focusedTransfer.value} transfers
                    {focusedTransfer.raw?.paise !== undefined && ` (Rs. ${formatPaise(focusedTransfer.raw.paise)})`}
                  </span>
                ) : (
                  <span>Focus or click on a bar to view exact counts</span>
                )}
              </div>
            </div>

            <SvgBarChart
              layout={transfersLayout}
              focusedItem={focusedTransfer}
              onFocusItem={setFocusedTransfer}
              unit="transfers"
            />
          </div>

          {/* First Seen Identifiers */}
          <div style={{ marginTop: "8px" }}>
            <h4 style={{ marginBottom: "8px" }}>First Seen Identifiers</h4>

            {/* Tab switch */}
            <div style={{ display: "flex", gap: "8px", marginBottom: "6px" }} role="tablist" aria-label="First seen identifier type">
              <button
                type="button"
                role="tab"
                aria-selected={currentTab === "phones"}
                className={currentTab === "phones" ? "primary" : ""}
                onClick={() => handleTabChange("phones")}
                style={{ fontSize: "11px", padding: "4px 8px" }}
              >
                {`Phones (${firstSeenPhones.length})`}
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={currentTab === "accounts"}
                className={currentTab === "accounts" ? "primary" : ""}
                onClick={() => handleTabChange("accounts")}
                style={{ fontSize: "11px", padding: "4px 8px" }}
              >
                {`Accounts (${firstSeenAccounts.length})`}
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={currentTab === "imeis"}
                className={currentTab === "imeis" ? "primary" : ""}
                onClick={() => handleTabChange("imeis")}
                style={{ fontSize: "11px", padding: "4px 8px" }}
              >
                {`IMEIs (${firstSeenImeis.length})`}
              </button>
            </div>

            <p style={{ margin: "0 0 10px 0", fontSize: "11px", color: "var(--muted)" }}>
              First seen means the first time it appears in the uploaded records, not when it first existed.
            </p>

            {/* One-line key explaining tags: shown only when at least one marker is present */}
            {hasAnyMarker && (
              <div
                style={{
                  display: "flex",
                  flexWrap: "wrap",
                  gap: "12px",
                  alignItems: "center",
                  fontSize: "11px",
                  color: "var(--muted)",
                  marginBottom: "10px",
                  padding: "4px 8px",
                  backgroundColor: "var(--bg)",
                  border: "1px solid var(--border)",
                }}
              >
                <span style={{ fontWeight: "600" }}>Example tags:</span>
                <span style={{ display: "inline-flex", alignItems: "center", gap: "6px" }}>
                  <ExampleTag category="category1" style={{ marginLeft: 0 }} />
                  <span>FIR mention and records (shows FIR + record groups in graph)</span>
                </span>
                <span style={{ display: "inline-flex", alignItems: "center", gap: "6px" }}>
                  <ExampleTag category="category2" style={{ marginLeft: 0 }} />
                  <span>No FIR mention with record activity (record group only)</span>
                </span>
              </div>
            )}

            {currentTab === "phones" && (
              <Table
                columns={firstSeenPhoneColumns}
                data={firstSeenPhones}
                keyField="phone"
                initialSortKey="t"
                initialSortDir="asc"
                emptyMessage="No first seen records available."
              />
            )}
            {currentTab === "accounts" && (
              <Table
                columns={firstSeenAccountColumns}
                data={firstSeenAccounts}
                keyField="account"
                initialSortKey="t"
                initialSortDir="asc"
                emptyMessage="No first seen records available."
              />
            )}
            {currentTab === "imeis" && (
              <Table
                columns={firstSeenImeiColumns}
                data={firstSeenImeis}
                keyField="imei"
                initialSortKey="t"
                initialSortDir="asc"
                emptyMessage="No first seen records available."
              />
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export function SvgBarChart({
  layout,
  focusedItem,
  onFocusItem,
  unit = "items",
  annotations = [],
  onSelectAnnotation,
  selectedAnnotationId,
}) {
  const { bars, maxVal, plotWidth, plotHeight, margin } = layout;
  const svgWidth = 640;
  const svgHeight = 160;

  if (bars.length === 0) {
    return (
      <div style={{ padding: "20px", textAlign: "center", color: "var(--muted)", fontSize: "11px" }}>
        No {unit} data available for the selected period.
      </div>
    );
  }

  const yZero = margin.top + plotHeight;

  // Group annotations by day/label
  const annByDay = new Map();
  for (const ann of annotations || []) {
    if (!ann || !ann.day) continue;
    if (!annByDay.has(ann.day)) annByDay.set(ann.day, []);
    annByDay.get(ann.day).push(ann);
  }

  return (
    <svg
      viewBox={`0 0 ${svgWidth} ${svgHeight}`}
      style={{
        width: "100%",
        height: "160px",
        overflow: "visible",
        display: "block",
      }}
      role="img"
      aria-label={`${unit} bar chart`}
    >
      {/* Background Grid Lines */}
      <line
        x1={margin.left}
        y1={margin.top}
        x2={margin.left + plotWidth}
        y2={margin.top}
        stroke="var(--border)"
        strokeDasharray="2,2"
      />
      <line
        x1={margin.left}
        y1={yZero}
        x2={margin.left + plotWidth}
        y2={yZero}
        stroke="var(--border)"
      />

      {/* Y Axis Labels */}
      <text
        x={margin.left - 6}
        y={margin.top + 4}
        textAnchor="end"
        fill="var(--muted)"
        fontSize="10"
        fontFamily="ui-monospace, monospace"
      >
        {maxVal}
      </text>
      <text
        x={margin.left - 6}
        y={yZero}
        textAnchor="end"
        fill="var(--muted)"
        fontSize="10"
        fontFamily="ui-monospace, monospace"
      >
        0
      </text>

      {/* Bars */}
      {bars.map((b, idx) => {
        const isFocused = focusedItem && focusedItem.label === b.label;
        const dayAnns = annByDay.get(b.label) || [];
        const hasSelectedAnn = dayAnns.some((a) => a.insightId === selectedAnnotationId);

        return (
          <g key={idx}>
            <rect
              x={b.x}
              y={b.y}
              width={b.width}
              height={b.height}
              fill={hasSelectedAnn || isFocused ? "var(--accent)" : "var(--border)"}
              stroke={hasSelectedAnn || isFocused ? "var(--text)" : "var(--muted)"}
              strokeWidth={hasSelectedAnn || isFocused ? 2 : 1}
              tabIndex={0}
              role="button"
              aria-label={`${b.label}: ${b.value} ${unit}`}
              style={{ cursor: "pointer", outline: "none" }}
              onFocus={() => onFocusItem && onFocusItem(b)}
              onClick={() => onFocusItem && onFocusItem(b)}
            >
              <title>{`${b.label}: ${b.value} ${unit}`}</title>
            </rect>

            {/* Circle annotations on bars */}
            {dayAnns.map((ann, aIdx) => {
              const k = dayAnns.length;
              const offset = (aIdx - (k - 1) / 2) * 18;
              const cx = b.x + b.width / 2 + offset;
              const cyPos = Math.max(margin.top + 9, b.y - 12);
              const isSelected = selectedAnnotationId === ann.insightId;

              return (
                <g
                  key={aIdx}
                  role="button"
                  tabIndex={0}
                  aria-label={`Insight ${ann.number}`}
                  style={{ cursor: "pointer" }}
                  onClick={(e) => {
                    e.stopPropagation();
                    if (onSelectAnnotation) onSelectAnnotation(ann.insightId);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.stopPropagation();
                      if (onSelectAnnotation) onSelectAnnotation(ann.insightId);
                    }
                  }}
                >
                  <circle
                    cx={cx}
                    cy={cyPos}
                    r={isSelected ? 9 : 8}
                    fill={isSelected ? "var(--highlight)" : "var(--surface)"}
                    stroke="var(--text)"
                    strokeWidth={isSelected ? 2.5 : 1.5}
                  />
                  <text
                    x={cx}
                    y={cyPos + 3}
                    textAnchor="middle"
                    fontSize="9"
                    fontWeight="bold"
                    fill="var(--text)"
                    fontFamily="ui-monospace, monospace"
                  >
                    {ann.number}
                  </text>
                </g>
              );
            })}
          </g>
        );
      })}

      {/* X Axis Edge Labels */}
      {bars.length > 0 && (
        <>
          <text
            x={bars[0].x}
            y={yZero + 14}
            textAnchor="start"
            fill="var(--muted)"
            fontSize="9"
            fontFamily="ui-monospace, monospace"
          >
            {bars[0].label}
          </text>
          <text
            x={bars[bars.length - 1].x + bars[bars.length - 1].width}
            y={yZero + 14}
            textAnchor="end"
            fill="var(--muted)"
            fontSize="9"
            fontFamily="ui-monospace, monospace"
          >
            {bars[bars.length - 1].label}
          </text>
        </>
      )}
    </svg>
  );
}

export function ExampleTag({ category, style = {} }) {
  if (category === "category1") {
    return (
      <span
        style={{
          display: "inline-block",
          fontSize: "10px",
          fontWeight: "600",
          padding: "1px 5px",
          borderRadius: "3px",
          marginLeft: "6px",
          color: "var(--tag-fir-text)",
          backgroundColor: "var(--tag-fir-bg)",
          border: "1px solid var(--tag-fir-border)",
          whiteSpace: "nowrap",
          ...style,
        }}
        title="Category 1: Mentions in FIR and records"
      >
        FIR + records
      </span>
    );
  }
  if (category === "category2") {
    return (
      <span
        style={{
          display: "inline-block",
          fontSize: "10px",
          fontWeight: "600",
          padding: "1px 5px",
          borderRadius: "3px",
          marginLeft: "6px",
          color: "var(--tag-records-text)",
          backgroundColor: "var(--tag-records-bg)",
          border: "1px solid var(--tag-records-border)",
          whiteSpace: "nowrap",
          ...style,
        }}
        title="Category 2: No FIR mention with record activity"
      >
        Records only
      </span>
    );
  }
  return null;
}

export default Timeline;
