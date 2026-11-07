"""
data/synthetic/generate_firs.py
Advanced seeded FIR text generator with ground-truth answer keys (Step 2c).
Produces realistic variety across 60 FIRs (train/dev/test splits), 6 FIR types,
3 languages (Hinglish, Devanagari Hindi, English), held-out test templates,
non-labelled decoys, cash amounts, entity_keys on all mentions, ALIAS and FATHER
spans, BNS terminology, verified bank.csv transfers (ACCOUNT->ACCOUNT and
PERSON->ACCOUNT), amount styles, and exact character spans.
"""

import argparse
import csv
import json
import os
import random
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Devanagari digits mapping
DEVANAGARI_DIGITS = {
    "0": "०", "1": "१", "2": "२", "3": "३", "4": "४",
    "5": "५", "6": "६", "7": "७", "8": "८", "9": "९"
}
DEVANAGARI_DIGITS_REV = {v: k for k, v in DEVANAGARI_DIGITS.items()}

def to_devanagari_digits(num_str: str) -> str:
    """Converts ASCII digits in a string to Devanagari digits."""
    return "".join(DEVANAGARI_DIGITS.get(ch, ch) for ch in str(num_str))

def format_indian_grouping(val: float, decimals: int = 0) -> str:
    """Formats a number in Indian number numbering system (e.g. 1,57,400 or 1,57,400.00)."""
    int_part = int(val)
    frac_part = f"{val - int_part:.{decimals}f}"[1:] if decimals > 0 else ""
    s = str(int_part)
    if len(s) <= 3:
        return s + frac_part
    last3 = s[-3:]
    remaining = s[:-3]
    groups = []
    while len(remaining) > 2:
        groups.append(remaining[-2:])
        remaining = remaining[:-2]
    if remaining:
        groups.append(remaining)
    groups.reverse()
    return ",".join(groups) + "," + last3 + frac_part

def format_amount_style(val: float, style_idx: int, lang: str = "english") -> str:
    """Formats monetary amounts into one of 4 allowed styles."""
    # Style 3: Lakh representation (only when cleanly representable, e.g. 1.5 lakh, 2 lakh, 5 lakh)
    if style_idx == 3:
        lakh = val / 100000.0
        if round(lakh, 1) * 100000.0 == val:
            formatted_lakh = f"{lakh:.1f}" if lakh != int(lakh) else f"{int(lakh)}"
            if lang == "hindi":
                return f"{formatted_lakh} लाख"
            return f"{formatted_lakh} lakh"
        else:
            style_idx = 0

    decimals = 2 if (val != int(val)) else 0

    if style_idx == 0:
        return format_indian_grouping(val, decimals=decimals)
    elif style_idx == 1:
        return f"Rs. {format_indian_grouping(val, decimals=decimals)}/-"
    else:  # style_idx == 2
        return f"INR {format_indian_grouping(val, decimals=2)}"

def parse_amount_surface(surface: str) -> float:
    """Parses an amount surface string back to numeric float value."""
    s = surface
    for k, v in DEVANAGARI_DIGITS.items():
        s = s.replace(v, k)
    m_lakh = re.search(r"([\d.]+)\s*(?:lakh|लाख)", s, re.IGNORECASE)
    if m_lakh:
        return float(m_lakh.group(1)) * 100000.0
    # Remove currency prefixes like "Rs.", "INR", "रु."
    s = re.sub(r"(?i)\b(?:rs|inr)\b\.?", "", s)
    s = re.sub(r"रु\.?", "", s)
    cleaned = re.sub(r"[^\d.]", "", s)
    if cleaned.endswith("."):
        cleaned = cleaned[:-1]
    return float(cleaned)


NAME_HINDI_MAP = {
    # Gang A
    "Rajendra Singh": "राजेंद्र सिंह",
    "Maheshwar Singh": "महेश्वर सिंह",
    "Raju Bhai": "राजू भाई",
    "Devendra Yadav": "देवेंद्र यादव",
    "Ramakant Yadav": "रमाकांत यादव",
    "Chhota Raju": "छोटा राजू",
    "Sanjay Mehra": "संजय मेहरा",
    "Prem Mehra": "प्रेम मेहरा",
    "Sanju": "संजू",
    "Vikas Sharma": "विकास शर्मा",
    "Harish Sharma": "हरीश शर्मा",
    "Bicky": "विक्की",
    "Viku": "विकू",
    "Kallu": "कल्लू",
    "Anand Verma": "आनंद वर्मा",
    "Shyam Verma": "श्याम वर्मा",
    "Andy": "एंडी",
    "Pankaj Tiwari": "पंकज तिवारी",
    "Madan Tiwari": "मदन तिवारी",
    "Pandit": "पंडित",
    "Manoj Rawat": "मनोज रावत",
    "Kishori Rawat": "किशोरी रावत",
    "Munna": "मुन्ना",
    "Deepak Chauhan": "दीपक चौहान",
    "Sardar Chauhan": "सरदार चौहान",
    "Deepu": "दीपू",
    "Sunil Kumar": "सुनील कुमार",
    "Bhagwan Kumar": "भगवान कुमार",
    "Sunny": "सनी",

    # Gang B
    "Mukhtar Ansari": "मुख्तार अंसारी",
    "Iqbal Ansari": "इकबाल अंसारी",
    "Bade Miyan": "बड़े मियां",
    "Farooq Ahmed": "फारूक अहमद",
    "Zahid Ahmed": "जाहिद अहमद",
    "Tiger": "टाइगर",
    "Rashid Khan": "राशिद खान",
    "Asif Khan": "आसिफ खान",
    "Shooter": "शूटर",
    "Bikas Sharma": "बिकास शर्मा",
    "Girish Sharma": "गिरीश शर्मा",
    "Biku": "बीकू",
    "Imran Sheikh": "इमरान शेख",
    "Mustaq Sheikh": "मुश्ताक शेख",
    "Kabira": "कबीरा",
    "Nadeem Qureshi": "नदीम कुरैशी",
    "Yusuf Qureshi": "यूसुफ कुरैशी",
    "Don": "डॉन",
    "Wasim Akram": "वसीम अकरम",
    "Shabir Akram": "शब्बीर अकरम",
    "Vicky": "विक्की",
    "Salman Mirza": "सलमान मिर्ज़ा",
    "Feroz Mirza": "फिरोज़ मिर्ज़ा",
    "Sallu": "सल्लू",
    "Aslam Parvez": "असलम परवेज़",
    "Latif Parvez": "लतीफ परवेज़",
    "Chacha": "चाचा",

    # Couriers & Decoys
    "Ramesh Chand": "रमेश चंद",
    "Kishan Chand": "किशन चंद",
    "Postman": "पोस्टमैन",
    "Suresh Pal": "सुरेश पाल",
    "Mohan Pal": "मोहन पाल",
    "Hawai": "हवाई",
    "Harish Chawla": "हरीश चावला",
    "Kailash Chawla": "कैलाश चावला",
    "Pizza Shop": "पिज़्ज़ा शॉप",

    # Neutral Personnel (Officers, Witnesses, Complainants)
    "Arvind Swaminathan": "अरविंद स्वामीनाथन",
    "Rajesh Kumar": "राजेश कुमार",
    "Vikram Rathore": "विक्रम राठौड़",
    "Amit Tomar": "अमित तोमर",
    "Satish Chandra": "सतीश चंद्र",
    "Rameshwar Dayal": "रामेश्वर दयाल",
    "Virender Tyagi": "वीरेंद्र त्यागी",
    "Kuldeep Singh": "कुलदीप सिंह",
    "Naresh Kumar": "नरेश कुमार",
    "Dharmendra Rawat": "धर्मेंद्र रावत",
    "Hariprasad Sharma": "हरिप्रसाद शर्मा",
    "Kuldeep Yadav": "कुलदीप यादव",
    "Anil Mishra": "अनिल मिश्रा",
    "Harish Chandra": "हरीश चंद्र",
    "Pawan Verma": "पवन वर्मा",
    "Dinesh Joshi": "दिनेश जोशी",
    "Mohan Lal": "मोहन लाल",
    "Ram Avatar": "राम अवतार",
    "Suresh Bansal": "सुरेश बंसल",
    "Kishore Sen": "किशोर सेन",
}


# ---------------------------------------------------------------------------
# Template Catalog: 6 phrasings per relation per language.
# Templates 01-04: Train / Dev allowed (not held-out).
# Templates 05-06: HELD-OUT (Test ONLY, each test FIR uses at least one).
# ---------------------------------------------------------------------------

TEMPLATES = {
    "OWNS_DEVICE": {
        "hinglish": [
            {"id": "T_OWNS_HG_01", "held_out": False, "before": "Mauke par talashi lene par suspect ", "mid": " ke possession se mobile handset ", "after": " recovred kiya gaya."},
            {"id": "T_OWNS_HG_02", "held_out": False, "before": "Accused ", "mid": " ke pas se operational calling connection ", "after": " zabt shuda paya gaya."},
            {"id": "T_OWNS_HG_03", "held_out": False, "before": "Personal search ke dauran abhiyukt ", "mid": " dwara apna personal mobile ", "after": " pesh kiya gaya."},
            {"id": "T_OWNS_HG_04", "held_out": False, "before": "Red-handed arrest ke waqt ", "mid": " ke jeb se active communication phone ", "after": " baramad hua."},
            {"id": "T_OWNS_HG_05", "held_out": True,  "before": "Interrogation report ke mutabiq ", "mid": " ne tasleem kiya ki device number ", "after": " usi ke zati istemal mein tha."},
            {"id": "T_OWNS_HG_06", "held_out": True,  "before": "Spot checking ke time apradhi ", "mid": " ke hathon se calling instrument ", "after": " secure kiya gaya."},
        ],
        "hindi": [
            {"id": "T_OWNS_HI_01", "held_out": False, "before": "तलाशी के दौरान अभियुक्त ", "mid": " के व्यक्तिगत कब्जे से मोबाइल फोन ", "after": " बरामद हुआ।"},
            {"id": "T_OWNS_HI_02", "held_out": False, "before": "मौके पर संदिग्ध ", "mid": " के पास से सक्रिय मोबाइल नंबर ", "after": " जब्त किया गया।"},
            {"id": "T_OWNS_HI_03", "held_out": False, "before": "गिरफ्तारी के समय आरोपी ", "mid": " से बातचीत हेतु प्रयुक्त फोन ", "after": " बरामद हुआ।"},
            {"id": "T_OWNS_HI_04", "held_out": False, "before": "अभिरक्षा में पूछताछ पर आरोपी ", "mid": " ने अपना प्रयुक्त हैंडसेट ", "after": " पुलिस के हवाले किया।"},
            {"id": "T_OWNS_HI_05", "held_out": True,  "before": "तलाशी फर्द के अनुसार नामजद अभियुक्त ", "mid": " से चालू हालत में सिम युक्त मोबाइल ", "after": " मिला।"},
            {"id": "T_OWNS_HI_06", "held_out": True,  "before": "घटनास्थल पर घेराबंदी कर पकड़े गए अभियुक्त ", "mid": " के पास से संचार उपकरण ", "after": " बरामद हुआ।"},
        ],
        "english": [
            {"id": "T_OWNS_EN_01", "held_out": False, "before": "Upon personal search, accused ", "mid": " was found in possession of mobile handset ", "after": "."},
            {"id": "T_OWNS_EN_02", "held_out": False, "before": "The apprehending squad intercepted suspect ", "mid": " and recovered active calling device ", "after": "."},
            {"id": "T_OWNS_EN_03", "held_out": False, "before": "Suspect ", "mid": " was found in physical custody of cellular connection ", "after": "."},
            {"id": "T_OWNS_EN_04", "held_out": False, "before": "At the interception point, police searched accused ", "mid": " and secured mobile phone ", "after": "."},
            {"id": "T_OWNS_EN_05", "held_out": True,  "before": "Custodial interrogation established that accused ", "mid": " operated communication handset ", "after": "."},
            {"id": "T_OWNS_EN_06", "held_out": True,  "before": "Physical frisking of suspect ", "mid": " led to the immediate recovery of calling line ", "after": "."},
        ],
    },
    "ASSOCIATED_IMEI": {
        "hinglish": [
            {"id": "T_IMEI_HG_01", "held_out": False, "before": "Ukt mobile number ", "mid": " ka hardware IMEI ", "after": " darj paya gaya."},
            {"id": "T_IMEI_HG_02", "held_out": False, "before": "Zabt shuda SIM ", "mid": " handset IMEI ", "after": " ke slot mein operational tha."},
            {"id": "T_IMEI_HG_03", "held_out": False, "before": "Technical verification se phone ", "mid": " ka valid device IMEI ", "after": " manifest hua."},
            {"id": "T_IMEI_HG_04", "held_out": False, "before": "Handset scrutiny ke dauran number ", "mid": " apparatus IMEI ", "after": " se mapped nikla."},
            {"id": "T_IMEI_HG_05", "held_out": True,  "before": "Baramad shuda line ", "mid": " ka physical instrument IMEI ", "after": " mark kiya gaya."},
            {"id": "T_IMEI_HG_06", "held_out": True,  "before": "Hardware extraction se connection ", "mid": " terminal IMEI ", "after": " par active mila."},
        ],
        "hindi": [
            {"id": "T_IMEI_HI_01", "held_out": False, "before": "बरामद फोन नंबर ", "mid": " का हैंडसेट आईएमईआई ", "after": " अंकित पाया गया।"},
            {"id": "T_IMEI_HI_02", "held_out": False, "before": "उपकरण जांच में सिम कार्ड ", "mid": " डिवाइस आईएमईआई ", "after": " में संचालित मिला।"},
            {"id": "T_IMEI_HI_03", "held_out": False, "before": "तकनीकी निरीक्षण के अनुसार नंबर ", "mid": " का यंत्र आईएमईआई ", "after": " पाया गया।"},
            {"id": "T_IMEI_HI_04", "held_out": False, "before": "मौके पर दर्ज फर्द के तहत कॉलिंग फोन ", "mid": " का हार्डवेयर पहचान क्रमांक ", "after": " दर्ज किया गया।"},
            {"id": "T_IMEI_HI_05", "held_out": True,  "before": "जांच के दौरान मोबाइल ", "mid": " का मूल आईएमईआई नंबर ", "after": " चिन्हित हुआ।"},
            {"id": "T_IMEI_HI_06", "held_out": True,  "before": "जब्त हैंडसेट में सक्रिय सिम ", "mid": " भौतिक आईएमईआई ", "after": " के साथ संबंध रखता है।"},
        ],
        "english": [
            {"id": "T_IMEI_EN_01", "held_out": False, "before": "Physical inspection showed mobile number ", "mid": " operational on device IMEI ", "after": "."},
            {"id": "T_IMEI_EN_02", "held_out": False, "before": "The seized connection ", "mid": " was paired with equipment hardware IMEI ", "after": "."},
            {"id": "T_IMEI_EN_03", "held_out": False, "before": "Diagnostics confirmed that mobile terminal ", "mid": " carries hardware IMEI ", "after": "."},
            {"id": "T_IMEI_EN_04", "held_out": False, "before": "The active calling line ", "mid": " was inserted in handset slot IMEI ", "after": "."},
            {"id": "T_IMEI_EN_05", "held_out": True,  "before": "Technical mapping validated that cellular number ", "mid": " corresponds to hardware IMEI ", "after": "."},
            {"id": "T_IMEI_EN_06", "held_out": True,  "before": "Digital verification certified that connection ", "mid": " ran inside equipment slot IMEI ", "after": "."},
        ],
    },
    "COMMUNICATED_WITH": {
        "hinglish": [
            {"id": "T_CALL_HG_01", "held_out": False, "before": "CDR analysis se pata chala ki phone ", "mid": " ne doosre mobile ", "after": " par multiple voice calls kiye."},
            {"id": "T_CALL_HG_02", "held_out": False, "before": "Tower CDR logs indicate karte hain ki number ", "mid": " aur target phone ", "after": " ke beech frequent audio dialogue chala."},
            {"id": "T_CALL_HG_03", "held_out": False, "before": "Cellular analysis ke mutabiq device ", "mid": " seedha syndicate partner ke number ", "after": " se linked tha."},
            {"id": "T_CALL_HG_04", "held_out": False, "before": "Service provider data se khulasa hua ki mobile ", "mid": " ne phone ", "after": " par calling traffic generate kiya."},
            {"id": "T_CALL_HG_05", "held_out": True,  "before": "Intercept records disclose karte hain ki apparatus ", "mid": " lagatar phone ", "after": " ke sath direct telephonic connectivity mein tha."},
            {"id": "T_CALL_HG_06", "held_out": True,  "before": "Exchange logs point karte hain ki connection ", "mid": " dwara phone ", "after": " par clandestine communications chalaye gaye."},
        ],
        "hindi": [
            {"id": "T_CALL_HI_01", "held_out": False, "before": "कॉल डिटेल रिकॉर्ड के परीक्षण से पता चला कि फोन ", "mid": " ने अन्य मोबाइल ", "after": " से लगातार संपर्क साधा।"},
            {"id": "T_CALL_HI_02", "held_out": False, "before": "सीडीआर विश्लेषण से सिद्ध हुआ कि नंबर ", "mid": " और संदिग्ध नंबर ", "after": " के मध्य निरंतर वार्ता हुई।"},
            {"id": "T_CALL_HI_03", "held_out": False, "before": "दूरसंचार डेटा के अनुसार उपकरण ", "mid": " से सहयोगी फोन ", "after": " पर कई कॉल किए गए।"},
            {"id": "T_CALL_HI_04", "held_out": False, "before": "नेटवर्क रिकॉर्ड से स्पष्ट हुआ कि सिम ", "mid": " द्वारा साथी नंबर ", "after": " पर सतत वार्तालाप जारी रखा गया।"},
            {"id": "T_CALL_HI_05", "held_out": True,  "before": "तकनीकी साक्ष्य यह प्रकट करते हैं कि मोबाइल ", "mid": " का सीधा कॉलिंग लिंक फोन ", "after": " के साथ बना हुआ था।"},
            {"id": "T_CALL_HI_06", "held_out": True,  "before": "सेलुलर विश्लेषण के तहत कनेक्शन ", "mid": " द्वारा अन्य हैंडसेट ", "after": " पर बार-बार बातचीत दर्ज की गई।"},
        ],
        "english": [
            {"id": "T_CALL_EN_01", "held_out": False, "before": "Cellular CDR scrutiny revealed that handset ", "mid": " exchanged repeated telephone traffic with ", "after": "."},
            {"id": "T_CALL_EN_02", "held_out": False, "before": "Telecom subscriber data established direct telephonic liaison between line ", "mid": " and mobile ", "after": "."},
            {"id": "T_CALL_EN_03", "held_out": False, "before": "Call ledger analysis established that calling device ", "mid": " made recurrent contact with phone ", "after": "."},
            {"id": "T_CALL_EN_04", "held_out": False, "before": "Electronic records demonstrated systematic voice calling sessions between connection ", "mid": " and ", "after": "."},
            {"id": "T_CALL_EN_05", "held_out": True,  "before": "Digital network extraction evidenced regular peer-to-peer audio transmissions from ", "mid": " to target ", "after": "."},
            {"id": "T_CALL_EN_06", "held_out": True,  "before": "Carrier exchange records documented persistent bidirectional communications between phone ", "mid": " and ", "after": "."},
        ],
    },
    "TRANSFERRED_FUNDS": {
        "hinglish": [
            {"id": "T_TXN_HG_01", "held_out": False, "before": "Banking ledger scrutiny se pata chala ki accused ", "mid1": " ne sum ", "mid2": " beneficiary account ", "after": " mein credit karwaya."},
            {"id": "T_TXN_HG_02", "held_out": False, "before": "Electronic fund trail ke mutabiq ", "mid1": " ne total rashi ", "mid2": " bank account ", "after": " mein jama karwayi."},
            {"id": "T_TXN_HG_03", "held_out": False, "before": "Financial investigation se pata chala ki ", "mid1": " ne amount ", "mid2": " recipient account ", "after": " mein electronically bhej diya."},
            {"id": "T_TXN_HG_04", "held_out": False, "before": "Forensic accounting records dikhate hain ki ", "mid1": " ne direct payout ", "mid2": " target account ", "after": " mein bheja."},
            {"id": "T_TXN_HG_05", "held_out": True,  "before": "Hawala trail audit se khulasa hua ki suspect ", "mid1": " ne illicit funds ", "mid2": " designated account ", "after": " mein deposit karwaye."},
            {"id": "T_TXN_HG_06", "held_out": True,  "before": "Statement of accounts se manifest hua ki apradhi ", "mid1": " dwara remittance ", "mid2": " destination account ", "after": " mein transfer hua."},
        ],
        "hindi": [
            {"id": "T_TXN_HI_01", "held_out": False, "before": "बैंक खाते की जांच से यह सिद्ध हुआ कि आरोपी ", "mid1": " ने धनराशि ", "mid2": " बैंक खाता ", "after": " में अंतरित की।"},
            {"id": "T_TXN_HI_02", "held_out": False, "before": "वित्तीय साक्ष्यों के अनुसार अभियुक्त ", "mid1": " द्वारा कुल रकम ", "mid2": " संबंधित खाता ", "after": " में जमा कराई गई।"},
            {"id": "T_TXN_HI_03", "held_out": False, "before": "खाता विवरण से स्पष्ट हुआ कि नामजद ", "mid1": " ने धन ", "mid2": " प्राप्तकर्ता खाता ", "after": " में भेजा।"},
            {"id": "T_TXN_HI_04", "held_out": False, "before": "लेखा परीक्षण से प्रमाणित हुआ कि अभियुक्त ", "mid1": " ने ऑनलाइन माध्यम से रकम ", "mid2": " खाता ", "after": " में प्रेषित की।"},
            {"id": "T_TXN_HI_05", "held_out": True,  "before": "हवाला लेन-देन विश्लेषण से प्रकट हुआ कि संदिग्ध ", "mid1": " ने फंड ", "mid2": " अभीष्ट खाता ", "after": " में क्रेडिट कराया।"},
            {"id": "T_TXN_HI_06", "held_out": True,  "before": "बैंक स्टेटमेंट के आधार पर आरोपी ", "mid1": " द्वारा आपराधिक राशि ", "mid2": " लक्षित खाता ", "after": " में भेजी गई।"},
        ],
        "english": [
            {"id": "T_TXN_EN_01", "held_out": False, "before": "Financial ledger inspection showed that accused ", "mid1": " credited the sum of ", "mid2": " into account ", "after": "."},
            {"id": "T_TXN_EN_02", "held_out": False, "before": "Banking transaction trails evidenced that suspect ", "mid1": " transferred remittance ", "mid2": " into bank account ", "after": "."},
            {"id": "T_TXN_EN_03", "held_out": False, "before": "Account statement scrutiny demonstrated that ", "mid1": " remitted funds amounting to ", "mid2": " to destination account ", "after": "."},
            {"id": "T_TXN_EN_04", "held_out": False, "before": "Financial tracking revealed that perpetrator ", "mid1": " transferred illicit proceeds of ", "mid2": " into recipient account ", "after": "."},
            {"id": "T_TXN_EN_05", "held_out": True,  "before": "Forensic financial auditing documented that ", "mid1": " routed cash volume of ", "mid2": " into syndicate account ", "after": "."},
            {"id": "T_TXN_EN_06", "held_out": True,  "before": "Fiscal transaction analysis established that perpetrator ", "mid1": " forwarded capital of ", "mid2": " to designated account ", "after": "."},
        ],
    },
    "TRANSFERRED_FUNDS_ACCT": {
        "hinglish": [
            {"id": "T_TXNA_HG_01", "held_out": False, "before": "Banking ledger scrutiny se pata chala ki remitter account ", "mid1": " se sum ", "mid2": " beneficiary account ", "after": " mein transfer kiya gaya."},
            {"id": "T_TXNA_HG_02", "held_out": False, "before": "Electronic fund trail ke mutabiq source account ", "mid1": " se total rashi ", "mid2": " bank account ", "after": " mein credit hui."},
            {"id": "T_TXNA_HG_03", "held_out": False, "before": "Financial investigation se pata chala ki account ", "mid1": " se amount ", "mid2": " recipient account ", "after": " mein electronically bhej diya gaya."},
            {"id": "T_TXNA_HG_04", "held_out": False, "before": "Forensic accounting records dikhate hain ki origin account ", "mid1": " se direct payout ", "mid2": " target account ", "after": " mein transfer hua."},
            {"id": "T_TXNA_HG_05", "held_out": True,  "before": "Hawala trail audit se khulasa hua ki source account ", "mid1": " se illicit funds ", "mid2": " designated account ", "after": " mein deposit karwaye gaye."},
            {"id": "T_TXNA_HG_06", "held_out": True,  "before": "Statement of accounts se manifest hua ki account ", "mid1": " dwara remittance ", "mid2": " destination account ", "after": " mein move hua."},
        ],
        "hindi": [
            {"id": "T_TXNA_HI_01", "held_out": False, "before": "बैंक खाते की जांच से यह सिद्ध हुआ कि खाता ", "mid1": " से धनराशि ", "mid2": " बैंक खाता ", "after": " में अंतरित की गई।"},
            {"id": "T_TXNA_HI_02", "held_out": False, "before": "वित्तीय साक्ष्यों के अनुसार स्रोत खाता ", "mid1": " द्वारा कुल रकम ", "mid2": " संबंधित खाता ", "after": " में जमा कराई गई।"},
            {"id": "T_TXNA_HI_03", "held_out": False, "before": "खाता विवरण से स्पष्ट हुआ कि बैंक खाता ", "mid1": " से धन ", "mid2": " प्राप्तकर्ता खाता ", "after": " में भेजा गया।"},
            {"id": "T_TXNA_HI_04", "held_out": False, "before": "लेखा परीक्षण से प्रमाणित हुआ कि मूल खाता ", "mid1": " से ऑनलाइन माध्यम से रकम ", "mid2": " खाता ", "after": " में प्रेषित की गई।"},
            {"id": "T_TXNA_HI_05", "held_out": True,  "before": "हवाला लेन-देन विश्लेषण से प्रकट हुआ कि खाता ", "mid1": " से फंड ", "mid2": " अभीष्ट खाता ", "after": " में क्रेडिट कराया गया।"},
            {"id": "T_TXNA_HI_06", "held_out": True,  "before": "बैंक स्टेटमेंट के आधार पर स्रोत खाता ", "mid1": " द्वारा आपराधिक राशि ", "mid2": " लक्षित खाता ", "after": " में भेजी गई।"},
        ],
        "english": [
            {"id": "T_TXNA_EN_01", "held_out": False, "before": "Financial ledger inspection showed that source account ", "mid1": " credited the sum of ", "mid2": " into account ", "after": "."},
            {"id": "T_TXNA_EN_02", "held_out": False, "before": "Banking transaction trails evidenced that remitter account ", "mid1": " transferred remittance ", "mid2": " into bank account ", "after": "."},
            {"id": "T_TXNA_EN_03", "held_out": False, "before": "Account statement scrutiny demonstrated that origin account ", "mid1": " remitted funds amounting to ", "mid2": " to destination account ", "after": "."},
            {"id": "T_TXNA_EN_04", "held_out": False, "before": "Financial tracking revealed that bank account ", "mid1": " transferred illicit proceeds of ", "mid2": " into recipient account ", "after": "."},
            {"id": "T_TXNA_EN_05", "held_out": True,  "before": "Forensic financial auditing documented that source account ", "mid1": " routed cash volume of ", "mid2": " into syndicate account ", "after": "."},
            {"id": "T_TXNA_EN_06", "held_out": True,  "before": "Fiscal transaction analysis established that remitter account ", "mid1": " forwarded capital of ", "mid2": " to designated account ", "after": "."},
        ],
    },
    "CONTROLS_ACCOUNT": {
        "hinglish": [
            {"id": "T_CTRL_HG_01", "held_out": False, "before": "Yeh designated account ", "mid": " syndicate member ", "after": " dwara operate kiya jata hai."},
            {"id": "T_CTRL_HG_02", "held_out": False, "before": "Beneficiary account ", "mid": " par direct control abhiyukt ", "after": " ka paya gaya."},
            {"id": "T_CTRL_HG_03", "held_out": False, "before": "Bank KYC records ke mutabiq account ", "mid": " authorized signatory ", "after": " ke hawale tha."},
            {"id": "T_CTRL_HG_04", "held_out": False, "before": "Ukt khata ", "mid": " mule handler ", "after": " dwara secretly manage hota tha."},
            {"id": "T_CTRL_HG_05", "held_out": True,  "before": "Financial audit se reveal hua ki account ", "mid": " ka ultimate signing authority ", "after": " ke pas hai."},
            {"id": "T_CTRL_HG_06", "held_out": True,  "before": "Account statement se pata chala ki khata ", "mid": " ka poora disposition ", "after": " ke order par chalta hai."},
        ],
        "hindi": [
            {"id": "T_CTRL_HI_01", "held_out": False, "before": "यह निर्दिष्ट बैंक खाता ", "mid": " सिंडिकेट संचालक ", "after": " द्वारा संचालित किया जाता है।"},
            {"id": "T_CTRL_HI_02", "held_out": False, "before": "बैंक साक्ष्यों के अनुसार लाभार्थी खाता ", "mid": " पर वास्तविक नियंत्रण अभियुक्त ", "after": " का है।"},
            {"id": "T_CTRL_HI_03", "held_out": False, "before": "केवाईसी अभिलेखों से स्पष्ट हुआ कि खाता ", "mid": " का अधिकृत प्रचालक ", "after": " ही है।"},
            {"id": "T_CTRL_HI_04", "held_out": False, "before": "वित्तीय जांच में यह पाया गया कि खाता ", "mid": " की देखरेख सरगना ", "after": " द्वारा की जाती है।"},
            {"id": "T_CTRL_HI_05", "held_out": True,  "before": "खाता पत्रावली के अनुसार उक्त खाता ", "mid": " का वित्तीय संचालन ", "after": " के निर्देश पर होता है।"},
            {"id": "T_CTRL_HI_06", "held_out": True,  "before": "जांच में पाया गया कि बैंकिंग खाता ", "mid": " का समस्त वित्तीय अधिकार ", "after": " के पास सुरक्षित है।"},
        ],
        "english": [
            {"id": "T_CTRL_EN_01", "held_out": False, "before": "The recipient account ", "mid": " is operational under the personal stewardship of ", "after": "."},
            {"id": "T_CTRL_EN_02", "held_out": False, "before": "Banking KYC filings showed that designated account ", "mid": " is strictly controlled by ", "after": "."},
            {"id": "T_CTRL_EN_03", "held_out": False, "before": "Financial intelligence established that destination account ", "mid": " functions under the authority of ", "after": "."},
            {"id": "T_CTRL_EN_04", "held_out": False, "before": "Custodial ledger records showed that account ", "mid": " was operated by syndicate figure ", "after": "."},
            {"id": "T_CTRL_EN_05", "held_out": True,  "before": "Fiscal analysis documented that target account ", "mid": " remains under the ultimate executive command of ", "after": "."},
            {"id": "T_CTRL_EN_06", "held_out": True,  "before": "Forensic banking evidence established that account ", "mid": " is administered by key coordinator ", "after": "."},
        ],
    },
    "ALIAS_RECORD": {
        "hinglish": [
            {"id": "T_ALREC_HG_01", "held_out": False, "text": "Dossier verification se suspect ki alias identity verify hui."},
            {"id": "T_ALREC_HG_02", "held_out": False, "text": "Record room records ke anusaar suspect ke aliases confirmed paye gaye."},
            {"id": "T_ALREC_HG_03", "held_out": False, "text": "Crime database mein suspect ki alias profile officially documented hai."},
            {"id": "T_ALREC_HG_04", "held_out": False, "text": "Interrogation data ke anusaar suspect ke alias names match karte hain."},
            {"id": "T_ALREC_HG_05", "held_out": True,  "text": "Syndicate intelligence profile mein suspect ki alias pehchan darj hai."},
            {"id": "T_ALREC_HG_06", "held_out": True,  "text": "Special cell dossier note ke mutabiq suspect ke aliases authenticated hain."},
        ],
        "hindi": [
            {"id": "T_ALREC_HI_01", "held_out": False, "text": "अपराध डोजियर के अनुसार अभियुक्त की उपनाम पहचान सत्यापित पाई गई।"},
            {"id": "T_ALREC_HI_02", "held_out": False, "text": "थाना अभिलेख के अनुसार अभियुक्त के उर्फ नाम पूर्व से दर्ज हैं।"},
            {"id": "T_ALREC_HI_03", "held_out": False, "text": "अभिलेखीय जांच में अभियुक्त के उपनामों की पुष्टि की गई।"},
            {"id": "T_ALREC_HI_04", "held_out": False, "text": "डाटाबेस के अनुसार अभियुक्त की उर्फ पहचान प्रमाणित पाई गई।"},
            {"id": "T_ALREC_HI_05", "held_out": True,  "text": "खुफिया प्रोफाइल के आधार पर अभियुक्त के उपनामों का सत्यापन किया गया।"},
            {"id": "T_ALREC_HI_06", "held_out": True,  "text": "विशेष प्रकोष्ठ डोजियर के अनुसार अभियुक्त के उपनाम सत्यापित हैं।"},
        ],
        "english": [
            {"id": "T_ALREC_EN_01", "held_out": False, "text": "Dossier verification authenticated the operational aliases of the accused."},
            {"id": "T_ALREC_EN_02", "held_out": False, "text": "Police database records corroborated the criminal aliases of the suspect."},
            {"id": "T_ALREC_EN_03", "held_out": False, "text": "Official surveillance files authenticated the documented alias identities."},
            {"id": "T_ALREC_EN_04", "held_out": False, "text": "Archival dossier data confirmed the registered aliases of the perpetrator."},
            {"id": "T_ALREC_EN_05", "held_out": True,  "text": "Syndicate intelligence confirmed the operational alias profile of the suspect."},
            {"id": "T_ALREC_EN_06", "held_out": True,  "text": "Intelligence records independently verified the syndicate alias identities."},
        ],
    },
}

BOILERPLATE_OPENINGS = {
    "hinglish": [
        "Police Station Special Staff ke tahat FIR No.201/2026 u/s 318(4)/61(2) BNS ke antargat mukadma darj kiya gaya.",
        "Crime branch investigation unit dwara ukt FIR No.302/2026 u/s 318(4)/61(2) BNS ke tahat prathmiki register hui.",
        "Secret vigilance report ke adhar par FIR No.403/2026 u/s 318(4)/61(2) BNS ke antargat formal karyawahi shuru ki gayi.",
        "Cyber crime cell mein prathmikta se FIR No.504/2026 u/s 318(4)/61(2) BNS ke antargat matter initiate kiya gaya.",
        "Police monitoring cell ke adesh par FIR No.605/2026 u/s 318(4)/61(2) BNS ke antargat mamla darj hua.",
    ],
    "hindi": [
        "थाना अपराध शाखा के अंतर्गत मुकदमा अपराध संख्या २०१/२०२६ धारा ३१८(४)/६१(२) BNS में विधिक कार्यवाही प्रारंभ की गई।",
        "विशेष कार्यबल द्वारा मुकदमा अपराध संख्या ३०२/२०२६ धारा ३१८(४)/६१(२) BNS के तहत अभियोग पंजीकृत किया गया।",
        "गोपनीय सूचना के आधार पर मुकदमा अपराध संख्या ४०३/२०२६ धारा ३१८(४)/६१(२) BNS में प्रथम सूचना रिपोर्ट दर्ज हुई।",
        "साइबर अपराध नियंत्रण प्रकोष्ठ द्वारा मुकदमा अपराध संख्या ५०४/२०२६ धारा ३१८(४)/६१(२) BNS के तहत प्राथमिकी लिखी गई।",
        "थाना केंद्रीय प्रकोष्ठ में मुकदमा अपराध संख्या ६०५/२०२६ धारा ३१८(४)/६१(२) BNS के अंतर्गत वैधानिक विवेचना शुरू की गई।",
    ],
    "english": [
        "Case proceedings were formally initiated under FIR No.201/2026 u/s 318(4)/61(2) BNS at Special Crime Branch.",
        "Police intelligence wing registered the preliminary investigation under FIR No.302/2026 u/s 318(4)/61(2) BNS.",
        "A formal criminal investigation commenced vide FIR No.403/2026 u/s 318(4)/61(2) BNS at Central Police Division.",
        "Vigilance and anti-fraud unit instituted official case proceedings under FIR No.504/2026 u/s 318(4)/61(2) BNS.",
        "Statutory criminal proceedings were duly registered under FIR No.605/2026 u/s 318(4)/61(2) BNS by the cyber cell.",
    ],
}

BOILERPLATE_CLOSINGS = {
    "hinglish": [
        "Zabt shuda material ko sealed pullanda mein safe custody hetu police malkhana mein jamah kiya gaya.",
        "Baramad shuda sabooton ko seal-bandh karke aage ki legal proceeding ke liye safe store kiya gaya.",
        "Maukai baramadgi ke tamam items ko proper seizure memo ke sath police custody mein rakha gaya.",
        "Zabt shuda items ko inventory register mein darj karke legal disposal hetu surakshit kiya gaya.",
        "Mauke par tayyar shuda sealed parcels ko judicial custody mein peshi hetu malkhana transmit kiya gaya.",
    ],
    "hindi": [
        "बरामद सामग्री को नियमानुसार सील कर सुरक्षित अभिरक्षा में मालखाना जमा कराया गया।",
        "जब्त शुदा साक्ष्यों को सीलबंद पुलिंदे में आगामी वैधानिक प्रक्रिया हेतु सुरक्षित रखा गया।",
        "मौके पर तैयार जब्ती सूची अनुसार समस्त सामग्री को थाना मालखाना में सुरक्षित दाखिल कराया गया।",
        "बरामदगी के समस्त वस्तुओं को सील मुहर कर विधिक परीक्षण हेतु अभिरक्षा में सुरक्षित किया गया।",
        "जब्त सामग्री को पंचनामा फर्द सहित न्यायिक अभिरक्षा में प्रस्तुत करने हेतु सुरक्षित रखा गया।",
    ],
    "english": [
        "All seized evidentiary items were sealed in cloth pullandas and lodged into the police repository.",
        "The recovered contraband and related articles were duly inventoried and lodged into safe custody.",
        "Seizure memos were executed on the spot and all relevant material placed in secure departmental custody.",
        "Sealed exhibits were deposited into the departmental malkhana under proper acknowledgment for further proceedings.",
        "All collected material objects were safely packed and sealed according to statutory procedure for trial submission.",
    ],
}


class SentenceBuilder:
    """Builds a single sentence from text chunks and labelled entity segments."""
    def __init__(self):
        self.segments: List[Tuple[str, Optional[Dict[str, Any]]]] = []

    def text(self, s: str) -> "SentenceBuilder":
        self.segments.append((s, None))
        return self

    def entity(
        self,
        surface: str,
        ent_type: str,
        value: Any,
        entity_key: str,
        truth_id: Optional[str] = None,
        aliases: Optional[List[str]] = None,
        role: Optional[str] = None
    ) -> Dict[str, Any]:
        ent_data = {
            "type": ent_type,
            "value": value,
            "entity_key": str(entity_key),
            "truth_id": truth_id,
            "aliases": aliases or [],
            "role": role,
        }
        self.segments.append((surface, ent_data))
        return ent_data


class FIRBuilder:
    """Orchestrates multi-sentence FIR text construction and answer key generation."""
    def __init__(self, doc_id: str, split: str, fir_type: str, language: str):
        self.doc_id = doc_id
        self.split = split
        self.fir_type = fir_type
        self.language = language
        self.sentences: List[SentenceBuilder] = []
        self.relationships_to_add: List[Tuple[SentenceBuilder, Dict[str, Any]]] = []
        self.template_ids_used: List[str] = []

    def record_template(self, t_id: str):
        if t_id not in self.template_ids_used:
            self.template_ids_used.append(t_id)

    def add_sentence(
        self,
        sb: SentenceBuilder,
        relations_in_sentence: Optional[List[Dict[str, Any]]] = None
    ) -> None:
        self.sentences.append(sb)
        if relations_in_sentence:
            for rel in relations_in_sentence:
                self.relationships_to_add.append((sb, rel))

    def build(self) -> Tuple[str, Dict[str, Any]]:
        full_text = ""
        entities = []
        ent_counter = 1
        sentence_spans = {}

        for idx, sb in enumerate(self.sentences):
            if full_text:
                full_text += " "
            s_start = len(full_text)
            for surface, ent_data in sb.segments:
                e_start = len(full_text)
                full_text += surface
                e_end = len(full_text)
                if ent_data is not None:
                    ent_id = f"E{ent_counter}"
                    ent_counter += 1
                    ent_obj = {
                        "id": ent_id,
                        "entity_key": ent_data["entity_key"],
                        "label": ent_data["type"],
                        "type": ent_data["type"],
                        "text": surface,
                        "surface": surface,
                        "start": e_start,
                        "end": e_end,
                        "char_span": [e_start, e_end],
                        "role": ent_data.get("role"),
                        "truth_id": ent_data.get("truth_id"),
                        "value": ent_data["value"],
                        "aliases": ent_data.get("aliases", []),
                    }
                    entities.append(ent_obj)
                    ent_data["_id"] = ent_id
            s_end = len(full_text)
            sentence_spans[id(sb)] = [s_start, s_end]

        relationships = []
        for sb, rel_def in self.relationships_to_add:
            source_id = rel_def["source_ref"]["_id"]
            target_id = rel_def["target_ref"]["_id"]
            source_key = rel_def["source_ref"]["entity_key"]
            target_key = rel_def["target_ref"]["entity_key"]
            evidence_span = sentence_spans[id(sb)]
            rel_obj = {
                "type": rel_def["relation"],
                "relation": rel_def["relation"],
                "source_key": source_key,
                "target_key": target_key,
                "source_mention": source_id,
                "target_mention": target_id,
                "source": source_id,
                "target": target_id,
                "amount": rel_def.get("amount"),
                "evidence_char_span": evidence_span,
            }
            if rel_def.get("txn_id"):
                rel_obj["txn_id"] = rel_def["txn_id"]
            relationships.append(rel_obj)

        answer_key = {
            "source_doc_id": self.doc_id,
            "split": self.split,
            "fir_type": self.fir_type,
            "template_ids": self.template_ids_used,
            "language": self.language,
            "entities": entities,
            "relationships": relationships,
        }
        return full_text, answer_key


def load_case_data(case_dir: Path) -> Dict[str, Any]:
    """Loads and indexes case data from truth.json, cdr.csv, and bank.csv."""
    truth_file = case_dir / "truth.json"
    cdr_file = case_dir / "cdr.csv"
    bank_file = case_dir / "bank.csv"

    if not truth_file.exists() or not cdr_file.exists() or not bank_file.exists():
        raise FileNotFoundError(f"Case files missing in {case_dir}")

    truth = json.loads(truth_file.read_text(encoding="utf-8"))
    with open(cdr_file, "r", encoding="utf-8") as f:
        cdr_rows = list(csv.DictReader(f))
    with open(bank_file, "r", encoding="utf-8") as f:
        bank_rows = list(csv.DictReader(f))

    people_map = {p["person_id"]: p for p in truth["people"]}

    # Account ownership mapping
    account_to_person = {}
    person_to_accounts: Dict[str, List[str]] = {}
    for p in truth["people"]:
        acc_nums = [acc["account_number"] for acc in p.get("accounts", [])]
        person_to_accounts[p["person_id"]] = acc_nums
        for acc_num in acc_nums:
            account_to_person[acc_num] = p

    # CDR contacts index (deterministic order)
    cdr_contacts: Dict[str, List[str]] = {}
    for r in cdr_rows:
        a, b = r["a_party"], r["b_party"]
        cdr_contacts.setdefault(a, set()).add(b)
        cdr_contacts.setdefault(b, set()).add(a)

    sorted_cdr_contacts = {
        ph: sorted(list(contacts)) for ph, contacts in cdr_contacts.items()
    }

    # Bank transactions index by from_acct and to_acct
    txns_by_from_acc: Dict[str, List[Dict[str, Any]]] = {}
    txns_by_to_acc: Dict[str, List[Dict[str, Any]]] = {}
    for r in bank_rows:
        txns_by_from_acc.setdefault(r["from_acct"], []).append(r)
        txns_by_to_acc.setdefault(r["to_acct"], []).append(r)

    # Person outgoing transactions
    person_outgoing_txns: Dict[str, List[Dict[str, Any]]] = {}
    for pid, accs in person_to_accounts.items():
        for a in accs:
            if a in txns_by_from_acc:
                person_outgoing_txns.setdefault(pid, []).extend(txns_by_from_acc[a])

    return {
        "truth": truth,
        "cdr_rows": cdr_rows,
        "bank_rows": bank_rows,
        "people_map": people_map,
        "account_to_person": account_to_person,
        "person_to_accounts": person_to_accounts,
        "cdr_contacts": sorted_cdr_contacts,
        "txns_by_from_acc": txns_by_from_acc,
        "txns_by_to_acc": txns_by_to_acc,
        "person_outgoing_txns": person_outgoing_txns,
    }


def find_grounded_transfer(
    suspect_p: Dict[str, Any],
    case_data: Dict[str, Any],
    prefer_person_sender: bool,
    offset: int = 0,
    forced_transfer_kind: Optional[str] = None
) -> Tuple[Dict[str, Any], str, str, Dict[str, Any], str]:
    """
    Finds a real bank transaction matching case data.
    Returns: (txn_row, from_acct, to_acct, controller_person, transfer_kind)
    transfer_kind is either 'PERSON_TO_ACCOUNT' or 'ACCOUNT_TO_ACCOUNT'.
    """
    bank_rows = case_data["bank_rows"]
    person_outgoing = case_data["person_outgoing_txns"]
    account_to_person = case_data["account_to_person"]
    people_map = case_data["people_map"]

    pid = suspect_p["person_id"]
    can_person_sender = (pid in person_outgoing and len(person_outgoing[pid]) > 0)

    use_person_sender = False
    if forced_transfer_kind == "PERSON_TO_ACCOUNT":
        use_person_sender = True
    elif forced_transfer_kind == "ACCOUNT_TO_ACCOUNT":
        use_person_sender = False
    else:
        use_person_sender = (prefer_person_sender and can_person_sender)

    if use_person_sender:
        if can_person_sender:
            candidate_txns = person_outgoing[pid]
            sender_person = suspect_p
        else:
            # Fallback to an operative who has outgoing txns
            valid_pids = [p for p in person_outgoing if len(person_outgoing[p]) > 0]
            fallback_pid = valid_pids[offset % len(valid_pids)]
            candidate_txns = person_outgoing[fallback_pid]
            sender_person = people_map[fallback_pid]

        txn_row = candidate_txns[offset % len(candidate_txns)]
        from_acct = txn_row["from_acct"]
        to_acct = txn_row["to_acct"]
        ctrl = account_to_person.get(to_acct)
        if not ctrl:
            gang = sender_person.get("gang", "GANG_A")
            kp_id = "PER_B_KP_01" if gang == "GANG_B" else "PER_A_KP_01"
            ctrl = people_map[kp_id]
        return txn_row, from_acct, to_acct, ctrl, "PERSON_TO_ACCOUNT"
    else:
        # ACCOUNT_TO_ACCOUNT
        txn_row = bank_rows[(offset * 13) % len(bank_rows)]
        from_acct = txn_row["from_acct"]
        to_acct = txn_row["to_acct"]
        ctrl = account_to_person.get(to_acct)
        if not ctrl:
            gang = suspect_p.get("gang", "GANG_A")
            kp_id = "PER_B_KP_01" if gang == "GANG_B" else "PER_A_KP_01"
            ctrl = people_map[kp_id]
        return txn_row, from_acct, to_acct, ctrl, "ACCOUNT_TO_ACCOUNT"


def pick_template(
    rel: str,
    lang: str,
    is_test: bool,
    force_held_out: bool,
    rng: random.Random
) -> Dict[str, Any]:
    """Selects a template for the given relation and language respecting held-out test constraints."""
    catalog = TEMPLATES[rel][lang]
    if is_test and force_held_out:
        candidates = [t for t in catalog if t["held_out"]]
    elif is_test:
        candidates = catalog  # Test can use any template
    else:
        candidates = [t for t in catalog if not t["held_out"]]  # Train and dev NEVER use held_out

    return rng.choice(candidates)


def generate_fir_v2(
    idx: int,
    spec: Dict[str, Any],
    case_data: Dict[str, Any],
    rng: random.Random
) -> Tuple[str, Dict[str, Any]]:
    """Generates an upgraded FIR adhering to split, fir_type, templates, and decoy rules."""
    doc_id = f"FIR_{idx:02d}"
    split = spec["split"]
    fir_type = spec["fir_type"]
    lang = spec["language"]
    is_test = (split == "test")

    builder = FIRBuilder(doc_id=doc_id, split=split, fir_type=fir_type, language=lang)
    people_map = case_data["people_map"]
    suspect_p = people_map[spec["suspect_ids"][0]]

    # Track held-out usage for test split
    used_held_out = False

    # Names and aliases
    suspect_name = suspect_p["name"]
    father_name = suspect_p["father_name"]
    aliases = spec.get("aliases") if spec.get("aliases") is not None else suspect_p.get("aliases", [])
    if lang == "hindi":
        suspect_name = NAME_HINDI_MAP.get(suspect_name, suspect_name)
        father_name = NAME_HINDI_MAP.get(father_name, father_name)
        aliases = [NAME_HINDI_MAP.get(a, a) for a in aliases]

    # Non-labelled decoys: BNS terminology only (No IPC!)
    fir_num_decoy = f"FIR No. {rng.randint(101, 899)}/2026" if lang != "hindi" else f"मुकदमा अपराध संख्या {to_devanagari_digits(rng.randint(101, 899))}/२०२६"
    section_decoy = "u/s 318(4)/61(2) BNS" if lang != "hindi" else "धारा ३१८(४)/६१(२) BNS"
    datetime_decoy = f"dated {rng.randint(10, 28)}.01.2026 at {rng.randint(10, 22)}:{rng.randint(10, 59)} hrs" if lang != "hindi" else f"दिनांक {to_devanagari_digits(rng.randint(10, 28))}.०१.२०२६ समय {to_devanagari_digits(rng.randint(10, 22))}:{to_devanagari_digits(rng.randint(10, 59))} बजे"
    vehicle_decoy = f"DL-{rng.randint(1, 9)}C-AB-{rng.randint(1000, 9999)}"

    # Sentences collector
    ordered_sentences: List[Tuple[SentenceBuilder, Optional[List[Dict[str, Any]]]]] = []

    # 1. Heading & Decoy preamble
    sb_pre = SentenceBuilder()
    opening_text = spec.get("opening_sentence") or BOILERPLATE_OPENINGS[lang][spec.get("opening_idx", idx % 5)]
    sb_pre.text(opening_text)
    ordered_sentences.append((sb_pre, None))

    # 2. Suspect Introduction sentence (with ALIAS and FATHER labelled spans)
    sb_susp = SentenceBuilder()
    if lang == "hinglish":
        sb_susp.text(f"Gupte suchna ke aadhar par police team ne suspicious vehicle {vehicle_decoy} ko intercept karke suspect ")
        ent_suspect = sb_susp.entity(
            surface=suspect_name,
            ent_type="PERSON",
            value=suspect_p["name"],
            entity_key=suspect_p["person_id"],
            truth_id=suspect_p["person_id"],
            aliases=aliases,
            role="SUSPECT"
        )
        if aliases:
            for a_idx, alias_item in enumerate(aliases):
                sep = " urf " if a_idx == 0 else " @ "
                sb_susp.text(sep)
                sb_susp.entity(
                    surface=alias_item,
                    ent_type="ALIAS",
                    value=suspect_p["name"],
                    entity_key=suspect_p["person_id"],
                    truth_id=suspect_p["person_id"],
                    aliases=[],
                    role=None
                )
        sb_susp.text(" s/o Shri ")
        sb_susp.entity(
            surface=father_name,
            ent_type="PERSON",
            value=suspect_p["father_name"],
            entity_key=f"FATHER:{suspect_p['father_name']}",
            truth_id=None,
            aliases=[],
            role="FATHER"
        )
        sb_susp.text(f" r/o {spec['address']} ko hirasat mein liya.")
    elif lang == "hindi":
        sb_susp.text(f"विशेष जांच दल ने वाहन चेकिंग के दौरान संदिग्ध वाहन {vehicle_decoy} को रोककर अभियुक्त ")
        ent_suspect = sb_susp.entity(
            surface=suspect_name,
            ent_type="PERSON",
            value=suspect_p["name"],
            entity_key=suspect_p["person_id"],
            truth_id=suspect_p["person_id"],
            aliases=aliases,
            role="SUSPECT"
        )
        if aliases:
            for a_idx, alias_item in enumerate(aliases):
                sb_susp.text(" उर्फ ")
                sb_susp.entity(
                    surface=alias_item,
                    ent_type="ALIAS",
                    value=suspect_p["name"],
                    entity_key=suspect_p["person_id"],
                    truth_id=suspect_p["person_id"],
                    aliases=[],
                    role=None
                )
        sb_susp.text(" आत्मज श्री ")
        sb_susp.entity(
            surface=father_name,
            ent_type="PERSON",
            value=suspect_p["father_name"],
            entity_key=f"FATHER:{suspect_p['father_name']}",
            truth_id=None,
            aliases=[],
            role="FATHER"
        )
        sb_susp.text(f" निवासी {spec['address']} को गिरफ्तार किया।")
    else:
        sb_susp.text(f"Acting on specific intelligence, police intercepted vehicle {vehicle_decoy} and apprehended accused ")
        ent_suspect = sb_susp.entity(
            surface=suspect_name,
            ent_type="PERSON",
            value=suspect_p["name"],
            entity_key=suspect_p["person_id"],
            truth_id=suspect_p["person_id"],
            aliases=aliases,
            role="SUSPECT"
        )
        if aliases:
            for a_idx, alias_item in enumerate(aliases):
                sep = " alias " if a_idx == 0 else " @ "
                sb_susp.text(sep)
                sb_susp.entity(
                    surface=alias_item,
                    ent_type="ALIAS",
                    value=suspect_p["name"],
                    entity_key=suspect_p["person_id"],
                    truth_id=suspect_p["person_id"],
                    aliases=[],
                    role=None
                )
        sb_susp.text(" s/o Shri ")
        sb_susp.entity(
            surface=father_name,
            ent_type="PERSON",
            value=suspect_p["father_name"],
            entity_key=f"FATHER:{suspect_p['father_name']}",
            truth_id=None,
            aliases=[],
            role="FATHER"
        )
        sb_susp.text(f" r/o {spec['address']}.")
    ordered_sentences.append((sb_susp, None))

    # Additional co-suspects for MULTI_SUSPECT
    ent_co_suspects = []
    if fir_type == "MULTI_SUSPECT" and len(spec["suspect_ids"]) > 1:
        for co_id in spec["suspect_ids"][1:]:
            co_p = people_map[co_id]
            co_name = co_p["name"]
            co_father = co_p["father_name"]
            co_aliases = co_p.get("aliases", [])
            if lang == "hindi":
                co_name = NAME_HINDI_MAP.get(co_name, co_name)
                co_father = NAME_HINDI_MAP.get(co_father, co_father)
                co_aliases = [NAME_HINDI_MAP.get(a, a) for a in co_aliases]

            sb_co = SentenceBuilder()
            if lang == "hinglish":
                sb_co.text("Mauke par co-accused ")
                e_co = sb_co.entity(
                    surface=co_name,
                    ent_type="PERSON",
                    value=co_p["name"],
                    entity_key=co_p["person_id"],
                    truth_id=co_p["person_id"],
                    aliases=co_aliases,
                    role="SUSPECT"
                )
                if co_aliases:
                    for a_idx, a_item in enumerate(co_aliases):
                        sep = " urf " if a_idx == 0 else " @ "
                        sb_co.text(sep)
                        sb_co.entity(
                            surface=a_item,
                            ent_type="ALIAS",
                            value=co_p["name"],
                            entity_key=co_p["person_id"],
                            truth_id=co_p["person_id"],
                            aliases=[],
                            role=None
                        )
                sb_co.text(" s/o Shri ")
                sb_co.entity(
                    surface=co_father,
                    ent_type="PERSON",
                    value=co_p["father_name"],
                    entity_key=f"FATHER:{co_p['father_name']}",
                    truth_id=None,
                    aliases=[],
                    role="FATHER"
                )
                sb_co.text(" bhi maujood paya gaya jise apprehended kiya gaya.")
            elif lang == "hindi":
                sb_co.text("घटनास्थल पर सह-अभियुक्त ")
                e_co = sb_co.entity(
                    surface=co_name,
                    ent_type="PERSON",
                    value=co_p["name"],
                    entity_key=co_p["person_id"],
                    truth_id=co_p["person_id"],
                    aliases=co_aliases,
                    role="SUSPECT"
                )
                if co_aliases:
                    for a_idx, a_item in enumerate(co_aliases):
                        sb_co.text(" उर्फ ")
                        sb_co.entity(
                            surface=a_item,
                            ent_type="ALIAS",
                            value=co_p["name"],
                            entity_key=co_p["person_id"],
                            truth_id=co_p["person_id"],
                            aliases=[],
                            role=None
                        )
                sb_co.text(" आत्मज श्री ")
                sb_co.entity(
                    surface=co_father,
                    ent_type="PERSON",
                    value=co_p["father_name"],
                    entity_key=f"FATHER:{co_p['father_name']}",
                    truth_id=None,
                    aliases=[],
                    role="FATHER"
                )
                sb_co.text(" को भी हिरासत में लिया गया।")
            else:
                sb_co.text("Co-conspirator ")
                e_co = sb_co.entity(
                    surface=co_name,
                    ent_type="PERSON",
                    value=co_p["name"],
                    entity_key=co_p["person_id"],
                    truth_id=co_p["person_id"],
                    aliases=co_aliases,
                    role="SUSPECT"
                )
                if co_aliases:
                    for a_idx, a_item in enumerate(co_aliases):
                        sep = " alias " if a_idx == 0 else " @ "
                        sb_co.text(sep)
                        sb_co.entity(
                            surface=a_item,
                            ent_type="ALIAS",
                            value=co_p["name"],
                            entity_key=co_p["person_id"],
                            truth_id=co_p["person_id"],
                            aliases=[],
                            role=None
                        )
                sb_co.text(" s/o Shri ")
                sb_co.entity(
                    surface=co_father,
                    ent_type="PERSON",
                    value=co_p["father_name"],
                    entity_key=f"FATHER:{co_p['father_name']}",
                    truth_id=None,
                    aliases=[],
                    role="FATHER"
                )
                sb_co.text(" was simultaneously taken into custody.")
            ent_co_suspects.append((e_co, co_p))
            ordered_sentences.append((sb_co, None))

    # Device & IMEI Sentence (for FULL, CALLS_ONLY, DEVICE_ONLY, MULTI_SUSPECT)
    ent_phone = None
    if fir_type in ("FULL", "CALLS_ONLY", "DEVICE_ONLY", "MULTI_SUSPECT"):
        force_h = (is_test and not used_held_out)
        t_owns = pick_template("OWNS_DEVICE", lang, is_test, force_h, rng)
        if t_owns["held_out"]:
            used_held_out = True
        builder.record_template(t_owns["id"])

        force_h2 = (is_test and not used_held_out and rng.random() < 0.5)
        t_imei = pick_template("ASSOCIATED_IMEI", lang, is_test, force_h2, rng)
        if t_imei["held_out"]:
            used_held_out = True
        builder.record_template(t_imei["id"])

        phone_obj = suspect_p["phones"][0]
        raw_phone = phone_obj["phone"]
        raw_imei = spec.get("override_imei") or phone_obj["imei"]

        phone_fmt = spec.get("phone_format", "plain")
        if phone_fmt == "space":
            phone_surface = f"{raw_phone[:5]} {raw_phone[5:]}"
        elif phone_fmt == "plus91":
            phone_surface = f"+91-{raw_phone}"
        elif phone_fmt == "devanagari" or lang == "hindi":
            phone_surface = to_devanagari_digits(raw_phone) if phone_fmt == "devanagari" else raw_phone
        else:
            phone_surface = raw_phone

        imei_surface = to_devanagari_digits(raw_imei) if (phone_fmt == "devanagari" and lang == "hindi") else raw_imei

        sb_dev = SentenceBuilder()
        sb_dev.text(t_owns["before"])
        ent_susp_dev = sb_dev.entity(
            surface=suspect_name,
            ent_type="PERSON",
            value=suspect_p["name"],
            entity_key=suspect_p["person_id"],
            truth_id=suspect_p["person_id"],
            aliases=aliases,
            role="SUSPECT"
        )
        sb_dev.text(t_owns["mid"])

        ent_phone = sb_dev.entity(
            surface=phone_surface,
            ent_type="PHONE",
            value=raw_phone,
            entity_key=raw_phone,
            truth_id=None,
            aliases=[],
            role=None
        )
        sb_dev.text(t_owns["after"]).text(" ")

        sb_dev.text(t_imei["before"])
        ent_phone_imei = sb_dev.entity(
            surface=phone_surface,
            ent_type="PHONE",
            value=raw_phone,
            entity_key=raw_phone,
            truth_id=None,
            aliases=[],
            role=None
        )
        sb_dev.text(t_imei["mid"])
        ent_imei = sb_dev.entity(
            surface=imei_surface,
            ent_type="IMEI",
            value=raw_imei,
            entity_key=raw_imei,
            truth_id=None,
            aliases=[],
            role=None
        )
        sb_dev.text(t_imei["after"])

        rels_dev = [
            {"source_ref": ent_susp_dev, "target_ref": ent_phone, "relation": "OWNS_DEVICE"},
            {"source_ref": ent_phone_imei, "target_ref": ent_imei, "relation": "ASSOCIATED_IMEI"},
        ]

        # For shared handset in MULTI_SUSPECT: co-suspect also owns a phone with the SAME IMEI
        if ent_co_suspects and spec.get("override_imei"):
            e_co, co_p = ent_co_suspects[0]
            co_ph_obj = co_p["phones"][0]
            co_raw_ph = co_ph_obj["phone"]
            co_ph_surf = to_devanagari_digits(co_raw_ph) if (phone_fmt == "devanagari" and lang == "hindi") else co_raw_ph

            sb_dev.text(" ")
            if lang == "hinglish":
                sb_dev.text("Co-accused ")
                ent_co_dev = sb_dev.entity(
                    surface=co_p["name"],
                    ent_type="PERSON",
                    value=co_p["name"],
                    entity_key=co_p["person_id"],
                    truth_id=co_p["person_id"],
                    aliases=co_p.get("aliases", []),
                    role="SUSPECT"
                )
                sb_dev.text(" ke possession se second phone ")
                e_co_ph = sb_dev.entity(
                    surface=co_ph_surf,
                    ent_type="PHONE",
                    value=co_raw_ph,
                    entity_key=co_raw_ph,
                    truth_id=None,
                    aliases=[],
                    role=None
                )
                sb_dev.text(" recover hua jiska hardware IMEI ")
                e_co_imei = sb_dev.entity(
                    surface=imei_surface,
                    ent_type="IMEI",
                    value=raw_imei,
                    entity_key=raw_imei,
                    truth_id=None,
                    aliases=[],
                    role=None
                )
                sb_dev.text(" common paya gaya.")
            elif lang == "hindi":
                co_hi_name = NAME_HINDI_MAP.get(co_p["name"], co_p["name"])
                sb_dev.text("सह-अभियुक्त ")
                ent_co_dev = sb_dev.entity(
                    surface=co_hi_name,
                    ent_type="PERSON",
                    value=co_p["name"],
                    entity_key=co_p["person_id"],
                    truth_id=co_p["person_id"],
                    aliases=co_p.get("aliases", []),
                    role="SUSPECT"
                )
                sb_dev.text(" के पास से अन्य फोन ")
                e_co_ph = sb_dev.entity(
                    surface=co_ph_surf,
                    ent_type="PHONE",
                    value=co_raw_ph,
                    entity_key=co_raw_ph,
                    truth_id=None,
                    aliases=[],
                    role=None
                )
                sb_dev.text(" बरामद हुआ जिसमें साझा आईएमईआई ")
                e_co_imei = sb_dev.entity(
                    surface=imei_surface,
                    ent_type="IMEI",
                    value=raw_imei,
                    entity_key=raw_imei,
                    truth_id=None,
                    aliases=[],
                    role=None
                )
                sb_dev.text(" संचालित था।")
            else:
                sb_dev.text("Co-conspirator ")
                ent_co_dev = sb_dev.entity(
                    surface=co_p["name"],
                    ent_type="PERSON",
                    value=co_p["name"],
                    entity_key=co_p["person_id"],
                    truth_id=co_p["person_id"],
                    aliases=co_p.get("aliases", []),
                    role="SUSPECT"
                )
                sb_dev.text(" operated another handset ")
                e_co_ph = sb_dev.entity(
                    surface=co_ph_surf,
                    ent_type="PHONE",
                    value=co_raw_ph,
                    entity_key=co_raw_ph,
                    truth_id=None,
                    aliases=[],
                    role=None
                )
                sb_dev.text(" sharing identical hardware IMEI ")
                e_co_imei = sb_dev.entity(
                    surface=imei_surface,
                    ent_type="IMEI",
                    value=raw_imei,
                    entity_key=raw_imei,
                    truth_id=None,
                    aliases=[],
                    role=None
                )
                sb_dev.text(".")

            rels_dev.append({"source_ref": ent_co_dev, "target_ref": e_co_ph, "relation": "OWNS_DEVICE"})
            rels_dev.append({"source_ref": e_co_ph, "target_ref": e_co_imei, "relation": "ASSOCIATED_IMEI"})

        ordered_sentences.append((sb_dev, rels_dev))

    # CDR Calls Sentence (for FULL, CALLS_ONLY, MULTI_SUSPECT)
    if fir_type in ("FULL", "CALLS_ONLY", "MULTI_SUSPECT") and ent_phone is not None:
        force_h = (is_test and not used_held_out and rng.random() < 0.5)
        t_call = pick_template("COMMUNICATED_WITH", lang, is_test, force_h, rng)
        if t_call["held_out"]:
            used_held_out = True
        builder.record_template(t_call["id"])

        candidates = case_data["cdr_contacts"].get(raw_phone, [])
        contact_ph = candidates[spec.get("contact_idx", 0) % len(candidates)] if candidates else case_data["cdr_rows"][0]["b_party"]
        contact_ph_surf = to_devanagari_digits(contact_ph) if (spec.get("phone_format") == "devanagari" and lang == "hindi") else contact_ph

        sb_call = SentenceBuilder()
        sb_call.text(t_call["before"])
        ent_call_src = sb_call.entity(
            surface=phone_surface,
            ent_type="PHONE",
            value=raw_phone,
            entity_key=raw_phone,
            truth_id=None,
            aliases=[],
            role=None
        )
        sb_call.text(t_call["mid"])
        ent_contact_ph = sb_call.entity(
            surface=contact_ph_surf,
            ent_type="PHONE",
            value=contact_ph,
            entity_key=contact_ph,
            truth_id=None,
            aliases=[],
            role=None
        )
        sb_call.text(t_call["after"])

        ordered_sentences.append((sb_call, [
            {"source_ref": ent_call_src, "target_ref": ent_contact_ph, "relation": "COMMUNICATED_WITH"}
        ]))

    # Financial Sentence (for FULL, MONEY_ONLY, MULTI_SUSPECT)
    if fir_type in ("FULL", "MONEY_ONLY", "MULTI_SUSPECT"):
        (txn_row, from_acct_num, to_acct_num, controller_person, transfer_kind) = find_grounded_transfer(
            suspect_p, case_data, prefer_person_sender=(idx % 2 == 1), offset=idx,
            forced_transfer_kind=spec.get("transfer_kind")
        )
        txn_amt = float(txn_row["amount"])
        matching_txn_id = txn_row["txn_id"]

        amt_style_idx = idx % 4
        amt_surf = format_amount_style(txn_amt, amt_style_idx, lang=lang)

        to_acc_surface = to_devanagari_digits(to_acct_num) if (spec.get("phone_format") == "devanagari" and lang == "hindi") else to_acct_num
        from_acc_surface = to_devanagari_digits(from_acct_num) if (spec.get("phone_format") == "devanagari" and lang == "hindi") else from_acct_num

        ctrl_name = controller_person["name"]
        ctrl_aliases = controller_person.get("aliases", [])
        if lang == "hindi":
            ctrl_name = NAME_HINDI_MAP.get(ctrl_name, ctrl_name)
            ctrl_aliases = [NAME_HINDI_MAP.get(a, a) for a in ctrl_aliases]

        sb_fin = SentenceBuilder()

        if transfer_kind == "PERSON_TO_ACCOUNT":
            force_h_txn = (is_test and not used_held_out)
            t_txn = pick_template("TRANSFERRED_FUNDS", lang, is_test, force_h_txn, rng)
            if t_txn["held_out"]:
                used_held_out = True
            builder.record_template(t_txn["id"])

            sb_fin.text(t_txn["before"])
            ent_sender = sb_fin.entity(
                surface=suspect_name,
                ent_type="PERSON",
                value=suspect_p["name"],
                entity_key=suspect_p["person_id"],
                truth_id=suspect_p["person_id"],
                aliases=aliases,
                role="SUSPECT"
            )
            sb_fin.text(t_txn["mid1"])
            ent_amt = sb_fin.entity(
                surface=amt_surf,
                ent_type="AMOUNT",
                value=txn_amt,
                entity_key=f"AMOUNT:{txn_amt:.2f}",
                truth_id=None,
                aliases=[],
                role=None
            )
            sb_fin.text(t_txn["mid2"])
            ent_to_acc = sb_fin.entity(
                surface=to_acc_surface,
                ent_type="ACCOUNT",
                value=to_acct_num,
                entity_key=to_acct_num,
                truth_id=None,
                aliases=[],
                role=None
            )
            sb_fin.text(t_txn["after"]).text(" ")

            rel_transfer = {
                "source_ref": ent_sender,
                "target_ref": ent_to_acc,
                "relation": "TRANSFERRED_FUNDS",
                "amount": txn_amt,
                "txn_id": matching_txn_id
            }
        else:
            # ACCOUNT_TO_ACCOUNT
            force_h_txn = (is_test and not used_held_out)
            t_txn = pick_template("TRANSFERRED_FUNDS_ACCT", lang, is_test, force_h_txn, rng)
            if t_txn["held_out"]:
                used_held_out = True
            builder.record_template(t_txn["id"])

            sb_fin.text(t_txn["before"])
            ent_from_acc = sb_fin.entity(
                surface=from_acc_surface,
                ent_type="ACCOUNT",
                value=from_acct_num,
                entity_key=from_acct_num,
                truth_id=None,
                aliases=[],
                role=None
            )
            sb_fin.text(t_txn["mid1"])
            ent_amt = sb_fin.entity(
                surface=amt_surf,
                ent_type="AMOUNT",
                value=txn_amt,
                entity_key=f"AMOUNT:{txn_amt:.2f}",
                truth_id=None,
                aliases=[],
                role=None
            )
            sb_fin.text(t_txn["mid2"])
            ent_to_acc = sb_fin.entity(
                surface=to_acc_surface,
                ent_type="ACCOUNT",
                value=to_acct_num,
                entity_key=to_acct_num,
                truth_id=None,
                aliases=[],
                role=None
            )
            sb_fin.text(t_txn["after"]).text(" ")

            rel_transfer = {
                "source_ref": ent_from_acc,
                "target_ref": ent_to_acc,
                "relation": "TRANSFERRED_FUNDS",
                "amount": txn_amt,
                "txn_id": matching_txn_id
            }

        # Controller part
        force_h_ctrl = (is_test and not used_held_out)
        t_ctrl = pick_template("CONTROLS_ACCOUNT", lang, is_test, force_h_ctrl, rng)
        if t_ctrl["held_out"]:
            used_held_out = True
        builder.record_template(t_ctrl["id"])

        sb_fin.text(t_ctrl["before"])
        ent_ctrl_acc = sb_fin.entity(
            surface=to_acc_surface,
            ent_type="ACCOUNT",
            value=to_acct_num,
            entity_key=to_acct_num,
            truth_id=None,
            aliases=[],
            role=None
        )
        sb_fin.text(t_ctrl["mid"])
        ent_ctrl = sb_fin.entity(
            surface=ctrl_name,
            ent_type="PERSON",
            value=controller_person["name"],
            entity_key=controller_person["person_id"],
            truth_id=controller_person["person_id"],
            aliases=ctrl_aliases,
            role="SUSPECT"
        )
        sb_fin.text(t_ctrl["after"])

        ordered_sentences.append((sb_fin, [
            rel_transfer,
            {"source_ref": ent_ctrl, "target_ref": ent_ctrl_acc, "relation": "CONTROLS_ACCOUNT"}
        ]))

    # Decoy Cash-Recovered Amount (Labelled AMOUNT entity, but NO relation!)
    if fir_type in ("FULL", "DEVICE_ONLY", "MULTI_SUSPECT"):
        cash_style_idx = (idx + 1) % 4
        if cash_style_idx == 3:
            cash_val = float(rng.choice([150000.0, 200000.0, 250000.0, 500000.0]))
        else:
            cash_val = float(rng.choice([15000.0, 18500.0, 22000.0, 25000.0]))
        cash_surf = format_amount_style(cash_val, cash_style_idx, lang=lang)
        if spec.get("phone_format") == "devanagari" and lang == "hindi":
            cash_surf = to_devanagari_digits(cash_surf)

        sb_cash = SentenceBuilder()
        if lang == "hinglish":
            sb_cash.text("Search memo ke dauran suspect ke bag se cash rashi ")
            sb_cash.entity(
                surface=cash_surf,
                ent_type="AMOUNT",
                value=cash_val,
                entity_key=f"AMOUNT:{cash_val:.2f}",
                truth_id=None,
                aliases=[],
                role=None
            )
            sb_cash.text(" alag se recover hui jo hawala proceeds ka hissa batayi gayi.")
        elif lang == "hindi":
            sb_cash.text("तलाशी फर्द के अनुसार अभियुक्त के बैग से नकद राशि ")
            sb_cash.entity(
                surface=cash_surf,
                ent_type="AMOUNT",
                value=cash_val,
                entity_key=f"AMOUNT:{cash_val:.2f}",
                truth_id=None,
                aliases=[],
                role=None
            )
            sb_cash.text(" अलग से बरामद की गई जिसका कोई संतोषजनक हिसाब नहीं मिला।")
        else:
            sb_cash.text("During physical search, an additional cash sum of ")
            sb_cash.entity(
                surface=cash_surf,
                ent_type="AMOUNT",
                value=cash_val,
                entity_key=f"AMOUNT:{cash_val:.2f}",
                truth_id=None,
                aliases=[],
                role=None
            )
            sb_cash.text(" was recovered from the vehicle glove box.")
        ordered_sentences.append((sb_cash, None))

    # Neutral Role: Officer / Complainant / Witness (PERSON entity, no relations)
    officer_name = spec["officer_name"]
    officer_val = spec["officer_val"]
    officer_role = spec.get("officer_role", "OFFICER")
    if lang == "hindi":
        officer_name = NAME_HINDI_MAP.get(officer_name, officer_name)
        officer_val = NAME_HINDI_MAP.get(officer_val, officer_val)

    sb_neutral = SentenceBuilder()
    if lang == "hinglish":
        title_prefix = "Duty Officer " if officer_role == "OFFICER" else ("Complainant Shri " if officer_role == "COMPLAINANT" else "Public Witness ")
        sb_neutral.text(f"{title_prefix}")
        sb_neutral.entity(
            surface=officer_name,
            ent_type="PERSON",
            value=spec["officer_name"],
            entity_key=f"{officer_role}:{spec['officer_name']}",
            truth_id=None,
            aliases=[],
            role=officer_role
        )
        sb_neutral.text(" ne recovery proceedings ko endorse karke formal statment record karwaya.")
    elif lang == "hindi":
        title_prefix = "जांच अधिकारी " if officer_role == "OFFICER" else ("शिकायतकर्ता श्री " if officer_role == "COMPLAINANT" else "स्वतंत्र गवाह ")
        sb_neutral.text(f"{title_prefix}")
        sb_neutral.entity(
            surface=officer_name,
            ent_type="PERSON",
            value=spec["officer_name"],
            entity_key=f"{officer_role}:{spec['officer_name']}",
            truth_id=None,
            aliases=[],
            role=officer_role
        )
        sb_neutral.text(" ने जब्ती कार्यवाही का अवलोकन कर अपने हस्ताक्षर किए।")
    else:
        title_prefix = "Investigating Officer " if officer_role == "OFFICER" else ("Complainant Shri " if officer_role == "COMPLAINANT" else "Witness ")
        sb_neutral.text(f"{title_prefix}")
        sb_neutral.entity(
            surface=officer_name,
            ent_type="PERSON",
            value=spec["officer_name"],
            entity_key=f"{officer_role}:{spec['officer_name']}",
            truth_id=None,
            aliases=[],
            role=officer_role
        )
        sb_neutral.text(" attested the contemporaneous seizure inventory at the scene.")
    ordered_sentences.append((sb_neutral, None))

    if fir_type == "ALIAS_ONLY":
        force_h_al = is_test
        t_al = pick_template("ALIAS_RECORD", lang, is_test, force_h_al, rng)
        if t_al["held_out"]:
            used_held_out = True
        builder.record_template(t_al["id"])
        sb_al = SentenceBuilder()
        sb_al.text(t_al["text"])
        ordered_sentences.append((sb_al, None))

    # Procedural closing sentence (No entities)
    sb_fill1 = SentenceBuilder()
    closing_text = spec.get("closing_sentence") or BOILERPLATE_CLOSINGS[lang][spec.get("closing_idx", idx % 5)]
    sb_fill1.text(closing_text)
    ordered_sentences.append((sb_fill1, None))

    # Sentence shuffle: Keep preamble and suspect first, then shuffle middle procedural sentences
    if len(ordered_sentences) > 4:
        pre = ordered_sentences[:2]
        mid = ordered_sentences[2:-1]
        post = ordered_sentences[-1:]
        rng.shuffle(mid)
        final_sentences = pre + mid + post
    else:
        final_sentences = ordered_sentences

    for sb, rels in final_sentences:
        builder.add_sentence(sb, rels)

    fir_text, answer_key = builder.build()
    return fir_text, answer_key


def generate_all_firs_v2(
    case_dir: str = "data/synthetic/out/case_demo_v2",
    seed: int = 42,
    count: int = 100,
    out_dir: str = "data/synthetic/out/firs_v5"
) -> List[Dict[str, Any]]:
    """Generates all 100 FIRs across train (60), dev (20), and test (20) splits with index.json."""
    rng = random.Random(seed)
    case_path = Path(case_dir)
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    case_data = load_case_data(case_path)
    shared_imei = case_data["truth"]["decoys"]["shared_handset_imei"]["imei"]

    neutrals = [
        {"name": "Arvind Swaminathan", "role": "OFFICER"},
        {"name": "Rajesh Kumar", "role": "OFFICER"},
        {"name": "Vikram Rathore", "role": "OFFICER"},
        {"name": "Amit Tomar", "role": "OFFICER"},
        {"name": "Kuldeep Yadav", "role": "OFFICER"},
        {"name": "Ram Avatar", "role": "COMPLAINANT"},
        {"name": "Suresh Bansal", "role": "COMPLAINANT"},
        {"name": "Pawan Verma", "role": "COMPLAINANT"},
        {"name": "Dinesh Joshi", "role": "WITNESS"},
        {"name": "Mohan Lal", "role": "WITNESS"},
        {"name": "Kishore Sen", "role": "WITNESS"},
        {"name": "Rameshwar Dayal", "role": "WITNESS"},
    ]

    all_people = case_data["truth"]["people"]
    suspect_ids_all = [p["person_id"] for p in all_people if p.get("role") != "DECOY_CIVILIAN"]
    suspects_with_outgoing = [pid for pid in suspect_ids_all if pid in case_data["person_outgoing_txns"]]

    fir_types_train = ["FULL", "CALLS_ONLY", "MONEY_ONLY", "DEVICE_ONLY", "MULTI_SUSPECT", "ALIAS_ONLY"]
    fir_types_dev = [
        "FULL", "MULTI_SUSPECT", "CALLS_ONLY", "MONEY_ONLY", "DEVICE_ONLY", "ALIAS_ONLY",
        "FULL", "MULTI_SUSPECT", "CALLS_ONLY", "MONEY_ONLY", "DEVICE_ONLY", "ALIAS_ONLY",
        "FULL", "MULTI_SUSPECT", "CALLS_ONLY", "MONEY_ONLY", "DEVICE_ONLY", "ALIAS_ONLY",
        "MULTI_SUSPECT", "ALIAS_ONLY"
    ]
    fir_types_test = [
        "FULL", "MULTI_SUSPECT", "CALLS_ONLY", "MONEY_ONLY", "DEVICE_ONLY", "ALIAS_ONLY",
        "FULL", "MULTI_SUSPECT", "CALLS_ONLY", "MONEY_ONLY", "DEVICE_ONLY", "ALIAS_ONLY",
        "FULL", "MULTI_SUSPECT", "CALLS_ONLY", "MONEY_ONLY", "DEVICE_ONLY", "ALIAS_ONLY",
        "MULTI_SUSPECT", "ALIAS_ONLY"
    ]

    transfer_counter = {"train": 0, "dev": 0, "test": 0}
    lang_counts = {"hinglish": 0, "hindi": 0, "english": 0}

    specs: List[Dict[str, Any]] = []

    for i in range(count):
        idx = i + 1
        # Splits: 60 train (1-60), 20 dev (61-80), 20 test (81-100)
        if idx <= 60:
            split = "train"
        elif idx <= 80:
            split = "dev"
        else:
            split = "test"

        # Languages: overall 66 Hinglish, 17 Hindi, 17 English
        # Train: 40 Hinglish, 10 Hindi, 10 English
        # Dev: 13 Hinglish, 4 Hindi, 3 English
        # Test: 13 Hinglish, 3 Hindi, 4 English
        if split == "train":
            if i < 40:
                lang = "hinglish"
            elif i < 50:
                lang = "hindi"
            else:
                lang = "english"
            fir_type = fir_types_train[i % len(fir_types_train)]
        elif split == "dev":
            dev_idx = i - 60
            if dev_idx < 13:
                lang = "hinglish"
            elif dev_idx < 17:
                lang = "hindi"
            else:
                lang = "english"
            fir_type = fir_types_dev[dev_idx]
        else:
            test_idx = i - 80
            if test_idx < 13:
                lang = "hinglish"
            elif test_idx < 16:
                lang = "hindi"
            else:
                lang = "english"
            fir_type = fir_types_test[test_idx]

        # Lookalikes & Shared handset special cases
        if idx in (1, 15, 25, 42, 52, 65, 85):
            fir_type = "MULTI_SUSPECT"
            suspect_ids = ["PER_A_OP_01", "PER_B_OP_01"]
            aliases = ["Bicky", "Viku", "Kallu"]
            override_imei = None
        elif idx in (5, 45, 55, 68, 88):
            fir_type = "MULTI_SUSPECT"
            suspect_ids = ["PER_A_OP_02", "PER_A_OP_03"]
            aliases = None
            override_imei = shared_imei
        else:
            aliases = None
            override_imei = None
            suspect_ids = None

        # Transfer kind assignment for financial FIRs
        if fir_type in ("FULL", "MONEY_ONLY", "MULTI_SUSPECT"):
            t_cnt = transfer_counter[split]
            transfer_kind = "PERSON_TO_ACCOUNT" if (t_cnt % 2 == 0) else "ACCOUNT_TO_ACCOUNT"
            transfer_counter[split] += 1
            if suspect_ids is None:
                if transfer_kind == "PERSON_TO_ACCOUNT":
                    base_pid = suspects_with_outgoing[(i * 3 + 2) % len(suspects_with_outgoing)]
                else:
                    base_pid = suspect_ids_all[(i * 3 + 2) % len(suspect_ids_all)]
                if fir_type == "MULTI_SUSPECT":
                    second_pid = suspect_ids_all[(i * 3 + 4) % len(suspect_ids_all)]
                    suspect_ids = [base_pid, second_pid]
                else:
                    suspect_ids = [base_pid]
        else:
            transfer_kind = None
            if suspect_ids is None:
                base_pid = suspect_ids_all[(i * 3 + 2) % len(suspect_ids_all)]
                if fir_type == "MULTI_SUSPECT":
                    second_pid = suspect_ids_all[(i * 3 + 4) % len(suspect_ids_all)]
                    suspect_ids = [base_pid, second_pid]
                else:
                    suspect_ids = [base_pid]

        # Opening and closing boilerplate indexing
        opening_idx = lang_counts[lang] % 5
        closing_idx = lang_counts[lang] % 5
        lang_counts[lang] += 1

        # Phone format variations in >= 3 FIRs
        if idx % 7 == 3:
            phone_fmt = "space"
        elif idx % 7 == 5:
            phone_fmt = "plus91"
        elif idx % 7 == 6 and lang == "hindi":
            phone_fmt = "devanagari"
        else:
            phone_fmt = "plain"

        # Neutral officer / complainant / witness
        neutral_pick = neutrals[i % len(neutrals)]

        spec = {
            "split": split,
            "fir_type": fir_type,
            "language": lang,
            "suspect_ids": suspect_ids,
            "aliases": aliases,
            "override_imei": override_imei,
            "transfer_kind": transfer_kind,
            "opening_idx": opening_idx,
            "closing_idx": closing_idx,
            "ps_name": f"Sector-{((i * 7) % 50) + 1} Central",
            "address": f"Block-{chr(65 + (i % 6))}, Lane-{((i * 3) % 15) + 1}",
            "phone_format": phone_fmt,
            "contact_idx": i % 5,
            "officer_name": neutral_pick["name"],
            "officer_val": neutral_pick["name"],
            "officer_role": neutral_pick["role"],
        }
        specs.append(spec)

    index_records = []

    for idx, spec in enumerate(specs, 1):
        fir_text, answer_key = generate_fir_v2(idx, spec, case_data, rng)
        doc_id = f"FIR_{idx:02d}"

        # Write .txt
        txt_path = out_path / f"{doc_id}.txt"
        with open(txt_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(fir_text)

        # Write .json
        json_path = out_path / f"{doc_id}.json"
        with open(json_path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(answer_key, f, indent=2, ensure_ascii=False)

        sentences = [s.strip() for s in re.split(r"[.!?।](?:\s+|$)", fir_text) if s.strip()]

        index_records.append({
            "doc_id": doc_id,
            "split": spec["split"],
            "fir_type": spec["fir_type"],
            "language": spec["language"],
            "txt_file": f"{doc_id}.txt",
            "json_file": f"{doc_id}.json",
            "char_length": len(fir_text),
            "sentence_count": len(sentences),
            "entities_count": len(answer_key["entities"]),
            "relationships_count": len(answer_key["relationships"]),
            "suspect_ids": spec["suspect_ids"],
            "template_ids": answer_key["template_ids"],
        })

    # Write index.json
    index_path = out_path / "index.json"
    with open(index_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(index_records, f, indent=2, ensure_ascii=False)

    return index_records


def main():
    parser = argparse.ArgumentParser(description="Advanced seeded FIR text generator with answer keys")
    parser.add_argument("--case-dir", type=str, default="data/synthetic/out/case_demo_v2", help="Input case directory")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    parser.add_argument("--count", type=int, default=100, help="Number of FIRs to generate")
    parser.add_argument("--out", type=str, default="data/synthetic/out/firs_v5", help="Output directory")
    args = parser.parse_args()

    records = generate_all_firs_v2(
        case_dir=args.case_dir,
        seed=args.seed,
        count=args.count,
        out_dir=args.out
    )
    print(f"Generated {len(records)} FIRs in '{args.out}'.")


if __name__ == "__main__":
    main()
