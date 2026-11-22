import { describe, it, expect } from "vitest";
import {
  getNodeShape,
  getEdgeWidth,
  getLabelVisibility,
  getNodeLabelVisibilityMap,
  parseSelectedIdFromUrl,
  filterGraphElements,
  splitExcerptHighlight,
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
