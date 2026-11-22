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
