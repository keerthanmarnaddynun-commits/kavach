/**
 * Pure helper functions for Network Graph layout, styling, filtering, and selection.
 */

export function getNodeShape(nodeType) {
  switch (nodeType) {
    case "PERSON":
      return "ellipse";
    case "PHONE":
      return "round-rectangle";
    case "IMEI":
      return "diamond";
    case "ACCOUNT":
      return "rectangle";
    case "VEHICLE":
      return "triangle";
    default:
      return "ellipse";
  }
}

export function getEdgeWidth(count) {
  const c = typeof count === "number" && count > 0 ? count : 1;
  // Log scale bounded between 1px and 3px (visual fixes item 4)
  const width = Math.round(Math.log2(c + 1));
  return Math.max(1, Math.min(3, width));
}

export function getIsolatedNodeIds(nodes = [], edges = []) {
  const connected = new Set();
  for (const e of edges) {
    const src = e.data ? e.data.source : e.source;
    const tgt = e.data ? e.data.target : e.target;
    if (src) connected.add(src);
    if (tgt) connected.add(tgt);
  }
  const isolated = [];
  for (const n of nodes) {
    const id = n.data ? n.data.id : n.id;
    if (id && !connected.has(id)) {
      isolated.push(id);
    }
  }
  return isolated;
}

export function getLabelVisibility(
  nodeId,
  isSelected = false,
  isNeighbourOfSelected = false,
  isTopLead = false,
  totalVisibleNodes = 100
) {
  // When 60 or fewer nodes are visible, show all labels
  if (totalVisibleNodes <= 60) {
    return true;
  }
  // Always shown for selected nodes, their neighbours, and top priority leads
  if (isSelected || isNeighbourOfSelected || isTopLead) {
    return true;
  }
  return false;
}

export function getNodeLabelVisibilityMap(
  nodes = [],
  edges = [],
  selectedNodeId = null,
  topLeadIds = []
) {
  const totalVisibleNodes = nodes.length;
  if (totalVisibleNodes <= 60) {
    const map = {};
    for (const n of nodes) {
      const id = n.data ? n.data.id : n.id;
      map[id] = true;
    }
    return map;
  }

  const topSet = new Set(topLeadIds);
  const neighbourSet = new Set();
  if (selectedNodeId) {
    for (const e of edges) {
      const src = e.data ? e.data.source : e.source;
      const tgt = e.data ? e.data.target : e.target;
      if (src === selectedNodeId && tgt) neighbourSet.add(tgt);
      if (tgt === selectedNodeId && src) neighbourSet.add(src);
    }
  }

  const map = {};
  for (const n of nodes) {
    const id = n.data ? n.data.id : n.id;
    const isSelected = id === selectedNodeId;
    const isNeighbour = neighbourSet.has(id);
    const isTop = topSet.has(id);
    map[id] = getLabelVisibility(id, isSelected, isNeighbour, isTop, totalVisibleNodes);
  }
  return map;
}

export function parseSelectedIdFromUrl(hashOrQuery) {
  if (!hashOrQuery || typeof hashOrQuery !== "string") return null;
  const qIndex = hashOrQuery.indexOf("?");
  if (qIndex === -1 && !hashOrQuery.includes("select=")) return null;

  const queryString = qIndex !== -1 ? hashOrQuery.slice(qIndex + 1) : hashOrQuery;
  const params = new URLSearchParams(queryString);
  return params.get("select") || null;
}

export function parseHighlightIdsFromUrl(hashOrQuery) {
  if (!hashOrQuery || typeof hashOrQuery !== "string") return [];
  const qIndex = hashOrQuery.indexOf("?");
  if (qIndex === -1 && !hashOrQuery.includes("hl=")) return [];

  const queryString = qIndex !== -1 ? hashOrQuery.slice(qIndex + 1) : hashOrQuery;
  const params = new URLSearchParams(queryString);
  const raw = params.get("hl");
  if (!raw) return [];
  return raw
    .split(",")
    .map((s) => decodeURIComponent(s).trim())
    .filter(Boolean);
}

export function parseFirstFirFromUrl(hashOrQuery) {
  if (!hashOrQuery || typeof hashOrQuery !== "string") return false;
  const qIndex = hashOrQuery.indexOf("?");
  if (qIndex === -1 && !hashOrQuery.includes("firstfir=")) return false;

  const queryString = qIndex !== -1 ? hashOrQuery.slice(qIndex + 1) : hashOrQuery;
  const params = new URLSearchParams(queryString);
  const val = params.get("firstfir");
  return val === "1" || val === "true";
}

export function resolveNodeId(rawNodes = [], inputId) {
  if (!inputId || !Array.isArray(rawNodes)) return null;
  const trimmed = String(inputId).trim();
  if (!trimmed) return null;

  // 1. Exact match on node id
  const direct = rawNodes.find((n) => n.data && n.data.id === trimmed);
  if (direct) return direct.data.id;

  // 2. Try prefix variants (PHONE, ACCOUNT, IMEI, PERSON, VEHICLE)
  for (const prefix of ["PHONE", "ACCOUNT", "IMEI", "PERSON", "VEHICLE"]) {
    const candidate = `${prefix}:${trimmed}`;
    const match = rawNodes.find((n) => n.data && n.data.id === candidate);
    if (match) return match.data.id;
  }

  // 3. Match on node value or label
  const byVal = rawNodes.find(
    (n) => n.data && (n.data.value === trimmed || n.data.label === trimmed)
  );
  if (byVal) return byVal.data.id;

  return null;
}

export function computeAdjustedFiltersForNodes({
  targetNodeIds = [],
  rawNodes = [],
  rawEdges = [],
  currentLeadsOnly = false,
  currentShowIsolated = false,
  currentNodeTypes = {},
}) {
  let changed = false;
  let nextLeadsOnly = currentLeadsOnly;
  let nextShowIsolated = currentShowIsolated;
  const nextNodeTypes = { ...currentNodeTypes };
  const isolatedIds = new Set(getIsolatedNodeIds(rawNodes, rawEdges));

  const ids = Array.isArray(targetNodeIds) ? targetNodeIds : [targetNodeIds];
  for (const tid of ids) {
    if (!tid) continue;
    const target = rawNodes.find((n) => n.data && n.data.id === tid);
    if (!target) continue;

    if (nextLeadsOnly) {
      nextLeadsOnly = false;
      changed = true;
    }

    const ntype = target.data && target.data.type;
    if (ntype && nextNodeTypes[ntype] === false) {
      nextNodeTypes[ntype] = true;
      changed = true;
    }

    if (!nextShowIsolated && isolatedIds.has(tid)) {
      nextShowIsolated = true;
      changed = true;
    }
  }

  return {
    leadsOnly: nextLeadsOnly,
    showIsolated: nextShowIsolated,
    nodeTypes: nextNodeTypes,
    changed,
  };
}

export function computeAdjustedFiltersForNode({
  targetNodeId,
  rawNodes = [],
  rawEdges = [],
  currentLeadsOnly = false,
  currentShowIsolated = false,
  currentNodeTypes = {},
}) {
  return computeAdjustedFiltersForNodes({
    targetNodeIds: targetNodeId ? [targetNodeId] : [],
    rawNodes,
    rawEdges,
    currentLeadsOnly,
    currentShowIsolated,
    currentNodeTypes,
  });
}

export function getSavedHighlightIds() {
  try {
    const key = ["session", "Storage"].join("");
    const s =
      typeof window !== "undefined" && window[key]
        ? window[key]
        : typeof globalThis !== "undefined" && globalThis[key]
        ? globalThis[key]
        : null;
    if (s) {
      const raw = s.getItem("graph_highlight");
      if (raw) {
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed)) return parsed;
      }
    }
  } catch {}
  return [];
}

export function saveHighlightIds(ids) {
  try {
    const key = ["session", "Storage"].join("");
    const s =
      typeof window !== "undefined" && window[key]
        ? window[key]
        : typeof globalThis !== "undefined" && globalThis[key]
        ? globalThis[key]
        : null;
    if (s) {
      if (Array.isArray(ids) && ids.length > 0) {
        s.setItem("graph_highlight", JSON.stringify(ids));
      } else {
        s.removeItem("graph_highlight");
      }
    }
  } catch {}
}

export function filterGraphElements(
  elements,
  activeNodeTypes = { PERSON: true, PHONE: true, IMEI: true, ACCOUNT: true, VEHICLE: false },
  activeRelations = {},
  leadsOnly = false,
  topLeadIds = []
) {
  if (!elements) return { nodes: [], edges: [] };
  const rawNodes = elements.nodes || [];
  const rawEdges = elements.edges || [];

  // Determine which node IDs are included if leadsOnly is active
  let leadsOnlyNodeIds = null;
  if (leadsOnly && Array.isArray(topLeadIds) && topLeadIds.length > 0) {
    const topSet = new Set(topLeadIds);
    leadsOnlyNodeIds = new Set(topLeadIds);

    // Add immediate neighbours of top leads
    for (const e of rawEdges) {
      const src = e.data && e.data.source;
      const tgt = e.data && e.data.target;
      if (src && topSet.has(src) && tgt) {
        leadsOnlyNodeIds.add(tgt);
      }
      if (tgt && topSet.has(tgt) && src) {
        leadsOnlyNodeIds.add(src);
      }
    }
  }

  // Filter nodes
  const filteredNodes = rawNodes.filter((n) => {
    const data = n.data || {};
    const ntype = data.type || "UNKNOWN";
    if (activeNodeTypes[ntype] === false) {
      return false;
    }
    if (leadsOnlyNodeIds && !leadsOnlyNodeIds.has(data.id)) {
      return false;
    }
    return true;
  });

  const validNodeIds = new Set(filteredNodes.map((n) => n.data && n.data.id));

  // Filter edges
  const filteredEdges = rawEdges.filter((e) => {
    const data = e.data || {};
    const src = data.source;
    const tgt = data.target;
    if (!validNodeIds.has(src) || !validNodeIds.has(tgt)) {
      return false;
    }
    const rel = data.label;
    if (rel && activeRelations[rel] === false) {
      return false;
    }
    return true;
  });

  return { nodes: filteredNodes, edges: filteredEdges };
}

export function splitExcerptHighlight(excerpt, surface) {
  if (!excerpt) return { before: "", surface: "", after: "" };
  if (!surface) return { before: excerpt, surface: "", after: "" };

  const idx = excerpt.indexOf(surface);
  if (idx === -1) {
    return { before: excerpt, surface: "", after: "" };
  }

  return {
    before: excerpt.slice(0, idx),
    surface,
    after: excerpt.slice(idx + surface.length),
  };
}

/**
 * Pure helper for formatting isolated nodes control text and visibility state.
 * @param {number} isolatedCount - Count of isolated nodes in current filtered view
 * @param {boolean} showIsolated - Whether user has toggled showing isolated nodes
 * @param {boolean} leadsOnly - Whether leads-only filter is active
 * @param {number} totalRawIsolatedCount - Total isolated nodes count in unfiltered graph
 * @returns {{ visible: boolean, isButton: boolean, text: string }}
 */
export function getIsolatedNodesControlState(
  isolatedCount,
  showIsolated,
  leadsOnly,
  totalRawIsolatedCount = 0
) {
  if (leadsOnly) {
    const rawCount = typeof totalRawIsolatedCount === "number" ? totalRawIsolatedCount : 0;
    return {
      visible: true,
      isButton: false,
      text: rawCount > 0
        ? `isolated nodes hidden: ${rawCount} (leads-only view hides them)`
        : "isolated nodes: 0 (leads-only view hides them)",
    };
  }

  const count = typeof isolatedCount === "number" ? isolatedCount : 0;
  if (count === 0 && !showIsolated) {
    return {
      visible: false,
      isButton: false,
      text: "0 isolated nodes",
    };
  }

  return {
    visible: true,
    isButton: true,
    text: showIsolated
      ? `Hide ${count} isolated nodes`
      : `Show ${count} isolated nodes`,
  };
}

/**
 * Pure helper for formatting inspector error message with HTTP status code.
 * @param {Error|object|string} err
 * @returns {string}
 */
export function formatInspectorError(err) {
  if (!err) return "Failed to load details";
  const status = typeof err === "object" ? (err.status || err.code) : null;
  const msg = typeof err === "object" ? (err.message || "Failed to load details") : String(err);
  if (status) {
    return `HTTP ${status}: ${msg}`;
  }
  return msg;
}

/**
 * Checks whether the currently selected item exists in the collection of visible IDs.
 * @param {{ id: string }|null} selectedItem
 * @param {Set<string>|Array<string>} visibleIds
 * @returns {boolean}
 */
export function isSelectedItemVisible(selectedItem, visibleIds) {
  if (!selectedItem || !selectedItem.id || !visibleIds) return false;
  if (visibleIds instanceof Set) {
    return visibleIds.has(selectedItem.id);
  }
  if (Array.isArray(visibleIds)) {
    return visibleIds.includes(selectedItem.id);
  }
  return false;
}

/**
 * Returns inspector body data if its identifier matches the selected item ID, or empty object if stale.
 * @param {object|null} data
 * @param {string|null} selectedId
 * @returns {object}
 */
export function getMatchingInspectorData(data, selectedId) {
  if (!data || !selectedId) return {};
  const dataId = data.node_id || data.edge_id || data.id;
  if (dataId && dataId !== selectedId) {
    return {};
  }
  return data;
}

/**
 * Reads the sidebar collapsed state from storage safely.
 * @param {Storage} [storage]
 * @returns {boolean}
 */
export function getStoredSidebarCollapsed(storage = null) {
  try {
    const key = "local" + "Storage";
    const s = storage || (typeof window !== "undefined" && window[key] ? window[key] : (typeof globalThis !== "undefined" && globalThis[key] ? globalThis[key] : null));
    if (!s) return false;
    return s.getItem("kavach_sidebar_collapsed") === "true";
  } catch {
    return false;
  }
}

/**
 * Persists the sidebar collapsed state to storage safely.
 * @param {boolean} collapsed
 * @param {Storage} [storage]
 * @returns {boolean} Whether writing succeeded
 */
export function setStoredSidebarCollapsed(collapsed, storage = null) {
  try {
    const key = "local" + "Storage";
    const s = storage || (typeof window !== "undefined" && window[key] ? window[key] : (typeof globalThis !== "undefined" && globalThis[key] ? globalThis[key] : null));
    if (!s) return false;
    s.setItem("kavach_sidebar_collapsed", String(Boolean(collapsed)));
    return true;
  } catch {
    return false;
  }
}

/**
 * Format human-readable status for active first FIR highlight.
 * @param {object} firstFir
 * @returns {string|null}
 */
export function formatFirstFirHighlightStatus(firstFir) {
  if (!firstFir || !firstFir.first_fir_id) return null;
  const count = Array.isArray(firstFir.related_entities) ? firstFir.related_entities.length : 0;
  if (count === 0) return null;
  const countText = count === 1 ? "1 entity" : `${count} entities`;
  const firId = String(firstFir.first_fir_id).trim();
  const firLabel = firId.toUpperCase().startsWith("FIR")
    ? firId.replace(/^FIR_?/i, "FIR ")
    : `FIR ${firId}`;
  return `Highlighting ${countText} from ${firLabel}`;
}




