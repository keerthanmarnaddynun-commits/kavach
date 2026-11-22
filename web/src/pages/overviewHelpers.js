/**
 * Helpers and view models for Overview & Leads page.
 */

export function getLimitations(isAnalyzed, limitations) {
  const ocrSentence = "Typed text only: no OCR";
  if (!isAnalyzed || !limitations || !Array.isArray(limitations)) {
    return [ocrSentence];
  }
  return [...limitations, ocrSentence];
}

export function extractDocId(personId, defaultDocId = "FIR_01") {
  if (!personId || typeof personId !== "string") return defaultDocId;
  const parts = personId.split(":");
  for (const part of parts) {
    if (part.startsWith("FIR_")) {
      return part;
    }
  }
  return defaultDocId;
}

export function buildPriorityLeadsData(moneyFlow, roleChips = {}, structuralMap = {}) {
  if (!moneyFlow || !Array.isArray(moneyFlow)) return [];

  return moneyFlow.map((lead) => {
    const pid = lead.person_id || "";
    const roles = (roleChips && roleChips[pid]) || lead.roles || [];
    const struct = (structuralMap && structuralMap[pid]) || {};

    return {
      ...lead,
      roles,
      degree: typeof struct.degree === "number" ? struct.degree : null,
      betweenness: typeof struct.betweenness === "number" ? struct.betweenness : null,
      eigenvector: typeof struct.eigenvector === "number" ? struct.eigenvector : null,
      composite: typeof struct.composite === "number" ? struct.composite : null,
    };
  });
}
