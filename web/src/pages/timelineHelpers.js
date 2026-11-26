/**
 * Pure helpers for hand-written SVG bar charts and timeline bucketing.
 */

export function computeMax(items = [], key = "count") {
  if (!items || items.length === 0) return 1;
  const vals = items.map((it) => (typeof it[key] === "number" ? it[key] : 0));
  return Math.max(1, ...vals);
}

export function computeBarLayout(
  items = [],
  key = "count",
  svgWidth = 600,
  svgHeight = 160,
  margin = { top: 20, right: 20, bottom: 30, left: 40 }
) {
  const plotWidth = Math.max(10, svgWidth - margin.left - margin.right);
  const plotHeight = Math.max(10, svgHeight - margin.top - margin.bottom);

  const maxVal = computeMax(items, key);
  const n = items.length;

  if (n === 0) {
    return { bars: [], maxVal, plotWidth, plotHeight, margin };
  }

  const slotWidth = plotWidth / n;
  const barPadding = Math.min(6, slotWidth * 0.2);
  const barWidth = Math.max(2, slotWidth - barPadding);

  const bars = items.map((it, idx) => {
    const val = typeof it[key] === "number" ? it[key] : 0;
    const barHeight = Math.round((val / maxVal) * plotHeight);
    const x = Math.round(margin.left + idx * slotWidth + barPadding / 2);
    const y = Math.round(margin.top + plotHeight - barHeight);

    return {
      x,
      y,
      width: Math.round(barWidth),
      height: Math.max(1, barHeight),
      value: val,
      label: it.t || `Item ${idx + 1}`,
      raw: it,
    };
  });

  return { bars, maxVal, plotWidth, plotHeight, margin };
}

export function formatPaise(paise) {
  if (typeof paise !== "number") return "-";
  return (paise / 100).toFixed(2);
}

export function getGraphNodeId(type, val) {
  if (!val || typeof val !== "string") return null;
  const trimmed = val.trim();
  if (!trimmed) return null;
  if (type === "ACCOUNT") {
    return trimmed.startsWith("ACCOUNT:") ? trimmed : `ACCOUNT:${trimmed}`;
  }
  if (type === "IMEI") {
    return trimmed.startsWith("IMEI:") ? trimmed : `IMEI:${trimmed}`;
  }
  if (type === "PHONE") {
    return trimmed.startsWith("PHONE:") ? trimmed : `PHONE:${trimmed}`;
  }
  if (type === "PERSON") {
    return trimmed.startsWith("PERSON:") ? trimmed : `PERSON:${trimmed}`;
  }
  return null;
}

/**
 * Select at most one example row per category from a list of timeline first-seen rows.
 * Category 1: identifier that HAS a FIR mention (shows FIR group + record group on graph),
 *             preferring one with >= 2 linked entities in FIR.
 * Category 2: identifier with NO FIR mention but with record activity (record group only).
 * Category 3: identifier with neither (cannot exist in First Seen tables, skipped entirely).
 *
 * @param {Array<object>} rows - Array of first-seen items (phones, accounts, or imeis).
 * @returns {{ [identifier: string]: "category1" | "category2" }} - Map of identifier to category.
 */
export function selectExampleRows(rows = []) {
  if (!Array.isArray(rows) || rows.length === 0) {
    return {};
  }

  const markers = {};

  let bestCat1 = null;
  let bestCat1Score = -1;

  let bestCat2 = null;
  let bestCat2Score = -1;

  for (const row of rows) {
    if (!row) continue;
    const id = row.phone || row.account || row.imei || row.id;
    if (!id) continue;

    const firstFir = row.first_fir;
    const hasFir = Boolean(firstFir && firstFir.first_fir_id);
    const relatedCount = (firstFir && (firstFir.related_entities?.length ?? firstFir.related_count)) || 0;

    const firstRecord = row.first_record;
    const hasRecord = Boolean(
      firstRecord && (firstRecord.timestamp || (firstRecord.rows && firstRecord.rows.length > 0))
    );
    const recordCps = (firstRecord && firstRecord.counterparts?.length) || 0;

    if (hasFir) {
      // Category 1: prefer >= 2 linked entities in FIR, then higher count
      let score = relatedCount;
      if (relatedCount >= 2) {
        score += 1000;
      }
      if (recordCps > 0) {
        score += Math.min(recordCps, 10);
      }
      if (score > bestCat1Score) {
        bestCat1Score = score;
        bestCat1 = id;
      }
    } else if (hasRecord) {
      // Category 2: no FIR mention, has record activity
      let score = recordCps;
      if (score > bestCat2Score) {
        bestCat2Score = score;
        bestCat2 = id;
      }
    }
  }

  if (bestCat1) {
    markers[bestCat1] = "category1";
  }
  if (bestCat2 && bestCat2 !== bestCat1) {
    markers[bestCat2] = "category2";
  }

  return markers;
}

/**
 * Module-level in-memory cache for Timeline Insights view selection per caseId.
 */
export const insightViewCache = new Map();

export function getCachedInsightView(caseId) {
  if (!caseId) return "Both";
  return insightViewCache.get(caseId) || "Both";
}

export function setCachedInsightView(caseId, view) {
  if (!caseId) return;
  insightViewCache.set(caseId, view);
}

export function clearCachedInsightView(caseId) {
  if (!caseId) {
    insightViewCache.clear();
  } else {
    insightViewCache.delete(caseId);
  }
}

/**
 * Filter insights based on active view switch: "Both", "Calls only", or "Transfers only".
 * Assigns sequential numbers (1, 2, ...) to the visible insights in that view.
 *
 * @param {Array<object>} insights - Full list of insight objects from API.
 * @param {string} view - "Both" | "Calls only" | "Transfers only".
 * @returns {Array<object>} - Filtered insights with `number` (1-indexed).
 */
export function filterInsightsByView(insights = [], view = "Both") {
  if (!Array.isArray(insights)) return [];

  let filtered = [];
  if (view === "Calls only") {
    filtered = insights.filter((it) => it && it.chart === "calls");
  } else if (view === "Transfers only") {
    filtered = insights.filter((it) => it && it.chart === "transfers");
  } else {
    // "Both": all insights (call_spike, transfer_spike, call_then_transfer, new_and_busy)
    filtered = [...insights];
  }

  return filtered.map((it, idx) => ({
    ...it,
    number: idx + 1,
  }));
}

/**
 * Align calls and transfers onto a unified day axis so their bar positions match 1:1.
 *
 * @param {Array<object>} calls - Daily calls array.
 * @param {Array<object>} transfers - Daily transfers array.
 * @returns {{ alignedCalls: Array<object>, alignedTransfers: Array<object>, allDays: Array<string> }}
 */
export function alignDailyBuckets(calls = [], transfers = []) {
  const callDays = (calls || []).map((c) => (c.t ? c.t.slice(0, 10) : "")).filter(Boolean);
  const transferDays = (transfers || []).map((t) => (t.t ? t.t.slice(0, 10) : "")).filter(Boolean);
  const allDays = Array.from(new Set([...callDays, ...transferDays])).sort();

  const callMap = new Map();
  for (const c of calls || []) {
    if (c && c.t) callMap.set(c.t.slice(0, 10), c);
  }

  const transferMap = new Map();
  for (const t of transfers || []) {
    if (t && t.t) transferMap.set(t.t.slice(0, 10), t);
  }

  const alignedCalls = allDays.map((d) => callMap.get(d) || { t: d, count: 0, voice: 0, sms: 0 });
  const alignedTransfers = allDays.map((d) => transferMap.get(d) || { t: d, count: 0, paise: 0 });

  return { alignedCalls, alignedTransfers, allDays };
}

/**
 * Extract circle annotations for a given chart ("calls" or "transfers")
 * from the list of currently visible insights.
 *
 * @param {Array<object>} insights - Visible insights with `number` field.
 * @param {"calls" | "transfers"} chartType - Target chart.
 * @returns {Array<{ day: string, number: number, insightId: string }>}
 */
export function getChartAnnotations(insights = [], chartType = "calls") {
  if (!Array.isArray(insights)) return [];
  const annotations = [];

  for (const ins of insights) {
    if (!ins) continue;
    if (chartType === "calls") {
      if (ins.chart === "calls" && ins.days && ins.days.length > 0) {
        annotations.push({
          day: ins.days[0],
          number: ins.number,
          insightId: ins.id,
        });
      } else if (ins.chart === "both" && ins.days && ins.days.length > 0) {
        // For call_then_transfer: first day is the call day
        annotations.push({
          day: ins.days[0],
          number: ins.number,
          insightId: ins.id,
        });
      }
    } else if (chartType === "transfers") {
      if (ins.chart === "transfers" && ins.days && ins.days.length > 0) {
        annotations.push({
          day: ins.days[0],
          number: ins.number,
          insightId: ins.id,
        });
      } else if (ins.chart === "both" && ins.days && ins.days.length > 1) {
        // For call_then_transfer: second day is the transfer day
        annotations.push({
          day: ins.days[1],
          number: ins.number,
          insightId: ins.id,
        });
      }
    }
  }

  return annotations;
}

