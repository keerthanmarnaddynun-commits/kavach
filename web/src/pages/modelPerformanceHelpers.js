/**
 * Helper functions for the Model Performance page.
 * Extracts, filters, sorts and formats data from model_performance.json snapshot.
 */
import snapshot from "../data/model_performance.json";

/**
 * Returns raw snapshot data (single source of truth).
 */
export function getSnapshot() {
  return snapshot || {};
}

/**
 * Formats a ratio/number as a percentage string (e.g. 0.7891 -> "78.9%").
 */
export function formatPercent(val) {
  if (val === null || val === undefined || isNaN(val)) return "-";
  return `${(Number(val) * 100).toFixed(1)}%`;
}

/**
 * Formats a metric score to 4 decimal places (e.g. 0.7891).
 */
export function formatScore(val) {
  if (val === null || val === undefined || isNaN(val)) return "-";
  return Number(val).toFixed(4);
}

/**
 * Formats latency milliseconds (e.g. 659.61 -> "659.6 ms").
 */
export function formatMs(val) {
  if (val === null || val === undefined || isNaN(val)) return "-";
  return `${Number(val).toFixed(1)} ms`;
}

/**
 * Block A: Extracts headline strip data.
 */
export function getHeadlineData(snap = snapshot) {
  if (!snap || !snap.headline) {
    return {
      heldOut: { mentionsF1: "-", relationsF1: "-" },
      syntheticTest: { mentionsF1: "-", relationsF1: "-" },
      caption: "-",
      provenance: "-",
    };
  }
  const h = snap.headline;
  return {
    heldOut: {
      mentionsF1: formatScore(h.held_out?.mention_strict_f1),
      relationsF1: formatScore(h.held_out?.relation_micro_f1),
      mentionsP: formatScore(h.held_out?.mention_strict_p),
      mentionsR: formatScore(h.held_out?.mention_strict_r),
      relationsP: formatScore(h.held_out?.relation_micro_p),
      relationsR: formatScore(h.held_out?.relation_micro_r),
    },
    syntheticTest: {
      mentionsF1: formatScore(h.synthetic_test?.mention_strict_f1),
      relationsF1: formatScore(h.synthetic_test?.relation_micro_f1),
    },
    caption: h.dataset_sizes?.caption || "",
    provenance: h.provenance_caption || "",
  };
}

/**
 * Block B & C: Filter and sort per-type items.
 * @param {Array} items - List of type objects from snapshot.
 * @param {string} metricMode - "strict" | "lenient"
 * @param {string} sortKey - "name" | "precision" | "recall" | "f1" | "gold"
 * @param {string} sortDir - "asc" | "desc"
 */
export function getPerTypeItems(items = [], metricMode = "strict", sortKey = "f1", sortDir = "desc") {
  if (!Array.isArray(items)) return [];

  const mapped = items.map((item) => {
    const scores = item[metricMode] || item.strict || {};
    const name = item.type || item.relation || "";
    return {
      name,
      gold: item.gold ?? 0,
      predicted: item.predicted ?? 0,
      precision: scores.precision ?? 0,
      recall: scores.recall ?? 0,
      f1: scores.f1 ?? 0,
      tp: scores.tp ?? 0,
      fp: scores.fp ?? 0,
      fn: scores.fn ?? 0,
    };
  });

  return mapped.sort((a, b) => {
    let valA = a[sortKey];
    let valB = b[sortKey];
    if (sortKey === "name") {
      valA = a.name.toLowerCase();
      valB = b.name.toLowerCase();
      return sortDir === "asc" ? valA.localeCompare(valB) : valB.localeCompare(valA);
    }
    const numA = Number(valA) || 0;
    const numB = Number(valB) || 0;
    return sortDir === "asc" ? numA - numB : numB - numA;
  });
}

/**
 * Block D: Error breakdown helper.
 * @param {Object} errorBreakdown - error_breakdown block from snapshot
 * @param {string} target - "mentions" | "relations"
 * @param {string} errorKind - "fp" | "fn"
 */
export function getErrorClasses(errorBreakdown = snapshot?.error_breakdown, target = "mentions", errorKind = "fp") {
  if (!errorBreakdown || !errorBreakdown[target]) return [];
  const key = errorKind === "fp" ? "fp_classes" : "fn_classes";
  const list = errorBreakdown[target][key] || [];
  return list.map((item) => ({
    className: item.class_name,
    count: item.count,
    pct: item.pct,
    examples: item.examples || [],
  }));
}

/**
 * Block E: Generalisation gap data helper.
 */
export function getGeneralisationGapData(snap = snapshot) {
  if (!snap || !snap.generalisation_gap) {
    return { comparison: [], provenance: "" };
  }
  const gg = snap.generalisation_gap;
  return {
    comparison: gg.comparison || [],
    provenance: gg.provenance_caption || "",
  };
}

/**
 * Block F: Baseline models helper.
 * @param {Object} baselines - baselines block from snapshot
 * @param {string} metricKey - "f1" | "precision" | "recall"
 */
export function getBaselineModels(baselines = snapshot?.baselines, metricKey = "f1") {
  if (!baselines || !Array.isArray(baselines.models)) {
    return { models: [], caption: "", provenance: "" };
  }
  const models = baselines.models.map((m) => ({
    name: m.name,
    modelId: m.model_id,
    run: m.run,
    value: m[metricKey] ?? 0,
    precision: m.precision ?? 0,
    recall: m.recall ?? 0,
    f1: m.f1 ?? 0,
    tp: m.tp ?? 0,
    fp: m.fp ?? 0,
    fn: m.fn ?? 0,
  }));
  return {
    models,
    caption: baselines.dataset_caption || "",
    provenance: baselines.provenance_caption || "",
  };
}

/**
 * Block G: Latency stages helper.
 */
export function getSpeedData(speed = snapshot?.speed) {
  if (!speed || !Array.isArray(speed.stages)) {
    return { stages: [], total: { mean_ms: 0, p95_ms: 0 }, provenance: "", modelLoadMs: 0 };
  }
  return {
    stages: speed.stages,
    total: speed.total || { mean_ms: 0, p95_ms: 0 },
    provenance: speed.provenance_caption || "",
    modelLoadMs: speed.model_load_ms || 0,
  };
}
