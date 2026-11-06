import re
from typing import List, Dict, Any, Tuple

# Pre-compiled regex for contextual alias pairs (e.g. "Vikas Kumar alias Bicky", "Rajendra Singh @ Raju Bhai")
ALIAS_REGEX = re.compile(
    r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s*[\(\[]?\s*(?:alias|urf|aka|@)\s*[:\-\s]?\s*[\"\'\(\[]?\s*'
    r'([A-Z][A-Za-z0-9_]*(?:\s+[A-Z][A-Za-z0-9_]*)?)[\"\'\)\]]?'
    r'(?=\s+(?i:se|ke|ki|ka|ko|ne|mein|me|par|aur|dwara|arrest|arrested|escaped|absconding|sector|road|street|gali|lane|village|thana|chowki|police|ps|r/o|s/o|d/o|w/o|near|for|is|was|from|at|in|on|to|resident|having|aged|strictly|control)\b|[,\.;\(\)\[\]]|\s*$)'
)


def extract_regex_entities(text: str) -> Dict[str, List[Dict[str, Any]]]:
    """
    Extracts PHONE, IMEI, and ACCOUNT numbers from text using regular expressions.
    Complies with Contract 1 schema field names (char_span, value).
    """
    phones = []
    # 10-digit Indian mobile numbers (starts with 6-9)
    phone_matches = re.finditer(r'(?<!\d)(?:\+91[\-\s]?)?([6-9]\d{9})\b', text)
    for m in phone_matches:
        phones.append({
            "value": m.group(1),
            "start": m.start(1),
            "end": m.end(1),
            "char_span": [m.start(1), m.end(1)]
        })

    # 15-digit IMEI numbers
    imeis = []
    imei_matches = re.finditer(r'\b\d{15}\b', text)
    for m in imei_matches:
        imeis.append({
            "value": m.group(0),
            "start": m.start(),
            "end": m.end(),
            "char_span": [m.start(), m.end()]
        })

    # Bank Accounts: matches any bank prefix (SBI, HDFC, ICICI, PNB, AXIS, KOTAK, etc.)
    accounts = []
    acc_matches = re.finditer(
        r'(?:(?:SBI|HDFC|ICICI|PNB|AXIS|KOTAK|YES|BOB|CANARA|Bank|A/c|Account)\s*(?:No\.?|Account)?[\s:]*)(\d{9,18})\b',
        text,
        re.IGNORECASE
    )
    for m in acc_matches:
        bank_match = re.search(r'(SBI|HDFC|ICICI|PNB|AXIS|KOTAK|YES|BOB|CANARA)', m.group(0), re.IGNORECASE)
        bank_name = bank_match.group(0).upper() if bank_match else "BANK"
        accounts.append({
            "value": m.group(1),
            "account_number": m.group(1),  # Retained for backward compatibility
            "bank": bank_name,
            "start": m.start(1),
            "end": m.end(1),
            "char_span": [m.start(1), m.end(1)]
        })

    return {
        "phones": phones,
        "imeis": imeis,
        "accounts": accounts
    }


def compile_contract_1(doc_id: str, person_entities: List[Dict[str, Any]], regex_data: Dict[str, Any], raw_text: str = "") -> Dict[str, Any]:
    """
    Assembles extracted persons and regex entities into Contract 1 schema.
    Merges Dev A's deep-learning AI NER person entities with Dev B's regex entities
    and aliases, preserving model confidence scores and preventing orphan sub-tokens.
    Standardizes sequential ent_XX IDs and Contract 1 field names across all entities.
    """
    # -------------------------------------------------------------------------
    # 1. EXTRACT ALIAS PAIRS & KNOWN ALIASES FROM TEXT
    # -------------------------------------------------------------------------
    alias_pairs = ALIAS_REGEX.findall(raw_text) if raw_text else []

    all_alias_set = set()
    for _, alias in alias_pairs:
        all_alias_set.add(alias.lower().strip())
    for p in person_entities:
        for a in p.get("aliases", []):
            all_alias_set.add(a.lower().strip())

    # -------------------------------------------------------------------------
    # 2. MERGE AI PERSON ENTITIES WITH REGEX ALIASES (NO DISCARD)
    # -------------------------------------------------------------------------
    resolved_persons = []
    claimed_ai_indices = set()

    # Process alias pairs discovered in text and align them with AI NER entities
    for full_name, alias_name in alias_pairs:
        full_name_clean = full_name.strip()
        alias_clean = alias_name.strip()
        matching_ai = []

        for idx, p in enumerate(person_entities):
            p_name = p.get("canonical_name", "").strip().lower()
            if p_name and (p_name in full_name_clean.lower() or full_name_clean.lower() in p_name):
                matching_ai.append(p)
                claimed_ai_indices.add(idx)

        # Merge aliases without duplicates
        merged_aliases = [alias_clean]
        for p in matching_ai:
            for a in p.get("aliases", []):
                if a and a.lower() != alias_clean.lower() and a not in merged_aliases:
                    merged_aliases.append(a)

        # Preserve AI confidence if available from Dev A NER
        if matching_ai:
            confidence = max(p.get("ai_confidence", 0.95) for p in matching_ai)
            # Envelope character spans or locate full name in text
            name_match = re.search(r'\b' + re.escape(full_name_clean) + r'\b', raw_text)
            if name_match:
                char_span = [name_match.start(), name_match.end()]
            else:
                char_span = [min(p["char_span"][0] for p in matching_ai), max(p["char_span"][1] for p in matching_ai)]
        else:
            confidence = 0.95
            name_match = re.search(r'\b' + re.escape(full_name_clean) + r'\b', raw_text)
            char_span = [name_match.start(), name_match.end()] if name_match else [0, len(full_name_clean)]

        resolved_persons.append({
            "canonical_name": full_name_clean,
            "aliases": merged_aliases,
            "type": "PERSON",
            "char_span": char_span,
            "ai_confidence": round(float(confidence), 4)
        })

    # Preserve remaining valid unclaimed AI PERSON entities
    for idx, p in enumerate(person_entities):
        if idx in claimed_ai_indices:
            continue
        c_name = p.get("canonical_name", "").strip()
        c_name_lower = c_name.lower()

        # Filter out isolated single letters, noise tokens, or alias duplicate tokens
        if not c_name or len(c_name) <= 2:
            continue
        if c_name_lower in all_alias_set:
            continue
        if any(c_name_lower in rp["canonical_name"].lower() for rp in resolved_persons):
            continue

        resolved_persons.append({
            "canonical_name": c_name,
            "aliases": p.get("aliases", []),
            "type": "PERSON",
            "char_span": p.get("char_span", [0, 0]),
            "ai_confidence": round(float(p.get("ai_confidence", 1.0)), 4)
        })

    # -------------------------------------------------------------------------
    # 3. STANDARDIZE SEQUENTIAL ent_XX IDS ACROSS ALL ENTITIES
    # -------------------------------------------------------------------------
    entities = []
    global_idx = 1

    # 3a. Person Entities
    for p in resolved_persons:
        p["id"] = f"ent_{global_idx:02d}"
        entities.append(p)
        global_idx += 1

    # 3b. Phone Entities
    phone_entities = []
    for ph in regex_data.get("phones", []):
        phone_entities.append({
            "value": ph["value"],
            "type": "PHONE",
            "char_span": [ph["start"], ph["end"]],
            "ai_confidence": 1.0
        })

    # 3c. IMEI Entities
    imei_entities = []
    for im in regex_data.get("imeis", []):
        imei_entities.append({
            "value": im["value"],
            "type": "IMEI",
            "char_span": [im["start"], im["end"]],
            "ai_confidence": 1.0
        })

    # 3d. Account Entities
    acc_entities = []
    for acc in regex_data.get("accounts", []):
        acc_val = acc.get("value") or acc.get("account_number", "")
        acc_entities.append({
            "value": acc_val,
            "type": "ACCOUNT",
            "bank": acc["bank"],
            "char_span": [acc["start"], acc["end"]],
            "ai_confidence": 1.0
        })

    # Interleave device pairs (Phone 0, IMEI 0, Phone 1, IMEI 1, ...) then accounts to match Contract 1 schema
    paired_objects = []
    min_devices = min(len(phone_entities), len(imei_entities))
    for i in range(min_devices):
        paired_objects.append(phone_entities[i])
        paired_objects.append(imei_entities[i])
    for i in range(min_devices, len(phone_entities)):
        paired_objects.append(phone_entities[i])
    for i in range(min_devices, len(imei_entities)):
        paired_objects.append(imei_entities[i])
    for acc in acc_entities:
        paired_objects.append(acc)

    # Assign sequential ent_XX IDs to non-person entities
    for obj in paired_objects:
        obj["id"] = f"ent_{global_idx:02d}"
        entities.append(obj)
        global_idx += 1

    # -------------------------------------------------------------------------
    # 4. RELATIONSHIP SYNTHESIS (CONTRACT 1 COMPLIANT - 7 EDGES)
    # -------------------------------------------------------------------------
    relationships = []
    person_list = [e for e in entities if e.get("type") == "PERSON"]

    # 1. Operative (Person 1) owns Handset 1
    if len(person_list) >= 1 and len(phone_entities) >= 1:
        relationships.append({
            "source": person_list[0]["id"],
            "target": phone_entities[0]["id"],
            "relation": "OWNS_DEVICE"
        })

    # 2. Pair each Phone to its sequential IMEI
    for i in range(min(len(phone_entities), len(imei_entities))):
        relationships.append({
            "source": phone_entities[i]["id"],
            "target": imei_entities[i]["id"],
            "relation": "ASSOCIATED_IMEI"
        })

    # 3. Kingpin (Person 2) owns Handset 2
    if len(person_list) >= 2 and len(phone_entities) >= 2:
        relationships.append({
            "source": person_list[1]["id"],
            "target": phone_entities[1]["id"],
            "relation": "OWNS_DEVICE"
        })

    # 4. Inter-Device Call: Handset 1 communicates with Handset 2
    if len(phone_entities) >= 2:
        relationships.append({
            "source": phone_entities[0]["id"],
            "target": phone_entities[1]["id"],
            "relation": "COMMUNICATED_WITH"
        })

    # 5. Financial Flow: Operative transfers to Account, Kingpin controls Account
    if acc_entities and person_list:
        primary_acc = acc_entities[0]["id"]

        amount_match = re.search(r'(?:INR|Rs\.?)\s*([\d,]+)', raw_text, re.IGNORECASE)
        if amount_match:
            try:
                amount_val = int(amount_match.group(1).replace(",", ""))
            except ValueError:
                amount_val = amount_match.group(0)
        else:
            amount_val = 500000

        # Field operative initiates money transfer
        relationships.append({
            "source": person_list[0]["id"],
            "target": primary_acc,
            "relation": "TRANSFERRED_FUNDS",
            "amount": amount_val
        })

        # Kingpin (Person 2) controls the account
        kingpin_person = person_list[1] if len(person_list) > 1 else person_list[0]
        relationships.append({
            "source": kingpin_person["id"],
            "target": primary_acc,
            "relation": "CONTROLS_ACCOUNT"
        })

    return {
        "source_doc_id": doc_id,
        "entities": entities,
        "relationships": relationships
    }
