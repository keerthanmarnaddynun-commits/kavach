/**
 * Helpers and filtering for People page.
 */

export function filterPeople(people, filterText) {
  if (!people || !Array.isArray(people)) return [];
  if (!filterText || !filterText.trim()) return people;

  const q = filterText.trim().toLowerCase();

  return people.filter((p) => {
    if ((p.name || "").toLowerCase().includes(q)) return true;
    if ((p.canonical_name || "").toLowerCase().includes(q)) return true;
    if ((p.id || "").toLowerCase().includes(q)) return true;

    if (Array.isArray(p.aliases) && p.aliases.some((a) => String(a).toLowerCase().includes(q))) {
      return true;
    }
    if (Array.isArray(p.owned_phones) && p.owned_phones.some((ph) => String(ph).toLowerCase().includes(q))) {
      return true;
    }
    if (Array.isArray(p.controlled_accounts) && p.controlled_accounts.some((acc) => String(acc).toLowerCase().includes(q))) {
      return true;
    }
    if (Array.isArray(p.documents) && p.documents.some((d) => String(d).toLowerCase().includes(q))) {
      return true;
    }
    if (Array.isArray(p.suggested_same_person)) {
      if (
        p.suggested_same_person.some(
          (s) =>
            (s.other_person_id || "").toLowerCase().includes(q) ||
            (Array.isArray(s.reasons) && s.reasons.some((r) => String(r).toLowerCase().includes(q)))
        )
      ) {
        return true;
      }
    }

    return false;
  });
}
