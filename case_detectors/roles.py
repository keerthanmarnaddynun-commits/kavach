"""Role chips assignment for investigative leads based on multi-source intelligence."""

from __future__ import annotations

from typing import Any, Mapping, Sequence


def assign_role_chips(
    person_nodes: Sequence[dict[str, Any] | str],
    financial_rank: Mapping[str, int],
    cut_members: Sequence[str] | set[str],
    mule_accounts_flagged: Sequence[str] | set[str],
    burner_phones_flagged: Sequence[str] | set[str],
    owner_maps: Mapping[str, Any],
) -> dict[str, list[dict[str, str]]]:
    """Assign investigative role chips to individuals based on network and financial leads.

    Chips assigned:
      - PRIORITY_LEAD_MONEY: Financial rank <= 3.
      - CUT_MEMBER: Critical network intermediary in cut set or articulation point lead.
      - MULE_OWNER: Controls a flagged mule lead account (top 8).
      - BURNER_USER: Owns a flagged burner lead phone (top 8).

    Wording strictly uses investigative terminology ('lead', 'chip').

    Args:
        person_nodes: List of person node dicts or person node ID strings.
        financial_rank: Map of person ID to rank integer.
        cut_members: Collection of person IDs in the cut set or articulation set.
        mule_accounts_flagged: Accounts flagged within top 8 mule ranking.
        burner_phones_flagged: Phones flagged within top 8 burner ranking.
        owner_maps: Dict with controlled account and owned phone associations.

    Returns:
        Dict mapping person ID to list of chip dicts with 'chip' and 'reason'.
    """
    flagged_mules = set(str(a) for a in mule_accounts_flagged)
    flagged_burners = set(str(p) for p in burner_phones_flagged)
    cut_set = set(str(c) for c in cut_members)

    person_ids: list[str] = []
    for item in person_nodes:
        if isinstance(item, dict):
            person_ids.append(str(item.get("id", "")))
        else:
            person_ids.append(str(item))

    # Normalize owner maps
    # Could be person -> accounts or account -> person
    ctrl_accts_map: dict[str, set[str]] = {}
    owned_phones_map: dict[str, set[str]] = {}

    raw_ctrl = owner_maps.get("controlled_accounts", {})
    raw_phones = owner_maps.get("owned_phones", {})

    for pid in person_ids:
        ctrl_accts_map[pid] = set()
        owned_phones_map[pid] = set()

    # If person -> items
    for k, v in raw_ctrl.items():
        k_str = str(k)
        if k_str in ctrl_accts_map:
            if isinstance(v, (list, set, tuple)):
                ctrl_accts_map[k_str].update(str(x) for x in v)
            else:
                ctrl_accts_map[k_str].add(str(v))
        else:
            # account -> persons
            acc_str = k_str
            persons = v if isinstance(v, (list, set, tuple)) else [v]
            for p in persons:
                p_str = str(p)
                if p_str in ctrl_accts_map:
                    ctrl_accts_map[p_str].add(acc_str)

    for k, v in raw_phones.items():
        k_str = str(k)
        if k_str in owned_phones_map:
            if isinstance(v, (list, set, tuple)):
                owned_phones_map[k_str].update(str(x) for x in v)
            else:
                owned_phones_map[k_str].add(str(v))
        else:
            # phone -> persons
            ph_str = k_str
            persons = v if isinstance(v, (list, set, tuple)) else [v]
            for p in persons:
                p_str = str(p)
                if p_str in owned_phones_map:
                    owned_phones_map[p_str].add(ph_str)

    results: dict[str, list[dict[str, str]]] = {}

    for pid in sorted(person_ids):
        chips: list[dict[str, str]] = []

        # 1. PRIORITY_LEAD_MONEY
        f_rank = financial_rank.get(pid)
        if f_rank is not None and f_rank <= 3:
            chips.append(
                {
                    "chip": "PRIORITY_LEAD_MONEY",
                    "reason": f"Top-3 financial control rank lead (rank #{f_rank})",
                }
            )

        # 2. CUT_MEMBER
        if pid in cut_set:
            chips.append(
                {
                    "chip": "CUT_MEMBER",
                    "reason": "Critical intermediary lead in network break analysis",
                }
            )

        # 3. MULE_OWNER
        my_accts = ctrl_accts_map.get(pid, set())
        matched_mules = sorted(my_accts & flagged_mules)
        if matched_mules:
            chips.append(
                {
                    "chip": "MULE_OWNER",
                    "reason": f"Controls flagged mule lead account(s): {', '.join(matched_mules)}",
                }
            )

        # 4. BURNER_USER
        my_phones = owned_phones_map.get(pid, set())
        matched_burners = sorted(my_phones & flagged_burners)
        if matched_burners:
            chips.append(
                {
                    "chip": "BURNER_USER",
                    "reason": f"Associated with flagged burner lead phone(s): {', '.join(matched_burners)}",
                }
            )

        results[pid] = chips

    return results
