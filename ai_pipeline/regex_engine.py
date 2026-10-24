"""
regex_engine.py
Implements:
1. extract_regex_entities(raw_text: str) -> dict
   Extracts PHONE, IMEI, ACCOUNT with exact char_spans and bank detection.
2. compile_contract_1(doc_id: str, persons: list, objects: dict, raw_text: str = "") -> dict
   Combines Dev A persons and Dev B objects, assigns deterministic IDs (ent_01, ent_02...),
   and resolves relationships matching contracts/ai_output_schema.json.
"""

import re
from typing import Dict, List, Any


def extract_regex_entities(raw_text: str) -> Dict[str, Any]:
    """
    Extracts PHONE (10 digits), IMEI (15 digits), and ACCOUNT (9-18 digits)
    with exact character spans for BSA legal compliance.
    """
    phones = []
    imeis = []
    accounts = []

    # 1. PHONE (10 contiguous digits starting with 6, 7, 8, or 9)
    phone_pattern = r'\b([6-9]\d{9})\b'
    for match in re.finditer(phone_pattern, raw_text):
        phones.append({
            "value": match.group(1),
            "type": "PHONE",
            "char_span": [match.start(), match.end()],
            "ai_confidence": 1.0
        })

    # 2. IMEI (15 contiguous digits)
    imei_pattern = r'\b(\d{15})\b'
    for match in re.finditer(imei_pattern, raw_text):
        imeis.append({
            "value": match.group(1),
            "type": "IMEI",
            "char_span": [match.start(), match.end()],
            "ai_confidence": 1.0
        })

    # 3. ACCOUNT (Bank accounts, 9 to 18 digits, with bank name detection)
    acct_pattern = r'(?:\b(SBI|HDFC|ICICI|PNB|AXIS|BOB)\s+Account\s+|Account\s+|A/C\s+)(\d{9,18})\b'
    for match in re.finditer(acct_pattern, raw_text, re.IGNORECASE):
        bank = match.group(1).upper() if match.group(1) else "UNKNOWN"
        acct_no = match.group(2)

        # Avoid classifying 15-digit IMEIs as bank accounts
        if len(acct_no) == 15 and any(im["value"] == acct_no for im in imeis):
            continue

        accounts.append({
            "value": acct_no,
            "type": "ACCOUNT",
            "bank": bank,
            "char_span": [match.start(2), match.end(2)],
            "ai_confidence": 1.0
        })

    return {
        "phones": phones,
        "imeis": imeis,
        "accounts": accounts
    }


def compile_contract_1(doc_id: str, persons: List[Dict[str, Any]], objects: Dict[str, Any], raw_text: str = "") -> Dict[str, Any]:
    """
    Merges entities, re-numbers them sequentially (ent_01, ent_02, ...),
    and derives relationships matching contracts/ai_output_schema.json.
    """
    all_entities = []
    id_counter = 1

    # 1. Assign sequential IDs to PERSON nodes
    person_nodes = []
    for p in persons:
        ent = dict(p)
        ent["id"] = f"ent_{id_counter:02d}"
        id_counter += 1
        person_nodes.append(ent)
        all_entities.append(ent)

    # 2. Assign sequential IDs to PHONE nodes
    phone_nodes = []
    for ph in objects.get("phones", []):
        ent = dict(ph)
        ent["id"] = f"ent_{id_counter:02d}"
        id_counter += 1
        phone_nodes.append(ent)
        all_entities.append(ent)

    # 3. Assign sequential IDs to IMEI nodes
    imei_nodes = []
    for im in objects.get("imeis", []):
        ent = dict(im)
        ent["id"] = f"ent_{id_counter:02d}"
        id_counter += 1
        imei_nodes.append(ent)
        all_entities.append(ent)

    # 4. Assign sequential IDs to ACCOUNT nodes
    account_nodes = []
    for ac in objects.get("accounts", []):
        ent = dict(ac)
        ent["id"] = f"ent_{id_counter:02d}"
        id_counter += 1
        account_nodes.append(ent)
        all_entities.append(ent)

    # 5. Extract Relationships
    relationships = []

    def get_person(name_substr: str):
        for p in person_nodes:
            if name_substr.lower() in p["canonical_name"].lower():
                return p
            for alias in p.get("aliases", []):
                if name_substr.lower() in alias.lower():
                    return p
        return None

    def get_phone(val: str):
        return next((p for p in phone_nodes if p["value"] == val), None)

    def get_account(val: str):
        return next((a for a in account_nodes if a["value"] == val), None)

    # A. ASSOCIATED_IMEI (PHONE -> IMEI) via text proximity
    for ph in phone_nodes:
        p_val = ph["value"]
        p_match = re.search(re.escape(p_val), raw_text)
        if p_match:
            window = raw_text[p_match.end():min(len(raw_text), p_match.end() + 50)]
            for im in imei_nodes:
                if im["value"] in window:
                    rel = {
                        "source": ph["id"],
                        "target": im["id"],
                        "relation": "ASSOCIATED_IMEI"
                    }
                    if rel not in relationships:
                        relationships.append(rel)

    # B. OWNS_DEVICE (PERSON -> PHONE) via distance/sentence proximity
    for per in person_nodes:
        names_to_check = [per["canonical_name"]] + per.get("aliases", [])
        for name in names_to_check:
            n_match = re.search(re.escape(name), raw_text)
            if not n_match:
                continue
            for ph in phone_nodes:
                ph_match = re.search(re.escape(ph["value"]), raw_text)
                if not ph_match:
                    continue
                dist = ph_match.start() - n_match.end()
                if 0 < dist < 170:
                    rel = {
                        "source": per["id"],
                        "target": ph["id"],
                        "relation": "OWNS_DEVICE"
                    }
                    if rel not in relationships:
                        relationships.append(rel)

    # C. COMMUNICATED_WITH (PHONE -> PHONE)
    cdr_pattern = r'(\d{10})[^\.\n]*?(?:contact|call|connected|communicat)[^\.\n]*?(\d{10})'
    for match in re.finditer(cdr_pattern, raw_text, re.IGNORECASE):
        src_ph = get_phone(match.group(1))
        tgt_ph = get_phone(match.group(2))
        if src_ph and tgt_ph:
            rel = {
                "source": src_ph["id"],
                "target": tgt_ph["id"],
                "relation": "COMMUNICATED_WITH"
            }
            if rel not in relationships:
                relationships.append(rel)

    # D. TRANSFERRED_FUNDS (PERSON -> ACCOUNT with amount)
    funds_pattern = r'([A-Z][a-z]+)[^\.\n]*?(?:INR|Rs\.?)\s*([\d,]+)[^\.\n]*?(?:transfer|sent|deposit)[^\.\n]*?(\d{9,18})'
    for match in re.finditer(funds_pattern, raw_text, re.IGNORECASE):
        src_name = match.group(1).strip()
        amt_raw = match.group(2).replace(",", "")
        acct_val = match.group(3).strip()

        src_p = get_person(src_name)
        tgt_acc = get_account(acct_val)
        if src_p and tgt_acc:
            try:
                amt = int(amt_raw)
            except ValueError:
                amt = amt_raw
            rel = {
                "source": src_p["id"],
                "target": tgt_acc["id"],
                "relation": "TRANSFERRED_FUNDS",
                "amount": amt
            }
            if rel not in relationships:
                relationships.append(rel)

    # E. CONTROLS_ACCOUNT (PERSON -> ACCOUNT)
    control_pattern = r'(\d{9,18})[^\.\n]*?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)[^\.\n]*?(?:dwara|strictly control|controls|held by)'
    for match in re.finditer(control_pattern, raw_text, re.IGNORECASE):
        acct_val = match.group(1).strip()
        person_name = match.group(2).strip()

        tgt_acc = get_account(acct_val)
        src_p = get_person(person_name)
        if tgt_acc and src_p:
            rel = {
                "source": src_p["id"],
                "target": tgt_acc["id"],
                "relation": "CONTROLS_ACCOUNT"
            }
            if rel not in relationships:
                relationships.append(rel)

    return {
        "source_doc_id": doc_id,
        "entities": all_entities,
        "relationships": relationships
    }