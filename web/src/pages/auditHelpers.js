/**
 * Pure helpers for the Admin Audit Log view.
 */

const SENSITIVE_KEY_PATTERN = /(password|pwd|secret|token|hash_password|pbkdf2)/i;

/**
 * Filter out any sensitive fields (passwords, tokens, secrets, password hashes) from audit detail.
 */
export function sanitizeAuditDetail(detail) {
  if (!detail || typeof detail !== "object") {
    return {};
  }

  const clean = {};
  for (const [k, v] of Object.entries(detail)) {
    if (SENSITIVE_KEY_PATTERN.test(k)) {
      continue;
    }
    if (typeof v === "string" && v.startsWith("pbkdf2_")) {
      continue;
    }
    clean[k] = v;
  }
  return clean;
}

/**
 * Format audit detail object for tabular presentation.
 */
export function formatAuditDetail(detail) {
  const sanitized = sanitizeAuditDetail(detail);
  const entries = Object.entries(sanitized);
  if (entries.length === 0) {
    return "-";
  }
  return entries
    .map(([k, v]) => `${k}: ${typeof v === "object" && v !== null ? JSON.stringify(v) : v}`)
    .join(", ");
}

/**
 * Format timestamp string to human-readable ISO slice.
 */
export function formatAuditTime(ts) {
  if (!ts) return "-";
  // Convert 2026-11-27T10:48:00.123456+00:00 to 2026-11-27 10:48:00
  const str = String(ts);
  if (str.includes("T")) {
    return str.slice(0, 19).replace("T", " ");
  }
  return str.slice(0, 19);
}

/**
 * Shorten a 64-character hash to prefix (default 8 chars).
 */
export function formatShortHash(hash, length = 8) {
  if (!hash) return "-";
  const str = String(hash);
  return str.length > length ? str.slice(0, length) : str;
}

/**
 * Filter entries client-side on current page by user, action, or case ID.
 */
export function filterAuditEntries(entries = [], filterText = "") {
  if (!Array.isArray(entries)) return [];
  const term = (filterText || "").trim().toLowerCase();
  if (!term) return entries;

  return entries.filter((e) => {
    const actor = (e.actor || "").toLowerCase();
    const action = (e.action || "").toLowerCase();
    const caseId = (e.case_id || "").toLowerCase();
    const role = (e.role || "").toLowerCase();
    return (
      actor.includes(term) ||
      action.includes(term) ||
      caseId.includes(term) ||
      role.includes(term)
    );
  });
}

/**
 * Calculate pagination metadata.
 */
export function calculatePagination(offset = 0, limit = 50, currentCount = 0, totalCount = null) {
  const safeOffset = Math.max(0, Number(offset) || 0);
  const safeLimit = Math.max(1, Number(limit) || 50);
  const currentPage = Math.floor(safeOffset / safeLimit) + 1;
  const hasPrev = safeOffset > 0;
  const hasNext = totalCount !== null ? safeOffset + currentCount < totalCount : currentCount >= safeLimit;
  const prevOffset = Math.max(0, safeOffset - safeLimit);
  const nextOffset = safeOffset + safeLimit;

  return {
    currentPage,
    hasPrev,
    hasNext,
    prevOffset,
    nextOffset,
    rangeStart: safeOffset + 1,
    rangeEnd: safeOffset + currentCount,
  };
}
