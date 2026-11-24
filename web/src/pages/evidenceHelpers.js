/**
 * Pure segmentation and query parsing helpers for Evidence Viewer.
 */

export function segmentTextWithSpans(text, spans = []) {
  if (typeof text !== "string") {
    return { segments: [], outOfRangeCount: 0 };
  }
  const L = text.length;
  if (L === 0) {
    return { segments: [], outOfRangeCount: 0 };
  }

  let outOfRangeCount = 0;
  const validSpans = [];

  for (const span of spans) {
    if (!span) continue;
    const charSpan = span.char_span || [span.start, span.end];
    if (!Array.isArray(charSpan) || charSpan.length < 2) {
      outOfRangeCount++;
      continue;
    }
    const [start, end] = charSpan;
    if (
      typeof start !== "number" ||
      typeof end !== "number" ||
      start < 0 ||
      end > L ||
      start >= end
    ) {
      outOfRangeCount++;
      continue;
    }
    validSpans.push({
      ...span,
      start,
      end,
    });
  }

  const boundarySet = new Set([0, L]);
  for (const s of validSpans) {
    boundarySet.add(s.start);
    boundarySet.add(s.end);
  }
  const boundaries = Array.from(boundarySet).sort((a, b) => a - b);

  const segments = [];
  for (let i = 0; i < boundaries.length - 1; i++) {
    const bStart = boundaries[i];
    const bEnd = boundaries[i + 1];
    const segText = text.slice(bStart, bEnd);
    const coveringSpans = validSpans.filter((s) => s.start <= bStart && s.end >= bEnd);

    segments.push({
      start: bStart,
      end: bEnd,
      text: segText,
      spans: coveringSpans,
      isHighlighted: coveringSpans.length > 0,
      isOverlap: coveringSpans.length > 1,
    });
  }

  return { segments, outOfRangeCount };
}

export function parseSpanQuery(hashOrSearch) {
  if (!hashOrSearch || typeof hashOrSearch !== "string") return null;
  const match = hashOrSearch.match(/[?&]span=(\d+)-(\d+)/) || hashOrSearch.match(/^span=(\d+)-(\d+)/);
  if (!match) return null;
  const start = parseInt(match[1], 10);
  const end = parseInt(match[2], 10);
  if (Number.isNaN(start) || Number.isNaN(end)) return null;
  return { start, end };
}

export function parseRowsQuery(hashOrSearch) {
  if (!hashOrSearch || typeof hashOrSearch !== "string") {
    return { rowNumbers: [], isOverLimit: false, totalRequested: 0, rawParam: "" };
  }
  const match = hashOrSearch.match(/[?&]rows=([^&]+)/) || hashOrSearch.match(/^rows=([^&]+)/);
  if (!match) {
    return { rowNumbers: [], isOverLimit: false, totalRequested: 0, rawParam: "" };
  }

  const rawParam = match[1];
  const parts = rawParam.split(",").map((s) => s.trim()).filter(Boolean);
  const rowNumbers = parts
    .map((p) => parseInt(p, 10))
    .filter((n) => !Number.isNaN(n) && n > 0);

  const totalRequested = rowNumbers.length;
  const isOverLimit = totalRequested > 200;

  return {
    rowNumbers: isOverLimit ? rowNumbers.slice(0, 200) : rowNumbers,
    isOverLimit,
    totalRequested,
    rawParam,
  };
}

export function parseHighlightQuery(hashOrSearch) {
  if (!hashOrSearch || typeof hashOrSearch !== "string") return "";
  const match = hashOrSearch.match(/[?&]highlight=([^&]+)/) || hashOrSearch.match(/^highlight=([^&]+)/);
  if (!match) return "";
  try {
    return decodeURIComponent(match[1].trim());
  } catch {
    return match[1].trim();
  }
}

/**
 * Normalizes values for comparison (strips trailing .0, whitespace, parses scientific notation).
 */
export function normalizeValue(val) {
  if (val === null || val === undefined) return "";
  let s = String(val).trim();
  if (s.endsWith(".0")) s = s.slice(0, -2);
  // Scientific notation handling if present (e.g. 2.58506431713e+11)
  if (/^[+-]?\d+(\.\d+)?[eE][+-]?\d+$/.test(s)) {
    try {
      const num = Number(s);
      if (!Number.isNaN(num) && Number.isFinite(num)) {
        s = BigInt(Math.round(num)).toString();
      }
    } catch {}
  }
  return s;
}

/**
 * Exact or normalized value comparison (handles string/int, float trailing .0, scientific notation,
 * and 10-digit vs country-code prefixed 12-digit phone numbers). Exact match only, no substring/fuzzy.
 */
export function isExactOrNormalizedMatch(cellVal, target) {
  if (cellVal === null || cellVal === undefined || !target) return false;
  const rawCell = String(cellVal).trim();
  const rawTarget = String(target).trim();
  if (!rawCell || !rawTarget) return false;

  // Direct exact match
  if (rawCell === rawTarget) return true;

  // Normalized string match (e.g. float trailing .0, scientific notation)
  const normCell = normalizeValue(rawCell);
  const normTarget = normalizeValue(rawTarget);
  if (normCell === normTarget) return true;

  // Phone / account digit-only exact match (e.g. country code +91 or 91 on 10-digit number)
  const digitsCell = rawCell.replace(/\D/g, "");
  const digitsTarget = rawTarget.replace(/\D/g, "");
  if (digitsCell && digitsTarget) {
    if (digitsCell === digitsTarget) return true;
    if (digitsCell.length === 12 && digitsCell.startsWith("91") && digitsCell.slice(2) === digitsTarget) {
      return true;
    }
    if (digitsTarget.length === 12 && digitsTarget.startsWith("91") && digitsTarget.slice(2) === digitsCell) {
      return true;
    }
  }

  return false;
}

/**
 * Checks all columns of a CSV row for exact or normalized match against target.
 * Returns array of matching column names.
 */
export function findMatchingColumnsInRow(row, target) {
  if (!row || !target) return [];
  const matchingCols = [];
  for (const [colKey, colVal] of Object.entries(row)) {
    if (colKey === "row") continue;
    if (isExactOrNormalizedMatch(colVal, target)) {
      matchingCols.push(colKey);
    }
  }
  return matchingCols;
}

/**
 * Matches a CSV row against a highlight target (phone or account, across columns, or row number).
 * Fixed columns checked first, then other columns of that row.
 * Exact match only (no substring/fuzzy).
 */
export function isRowMatch(row, highlightTarget, fileKind = "") {
  if (!row || !highlightTarget) return false;
  const target = String(highlightTarget).trim();
  if (!target) return false;

  const kind = String(fileKind).toLowerCase();

  // 1. Check primary columns for fileKind
  if (kind.includes("bank")) {
    if (isExactOrNormalizedMatch(row.from_acct, target) || isExactOrNormalizedMatch(row.to_acct, target)) {
      return true;
    }
  } else if (kind.includes("cdr")) {
    if (isExactOrNormalizedMatch(row.a_party, target) || isExactOrNormalizedMatch(row.b_party, target)) {
      return true;
    }
  }

  // 2. Check across all other columns of that row
  const matchedCols = findMatchingColumnsInRow(row, target);
  if (matchedCols.length > 0) return true;

  // 3. Also check if target is a row number
  const targetNum = parseInt(target, 10);
  if (!Number.isNaN(targetNum) && String(targetNum) === target) {
    if (row.row === targetNum) return true;
  }

  return false;
}

export function getMatchingRowIndices(rows = [], highlightTarget = "", fileKind = "") {
  if (!rows || rows.length === 0 || !highlightTarget) return [];
  const target = String(highlightTarget).trim();
  if (!target) return [];

  // Check if target is comma-separated row numbers e.g. "57,59,62"
  const rowNumberSet = new Set();
  const parts = target.split(",").map((s) => s.trim());
  const allNumeric = parts.length > 0 && parts.every((p) => /^\d+$/.test(p) && p.length < 8);
  if (allNumeric) {
    for (const p of parts) {
      rowNumberSet.add(parseInt(p, 10));
    }
  }

  const matchingIndices = [];
  for (let i = 0; i < rows.length; i++) {
    const r = rows[i];
    if (rowNumberSet.has(r.row)) {
      matchingIndices.push(i);
    } else if (isRowMatch(r, target, fileKind)) {
      matchingIndices.push(i);
    }
  }
  return matchingIndices;
}

/**
 * Pure state calculation for Evidence Rows highlighting banner and row set.
 * Rules:
 * - If rows contain the target value (primary or other columns, normalized): highlight those rows ("N matching rows highlighted").
 * - If stored rows do NOT contain the target value (related transactions/counterparties/layering chain):
 *   highlight ALL stored evidence rows ("N evidence rows highlighted").
 * - "No matching row found" appears ONLY when the lead has no stored rows at all.
 */
export function getEvidenceHighlightState({
  rows = [],
  highlightTarget = "",
  storedRowRefs = [],
  fileKind = "",
}) {
  if (!highlightTarget) {
    return {
      hasTarget: false,
      bannerType: "none",
      bannerText: "",
      highlightedRowIndices: [],
      highlightedRowSet: new Set(),
      isEvidenceMode: false,
      matchCount: 0,
    };
  }

  const target = String(highlightTarget).trim();

  // Find all rows that contain the lead value in ANY column
  const valueMatchIndices = [];
  for (let i = 0; i < rows.length; i++) {
    if (isRowMatch(rows[i], target, fileKind)) {
      valueMatchIndices.push(i);
    }
  }

  // Case 1: Specific rows contain the target value
  if (valueMatchIndices.length > 0) {
    const count = valueMatchIndices.length;
    return {
      hasTarget: true,
      bannerType: "value_matches",
      bannerText: `${count} matching row${count === 1 ? "" : "s"} highlighted for ${target}`,
      highlightedRowIndices: valueMatchIndices,
      highlightedRowSet: new Set(valueMatchIndices.map((idx) => rows[idx]?.row).filter((r) => r !== undefined)),
      isEvidenceMode: false,
      matchCount: count,
    };
  }

  // Case 2: Stored rows do not contain the lead value (related transactions, e.g. counterparties or layering chain)
  // Highlight ALL stored evidence rows for that lead
  if (rows.length > 0 && storedRowRefs && storedRowRefs.length > 0) {
    const count = rows.length;
    const allIndices = rows.map((_, i) => i);
    return {
      hasTarget: true,
      bannerType: "evidence_rows",
      bannerText: `${count} evidence row${count === 1 ? "" : "s"} highlighted for ${target}`,
      highlightedRowIndices: allIndices,
      highlightedRowSet: new Set(rows.map((r) => r.row).filter((r) => r !== undefined)),
      isEvidenceMode: true,
      matchCount: count,
    };
  }

  // Case 3: Lead has no stored rows at all
  return {
    hasTarget: true,
    bannerType: "no_matches",
    bannerText: `No matching row found for ${target}.`,
    highlightedRowIndices: [],
    highlightedRowSet: new Set(),
    isEvidenceMode: false,
    matchCount: 0,
  };
}
