import { describe, it, expect } from "vitest";
import {
  segmentTextWithSpans,
  parseSpanQuery,
  parseRowsQuery,
  parseHighlightQuery,
  isRowMatch,
  getMatchingRowIndices,
  normalizeValue,
  isExactOrNormalizedMatch,
  findMatchingColumnsInRow,
  getEvidenceHighlightState,
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

describe("parseHighlightQuery", () => {
  it("parses highlight param from hash or query string", () => {
    expect(parseHighlightQuery("?rows=1,2&highlight=15329318393")).toBe("15329318393");
    expect(parseHighlightQuery("#/case/C-01/evidence/rows/bank?highlight=ACCT123")).toBe("ACCT123");
    expect(parseHighlightQuery("?highlight=9876543210&rows=1,2")).toBe("9876543210");
  });

  it("handles URL encoding safely", () => {
    expect(parseHighlightQuery("?highlight=ACCOUNT%3A123")).toBe("ACCOUNT:123");
  });

  it("returns empty string when highlight is missing", () => {
    expect(parseHighlightQuery("?rows=1,2,3")).toBe("");
    expect(parseHighlightQuery("")).toBe("");
  });
});

describe("isRowMatch", () => {
  it("matches bank rows by from_acct or to_acct exact match", () => {
    const row = { row: 5, from_acct: "109751102939", to_acct: "15329318393", amount: "5000" };
    expect(isRowMatch(row, "15329318393", "bank")).toBe(true);
    expect(isRowMatch(row, "109751102939", "bank")).toBe(true);
    expect(isRowMatch(row, "9999999999", "bank")).toBe(false);
  });

  it("matches cdr rows by a_party or b_party exact match", () => {
    const row = { row: 12, a_party: "8149368998", b_party: "9065627298", duration_sec: 120 };
    expect(isRowMatch(row, "8149368998", "cdr")).toBe(true);
    expect(isRowMatch(row, "9065627298", "cdr")).toBe(true);
    expect(isRowMatch(row, "1234567890", "cdr")).toBe(false);
  });

  it("matches by row number if target is numeric", () => {
    const row = { row: 57, from_acct: "111", to_acct: "222" };
    expect(isRowMatch(row, "57", "bank")).toBe(true);
    expect(isRowMatch(row, "58", "bank")).toBe(false);
  });

  it("handles empty or null row gracefully", () => {
    expect(isRowMatch(null, "123", "bank")).toBe(false);
    expect(isRowMatch({}, "", "bank")).toBe(false);
  });
});

describe("getMatchingRowIndices", () => {
  it("returns matching indices in row order", () => {
    const rows = [
      { row: 1, from_acct: "AAA", to_acct: "BBB" },
      { row: 2, from_acct: "TARGET", to_acct: "CCC" },
      { row: 3, from_acct: "DDD", to_acct: "EEE" },
      { row: 4, from_acct: "FFF", to_acct: "TARGET" },
    ];
    const matches = getMatchingRowIndices(rows, "TARGET", "bank");
    expect(matches).toEqual([1, 3]);
  });

  it("returns empty array when no row matches", () => {
    const rows = [
      { row: 1, a_party: "111", b_party: "222" },
      { row: 2, a_party: "333", b_party: "444" },
    ];
    const matches = getMatchingRowIndices(rows, "999", "cdr");
    expect(matches).toEqual([]);
  });

  it("matches comma-separated row numbers", () => {
    const rows = [
      { row: 10, a_party: "111", b_party: "222" },
      { row: 20, a_party: "333", b_party: "444" },
      { row: 30, a_party: "555", b_party: "666" },
    ];
    const matches = getMatchingRowIndices(rows, "10,30", "cdr");
    expect(matches).toEqual([0, 2]);
  });
});

describe("isExactOrNormalizedMatch", () => {
  it("normalizes float trailing .0, scientific notation, and whitespace", () => {
    expect(isExactOrNormalizedMatch("258506431713.0", "258506431713")).toBe(true);
    expect(isExactOrNormalizedMatch(" 258506431713 ", "258506431713")).toBe(true);
    expect(isExactOrNormalizedMatch("2.58506431713e+11", "258506431713")).toBe(true);
  });

  it("handles country code prefix matching on 10-digit phones", () => {
    expect(isExactOrNormalizedMatch("+918149368998", "8149368998")).toBe(true);
    expect(isExactOrNormalizedMatch("918149368998", "8149368998")).toBe(true);
    expect(isExactOrNormalizedMatch("8149368998", "+918149368998")).toBe(true);
  });

  it("does not match substrings or fuzzy text", () => {
    expect(isExactOrNormalizedMatch("12585064317139", "258506431713")).toBe(false);
    expect(isExactOrNormalizedMatch("2585064317", "258506431713")).toBe(false);
  });
});

describe("findMatchingColumnsInRow", () => {
  it("finds matching target in any column", () => {
    const row = {
      row: 7,
      txn_id: "TXN001",
      from_acct: "111",
      to_acct: "222",
      narration: "258506431713",
    };
    expect(findMatchingColumnsInRow(row, "258506431713")).toEqual(["narration"]);
  });
});

describe("getEvidenceHighlightState", () => {
  it("highlights matching rows when target exists in row columns", () => {
    const rows = [
      { row: 57, from_acct: "109751102939", to_acct: "15329318393" },
      { row: 58, from_acct: "111111111111", to_acct: "222222222222" },
    ];
    const state = getEvidenceHighlightState({
      rows,
      highlightTarget: "15329318393",
      storedRowRefs: [57],
      fileKind: "bank",
    });

    expect(state.bannerType).toBe("value_matches");
    expect(state.isEvidenceMode).toBe(false);
    expect(state.matchCount).toBe(1);
    expect(state.bannerText).toBe("1 matching row highlighted for 15329318393");
    expect(state.highlightedRowIndices).toEqual([0]);
    expect(state.highlightedRowSet.has(57)).toBe(true);
  });

  it("handles failing example 258506431713 by highlighting all stored evidence rows", () => {
    // Concrete failing rows from actual data where target does not sit in returned row cells
    const rows = [
      { row: 7, txn_id: "TXN000234", from_acct: "53710458260", to_acct: "24919058651850" },
      { row: 12, txn_id: "TXN000244", from_acct: "459607124084", to_acct: "46014671511888" },
      { row: 17, txn_id: "TXN000238", from_acct: "72314387443", to_acct: "44671844617327" },
    ];
    const state = getEvidenceHighlightState({
      rows,
      highlightTarget: "258506431713",
      storedRowRefs: [7, 12, 17],
      fileKind: "bank",
    });

    // Instead of saying "No matching row", highlights all stored evidence rows
    expect(state.bannerType).toBe("evidence_rows");
    expect(state.isEvidenceMode).toBe(true);
    expect(state.matchCount).toBe(3);
    expect(state.bannerText).toBe("3 evidence rows highlighted for 258506431713");
    expect(state.highlightedRowIndices).toEqual([0, 1, 2]);
    expect(state.highlightedRowSet.has(7)).toBe(true);
    expect(state.highlightedRowSet.has(12)).toBe(true);
    expect(state.highlightedRowSet.has(17)).toBe(true);
  });

  it("shows no matching row found ONLY when lead has no stored rows", () => {
    const state = getEvidenceHighlightState({
      rows: [],
      highlightTarget: "258506431713",
      storedRowRefs: [],
      fileKind: "bank",
    });

    expect(state.bannerType).toBe("no_matches");
    expect(state.matchCount).toBe(0);
    expect(state.bannerText).toBe("No matching row found for 258506431713.");
  });
});
