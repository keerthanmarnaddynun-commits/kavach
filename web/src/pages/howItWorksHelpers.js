/**
 * Helper functions for the "How the NLP works" walkthrough page.
 */

import snapshot from "../data/pipeline_walkthrough.json";

export function getWalkthroughSnapshot() {
  return snapshot;
}

export function getSampleList(snap = snapshot) {
  if (!snap || !Array.isArray(snap.samples)) return [];
  return snap.samples.map((s) => ({
    sampleId: s.sample_id,
    title: s.title,
    language: s.language,
    charCount: s.char_count,
    sha256: s.sha256,
  }));
}

export function getSampleData(snap = snapshot, sampleId = "FIR_01") {
  if (!snap || !Array.isArray(snap.samples)) return null;
  return snap.samples.find((s) => s.sample_id === sampleId) || snap.samples[0] || null;
}

export function getStepData(sample, stepIndex = 0) {
  if (!sample || !Array.isArray(sample.steps)) return null;
  const idx = Math.max(0, Math.min(stepIndex, sample.steps.length - 1));
  return sample.steps[idx] || null;
}

export function getCodeMap(snap = snapshot) {
  return snap?.code_map || [];
}

export function getTypeStyle(type = "PERSON", source = "model") {
  const isModel = source === "model";
  const borderStyle = isModel ? "2px dashed var(--accent)" : "2px solid var(--record-accent)";

  switch (type) {
    case "PERSON":
      return {
        backgroundColor: "var(--accent-weak)",
        color: "var(--accent)",
        border: borderStyle,
      };
    case "PHONE":
      return {
        backgroundColor: "var(--tag-fir-bg)",
        color: "var(--tag-fir-text)",
        border: borderStyle,
      };
    case "ACCOUNT":
      return {
        backgroundColor: "var(--tag-records-bg)",
        color: "var(--tag-records-text)",
        border: borderStyle,
      };
    case "IMEI":
      return {
        backgroundColor: "var(--highlight)",
        color: "var(--record-accent)",
        border: borderStyle,
      };
    case "AMOUNT":
      return {
        backgroundColor: "var(--highlight)",
        color: "var(--text)",
        border: borderStyle,
      };
    case "ALIAS":
    case "FATHER":
      return {
        backgroundColor: "var(--accent-weak)",
        color: "var(--accent)",
        border: "1px dashed var(--accent)",
      };
    default:
      return {
        backgroundColor: "var(--bg)",
        color: "var(--text)",
        border: "1px solid var(--border)",
      };
  }
}

/**
 * Cut-point based segmenter that partitions text into styled span chunks
 * and evidence sentence highlighting without overlapping tags.
 */
export function splitTextIntoHighlightedSegments(text, rawSpans = [], activeEvidenceSpan = null) {
  if (!text) return [];

  // Filter out evidence spans from entity spans
  const validSpans = (rawSpans || [])
    .filter((s) => s.type !== "EVIDENCE" && s.start >= 0 && s.end <= text.length && s.start < s.end)
    .sort((a, b) => a.start - b.start || b.end - a.end);

  const nonOverlapping = [];
  let lastEnd = -1;
  for (const s of validSpans) {
    if (s.start >= lastEnd) {
      nonOverlapping.push(s);
      lastEnd = s.end;
    }
  }

  const evStart = activeEvidenceSpan ? activeEvidenceSpan[0] : -1;
  const evEnd = activeEvidenceSpan ? activeEvidenceSpan[1] : -1;

  const isInEvidence = (start, end) => {
    if (evStart < 0 || evEnd <= evStart) return false;
    return start < evEnd && end > evStart;
  };

  const cuts = new Set([0, text.length]);
  if (evStart >= 0 && evStart < text.length) cuts.add(evStart);
  if (evEnd > 0 && evEnd <= text.length) cuts.add(evEnd);

  for (const s of nonOverlapping) {
    cuts.add(s.start);
    cuts.add(s.end);
  }

  const sortedCuts = Array.from(cuts).sort((a, b) => a - b);
  const segments = [];

  for (let i = 0; i < sortedCuts.length - 1; i++) {
    const segStart = sortedCuts[i];
    const segEnd = sortedCuts[i + 1];
    if (segStart >= segEnd) continue;

    const segText = text.slice(segStart, segEnd);
    const matchingSpan = nonOverlapping.find((s) => s.start <= segStart && s.end >= segEnd);
    const inEv = isInEvidence(segStart, segEnd);

    segments.push({
      start: segStart,
      end: segEnd,
      text: segText,
      isSpan: !!matchingSpan,
      span: matchingSpan || null,
      inEvidence: inEv,
    });
  }

  return segments;
}
