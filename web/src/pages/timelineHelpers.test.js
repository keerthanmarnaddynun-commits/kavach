import { describe, it, expect } from "vitest";
import { computeMax, computeBarLayout, formatPaise } from "./timelineHelpers.js";

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
