import React, { useState, useEffect, useRef, useMemo } from "react";
import cytoscape from "cytoscape";
import fcose from "cytoscape-fcose";
import { request } from "../api/client.js";
import {
  getNodeShape,
  getEdgeWidth,
  getNodeLabelVisibilityMap,
  parseSelectedIdFromUrl,
  filterGraphElements,
  splitExcerptHighlight,
} from "./graphHelpers.js";

// Register fcose layout plugin once
if (typeof cytoscape === "function" && typeof cytoscape("core", "fcose") !== "function") {
  cytoscape.use(fcose);
}

export function getCytoscapeStyles() {
  function getComputedToken(name) {
    if (typeof window !== "undefined" && typeof document !== "undefined") {
      return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    }
    return "";
  }

  const border = getComputedToken("--border");
  const text = getComputedToken("--text");
  const muted = getComputedToken("--muted");
  const accent = getComputedToken("--accent");
  const accentWeak = getComputedToken("--accent-weak");
  const surface = getComputedToken("--surface");

  return [
    {
      selector: "node",
      style: {
        shape: "data(shape)",
        "background-color": border,
        "border-width": 1,
        "border-color": muted,
        label: "data(label)",
        color: text,
        "font-size": "10px",
        "font-family": 'ui-monospace, "Cascadia Mono", Consolas, monospace',
        "text-valign": "bottom",
        "text-margin-y": 4,
        "min-zoomed-font-size": 8,
        width: 28,
        height: 28,
      },
    },
    {
      selector: "node.show-label",
      style: {
        "min-zoomed-font-size": 0,
      },
    },
    {
      selector: "node[?isTopLead]",
      style: {
        "border-color": accent,
        "border-width": 2,
        "background-color": accentWeak,
      },
    },
    {
      selector: "node:selected",
      style: {
        "border-color": accent,
        "border-width": 3,
        "background-color": accent,
        color: accent,
        "font-weight": "bold",
      },
    },
    {
      selector: "edge",
      style: {
        width: "data(edgeWidth)",
        "line-color": muted,
        "target-arrow-shape": "triangle",
        "target-arrow-color": muted,
        "curve-style": "bezier",
        "arrow-scale": 0.8,
      },
    },
    {
      selector: "edge:selected",
      style: {
        label: "data(label)",
        "font-size": "10px",
        color: accent,
        "text-background-color": surface,
        "text-background-opacity": 0.9,
        "text-background-padding": 2,
        "line-color": accent,
        "target-arrow-color": accent,
        width: 3,
      },
    },
  ];
}

export function Graph({ caseId, route }) {
  const containerRef = useRef(null);
  const cyRef = useRef(null);

  const [rawElements, setRawElements] = useState(null);
  const [topLeadIds, setTopLeadIds] = useState([]);
  const [loading, setLoading] = useState(true);
  const [layoutRunning, setLayoutRunning] = useState(false);
  const [errorText, setErrorText] = useState(null);

  // Filters
  const [nodeTypes, setNodeTypes] = useState({
    PERSON: true,
    PHONE: true,
    IMEI: true,
    ACCOUNT: true,
    VEHICLE: false,
  });
  const [relations, setRelations] = useState({});
  const [leadsOnly, setLeadsOnly] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");

  // Selection & Inspector
  const [selectedItem, setSelectedItem] = useState(null); // { type: 'node' | 'edge', id: string, data: object }
  const [inspectorData, setInspectorData] = useState(null);
  const [inspectorLoading, setInspectorLoading] = useState(false);
  const [inspectorCollapsed, setInspectorCollapsed] = useState(false);

  // Load Graph elements and Leads
  useEffect(() => {
    if (!caseId) return;
    setLoading(true);
    setErrorText(null);

    Promise.all([
      request(`/cases/${caseId}/graph`),
      request(`/cases/${caseId}/leads`).catch(() => null),
    ])
      .then(([graphRes, leadsRes]) => {
        const eles = graphRes && graphRes.elements ? graphRes.elements : { nodes: [], edges: [] };
        setRawElements(eles);

        // Discover relations in graph
        const relMap = {};
        for (const e of eles.edges || []) {
          const r = e.data && e.data.label;
          if (r) relMap[r] = true;
        }
        setRelations(relMap);

        // Top 10 priority leads
        if (leadsRes && Array.isArray(leadsRes.money_flow)) {
          const top10 = leadsRes.money_flow.slice(0, 10).map((l) => l.person_id).filter(Boolean);
          setTopLeadIds(top10);
        }
      })
      .catch((err) => {
        setErrorText(err.message || "Failed to load graph");
      })
      .finally(() => {
        setLoading(false);
      });
  }, [caseId]);

  // Compute filtered elements
  const filteredElements = useMemo(() => {
    if (!rawElements) return { nodes: [], edges: [] };
    return filterGraphElements(rawElements, nodeTypes, relations, leadsOnly, topLeadIds);
  }, [rawElements, nodeTypes, relations, leadsOnly, topLeadIds]);

  // Initialise Cytoscape instance
  useEffect(() => {
    if (!containerRef.current || loading || !rawElements) return;

    // Build elements with styling attributes
    const topSet = new Set(topLeadIds);
    const cyNodes = filteredElements.nodes.map((n) => {
      const d = n.data || {};
      const isTop = topSet.has(d.id);
      return {
        data: {
          ...d,
          shape: getNodeShape(d.type),
          isTopLead: isTop,
        },
      };
    });

    const cyEdges = filteredElements.edges.map((e) => {
      const d = e.data || {};
      return {
        data: {
          ...d,
          edgeWidth: getEdgeWidth(d.count),
        },
      };
    });

    const cy = cytoscape({
      container: containerRef.current,
      elements: [...cyNodes, ...cyEdges],
      style: getCytoscapeStyles(),
      wheelSensitivity: 0.3,
    });

    cyRef.current = cy;

    // Run layout
    runLayout(cy);

    // Event listeners
    cy.on("tap", "node", (evt) => {
      const node = evt.target;
      setSelectedItem({ type: "node", id: node.id(), data: node.data() });
    });

    cy.on("tap", "edge", (evt) => {
      const edge = evt.target;
      setSelectedItem({ type: "edge", id: edge.id(), data: edge.data() });
    });

    cy.on("tap", (evt) => {
      if (evt.target === cy) {
        setSelectedItem(null);
      }
    });

    // Check for URL selection parameter
    const initialSelect = parseSelectedIdFromUrl(route || (typeof window !== "undefined" ? window.location.hash : ""));
    if (initialSelect) {
      const targetNode = cy.getElementById(initialSelect);
      if (targetNode.length > 0) {
        targetNode.select();
        cy.center(targetNode);
        setSelectedItem({ type: "node", id: targetNode.id(), data: targetNode.data() });
      }
    }

    return () => {
      cy.destroy();
      cyRef.current = null;
    };
  }, [loading, filteredElements, topLeadIds]);

  // Label policy update via Cytoscape classes
  useEffect(() => {
    if (!cyRef.current) return;
    const cy = cyRef.current;
    const selId = selectedItem && selectedItem.type === "node" ? selectedItem.id : null;
    const visMap = getNodeLabelVisibilityMap(
      filteredElements.nodes,
      filteredElements.edges,
      selId,
      topLeadIds
    );
    cy.batch(() => {
      cy.nodes().forEach((n) => {
        if (visMap[n.id()]) {
          n.addClass("show-label");
        } else {
          n.removeClass("show-label");
        }
      });
    });
  }, [selectedItem, filteredElements, topLeadIds]);

  function runLayout(cyInstance) {
    const cy = cyInstance || cyRef.current;
    if (!cy) return;

    setLayoutRunning(true);
    const layout = cy.layout({
      name: "fcose",
      nodeDimensionsIncludeLabels: true,
      animate: false,
      randomize: false,
      fit: true,
      padding: 30,
    });

    layout.one("layoutstop", () => {
      setLayoutRunning(false);
    });

    layout.run();
  }

  // Handle Inspector Loading when selection changes
  useEffect(() => {
    if (!selectedItem || !caseId) {
      setInspectorData(null);
      return;
    }

    setInspectorLoading(true);
    const endpoint = selectedItem.type === "node"
      ? `/cases/${caseId}/nodes/${selectedItem.id}`
      : `/cases/${caseId}/edges/${selectedItem.id}`;

    request(endpoint)
      .then((data) => {
        setInspectorData(data);
      })
      .catch((err) => {
        setInspectorData({ error: err.message || "Failed to load details" });
      })
      .finally(() => {
        setInspectorLoading(false);
      });
  }, [selectedItem, caseId]);

  // Search handler (instant centering without cy.animate)
  function handleSearch(e) {
    if (e) e.preventDefault();
    const query = searchQuery.trim().toLowerCase();
    if (!query || !cyRef.current) return;

    const cy = cyRef.current;
    const matches = cy.nodes().filter((n) => {
      const id = (n.id() || "").toLowerCase();
      const label = (n.data("label") || "").toLowerCase();
      return id.includes(query) || label.includes(query);
    });

    if (matches.length > 0) {
      cy.nodes().unselect();
      matches.select();
      cy.center(matches);
      if (cy.zoom() < 1.2) {
        cy.zoom(1.2);
      }
      const first = matches[0];
      setSelectedItem({ type: "node", id: first.id(), data: first.data() });
    }
  }

  // Handle selecting a neighbour node
  function handleNeighbourClick(neighbourId) {
    if (!cyRef.current) return;
    const target = cyRef.current.getElementById(neighbourId);
    if (target.length > 0) {
      cyRef.current.nodes().unselect();
      target.select();
      cyRef.current.center(target);
      setSelectedItem({ type: "node", id: target.id(), data: target.data() });
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "calc(100vh - 80px)", overflow: "hidden" }}>
      {/* Top Filter & Toolbar */}
      <div
        style={{
          padding: "8px 12px",
          backgroundColor: "var(--surface)",
          borderBottom: "1px solid var(--border)",
          display: "flex",
          flexWrap: "wrap",
          gap: "12px",
          alignItems: "center",
          fontSize: "12px",
        }}
      >
        {/* Node Type Toggles */}
        <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
          <span style={{ fontWeight: "600", fontSize: "11px", color: "var(--muted)" }}>Nodes:</span>
          {["PERSON", "PHONE", "IMEI", "ACCOUNT", "VEHICLE"].map((t) => (
            <label key={t} style={{ display: "flex", alignItems: "center", gap: "4px", cursor: "pointer" }}>
              <input
                type="checkbox"
                checked={Boolean(nodeTypes[t])}
                onChange={(e) => setNodeTypes({ ...nodeTypes, [t]: e.target.checked })}
              />
              {t}
            </label>
          ))}
        </div>

        {/* Leads Only Toggle */}
        <label style={{ display: "flex", alignItems: "center", gap: "4px", cursor: "pointer", marginLeft: "6px" }}>
          <input
            type="checkbox"
            checked={leadsOnly}
            onChange={(e) => setLeadsOnly(e.target.checked)}
          />
          <strong>Top Leads &amp; Neighbours</strong>
        </label>

        {/* Search */}
        <form onSubmit={handleSearch} style={{ display: "flex", gap: "4px", alignItems: "center" }}>
          <input
            type="text"
            placeholder="Search label or ID..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{ width: "160px" }}
          />
          <button type="submit" style={{ fontSize: "11px" }}>
            Find
          </button>
        </form>

        {/* Controls */}
        <div style={{ display: "flex", gap: "6px", marginLeft: "auto" }}>
          <button type="button" onClick={() => runLayout()} disabled={layoutRunning}>
            Re-layout
          </button>
          <button type="button" onClick={() => cyRef.current && cyRef.current.fit()}>
            Fit
          </button>
        </div>
      </div>

      {/* Status & Legend Bar */}
      <div
        style={{
          padding: "4px 12px",
          backgroundColor: "var(--bg)",
          borderBottom: "1px solid var(--border)",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          fontSize: "11px",
          color: "var(--muted)",
        }}
      >
        <div>
          Legend: PERSON (ellipse) | PHONE (round-rectangle) | IMEI (diamond) | ACCOUNT (rectangle) | VEHICLE (triangle)
        </div>
        <div>
          {layoutRunning ? (
            <strong style={{ color: "var(--accent)" }}>Layout running...</strong>
          ) : (
            <span>Visible: {filteredElements.nodes.length} nodes, {filteredElements.edges.length} edges</span>
          )}
        </div>
      </div>

      {/* Main Graph Area + Inspector Pane */}
      <div style={{ display: "flex", flex: 1, position: "relative", overflow: "hidden" }}>
        {/* Cytoscape Canvas */}
        <div
          ref={containerRef}
          style={{
            flex: 1,
            height: "100%",
            backgroundColor: "var(--bg)",
          }}
        />

        {errorText && (
          <div
            style={{
              position: "absolute",
              top: "20px",
              left: "20px",
              padding: "8px 12px",
              backgroundColor: "var(--surface)",
              border: "1px solid var(--danger)",
              color: "var(--danger)",
              fontSize: "12px",
              zIndex: 10,
            }}
          >
            {errorText}
          </div>
        )}

        {/* Inspector Pane (340px) */}
        {selectedItem && (
          <aside
            style={{
              width: inspectorCollapsed ? "36px" : "340px",
              borderLeft: "1px solid var(--border)",
              backgroundColor: "var(--surface)",
              overflowY: "auto",
              padding: inspectorCollapsed ? "8px 4px" : "12px",
              fontSize: "12px",
              display: "flex",
              flexDirection: "column",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
              {!inspectorCollapsed && (
                <strong>{selectedItem.type === "node" ? "Node Inspector" : "Edge Inspector"}</strong>
              )}
              <button
                type="button"
                onClick={() => setInspectorCollapsed(!inspectorCollapsed)}
                style={{ fontSize: "10px", padding: "2px 6px" }}
              >
                {inspectorCollapsed ? "◀" : "▶"}
              </button>
            </div>

            {!inspectorCollapsed && (
              <div>
                {inspectorLoading ? (
                  <div>Loading details...</div>
                ) : inspectorData && inspectorData.error ? (
                  <div className="error-text">{inspectorData.error}</div>
                ) : (
                  <InspectorContent
                    caseId={caseId}
                    itemType={selectedItem.type}
                    selectedItem={selectedItem}
                    data={inspectorData || {}}
                    onNeighbourClick={handleNeighbourClick}
                  />
                )}
              </div>
            )}
          </aside>
        )}
      </div>
    </div>
  );
}

function InspectorContent({ caseId, itemType, selectedItem, data, onNeighbourClick }) {
  if (itemType === "node") {
    return (
      <NodeInspectorView
        caseId={caseId}
        selectedItem={selectedItem}
        data={data}
        onNeighbourClick={onNeighbourClick}
      />
    );
  }
  return (
    <EdgeInspectorView
      caseId={caseId}
      selectedItem={selectedItem}
      data={data}
      onNeighbourClick={onNeighbourClick}
    />
  );
}

export function NodeInspectorView({ caseId, selectedItem, data = {}, onNeighbourClick }) {
  const rawData = (selectedItem && selectedItem.data) || {};
  const firEvidence = data.fir_evidence || [];
  const csvEvidence = data.csv_evidence || [];
  const neighbours = data.neighbours || [];

  // Extractor confidence
  const confidence = typeof rawData.ai_confidence === "number"
    ? (rawData.ai_confidence * 100).toFixed(0) + "%"
    : (firEvidence.length > 0 && typeof firEvidence[0].ai_confidence === "number"
        ? (firEvidence[0].ai_confidence * 100).toFixed(0) + "%"
        : "N/A");

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
      <div>
        <div style={{ color: "var(--muted)", fontSize: "10px" }}>Type</div>
        <div><strong>{rawData.type || "NODE"}</strong></div>
      </div>

      <div>
        <div style={{ color: "var(--muted)", fontSize: "10px" }}>Label</div>
        <div>{rawData.label || "-"}</div>
        <div className="mono" style={{ fontSize: "10px", color: "var(--muted)" }}>{(selectedItem && selectedItem.id) || rawData.id}</div>
      </div>

      <div>
        <div style={{ color: "var(--muted)", fontSize: "10px" }}>Extractor Confidence</div>
        <div>{confidence}</div>
      </div>

      {/* FIR Evidence Blocks */}
      {firEvidence.length > 0 && (
        <div>
          <div style={{ color: "var(--muted)", fontSize: "10px", marginBottom: "4px" }}>
            FIR Evidence ({firEvidence.length})
          </div>
          {firEvidence.map((ev, idx) => {
            const highlight = splitExcerptHighlight(ev.excerpt, ev.surface);
            return (
              <div
                key={idx}
                style={{
                  padding: "6px",
                  backgroundColor: "var(--bg)",
                  border: "1px solid var(--border)",
                  marginBottom: "6px",
                  fontSize: "11px",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "2px" }}>
                  <a
                    href={`#/case/${caseId}/evidence/doc/${ev.doc_id}?span=${(ev.char_span || []).join("-")}`}
                    className="mono table-link"
                  >
                    {ev.doc_id}
                  </a>
                  <span className="mono" style={{ fontSize: "10px" }}>
                    [{ (ev.char_span || []).join(", ") }]
                  </span>
                </div>
                <div style={{ lineHeight: "1.4", marginTop: "4px" }}>
                  <span>{highlight.before}</span>
                  <mark style={{ backgroundColor: "var(--accent-weak)", color: "var(--accent)", padding: "1px 2px" }}>
                    {highlight.surface}
                  </mark>
                  <span>{highlight.after}</span>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* CSV Evidence References */}
      {csvEvidence.length > 0 && (
        <div>
          <div style={{ color: "var(--muted)", fontSize: "10px", marginBottom: "4px" }}>
            CSV Evidence References
          </div>
          {csvEvidence.map((cev, idx) => {
            const rows = cev.row_numbers || cev.rows || [];
            const fName = (cev.file || "").includes("bank") ? "bank" : "cdr";
            return (
              <div
                key={idx}
                style={{
                  padding: "6px",
                  backgroundColor: "var(--bg)",
                  border: "1px solid var(--border)",
                  marginBottom: "6px",
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                }}
              >
                <span className="mono">{cev.file || fName} ({rows.length} rows)</span>
                <a
                  href={`#/case/${caseId}/evidence/rows/${fName}?rows=${rows.join(",")}`}
                  className="table-link"
                  style={{ fontSize: "11px" }}
                >
                  View Rows
                </a>
              </div>
            );
          })}
        </div>
      )}

      {/* Neighbours List */}
      <div>
        <div style={{ color: "var(--muted)", fontSize: "10px", marginBottom: "4px" }}>
          Neighbours ({neighbours.length})
        </div>
        {neighbours.length === 0 ? (
          <div style={{ color: "var(--muted)", fontSize: "11px" }}>None</div>
        ) : (
          <ul style={{ margin: 0, paddingLeft: "16px", fontSize: "11px" }}>
            {neighbours.map((nbr, idx) => (
              <li key={idx} style={{ marginBottom: "2px" }}>
                <button
                  type="button"
                  onClick={() => onNeighbourClick && onNeighbourClick(nbr.id)}
                  style={{
                    background: "none",
                    border: "none",
                    color: "var(--accent)",
                    cursor: "pointer",
                    padding: 0,
                    textAlign: "left",
                  }}
                >
                  <span className="mono">{nbr.label || nbr.id}</span>
                  <span style={{ color: "var(--muted)", marginLeft: "4px" }}>({nbr.relation || nbr.type})</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

export function EdgeInspectorView({ caseId, selectedItem, data = {}, onNeighbourClick }) {
  const rawData = (selectedItem && selectedItem.data) || {};
  const firEvidence = data.fir_evidence || [];
  const csvEvidence = data.csv_evidence || [];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
      <div>
        <div style={{ color: "var(--muted)", fontSize: "10px" }}>Relation</div>
        <div><strong>{data.relation || rawData.label || "EDGE"}</strong></div>
        <div className="mono" style={{ fontSize: "10px", color: "var(--muted)" }}>{(selectedItem && selectedItem.id) || rawData.id}</div>
      </div>

      <div>
        <div style={{ color: "var(--muted)", fontSize: "10px" }}>Source</div>
        <button
          type="button"
          onClick={() => onNeighbourClick && onNeighbourClick(data.source || rawData.source)}
          style={{ background: "none", border: "none", color: "var(--accent)", cursor: "pointer", padding: 0 }}
        >
          <span className="mono">{data.source || rawData.source}</span>
        </button>
      </div>

      <div>
        <div style={{ color: "var(--muted)", fontSize: "10px" }}>Target</div>
        <button
          type="button"
          onClick={() => onNeighbourClick && onNeighbourClick(data.target || rawData.target)}
          style={{ background: "none", border: "none", color: "var(--accent)", cursor: "pointer", padding: 0 }}
        >
          <span className="mono">{data.target || rawData.target}</span>
        </button>
      </div>

      {/* Financial amount shown in inspector only */}
      {(data.amount !== undefined || rawData.amount !== undefined) && (
        <div>
          <div style={{ color: "var(--muted)", fontSize: "10px" }}>Transfer Amount</div>
          <div className="mono">
            {data.amount !== undefined ? data.amount : rawData.amount}
          </div>
        </div>
      )}

      {/* FIR Evidence Blocks */}
      {firEvidence.length > 0 && (
        <div>
          <div style={{ color: "var(--muted)", fontSize: "10px", marginBottom: "4px" }}>
            FIR Evidence ({firEvidence.length})
          </div>
          {firEvidence.map((ev, idx) => {
            const highlight = splitExcerptHighlight(ev.excerpt, ev.surface);
            return (
              <div
                key={idx}
                style={{
                  padding: "6px",
                  backgroundColor: "var(--bg)",
                  border: "1px solid var(--border)",
                  marginBottom: "6px",
                  fontSize: "11px",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "2px" }}>
                  <a
                    href={`#/case/${caseId}/evidence/doc/${ev.doc_id}?span=${(ev.char_span || []).join("-")}`}
                    className="mono table-link"
                  >
                    {ev.doc_id}
                  </a>
                  <span className="mono" style={{ fontSize: "10px" }}>
                    [{ (ev.char_span || []).join(", ") }]
                  </span>
                </div>
                <div style={{ lineHeight: "1.4", marginTop: "4px" }}>
                  <span>{highlight.before}</span>
                  <mark style={{ backgroundColor: "var(--accent-weak)", color: "var(--accent)", padding: "1px 2px" }}>
                    {highlight.surface}
                  </mark>
                  <span>{highlight.after}</span>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* CSV Evidence References */}
      {csvEvidence.length > 0 && (
        <div>
          <div style={{ color: "var(--muted)", fontSize: "10px", marginBottom: "4px" }}>
            CSV Evidence References
          </div>
          {csvEvidence.map((cev, idx) => {
            const rows = cev.row_numbers || cev.rows || [];
            const fName = (cev.file || "").includes("bank") ? "bank" : "cdr";
            return (
              <div
                key={idx}
                style={{
                  padding: "6px",
                  backgroundColor: "var(--bg)",
                  border: "1px solid var(--border)",
                  marginBottom: "6px",
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                }}
              >
                <span className="mono">{cev.file || fName} ({rows.length} rows)</span>
                <a
                  href={`#/case/${caseId}/evidence/rows/${fName}?rows=${rows.join(",")}`}
                  className="table-link"
                  style={{ fontSize: "11px" }}
                >
                  View Rows
                </a>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default Graph;
