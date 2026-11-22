import React, { useState, useEffect, useRef, useMemo } from "react";
import { request } from "../api/client.js";
import { shortenHash, copyToClipboard } from "../lib/format.js";
import { segmentTextWithSpans, parseSpanQuery } from "./evidenceHelpers.js";

export function EvidenceDoc({ caseId, docId, route }) {
  const [docList, setDocList] = useState([]);
  const [docData, setDocData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [errorText, setErrorText] = useState(null);
  const [selectedSpan, setSelectedSpan] = useState(null);
  const [copyStatus, setCopyStatus] = useState({});

  const targetSpanRef = useRef(null);

  // Parse active span from query ?span=start-end
  const targetSpan = useMemo(() => {
    return parseSpanQuery(route || (typeof window !== "undefined" ? window.location.hash : ""));
  }, [route]);

  // Load documents list for the case
  useEffect(() => {
    if (!caseId) return;
    request(`/cases/${caseId}`)
      .then((data) => {
        setDocList(data.documents || []);
      })
      .catch(() => {});
  }, [caseId]);

  // Load document content
  useEffect(() => {
    if (!caseId || !docId) return;
    setLoading(true);
    setErrorText(null);
    setSelectedSpan(null);

    request(`/cases/${caseId}/documents/${docId}`)
      .then((data) => {
        setDocData(data);
      })
      .catch((err) => {
        setErrorText(err.message || "Failed to load document");
      })
      .finally(() => {
        setLoading(false);
      });
  }, [caseId, docId]);

  // Segment text with spans
  const { segments, outOfRangeCount } = useMemo(() => {
    if (!docData || !docData.text) {
      return { segments: [], outOfRangeCount: 0 };
    }
    return segmentTextWithSpans(docData.text, docData.spans || []);
  }, [docData]);

  // Auto-scroll to target span if present
  useEffect(() => {
    if (targetSpan && targetSpanRef.current) {
      targetSpanRef.current.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [targetSpan, segments]);

  async function handleCopy(key, text) {
    const ok = await copyToClipboard(text);
    if (ok) {
      setCopyStatus((prev) => ({ ...prev, [key]: true }));
      setTimeout(() => {
        setCopyStatus((prev) => ({ ...prev, [key]: false }));
      }, 2000);
    }
  }

  return (
    <EvidenceDocView
      caseId={caseId}
      docId={docId}
      docList={docList}
      docData={docData}
      loading={loading}
      errorText={errorText}
      selectedSpan={selectedSpan}
      setSelectedSpan={setSelectedSpan}
      targetSpan={targetSpan}
      segments={segments}
      outOfRangeCount={outOfRangeCount}
      targetSpanRef={targetSpanRef}
      copyStatus={copyStatus}
      handleCopy={handleCopy}
      onSelectDoc={(id) => {
        if (typeof window !== "undefined") {
          window.location.hash = `#/case/${caseId}/evidence/doc/${id}`;
        }
      }}
    />
  );
}

export function EvidenceDocView({
  caseId,
  docId,
  docList = [],
  docData,
  loading = false,
  errorText = null,
  selectedSpan = null,
  setSelectedSpan,
  targetSpan = null,
  segments = [],
  outOfRangeCount = 0,
  targetSpanRef,
  copyStatus = {},
  handleCopy,
  onSelectDoc,
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", height: "calc(100vh - 80px)", overflow: "hidden" }}>
      {/* Top Document Header */}
      <div
        style={{
          padding: "10px 14px",
          backgroundColor: "var(--surface)",
          borderBottom: "1px solid var(--border)",
          fontSize: "12px",
          display: "flex",
          flexWrap: "wrap",
          justifyContent: "space-between",
          alignItems: "center",
          gap: "12px",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          {/* Document Switcher */}
          <label htmlFor="doc-select" style={{ fontWeight: "600" }}>Document:</label>
          <select
            id="doc-select"
            value={docId}
            onChange={(e) => onSelectDoc && onSelectDoc(e.target.value)}
            style={{ fontSize: "12px" }}
          >
            {docList.map((d) => (
              <option key={d.doc_id} value={d.doc_id}>
                {d.doc_id} ({d.filename || d.name || "-"})
              </option>
            ))}
          </select>

          {docData && (
            <span style={{ color: "var(--muted)" }}>
              Filename: <strong>{docData.filename || "-"}</strong>
            </span>
          )}
        </div>

        {docData && (
          <div style={{ display: "flex", gap: "16px", alignItems: "center" }}>
            <span>
              Characters: <span className="mono">{docData.text ? docData.text.length : 0}</span>
            </span>

            <span>
              SHA-256 Raw:{" "}
              <span className="mono" title={docData.sha256_raw}>
                {shortenHash(docData.sha256_raw, 12)}
              </span>
              {handleCopy && (
                <button
                  type="button"
                  className="copy-btn"
                  onClick={() => handleCopy("raw", docData.sha256_raw)}
                  style={{ marginLeft: "4px" }}
                >
                  {copyStatus["raw"] ? "Copied" : "Copy"}
                </button>
              )}
            </span>

            <span>
              SHA-256 Text:{" "}
              <span className="mono" title={docData.sha256_text}>
                {shortenHash(docData.sha256_text, 12)}
              </span>
              {handleCopy && (
                <button
                  type="button"
                  className="copy-btn"
                  onClick={() => handleCopy("text", docData.sha256_text)}
                  style={{ marginLeft: "4px" }}
                >
                  {copyStatus["text"] ? "Copied" : "Copy"}
                </button>
              )}
            </span>
          </div>
        )}
      </div>

      {/* Main Content Area */}
      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
        {/* Text Pane */}
        <div
          style={{
            flex: 1,
            padding: "16px",
            overflowY: "auto",
            backgroundColor: "var(--surface)",
            borderRight: "1px solid var(--border)",
          }}
        >
          {errorText && <div className="error-text" style={{ marginBottom: "12px" }}>{errorText}</div>}
          {loading && <div>Loading document...</div>}

          {outOfRangeCount > 0 && (
            <div
              style={{
                padding: "6px 10px",
                backgroundColor: "var(--bg)",
                border: "1px solid var(--border)",
                fontSize: "11px",
                color: "var(--muted)",
                marginBottom: "12px",
              }}
            >
              Notice: {outOfRangeCount} out-of-range span(s) recorded in extraction annotations.
            </div>
          )}

          {!loading && docData && (
            <div
              style={{
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
                fontFamily: 'ui-monospace, "Cascadia Mono", Consolas, monospace',
                fontSize: "13px",
                lineHeight: "1.7",
              }}
            >
              {segments.map((seg, idx) => {
                if (!seg.isHighlighted) {
                  return <span key={idx}>{seg.text}</span>;
                }

                const isTarget = targetSpan && seg.start >= targetSpan.start && seg.end <= targetSpan.end;
                const isSelected = selectedSpan && seg.spans.some((s) => s === selectedSpan);

                let bg = "var(--accent-weak)";
                let color = "var(--text)";
                let border = "1px solid var(--accent)";

                if (seg.isOverlap) {
                  bg = "var(--bg)";
                  border = "1px dashed var(--muted)";
                }
                if (isTarget) {
                  border = "2px solid var(--accent)";
                  bg = "var(--accent-weak)";
                }
                if (isSelected) {
                  border = "2px solid var(--text)";
                }

                return (
                  <mark
                    key={idx}
                    ref={isTarget ? targetSpanRef : null}
                    style={{
                      backgroundColor: bg,
                      color,
                      border,
                      borderRadius: "2px",
                      padding: "1px 2px",
                      cursor: "pointer",
                      fontWeight: isTarget || isSelected ? "600" : "normal",
                    }}
                    onClick={() => {
                      if (setSelectedSpan && seg.spans) {
                        setSelectedSpan(seg.spans[0]);
                      }
                    }}
                    title={`Span [${seg.start}, ${seg.end}] - ${(seg.spans || []).map((s) => s.surface || s.node_id).join(", ")}`}
                  >
                    {seg.text}
                    {seg.isOverlap && (
                      <span
                        style={{
                          fontSize: "9px",
                          verticalAlign: "super",
                          marginLeft: "2px",
                          color: "var(--muted)",
                          fontWeight: "bold",
                        }}
                      >
                        [{(seg.spans || []).length}]
                      </span>
                    )}
                  </mark>
                );
              })}
            </div>
          )}
        </div>

        {/* Span Detail Inspector Pane (320px) */}
        <aside
          style={{
            width: "320px",
            padding: "16px",
            backgroundColor: "var(--bg)",
            overflowY: "auto",
            fontSize: "12px",
          }}
        >
          <h4 style={{ marginBottom: "12px" }}>Annotation Inspector</h4>
          {selectedSpan ? (
            <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
              <div>
                <div style={{ color: "var(--muted)", fontSize: "11px" }}>Surface Text</div>
                <div style={{ fontWeight: "600", fontSize: "13px" }}>{selectedSpan.surface || "-"}</div>
              </div>

              <div>
                <div style={{ color: "var(--muted)", fontSize: "11px" }}>Character Span</div>
                <div className="mono">
                  [{ (selectedSpan.char_span || [selectedSpan.start, selectedSpan.end]).join(", ") }]
                </div>
              </div>

              {selectedSpan.type && (
                <div>
                  <div style={{ color: "var(--muted)", fontSize: "11px" }}>Entity Type</div>
                  <div><span className="role-chip">{selectedSpan.type}</span></div>
                </div>
              )}

              {selectedSpan.kind && (
                <div>
                  <div style={{ color: "var(--muted)", fontSize: "11px" }}>Mention Kind</div>
                  <div>{selectedSpan.kind}</div>
                </div>
              )}

              {selectedSpan.node_id && (
                <div>
                  <div style={{ color: "var(--muted)", fontSize: "11px" }}>Graph Node ID</div>
                  <div className="mono">{selectedSpan.node_id}</div>
                  <a
                    href={`#/case/${caseId}/graph?select=${selectedSpan.node_id}`}
                    className="table-link"
                    style={{ fontSize: "11px", display: "inline-block", marginTop: "2px" }}
                  >
                    Show on Graph
                  </a>
                </div>
              )}

              {selectedSpan.relation && (
                <div>
                  <div style={{ color: "var(--muted)", fontSize: "11px" }}>Relation</div>
                  <div><strong>{selectedSpan.relation}</strong></div>
                </div>
              )}
            </div>
          ) : (
            <div style={{ color: "var(--muted)" }}>
              Click on any highlighted text span in the document to view its entity or relation properties.
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}

export default EvidenceDoc;
