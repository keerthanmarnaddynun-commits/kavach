import React, { useState, useEffect, useRef, useMemo } from "react";
import cytoscape from "cytoscape";
import fcose from "cytoscape-fcose";
import { request } from "../api/client.js";
import {
  getNodeShape,
  getEdgeWidth,
  getNodeLabelVisibilityMap,
  parseSelectedIdFromUrl,
  parseHighlightIdsFromUrl,
  parseFirstFirFromUrl,
  resolveNodeId,
  computeAdjustedFiltersForNode,
  computeAdjustedFiltersForNodes,
  getSavedHighlightIds,
  saveHighlightIds,
  filterGraphElements,
  splitExcerptHighlight,
  getIsolatedNodeIds,
  getIsolatedNodesControlState,
  formatInspectorError,
  isSelectedItemVisible,
  getMatchingInspectorData,
  formatFirstFirHighlightStatus,
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

  const bg = getComputedToken("--bg");
  const border = getComputedToken("--border");
  const text = getComputedToken("--text");
  const muted = getComputedToken("--muted");
  const accent = getComputedToken("--accent");
  const accentWeak = getComputedToken("--accent-weak");
  const recordAccent = getComputedToken("--record-accent");
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
        "font-size": "11px",
        "font-family": 'ui-monospace, "Cascadia Mono", Consolas, monospace',
        "text-valign": "bottom",
        "text-margin-y": 4,
        "text-outline-width": 2,
        "text-outline-color": bg,
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
        opacity: 0.35,
        "target-arrow-shape": "none",
        "curve-style": "bezier",
        "arrow-scale": 0.8,
      },
    },
    {
      selector: 'edge[label = "TRANSFERRED_FUNDS"], edge[label = "CONTROLS_ACCOUNT"]',
      style: {
        "target-arrow-shape": "triangle",
        "target-arrow-color": muted,
        "arrow-scale": 0.8,
      },
    },
    {
      selector: 'edge[label = "COMMUNICATED_WITH"]',
      style: {
        "curve-style": "haystack",
      },
    },
    {
      selector: "edge:selected",
      style: {
        label: "data(label)",
        "font-size": "10px",
        color: accent,
        opacity: 1,
        "text-background-color": surface,
        "text-background-opacity": 0.9,
        "text-background-padding": 2,
        "line-color": accent,
        "target-arrow-color": accent,
        width: 3,
      },
    },
    {
      selector: "node.highlighted",
      style: {
        "border-color": accent,
        "border-width": 3,
        opacity: 1,
        "min-zoomed-font-size": 0,
        "font-weight": "bold",
      },
    },
    {
      selector: "node.highlighted-record",
      style: {
        "border-color": recordAccent,
        "border-width": 3,
        opacity: 1,
        "min-zoomed-font-size": 0,
        "font-weight": "bold",
      },
    },
    {
      selector: "node.dimmed",
      style: {
        opacity: 0.15,
      },
    },
    {
      selector: "edge.highlighted",
      style: {
        label: "data(label)",
        "font-size": "10px",
        color: accent,
        opacity: 1,
        width: 3,
        "line-color": accent,
        "target-arrow-color": accent,
        "curve-style": "bezier",
        "text-rotation": "autorotate",
        "text-background-color": surface,
        "text-background-opacity": 0.9,
        "text-background-padding": 2,
      },
    },
    {
      selector: "edge.highlighted-record",
      style: {
        label: "data(label)",
        "font-size": "10px",
        color: recordAccent,
        opacity: 1,
        width: 3,
        "line-color": recordAccent,
        "target-arrow-color": recordAccent,
        "curve-style": "bezier",
        "text-rotation": "autorotate",
        "text-background-color": surface,
        "text-background-opacity": 0.9,
        "text-background-padding": 2,
      },
    },
    {
      selector: "edge.dimmed",
      style: {
        opacity: 0.05,
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
  // Visual Fix 2: Leads only default ON at load
  const [leadsOnly, setLeadsOnly] = useState(true);
  // Visual Fix 1: Hide isolated nodes by default
  const [showIsolated, setShowIsolated] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");

  // Selection & Inspector
  const [selectedItem, setSelectedItem] = useState(null); // { type: 'node' | 'edge', id: string, data: object }
  const selectedItemRef = useRef(selectedItem);
  selectedItemRef.current = selectedItem;
  const lastAppliedUrlSelectRef = useRef(null);
  const [isHighlighted, setIsHighlighted] = useState(false);
  const [highlightLegend, setHighlightLegend] = useState(null);
  const [highlightStatus, setHighlightStatus] = useState(null);
  const lastAppliedHighlightRef = useRef(null);
  const lastSeenRouteRef = useRef(null);
  const highlightClearedRef = useRef(false);
  const [inspectorData, setInspectorData] = useState(null);
  const [inspectorLoading, setInspectorLoading] = useState(false);
  const [inspectorCollapsed, setInspectorCollapsed] = useState(false);

  // Load Graph elements and Leads
  useEffect(() => {
    if (!caseId) return;
    lastAppliedUrlSelectRef.current = null;
    lastAppliedHighlightRef.current = null;
    highlightClearedRef.current = false;
    setIsHighlighted(false);
    setHighlightStatus(null);
    setSelectedItem(null);
    setInspectorData(null);
    setInspectorCollapsed(false);
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

  // Compute total raw isolated nodes across full unfiltered graph
  const totalRawIsolatedCount = useMemo(() => {
    if (!rawElements || !rawElements.nodes) return 0;
    return getIsolatedNodeIds(rawElements.nodes, rawElements.edges).length;
  }, [rawElements]);

  // Compute filtered elements (accounting for leadsOnly, nodeTypes, relations, and isolated nodes)
  const { filteredElements, isolatedCount } = useMemo(() => {
    if (!rawElements) return { filteredElements: { nodes: [], edges: [] }, isolatedCount: 0 };
    const base = filterGraphElements(rawElements, nodeTypes, relations, leadsOnly, topLeadIds);

    const isolatedIds = new Set(getIsolatedNodeIds(base.nodes, base.edges));
    const count = isolatedIds.size;

    if (!showIsolated && count > 0) {
      const activeNodes = base.nodes.filter((n) => !isolatedIds.has(n.data && n.data.id));
      return {
        filteredElements: { nodes: activeNodes, edges: base.edges },
        isolatedCount: count,
      };
    }

    return { filteredElements: base, isolatedCount: count };
  }, [rawElements, nodeTypes, relations, leadsOnly, topLeadIds, showIsolated]);

  // Compute isolated nodes control visibility and text (Report 1)
  const isolatedControlState = useMemo(() => {
    return getIsolatedNodesControlState(
      isolatedCount,
      showIsolated,
      leadsOnly,
      totalRawIsolatedCount
    );
  }, [isolatedCount, showIsolated, leadsOnly, totalRawIsolatedCount]);

  // Central helper to update selection and ensure inspector opens expanded
  const updateSelection = (item) => {
    selectedItemRef.current = item;
    setSelectedItem(item);
    if (item) {
      setInspectorCollapsed(false);
    }
  };

  const selectNode = (node) => {
    if (!node) return;
    const id = typeof node.id === "function" ? node.id() : node.id;
    const data = typeof node.data === "function" ? node.data() : (node.data || {});
    updateSelection({ type: "node", id, data });
  };

  const selectEdge = (edge) => {
    if (!edge) return;
    const id = typeof edge.id === "function" ? edge.id() : edge.id;
    const data = typeof edge.data === "function" ? edge.data() : (edge.data || {});
    updateSelection({ type: "edge", id, data });
  };

  // Initialise single Cytoscape instance for page lifetime
  useEffect(() => {
    if (!containerRef.current) return;

    const cy = cytoscape({
      container: containerRef.current,
      elements: [],
      style: getCytoscapeStyles(),
      wheelSensitivity: 0.3,
    });

    cyRef.current = cy;
    if (typeof window !== "undefined") {
      window.cy = cy;
    }

    // Event listeners bound ONCE to lifetime instance
    cy.on("tap", "node", (evt) => {
      selectNode(evt.target);
    });

    cy.on("tap", "edge", (evt) => {
      selectEdge(evt.target);
    });

    cy.on("tap", (evt) => {
      if (evt.target === cy) {
        updateSelection(null);
      }
    });

    return () => {
      cy.destroy();
      cyRef.current = null;
      if (typeof window !== "undefined" && window.cy === cy) {
        window.cy = null;
      }
    };
  }, []);

  // Update Cytoscape elements in-place on filter / leads changes without destroying instance
  useEffect(() => {
    if (!cyRef.current || loading || !rawElements) return;
    const cy = cyRef.current;

    const topSet = new Set(topLeadIds);
    const targetNodes = filteredElements.nodes.map((n) => {
      const d = n.data || {};
      return {
        group: "nodes",
        data: {
          ...d,
          shape: getNodeShape(d.type),
          isTopLead: topSet.has(d.id),
        },
      };
    });

    const targetEdges = filteredElements.edges.map((e) => {
      const d = e.data || {};
      return {
        group: "edges",
        data: {
          ...d,
          edgeWidth: getEdgeWidth(d.count),
        },
      };
    });

    const targetElements = [...targetNodes, ...targetEdges];
    const targetIds = new Set(targetElements.map((el) => el.data.id));

    cy.batch(() => {
      // Remove elements no longer visible
      const toRemove = cy.elements().filter((el) => !targetIds.has(el.id()));
      if (toRemove.length > 0) {
        cy.remove(toRemove);
      }

      // Add new elements or update data
      const toAdd = [];
      for (const el of targetElements) {
        const existing = cy.getElementById(el.data.id);
        if (existing.length === 0) {
          toAdd.push(el);
        } else {
          existing.data(el.data);
        }
      }
      if (toAdd.length > 0) {
        cy.add(toAdd);
      }
    });

    // Run layout
    runLayout(cy);

    // Keep current selection if visible
    if (selectedItemRef.current) {
      if (targetIds.has(selectedItemRef.current.id)) {
        const target = cy.getElementById(selectedItemRef.current.id);
        if (target.length > 0) {
          target.select();
        }
      }
    }
  }, [loading, filteredElements, topLeadIds]);

  // Auto-adjust filters so selected or highlighted nodes become visible
  useEffect(() => {
    if (!rawElements || !rawElements.nodes) return;
    const hashOrRoute = route || (typeof window !== "undefined" ? window.location.hash : "");
    const selectId = parseSelectedIdFromUrl(hashOrRoute);
    const hlFromUrl = parseHighlightIdsFromUrl(hashOrRoute);
    const hlIds = hlFromUrl.length > 0 ? hlFromUrl : getSavedHighlightIds();

    // 1. If selectId is present, ensure target node is visible
    if (selectId) {
      const resolvedSelectId = resolveNodeId(rawElements.nodes, selectId);
      if (resolvedSelectId) {
        const adj = computeAdjustedFiltersForNode({
          targetNodeId: resolvedSelectId,
          rawNodes: rawElements.nodes,
          rawEdges: rawElements.edges || [],
          currentLeadsOnly: leadsOnly,
          currentShowIsolated: showIsolated,
          currentNodeTypes: nodeTypes,
        });
        if (adj.changed) {
          if (adj.leadsOnly !== leadsOnly) setLeadsOnly(adj.leadsOnly);
          if (adj.showIsolated !== showIsolated) setShowIsolated(adj.showIsolated);
          if (adj.nodeTypes !== nodeTypes) setNodeTypes(adj.nodeTypes);
        }
      }
    }

    // 2. Also ensure any highlighted nodes are visible
    if (hlIds.length > 0) {
      const idSet = new Set(hlIds);
      const rawNodes = rawElements.nodes || [];
      const matchedHlNodes = rawNodes.filter((n) => idSet.has(n.data && n.data.id));
      if (matchedHlNodes.length > 0) {
        if (leadsOnly) {
          const topSet = new Set(topLeadIds);
          if (matchedHlNodes.some((n) => !topSet.has(n.data && n.data.id))) {
            setLeadsOnly(false);
          }
        }
        let typesChanged = false;
        const updatedTypes = { ...nodeTypes };
        for (const n of matchedHlNodes) {
          const t = n.data && n.data.type;
          if (t && updatedTypes[t] === false) {
            updatedTypes[t] = true;
            typesChanged = true;
          }
        }
        if (typesChanged) {
          setNodeTypes(updatedTypes);
        }
        if (!showIsolated) {
          const isolatedIds = new Set(getIsolatedNodeIds(rawNodes, rawElements.edges || []));
          if (matchedHlNodes.some((n) => isolatedIds.has(n.data && n.data.id))) {
            setShowIsolated(true);
          }
        }
      }
    }
  }, [route, rawElements, topLeadIds, leadsOnly, showIsolated, nodeTypes]);

  // Synchronize URL selection and highlight to Cytoscape instance
  useEffect(() => {
    if (!cyRef.current || loading || !rawElements) return;
    const cy = cyRef.current;
    const hashOrRoute = route || (typeof window !== "undefined" ? window.location.hash : "");

    // Reset clear state if route has changed
    if (hashOrRoute !== lastSeenRouteRef.current) {
      lastSeenRouteRef.current = hashOrRoute;
      highlightClearedRef.current = false;
    }

    const selectId = parseSelectedIdFromUrl(hashOrRoute);
    const hlFromUrl = parseHighlightIdsFromUrl(hashOrRoute);
    const hlIds = hlFromUrl.length > 0 ? hlFromUrl : getSavedHighlightIds();

    // 1. Apply Highlighting if hlIds present and not manually cleared
    if (hlIds && hlIds.length > 0 && !highlightClearedRef.current) {
      const hlKey = hlIds.join(",");
      const hlSet = new Set(hlIds);
      cy.batch(() => {
        cy.nodes().forEach((n) => {
          if (hlSet.has(n.id())) {
            n.addClass("highlighted").removeClass("dimmed");
          } else {
            n.addClass("dimmed").removeClass("highlighted");
          }
        });
        cy.edges().forEach((e) => {
          const src = e.data("source");
          const tgt = e.data("target");
          if (hlSet.has(e.id()) || (hlSet.has(src) && hlSet.has(tgt))) {
            e.addClass("highlighted").removeClass("dimmed");
          } else {
            e.addClass("dimmed").removeClass("highlighted");
          }
        });
      });
      setIsHighlighted(true);
      lastAppliedHighlightRef.current = hlKey;
    }

    // 2. Apply Node Selection if selectId present
    if (selectId && rawElements && rawElements.nodes) {
      const resolvedSelectId = resolveNodeId(rawElements.nodes, selectId) || selectId;
      const targetNode = cy.getElementById(resolvedSelectId);
      if (targetNode.length > 0) {
        cy.nodes().unselect();
        cy.edges().unselect();
        targetNode.select();
        cy.center(targetNode);
        selectNode(targetNode);
        setInspectorCollapsed(false);
        lastAppliedUrlSelectRef.current = selectId;
      }
    }
  }, [route, loading, rawElements, filteredElements]);

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

  // Resize cytoscape canvas whenever inspector collapses/expands or sidebar collapses/expands
  useEffect(() => {
    if (cyRef.current) {
      cyRef.current.resize();
    }
  }, [inspectorCollapsed]);

  useEffect(() => {
    function handleResize() {
      if (cyRef.current) {
        cyRef.current.resize();
      }
    }
    window.addEventListener("resize", handleResize);

    let ro = null;
    if (typeof ResizeObserver !== "undefined" && containerRef.current) {
      ro = new ResizeObserver(() => {
        if (cyRef.current) {
          cyRef.current.resize();
        }
      });
      ro.observe(containerRef.current);
    }

    return () => {
      window.removeEventListener("resize", handleResize);
      if (ro) ro.disconnect();
    };
  }, []);

  function runLayout(cyInstance) {
    const cy = cyInstance || cyRef.current;
    if (!cy) return;

    setLayoutRunning(true);
    // Visual Fix 3: fcose options
    const layout = cy.layout({
      name: "fcose",
      nodeDimensionsIncludeLabels: true,
      animate: false,
      randomize: true,
      quality: "default",
      nodeRepulsion: 20000,
      idealEdgeLength: 120,
      edgeElasticity: 0.2,
      nodeSeparation: 150,
      numIter: 2500,
      packComponents: true,
      fit: true,
      padding: 30,
    });

    layout.one("layoutstop", () => {
      setLayoutRunning(false);
      // Visual Fix 1: Call fit with 30 px padding after every layout
      cy.fit(undefined, 30);
    });

    layout.run();
  }

  // Handle Inspector Loading when selection changes
  useEffect(() => {
    if (!selectedItem || !caseId) {
      setInspectorData(null);
      return;
    }

    let cancelled = false;
    setInspectorLoading(true);
    const endpoint = selectedItem.type === "node"
      ? `/cases/${caseId}/nodes/${selectedItem.id}`
      : `/cases/${caseId}/edges/${selectedItem.id}`;

    request(endpoint)
      .then((data) => {
        if (!cancelled) {
          setInspectorData(data);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setInspectorData({ error: formatInspectorError(err) });
        }
      })
      .finally(() => {
        if (!cancelled) {
          setInspectorLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
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
      setInspectorCollapsed(false);
    }
  }

  // Handle selecting a neighbour node
  function handleNeighbourClick(neighbourId) {
    if (!cyRef.current) return;
    const resolved = (rawElements && rawElements.nodes ? resolveNodeId(rawElements.nodes, neighbourId) : null) || neighbourId;
    if (rawElements && rawElements.nodes) {
      const adj = computeAdjustedFiltersForNode({
        targetNodeId: resolved,
        rawNodes: rawElements.nodes,
        rawEdges: rawElements.edges || [],
        currentLeadsOnly: leadsOnly,
        currentShowIsolated: showIsolated,
        currentNodeTypes: nodeTypes,
      });
      if (adj.changed) {
        if (adj.leadsOnly !== leadsOnly) setLeadsOnly(adj.leadsOnly);
        if (adj.showIsolated !== showIsolated) setShowIsolated(adj.showIsolated);
        if (adj.nodeTypes !== nodeTypes) setNodeTypes(adj.nodeTypes);
      }
    }
    const target = cyRef.current.getElementById(resolved);
    if (target.length > 0) {
      cyRef.current.nodes().unselect();
      target.select();
      cyRef.current.center(target);
      setSelectedItem({ type: "node", id: target.id(), data: target.data() });
      setInspectorCollapsed(false);
    }
  }

  const applyEvidenceHighlight = (nodeId, firstFir, firstRecord) => {
    if (!cyRef.current || !nodeId) return;
    const cy = cyRef.current;

    const firGroup = (firstFir && firstFir.first_fir_id && Array.isArray(firstFir.related_entities))
      ? firstFir.related_entities.map((e) => e.id)
      : [];
    const firSet = new Set(firGroup);

    const recordCounterpartIds = [];
    if (firstRecord && Array.isArray(firstRecord.counterparts)) {
      for (const cp of firstRecord.counterparts) {
        const resolved = (rawElements && rawElements.nodes ? resolveNodeId(rawElements.nodes, cp) : null) || cp;
        recordCounterpartIds.push(resolved);
      }
    }
    const recordSet = new Set(recordCounterpartIds);

    const undimmedNodeIds = new Set([nodeId, ...firSet, ...recordSet]);

    cy.batch(() => {
      cy.nodes().forEach((n) => {
        const nid = n.id();
        if (!undimmedNodeIds.has(nid)) {
          n.addClass("dimmed").removeClass("highlighted highlighted-record");
        } else if (nid === nodeId) {
          n.addClass("highlighted").removeClass("dimmed highlighted-record");
        } else if (firSet.has(nid)) {
          n.addClass("highlighted").removeClass("dimmed highlighted-record");
        } else if (recordSet.has(nid)) {
          n.addClass("highlighted-record").removeClass("dimmed highlighted");
        }
      });

      cy.edges().forEach((e) => {
        const src = e.data("source");
        const tgt = e.data("target");
        const connectsFir =
          (src === nodeId && firSet.has(tgt)) ||
          (tgt === nodeId && firSet.has(src));
        const connectsRecord =
          (src === nodeId && recordSet.has(tgt)) ||
          (tgt === nodeId && recordSet.has(src)) ||
          (recordSet.has(src) && recordSet.has(tgt));

        if (connectsFir) {
          e.addClass("highlighted").removeClass("dimmed highlighted-record");
        } else if (connectsRecord) {
          e.addClass("highlighted-record").removeClass("dimmed highlighted");
        } else {
          e.addClass("dimmed").removeClass("highlighted highlighted-record");
        }
      });
    });

    const highlightedNodes = cy.nodes(".highlighted, .highlighted-record");
    if (highlightedNodes.length > 1) {
      cy.fit(highlightedNodes, 60);
    } else if (highlightedNodes.length === 1) {
      cy.center(highlightedNodes);
    }

    setIsHighlighted(true);
    setHighlightLegend({
      hasFir: Boolean(firstFir && firstFir.first_fir_id && firGroup.length > 0),
      hasRecord: Boolean(firstRecord && firstRecord.timestamp && recordCounterpartIds.length > 0),
      recordTimestamp: firstRecord ? firstRecord.timestamp : null,
    });

    const statusText = formatFirstFirHighlightStatus(firstFir);
    setHighlightStatus(statusText);
  };

  // Ensure counterpart nodes from first_record and related entities from first_fir are made visible
  useEffect(() => {
    if (!inspectorData || !rawElements || !rawElements.nodes) return;
    const targetNodeIds = [];
    const firstRecord = inspectorData.first_record;
    if (firstRecord && Array.isArray(firstRecord.counterparts)) {
      for (const cp of firstRecord.counterparts) {
        targetNodeIds.push(resolveNodeId(rawElements.nodes, cp) || cp);
      }
    }
    const firstFir = inspectorData.first_fir;
    if (firstFir && Array.isArray(firstFir.related_entities)) {
      for (const rel of firstFir.related_entities) {
        if (rel.id) {
          targetNodeIds.push(resolveNodeId(rawElements.nodes, rel.id) || rel.id);
        }
      }
    }
    if (targetNodeIds.length === 0) return;

    const adj = computeAdjustedFiltersForNodes({
      targetNodeIds,
      rawNodes: rawElements.nodes,
      rawEdges: rawElements.edges || [],
      currentLeadsOnly: leadsOnly,
      currentShowIsolated: showIsolated,
      currentNodeTypes: nodeTypes,
    });
    if (adj.changed) {
      if (adj.leadsOnly !== leadsOnly) setLeadsOnly(adj.leadsOnly);
      if (adj.showIsolated !== showIsolated) setShowIsolated(adj.showIsolated);
      if (adj.nodeTypes !== nodeTypes) setNodeTypes(adj.nodeTypes);
    }
  }, [inspectorData, rawElements, leadsOnly, showIsolated, nodeTypes]);

  const lastAppliedEvidenceRef = useRef(null);
  useEffect(() => {
    if (!inspectorData || !selectedItem || selectedItem.type !== "node") return;
    const hashOrRoute = route || (typeof window !== "undefined" ? window.location.hash : "");
    if (!parseFirstFirFromUrl(hashOrRoute)) return;
    if (highlightClearedRef.current) return;
    const firstFir = inspectorData.first_fir;
    const firstRecord = inspectorData.first_record;
    const key = `${selectedItem.id}:${firstFir?.first_fir_id || "nofir"}:${firstRecord?.timestamp || "norecord"}:${filteredElements.nodes.length}`;
    if (lastAppliedEvidenceRef.current !== key) {
      lastAppliedEvidenceRef.current = key;
      applyEvidenceHighlight(selectedItem.id, firstFir, firstRecord);
    }
  }, [inspectorData, selectedItem, route, filteredElements]);

  const handleShowEvidenceHighlight = () => {
    if (selectedItem && selectedItem.type === "node" && inspectorData) {
      highlightClearedRef.current = false;
      applyEvidenceHighlight(selectedItem.id, inspectorData.first_fir, inspectorData.first_record);
    }
  };

  function handleClearHighlight() {
    if (cyRef.current) {
      cyRef.current.batch(() => {
        cyRef.current.elements().removeClass("highlighted highlighted-record dimmed");
      });
    }
    saveHighlightIds(null);
    setIsHighlighted(false);
    setHighlightLegend(null);
    setHighlightStatus(null);
    highlightClearedRef.current = true;
    lastAppliedHighlightRef.current = null;
    lastAppliedEvidenceRef.current = null;
  }

  return (
    <div className="graph-page" style={{ display: "flex", flexDirection: "column", height: "100%", width: "100%", minWidth: 0, overflow: "hidden" }}>
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

        {/* Visual Fix 2: Leads Only Toggle with one-click full graph */}
        <label style={{ display: "flex", alignItems: "center", gap: "4px", cursor: "pointer", marginLeft: "6px" }}>
          <input
            type="checkbox"
            checked={leadsOnly}
            onChange={(e) => setLeadsOnly(e.target.checked)}
          />
          <strong>Leads only (Top 10 + Neighbours)</strong>
        </label>

        {/* Visual Fix 1: Isolated nodes control */}
        {isolatedControlState.visible && (
          isolatedControlState.isButton ? (
            <button
              type="button"
              onClick={() => setShowIsolated(!showIsolated)}
              style={{ fontSize: "11px", padding: "2px 8px" }}
            >
              {isolatedControlState.text}
            </button>
          ) : (
            <span style={{ fontSize: "11px", color: "var(--muted)", padding: "2px 4px" }}>
              {isolatedControlState.text}
            </span>
          )
        )}

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
        <div style={{ display: "flex", gap: "6px", marginLeft: "auto", alignItems: "center" }}>
          {isHighlighted && (
            <div style={{ display: "flex", gap: "8px", alignItems: "center", marginRight: "4px" }}>
              {highlightLegend?.hasFir && (
                <span style={{ display: "inline-flex", alignItems: "center", gap: "4px", fontSize: "11px" }}>
                  <span style={{ width: "10px", height: "10px", backgroundColor: "var(--accent)", borderRadius: "2px", display: "inline-block" }} />
                  <span>First FIR mention</span>
                </span>
              )}
              {highlightLegend?.hasRecord && (
                <span style={{ display: "inline-flex", alignItems: "center", gap: "4px", fontSize: "11px" }}>
                  <span style={{ width: "10px", height: "10px", backgroundColor: "var(--record-accent)", borderRadius: "2px", display: "inline-block" }} />
                  <span>
                    {highlightLegend.recordTimestamp
                      ? `First seen in records: ${highlightLegend.recordTimestamp}`
                      : "First seen in records"}
                  </span>
                </span>
              )}
              {(!highlightLegend || (!highlightLegend.hasFir && !highlightLegend.hasRecord)) && (
                <span style={{ display: "inline-flex", alignItems: "center", gap: "4px", fontSize: "11px" }}>
                  <span style={{ width: "10px", height: "10px", backgroundColor: "var(--accent)", borderRadius: "2px", display: "inline-block" }} />
                  <span>Highlighted path</span>
                </span>
              )}
              <button
                type="button"
                onClick={handleClearHighlight}
                style={{
                  fontSize: "11px",
                  padding: "2px 8px",
                  backgroundColor: "var(--accent-weak)",
                  color: "var(--accent)",
                  borderColor: "var(--accent)",
                  fontWeight: "600",
                  cursor: "pointer",
                }}
              >
                Clear highlight
              </button>
            </div>
          )}
          <button type="button" onClick={() => runLayout()} disabled={layoutRunning}>
            Re-layout
          </button>
          <button type="button" onClick={() => cyRef.current && cyRef.current.fit(undefined, 30)}>
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
          {/* Visual Fix 2: Large view line if > 150 nodes */}
          {filteredElements.nodes.length > 150 && (
            <span style={{ marginLeft: "10px", color: "var(--text)" }}>
              Large view: labels shown only for leads and the selection
            </span>
          )}
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
      <div style={{ display: "flex", flex: 1, minWidth: 0, minHeight: 0, position: "relative", overflow: "hidden" }}>
        {/* Cytoscape Canvas */}
        <div
          ref={containerRef}
          style={{
            flex: 1,
            minWidth: 0,
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
        <GraphInspectorAside
          selectedItem={selectedItem}
          inspectorCollapsed={inspectorCollapsed}
          setInspectorCollapsed={setInspectorCollapsed}
          inspectorLoading={inspectorLoading}
          inspectorData={inspectorData}
          caseId={caseId}
          onNeighbourClick={handleNeighbourClick}
          onShowFirstFir={handleShowEvidenceHighlight}
          onShowEvidenceHighlight={handleShowEvidenceHighlight}
          highlightStatus={highlightStatus}
          isHighlighted={isHighlighted}
        />
      </div>
    </div>
  );
}

export function GraphInspectorAside({
  selectedItem,
  inspectorCollapsed,
  setInspectorCollapsed,
  inspectorLoading,
  inspectorData,
  caseId,
  onNeighbourClick,
  onShowFirstFir,
  onShowEvidenceHighlight,
  highlightStatus = null,
  isHighlighted = false,
}) {
  if (!selectedItem) return null;

  return (
    <aside
      className={`inspector-pane ${inspectorCollapsed ? "collapsed" : ""}`}
      style={{
        width: inspectorCollapsed ? "36px" : "340px",
        minWidth: inspectorCollapsed ? "36px" : "340px",
        maxWidth: inspectorCollapsed ? "36px" : "340px",
        flexShrink: 0,
        borderLeft: "1px solid var(--border)",
        backgroundColor: "var(--surface)",
        overflowY: inspectorCollapsed ? "visible" : "auto",
        overflowX: "hidden",
        padding: inspectorCollapsed ? "8px 4px" : "12px",
        fontSize: "12px",
        display: "flex",
        flexDirection: "column",
        boxSizing: "border-box",
        position: "relative",
        zIndex: 10,
        pointerEvents: "auto",
        cursor: inspectorCollapsed ? "pointer" : "default",
      }}
      onClick={() => {
        if (inspectorCollapsed && setInspectorCollapsed) {
          setInspectorCollapsed(false);
        }
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: inspectorCollapsed ? "center" : "space-between",
          alignItems: "center",
          marginBottom: "8px",
          width: "100%",
        }}
      >
        {!inspectorCollapsed && (
          <strong>{selectedItem.type === "node" ? "Node Inspector" : "Edge Inspector"}</strong>
        )}
        <button
          type="button"
          aria-label={inspectorCollapsed ? "Expand Inspector" : "Collapse Inspector"}
          title={inspectorCollapsed ? "Expand Inspector" : "Collapse Inspector"}
          onClick={(e) => {
            e.stopPropagation();
            if (setInspectorCollapsed) {
              setInspectorCollapsed(!inspectorCollapsed);
            }
          }}
          style={{
            fontSize: "12px",
            padding: "2px 6px",
            cursor: "pointer",
            minWidth: "24px",
            textAlign: "center",
            zIndex: 20,
            pointerEvents: "auto",
          }}
        >
          {inspectorCollapsed ? "◀" : "▶"}
        </button>
      </div>

      {!inspectorCollapsed && (
        <div>
          {inspectorLoading ? (
            <div>Loading details...</div>
          ) : inspectorData && inspectorData.error ? (
            <div className="error-text" style={{ padding: "8px", color: "var(--danger)" }}>
              {inspectorData.error}
            </div>
          ) : (
            <InspectorContent
              caseId={caseId}
              itemType={selectedItem.type}
              selectedItem={selectedItem}
              data={inspectorData || {}}
              onNeighbourClick={onNeighbourClick}
              onShowFirstFir={onShowFirstFir}
              onShowEvidenceHighlight={onShowEvidenceHighlight}
              highlightStatus={highlightStatus}
              isHighlighted={isHighlighted}
            />
          )}
        </div>
      )}
    </aside>
  );
}

function InspectorContent({
  caseId,
  itemType,
  selectedItem,
  data,
  onNeighbourClick,
  onShowFirstFir,
  onShowEvidenceHighlight,
  highlightStatus = null,
  isHighlighted = false,
}) {
  const matchingData = getMatchingInspectorData(data, selectedItem?.id);
  if (itemType === "node") {
    return (
      <NodeInspectorView
        caseId={caseId}
        selectedItem={selectedItem}
        data={matchingData}
        onNeighbourClick={onNeighbourClick}
        onShowFirstFir={onShowFirstFir}
        onShowEvidenceHighlight={onShowEvidenceHighlight}
        highlightStatus={highlightStatus}
        isHighlighted={isHighlighted}
      />
    );
  }
  return (
    <EdgeInspectorView
      caseId={caseId}
      selectedItem={selectedItem}
      data={matchingData}
      onNeighbourClick={onNeighbourClick}
    />
  );
}

export function NodeInspectorView({
  caseId,
  selectedItem,
  data = {},
  onNeighbourClick,
  onShowFirstFir,
  onShowEvidenceHighlight,
  highlightStatus = null,
  isHighlighted = false,
}) {
  const rawData = (selectedItem && selectedItem.data) || {};
  const firEvidence = data.fir_evidence || [];
  const csvEvidence = data.csv_evidence || [];
  const neighbours = data.neighbours || [];
  const firstFir = data.first_fir;
  const firstRecord = data.first_record;

  const hasFir = Boolean(firstFir && firstFir.first_fir_id);
  const hasRecord = Boolean(firstRecord && firstRecord.timestamp);
  const relatedCount = Array.isArray(firstFir?.related_entities) ? firstFir.related_entities.length : 0;
  const isFirHighlightActive = isHighlighted && Boolean(highlightStatus);

  // Visual Fix 6: Extractor confidence calculation
  let confidence = "not recorded";
  if (typeof rawData.ai_confidence === "number" && rawData.ai_confidence > 0) {
    confidence = (rawData.ai_confidence * 100).toFixed(0) + "%";
  } else if (firEvidence.length > 0) {
    const confs = firEvidence
      .map((ev) => ev.ai_confidence)
      .filter((c) => typeof c === "number" && c > 0);
    if (confs.length > 0) {
      const highest = Math.max(...confs);
      confidence = `${(highest * 100).toFixed(0)}% (highest extractor confidence in evidence)`;
    }
  }

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

      {/* First FIR Mention & First Seen in Records */}
      {!hasFir && !hasRecord ? (
        <div>
          <div style={{ color: "var(--muted)", fontSize: "10px", marginBottom: "4px" }}>
            First FIR Mention & Activity
          </div>
          <div
            style={{
              padding: "8px",
              backgroundColor: "var(--bg)",
              border: "1px solid var(--border)",
              fontSize: "11px",
              color: "var(--muted)",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            <span>Not mentioned in any FIR and no activity in the records</span>
            <button
              type="button"
              disabled
              style={{
                fontSize: "10px",
                padding: "2px 6px",
                opacity: 0.6,
                cursor: "not-allowed",
              }}
              title="Not mentioned in any FIR"
            >
              Not mentioned in any FIR
            </button>
          </div>
        </div>
      ) : (
        <>
          {/* First FIR Mention */}
      <div>
        <div style={{ color: "var(--muted)", fontSize: "10px", marginBottom: "4px" }}>
          First FIR Mention
        </div>
        {hasFir ? (
          <div
            style={{
              padding: "8px",
              backgroundColor: "var(--bg)",
              border: "1px solid var(--border)",
              fontSize: "11px",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
              <span>
                First FIR mention:{" "}
                <a
                  href={`#/case/${caseId}/evidence/doc/${firstFir.first_fir_id}`}
                  className="mono table-link"
                >
                  {firstFir.first_fir_id.startsWith("FIR") ? firstFir.first_fir_id : `FIR ${firstFir.first_fir_id}`}
                </a>
                {firstFir.date && (
                  <span style={{ color: "var(--muted)", marginLeft: "4px" }}>
                    ({firstFir.date})
                  </span>
                )}
              </span>
              {relatedCount === 0 ? (
                <button
                  type="button"
                  disabled
                  style={{
                    fontSize: "10px",
                    padding: "2px 6px",
                    opacity: 0.6,
                    cursor: "not-allowed",
                  }}
                  title="No linked entities in this FIR"
                >
                  No linked entities
                </button>
              ) : isFirHighlightActive ? (
                <button
                  type="button"
                  disabled
                  style={{
                    fontSize: "10px",
                    padding: "2px 6px",
                    backgroundColor: "var(--accent-weak)",
                    color: "var(--accent)",
                    border: "1px solid var(--accent)",
                    fontWeight: "600",
                    cursor: "default",
                  }}
                >
                  Highlight active
                </button>
              ) : (
                (onShowEvidenceHighlight || onShowFirstFir) && (
                  <button
                    type="button"
                    onClick={onShowEvidenceHighlight || onShowFirstFir}
                    style={{
                      fontSize: "10px",
                      padding: "2px 6px",
                      cursor: "pointer",
                    }}
                  >
                    Show first FIR mention
                  </button>
                )
              )}
            </div>

            {/* One-line status in the panel */}
            {isFirHighlightActive && highlightStatus && (
              <div
                style={{
                  fontSize: "11px",
                  color: "var(--accent)",
                  fontWeight: "600",
                  marginBottom: "6px",
                }}
              >
                {highlightStatus}
              </div>
            )}

            {/* Group (a) Related Entities */}
            {firstFir.related_entities && firstFir.related_entities.length > 0 && (
              <div style={{ marginTop: "6px" }}>
                <div style={{ color: "var(--muted)", fontSize: "10px", marginBottom: "2px" }}>
                  Related in this FIR:
                </div>
                <ul style={{ margin: 0, paddingLeft: "16px" }}>
                  {firstFir.related_entities.map((relEnt, idx) => (
                    <li key={idx} style={{ marginBottom: "2px" }}>
                      {onNeighbourClick ? (
                        <button
                          type="button"
                          className="table-link"
                          style={{
                            background: "none",
                            border: "none",
                            padding: 0,
                            cursor: "pointer",
                            textAlign: "left",
                            fontSize: "11px",
                          }}
                          onClick={() => onNeighbourClick(relEnt.id)}
                        >
                          <span className="mono">{relEnt.label || relEnt.id}</span>
                        </button>
                      ) : (
                        <span className="mono">{relEnt.label || relEnt.id}</span>
                      )}
                      <span style={{ color: "var(--muted)", marginLeft: "4px" }}>
                        ({relEnt.relation})
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Group (b) Other Entities (collapsed by default) */}
            {firstFir.other_entities && firstFir.other_entities.length > 0 && (
              <details style={{ marginTop: "6px" }}>
                <summary style={{ cursor: "pointer", color: "var(--muted)", fontSize: "10px" }}>
                  {`Also mentioned in this FIR (${firstFir.other_entities.length})`}
                </summary>
                <ul style={{ margin: "4px 0 0 0", paddingLeft: "16px", fontSize: "10px" }}>
                  {firstFir.other_entities.map((oth, idx) => (
                    <li key={idx} style={{ marginBottom: "2px" }}>
                      {onNeighbourClick ? (
                        <button
                          type="button"
                          className="table-link"
                          style={{
                            background: "none",
                            border: "none",
                            padding: 0,
                            cursor: "pointer",
                            textAlign: "left",
                            fontSize: "10px",
                          }}
                          onClick={() => onNeighbourClick(oth.id)}
                        >
                          <span className="mono">{oth.label || oth.id}</span>
                        </button>
                      ) : (
                        <span className="mono">{oth.label || oth.id}</span>
                      )}
                      <span style={{ color: "var(--muted)", marginLeft: "4px" }}>
                        ({oth.type})
                      </span>
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </div>
        ) : (
          <div
            style={{
              padding: "8px",
              backgroundColor: "var(--bg)",
              border: "1px solid var(--border)",
              fontSize: "11px",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            <span style={{ color: "var(--muted)" }}>Not mentioned in any FIR</span>
            <button
              type="button"
              disabled
              style={{
                fontSize: "10px",
                padding: "2px 6px",
                opacity: 0.6,
                cursor: "not-allowed",
              }}
              title="Not mentioned in any FIR"
            >
              Not mentioned in any FIR
            </button>
          </div>
        )}
      </div>

      {/* First Seen in Records */}
      <div>
        <div style={{ color: "var(--muted)", fontSize: "10px", marginBottom: "4px" }}>
          First seen in records
        </div>
        {hasRecord ? (
          <div
            style={{
              padding: "8px",
              backgroundColor: "var(--bg)",
              border: "1px solid var(--border)",
              fontSize: "11px",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
              <span>
                First seen in records:{" "}
                <span className="mono" style={{ fontWeight: "600" }}>
                  {firstRecord.timestamp}
                </span>
              </span>
              {(onShowEvidenceHighlight || onShowFirstFir) && (
                <button
                  type="button"
                  disabled={isHighlighted}
                  onClick={onShowEvidenceHighlight || onShowFirstFir}
                  style={{
                    fontSize: "10px",
                    padding: "2px 6px",
                    cursor: isHighlighted ? "default" : "pointer",
                    opacity: isHighlighted ? 0.7 : 1,
                  }}
                >
                  {isHighlighted ? "Highlight active" : "Highlight in graph"}
                </button>
              )}
            </div>

                {firstRecord.counterparts && firstRecord.counterparts.length > 0 && (
                  <div style={{ marginTop: "6px" }}>
                    <div style={{ color: "var(--muted)", fontSize: "10px", marginBottom: "2px" }}>
                      Counterparts:
                    </div>
                    <ul style={{ margin: 0, paddingLeft: "16px" }}>
                      {firstRecord.counterparts.map((cp, idx) => (
                        <li key={idx} style={{ marginBottom: "2px" }}>
                          <span className="mono">{cp}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                <div style={{ marginTop: "8px" }}>
                  {(() => {
                    const rawVal = rawData.value || rawData.label || (selectedItem && selectedItem.id) || "";
                    const cleanId = String(rawVal).replace(/^(PHONE|ACCOUNT|IMEI|PERSON|VEHICLE):/, "");
                    const file = firstRecord.file || "cdr";
                    const rowsParam = (firstRecord.rows || []).join(",");
                    return (
                      <a
                        href={`#/case/${caseId}/evidence/rows/${file}?rows=${rowsParam}&highlight=${encodeURIComponent(cleanId)}`}
                        className="mono table-link"
                      >
                        View row evidence ({(firstRecord.rows || []).length} {firstRecord.rows?.length === 1 ? "row" : "rows"})
                      </a>
                    );
                  })()}
                </div>
              </div>
            ) : (
              <div style={{ fontSize: "11px", color: "var(--muted)" }}>
                No activity in the records
              </div>
            )}
          </div>
        </>
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

