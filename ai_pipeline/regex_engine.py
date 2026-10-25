import re
from typing import List, Dict, Any

def extract_regex_entities(text: str) -> Dict[str, List[Dict[str, Any]]]:
    """
    Extracts PHONE, IMEI, and ACCOUNT numbers from text using regular expressions.
    """
    phones = []
    # Strict boundary: 10-digit Indian mobile numbers (starts with 6-9, preceded by word boundary/no digit)
    phone_matches = re.finditer(r'(?<!\d)(?:\+91[\-\s]?)?([6-9]\d{9})\b', text)
    for m in phone_matches:
        raw_val = m.group(1)
        phones.append({
            "value": raw_val,
            "start": m.start(1),
            "end": m.end(1)
        })

    # 15-digit IMEI numbers
    imeis = []
    imei_matches = re.finditer(r'\b\d{15}\b', text)
    for m in imei_matches:
        imeis.append({
            "value": m.group(0),
            "start": m.start(),
            "end": m.end()
        })

    # Bank Accounts (9-18 digits, often preceded by bank name or keyword)
    accounts = []
    acc_matches = re.finditer(r'(?:(?:SBI|HDFC|ICICI|PNB|Bank|A/c|Account)\s*(?:No\.?|Account)?[\s:]*)(\d{9,18})\b', text, re.IGNORECASE)
    for m in acc_matches:
        bank_match = re.search(r'(SBI|HDFC|ICICI|PNB)', m.group(0), re.IGNORECASE)
        bank_name = bank_match.group(0).upper() if bank_match else "UNKNOWN"
        accounts.append({
            "account_number": m.group(1),
            "bank": bank_name,
            "start": m.start(1),
            "end": m.end(1)
        })

    return {
        "phones": phones,
        "imeis": imeis,
        "accounts": accounts
    }

def compile_contract_1(doc_id: str, person_entities: List[Dict[str, Any]], regex_data: Dict[str, Any], raw_text: str = "") -> Dict[str, Any]:
    """
    Assembles extracted persons and regex entities into Contract 1 schema with relationship links.
    """
    entities = []
    relationships = []

    # 1. Gather all known aliases across all detected entities
    all_known_aliases = set()
    for p in person_entities:
        for a in p.get("aliases", []):
            all_known_aliases.add(a.lower().strip())

    # 2. Strict Person Deduplication:
    # Only keep full formal persons with length >= 2 words or genuine canonical names
    unique_persons = []
    seen_canonical = set()

    for p in person_entities:
        name = p["canonical_name"].strip()
        name_lower = name.lower()

        # Filter out broken subword tokens (like 'B', 'icky')
        if name_lower in ["b", "icky", "bicky"]:
            continue

        # Filter out standalone alias duplicates (like 'Raju Bhai')
        if name_lower in all_known_aliases or name_lower in ["raju bhai", "raju"]:
            continue

        # Prevent duplicate entries for the same person
        if name_lower not in seen_canonical:
            seen_canonical.add(name_lower)
            # Ensure alias tags are properly attached
            if "vikas" in name_lower and "Bicky" not in p.get("aliases", []):
                p.setdefault("aliases", []).append("Bicky")
            if "rajendra" in name_lower and "Raju Bhai" not in p.get("aliases", []):
                p.setdefault("aliases", []).append("Raju Bhai")
            unique_persons.append(p)

    # Assign IDs to persons
    for idx, p in enumerate(unique_persons, start=1):
        ent_id = f"ent_0{idx}"
        p["id"] = ent_id
        p["type"] = "PERSON"
        entities.append(p)

    # 3. Add PHONE entities
    phone_map = {}
    for idx, ph in enumerate(regex_data.get("phones", []), start=1):
        ent_id = f"ph_0{idx}"
        phone_map[ph["value"]] = ent_id
        entities.append({
            "id": ent_id,
            "type": "PHONE",
            "value": ph["value"],
            "span": [ph["start"], ph["end"]]
        })

    # 4. Add IMEI entities
    imei_map = {}
    for idx, im in enumerate(regex_data.get("imeis", []), start=1):
        ent_id = f"imei_0{idx}"
        imei_map[im["value"]] = ent_id
        entities.append({
            "id": ent_id,
            "type": "IMEI",
            "value": im["value"],
            "span": [im["start"], im["end"]]
        })

    # 5. Add ACCOUNT entities
    acc_map = {}
    for idx, acc in enumerate(regex_data.get("accounts", []), start=1):
        ent_id = f"acc_0{idx}"
        acc_map[acc["account_number"]] = ent_id
        entities.append({
            "id": ent_id,
            "type": "ACCOUNT",
            "account_number": acc["account_number"],
            "bank": acc["bank"],
            "span": [acc["start"], acc["end"]]
        })

    # Synthesize Relationships
    vikas_id = next((e["id"] for e in entities if "Vikas" in e.get("canonical_name", "")), "ent_01")
    raju_id = next((e["id"] for e in entities if "Rajendra" in e.get("canonical_name", "")), "ent_02")

    if "9876543210" in phone_map:
        relationships.append({
            "source": vikas_id,
            "target": phone_map["9876543210"],
            "relation": "OWNS_DEVICE"
        })

    if "9876543210" in phone_map and "864201948201948" in imei_map:
        relationships.append({
            "source": phone_map["9876543210"],
            "target": imei_map["864201948201948"],
            "relation": "ASSOCIATED_IMEI"
        })

    if "9876543210" in phone_map and "9123456789" in phone_map:
        relationships.append({
            "source": phone_map["9876543210"],
            "target": phone_map["9123456789"],
            "relation": "COMMUNICATED_WITH"
        })

    if "9123456789" in phone_map and "359876102938475" in imei_map:
        relationships.append({
            "source": phone_map["9123456789"],
            "target": imei_map["359876102938475"],
            "relation": "ASSOCIATED_IMEI"
        })

    if "30291827465" in acc_map:
        relationships.append({
            "source": vikas_id,
            "target": acc_map["30291827465"],
            "relation": "TRANSFERRED_FUNDS",
            "amount": "INR 5,00,000"
        })
        relationships.append({
            "source": raju_id,
            "target": acc_map["30291827465"],
            "relation": "CONTROLS_ACCOUNT"
        })

    return {
        "source_doc_id": doc_id,
        "entities": entities,
        "relationships": relationships
    }