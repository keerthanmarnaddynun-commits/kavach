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
    cutDetails: data.cut_details || {},
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

export function generateCandidateBreakPairs(pids = []) {
  if (!Array.isArray(pids) || pids.length < 4) {
    return [];
  }
  const n = pids.length;
  const candidates = [];
  const seen = new Set();

  function addPair(a, b) {
    if (!a || !b || a.length === 0 || b.length === 0) return;
    const setA = new Set(a);
    if (b.some((id) => setA.has(id))) return;
    const key = `${[...a].sort().join(",")}|${[...b].sort().join(",")}`;
    const revKey = `${[...b].sort().join(",")}|${[...a].sort().join(",")}`;
    if (!seen.has(key) && !seen.has(revKey)) {
      seen.add(key);
      candidates.push({ groupA: a, groupB: b });
    }
  }

  // 1. Cross-cluster / distant pairs (interleaved offset)
  for (let i = 0; i < Math.min(n - 4, 8); i++) {
    addPair([pids[i], pids[i + 2]], [pids[i + 1], pids[Math.min(i + 7, n - 1)]]);
  }

  // 2. Adjacent blocks 2 vs 2 and 2 vs 3
  for (let i = 2; i < Math.min(n - 3, 8); i += 2) {
    addPair([pids[i], pids[i + 1]], [pids[i + 2], pids[i + 3]]);
    addPair([pids[i], pids[i + 1]], [pids[i + 2], pids[i + 3], pids[Math.min(i + 4, n - 1)]]);
  }

  // 3. Stride pairs 2 vs 2
  for (let i = 0; i < Math.min(n - 3, 8); i += 2) {
    addPair([pids[i], pids[i + 2]], [pids[i + 1], pids[i + 3]]);
  }

  // 4. Fallback 2 vs 2 sliding pairs across the array
  for (let i = 0; i < Math.min(n - 3, 12); i += 2) {
    for (let j = i + 2; j < Math.min(n - 1, 16); j += 2) {
      addPair([pids[i], pids[i + 1]], [pids[j], pids[j + 1]]);
    }
  }

  // 5. 3 vs 3 pairs
  const half = Math.floor(n / 2);
  for (let i = 0; i < Math.min(half - 2, 4); i++) {
    if (i + 3 <= half && half + 3 <= n) {
      addPair(pids.slice(i, i + 3), pids.slice(half, half + 3));
    }
  }

  return candidates;
}

export function formatExampleLabel(index, groupA = [], groupB = [], result = {}) {
  if (result.direct_link) {
    return `Example ${index}: ${groupA.length} + ${groupB.length} people, direct link`;
  }
  const cutLen = (result.cut && result.cut.length) || (typeof result.size === "number" ? result.size : 0);
  if (result.finite === false || cutLen === 0) {
    return `Example ${index}: ${groupA.length} + ${groupB.length} people, no link`;
  }
  const bridgeText = `${cutLen} bridge${cutLen === 1 ? "" : "s"}`;
  return `Example ${index}: ${groupA.length} + ${groupB.length} people, ${bridgeText}`;
}

export async function findBreakExamples(caseId, people = [], requestFn, isCancelled = () => false) {
  if (!caseId || !Array.isArray(people) || people.length < 4 || typeof requestFn !== "function") {
    return [];
  }

  // Prefer individuals who own devices/phones on the call layer
  const phonePids = people
    .filter((p) => Array.isArray(p.owned_phones) && p.owned_phones.length > 0)
    .map((p) => p.id || p.person_id);

  const candidatePids = phonePids.length >= 4
    ? phonePids
    : people.map((p) => p.id || p.person_id);

  const candidates = generateCandidateBreakPairs(candidatePids);
  const foundSizes = {};
  let noLinkExample = null;
  let directLinkExample = null;
  let calls = 0;

  for (const cand of candidates) {
    if (isCancelled()) break;
    if (calls >= 30) break;
    calls++;

    try {
      const res = await requestFn(`/cases/${caseId}/break`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ group_a: cand.groupA, group_b: cand.groupB }),
      });
      const finite = Boolean(res && res.finite);
      const cut = Array.isArray(res && res.cut) ? res.cut : [];
      const sz = typeof res?.size === "number" ? res.size : cut.length;
      const isDirect = Boolean(res?.direct_link);

      if (isDirect && !directLinkExample) {
        directLinkExample = {
          groupA: cand.groupA,
          groupB: cand.groupB,
          result: res,
        };
      } else if (finite && sz > 0) {
        if (!foundSizes[sz]) {
          foundSizes[sz] = {
            groupA: cand.groupA,
            groupB: cand.groupB,
            result: res,
          };
          if (Object.keys(foundSizes).length >= 3 && noLinkExample) {
            break;
          }
        }
      } else if (!finite && sz === 0 && !isDirect && !noLinkExample) {
        noLinkExample = {
          groupA: cand.groupA,
          groupB: cand.groupB,
          result: res,
        };
      }
    } catch {
      // Ignore individual test failure and continue
    }
  }

  // If no "no link" example was found during candidate evaluation and we have API call budget,
  // evaluate a pair with 2 non-phone owners (who have 0 call-layer connections)
  if (!noLinkExample && calls < 30 && !isCancelled()) {
    const nonPhonePids = people
      .filter((p) => !Array.isArray(p.owned_phones) || p.owned_phones.length === 0)
      .map((p) => p.id || p.person_id);

    if (candidatePids.length >= 2 && nonPhonePids.length >= 2) {
      const gA = [candidatePids[0], candidatePids[1]];
      const gB = [nonPhonePids[0], nonPhonePids[1]];
      calls++;
      try {
        const res = await requestFn(`/cases/${caseId}/break`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ group_a: gA, group_b: gB }),
        });
        if (res && !res.finite && (!res.cut || res.cut.length === 0) && !res.direct_link) {
          noLinkExample = {
            groupA: gA,
            groupB: gB,
            result: res,
          };
        }
      } catch {}
    }
  }

  if (isCancelled && isCancelled()) {
    return [];
  }

  const finiteExamples = Object.values(foundSizes)
    .sort((x, y) => {
      const szX = x.result?.size ?? x.result?.cut?.length ?? 0;
      const szY = y.result?.size ?? y.result?.cut?.length ?? 0;
      return szX - szY;
    })
    .slice(0, 3);

  const combined = [...finiteExamples];
  if (noLinkExample) {
    combined.push(noLinkExample);
  }
  if (directLinkExample) {
    combined.push(directLinkExample);
  }

  return combined.map((item, idx) => ({
    ...item,
    label: formatExampleLabel(idx + 1, item.groupA, item.groupB, item.result),
  }));
}

// Module-level in-memory caches keyed by caseId (plain JS Maps in memory)
export const breakExamplesCache = new Map();
export const inFlightExamples = new Map();
export const breakStateCache = new Map();

export function getCachedBreakExamples(caseId) {
  if (!caseId) return null;
  return breakExamplesCache.get(caseId) || null;
}

export function setCachedBreakExamples(caseId, examples) {
  if (!caseId) return;
  breakExamplesCache.set(caseId, examples);
}

export function clearCachedBreakExamples(caseId) {
  if (caseId) {
    breakExamplesCache.delete(caseId);
    inFlightExamples.delete(caseId);
  } else {
    breakExamplesCache.clear();
    inFlightExamples.clear();
  }
}

export function getCachedBreakState(caseId) {
  if (!caseId) return null;
  return breakStateCache.get(caseId) || null;
}

export function setCachedBreakState(caseId, state) {
  if (!caseId || !state) return;
  if (
    (!state.groupA || state.groupA.length === 0) &&
    (!state.groupB || state.groupB.length === 0) &&
    !state.filterTextA &&
    !state.filterTextB &&
    !state.resultData
  ) {
    breakStateCache.delete(caseId);
    return;
  }
  breakStateCache.set(caseId, state);
}

export function clearCachedBreakState(caseId, part = "all") {
  if (!caseId) return;
  if (part === "all") {
    breakStateCache.delete(caseId);
  } else if (breakStateCache.has(caseId)) {
    const curr = breakStateCache.get(caseId) || {};
    if (part === "A") {
      setCachedBreakState(caseId, {
        ...curr,
        groupA: [],
        resultData: null,
      });
    } else if (part === "B") {
      setCachedBreakState(caseId, {
        ...curr,
        groupB: [],
        resultData: null,
      });
    }
  }
}

export function filterValidPeopleIds(selectedIds = [], people = []) {
  if (!Array.isArray(selectedIds) || selectedIds.length === 0) return [];
  if (!Array.isArray(people) || people.length === 0) return selectedIds;
  const validSet = new Set(people.map((p) => p.id || p.person_id).filter(Boolean));
  return selectedIds.filter((id) => validSet.has(id));
}

