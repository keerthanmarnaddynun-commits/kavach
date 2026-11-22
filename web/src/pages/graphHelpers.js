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

export function getEdgeWidth(amount, count) {
  const num = typeof amount === "number" && amount > 0
    ? amount
    : (typeof count === "number" && count > 0 ? count : 1);

  // Log scale bounded between 1px and 8px
  const width = Math.round(Math.log2(num + 1));
  return Math.max(1, Math.min(8, width));
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

export function parseSelectedIdFromUrl(hashOrQuery) {
  if (!hashOrQuery || typeof hashOrQuery !== "string") return null;
  const qIndex = hashOrQuery.indexOf("?");
  if (qIndex === -1 && !hashOrQuery.includes("select=")) return null;

  const queryString = qIndex !== -1 ? hashOrQuery.slice(qIndex + 1) : hashOrQuery;
  const params = new URLSearchParams(queryString);
  return params.get("select") || null;
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
