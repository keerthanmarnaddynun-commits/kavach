import React, { useState, useMemo } from "react";
import snapshot from "../data/model_performance.json";
import { hasRole } from "../lib/roles.js";
import {
  formatPercent,
  formatScore,
  formatMs,
  getHeadlineData,
  getPerTypeItems,
  getErrorClasses,
  getGeneralisationGapData,
  getBaselineModels,
  getSpeedData,
} from "./modelPerformanceHelpers.js";

/**
 * Admin-only Model Performance Dashboard.
 * Visualizes model evaluation metrics, error breakdowns, generalisation gaps, baselines and speed.
 */
export function ModelPerformance({ user }) {
  const isAdmin = user && hasRole(user.role, "admin");

  // Route guard: only admin can view this page
  if (!isAdmin) {
    return (
      <div
        className="admin-access-required"
        data-testid="admin-access-required"
        style={{
          padding: "24px",
          color: "var(--danger)",
          fontSize: "14px",
          backgroundColor: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: "4px",
          margin: "24px",
        }}
      >
        Admin access required
      </div>
    );
  }

  // State controls for interactivity
  // Block B (Entity extraction)
  const [entityDataset, setEntityDataset] = useState("held_out"); // "held_out" | "synthetic_test"
  const [entityMode, setEntityMode] = useState("strict"); // "strict" | "lenient"
  const [entitySortKey, setEntitySortKey] = useState("f1");
  const [entitySortDir, setEntitySortDir] = useState("desc");

  // Block C (Relation extraction)
  const [relDataset, setRelDataset] = useState("held_out"); // "held_out" | "synthetic_test"
  const [relMode, setRelMode] = useState("strict"); // "strict" | "lenient"
  const [relSortKey, setRelSortKey] = useState("f1");
  const [relSortDir, setRelSortDir] = useState("desc");

  // Block D (Error breakdown)
  const [errorTarget, setErrorTarget] = useState("mentions"); // "mentions" | "relations"
  const [errorKind, setErrorKind] = useState("fp"); // "fp" | "fn"
  const [selectedErrorClass, setSelectedErrorClass] = useState("REPEAT_SHORT_FORM");

  // Block F (Baselines)
  const [baselineMetric, setBaselineMetric] = useState("f1"); // "f1" | "grouped"

  // Hover tooltips state
  const [tooltip, setTooltip] = useState(null);

  // Data extraction
  const headline = useMemo(() => getHeadlineData(snapshot), []);
  const generalisation = useMemo(() => getGeneralisationGapData(snapshot), []);
  const baselines = useMemo(() => getBaselineModels(snapshot?.baselines, "f1"), []);
  const speed = useMemo(() => getSpeedData(snapshot?.speed), []);

  // Entity items
  const rawEntityItems = snapshot?.entities_by_type?.[entityDataset] || [];
  const entityItems = useMemo(
    () => getPerTypeItems(rawEntityItems, entityMode, entitySortKey, entitySortDir),
    [rawEntityItems, entityMode, entitySortKey, entitySortDir]
  );

  // Relation items
  const rawRelItems = snapshot?.relations_by_type?.[relDataset] || [];
  const relItems = useMemo(
    () => getPerTypeItems(rawRelItems, relMode, relSortKey, relSortDir),
    [rawRelItems, relMode, relSortKey, relSortDir]
  );

  // Error breakdown items
  const errorClasses = useMemo(
    () => getErrorClasses(snapshot?.error_breakdown, errorTarget, errorKind),
    [errorTarget, errorKind]
  );

  const activeErrorObj = useMemo(() => {
    return errorClasses.find((c) => c.className === selectedErrorClass) || errorClasses[0] || null;
  }, [errorClasses, selectedErrorClass]);

  // Sorting handlers
  const handleEntitySort = (key) => {
    if (entitySortKey === key) {
      setEntitySortDir(entitySortDir === "asc" ? "desc" : "asc");
    } else {
      setEntitySortKey(key);
      setEntitySortDir("desc");
    }
  };

  const handleRelSort = (key) => {
    if (relSortKey === key) {
      setRelSortDir(relSortDir === "asc" ? "desc" : "asc");
    } else {
      setRelSortKey(key);
      setRelSortDir("desc");
    }
  };

  return (
    <div
      className="model-performance-page"
      data-testid="model-performance-page"
      style={{
        padding: "24px 32px",
        maxWidth: "1280px",
        margin: "0 auto",
        color: "var(--text)",
        fontFamily: "system-ui, -apple-system, sans-serif",
      }}
    >
      {/* Page Header */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
          marginBottom: "24px",
          borderBottom: "1px solid var(--border)",
          paddingBottom: "12px",
        }}
      >
        <div>
          <h1 style={{ margin: 0, fontSize: "22px", fontWeight: 700 }}>Model performance</h1>
          <div style={{ fontSize: "12px", color: "var(--muted)", marginTop: "4px" }}>
            Single source of truth evaluation dashboard from official pipeline and held-out benchmarks.
          </div>
        </div>
        <div style={{ fontSize: "12px", color: "var(--muted)" }}>
          <span className="mono">Admin Mode</span>
        </div>
      </div>

      {/* BLOCK A: Headline Strip */}
      <section
        data-testid="block-headline"
        style={{
          backgroundColor: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: "4px",
          padding: "16px 20px",
          marginBottom: "24px",
        }}
      >
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
            gap: "16px",
          }}
        >
          {/* Held-Out Mentions */}
          <div style={{ borderLeft: "3px solid var(--accent)", paddingLeft: "12px" }}>
            <div style={{ fontSize: "11px", color: "var(--muted)", textTransform: "uppercase" }}>
              Held-Out Mentions (Strict)
            </div>
            <div style={{ fontSize: "24px", fontWeight: 700, color: "var(--text)", marginTop: "2px" }}>
              {headline.heldOut.mentionsF1}
            </div>
            <div style={{ fontSize: "11px", color: "var(--muted)", marginTop: "2px" }}>
              {`Precision ${headline.heldOut.mentionsP} | Recall ${headline.heldOut.mentionsR}`}
            </div>
          </div>

          {/* Held-Out Relations */}
          <div style={{ borderLeft: "3px solid var(--record-accent)", paddingLeft: "12px" }}>
            <div style={{ fontSize: "11px", color: "var(--muted)", textTransform: "uppercase" }}>
              Held-Out Relations (Micro)
            </div>
            <div style={{ fontSize: "24px", fontWeight: 700, color: "var(--text)", marginTop: "2px" }}>
              {headline.heldOut.relationsF1}
            </div>
            <div style={{ fontSize: "11px", color: "var(--muted)", marginTop: "2px" }}>
              {`Precision ${headline.heldOut.relationsP} | Recall ${headline.heldOut.relationsR}`}
            </div>
          </div>

          {/* Synthetic Test Mentions */}
          <div style={{ borderLeft: "3px solid var(--tag-records-text)", paddingLeft: "12px" }}>
            <div style={{ fontSize: "11px", color: "var(--muted)", textTransform: "uppercase" }}>
              Synthetic Test Mentions
            </div>
            <div style={{ fontSize: "24px", fontWeight: 700, color: "var(--text)", marginTop: "2px" }}>
              {headline.syntheticTest.mentionsF1}
            </div>
            <div style={{ fontSize: "11px", color: "var(--muted)", marginTop: "2px" }}>
              Strict F1 across test set
            </div>
          </div>

          {/* Synthetic Test Relations */}
          <div style={{ borderLeft: "3px solid var(--tag-fir-text)", paddingLeft: "12px" }}>
            <div style={{ fontSize: "11px", color: "var(--muted)", textTransform: "uppercase" }}>
              Synthetic Test Relations
            </div>
            <div style={{ fontSize: "24px", fontWeight: 700, color: "var(--text)", marginTop: "2px" }}>
              {headline.syntheticTest.relationsF1}
            </div>
            <div style={{ fontSize: "11px", color: "var(--muted)", marginTop: "2px" }}>
              Micro F1 on test split
            </div>
          </div>
        </div>

        {/* Dataset Count Line & Provenance Caption */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginTop: "14px",
            paddingTop: "10px",
            borderTop: "1px dashed var(--border)",
            fontSize: "12px",
          }}
        >
          <div style={{ fontWeight: 600, color: "var(--text)" }}>{headline.caption}</div>
          <div style={{ color: "var(--muted)", fontSize: "11px" }}>
            {`Run: ${headline.provenance}`}
          </div>
        </div>
      </section>

      {/* Grid: Block B (Entities) & Block C (Relations) */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: "24px", marginBottom: "24px" }}>
        {/* BLOCK B: Entity Extraction by Type */}
        <section
          data-testid="block-entities"
          style={{
            backgroundColor: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: "4px",
            padding: "20px",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
            <div>
              <h2 style={{ fontSize: "16px", fontWeight: 700, margin: 0 }}>Entity extraction by type</h2>
              <div style={{ fontSize: "12px", color: "var(--muted)", marginTop: "2px" }}>
                Grouped metrics for precision, recall, and F1 score with support counts.
              </div>
            </div>
            {/* Toggles */}
            <div style={{ display: "flex", gap: "8px" }}>
              {/* Dataset toggle */}
              <div style={{ display: "inline-flex", border: "1px solid var(--border)", borderRadius: "3px" }}>
                <button
                  type="button"
                  data-testid="entity-dataset-heldout"
                  onClick={() => setEntityDataset("held_out")}
                  style={{
                    padding: "4px 10px",
                    fontSize: "12px",
                    border: "none",
                    cursor: "pointer",
                    backgroundColor: entityDataset === "held_out" ? "var(--accent)" : "var(--surface)",
                    color: entityDataset === "held_out" ? "var(--surface)" : "var(--text)",
                    fontWeight: entityDataset === "held_out" ? 600 : 400,
                  }}
                >
                  Held-out
                </button>
                <button
                  type="button"
                  data-testid="entity-dataset-synthetic"
                  onClick={() => setEntityDataset("synthetic_test")}
                  style={{
                    padding: "4px 10px",
                    fontSize: "12px",
                    border: "none",
                    cursor: "pointer",
                    backgroundColor: entityDataset === "synthetic_test" ? "var(--accent)" : "var(--surface)",
                    color: entityDataset === "synthetic_test" ? "var(--surface)" : "var(--text)",
                    fontWeight: entityDataset === "synthetic_test" ? 600 : 400,
                  }}
                >
                  Synthetic test
                </button>
              </div>

              {/* Mode toggle */}
              <div style={{ display: "inline-flex", border: "1px solid var(--border)", borderRadius: "3px" }}>
                <button
                  type="button"
                  data-testid="entity-mode-strict"
                  onClick={() => setEntityMode("strict")}
                  style={{
                    padding: "4px 10px",
                    fontSize: "12px",
                    border: "none",
                    cursor: "pointer",
                    backgroundColor: entityMode === "strict" ? "var(--muted)" : "var(--surface)",
                    color: entityMode === "strict" ? "var(--surface)" : "var(--text)",
                    fontWeight: entityMode === "strict" ? 600 : 400,
                  }}
                >
                  Strict
                </button>
                <button
                  type="button"
                  data-testid="entity-mode-lenient"
                  onClick={() => setEntityMode("lenient")}
                  style={{
                    padding: "4px 10px",
                    fontSize: "12px",
                    border: "none",
                    cursor: "pointer",
                    backgroundColor: entityMode === "lenient" ? "var(--muted)" : "var(--surface)",
                    color: entityMode === "lenient" ? "var(--surface)" : "var(--text)",
                    fontWeight: entityMode === "lenient" ? 600 : 400,
                  }}
                >
                  Lenient
                </button>
              </div>
            </div>
          </div>

          {/* Grouped Bar Chart */}
          <GroupedBarChart
            items={entityItems}
            onHoverBar={(item, metric, val, e) => {
              if (item) {
                setTooltip({
                  x: e.clientX,
                  y: e.clientY,
                  title: `${item.name} (${entityMode})`,
                  lines: [
                    `Precision: ${formatScore(item.precision)}`,
                    `Recall: ${formatScore(item.recall)}`,
                    `F1 Score: ${formatScore(item.f1)}`,
                    `Support (Gold): ${item.gold}`,
                    `Predicted: ${item.predicted}`,
                  ],
                });
              } else {
                setTooltip(null);
              }
            }}
          />

          {/* Sortable Table */}
          <div style={{ marginTop: "16px", overflowX: "auto" }}>
            <table
              data-testid="entity-table"
              style={{
                width: "100%",
                borderCollapse: "collapse",
                fontSize: "12px",
                textAlign: "left",
              }}
            >
              <thead>
                <tr style={{ borderBottom: "2px solid var(--border)", color: "var(--muted)" }}>
                  <th
                    style={{ padding: "8px 6px", cursor: "pointer" }}
                    onClick={() => handleEntitySort("name")}
                  >
                    Entity Type {entitySortKey === "name" && (entitySortDir === "asc" ? "↑" : "↓")}
                  </th>
                  <th
                    style={{ padding: "8px 6px", cursor: "pointer", textAlign: "right" }}
                    onClick={() => handleEntitySort("precision")}
                  >
                    Precision {entitySortKey === "precision" && (entitySortDir === "asc" ? "↑" : "↓")}
                  </th>
                  <th
                    style={{ padding: "8px 6px", cursor: "pointer", textAlign: "right" }}
                    onClick={() => handleEntitySort("recall")}
                  >
                    Recall {entitySortKey === "recall" && (entitySortDir === "asc" ? "↑" : "↓")}
                  </th>
                  <th
                    style={{ padding: "8px 6px", cursor: "pointer", textAlign: "right" }}
                    onClick={() => handleEntitySort("f1")}
                  >
                    F1 Score {entitySortKey === "f1" && (entitySortDir === "asc" ? "↑" : "↓")}
                  </th>
                  <th
                    style={{ padding: "8px 6px", cursor: "pointer", textAlign: "right" }}
                    onClick={() => handleEntitySort("gold")}
                  >
                    Support {entitySortKey === "gold" && (entitySortDir === "asc" ? "↑" : "↓")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {entityItems.map((item, idx) => (
                  <tr
                    key={item.name}
                    style={{
                      borderBottom: "1px solid var(--border)",
                      backgroundColor: idx % 2 === 0 ? "var(--surface)" : "var(--bg)",
                    }}
                  >
                    <td style={{ padding: "6px", fontWeight: 600 }} className="mono">
                      {item.name}
                    </td>
                    <td style={{ padding: "6px", textAlign: "right" }} className="mono">
                      {formatScore(item.precision)}
                    </td>
                    <td style={{ padding: "6px", textAlign: "right" }} className="mono">
                      {formatScore(item.recall)}
                    </td>
                    <td style={{ padding: "6px", textAlign: "right", fontWeight: 600 }} className="mono">
                      {formatScore(item.f1)}
                    </td>
                    <td style={{ padding: "6px", textAlign: "right" }} className="mono">
                      {item.gold}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div style={{ marginTop: "12px", textAlign: "right", fontSize: "11px", color: "var(--muted)" }}>
            {`Run: ${snapshot?.entities_by_type?.provenance_caption || ""}`}
          </div>
        </section>

        {/* BLOCK C: Relation Extraction by Type */}
        <section
          data-testid="block-relations"
          style={{
            backgroundColor: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: "4px",
            padding: "20px",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
            <div>
              <h2 style={{ fontSize: "16px", fontWeight: 700, margin: 0 }}>Relation extraction by type</h2>
              <div style={{ fontSize: "12px", color: "var(--muted)", marginTop: "2px" }}>
                Relational link detection precision, recall, and F1 score with support counts.
              </div>
            </div>
            {/* Toggles */}
            <div style={{ display: "flex", gap: "8px" }}>
              <div style={{ display: "inline-flex", border: "1px solid var(--border)", borderRadius: "3px" }}>
                <button
                  type="button"
                  data-testid="rel-dataset-heldout"
                  onClick={() => setRelDataset("held_out")}
                  style={{
                    padding: "4px 10px",
                    fontSize: "12px",
                    border: "none",
                    cursor: "pointer",
                    backgroundColor: relDataset === "held_out" ? "var(--accent)" : "var(--surface)",
                    color: relDataset === "held_out" ? "var(--surface)" : "var(--text)",
                    fontWeight: relDataset === "held_out" ? 600 : 400,
                  }}
                >
                  Held-out
                </button>
                <button
                  type="button"
                  data-testid="rel-dataset-synthetic"
                  onClick={() => setRelDataset("synthetic_test")}
                  style={{
                    padding: "4px 10px",
                    fontSize: "12px",
                    border: "none",
                    cursor: "pointer",
                    backgroundColor: relDataset === "synthetic_test" ? "var(--accent)" : "var(--surface)",
                    color: relDataset === "synthetic_test" ? "var(--surface)" : "var(--text)",
                    fontWeight: relDataset === "synthetic_test" ? 600 : 400,
                  }}
                >
                  Synthetic test
                </button>
              </div>

              <div style={{ display: "inline-flex", border: "1px solid var(--border)", borderRadius: "3px" }}>
                <button
                  type="button"
                  data-testid="rel-mode-strict"
                  onClick={() => setRelMode("strict")}
                  style={{
                    padding: "4px 10px",
                    fontSize: "12px",
                    border: "none",
                    cursor: "pointer",
                    backgroundColor: relMode === "strict" ? "var(--muted)" : "var(--surface)",
                    color: relMode === "strict" ? "var(--surface)" : "var(--text)",
                    fontWeight: relMode === "strict" ? 600 : 400,
                  }}
                >
                  Strict
                </button>
                <button
                  type="button"
                  data-testid="rel-mode-lenient"
                  onClick={() => setRelMode("lenient")}
                  style={{
                    padding: "4px 10px",
                    fontSize: "12px",
                    border: "none",
                    cursor: "pointer",
                    backgroundColor: relMode === "lenient" ? "var(--muted)" : "var(--surface)",
                    color: relMode === "lenient" ? "var(--surface)" : "var(--text)",
                    fontWeight: relMode === "lenient" ? 600 : 400,
                  }}
                >
                  Lenient
                </button>
              </div>
            </div>
          </div>

          {/* Grouped Bar Chart */}
          <GroupedBarChart
            items={relItems}
            onHoverBar={(item, metric, val, e) => {
              if (item) {
                setTooltip({
                  x: e.clientX,
                  y: e.clientY,
                  title: `${item.name}`,
                  lines: [
                    `Precision: ${formatScore(item.precision)}`,
                    `Recall: ${formatScore(item.recall)}`,
                    `F1 Score: ${formatScore(item.f1)}`,
                    `Support (Gold): ${item.gold}`,
                    `Predicted: ${item.predicted}`,
                  ],
                });
              } else {
                setTooltip(null);
              }
            }}
          />

          {/* Sortable Table */}
          <div style={{ marginTop: "16px", overflowX: "auto" }}>
            <table
              data-testid="relation-table"
              style={{
                width: "100%",
                borderCollapse: "collapse",
                fontSize: "12px",
                textAlign: "left",
              }}
            >
              <thead>
                <tr style={{ borderBottom: "2px solid var(--border)", color: "var(--muted)" }}>
                  <th
                    style={{ padding: "8px 6px", cursor: "pointer" }}
                    onClick={() => handleRelSort("name")}
                  >
                    Relation Type {relSortKey === "name" && (relSortDir === "asc" ? "↑" : "↓")}
                  </th>
                  <th
                    style={{ padding: "8px 6px", cursor: "pointer", textAlign: "right" }}
                    onClick={() => handleRelSort("precision")}
                  >
                    Precision {relSortKey === "precision" && (relSortDir === "asc" ? "↑" : "↓")}
                  </th>
                  <th
                    style={{ padding: "8px 6px", cursor: "pointer", textAlign: "right" }}
                    onClick={() => handleRelSort("recall")}
                  >
                    Recall {relSortKey === "recall" && (relSortDir === "asc" ? "↑" : "↓")}
                  </th>
                  <th
                    style={{ padding: "8px 6px", cursor: "pointer", textAlign: "right" }}
                    onClick={() => handleRelSort("f1")}
                  >
                    F1 Score {relSortKey === "f1" && (relSortDir === "asc" ? "↑" : "↓")}
                  </th>
                  <th
                    style={{ padding: "8px 6px", cursor: "pointer", textAlign: "right" }}
                    onClick={() => handleRelSort("gold")}
                  >
                    Support {relSortKey === "gold" && (relSortDir === "asc" ? "↑" : "↓")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {relItems.map((item, idx) => (
                  <tr
                    key={item.name}
                    style={{
                      borderBottom: "1px solid var(--border)",
                      backgroundColor: idx % 2 === 0 ? "var(--surface)" : "var(--bg)",
                    }}
                  >
                    <td style={{ padding: "6px", fontWeight: 600 }} className="mono">
                      {item.name}
                    </td>
                    <td style={{ padding: "6px", textAlign: "right" }} className="mono">
                      {formatScore(item.precision)}
                    </td>
                    <td style={{ padding: "6px", textAlign: "right" }} className="mono">
                      {formatScore(item.recall)}
                    </td>
                    <td style={{ padding: "6px", textAlign: "right", fontWeight: 600 }} className="mono">
                      {formatScore(item.f1)}
                    </td>
                    <td style={{ padding: "6px", textAlign: "right" }} className="mono">
                      {item.gold}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div style={{ marginTop: "12px", textAlign: "right", fontSize: "11px", color: "var(--muted)" }}>
            {`Run: ${snapshot?.relations_by_type?.provenance_caption || ""}`}
          </div>
        </section>
      </div>

      {/* BLOCK D: How it fails (held-out) */}
      <section
        data-testid="block-errors"
        style={{
          backgroundColor: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: "4px",
          padding: "20px",
          marginBottom: "24px",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
          <div>
            <h2 style={{ fontSize: "16px", fontWeight: 700, margin: 0 }}>How it fails (held-out error breakdown)</h2>
            <div style={{ fontSize: "12px", color: "var(--muted)", marginTop: "2px" }}>
              Taxonomy of extraction errors from held-out gap analysis. Click any bar to inspect real examples.
            </div>
          </div>
          {/* Toggles */}
          <div style={{ display: "flex", gap: "8px" }}>
            <div style={{ display: "inline-flex", border: "1px solid var(--border)", borderRadius: "3px" }}>
              <button
                type="button"
                data-testid="error-target-mentions"
                onClick={() => {
                  setErrorTarget("mentions");
                  setSelectedErrorClass("");
                }}
                style={{
                  padding: "4px 10px",
                  fontSize: "12px",
                  border: "none",
                  cursor: "pointer",
                  backgroundColor: errorTarget === "mentions" ? "var(--accent)" : "var(--surface)",
                  color: errorTarget === "mentions" ? "var(--surface)" : "var(--text)",
                  fontWeight: errorTarget === "mentions" ? 600 : 400,
                }}
              >
                Mentions
              </button>
              <button
                type="button"
                data-testid="error-target-relations"
                onClick={() => {
                  setErrorTarget("relations");
                  setSelectedErrorClass("");
                }}
                style={{
                  padding: "4px 10px",
                  fontSize: "12px",
                  border: "none",
                  cursor: "pointer",
                  backgroundColor: errorTarget === "relations" ? "var(--accent)" : "var(--surface)",
                  color: errorTarget === "relations" ? "var(--surface)" : "var(--text)",
                  fontWeight: errorTarget === "relations" ? 600 : 400,
                }}
              >
                Relations
              </button>
            </div>

            <div style={{ display: "inline-flex", border: "1px solid var(--border)", borderRadius: "3px" }}>
              <button
                type="button"
                data-testid="error-kind-fp"
                onClick={() => {
                  setErrorKind("fp");
                  setSelectedErrorClass("");
                }}
                style={{
                  padding: "4px 10px",
                  fontSize: "12px",
                  border: "none",
                  cursor: "pointer",
                  backgroundColor: errorKind === "fp" ? "var(--record-accent)" : "var(--surface)",
                  color: errorKind === "fp" ? "var(--surface)" : "var(--text)",
                  fontWeight: errorKind === "fp" ? 600 : 400,
                }}
              >
                False Positives
              </button>
              <button
                type="button"
                data-testid="error-kind-fn"
                onClick={() => {
                  setErrorKind("fn");
                  setSelectedErrorClass("");
                }}
                style={{
                  padding: "4px 10px",
                  fontSize: "12px",
                  border: "none",
                  cursor: "pointer",
                  backgroundColor: errorKind === "fn" ? "var(--record-accent)" : "var(--surface)",
                  color: errorKind === "fn" ? "var(--surface)" : "var(--text)",
                  fontWeight: errorKind === "fn" ? 600 : 400,
                }}
              >
                False Negatives
              </button>
            </div>
          </div>
        </div>

        {/* Horizontal Bar Chart for Error Classes */}
        <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
          {errorClasses.map((item) => {
            const isSelected = activeErrorObj?.className === item.className;
            return (
              <div
                key={item.className}
                data-testid={`error-bar-${item.className}`}
                onClick={() => setSelectedErrorClass(item.className)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  cursor: "pointer",
                  padding: "6px 8px",
                  borderRadius: "3px",
                  backgroundColor: isSelected ? "var(--highlight)" : "transparent",
                  border: isSelected ? "1px solid var(--highlight-border)" : "1px solid transparent",
                }}
              >
                <div style={{ width: "260px", fontSize: "12px", fontWeight: 600 }} className="mono">
                  {item.className}
                </div>
                <div style={{ flex: 1, backgroundColor: "var(--bg)", height: "18px", borderRadius: "2px", overflow: "hidden", margin: "0 12px" }}>
                  <div
                    style={{
                      width: `${Math.min(item.pct, 100)}%`,
                      backgroundColor: isSelected ? "var(--record-accent)" : "var(--accent)",
                      height: "100%",
                      borderRadius: "2px",
                    }}
                  />
                </div>
                <div style={{ width: "110px", textAlign: "right", fontSize: "12px" }} className="mono">
                  {`${item.count} (${item.pct}%)`}
                </div>
              </div>
            );
          })}
        </div>

        {/* Selected Error Examples Panel */}
        <div
          data-testid="error-examples-panel"
          style={{
            marginTop: "18px",
            padding: "14px 16px",
            backgroundColor: "var(--bg)",
            border: "1px solid var(--border)",
            borderRadius: "4px",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "8px" }}>
            <span style={{ fontSize: "13px", fontWeight: 700 }}>
              {`Class: ${activeErrorObj?.className || "None"} (${activeErrorObj?.count || 0} occurrences, ${activeErrorObj?.pct || 0}%)`}
            </span>
            <span style={{ fontSize: "11px", color: "var(--muted)" }}>Showing up to 5 real examples from errors.json</span>
          </div>

          {activeErrorObj?.examples && activeErrorObj.examples.length > 0 ? (
            <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
              {activeErrorObj.examples.map((ex, i) => (
                <div
                  key={i}
                  style={{
                    padding: "6px 10px",
                    backgroundColor: "var(--surface)",
                    border: "1px solid var(--border)",
                    borderRadius: "3px",
                    fontSize: "12px",
                  }}
                >
                  <span className="mono" style={{ color: "var(--accent)", fontWeight: 600, marginRight: "8px" }}>
                    {`[${ex.file}]`}
                  </span>
                  {ex.surface && (
                    <span style={{ marginRight: "8px" }}>
                      Surface: <strong>&ldquo;{ex.surface}&rdquo;</strong>
                    </span>
                  )}
                  {ex.relation && (
                    <span style={{ marginRight: "8px" }}>
                      Relation: <span className="mono">{ex.relation}</span>
                      {ex.source_surface && ex.target_surface && ` (${ex.source_surface} -> ${ex.target_surface})`}
                    </span>
                  )}
                  {ex.char_span && (
                    <span className="mono" style={{ color: "var(--muted)", marginRight: "8px" }}>
                      {`span: [${ex.char_span.join(", ")}]`}
                    </span>
                  )}
                  {ex.note && (
                    <span style={{ color: "var(--muted)", fontStyle: "italic" }}>
                      {`(${ex.note})`}
                    </span>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div style={{ fontSize: "12px", color: "var(--muted)" }}>
              No example occurrences listed for this class.
            </div>
          )}
        </div>

        <div style={{ marginTop: "12px", textAlign: "right", fontSize: "11px", color: "var(--muted)" }}>
          {`Run: ${snapshot?.error_breakdown?.provenance_caption || ""}`}
        </div>
      </section>

      {/* Grid: Block E (Generalisation gap) & Block F (Baselines) */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "24px", marginBottom: "24px" }}>
        {/* BLOCK E: Generalisation Gap */}
        <section
          data-testid="block-gap"
          style={{
            backgroundColor: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: "4px",
            padding: "20px",
          }}
        >
          <h2 style={{ fontSize: "16px", fontWeight: 700, margin: 0 }}>Generalisation gap</h2>
          <div style={{ fontSize: "12px", color: "var(--muted)", marginTop: "2px", marginBottom: "16px" }}>
            Synthetic test vs independent held-out evaluation comparison.
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
            {generalisation.comparison.map((row) => (
              <div key={row.metric} style={{ borderBottom: "1px solid var(--border)", paddingBottom: "12px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: "13px", fontWeight: 600, marginBottom: "6px" }}>
                  <span>{row.metric}</span>
                  <span style={{ color: "var(--danger)" }}>{`Gap: -${formatScore(row.gap)}`}</span>
                </div>
                {/* Visual bar pair */}
                <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                  <div style={{ display: "flex", alignItems: "center", fontSize: "11px" }}>
                    <span style={{ width: "110px", color: "var(--muted)" }}>Synthetic test:</span>
                    <div style={{ flex: 1, backgroundColor: "var(--bg)", height: "14px", borderRadius: "2px", margin: "0 8px" }}>
                      <div
                        style={{
                          width: `${Math.min(row.synthetic_test * 100, 100)}%`,
                          backgroundColor: "var(--tag-records-text)",
                          height: "100%",
                          borderRadius: "2px",
                        }}
                      />
                    </div>
                    <span className="mono" style={{ width: "45px", textAlign: "right" }}>
                      {formatScore(row.synthetic_test)}
                    </span>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", fontSize: "11px" }}>
                    <span style={{ width: "110px", color: "var(--muted)" }}>Held-out:</span>
                    <div style={{ flex: 1, backgroundColor: "var(--bg)", height: "14px", borderRadius: "2px", margin: "0 8px" }}>
                      <div
                        style={{
                          width: `${Math.min(row.held_out * 100, 100)}%`,
                          backgroundColor: "var(--record-accent)",
                          height: "100%",
                          borderRadius: "2px",
                        }}
                      />
                    </div>
                    <span className="mono" style={{ width: "45px", textAlign: "right" }}>
                      {formatScore(row.held_out)}
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>

          <div style={{ marginTop: "16px", textAlign: "right", fontSize: "11px", color: "var(--muted)" }}>
            {`Run: ${generalisation.provenance}`}
          </div>
        </section>

        {/* BLOCK F: Against Baselines */}
        <section
          data-testid="block-baselines"
          style={{
            backgroundColor: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: "4px",
            padding: "20px",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
            <div>
              <h2 style={{ fontSize: "16px", fontWeight: 700, margin: 0 }}>Against baselines</h2>
              <div style={{ fontSize: "12px", color: "var(--muted)", marginTop: "2px" }}>
                Comparison on synthetic test corpus.
              </div>
            </div>
            {/* Metric Toggle */}
            <div style={{ display: "inline-flex", border: "1px solid var(--border)", borderRadius: "3px" }}>
              <button
                type="button"
                data-testid="baseline-toggle-f1"
                onClick={() => setBaselineMetric("f1")}
                style={{
                  padding: "4px 10px",
                  fontSize: "12px",
                  border: "none",
                  cursor: "pointer",
                  backgroundColor: baselineMetric === "f1" ? "var(--accent)" : "var(--surface)",
                  color: baselineMetric === "f1" ? "var(--surface)" : "var(--text)",
                  fontWeight: baselineMetric === "f1" ? 600 : 400,
                }}
              >
                F1 Score
              </button>
              <button
                type="button"
                data-testid="baseline-toggle-grouped"
                onClick={() => setBaselineMetric("grouped")}
                style={{
                  padding: "4px 10px",
                  fontSize: "12px",
                  border: "none",
                  cursor: "pointer",
                  backgroundColor: baselineMetric === "grouped" ? "var(--accent)" : "var(--surface)",
                  color: baselineMetric === "grouped" ? "var(--surface)" : "var(--text)",
                  fontWeight: baselineMetric === "grouped" ? 600 : 400,
                }}
              >
                P / R / F1
              </button>
            </div>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
            {baselines.models.map((model) => (
              <div key={model.name} style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: "12px" }}>
                  <span style={{ fontWeight: 600 }}>{model.name}</span>
                  <span className="mono">
                    {baselineMetric === "f1"
                      ? `F1: ${formatScore(model.f1)}`
                      : `P: ${formatScore(model.precision)} | R: ${formatScore(model.recall)} | F1: ${formatScore(model.f1)}`}
                  </span>
                </div>
                <div style={{ backgroundColor: "var(--bg)", height: "16px", borderRadius: "2px", overflow: "hidden" }}>
                  <div
                    style={{
                      width: `${Math.min(model.f1 * 100, 100)}%`,
                      backgroundColor: model.modelId === "pipeline" ? "var(--tag-records-text)" : "var(--accent)",
                      height: "100%",
                      borderRadius: "2px",
                    }}
                  />
                </div>
              </div>
            ))}
          </div>

          <div style={{ marginTop: "14px", fontStyle: "italic", fontSize: "11px", color: "var(--muted)" }}>
            {baselines.caption}
          </div>

          <div style={{ marginTop: "8px", textAlign: "right", fontSize: "11px", color: "var(--muted)" }}>
            {`Run: ${baselines.provenance}`}
          </div>
        </section>
      </div>

      {/* BLOCK G: Speed (Latency per stage) */}
      <section
        data-testid="block-speed"
        style={{
          backgroundColor: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: "4px",
          padding: "20px",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
          <div>
            <h2 style={{ fontSize: "16px", fontWeight: 700, margin: 0 }}>Speed (latency per stage)</h2>
            <div style={{ fontSize: "12px", color: "var(--muted)", marginTop: "2px" }}>
              Pipeline processing duration from latency.run2 measurements.
            </div>
          </div>
          <div style={{ textAlign: "right" }}>
            <div style={{ fontSize: "18px", fontWeight: 700, color: "var(--text)" }}>
              {`Total: ${formatMs(speed.total.mean_ms)}`}
            </div>
            <div style={{ fontSize: "11px", color: "var(--muted)" }}>
              {`p95: ${formatMs(speed.total.p95_ms)} | Model load: ${formatMs(speed.modelLoadMs)}`}
            </div>
          </div>
        </div>

        {/* Stacked Latency Bar */}
        <div style={{ marginBottom: "16px" }}>
          <div
            style={{
              display: "flex",
              height: "24px",
              borderRadius: "4px",
              overflow: "hidden",
              backgroundColor: "var(--bg)",
            }}
          >
            {speed.stages.map((stage, idx) => {
              const widthPct = (stage.mean_ms / (speed.total.mean_ms || 1)) * 100;
              const colors = [
                "var(--accent)",
                "var(--record-accent)",
                "var(--tag-fir-text)",
                "var(--tag-records-text)",
                "var(--muted)",
                "var(--danger)",
              ];
              const color = colors[idx % colors.length];
              return (
                <div
                  key={stage.id}
                  title={`${stage.label}: ${formatMs(stage.mean_ms)} (p95: ${formatMs(stage.p95_ms)})`}
                  style={{
                    width: `${widthPct}%`,
                    backgroundColor: color,
                    height: "100%",
                  }}
                />
              );
            })}
          </div>
        </div>

        {/* Latency Stages Table */}
        <div style={{ overflowX: "auto" }}>
          <table
            data-testid="speed-table"
            style={{
              width: "100%",
              borderCollapse: "collapse",
              fontSize: "12px",
              textAlign: "left",
            }}
          >
            <thead>
              <tr style={{ borderBottom: "2px solid var(--border)", color: "var(--muted)" }}>
                <th style={{ padding: "6px" }}>Pipeline Stage</th>
                <th style={{ padding: "6px", textAlign: "right" }}>Mean Latency</th>
                <th style={{ padding: "6px", textAlign: "right" }}>p95 Latency</th>
                <th style={{ padding: "6px", textAlign: "right" }}>Share</th>
              </tr>
            </thead>
            <tbody>
              {speed.stages.map((stage, idx) => {
                const colors = [
                  "var(--accent)",
                  "var(--record-accent)",
                  "var(--tag-fir-text)",
                  "var(--tag-records-text)",
                  "var(--muted)",
                  "var(--danger)",
                ];
                const color = colors[idx % colors.length];
                const sharePct = ((stage.mean_ms / (speed.total.mean_ms || 1)) * 100).toFixed(1);
                return (
                  <tr
                    key={stage.id}
                    style={{
                      borderBottom: "1px solid var(--border)",
                      backgroundColor: idx % 2 === 0 ? "var(--surface)" : "var(--bg)",
                    }}
                  >
                    <td style={{ padding: "6px", display: "flex", alignItems: "center", gap: "8px" }}>
                      <span style={{ width: "10px", height: "10px", borderRadius: "2px", backgroundColor: color, display: "inline-block" }} />
                      <span style={{ fontWeight: 600 }}>{stage.label}</span>
                    </td>
                    <td style={{ padding: "6px", textAlign: "right" }} className="mono">
                      {formatMs(stage.mean_ms)}
                    </td>
                    <td style={{ padding: "6px", textAlign: "right" }} className="mono">
                      {formatMs(stage.p95_ms)}
                    </td>
                    <td style={{ padding: "6px", textAlign: "right" }} className="mono">
                      {`${sharePct}%`}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        <div style={{ marginTop: "12px", textAlign: "right", fontSize: "11px", color: "var(--muted)" }}>
          {`Run: ${speed.provenance}`}
        </div>
      </section>

      {/* Floating Hover Tooltip */}
      {tooltip && (
        <div
          style={{
            position: "fixed",
            left: tooltip.x + 12,
            top: tooltip.y + 12,
            backgroundColor: "var(--text)",
            color: "var(--surface)",
            padding: "8px 12px",
            borderRadius: "4px",
            fontSize: "11px",
            zIndex: 9999,
            pointerEvents: "none",
          }}
        >
          <div style={{ fontWeight: 700, marginBottom: "4px" }}>{tooltip.title}</div>
          {tooltip.lines.map((l, i) => (
            <div key={i}>{l}</div>
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * Reusable Grouped Bar Chart using clean inline SVG (no external libraries).
 */
function GroupedBarChart({ items = [], onHoverBar }) {
  if (!items || items.length === 0) {
    return <div style={{ fontSize: "12px", color: "var(--muted)", padding: "16px" }}>No items to display.</div>;
  }

  const svgWidth = 800;
  const svgHeight = 180;
  const margin = { top: 15, right: 20, bottom: 45, left: 40 };
  const plotWidth = svgWidth - margin.left - margin.right;
  const plotHeight = svgHeight - margin.top - margin.bottom;

  const numGroups = items.length;
  const groupWidth = plotWidth / numGroups;
  const barWidth = Math.min(Math.max(groupWidth / 4, 6), 18);
  const barSpacing = 2;

  return (
    <div style={{ width: "100%", overflowX: "auto" }}>
      <svg
        viewBox={`0 0 ${svgWidth} ${svgHeight}`}
        style={{
          width: "100%",
          height: "200px",
          display: "block",
          overflow: "visible",
        }}
        role="img"
        aria-label="Grouped performance chart"
      >
        {/* Background Grid Lines & Ticks */}
        {[0, 0.25, 0.5, 0.75, 1.0].map((tick) => {
          const y = margin.top + plotHeight - tick * plotHeight;
          return (
            <g key={tick}>
              <line
                x1={margin.left}
                y1={y}
                x2={margin.left + plotWidth}
                y2={y}
                stroke="var(--border)"
                strokeDasharray={tick === 0 ? "none" : "2,2"}
              />
              <text
                x={margin.left - 6}
                y={y + 4}
                textAnchor="end"
                fontSize="10"
                fill="var(--muted)"
                fontFamily="ui-monospace, monospace"
              >
                {tick.toFixed(2)}
              </text>
            </g>
          );
        })}

        {/* Groups of Bars */}
        {items.map((item, groupIdx) => {
          const groupCenterX = margin.left + groupIdx * groupWidth + groupWidth / 2;
          const startX = groupCenterX - (barWidth * 3 + barSpacing * 2) / 2;

          const pHeight = Math.max((item.precision || 0) * plotHeight, 1);
          const rHeight = Math.max((item.recall || 0) * plotHeight, 1);
          const fHeight = Math.max((item.f1 || 0) * plotHeight, 1);

          const pY = margin.top + plotHeight - pHeight;
          const rY = margin.top + plotHeight - rHeight;
          const fY = margin.top + plotHeight - fHeight;

          return (
            <g key={item.name}>
              {/* Precision Bar */}
              <rect
                x={startX}
                y={pY}
                width={barWidth}
                height={pHeight}
                fill="var(--accent)"
                rx="1"
                onMouseEnter={(e) => onHoverBar(item, "Precision", item.precision, e)}
                onMouseLeave={(e) => onHoverBar(null, null, null, e)}
                style={{ cursor: "pointer" }}
              />
              {/* Recall Bar */}
              <rect
                x={startX + barWidth + barSpacing}
                y={rY}
                width={barWidth}
                height={rHeight}
                fill="var(--record-accent)"
                rx="1"
                onMouseEnter={(e) => onHoverBar(item, "Recall", item.recall, e)}
                onMouseLeave={(e) => onHoverBar(null, null, null, e)}
                style={{ cursor: "pointer" }}
              />
              {/* F1 Bar */}
              <rect
                x={startX + (barWidth + barSpacing) * 2}
                y={fY}
                width={barWidth}
                height={fHeight}
                fill="var(--tag-fir-text)"
                rx="1"
                onMouseEnter={(e) => onHoverBar(item, "F1", item.f1, e)}
                onMouseLeave={(e) => onHoverBar(null, null, null, e)}
                style={{ cursor: "pointer" }}
              />

              {/* X Axis Label */}
              <text
                x={groupCenterX}
                y={margin.top + plotHeight + 14}
                textAnchor="middle"
                fontSize="10"
                fill="var(--text)"
                fontWeight="600"
                fontFamily="ui-monospace, monospace"
              >
                {item.name}
              </text>
              <text
                x={groupCenterX}
                y={margin.top + plotHeight + 26}
                textAnchor="middle"
                fontSize="9"
                fill="var(--muted)"
                fontFamily="ui-monospace, monospace"
              >
                {`n=${item.gold}`}
              </text>
            </g>
          );
        })}
      </svg>
      {/* Legend */}
      <div style={{ display: "flex", justifyContent: "center", gap: "16px", marginTop: "4px", fontSize: "11px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "4px" }}>
          <span style={{ width: "10px", height: "10px", backgroundColor: "var(--accent)", display: "inline-block", borderRadius: "1px" }} />
          <span>Precision</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "4px" }}>
          <span style={{ width: "10px", height: "10px", backgroundColor: "var(--record-accent)", display: "inline-block", borderRadius: "1px" }} />
          <span>Recall</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "4px" }}>
          <span style={{ width: "10px", height: "10px", backgroundColor: "var(--tag-fir-text)", display: "inline-block", borderRadius: "1px" }} />
          <span>F1 Score</span>
        </div>
      </div>
    </div>
  );
}
