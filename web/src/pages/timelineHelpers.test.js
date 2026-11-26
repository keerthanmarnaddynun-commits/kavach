import { describe, it, expect } from "vitest";
import {
  computeMax,
  computeBarLayout,
  formatPaise,
  getGraphNodeId,
  selectExampleRows,
  insightViewCache,
  getCachedInsightView,
  setCachedInsightView,
  clearCachedInsightView,
  filterInsightsByView,
  alignDailyBuckets,
  getChartAnnotations,
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

describe("insightViewCache", () => {
  it("defaults to Both when uncached and persists updates in memory per caseId", () => {
    clearCachedInsightView();
    expect(getCachedInsightView("C-case1")).toBe("Both");

    setCachedInsightView("C-case1", "Calls only");
    expect(getCachedInsightView("C-case1")).toBe("Calls only");
    expect(getCachedInsightView("C-case2")).toBe("Both");

    setCachedInsightView("C-case2", "Transfers only");
    expect(getCachedInsightView("C-case2")).toBe("Transfers only");

    clearCachedInsightView("C-case1");
    expect(getCachedInsightView("C-case1")).toBe("Both");
    expect(getCachedInsightView("C-case2")).toBe("Transfers only");

    clearCachedInsightView();
    expect(getCachedInsightView("C-case2")).toBe("Both");
  });
});

describe("filterInsightsByView", () => {
  const sampleInsights = [
    { id: "ins-1", kind: "call_spike", chart: "calls", days: ["2026-03-01"] },
    { id: "ins-2", kind: "call_then_transfer", chart: "both", days: ["2026-03-01", "2026-03-03"] },
    { id: "ins-3", kind: "transfer_spike", chart: "transfers", days: ["2026-03-03"] },
    { id: "ins-4", kind: "new_and_busy", chart: "calls", days: ["2026-03-05"] },
  ];

  it("filters Calls only and assigns 1-based sequential numbers", () => {
    const callsView = filterInsightsByView(sampleInsights, "Calls only");
    expect(callsView.map((x) => x.id)).toEqual(["ins-1", "ins-4"]);
    expect(callsView[0].number).toBe(1);
    expect(callsView[1].number).toBe(2);
  });

  it("filters Transfers only and assigns 1-based sequential numbers", () => {
    const trView = filterInsightsByView(sampleInsights, "Transfers only");
    expect(trView.map((x) => x.id)).toEqual(["ins-3"]);
    expect(trView[0].number).toBe(1);
  });

  it("includes all insights in Both view with sequential numbers", () => {
    const bothView = filterInsightsByView(sampleInsights, "Both");
    expect(bothView.map((x) => x.id)).toEqual(["ins-1", "ins-2", "ins-3", "ins-4"]);
    expect(bothView.map((x) => x.number)).toEqual([1, 2, 3, 4]);
  });
});

describe("alignDailyBuckets", () => {
  it("aligns distinct call and transfer dates onto a shared timeline with zero-fill", () => {
    const calls = [
      { t: "2026-03-01", count: 15 },
      { t: "2026-03-03", count: 25 },
    ];
    const transfers = [
      { t: "2026-03-02", count: 10, paise: 50000 },
      { t: "2026-03-03", count: 8, paise: 40000 },
    ];

    const { alignedCalls, alignedTransfers, allDays } = alignDailyBuckets(calls, transfers);
    expect(allDays).toEqual(["2026-03-01", "2026-03-02", "2026-03-03"]);

    expect(alignedCalls.map((c) => c.count)).toEqual([15, 0, 25]);
    expect(alignedTransfers.map((tr) => tr.count)).toEqual([0, 10, 8]);
  });
});

describe("getChartAnnotations", () => {
  const visible = [
    { id: "ins-1", chart: "calls", days: ["2026-03-01"], number: 1 },
    { id: "ins-2", chart: "both", days: ["2026-03-01", "2026-03-03"], number: 2 },
    { id: "ins-3", chart: "transfers", days: ["2026-03-03"], number: 3 },
  ];

  it("returns circle annotations for calls and transfers correctly", () => {
    const callAnn = getChartAnnotations(visible, "calls");
    expect(callAnn).toEqual([
      { day: "2026-03-01", number: 1, insightId: "ins-1" },
      { day: "2026-03-01", number: 2, insightId: "ins-2" },
    ]);

    const trAnn = getChartAnnotations(visible, "transfers");
    expect(trAnn).toEqual([
      { day: "2026-03-03", number: 2, insightId: "ins-2" },
      { day: "2026-03-03", number: 3, insightId: "ins-3" },
    ]);
  });
});

