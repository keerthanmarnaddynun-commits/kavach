/**
 * Pure helpers for Network Break Analysis page: group validation and result view-model.
 */

export function validateBreakGroups(groupA = [], groupB = []) {
  if (!Array.isArray(groupA) || groupA.length === 0) {
    return { valid: false, error: "Group A must contain at least one person." };
  }
  if (!Array.isArray(groupB) || groupB.length === 0) {
    return { valid: false, error: "Group B must contain at least one person." };
  }
  if (groupA.length > 200) {
    return { valid: false, error: "Group A cannot exceed 200 members." };
  }
  if (groupB.length > 200) {
    return { valid: false, error: "Group B cannot exceed 200 members." };
  }

  const setA = new Set(groupA);
  const overlap = groupB.filter((id) => setA.has(id));
  if (overlap.length > 0) {
    return {
      valid: false,
      error: `Groups cannot overlap: ${overlap.join(", ")} appear in both groups.`,
    };
  }

  return { valid: true, error: null };
}

export function buildBreakViewModel(data) {
  if (!data) return null;

  const isFinite = Boolean(data.finite);
  const cut = Array.isArray(data.cut) ? data.cut : [];
  const isEmptyCut = !isFinite || cut.length === 0;

  return {
    finite: isFinite,
    size: typeof data.size === "number" ? data.size : cut.length,
    cut,
    directLink: Boolean(data.direct_link),
    bridgingPhones: Array.isArray(data.bridging_unowned_phones)
      ? data.bridging_unowned_phones
      : [],
    note: data.note || "",
    disclaimer: data.disclaimer || "",
    isEmptyCut,
    emptyCutMessage:
      "No observed link between the groups on the call layer. This does not mean the groups are unconnected.",
  };
}
