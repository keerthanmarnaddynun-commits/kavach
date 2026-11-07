"""
Indian identifier extraction with precedence-based conflict resolution (Step 4b).
"""

from __future__ import annotations

from ai_pipeline.validators import (
    Candidate,
    find_aadhaar,
    find_accounts,
    find_amounts,
    find_ifsc,
    find_imeis,
    find_pan,
    find_phones,
    find_upi,
    find_vehicle_plates,
)

PRECEDENCE: tuple[str, ...] = (
    "UPI",
    "AADHAAR",
    "PAN",
    "IFSC",
    "VEHICLE",
    "IMEI",
    "ACCOUNT",
    "AMOUNT",
    "PHONE",
)

_RANK: dict[str, int] = {t: i for i, t in enumerate(PRECEDENCE)}


def find_all_identifiers(text: str) -> list[Candidate]:
    """
    Run all nine identifier finders on original text and resolve overlapping spans
    using the fixed precedence rule.

    Precedence order (highest to lowest):
      UPI > AADHAAR > PAN > IFSC > VEHICLE > IMEI > ACCOUNT > AMOUNT > PHONE

    Same type tie-breaker: longer span stays, then earlier start.
    Candidates that stay receive a flag 'DROPPED_OVERLAP:<TYPE>' for each dropped
    candidate they overlapped with.

    Returns candidate list sorted by start position.
    """
    if not text:
        return []

    # 1. Collect all candidates from the nine finders
    raw_candidates: list[Candidate] = []
    raw_candidates.extend(find_upi(text))
    raw_candidates.extend(find_aadhaar(text))
    raw_candidates.extend(find_pan(text))
    raw_candidates.extend(find_ifsc(text))
    raw_candidates.extend(find_vehicle_plates(text))
    raw_candidates.extend(find_imeis(text))
    raw_candidates.extend(find_accounts(text))
    raw_candidates.extend(find_amounts(text))
    raw_candidates.extend(find_phones(text))

    # Make independent copies of candidates so flags can be mutated safely
    candidates = [
        Candidate(
            type=c.type,
            value=c.value,
            start=c.start,
            end=c.end,
            surface=c.surface,
            valid=c.valid,
            flags=list(c.flags),
        )
        for c in raw_candidates
    ]

    # 2. Sort candidates by priority:
    #    - Lower rank index first (higher precedence)
    #    - For same type: longer span first (-(end - start))
    #    - For same length: earlier start first
    #    - Stable tie-breaker: original index in collection
    sorted_with_idx = sorted(
        enumerate(candidates),
        key=lambda item: (
            _RANK[item[1].type],
            -(item[1].end - item[1].start),
            item[1].start,
            item[0],
        ),
    )

    accepted: list[Candidate] = []

    for _, cand in sorted_with_idx:
        # Check overlap with any accepted candidate (shared characters)
        overlapping_accepted = [
            acc
            for acc in accepted
            if max(acc.start, cand.start) < min(acc.end, cand.end)
        ]
        if overlapping_accepted:
            # cand is dropped; add DROPPED_OVERLAP flag to the candidate(s) that stay
            for acc in overlapping_accepted:
                acc.flags.append(f"DROPPED_OVERLAP:{cand.type}")
        else:
            accepted.append(cand)

    # 3. Sort accepted candidates by start position
    accepted.sort(key=lambda c: c.start)
    return accepted

