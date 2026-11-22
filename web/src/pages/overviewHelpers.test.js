import { describe, it, expect } from "vitest";
import {
  getLimitations,
  extractDocId,
  buildPriorityLeadsData,
} from "./overviewHelpers.js";

describe("getLimitations", () => {
  it("returns only OCR sentence when case is not analyzed", () => {
    expect(getLimitations(false, ["Some limit"])).toEqual(["Typed text only: no OCR"]);
    expect(getLimitations(false, null)).toEqual(["Typed text only: no OCR"]);
  });

  it("returns limitations plus OCR sentence when case is analyzed", () => {
    const limits = ["F1 score 0.32", "Synthetic data only"];
    const result = getLimitations(true, limits);
    expect(result).toHaveLength(3);
    expect(result[0]).toBe("F1 score 0.32");
    expect(result[1]).toBe("Synthetic data only");
    expect(result[2]).toBe("Typed text only: no OCR");
  });
});

describe("extractDocId", () => {
  it("extracts FIR doc ID from entity identifier", () => {
    expect(extractDocId("PERSON:FIR_05:ent_09")).toBe("FIR_05");
    expect(extractDocId("PERSON:FIR_123:node_4")).toBe("FIR_123");
  });

  it("falls back to default doc ID when missing", () => {
    expect(extractDocId("PERSON:P1", "FIR_02")).toBe("FIR_02");
    expect(extractDocId("", "FIR_01")).toBe("FIR_01");
    expect(extractDocId(null, "FIR_01")).toBe("FIR_01");
  });
});

describe("buildPriorityLeadsData", () => {
  it("combines money flow with roles and structural metrics", () => {
    const moneyFlow = [
      { person_id: "P1", name: "Alice", rank: 1, score: 0.95 },
    ];
    const roleChips = { P1: ["BENEFICIARY"] };
    const structuralMap = {
      P1: { degree: 0.45, betweenness: 0.12, eigenvector: 0.33, composite: 0.5 },
    };

    const res = buildPriorityLeadsData(moneyFlow, roleChips, structuralMap);
    expect(res).toHaveLength(1);
    expect(res[0].roles).toEqual(["BENEFICIARY"]);
    expect(res[0].degree).toBe(0.45);
    expect(res[0].betweenness).toBe(0.12);
    expect(res[0].eigenvector).toBe(0.33);
    expect(res[0].composite).toBe(0.5);
  });
});
