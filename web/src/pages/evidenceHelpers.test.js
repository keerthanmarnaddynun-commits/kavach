import { describe, it, expect } from "vitest";
import {
  segmentTextWithSpans,
  parseSpanQuery,
  parseRowsQuery,
} from "./evidenceHelpers.js";

describe("segmentTextWithSpans", () => {
  it("segments non-overlapping spans cleanly", () => {
    const text = "Alpha Bravo Charlie Delta";
    const spans = [
      { char_span: [0, 5], label: "Alpha" },
      { char_span: [12, 19], label: "Charlie" },
    ];

    const { segments, outOfRangeCount } = segmentTextWithSpans(text, spans);
    expect(outOfRangeCount).toBe(0);
    expect(segments).toHaveLength(4);

    expect(segments[0].text).toBe("Alpha");
    expect(segments[0].isHighlighted).toBe(true);

    expect(segments[1].text).toBe(" Bravo ");
    expect(segments[1].isHighlighted).toBe(false);

    expect(segments[2].text).toBe("Charlie");
    expect(segments[2].isHighlighted).toBe(true);

    expect(segments[3].text).toBe(" Delta");
    expect(segments[3].isHighlighted).toBe(false);
  });

  it("handles overlapping spans without dropping overlap", () => {
    const text = "Vikas Sharma was present";
    // Vikas: [0, 5], Vikas Sharma: [0, 12]
    const spans = [
      { char_span: [0, 5], label: "Short" },
      { char_span: [0, 12], label: "Long" },
    ];

    const { segments, outOfRangeCount } = segmentTextWithSpans(text, spans);
    expect(outOfRangeCount).toBe(0);

    // Segment 1: [0, 5] "Vikas" has both spans
    expect(segments[0].text).toBe("Vikas");
    expect(segments[0].spans).toHaveLength(2);
    expect(segments[0].isOverlap).toBe(true);

    // Segment 2: [5, 12] " Sharma" has only Long span
    expect(segments[1].text).toBe(" Sharma");
    expect(segments[1].spans).toHaveLength(1);
    expect(segments[1].isOverlap).toBe(false);

    // Segment 3: [12, 24] " was present" has 0 spans
    expect(segments[2].text).toBe(" was present");
    expect(segments[2].isHighlighted).toBe(false);
  });

  it("handles adjacent spans correctly without merge conflicts", () => {
    const text = "ABCDEF";
    const spans = [
      { char_span: [0, 3], label: "First" },
      { char_span: [3, 6], label: "Second" },
    ];

    const { segments, outOfRangeCount } = segmentTextWithSpans(text, spans);
    expect(outOfRangeCount).toBe(0);
    expect(segments).toHaveLength(2);
    expect(segments[0].text).toBe("ABC");
    expect(segments[1].text).toBe("DEF");
  });

  it("handles empty spans safely", () => {
    const text = "Testing";
    const spans = [
      { char_span: [2, 2], label: "ZeroLength" },
      { char_span: [5, 3], label: "Inverted" },
    ];

    const { segments, outOfRangeCount } = segmentTextWithSpans(text, spans);
    expect(outOfRangeCount).toBe(2);
    expect(segments).toHaveLength(1);
    expect(segments[0].text).toBe("Testing");
  });

  it("counts out of range spans and ignores them in segments", () => {
    const text = "Short"; // length 5
    const spans = [
      { char_span: [-1, 3], label: "Negative" },
      { char_span: [0, 10], label: "TooFar" },
      { char_span: [1, 4], label: "Valid" },
    ];

    const { segments, outOfRangeCount } = segmentTextWithSpans(text, spans);
    expect(outOfRangeCount).toBe(2);
    expect(segments.find((s) => s.isHighlighted)?.text).toBe("hor");
  });
});

describe("parseSpanQuery", () => {
  it("parses valid span range parameter", () => {
    expect(parseSpanQuery("?span=14-27")).toEqual({ start: 14, end: 27 });
    expect(parseSpanQuery("#/case/C-01/evidence/doc/FIR_01?span=100-250")).toEqual({
      start: 100,
      end: 250,
    });
  });

  it("returns null when span query is missing or malformed", () => {
    expect(parseSpanQuery("?other=123")).toBe(null);
    expect(parseSpanQuery("?span=abc")).toBe(null);
    expect(parseSpanQuery("")).toBe(null);
  });
});

describe("parseRowsQuery", () => {
  it("parses requested row numbers accurately", () => {
    const res = parseRowsQuery("?rows=1,2,5,10");
    expect(res.rowNumbers).toEqual([1, 2, 5, 10]);
    expect(res.isOverLimit).toBe(false);
    expect(res.totalRequested).toBe(4);
  });

  it("flags queries with over 200 rows and truncates to 200", () => {
    const rowList = Array.from({ length: 220 }, (_, i) => i + 1).join(",");
    const res = parseRowsQuery(`?rows=${rowList}`);
    expect(res.totalRequested).toBe(220);
    expect(res.isOverLimit).toBe(true);
    expect(res.rowNumbers).toHaveLength(200);
  });

  it("returns empty safe structure on empty input", () => {
    const res = parseRowsQuery("");
    expect(res.rowNumbers).toEqual([]);
    expect(res.isOverLimit).toBe(false);
  });
});
