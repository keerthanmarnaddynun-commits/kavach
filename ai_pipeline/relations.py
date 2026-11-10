"""
Step 6b-2: Rule-based relation extraction into Contract 1 v1.1 format.
Implements sentence splitting (with abbreviation/initial/number guards),
grouped multilingual cue lexicons (English, Roman Hinglish, Devanagari),
direction disambiguation, suspect-only ownership/control/transfer filtering,
2-sentence suspect carry-forward, and cash-recovery guards.
"""
from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# Abbreviations (never trigger sentence splits after ".")
# ---------------------------------------------------------------------------
ABBREVIATIONS: frozenset[str] = frozenset({
    "no", "rs", "inr", "u/s", "dy", "sp", "sr", "jr",
    "s/o", "d/o", "w/o", "c/o", "r/o",
    "shri", "sri", "shree", "smt", "sh", "mr", "mrs", "ms", "dr", "prof",
    "insp", "si", "asi", "hc", "vs", "etc", "dist", "ps", "st", "rd",
    "mohd", "md", "col", "lt", "capt", "fig", "sec",
})

# ---------------------------------------------------------------------------
# Module-level Cue Lexicons grouped per relation (English, Hinglish, Devanagari)
# ---------------------------------------------------------------------------

OWNS_DEVICE_ENGLISH: tuple[str, ...] = (
    "in possession of", "physical custody of", "personal search",
    "operated handset", "operated phone", "operated mobile",
    "using mobile", "using phone", "used phone", "used mobile", "used handset", "used number",
    "owned", "owns", "possession", "custody", "secured mobile", "found with",
    "calling connection", "personal mobile", "seized", "recovered", "recovred",
    "belongs to", "registered to", "had mobile", "had phone",
)
OWNS_DEVICE_HINGLISH: tuple[str, ...] = (
    "ke pas se", "ke paas se", "paas se", "pas se", "ke jeb se", "jeb se",
    "kabze se", "qabze se", "ke kabze se", "baramad", "zabt shuda", "zabt",
    "pesh kiya", "apna mobile", "apna phone", "pratyaksh talashi", "talashi",
    "istemal", "prayukt", "use karta", "chalata",
)
OWNS_DEVICE_HINDI: tuple[str, ...] = (
    "के पास से", "पास से", "के कब्जे से", "कब्जे से", "जेब से", "बरामद", "बरामदगी",
    "जब्त", "पेश किया", "हवाले किया", "प्रयुक्त हैंडसेट", "प्रयुक्त फोन", "प्रयुक्त मोबाइल",
    "अपना प्रयुक्त", "अपना मोबाइल", "अपना फोन", "सक्रिय मोबाइल", "बातचीत हेतु प्रयुक्त",
    "इस्तेमाल", "उपयोग",
)
OWNS_DEVICE_CUES: tuple[str, ...] = (
    OWNS_DEVICE_ENGLISH + OWNS_DEVICE_HINGLISH + OWNS_DEVICE_HINDI
)

ASSOCIATED_IMEI_ENGLISH: tuple[str, ...] = (
    "imei", "paired with", "operational on", "device imei", "hardware imei",
    "handset imei", "apparatus imei", "sharing identical", "mapped",
    "associated with", "linked to", "inserted in", "installed in",
    "bearing imei", "bound to", "tagged with",
)
ASSOCIATED_IMEI_HINGLISH: tuple[str, ...] = (
    "slot mein", "se mapped", "darj paya", "common paya", "valid device",
    "hardware", "handset scrutiny", "technical verification", "apparatus",
    "se juda", "mein laga",
)
ASSOCIATED_IMEI_HINDI: tuple[str, ...] = (
    "आईएमईआई", "में संचालित", "अंकित पाया", "डिवाइस आईएमईआई", "हैंडसेट आईएमईआई",
    "उपकरण जांच", "हार्डवेयर", "पहचान क्रमांक", "हार्डवेयर पहचान", "दर्ज किया",
    "से जुड़ा", "में लगा",
)
ASSOCIATED_IMEI_CUES: tuple[str, ...] = (
    ASSOCIATED_IMEI_ENGLISH + ASSOCIATED_IMEI_HINGLISH + ASSOCIATED_IMEI_HINDI
)

COMMUNICATED_WITH_ENGLISH: tuple[str, ...] = (
    "cdr", "called", "calling", "call", "calls", "voice call", "voice calls",
    "telephone traffic", "calling sessions", "communicated with", "contacted",
    "spoke with", "spoke to", "talked to", "talked with", "dialed", "dialled",
    "messaged", "phoned", "sms", "whatsapp", "exchanged", "telephonic",
)
COMMUNICATED_WITH_HINGLISH: tuple[str, ...] = (
    "calls kiye", "call kiya", "calling traffic", "baat ki", "baat hui",
    "baatcheet", "varta", "audio dialogue", "sampark", "seedha", "linked tha",
    "ke beech", "par call", "se baat",
)
COMMUNICATED_WITH_HINDI: tuple[str, ...] = (
    "सीडीआर", "कॉल किए", "कॉल किया", "कॉल", "वार्तालाप", "वार्ता", "संपर्क",
    "बातचीत", "बात की", "फ़ोन किया", "फोन किया", "डायल", "नेटवर्क रिकॉर्ड",
    "दूरसंचार", "के मध्य",
)
COMMUNICATED_WITH_CUES: tuple[str, ...] = (
    COMMUNICATED_WITH_ENGLISH + COMMUNICATED_WITH_HINGLISH + COMMUNICATED_WITH_HINDI
)

CONTROLS_ACCOUNT_ENGLISH: tuple[str, ...] = (
    "controlled", "controls", "control", "controlling",
    "operated", "operates", "operate", "operating",
    "managed", "manages", "manage", "managing", "handler",
    "stewardship", "authorized signatory", "signatory", "beneficial owner",
    "account holder", "maintained by", "maintains", "handled by", "handles",
    "administered", "administer", "oversight", "run by",
)
CONTROLS_ACCOUNT_HINGLISH: tuple[str, ...] = (
    "niyantran", "sanchalit", "sanchalan", "dekhrekh", "prabandh", "prabhand",
    "manage hota", "operate kiya", "operate karta", "control karta",
    "ke hawale", "hawale tha", "adhikar", "malikana", "chalata", "chalati",
)
CONTROLS_ACCOUNT_HINDI: tuple[str, ...] = (
    "नियंत्रण", "नियंत्रित", "संचालित", "संचालन", "देखरेख", "प्रबंधन", "प्रबंध",
    "हवाले", "प्रचालक", "अधिकृत प्रचालक", "प्रचालन", "खाताधारक",
    "चलाता", "चलाती", "संभालता", "संभालती", "स्वामित्व",
)
CONTROLS_ACCOUNT_CUES: tuple[str, ...] = (
    CONTROLS_ACCOUNT_ENGLISH + CONTROLS_ACCOUNT_HINGLISH + CONTROLS_ACCOUNT_HINDI
)

TRANSFERRED_FUNDS_ENGLISH: tuple[str, ...] = (
    "transferred", "transferring", "transfer",
    "remitted", "remitting", "remittance", "remit",
    "deposited", "depositing", "deposit",
    "credited", "crediting", "credit",
    "sent", "sending", "send",
    "wired", "wire", "paid", "payout", "routed", "channeled", "channelled",
    "diverted", "disbursed", "neft", "rtgs", "imps",
)
TRANSFERRED_FUNDS_HINGLISH: tuple[str, ...] = (
    "bhej diya", "bheja", "bheji", "jama karwaya", "jama karwayi", "jama kiya",
    "jama hui", "jama hua", "jama", "credit karwaya", "credit hui",
    "transfer kiya", "transfer hua", "antrit", "antaran", "preshit", "bhugtan",
    "dala", "daala",
)
TRANSFERRED_FUNDS_HINDI: tuple[str, ...] = (
    "प्रेषित", "अंतरित", "अंतरण", "जमा कराया", "जमा कराई", "जमा किया", "जमा की", "जमा",
    "भेज दिया", "भेजा", "भेजी", "स्थानांतरित", "हस्तांतरित", "भुगतान",
    "ट्रांसफर", "क्रेडिट", "हस्तांतरण",
)
TRANSFERRED_FUNDS_CUES: tuple[str, ...] = (
    TRANSFERRED_FUNDS_ENGLISH + TRANSFERRED_FUNDS_HINGLISH + TRANSFERRED_FUNDS_HINDI
)

CASH_WORDS: tuple[str, ...] = (
    "cash", "currency notes", "nakad", "nagad", "नकद", "नकदी", "रोकड़",
)
SEIZURE_WORDS: tuple[str, ...] = (
    "recover", "recovered", "recovred", "recovery", "seize", "seized", "seizure",
    "confiscated", "confiscate", "baramad", "zabt", "zabti",
    "बरामद", "बरामदगी", "जब्त", "जब्ती",
)
CARRY_FORWARD_PRONOUNS: tuple[str, ...] = (
    "uske", "unke", "uska", "uski", "usne", "usse",
    "his", "her", "their", "him",
    "उसके", "उनके", "उसका", "उसकी", "उसने", "उससे",
)


def _compile_cue_regex(cues: tuple[str, ...]) -> re.Pattern[str]:
    """Compile multilingual cue list with ASCII word boundaries and Devanagari lookarounds."""
    sorted_cues = sorted(set(cues), key=len, reverse=True)
    parts: list[str] = []
    for cue in sorted_cues:
        esc = re.escape(cue)
        if cue.isascii():
            parts.append(rf"\b{esc}\b")
        else:
            parts.append(rf"(?<![\u0900-\u097f]){esc}(?![\u0900-\u097f])")
    return re.compile("(?:" + "|".join(parts) + ")", re.IGNORECASE)


_OWNS_DEVICE_RE = _compile_cue_regex(OWNS_DEVICE_CUES)
_ASSOCIATED_IMEI_RE = _compile_cue_regex(ASSOCIATED_IMEI_CUES)
_COMMUNICATED_WITH_RE = _compile_cue_regex(COMMUNICATED_WITH_CUES)
_CONTROLS_ACCOUNT_RE = _compile_cue_regex(CONTROLS_ACCOUNT_CUES)
_TRANSFERRED_FUNDS_RE = _compile_cue_regex(TRANSFERRED_FUNDS_CUES)
_CASH_RE = _compile_cue_regex(CASH_WORDS)
_SEIZURE_RE = _compile_cue_regex(SEIZURE_WORDS)
_PRONOUN_RE = _compile_cue_regex(CARRY_FORWARD_PRONOUNS)

_STRONG_POSSESSION_RE = _compile_cue_regex((
    "in possession of", "physical custody of", "possession", "custody",
    "ke pas se", "ke paas se", "paas se", "pas se", "ke jeb se", "jeb se",
    "kabze se", "qabze se", "ke kabze se",
    "के पास से", "पास से", "के कब्जे से", "कब्जे से", "जेब से",
    "uske", "unke", "his", "her", "their", "उसके", "उनके", "उससे",
))

_OWNS_NEAR_PHONE_RE = re.compile(
    r"\b(?:operat(?:e|es|ed|ing)|us(?:e|es|ed|ing)|carr(?:y|ies|ied)|"
    r"keep|kept|held|hold|holding)\b[^.।\n]{0,30}"
    r"\b(?:handset|phone|mobile|sim|connection|device|number)\b",
    re.IGNORECASE,
)


def _is_upper_latin_or_deva(ch: str) -> bool:
    """Return True if ch is an uppercase Latin letter or a Devanagari non-digit/non-danda letter."""
    if "A" <= ch <= "Z":
        return True
    if "\u0900" <= ch <= "\u097f" and ch not in "।॥०१२३४५६७८९":
        return True
    return False


def _is_non_splitting_period(text: str, sent_start: int, dot_idx: int, next_non_ws_idx: int) -> bool:
    """Return True if '.' at dot_idx is an abbreviation, initial, or inside a number."""
    n = len(text)
    if dot_idx > 0 and text[dot_idx - 1].isdigit():
        if dot_idx + 1 < n and text[dot_idx + 1].isdigit():
            return True
    if next_non_ws_idx >= n or not _is_upper_latin_or_deva(text[next_non_ws_idx]):
        return True

    pre = text[sent_start:dot_idx]
    # Single-letter initial (e.g. "A. K. Verma", "S. Sharma")
    if re.search(r"(?:^|[^A-Za-z])([A-Za-z])$", pre):
        return True

    m_tok = re.search(r"([A-Za-z][A-Za-z/.]*)$", pre)
    if m_tok:
        tok_raw = m_tok.group(1).lower()
        tok = tok_raw.rstrip(".")
        if tok in ABBREVIATIONS:
            return True
        if "." in tok_raw:
            segs = [s for s in tok_raw.split(".") if s]
            if any(s in ABBREVIATIONS for s in segs) or all(len(s) == 1 for s in segs):
                return True

    return False


def split_sentences(text: str) -> list[tuple[int, int, str]]:
    """
    Split text into (start, end, sentence_text) tuples.
    Splits on '।'/'॥'/'\\n' and on '. ' followed by uppercase Latin or Devanagari letter,
    preserving abbreviations, initials, and numbers.
    """
    if not text:
        return []

    n = len(text)
    sents: list[tuple[int, int, str]] = []
    cur_start = 0
    i = 0

    def _push(raw_s: int, raw_e: int) -> None:
        seg = text[raw_s:raw_e]
        ls = len(seg) - len(seg.lstrip())
        rs = len(seg) - len(seg.rstrip())
        s = raw_s + ls
        e = raw_e - rs
        if s < e:
            sents.append((s, e, text[s:e]))

    while i < n:
        ch = text[i]
        if ch in "।॥\n":
            end = i + 1 if ch in "।॥" else i
            _push(cur_start, end)
            i += 1
            while i < n and text[i].isspace():
                i += 1
            cur_start = i
            continue

        if ch == "." and i + 1 < n and text[i + 1].isspace():
            j = i + 1
            while j < n and text[j].isspace():
                j += 1
            if not _is_non_splitting_period(text, cur_start, i, j):
                _push(cur_start, i + 1)
                cur_start = j
                i = j
                continue

        i += 1

    if cur_start < n:
        _push(cur_start, n)

    return sents


def _is_cash_recovery(sent_text: str) -> bool:
    """Return True if sentence describes cash seizure/recovery rather than an account transfer."""
    return bool(_CASH_RE.search(sent_text) and _SEIZURE_RE.search(sent_text))


def _span_dist(a: tuple[int, int], b: tuple[int, int]) -> int:
    """Return character gap distance between two spans (0 if overlapping)."""
    return max(0, max(a[0], b[0]) - min(a[1], b[1]))


def _best_trigger_near(matches: list[re.Match[str]], span: tuple[int, int], sent_start: int) -> tuple[str, tuple[int, int]]:
    """Pick trigger match closest to span."""
    best = min(
        matches,
        key=lambda m: _span_dist((sent_start + m.start(), sent_start + m.end()), span),
    )
    return best.group(0), (sent_start + best.start(), sent_start + best.end())


def _resolve_comm_direction(
    sent_text: str,
    sent_start: int,
    p1: dict[str, Any],
    p2: dict[str, Any],
    owned_ids: set[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Decide COMMUNICATED_WITH direction between p1 (earlier) and p2 (later).
    Uses directional cue grammar first; falls back to suspect-linked phone, then earlier mention.
    """
    s1_rel = p1["start"] - sent_start
    e1_rel = p1["end"] - sent_start
    s2_rel = p2["start"] - sent_start
    e2_rel = p2["end"] - sent_start

    before_p1 = sent_text[max(0, s1_rel - 35):s1_rel]
    between = sent_text[e1_rel:s2_rel]
    after_p2 = sent_text[e2_rel:min(len(sent_text), e2_rel + 35)]

    # Reverse patterns (p2 -> p1):
    # - English passive / receiver-first: "<p1> received ... from <p2>", "<p1> was called by <p2>", "to/on <p1> from <p2>"
    if re.search(r"\b(?:received|got|incoming)\b.*\bfrom\b", between, re.IGNORECASE):
        return p2, p1
    if re.search(r"\b(?:was|were)\s+(?:called|contacted|dialed|dialled|phoned|messaged|rung)\b.*\bby\b", between, re.IGNORECASE):
        return p2, p1
    if re.search(r"\b(?:to|on|at)\s+(?:phone|mobile|number|handset|sim|connection)?\s*$", before_p1, re.IGNORECASE) and re.search(r"\bfrom\b\s*(?:phone|mobile|number|handset|sim|connection)?\s*$", between, re.IGNORECASE):
        return p2, p1
    if re.search(r"^\s*(?:to|par|ko)\b|^\s*(?:पर|को)(?![\u0900-\u097f])", between, re.IGNORECASE):
        if re.search(r"\bfrom\b\s*(?:phone|mobile|number|handset|sim|connection)?\s*$", between, re.IGNORECASE):
            return p2, p1
        if re.search(r"^\s*(?:ke\s+dwara|ne|dwara|se)\b|^\s*(?:के\s+द्वारा|ने|द्वारा|से)(?![\u0900-\u097f])", after_p2, re.IGNORECASE):
            return p2, p1

    # Forward patterns (p1 -> p2):
    # - "<p1> called/dialed/contacted <p2>", "from <p1> to <p2>", "<p1> ne/se/dwara <p2> par/ko"
    if re.search(r"\b(?:called|dialed|dialled|contacted|phoned|messaged|rang)\b", between, re.IGNORECASE):
        return p1, p2
    if re.search(r"\bfrom\b\s*(?:phone|mobile|number|handset|sim|connection)?\s*$", before_p1, re.IGNORECASE) and re.search(r"\bto\b\s*(?:phone|mobile|number|handset|sim|connection)?\s*$", between, re.IGNORECASE):
        return p1, p2
    if re.search(r"^\s*(?:ke\s+dwara|ne|se|dwara)\b|^\s*(?:के\s+द्वारा|ने|द्वारा|से)(?![\u0900-\u097f])", between, re.IGNORECASE) and re.search(r"\b(?:par|ko)\b|(?:पर|को)(?![\u0900-\u097f])", between + after_p2, re.IGNORECASE):
        return p1, p2

    # Symmetric / ambiguous fallback: already linked to a suspect, else first mentioned
    p1_owned = p1["id"] in owned_ids
    p2_owned = p2["id"] in owned_ids
    if p2_owned and not p1_owned:
        return p2, p1
    return p1, p2


def _resolve_acc_transfer_direction(
    sent_text: str,
    sent_start: int,
    a1: dict[str, Any],
    a2: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Decide direction between two ACCOUNT spans in a transfer sentence."""
    s1_rel = a1["start"] - sent_start
    e1_rel = a1["end"] - sent_start
    s2_rel = a2["start"] - sent_start
    e2_rel = a2["end"] - sent_start

    before_a1 = sent_text[max(0, s1_rel - 35):s1_rel]
    between = sent_text[e1_rel:s2_rel]
    after_a2 = sent_text[e2_rel:min(len(sent_text), e2_rel + 35)]

    # Receiver-first: "credited/into/to <a1> from <a2>" or "<a1> mein <a2> se"
    if re.search(r"\b(?:to|into)\s+(?:account|a/c|bank account)?\s*$", before_a1, re.IGNORECASE) and re.search(r"\bfrom\b", between, re.IGNORECASE):
        return a2, a1
    if re.search(r"^\s*(?:mein|me)\b|^\s*में(?![\u0900-\u097f])", between, re.IGNORECASE) and re.search(r"^\s*(?:se|dwara)\b|^\s*(?:से|द्वारा)(?![\u0900-\u097f])", after_a2, re.IGNORECASE):
        return a2, a1
    if re.search(r"\b(?:beneficiary|recipient|target|destination)\b", before_a1, re.IGNORECASE) and re.search(r"\b(?:origin|source|remitter|sender)\b", between, re.IGNORECASE):
        return a2, a1

    return a1, a2


def extract_relations(
    text: str,
    doc: dict[str, Any],
    aux: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Extract relationships (OWNS_DEVICE, ASSOCIATED_IMEI, COMMUNICATED_WITH,
    CONTROLS_ACCOUNT, TRANSFERRED_FUNDS) from text using assembled Contract v1.1 entities
    and aux amounts. Returns relationship dicts ready for Contract 1 v1.1.
    """
    if not text or not doc.get("entities"):
        return []

    sentences = split_sentences(text)
    entities = doc.get("entities", [])
    ent_role: dict[str, str | None] = {e["id"]: e.get("role") for e in entities}

    # Index mentions: kind == NAME for PERSON, kind == VALUE for PHONE/IMEI/ACCOUNT
    all_mentions: list[dict[str, Any]] = []
    for ent in entities:
        eid = ent["id"]
        etype = ent["type"]
        valid_kind = "NAME" if etype == "PERSON" else "VALUE"
        for m in ent.get("mentions", []):
            if m.get("kind") != valid_kind:
                continue
            ms, me = int(m["char_span"][0]), int(m["char_span"][1])
            all_mentions.append({
                "id": eid,
                "type": etype,
                "role": ent_role.get(eid),
                "start": ms,
                "end": me,
                "surface": m["surface"],
            })

    amounts = list(aux.get("amounts", []))
    relationships: list[dict[str, Any]] = []
    seen_triples: set[tuple[str, str, str]] = set()
    recent_suspects: list[tuple[int, dict[str, Any]]] = []
    suspect_owned_phones: set[str] = set()

    def _emit(
        src_id: str,
        tgt_id: str,
        rel_type: str,
        trigger: str,
        conf: float,
        ev_span: tuple[int, int],
        amount_val: float | None = None,
    ) -> None:
        key = (src_id, tgt_id, rel_type)
        if key in seen_triples or src_id == tgt_id:
            return
        seen_triples.add(key)
        rel_obj: dict[str, Any] = {
            "source": src_id,
            "target": tgt_id,
            "relation": rel_type,
            "trigger": trigger,
            "confidence": conf,
            "evidence_char_span": [ev_span[0], ev_span[1]],
        }
        if rel_type == "TRANSFERRED_FUNDS" and amount_val is not None and amount_val > 0:
            rel_obj["amount"] = float(amount_val)
        relationships.append(rel_obj)

    def _pick_suspect(
        curr_suspects: list[dict[str, Any]],
        sent_idx: int,
        sent_text: str,
        sent_start: int,
        non_suspect_persons: list[dict[str, Any]],
        target_span: tuple[int, int],
        trigger_span: tuple[int, int],
    ) -> tuple[dict[str, Any] | None, float]:
        if curr_suspects:
            chosen = min(
                curr_suspects,
                key=lambda s: (
                    _span_dist((s["start"], s["end"]), trigger_span)
                    + _span_dist((s["start"], s["end"]), target_span),
                    s["start"],
                ),
            )
            return chosen, 0.9

        # Carry forward only if no non-suspect actor owns the clause (unless pronoun exists)
        if non_suspect_persons and not _PRONOUN_RE.search(sent_text):
            return None, 0.0

        for prev_idx, prev_susp in reversed(recent_suspects):
            if 0 < sent_idx - prev_idx <= 2:
                return prev_susp, 0.5
        return None, 0.0

    for sent_idx, (sent_start, sent_end, sent_text) in enumerate(sentences):
        ev_span = (sent_start, sent_end)
        s_mentions = [
            m for m in all_mentions
            if sent_start <= m["start"] and m["end"] <= sent_end
        ]
        if not s_mentions:
            continue

        s_mentions.sort(key=lambda m: (m["start"], m["end"]))
        curr_suspects = [m for m in s_mentions if m["type"] == "PERSON" and m["role"] == "SUSPECT"]
        non_suspects = [m for m in s_mentions if m["type"] == "PERSON" and m["role"] != "SUSPECT"]
        phones = [m for m in s_mentions if m["type"] == "PHONE"]
        imeis = [m for m in s_mentions if m["type"] == "IMEI"]
        accounts = [m for m in s_mentions if m["type"] == "ACCOUNT"]
        s_amounts = [
            a for a in amounts
            if sent_start <= int(a["start"]) and int(a["end"]) <= sent_end
        ]

        # 1. OWNS_DEVICE (PERSON[SUSPECT] -> PHONE)
        owns_matches = (
            list(_OWNS_DEVICE_RE.finditer(sent_text))
            + list(_OWNS_NEAR_PHONE_RE.finditer(sent_text))
        )
        if owns_matches and phones:
            # Guard carry-forward on pure IMEI/CDR follow-up sentences lacking strong possession cues
            allow_owns = bool(curr_suspects) or bool(_STRONG_POSSESSION_RE.search(sent_text)) or (
                not imeis and not _COMMUNICATED_WITH_RE.search(sent_text)
            )
            if allow_owns:
                for ph in phones:
                    ph_span = (ph["start"], ph["end"])
                    trig, trig_span = _best_trigger_near(owns_matches, ph_span, sent_start)
                    susp, conf = _pick_suspect(
                        curr_suspects, sent_idx, sent_text, sent_start, non_suspects, ph_span, trig_span
                    )
                    if susp is not None:
                        _emit(susp["id"], ph["id"], "OWNS_DEVICE", trig, conf, ev_span)
                        suspect_owned_phones.add(ph["id"])

        # 2. ASSOCIATED_IMEI (PHONE -> IMEI)
        imei_matches = list(_ASSOCIATED_IMEI_RE.finditer(sent_text))
        if imei_matches and phones and imeis:
            for im in imeis:
                im_span = (im["start"], im["end"])
                nearest_ph = min(
                    phones,
                    key=lambda p: (
                        _span_dist((p["start"], p["end"]), im_span),
                        0 if p["start"] < im["start"] else 1,
                        p["start"],
                    ),
                )
                trig, _ = _best_trigger_near(imei_matches, im_span, sent_start)
                _emit(nearest_ph["id"], im["id"], "ASSOCIATED_IMEI", trig, 0.9, ev_span)

        # 3. COMMUNICATED_WITH (PHONE -> PHONE)
        comm_matches = list(_COMMUNICATED_WITH_RE.finditer(sent_text))
        distinct_phones: list[dict[str, Any]] = []
        seen_ph_ids: set[str] = set()
        for ph in phones:
            if ph["id"] not in seen_ph_ids:
                seen_ph_ids.add(ph["id"])
                distinct_phones.append(ph)
        if comm_matches and len(distinct_phones) >= 2:
            for idx in range(len(distinct_phones) - 1):
                p1 = distinct_phones[idx]
                p2 = distinct_phones[idx + 1]
                src_ph, tgt_ph = _resolve_comm_direction(
                    sent_text, sent_start, p1, p2, suspect_owned_phones
                )
                mid_span = (p1["start"], p2["end"])
                trig, _ = _best_trigger_near(comm_matches, mid_span, sent_start)
                _emit(src_ph["id"], tgt_ph["id"], "COMMUNICATED_WITH", trig, 0.9, ev_span)

        # 4. CONTROLS_ACCOUNT (PERSON[SUSPECT] -> ACCOUNT)
        ctrl_matches = list(_CONTROLS_ACCOUNT_RE.finditer(sent_text))
        trans_matches = list(_TRANSFERRED_FUNDS_RE.finditer(sent_text)) if not _is_cash_recovery(sent_text) else []

        if ctrl_matches and accounts:
            # If both transfer and control appear in same sentence with >1 accounts,
            # bind control only to the account closest to the control trigger.
            target_accs = accounts
            if trans_matches and len(accounts) > 1:
                c_span0 = (sent_start + ctrl_matches[0].start(), sent_start + ctrl_matches[0].end())
                target_accs = [min(accounts, key=lambda a: _span_dist((a["start"], a["end"]), c_span0))]
            for acc in target_accs:
                acc_span = (acc["start"], acc["end"])
                trig, trig_span = _best_trigger_near(ctrl_matches, acc_span, sent_start)
                susp, conf = _pick_suspect(
                    curr_suspects, sent_idx, sent_text, sent_start, non_suspects, acc_span, trig_span
                )
                if susp is not None:
                    _emit(susp["id"], acc["id"], "CONTROLS_ACCOUNT", trig, conf, ev_span)

        # 5. TRANSFERRED_FUNDS (PERSON[SUSPECT] -> ACCOUNT or ACCOUNT -> ACCOUNT)
        if trans_matches and accounts and not _is_cash_recovery(sent_text):
            distinct_accs: list[dict[str, Any]] = []
            seen_acc_ids: set[str] = set()
            for acc in accounts:
                if acc["id"] not in seen_acc_ids:
                    seen_acc_ids.add(acc["id"])
                    distinct_accs.append(acc)

            if len(distinct_accs) >= 2:
                a1, a2 = distinct_accs[0], distinct_accs[1]
                src_acc, tgt_acc = _resolve_acc_transfer_direction(sent_text, sent_start, a1, a2)
                tgt_span = (tgt_acc["start"], tgt_acc["end"])
                trig, trig_span = _best_trigger_near(trans_matches, tgt_span, sent_start)
                amt_val = None
                if s_amounts:
                    nearest_amt = min(
                        s_amounts,
                        key=lambda am: _span_dist((int(am["start"]), int(am["end"])), tgt_span)
                        + _span_dist((int(am["start"]), int(am["end"])), (src_acc["start"], src_acc["end"])),
                    )
                    amt_val = float(nearest_amt["value"])
                _emit(src_acc["id"], tgt_acc["id"], "TRANSFERRED_FUNDS", trig, 0.9, ev_span, amt_val)
            else:
                tgt_acc = distinct_accs[0]
                tgt_span = (tgt_acc["start"], tgt_acc["end"])
                trig, trig_span = _best_trigger_near(trans_matches, tgt_span, sent_start)
                susp, conf = _pick_suspect(
                    curr_suspects, sent_idx, sent_text, sent_start, non_suspects, tgt_span, trig_span
                )
                if susp is not None:
                    amt_val = None
                    if s_amounts:
                        nearest_amt = min(
                            s_amounts,
                            key=lambda am: _span_dist((int(am["start"]), int(am["end"])), tgt_span)
                            + _span_dist((int(am["start"]), int(am["end"])), trig_span),
                        )
                        amt_val = float(nearest_amt["value"])
                    _emit(susp["id"], tgt_acc["id"], "TRANSFERRED_FUNDS", trig, conf, ev_span, amt_val)

        # Update suspect history at the end of processing this sentence
        for sp in curr_suspects:
            recent_suspects.append((sent_idx, sp))

    return relationships
