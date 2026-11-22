/**
 * Formatting and string utility functions.
 */

export function shortenHash(hash, length = 12) {
  if (!hash || typeof hash !== "string") {
    return "";
  }
  return hash.slice(0, length);
}

export function formatCaseFingerprint(isAnalyzed, documentHash) {
  if (!isAnalyzed || !documentHash || typeof documentHash !== "string") {
    return "not analyzed";
  }
  return documentHash.slice(0, 12);
}

export function formatNumber(val) {
  if (val === null || val === undefined) {
    return "0";
  }
  const n = Number(val);
  return Number.isNaN(n) ? "0" : n.toLocaleString("en-US");
}

export function formatDate(isoStr) {
  if (!isoStr) return "";
  try {
    const d = new Date(isoStr);
    return Number.isNaN(d.getTime()) ? isoStr : d.toISOString().replace("T", " ").slice(0, 19);
  } catch {
    return isoStr;
  }
}

export async function copyToClipboard(text) {
  if (navigator && navigator.clipboard && navigator.clipboard.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      return false;
    }
  }
  return false;
}
