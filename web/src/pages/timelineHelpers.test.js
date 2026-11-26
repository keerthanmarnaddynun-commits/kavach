import { describe, it, expect } from "vitest";
import {
  computeMax,
  computeBarLayout,
  formatPaise,
  getGraphNodeId,
  selectExampleRows,
} from "./timelineHelpers.js";

describe("computeMax", () => {
  it("calculates max value across items", () => {
    const items = [{ count: 10 }, { count: 45 }, { count: 20 }];
    expect(computeMax(items, "count")).toBe(45);
  });

  it("returns at least 1 when items array is empty or zero", () => {
    expect(computeMax([], "count")).toBe(1);
    expect(computeMax([{ count: 0 }], "count")).toBe(1);
  });
});

describe("computeBarLayout", () => {
  it("generates deterministic coordinates within plot margins", () => {
    const items = [
      { t: "2026-01-01", count: 100 },
      { t: "2026-01-02", count: 200 },
    ];
    const layout = computeBarLayout(items, "count", 600, 200, {
      top: 20,
      right: 20,
      bottom: 30,
      left: 40,
    });

    expect(layout.bars.length).toBe(2);
    expect(layout.maxVal).toBe(200);

    const first = layout.bars[0];
    const second = layout.bars[1];

    expect(first.x).toBeGreaterThanOrEqual(40);
    expect(second.x).toBeGreaterThan(first.x);
    expect(second.height).toBeGreaterThan(first.height);
    expect(first.value).toBe(100);
    expect(second.value).toBe(200);
  });

  it("handles empty items list cleanly", () => {
    const layout = computeBarLayout([], "count");
    expect(layout.bars).toEqual([]);
    expect(layout.maxVal).toBe(1);
  });
});

describe("formatPaise", () => {
  it("converts paise to rupees with 2 decimal places", () => {
    expect(formatPaise(10050)).toBe("100.50");
    expect(formatPaise(0)).toBe("0.00");
    expect(formatPaise(null)).toBe("-");
  });
});

describe("getGraphNodeId", () => {
  it("derives graph node ID for ACCOUNT and IMEI", () => {
    expect(getGraphNodeId("ACCOUNT", "1234567890")).toBe("ACCOUNT:1234567890");
    expect(getGraphNodeId("ACCOUNT", "ACCOUNT:1234567890")).toBe("ACCOUNT:1234567890");
    expect(getGraphNodeId("IMEI", "351756051523999")).toBe("IMEI:351756051523999");
    expect(getGraphNodeId("IMEI", "IMEI:351756051523999")).toBe("IMEI:351756051523999");
    expect(getGraphNodeId("PHONE", "9876543210")).toBe("PHONE:9876543210");
    expect(getGraphNodeId("PHONE", "PHONE:9876543210")).toBe("PHONE:9876543210");
  });

  it("returns null for empty or non-string inputs", () => {
    expect(getGraphNodeId("ACCOUNT", "")).toBeNull();
    expect(getGraphNodeId("ACCOUNT", "   ")).toBeNull();
    expect(getGraphNodeId("ACCOUNT", null)).toBeNull();
    expect(getGraphNodeId("OTHER", "123")).toBeNull();
  });
});

describe("selectExampleRows", () => {
  it("selects at most one row per category, preferring category 1 with >= 2 linked entities", () => {
    const rows = [
      {
        phone: "P1",
        first_fir: { first_fir_id: "FIR_01", related_count: 1 },
        first_record: { timestamp: "2026-01-01T08:00:00", counterparts: ["P2"] },
      },
      {
        phone: "P2",
        first_fir: { first_fir_id: "FIR_02", related_count: 3 },
        first_record: { timestamp: "2026-01-01T08:00:00", counterparts: ["P1"] },
      },
      {
        phone: "P3",
        first_fir: null,
        first_record: { timestamp: "2026-01-01T09:00:00", counterparts: ["P4"] },
      },
      {
        phone: "P4",
        first_fir: null,
        first_record: { timestamp: "2026-01-01T09:00:00", counterparts: [] },
      },
    ];

    const markers = selectExampleRows(rows);
    // P2 should be selected for category 1 (has 3 linked entities vs 1)
    expect(markers["P2"]).toBe("category1");
    // P3 should be selected for category 2 (has counterparts vs none)
    expect(markers["P3"]).toBe("category2");
    // P1 and P4 should not have markers (at most one per category)
    expect(markers["P1"]).toBeUndefined();
    expect(markers["P4"]).toBeUndefined();
  });

  it("handles missing categories cleanly when only category 1 or only category 2 exists", () => {
    // Only Category 1 rows
    const onlyCat1 = [
      {
        account: "A1",
        first_fir: { first_fir_id: "FIR_01", related_count: 2 },
        first_record: { timestamp: "2026-01-01T08:00:00", counterparts: ["A2"] },
      },
    ];
    const markers1 = selectExampleRows(onlyCat1);
    expect(markers1["A1"]).toBe("category1");
    expect(Object.values(markers1)).not.toContain("category2");

    // Only Category 2 rows
    const onlyCat2 = [
      {
        imei: "IM1",
        first_fir: null,
        first_record: { timestamp: "2026-01-01T08:00:00", counterparts: ["P1"] },
      },
    ];
    const markers2 = selectExampleRows(onlyCat2);
    expect(markers2["IM1"]).toBe("category2");
    expect(Object.values(markers2)).not.toContain("category1");
  });

  it("returns empty object for empty or invalid rows", () => {
    expect(selectExampleRows([])).toEqual({});
    expect(selectExampleRows(null)).toEqual({});
    expect(selectExampleRows(undefined)).toEqual({});
  });
});
