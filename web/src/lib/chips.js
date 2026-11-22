/**
 * Pure helpers for role chip normalization and display.
 */

export function chipLabel(chip) {
  if (chip === null || chip === undefined) {
    return "";
  }
  if (typeof chip === "object") {
    return chip.chip || chip.name || chip.role || "";
  }
  return String(chip);
}

export function chipTooltip(chip) {
  if (typeof chip === "object" && chip !== null) {
    return chip.reason || undefined;
  }
  return undefined;
}
