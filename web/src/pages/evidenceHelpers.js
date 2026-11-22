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
