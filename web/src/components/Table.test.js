import { describe, it, expect } from "vitest";
import { compareTableValues, nextSortState, sortTableData } from "./Table.jsx";

describe("compareTableValues", () => {
  it("sorts numbers numerically", () => {
    expect(compareTableValues(10, 2, true, false, "asc")).toBeGreaterThan(0);
    expect(compareTableValues(2, 10, true, false, "asc")).toBeLessThan(0);
    expect(compareTableValues(10, 2, true, false, "desc")).toBeLessThan(0);
    expect(compareTableValues(5, 5, true, false, "asc")).toBe(0);
  });

  it("sorts identifiers as exact text", () => {
    expect(compareTableValues("P10", "P2", false, true, "asc")).toBeLessThan(0);
    expect(compareTableValues("P2", "P10", false, true, "asc")).toBeGreaterThan(0);
    expect(compareTableValues("P10", "P2", false, true, "desc")).toBeGreaterThan(0);
  });

  it("always puts empty values at the end in both asc and desc", () => {
    // Ascending: empty after valid
    expect(compareTableValues(null, 5, true, false, "asc")).toBe(1);
    expect(compareTableValues(5, null, true, false, "asc")).toBe(-1);
    expect(compareTableValues("", "abc", false, false, "asc")).toBe(1);
    expect(compareTableValues([], ["a"], false, false, "asc")).toBe(1);

    // Descending: empty still after valid
    expect(compareTableValues(null, 5, true, false, "desc")).toBe(1);
    expect(compareTableValues(5, null, true, false, "desc")).toBe(-1);
    expect(compareTableValues("", "abc", false, false, "desc")).toBe(1);

    // Both empty: equal
    expect(compareTableValues(null, undefined, true, false, "asc")).toBe(0);
    expect(compareTableValues("", null, false, false, "desc")).toBe(0);
  });
});

describe("nextSortState", () => {
  it("switches column to asc first", () => {
    expect(nextSortState("name", "asc", "score")).toEqual({ sortKey: "score", sortDir: "asc" });
  });

  it("toggles direction when same column clicked", () => {
    expect(nextSortState("score", "asc", "score")).toEqual({ sortKey: "score", sortDir: "desc" });
    expect(nextSortState("score", "desc", "score")).toEqual({ sortKey: "score", sortDir: "asc" });
  });
});

describe("sortTableData", () => {
  const sample = [
    { id: 1, name: "Charlie", score: 20 },
    { id: 2, name: "Alice", score: 50 },
    { id: 3, name: "Bob", score: 50 },
    { id: 4, name: "Dave", score: null },
  ];

  const columns = [
    { key: "name", isNumeric: false, isIdentifier: false },
    { key: "score", isNumeric: true },
  ];

  it("performs stable sorting preserving initial tie order", () => {
    const sorted = sortTableData(sample, "score", "desc", columns);
    // Alice and Bob both have score 50. Alice was index 1, Bob index 2.
    expect(sorted[0].name).toBe("Alice");
    expect(sorted[1].name).toBe("Bob");
    expect(sorted[2].name).toBe("Charlie");
    expect(sorted[3].name).toBe("Dave"); // null score at end
  });

  it("sorts text column ascending", () => {
    const sorted = sortTableData(sample, "name", "asc", columns);
    expect(sorted.map((x) => x.name)).toEqual(["Alice", "Bob", "Charlie", "Dave"]);
  });
});
