import { describe, it, expect } from "vitest";
import {
  getNodeShape,
  getEdgeWidth,
  getLabelVisibility,
  getNodeLabelVisibilityMap,
  parseSelectedIdFromUrl,
  parseHighlightIdsFromUrl,
  parseFirstFirFromUrl,
  resolveNodeId,
  computeAdjustedFiltersForNode,
  computeAdjustedFiltersForNodes,
  filterGraphElements,
  splitExcerptHighlight,
  getIsolatedNodesControlState,
  formatInspectorError,
  isSelectedItemVisible,
  getMatchingInspectorData,
  getStoredSidebarCollapsed,
  setStoredSidebarCollapsed,
} from "./graphHelpers.js";

describe("getNodeShape", () => {
  it("maps node types to required geometric shapes", () => {
    expect(getNodeShape("PERSON")).toBe("ellipse");
    expect(getNodeShape("PHONE")).toBe("round-rectangle");
    expect(getNodeShape("IMEI")).toBe("diamond");
    expect(getNodeShape("ACCOUNT")).toBe("rectangle");
    expect(getNodeShape("VEHICLE")).toBe("triangle");
    expect(getNodeShape("OTHER")).toBe("ellipse");
  });
});

describe("getEdgeWidth", () => {
  it("calculates log scale width from count only bounded within 1 and 3", () => {
    expect(getEdgeWidth(0)).toBe(1);
    expect(getEdgeWidth(undefined)).toBe(1);
    expect(getEdgeWidth(1)).toBe(1);
    expect(getEdgeWidth(3)).toBe(2);
    expect(getEdgeWidth(7)).toBe(3);
    expect(getEdgeWidth(15)).toBe(3);
    expect(getEdgeWidth(100)).toBe(3);
    expect(getEdgeWidth(1000000)).toBe(3);
  });
});

describe("getLabelVisibility", () => {
  it("shows all labels when visible nodes count <= 60", () => {
    expect(getLabelVisibility("N1", false, false, false, 50)).toBe(true);
    expect(getLabelVisibility("N1", false, false, false, 60)).toBe(true);
  });

  it("shows labels only for selected, neighbours, or top leads when count > 60", () => {
    expect(getLabelVisibility("N1", true, false, false, 100)).toBe(true);
    expect(getLabelVisibility("N1", false, true, false, 100)).toBe(true);
    expect(getLabelVisibility("N1", false, false, true, 100)).toBe(true);
    expect(getLabelVisibility("N1", false, false, false, 100)).toBe(false);
  });
});

describe("getNodeLabelVisibilityMap", () => {
  const dummyNodes = Array.from({ length: 70 }, (_, i) => ({
    data: { id: `N${i + 1}` },
  }));
  const dummyEdges = [
    { data: { id: "E1", source: "N1", target: "N2" } },
    { data: { id: "E2", source: "N2", target: "N3" } },
  ];

  it("shows all labels when total nodes <= 60", () => {
    const smallNodes = dummyNodes.slice(0, 50);
    const map = getNodeLabelVisibilityMap(smallNodes, dummyEdges, null, []);
    expect(Object.keys(map).length).toBe(50);
    expect(map["N1"]).toBe(true);
    expect(map["N50"]).toBe(true);
  });

  it("shows labels for selected node, its neighbours, and top leads (covering neighbour case)", () => {
    const topLeads = ["N10"];
    const map = getNodeLabelVisibilityMap(dummyNodes, dummyEdges, "N1", topLeads);

    expect(map["N1"]).toBe(true); // Selected
    expect(map["N2"]).toBe(true); // Immediate neighbour of selected N1
    expect(map["N10"]).toBe(true); // Top lead
    expect(map["N3"]).toBe(false); // Second-degree neighbour (not immediate)
    expect(map["N4"]).toBe(false); // Unrelated node
  });
});

describe("parseSelectedIdFromUrl", () => {
  it("extracts select parameter from hash routes", () => {
    expect(parseSelectedIdFromUrl("#/case/C-01/graph?select=PERSON:FIR_01:ent_02")).toBe(
      "PERSON:FIR_01:ent_02"
    );
    expect(parseSelectedIdFromUrl("?select=ACCOUNT:123")).toBe("ACCOUNT:123");
    expect(parseSelectedIdFromUrl("#/case/C-01/graph")).toBe(null);
    expect(parseSelectedIdFromUrl("")).toBe(null);
  });
});

describe("parseFirstFirFromUrl", () => {
  it("detects firstfir=1 in hash or query parameters", () => {
    expect(parseFirstFirFromUrl("#/case/C-01/graph?select=PHONE:123&firstfir=1")).toBe(true);
    expect(parseFirstFirFromUrl("?select=ACCOUNT:456&firstfir=true")).toBe(true);
    expect(parseFirstFirFromUrl("#/case/C-01/graph?select=PHONE:123")).toBe(false);
    expect(parseFirstFirFromUrl("")).toBe(false);
  });
});

describe("resolveNodeId", () => {
  const nodes = [
    { data: { id: "PHONE:9876543210", type: "PHONE", value: "9876543210" } },
    { data: { id: "ACCOUNT:ACC9988", type: "ACCOUNT", value: "ACC9988" } },
    { data: { id: "PERSON:FIR_01:ent_02", type: "PERSON", label: "Vikas Sharma" } },
  ];

  it("resolves direct ID and bare values with prefixes", () => {
    expect(resolveNodeId(nodes, "PHONE:9876543210")).toBe("PHONE:9876543210");
    expect(resolveNodeId(nodes, "9876543210")).toBe("PHONE:9876543210");
    expect(resolveNodeId(nodes, "ACC9988")).toBe("ACCOUNT:ACC9988");
    expect(resolveNodeId(nodes, "Vikas Sharma")).toBe("PERSON:FIR_01:ent_02");
    expect(resolveNodeId(nodes, "UNKNOWN_NODE")).toBe(null);
    expect(resolveNodeId(nodes, "")).toBe(null);
  });
});

describe("computeAdjustedFiltersForNode", () => {
  const rawNodes = [
    { data: { id: "P1", type: "PERSON" } },
    { data: { id: "V1", type: "VEHICLE" } },
    { data: { id: "ISO1", type: "ACCOUNT" } },
  ];
  const rawEdges = [{ data: { source: "P1", target: "V1" } }];

  it("turns off leadsOnly and enables target node type and isolated state when needed", () => {
    const adj = computeAdjustedFiltersForNode({
      targetNodeId: "V1",
      rawNodes,
      rawEdges,
      currentLeadsOnly: true,
      currentShowIsolated: false,
      currentNodeTypes: { PERSON: true, VEHICLE: false },
    });
    expect(adj.changed).toBe(true);
    expect(adj.leadsOnly).toBe(false);
    expect(adj.nodeTypes.VEHICLE).toBe(true);

    // Isolated node adjustment
    const adjIso = computeAdjustedFiltersForNode({
      targetNodeId: "ISO1",
      rawNodes,
      rawEdges,
      currentLeadsOnly: false,
      currentShowIsolated: false,
      currentNodeTypes: { PERSON: true, ACCOUNT: true },
    });
    expect(adjIso.changed).toBe(true);
    expect(adjIso.showIsolated).toBe(true);

    // Multi-node counterparts adjustment
    const adjMulti = computeAdjustedFiltersForNodes({
      targetNodeIds: ["V1", "ISO1"],
      rawNodes,
      rawEdges,
      currentLeadsOnly: true,
      currentShowIsolated: false,
      currentNodeTypes: { PERSON: true, VEHICLE: false, ACCOUNT: false },
    });
    expect(adjMulti.changed).toBe(true);
    expect(adjMulti.leadsOnly).toBe(false);
    expect(adjMulti.showIsolated).toBe(true);
    expect(adjMulti.nodeTypes.VEHICLE).toBe(true);
  });
});

describe("filterGraphElements", () => {
  const elements = {
    nodes: [
      { data: { id: "P1", type: "PERSON" } },
      { data: { id: "PH1", type: "PHONE" } },
      { data: { id: "V1", type: "VEHICLE" } },
      { data: { id: "P2", type: "PERSON" } },
    ],
    edges: [
      { data: { id: "E1", source: "P1", target: "PH1", label: "OWNS_DEVICE" } },
      { data: { id: "E2", source: "P1", target: "V1", label: "USES_VEHICLE" } },
      { data: { id: "E3", source: "P2", target: "PH1", label: "CALLS" } },
    ],
  };

  it("hides VEHICLE by default", () => {
    const res = filterGraphElements(elements);
    const types = res.nodes.map((n) => n.data.type);
    expect(types).not.toContain("VEHICLE");
    expect(res.edges.map((e) => e.data.id)).not.toContain("E2");
  });

  it("filters to leads only with immediate neighbours", () => {
    const res = filterGraphElements(
      elements,
      { PERSON: true, PHONE: true, IMEI: true, ACCOUNT: true, VEHICLE: false },
      {},
      true,
      ["P1"]
    );
    const nodeIds = res.nodes.map((n) => n.data.id);
    expect(nodeIds).toContain("P1");
    expect(nodeIds).toContain("PH1"); // Neighbour
    expect(nodeIds).not.toContain("P2"); // Unrelated
  });
});

describe("splitExcerptHighlight", () => {
  it("splits excerpt around surface text correctly", () => {
    const excerpt = "Suspect Vikas Sharma was spotted near market.";
    const res = splitExcerptHighlight(excerpt, "Vikas Sharma");
    expect(res.before).toBe("Suspect ");
    expect(res.surface).toBe("Vikas Sharma");
    expect(res.after).toBe(" was spotted near market.");
  });

  it("handles missing surface safely", () => {
    const res = splitExcerptHighlight("Some text here", "NotFound");
    expect(res.before).toBe("Some text here");
    expect(res.surface).toBe("");
  });
});

describe("getIsolatedNodesControlState", () => {
  it("formats informative non-button text in leads-only view with raw isolated count", () => {
    const demoLo = getIsolatedNodesControlState(0, false, true, 205);
    expect(demoLo.visible).toBe(true);
    expect(demoLo.isButton).toBe(false);
    expect(demoLo.text).toBe("isolated nodes hidden: 205 (leads-only view hides them)");

    const practiceLo = getIsolatedNodesControlState(0, false, true, 0);
    expect(practiceLo.visible).toBe(true);
    expect(practiceLo.isButton).toBe(false);
    expect(practiceLo.text).toBe("isolated nodes: 0 (leads-only view hides them)");
  });

  it("hides control in full view when isolated count is 0 and not shown", () => {
    const res = getIsolatedNodesControlState(0, false, false, 0);
    expect(res.visible).toBe(false);
    expect(res.isButton).toBe(false);
  });

  it("shows toggle button in full view when isolated count > 0", () => {
    const hiddenState = getIsolatedNodesControlState(205, false, false, 205);
    expect(hiddenState.visible).toBe(true);
    expect(hiddenState.isButton).toBe(true);
    expect(hiddenState.text).toBe("Show 205 isolated nodes");

    const shownState = getIsolatedNodesControlState(205, true, false, 205);
    expect(shownState.visible).toBe(true);
    expect(shownState.isButton).toBe(true);
    expect(shownState.text).toBe("Hide 205 isolated nodes");
  });
});

describe("formatInspectorError", () => {
  it("formats error with HTTP status code when present", () => {
    const errObj = { status: 404, message: "Node 'N1' not found in case graph" };
    expect(formatInspectorError(errObj)).toBe("HTTP 404: Node 'N1' not found in case graph");

    const codeObj = { code: 500, message: "Internal server error" };
    expect(formatInspectorError(codeObj)).toBe("HTTP 500: Internal server error");
  });

  it("formats error fallback without status code", () => {
    expect(formatInspectorError({ message: "Network connection lost" })).toBe("Network connection lost");
    expect(formatInspectorError(null)).toBe("Failed to load details");
  });
});

describe("isSelectedItemVisible", () => {
  it("keeps selection when item exists in new visible IDs, clears when missing", () => {
    const selectedItem = { type: "node", id: "P1" };
    const visibleIdsSet = new Set(["P1", "P2", "PH1"]);
    expect(isSelectedItemVisible(selectedItem, visibleIdsSet)).toBe(true);

    const isolatedOnlySet = new Set(["P2", "PH1"]);
    expect(isSelectedItemVisible(selectedItem, isolatedOnlySet)).toBe(false);

    expect(isSelectedItemVisible(null, visibleIdsSet)).toBe(false);
  });
});

describe("getMatchingInspectorData", () => {
  it("returns data when ID matches selected item, empty object when response is stale", () => {
    const freshData = { node_id: "P1", fir_evidence: [{ doc_id: "FIR_01" }] };
    expect(getMatchingInspectorData(freshData, "P1")).toBe(freshData);

    const staleData = { node_id: "P0", fir_evidence: [{ doc_id: "FIR_00" }] };
    expect(getMatchingInspectorData(staleData, "P1")).toEqual({});

    expect(getMatchingInspectorData(null, "P1")).toEqual({});
  });
});

describe("sidebarCollapsed storage helpers", () => {
  it("defaults to false when storage is empty or throws", () => {
    const mockStorage = { getItem: () => null, setItem: () => {} };
    expect(getStoredSidebarCollapsed(mockStorage)).toBe(false);

    const throwingStorage = { getItem: () => { throw new Error("denied"); } };
    expect(getStoredSidebarCollapsed(throwingStorage)).toBe(false);
    expect(getStoredSidebarCollapsed(null)).toBe(false);
  });

  it("reads stored true value", () => {
    const mockStorage = { getItem: () => "true", setItem: () => {} };
    expect(getStoredSidebarCollapsed(mockStorage)).toBe(true);
  });

  it("persists collapsed state to storage safely", () => {
    let stored = null;
    const mockStorage = {
      getItem: () => stored,
      setItem: (_, v) => { stored = String(v); },
    };
    expect(setStoredSidebarCollapsed(true, mockStorage)).toBe(true);
    expect(stored).toBe("true");
    expect(setStoredSidebarCollapsed(false, mockStorage)).toBe(true);
    expect(stored).toBe("false");

    const throwingStorage = { setItem: () => { throw new Error("denied"); } };
    expect(setStoredSidebarCollapsed(true, throwingStorage)).toBe(false);
    expect(setStoredSidebarCollapsed(true, null)).toBe(false);
  });
});



