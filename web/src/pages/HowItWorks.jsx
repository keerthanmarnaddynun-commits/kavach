/**
 * HowItWorks.jsx - Admin-only interactive walkthrough of the extraction pipeline.
 * Explains the real KAVACH NLP extraction pipeline to examiners without showing code.
 */

import React, { useState } from "react";
import snapshot from "../data/pipeline_walkthrough.json";
import {
  getSampleList,
  getSampleData,
  getStepData,
  getCodeMap,
  getTypeStyle,
  splitTextIntoHighlightedSegments,
} from "./howItWorksHelpers.js";

export function HowItWorks({ user, initialSampleId = "FIR_01", initialStepIndex = 0 }) {
  const isAdmin = user?.role === "admin";

  const [selectedSampleId, setSelectedSampleId] = useState(initialSampleId);
  const [currentStepIndex, setCurrentStepIndex] = useState(initialStepIndex);
  const [activeEvidenceSpan, setActiveEvidenceSpan] = useState(null);
  const [hoveredSpan, setHoveredSpan] = useState(null);
  const [isCodeMapOpen, setIsCodeMapOpen] = useState(false);

  // Route guard
  if (!isAdmin) {
    return (
      <div style={{ padding: "40px 24px", maxWidth: "800px", margin: "0 auto" }}>
        <div
          data-testid="how-it-works-guard-denied"
          style={{
            padding: "20px",
            backgroundColor: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: "4px",
          }}
        >
          <h2 style={{ margin: "0 0 8px", fontSize: "18px", color: "var(--danger)" }}>
            Admin access required
          </h2>
          <p style={{ margin: 0, fontSize: "14px", color: "var(--muted)" }}>
            You must be signed in as an administrator to view the NLP pipeline walkthrough.
          </p>
        </div>
      </div>
    );
  }

  const sampleList = getSampleList(snapshot);
  const currentSample = getSampleData(snapshot, selectedSampleId);
  const currentStep = getStepData(currentSample, currentStepIndex);
  const codeMap = getCodeMap(snapshot);
  const steps = currentSample?.steps || [];

  const handleSampleChange = (e) => {
    setSelectedSampleId(e.target.value);
    setActiveEvidenceSpan(null);
    setHoveredSpan(null);
  };

  const handlePrevStep = () => {
    setCurrentStepIndex((prev) => Math.max(0, prev - 1));
    setActiveEvidenceSpan(null);
    setHoveredSpan(null);
  };

  const handleNextStep = () => {
    setCurrentStepIndex((prev) => Math.min(steps.length - 1, prev + 1));
    setActiveEvidenceSpan(null);
    setHoveredSpan(null);
  };

  const textSegments = splitTextIntoHighlightedSegments(
    currentSample?.text || "",
    currentStep?.spans || [],
    activeEvidenceSpan
  );

  return (
    <div
      data-testid="how-it-works-page"
      style={{
        padding: "24px",
        maxWidth: "1400px",
        margin: "0 auto",
        color: "var(--text)",
      }}
    >
      {/* Page Header */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          marginBottom: "20px",
          flexWrap: "wrap",
          gap: "16px",
        }}
      >
        <div>
          <h1 style={{ fontSize: "22px", fontWeight: 700, margin: "0 0 4px" }}>
            How the NLP works
          </h1>
          <div style={{ fontSize: "13px", color: "var(--muted)" }}>
            Step-by-step walkthrough of the extraction pipeline on real FIR samples for examiners.
          </div>
        </div>

        {/* Sample Selector */}
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <label htmlFor="sample-select" style={{ fontSize: "13px", fontWeight: 600 }}>
            Sample FIR:
          </label>
          <select
            id="sample-select"
            data-testid="sample-selector"
            value={selectedSampleId}
            onChange={handleSampleChange}
            style={{
              padding: "6px 12px",
              fontSize: "13px",
              backgroundColor: "var(--surface)",
              color: "var(--text)",
              border: "1px solid var(--border)",
              borderRadius: "4px",
              cursor: "pointer",
            }}
          >
            {sampleList.map((s) => (
              <option key={s.sampleId} value={s.sampleId}>
                {s.title}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Stepper Navigation */}
      <div
        data-testid="pipeline-stepper"
        style={{
          backgroundColor: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: "4px",
          padding: "12px 16px",
          marginBottom: "20px",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: "8px",
            overflowX: "auto",
            paddingBottom: "4px",
          }}
        >
          <button
            type="button"
            data-testid="stepper-prev"
            onClick={handlePrevStep}
            disabled={currentStepIndex === 0}
            style={{
              padding: "6px 14px",
              fontSize: "12px",
              fontWeight: 600,
              backgroundColor: "var(--surface)",
              color: currentStepIndex === 0 ? "var(--muted)" : "var(--accent)",
              border: "1px solid var(--border)",
              borderRadius: "4px",
              cursor: currentStepIndex === 0 ? "not-allowed" : "pointer",
              opacity: currentStepIndex === 0 ? 0.5 : 1,
            }}
          >
            &larr; Previous
          </button>

          <div style={{ display: "flex", gap: "6px", flexWrap: "wrap", justifyContent: "center" }}>
            {steps.map((st, idx) => {
              const isActive = idx === currentStepIndex;
              return (
                <button
                  key={st.stage_id}
                  type="button"
                  data-testid={`step-button-${idx}`}
                  onClick={() => {
                    setCurrentStepIndex(idx);
                    setActiveEvidenceSpan(null);
                    setHoveredSpan(null);
                  }}
                  style={{
                    padding: "6px 12px",
                    fontSize: "12px",
                    fontWeight: isActive ? 700 : 500,
                    backgroundColor: isActive ? "var(--accent)" : "var(--surface)",
                    color: isActive ? "var(--surface)" : "var(--text)",
                    border: isActive ? "1px solid var(--accent)" : "1px solid var(--border)",
                    borderRadius: "4px",
                    cursor: "pointer",
                    display: "flex",
                    alignItems: "center",
                    gap: "6px",
                  }}
                >
                  <span
                    style={{
                      width: "18px",
                      height: "18px",
                      borderRadius: "50%",
                      backgroundColor: isActive ? "var(--surface)" : "var(--bg)",
                      color: isActive ? "var(--accent)" : "var(--muted)",
                      display: "inline-flex",
                      alignItems: "center",
                      justifyContent: "center",
                      fontSize: "11px",
                      fontWeight: 700,
                    }}
                  >
                    {idx}
                  </span>
                  <span>{st.step_name}</span>
                </button>
              );
            })}
          </div>

          <button
            type="button"
            data-testid="stepper-next"
            onClick={handleNextStep}
            disabled={currentStepIndex === steps.length - 1}
            style={{
              padding: "6px 14px",
              fontSize: "12px",
              fontWeight: 600,
              backgroundColor: "var(--surface)",
              color: currentStepIndex === steps.length - 1 ? "var(--muted)" : "var(--accent)",
              border: "1px solid var(--border)",
              borderRadius: "4px",
              cursor: currentStepIndex === steps.length - 1 ? "not-allowed" : "pointer",
              opacity: currentStepIndex === steps.length - 1 ? 0.5 : 1,
            }}
          >
            Next &rarr;
          </button>
        </div>
      </div>

      {/* Main Two-Column Walkthrough Grid */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1.1fr 0.9fr",
          gap: "24px",
          alignItems: "start",
          marginBottom: "24px",
        }}
      >
        {/* Left Column: FIR Text with Inline Highlights */}
        <div
          data-testid="fir-text-panel"
          style={{
            backgroundColor: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: "4px",
            padding: "20px",
          }}
        >
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: "12px",
              borderBottom: "1px solid var(--border)",
              paddingBottom: "8px",
            }}
          >
            <div>
              <span style={{ fontWeight: 700, fontSize: "14px" }}>{currentSample?.title}</span>
              <span style={{ fontSize: "12px", color: "var(--muted)", marginLeft: "10px" }}>
                ({currentSample?.language})
              </span>
            </div>
            <div className="mono" style={{ fontSize: "11px", color: "var(--muted)" }}>
              {currentSample?.char_count} chars | SHA-256: {currentSample?.sha256?.slice(0, 10)}...
            </div>
          </div>

          {/* Text Container with Highlighting */}
          <div
            data-testid="highlighted-text-box"
            style={{
              backgroundColor: "var(--bg)",
              border: "1px solid var(--border)",
              borderRadius: "4px",
              padding: "16px",
              fontSize: "13px",
              lineHeight: 1.7,
              fontFamily: "monospace",
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
              maxHeight: "520px",
              overflowY: "auto",
            }}
          >
            {textSegments.map((seg, sIdx) => {
              if (!seg.isSpan && !seg.inEvidence) {
                return <span key={sIdx}>{seg.text}</span>;
              }

              if (seg.isSpan) {
                const style = getTypeStyle(seg.span?.type, seg.span?.source);
                const titleText = `${seg.span?.type} (${seg.span?.source === "model" ? "Neural Model" : "Rule"})${
                  seg.span?.score ? ` [conf: ${seg.span.score}]` : ""
                }`;
                return (
                  <mark
                    key={sIdx}
                    data-testid={`span-highlight-${seg.start}`}
                    title={titleText}
                    onMouseEnter={() => setHoveredSpan(seg.span)}
                    onMouseLeave={() => setHoveredSpan(null)}
                    style={{
                      backgroundColor: seg.inEvidence ? "var(--highlight-hover)" : style.backgroundColor,
                      color: style.color,
                      border: style.border,
                      borderRadius: "3px",
                      padding: "1px 4px",
                      margin: "0 1px",
                      fontWeight: 600,
                      cursor: "pointer",
                      display: "inline-block",
                    }}
                  >
                    {seg.text}
                  </mark>
                );
              }

              // In evidence sentence only
              return (
                <mark
                  key={sIdx}
                  title="Supporting evidence sentence for relationship"
                  style={{
                    backgroundColor: "var(--highlight)",
                    color: "var(--text)",
                    borderBottom: "2px solid var(--record-accent)",
                    padding: "1px 0",
                  }}
                >
                  {seg.text}
                </mark>
              );
            })}
          </div>

          {/* Hover Status Bar */}
          <div
            style={{
              marginTop: "8px",
              minHeight: "22px",
              fontSize: "12px",
              color: hoveredSpan ? "var(--accent)" : "var(--muted)",
              fontStyle: hoveredSpan ? "normal" : "italic",
            }}
          >
            {hoveredSpan ? (
              <span>
                <strong>{hoveredSpan.type}</strong> ({hoveredSpan.source === "model" ? "Neural model" : "Rule"}):{" "}
                &quot;{hoveredSpan.surface || hoveredSpan.canonical_name}&quot;
                {hoveredSpan.score ? ` (confidence: ${hoveredSpan.score})` : ""}
              </span>
            ) : (
              "Hover over any highlighted span to inspect its type, source, and detection confidence."
            )}
          </div>

          {/* Legend */}
          <div
            style={{
              marginTop: "16px",
              paddingTop: "12px",
              borderTop: "1px solid var(--border)",
              display: "flex",
              flexWrap: "wrap",
              gap: "12px",
              fontSize: "11px",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
              <span
                style={{
                  display: "inline-block",
                  width: "16px",
                  height: "12px",
                  backgroundColor: "var(--accent-weak)",
                  border: "2px dashed var(--accent)",
                  borderRadius: "2px",
                }}
              />
              <span>Model found (XLM-R)</span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
              <span
                style={{
                  display: "inline-block",
                  width: "16px",
                  height: "12px",
                  backgroundColor: "var(--tag-fir-bg)",
                  border: "2px solid var(--record-accent)",
                  borderRadius: "2px",
                }}
              />
              <span>Rule found (Phone / IMEI / Acct)</span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
              <span
                style={{
                  display: "inline-block",
                  width: "16px",
                  height: "12px",
                  backgroundColor: "var(--highlight)",
                  borderBottom: "2px solid var(--record-accent)",
                }}
              />
              <span>Supporting relation cue</span>
            </div>
          </div>
        </div>

        {/* Right Column: Step Explanation & Output */}
        <div
          data-testid="step-output-panel"
          style={{
            backgroundColor: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: "4px",
            padding: "20px",
          }}
        >
          {/* Step Header */}
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: "14px",
              borderBottom: "1px solid var(--border)",
              paddingBottom: "10px",
            }}
          >
            <div>
              <span
                style={{
                  fontSize: "11px",
                  fontWeight: 700,
                  color: "var(--muted)",
                  textTransform: "uppercase",
                  letterSpacing: "0.5px",
                }}
              >
                {`Step ${currentStep?.step_index} of ${steps.length - 1}`}
              </span>
              <h2 style={{ fontSize: "17px", fontWeight: 700, margin: "2px 0 0" }}>
                {currentStep?.step_name}
              </h2>
            </div>
            {currentStep?.timing_ms > 0 ? (
              <span
                data-testid="step-timing-badge"
                className="mono"
                style={{
                  padding: "4px 8px",
                  backgroundColor: "var(--bg)",
                  border: "1px solid var(--border)",
                  borderRadius: "3px",
                  fontSize: "12px",
                  fontWeight: 600,
                  color: "var(--accent)",
                }}
                title="Average processing duration from latency benchmarks"
              >
                {currentStep.timing_ms} ms avg
              </span>
            ) : (
              <span
                className="mono"
                style={{
                  padding: "4px 8px",
                  backgroundColor: "var(--bg)",
                  border: "1px solid var(--border)",
                  borderRadius: "3px",
                  fontSize: "12px",
                  color: "var(--muted)",
                }}
              >
                Intake / View
              </span>
            )}
          </div>

          {/* Plain-Language Explanation */}
          <div
            style={{
              backgroundColor: "var(--bg)",
              border: "1px solid var(--border)",
              borderRadius: "4px",
              padding: "12px 14px",
              marginBottom: "18px",
              fontSize: "13px",
              lineHeight: 1.5,
            }}
          >
            <div style={{ marginBottom: "6px" }}>
              <strong style={{ color: "var(--accent)" }}>What this step does: </strong>
              <span>{currentStep?.what_it_does}</span>
            </div>
            <div>
              <strong style={{ color: "var(--record-accent)" }}>Why it is needed: </strong>
              <span>{currentStep?.why_needed}</span>
            </div>
          </div>

          {/* Step-Specific Output View */}
          <div>
            <div
              style={{
                fontSize: "13px",
                fontWeight: 700,
                marginBottom: "8px",
                color: "var(--text)",
              }}
            >
              Stage Output &amp; Discovered Items
            </div>

            {/* STEP 0: Raw FIR Metadata */}
            {currentStepIndex === 0 && (
              <div data-testid="step-output-raw" style={{ fontSize: "12px" }}>
                <table style={{ width: "100%", borderCollapse: "collapse" }}>
                  <tbody>
                    <tr style={{ borderBottom: "1px solid var(--border)" }}>
                      <td style={{ padding: "8px 0", color: "var(--muted)", width: "130px" }}>Document ID</td>
                      <td className="mono" style={{ fontWeight: 600 }}>{currentSample?.sample_id}</td>
                    </tr>
                    <tr style={{ borderBottom: "1px solid var(--border)" }}>
                      <td style={{ padding: "8px 0", color: "var(--muted)" }}>Language</td>
                      <td style={{ fontWeight: 600 }}>{currentSample?.language}</td>
                    </tr>
                    <tr style={{ borderBottom: "1px solid var(--border)" }}>
                      <td style={{ padding: "8px 0", color: "var(--muted)" }}>Character Count</td>
                      <td className="mono">{`${currentSample?.char_count} characters`}</td>
                    </tr>
                    <tr style={{ borderBottom: "1px solid var(--border)" }}>
                      <td style={{ padding: "8px 0", color: "var(--muted)" }}>SHA-256 Digest</td>
                      <td className="mono" style={{ wordBreak: "break-all" }}>{currentSample?.sha256}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            )}

            {/* STEP 1: Neural Model Mentions */}
            {currentStepIndex === 1 && (
              <div data-testid="step-output-model" style={{ maxHeight: "320px", overflowY: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "12px" }}>
                  <thead>
                    <tr style={{ borderBottom: "2px solid var(--border)", color: "var(--muted)", textAlign: "left" }}>
                      <th style={{ padding: "6px" }}>Mention Text</th>
                      <th style={{ padding: "6px" }}>Span</th>
                      <th style={{ padding: "6px", textAlign: "right" }}>Confidence</th>
                    </tr>
                  </thead>
                  <tbody>
                    {currentStep?.new_items?.map((item, idx) => (
                      <tr key={idx} style={{ borderBottom: "1px solid var(--border)" }}>
                        <td style={{ padding: "6px", fontWeight: 600 }}>{item.surface}</td>
                        <td className="mono" style={{ padding: "6px", color: "var(--muted)" }}>
                          [{item.start}, {item.end}]
                        </td>
                        <td className="mono" style={{ padding: "6px", textAlign: "right" }}>
                          {item.score}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* STEP 2: Postprocessing Alignment Table */}
            {currentStepIndex === 2 && (
              <div data-testid="step-output-postprocess" style={{ maxHeight: "320px", overflowY: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "12px" }}>
                  <thead>
                    <tr style={{ borderBottom: "2px solid var(--border)", color: "var(--muted)", textAlign: "left" }}>
                      <th style={{ padding: "6px" }}>Raw piece(s)</th>
                      <th style={{ padding: "6px" }}>Cleaned mention</th>
                      <th style={{ padding: "6px" }}>What changed</th>
                    </tr>
                  </thead>
                  <tbody>
                    {currentStep?.new_items?.map((item, idx) => {
                      const rawSpans = item.raw_spans || [];
                      const rawOffsets = rawSpans.map((s) => `[${s[0]}, ${s[1]}]`).join(" + ");
                      const cleanedOffsets = item.cleaned_span ? `[${item.cleaned_span[0]}, ${item.cleaned_span[1]}]` : "(dropped)";
                      const tooltip = `Raw: ${rawOffsets} -> Cleaned: ${cleanedOffsets}`;
                      const isMerged = item.changes?.some((c) => c.startsWith("merged"));
                      const isDropped = item.status === "dropped";
                      return (
                        <tr
                          key={idx}
                          title={tooltip}
                          data-testid={`postprocess-row-${idx}`}
                          style={{ borderBottom: "1px solid var(--border)", cursor: "help" }}
                        >
                          <td className="mono" style={{ padding: "6px", color: isDropped ? "var(--muted)" : "var(--text)" }}>
                            {item.raw_text}
                          </td>
                          <td
                            style={{
                              padding: "6px",
                              fontWeight: isDropped ? 400 : 600,
                              color: isDropped ? "var(--muted)" : "var(--text)",
                              fontStyle: isDropped ? "italic" : "normal",
                            }}
                          >
                            {item.cleaned}
                          </td>
                          <td style={{ padding: "6px" }}>
                            {isMerged ? (
                              <span style={{ color: "var(--record-accent)", fontSize: "11px", fontWeight: 600 }}>
                                {item.status}
                              </span>
                            ) : isDropped ? (
                              <span style={{ color: "var(--danger)", fontSize: "11px", fontWeight: 600 }}>
                                {item.status}
                              </span>
                            ) : item.status === "unchanged" ? (
                              <span style={{ color: "var(--muted)", fontSize: "11px" }}>
                                {item.status}
                              </span>
                            ) : (
                              <span style={{ color: "var(--accent)", fontSize: "11px", fontWeight: 600 }}>
                                {item.status}
                              </span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
                <div
                  data-testid="postprocess-caption"
                  style={{
                    marginTop: "8px",
                    fontSize: "12px",
                    color: "var(--muted)",
                    fontStyle: "italic",
                  }}
                >
                  Postprocessing is a light clean-up step; most mentions pass through unchanged.
                </div>
              </div>
            )}

            {/* STEP 3: Rule-based Names & Identifiers */}
            {currentStepIndex === 3 && (
              <div data-testid="step-output-names-ids" style={{ maxHeight: "320px", overflowY: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "12px" }}>
                  <thead>
                    <tr style={{ borderBottom: "2px solid var(--border)", color: "var(--muted)", textAlign: "left" }}>
                      <th style={{ padding: "6px" }}>Type</th>
                      <th style={{ padding: "6px" }}>Value / Text</th>
                      <th style={{ padding: "6px" }}>Validation</th>
                    </tr>
                  </thead>
                  <tbody>
                    {currentStep?.new_items?.map((item, idx) => (
                      <tr key={idx} style={{ borderBottom: "1px solid var(--border)" }}>
                        <td style={{ padding: "6px" }}>
                          <span
                            style={{
                              padding: "2px 6px",
                              borderRadius: "3px",
                              fontSize: "11px",
                              fontWeight: 700,
                              backgroundColor: "var(--tag-fir-bg)",
                              color: "var(--tag-fir-text)",
                            }}
                          >
                            {item.type}
                          </span>
                        </td>
                        <td className="mono" style={{ padding: "6px", fontWeight: 600 }}>
                          {item.surface || item.value}
                        </td>
                        <td style={{ padding: "6px", color: "var(--muted)", fontSize: "11px" }}>
                          {item.check || "Pattern matched"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* STEP 4: Entity Assembly */}
            {currentStepIndex === 4 && (
              <div data-testid="step-output-assemble" style={{ maxHeight: "320px", overflowY: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "12px" }}>
                  <thead>
                    <tr style={{ borderBottom: "2px solid var(--border)", color: "var(--muted)", textAlign: "left" }}>
                      <th style={{ padding: "6px" }}>ID</th>
                      <th style={{ padding: "6px" }}>Type</th>
                      <th style={{ padding: "6px" }}>Canonical Name / Value</th>
                      <th style={{ padding: "6px" }}>Attributes</th>
                    </tr>
                  </thead>
                  <tbody>
                    {currentStep?.new_items?.map((ent) => (
                      <tr key={ent.entity_id} style={{ borderBottom: "1px solid var(--border)" }}>
                        <td className="mono" style={{ padding: "6px", color: "var(--muted)" }}>
                          {ent.entity_id}
                        </td>
                        <td style={{ padding: "6px" }}>
                          <span
                            style={{
                              padding: "2px 6px",
                              borderRadius: "3px",
                              fontSize: "11px",
                              fontWeight: 700,
                              backgroundColor: ent.type === "PERSON" ? "var(--accent-weak)" : "var(--tag-records-bg)",
                              color: ent.type === "PERSON" ? "var(--accent)" : "var(--tag-records-text)",
                            }}
                          >
                            {ent.type}
                          </span>
                        </td>
                        <td style={{ padding: "6px", fontWeight: 600 }}>
                          {ent.canonical_name}
                          {ent.role && (
                            <span style={{ fontSize: "10px", color: "var(--muted)", marginLeft: "6px" }}>
                              ({ent.role})
                            </span>
                          )}
                        </td>
                        <td style={{ padding: "6px", fontSize: "11px", color: "var(--muted)" }}>
                          {ent.aliases && ent.aliases.length > 0 && `Alias: ${ent.aliases.join(", ")} `}
                          {ent.father_name && `Father: ${ent.father_name}`}
                          {!ent.aliases?.length && !ent.father_name && `${ent.mention_count} mention(s)`}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* STEP 5: Relation Extraction with Hover Cue Highlighting */}
            {currentStepIndex === 5 && (
              <div data-testid="step-output-relations" style={{ maxHeight: "320px", overflowY: "auto" }}>
                <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                  {currentStep?.new_items?.map((rel) => {
                    const isHovered = activeEvidenceSpan && activeEvidenceSpan[0] === rel.evidence_char_span[0];
                    return (
                      <div
                        key={rel.relation_id}
                        data-testid={`rel-item-${rel.relation_id}`}
                        onMouseEnter={() => setActiveEvidenceSpan(rel.evidence_char_span)}
                        onMouseLeave={() => setActiveEvidenceSpan(null)}
                        style={{
                          padding: "10px 12px",
                          backgroundColor: isHovered ? "var(--highlight-hover)" : "var(--bg)",
                          border: isHovered ? "1px solid var(--record-accent)" : "1px solid var(--border)",
                          borderRadius: "4px",
                          cursor: "pointer",
                          transition: "background-color 0.15s ease",
                        }}
                      >
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "4px" }}>
                          <div style={{ fontSize: "13px", fontWeight: 700 }}>
                            <span style={{ color: "var(--accent)" }}>{rel.source_name}</span>
                            <span style={{ margin: "0 8px", color: "var(--record-accent)" }}>
                              &mdash; {rel.relation} &rarr;
                            </span>
                            <span style={{ color: "var(--accent)" }}>{rel.target_name}</span>
                          </div>
                          <span
                            className="mono"
                            style={{
                              padding: "2px 6px",
                              borderRadius: "3px",
                              fontSize: "10px",
                              fontWeight: 700,
                              backgroundColor: "var(--surface)",
                              border: "1px solid var(--border)",
                              color: "var(--muted)",
                            }}
                          >
                            {rel.trigger}
                          </span>
                        </div>
                        {rel.cue_sentence && (
                          <div style={{ fontSize: "11px", color: "var(--muted)", fontStyle: "italic", marginTop: "4px" }}>
                            &ldquo;{rel.cue_sentence.slice(0, 100)}...&rdquo;
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* STEP 6: Contract Validation Checklist */}
            {currentStepIndex === 6 && (
              <div data-testid="step-output-validate">
                <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                  {currentStep?.new_items?.map((chk, idx) => (
                    <div
                      key={idx}
                      style={{
                        display: "flex",
                        alignItems: "flex-start",
                        justifyContent: "space-between",
                        padding: "10px 12px",
                        backgroundColor: "var(--bg)",
                        border: "1px solid var(--border)",
                        borderRadius: "4px",
                      }}
                    >
                      <div>
                        <div style={{ fontWeight: 600, fontSize: "13px" }}>{chk.check}</div>
                        <div style={{ fontSize: "11px", color: "var(--muted)", marginTop: "2px" }}>
                          {chk.detail}
                        </div>
                      </div>
                      <span
                        style={{
                          padding: "2px 8px",
                          borderRadius: "3px",
                          fontSize: "11px",
                          fontWeight: 700,
                          backgroundColor: "var(--accent-weak)",
                          color: "var(--accent)",
                        }}
                      >
                        {chk.status}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* STEP 7: Into the Case Graph Static Diagram */}
            {currentStepIndex === 7 && (
              <div data-testid="step-output-graph">
                <div
                  style={{
                    backgroundColor: "var(--bg)",
                    border: "1px solid var(--border)",
                    borderRadius: "4px",
                    padding: "12px",
                    marginBottom: "12px",
                    textAlign: "center",
                  }}
                >
                  <div style={{ fontSize: "11px", color: "var(--muted)", marginBottom: "8px" }}>
                    Static Graph Projection ({currentStep?.summary?.nodes_count} nodes, {currentStep?.summary?.edges_count} edges)
                  </div>

                  {/* Clean SVG Graph Diagram */}
                  <svg
                    data-testid="static-graph-svg"
                    viewBox="0 0 440 240"
                    style={{
                      width: "100%",
                      maxHeight: "220px",
                      backgroundColor: "var(--surface)",
                      borderRadius: "4px",
                      border: "1px solid var(--border)",
                    }}
                  >
                    <defs>
                      <marker
                        id="arrow"
                        viewBox="0 0 10 10"
                        refX="8"
                        refY="5"
                        markerWidth="6"
                        markerHeight="6"
                        orient="auto-start-reverse"
                      >
                        <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--record-accent)" />
                      </marker>
                    </defs>

                    {/* Edge lines */}
                    <line x1="80" y1="60" x2="220" y2="60" stroke="var(--record-accent)" strokeWidth="2" markerEnd="url(#arrow)" />
                    <line x1="220" y1="60" x2="360" y2="60" stroke="var(--record-accent)" strokeWidth="2" markerEnd="url(#arrow)" />
                    <line x1="80" y1="60" x2="150" y2="170" stroke="var(--record-accent)" strokeWidth="2" markerEnd="url(#arrow)" />
                    <line x1="150" y1="170" x2="290" y2="170" stroke="var(--record-accent)" strokeWidth="2" markerEnd="url(#arrow)" />

                    {/* Edge labels */}
                    <text x="145" y="52" fontSize="9" fill="var(--record-accent)" textAnchor="middle" fontWeight="bold">OWNS_DEVICE</text>
                    <text x="290" y="52" fontSize="9" fill="var(--record-accent)" textAnchor="middle" fontWeight="bold">ASSOCIATED_IMEI</text>
                    <text x="95" y="125" fontSize="9" fill="var(--record-accent)" textAnchor="middle" fontWeight="bold">CONTROLS</text>
                    <text x="220" y="162" fontSize="9" fill="var(--record-accent)" textAnchor="middle" fontWeight="bold">TRANSFERRED</text>

                    {/* Nodes */}
                    <g transform="translate(80, 60)">
                      <circle r="22" fill="var(--accent-weak)" stroke="var(--accent)" strokeWidth="2" />
                      <text textAnchor="middle" y="4" fontSize="10" fontWeight="bold" fill="var(--accent)">Person</text>
                    </g>
                    <g transform="translate(220, 60)">
                      <rect x="-28" y="-18" width="56" height="36" rx="4" fill="var(--tag-fir-bg)" stroke="var(--tag-fir-text)" strokeWidth="2" />
                      <text textAnchor="middle" y="4" fontSize="10" fontWeight="bold" fill="var(--tag-fir-text)">Phone</text>
                    </g>
                    <g transform="translate(360, 60)">
                      <rect x="-24" y="-18" width="48" height="36" rx="4" fill="var(--highlight)" stroke="var(--record-accent)" strokeWidth="2" />
                      <text textAnchor="middle" y="4" fontSize="10" fontWeight="bold" fill="var(--record-accent)">IMEI</text>
                    </g>
                    <g transform="translate(150, 170)">
                      <rect x="-30" y="-18" width="60" height="36" rx="4" fill="var(--tag-records-bg)" stroke="var(--tag-records-text)" strokeWidth="2" />
                      <text textAnchor="middle" y="4" fontSize="10" fontWeight="bold" fill="var(--tag-records-text)">Account A</text>
                    </g>
                    <g transform="translate(290, 170)">
                      <rect x="-30" y="-18" width="60" height="36" rx="4" fill="var(--tag-records-bg)" stroke="var(--tag-records-text)" strokeWidth="2" />
                      <text textAnchor="middle" y="4" fontSize="10" fontWeight="bold" fill="var(--tag-records-text)">Account B</text>
                    </g>
                  </svg>
                </div>

                <div style={{ fontSize: "11px", color: "var(--muted)" }}>
                  The case graph viewer visualizes these assembled nodes and relationships, supporting multi-hop path exploration and syndicate cut analysis.
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Collapsible "Where the code lives" Panel */}
      <div
        data-testid="code-map-accordion"
        style={{
          backgroundColor: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: "4px",
          overflow: "hidden",
        }}
      >
        <button
          type="button"
          data-testid="code-map-toggle"
          onClick={() => setIsCodeMapOpen(!isCodeMapOpen)}
          style={{
            width: "100%",
            padding: "14px 18px",
            backgroundColor: "var(--surface)",
            border: "none",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            cursor: "pointer",
            fontSize: "14px",
            fontWeight: 700,
            color: "var(--text)",
            textAlign: "left",
          }}
        >
          <span>Where the code lives (Pipeline source files &amp; functions)</span>
          <span style={{ fontSize: "16px", color: "var(--muted)" }}>
            {isCodeMapOpen ? "\u25B2 Collapse" : "\u25BC Expand"}
          </span>
        </button>

        {isCodeMapOpen && (
          <div
            data-testid="code-map-content"
            style={{
              padding: "0 18px 18px",
              borderTop: "1px solid var(--border)",
            }}
          >
            <div style={{ fontSize: "12px", color: "var(--muted)", margin: "12px 0 16px" }}>
              Exact repository file paths and function names for each extraction stage. Show paths only, no code.
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
              {codeMap.map((stage) => (
                <div
                  key={stage.stage_id}
                  style={{
                    backgroundColor: "var(--bg)",
                    border: "1px solid var(--border)",
                    borderRadius: "4px",
                    padding: "12px 14px",
                  }}
                >
                  <div style={{ fontWeight: 700, fontSize: "13px", marginBottom: "8px", color: "var(--accent)" }}>
                    {stage.stage_name}
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                    {stage.entries.map((entry, eIdx) => (
                      <div
                        key={eIdx}
                        style={{
                          display: "grid",
                          gridTemplateColumns: "220px 240px 1fr",
                          gap: "12px",
                          fontSize: "12px",
                          alignItems: "baseline",
                        }}
                      >
                        <span className="mono" style={{ fontWeight: 600 }}>
                          {entry.file}
                        </span>
                        <span className="mono" style={{ color: "var(--record-accent)" }}>
                          {entry.function}
                        </span>
                        <span style={{ color: "var(--muted)" }}>
                          {entry.role}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
