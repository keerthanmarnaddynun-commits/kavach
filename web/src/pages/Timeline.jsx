import React, { useState, useEffect } from "react";
import { request } from "../api/client.js";
import { Table } from "../components/Table.jsx";
import { computeBarLayout, formatPaise } from "./timelineHelpers.js";

export function Timeline({ caseId }) {
  const [bucket, setBucket] = useState("day");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [errorText, setErrorText] = useState(null);

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

  return (
    <TimelineView
      caseId={caseId}
      bucket={bucket}
      setBucket={setBucket}
      data={data}
      loading={loading}
      errorText={errorText}
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
}) {
  const [focusedCall, setFocusedCall] = useState(null);
  const [focusedTransfer, setFocusedTransfer] = useState(null);

  const calls = (data && data.calls) || [];
  const transfers = (data && data.transfers) || [];
  const firstSeen = (data && data.first_seen) || [];

  const callsLayout = computeBarLayout(calls, "count", 640, 160);
  const transfersLayout = computeBarLayout(transfers, "count", 640, 160);

  const firstSeenColumns = [
    {
      key: "phone",
      header: "Phone Number",
      isIdentifier: true,
      headerStyle: { width: "200px" },
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

          {/* First Seen Table */}
          <div style={{ marginTop: "8px" }}>
            <h4 style={{ marginBottom: "8px" }}>First Seen Identifiers ({firstSeen.length})</h4>
            <Table
              columns={firstSeenColumns}
              data={firstSeen}
              keyField="phone"
              initialSortKey="t"
              initialSortDir="asc"
              emptyMessage="No first seen records available."
            />
          </div>
        </div>
      )}
    </div>
  );
}

function SvgBarChart({ layout, focusedItem, onFocusItem, unit = "items" }) {
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
        return (
          <g key={idx}>
            <rect
              x={b.x}
              y={b.y}
              width={b.width}
              height={b.height}
              fill={isFocused ? "var(--accent)" : "var(--border)"}
              stroke={isFocused ? "var(--text)" : "var(--muted)"}
              strokeWidth={isFocused ? 2 : 1}
              tabIndex={0}
              role="button"
              aria-label={`${b.label}: ${b.value} ${unit}`}
              style={{ cursor: "pointer", outline: "none" }}
              onFocus={() => onFocusItem && onFocusItem(b)}
              onClick={() => onFocusItem && onFocusItem(b)}
            >
              <title>{`${b.label}: ${b.value} ${unit}`}</title>
            </rect>
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

export default Timeline;
