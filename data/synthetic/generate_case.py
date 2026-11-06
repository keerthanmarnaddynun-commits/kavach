"""
data/synthetic/generate_case.py
Seeded synthetic case generator for criminal network intelligence.
Generates fictional Indian crime ring datasets (truth.json, cdr.csv, bank.csv)
using only Python 3.10+ standard libraries (random, csv, json, datetime).
"""

import argparse
import csv
import datetime
import json
import math
import os
import random
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

# Structuring threshold for Anti-Money Laundering (AML) monitoring in India
STRUCTURING_THRESHOLD = 50000

# Base reference date for 30-day simulation
BASE_DATE = datetime.datetime(2026, 1, 1, 0, 0, 0)
INCIDENT_DAY = 25  # Day of the key syndicate incident

# Fixed Delhi NCR Cell Towers
DELHI_TOWERS = [
    {"tower_id": "TWR_DEL_01", "name": "Connaught Place", "lat": 28.6315, "lon": 77.2167},
    {"tower_id": "TWR_DEL_02", "name": "Chandni Chowk", "lat": 28.6506, "lon": 77.2303},
    {"tower_id": "TWR_DEL_03", "name": "Karol Bagh", "lat": 28.6517, "lon": 77.1906},
    {"tower_id": "TWR_DEL_04", "name": "Lajpat Nagar", "lat": 28.5700, "lon": 77.2373},
    {"tower_id": "TWR_DEL_05", "name": "Rohini Sector 10", "lat": 28.7166, "lon": 77.1166},
    {"tower_id": "TWR_DEL_06", "name": "Dwarka Sector 12", "lat": 28.5921, "lon": 77.0460},
    {"tower_id": "TWR_DEL_07", "name": "Noida Sector 62", "lat": 28.6280, "lon": 77.3649},
    {"tower_id": "TWR_DEL_08", "name": "Gurugram Cyber Hub", "lat": 28.4950, "lon": 77.0895},
    {"tower_id": "TWR_DEL_09", "name": "Saket District Centre", "lat": 28.5244, "lon": 77.2188},
    {"tower_id": "TWR_DEL_10", "name": "Shahdara East", "lat": 28.6739, "lon": 77.2917},
]

BANK_IFSC_MAP = {
    "SBI": "SBIN00",
    "HDFC": "HDFC00",
    "ICICI": "ICIC00",
    "PNB": "PUNB00",
}


def luhn_checksum(digits_str: str) -> bool:
    """Verifies that a numeric string satisfies the standard Luhn algorithm."""
    total = 0
    for i, ch in enumerate(reversed(digits_str)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def generate_luhn_imei(rng: random.Random) -> str:
    """Generates a 15-digit IMEI with a valid Luhn check digit."""
    # First 14 digits
    prefix_digits = [rng.randint(1, 9) if i == 0 else rng.randint(0, 9) for i in range(14)]
    total = 0
    for j, d in enumerate(reversed(prefix_digits)):
        val = d
        if j % 2 == 0:  # Odd position from right in 15-digit string
            val *= 2
            if val > 9:
                val -= 9
        total += val
    check_digit = (10 - (total % 10)) % 10
    imei = "".join(str(d) for d in prefix_digits) + str(check_digit)
    return imei


def generate_phone(rng: random.Random, used_phones: Set[str]) -> str:
    """Generates a 10-digit Indian phone number starting with 6, 7, 8, or 9."""
    while True:
        first = rng.choice(["6", "7", "8", "9"])
        rest = "".join(str(rng.randint(0, 9)) for _ in range(9))
        phone = first + rest
        if phone not in used_phones:
            used_phones.add(phone)
            return phone


def generate_imsi(rng: random.Random) -> str:
    """Generates a 15-digit Indian IMSI."""
    mcc_mnc = rng.choice(["40445", "40420", "40585", "40570"])
    rest = "".join(str(rng.randint(0, 9)) for _ in range(10))
    return mcc_mnc + rest


def generate_bank_account(rng: random.Random, used_accounts: Set[str], bank: str = None) -> Tuple[str, str, str]:
    """Generates a 9-18 digit bank account, bank name, and matching IFSC."""
    if not bank:
        bank = rng.choice(["SBI", "HDFC", "ICICI", "PNB"])
    while True:
        length = rng.randint(11, 16)
        acct = "".join(str(rng.randint(1, 9) if i == 0 else rng.randint(0, 9)) for i in range(length))
        if acct not in used_accounts:
            used_accounts.add(acct)
            ifsc = BANK_IFSC_MAP[bank] + f"{rng.randint(1000, 9999)}"
            return acct, bank, ifsc


def build_crime_ring_entities(rng: random.Random) -> Dict[str, Any]:
    """
    Builds the complete entities dictionary (people, phones, IMEIs, accounts,
    mules, burners, and decoys) following all specifications.
    """
    used_phones: Set[str] = set()
    used_accounts: Set[str] = set()
    all_imeis: Set[str] = set()

    # Pre-generate shared IMEI for the two operatives (Decoy 4)
    shared_handset_imei = generate_luhn_imei(rng)
    all_imeis.add(shared_handset_imei)

    # 1. Gang A Definition (1 KP, 2 LT, 6 OP)
    gang_a_specs = [
        {"id": "PER_A_KP_01", "name": "Rajendra Singh", "father": "Maheshwar Singh", "aliases": ["Raju Bhai"], "role": "KINGPIN"},
        {"id": "PER_A_LT_01", "name": "Devendra Yadav", "father": "Ramakant Yadav", "aliases": ["Chhota Raju"], "role": "LIEUTENANT"},
        {"id": "PER_A_LT_02", "name": "Sanjay Mehra", "father": "Prem Mehra", "aliases": ["Sanju"], "role": "LIEUTENANT"},
        {"id": "PER_A_OP_01", "name": "Vikas Sharma", "father": "Harish Sharma", "aliases": ["Bicky", "Viku", "Kallu"], "role": "OPERATIVE"},  # Decoy: 3 aliases & similar name to Bikas
        {"id": "PER_A_OP_02", "name": "Anand Verma", "father": "Shyam Verma", "aliases": ["Andy"], "role": "OPERATIVE"},                        # Decoy: Shared handset
        {"id": "PER_A_OP_03", "name": "Pankaj Tiwari", "father": "Madan Tiwari", "aliases": ["Pandit"], "role": "OPERATIVE"},                   # Decoy: Shared handset
        {"id": "PER_A_OP_04", "name": "Manoj Rawat", "father": "Kishori Rawat", "aliases": ["Munna"], "role": "OPERATIVE"},
        {"id": "PER_A_OP_05", "name": "Deepak Chauhan", "father": "Sardar Chauhan", "aliases": ["Deepu"], "role": "OPERATIVE"},                 # Holds Mule A1
        {"id": "PER_A_OP_06", "name": "Sunil Kumar", "father": "Bhagwan Kumar", "aliases": ["Sunny"], "role": "OPERATIVE"},                     # Holds Mule A2
    ]

    # 2. Gang B Definition (1 KP, 2 LT, 6 OP)
    gang_b_specs = [
        {"id": "PER_B_KP_01", "name": "Mukhtar Ansari", "father": "Iqbal Ansari", "aliases": ["Bade Miyan"], "role": "KINGPIN"},
        {"id": "PER_B_LT_01", "name": "Farooq Ahmed", "father": "Zahid Ahmed", "aliases": ["Tiger"], "role": "LIEUTENANT"},
        {"id": "PER_B_LT_02", "name": "Rashid Khan", "father": "Asif Khan", "aliases": ["Shooter"], "role": "LIEUTENANT"},
        {"id": "PER_B_OP_01", "name": "Bikas Sharma", "father": "Girish Sharma", "aliases": ["Biku"], "role": "OPERATIVE"},                     # Decoy: Similar name to Vikas Sharma
        {"id": "PER_B_OP_02", "name": "Imran Sheikh", "father": "Mustaq Sheikh", "aliases": ["Kabira"], "role": "OPERATIVE"},
        {"id": "PER_B_OP_03", "name": "Nadeem Qureshi", "father": "Yusuf Qureshi", "aliases": ["Don"], "role": "OPERATIVE"},
        {"id": "PER_B_OP_04", "name": "Wasim Akram", "father": "Shabir Akram", "aliases": ["Vicky"], "role": "OPERATIVE"},
        {"id": "PER_B_OP_05", "name": "Salman Mirza", "father": "Feroz Mirza", "aliases": ["Sallu"], "role": "OPERATIVE"},                     # Holds Mule B1
        {"id": "PER_B_OP_06", "name": "Aslam Parvez", "father": "Latif Parvez", "aliases": ["Chacha"], "role": "OPERATIVE"},                   # Holds Mule B2 (Dormant 15+ days)
    ]

    # 3. Two Bridge Couriers (The ONLY link between Gang A and Gang B)
    courier_specs = [
        {"id": "PER_CR_01", "name": "Ramesh Chand", "father": "Kishan Chand", "aliases": ["Postman"], "role": "BRIDGE_COURIER", "gang": "COURIER"},
        {"id": "PER_CR_02", "name": "Suresh Pal", "father": "Mohan Pal", "aliases": ["Hawai"], "role": "BRIDGE_COURIER", "gang": "COURIER"},
    ]

    # 4. Decoy Pizza Shop (Civilian High-Degree Number, called only by Gang A)
    decoy_specs = [
        {"id": "DEC_PIZZA_01", "name": "Harish Chawla (Royal Pizza)", "father": "Kailash Chawla", "aliases": ["Pizza Shop"], "role": "DECOY_CIVILIAN", "gang": "CIVILIAN"},
    ]

    people: List[Dict[str, Any]] = []
    people_map: Dict[str, Dict[str, Any]] = {}
    phones_list: List[Dict[str, Any]] = []
    accounts_list: List[Dict[str, Any]] = []

    def process_person_specs(specs: List[Dict[str, Any]], gang_name: str):
        for s in specs:
            pid = s["id"]
            gang = s.get("gang", gang_name)
            p_phones = []
            
            # 1-2 phones per person
            # Kingpins, Couriers, and Pizza shop have 1 phone; some lieutenants/operatives have 2
            phone_count = 2 if (s["role"] in ["LIEUTENANT", "OPERATIVE"] and rng.random() < 0.4) else 1
            for p_idx in range(phone_count):
                ph = generate_phone(rng, used_phones)
                # Assign IMEI
                if pid in ["PER_A_OP_02", "PER_A_OP_03"] and p_idx == 0:
                    imei = shared_handset_imei
                else:
                    imei = generate_luhn_imei(rng)
                    all_imeis.add(imei)

                imsi = generate_imsi(rng)
                p_phones.append({"phone": ph, "imei": imei, "imsi": imsi})
                phones_list.append({
                    "phone": ph,
                    "person_id": pid,
                    "imei": imei,
                    "imsi": imsi,
                    "is_burner": False,
                    "is_decoy": (s["role"] == "DECOY_CIVILIAN"),
                })

            # 0-2 bank accounts per person
            # Kingpins each have 1 primary controlled account; mules hold 1 mule account
            # Pizza shop is an innocent decoy and holds 0 accounts
            if s["role"] == "DECOY_CIVILIAN":
                _ = rng.random()  # Keep RNG stream in sync
                acct_count = 0
            elif s["role"] in ["KINGPIN", "LIEUTENANT"]:
                acct_count = 1
            else:
                acct_count = 1 if rng.random() < 0.6 else 0
            p_accounts = []
            for _ in range(acct_count):
                acct_num, bank, ifsc = generate_bank_account(rng, used_accounts)
                p_accounts.append({"account_number": acct_num, "bank": bank, "ifsc": ifsc})
                accounts_list.append({
                    "account_number": acct_num,
                    "bank": bank,
                    "ifsc": ifsc,
                    "person_id": pid,
                    "is_mule": False,
                    "is_kingpin_controlled": (s["role"] == "KINGPIN"),
                })

            person_obj = {
                "person_id": pid,
                "name": s["name"],
                "aliases": s["aliases"],
                "father_name": s["father"],
                "role": s["role"],
                "gang": gang,
                "phones": p_phones,
                "accounts": p_accounts,
                "is_decoy": (s["role"] == "DECOY_CIVILIAN"),
            }
            people.append(person_obj)
            people_map[pid] = person_obj

    process_person_specs(gang_a_specs, "GANG_A")
    process_person_specs(gang_b_specs, "GANG_B")
    process_person_specs(courier_specs, "COURIER")
    process_person_specs(decoy_specs, "CIVILIAN")

    # Designate 4 Mule Accounts (Held by OP_A_05, OP_A_06, OP_B_05, OP_B_06)
    mule_owners = ["PER_A_OP_05", "PER_A_OP_06", "PER_B_OP_05", "PER_B_OP_06"]
    mule_accounts = []
    for m_owner_id in mule_owners:
        acct_num, bank, ifsc = generate_bank_account(rng, used_accounts)
        mule_acc_obj = {
            "account_number": acct_num,
            "bank": bank,
            "ifsc": ifsc,
            "person_id": m_owner_id,
            "is_mule": True,
            "is_kingpin_controlled": False,
        }
        people_map[m_owner_id]["accounts"].append({"account_number": acct_num, "bank": bank, "ifsc": ifsc, "is_mule": True})
        accounts_list.append(mule_acc_obj)
        mule_accounts.append(acct_num)

    # Kingpin primary accounts for mule onward funneling
    kp_a_acct = people_map["PER_A_KP_01"]["accounts"][0]["account_number"]
    kp_b_acct = people_map["PER_B_KP_01"]["accounts"][0]["account_number"]

    # 4 Burner Phones (active 3-8 days, new IMEI, activated 1-4 days before incident on day 25)
    # Burner 1: Gang A Operative (activated day 21, life 5 days -> 21..25)
    # Burner 2: Gang A Operative (activated day 23, life 4 days -> 23..26)
    # Burner 3: Gang B Operative (activated day 22, life 7 days -> 22..28)
    # Burner 4: Gang B Operative (activated day 24, life 3 days -> 24..26)
    burner_configs = [
        {"owner": "PER_A_OP_01", "act_day": 21, "lifespan": 5, "partners": ["PER_A_OP_02", "PER_A_OP_04"]},
        {"owner": "PER_A_OP_03", "act_day": 23, "lifespan": 4, "partners": ["PER_A_LT_01"]},
        {"owner": "PER_B_OP_01", "act_day": 22, "lifespan": 7, "partners": ["PER_B_OP_02", "PER_B_OP_03"]},
        {"owner": "PER_B_OP_04", "act_day": 24, "lifespan": 3, "partners": ["PER_B_LT_01"]},
    ]

    burner_phones = []
    burner_phone_records = []
    for idx, b_cfg in enumerate(burner_configs, 1):
        b_ph = generate_phone(rng, used_phones)
        b_imei = generate_luhn_imei(rng)
        b_imsi = generate_imsi(rng)
        all_imeis.add(b_imei)
        burner_phones.append(b_ph)
        
        b_rec = {
            "burner_id": f"BURNER_{idx:02d}",
            "phone": b_ph,
            "imei": b_imei,
            "imsi": b_imsi,
            "assigned_to": b_cfg["owner"],
            "activation_day": b_cfg["act_day"],
            "lifespan_days": b_cfg["lifespan"],
            "partners": b_cfg["partners"],
        }
        burner_phone_records.append(b_rec)
        phones_list.append({
            "phone": b_ph,
            "person_id": b_cfg["owner"],
            "imei": b_imei,
            "imsi": b_imsi,
            "is_burner": True,
            "is_decoy": False,
        })

    # 20 Outside Customer Phones for Decoy Pizza Shop (Civilian, no accounts, valid 10-digit)
    decoy_customers = []
    customer_hardware = {}
    for _ in range(20):
        c_ph = generate_phone(rng, used_phones)
        c_imei = generate_luhn_imei(rng)
        c_imsi = generate_imsi(rng)
        all_imeis.add(c_imei)
        decoy_customers.append(c_ph)
        customer_hardware[c_ph] = (c_imei, c_imsi)
        phones_list.append({
            "phone": c_ph,
            "person_id": None,
            "imei": c_imei,
            "imsi": c_imsi,
            "is_burner": False,
            "is_decoy": True,
        })

    # Decoy metadata
    decoys_meta = {
        "pizza_shop_number": people_map["DEC_PIZZA_01"]["phones"][0]["phone"],
        "is_decoy": True,
        "decoy_customers": decoy_customers,
        "similar_names": [
            {"person_id": "PER_A_OP_01", "name": "Vikas Sharma", "gang": "GANG_A"},
            {"person_id": "PER_B_OP_01", "name": "Bikas Sharma", "gang": "GANG_B"},
        ],
        "person_with_3_aliases": {
            "person_id": "PER_A_OP_01",
            "name": "Vikas Sharma",
            "aliases": ["Bicky", "Viku", "Kallu"],
        },
        "shared_handset_imei": {
            "imei": shared_handset_imei,
            "shared_by": ["PER_A_OP_02", "PER_A_OP_03"],
        },
    }

    # Summary structures for truth.json
    all_roles = sorted(list({p["role"] for p in people}))
    aliases_dict = {p["person_id"]: p["aliases"] for p in people}

    truth = {
        "incident_day": INCIDENT_DAY,
        "structuring_threshold": STRUCTURING_THRESHOLD,
        "kingpin_ids": ["PER_A_KP_01", "PER_B_KP_01"],
        "bridge_courier_ids": ["PER_CR_01", "PER_CR_02"],
        "mule_accounts": mule_accounts,
        "burner_phones": burner_phones,
        "decoy_customers": decoy_customers,
        "is_decoy": True,
        "decoys": decoys_meta,
        "people": people,
        "roles": all_roles,
        "aliases": aliases_dict,
        "phones": phones_list,
        "imeis": sorted(list(all_imeis)),
        "accounts": accounts_list,
    }

    return {
        "truth": truth,
        "people_map": people_map,
        "burner_phone_records": burner_phone_records,
        "kp_a_acct": kp_a_acct,
        "kp_b_acct": kp_b_acct,
        "mule_accounts": mule_accounts,
        "pizza_phone": decoys_meta["pizza_shop_number"],
        "decoy_customers": decoy_customers,
        "customer_hardware": customer_hardware,
        "shared_handset_imei": shared_handset_imei,
    }


def generate_cdr_records(
    rng: random.Random,
    entities_data: Dict[str, Any],
    total_days: int = 30
) -> List[Dict[str, Any]]:
    """
    Generates ~8000 CDR rows strictly enforcing call network rules:
    - Kingpins call ONLY their 2 lieutenants, very rarely (raw call count NOT top).
    - Couriers are the ONLY bridge between Gang A and Gang B (each calls 1 LT of A, 1 LT of B).
    - Burners active strictly 3-8 days, calling only 1-2 numbers.
    - Decoy Pizza Shop called heavily by Gang A, never by Gang B.
    - Removing couriers disconnects Gang A from Gang B.
    """
    people_map = entities_data["people_map"]
    burner_records = entities_data["burner_phone_records"]
    pizza_phone = entities_data["pizza_phone"]
    decoy_customers = entities_data["decoy_customers"]

    # Gather phones
    kp_a_phones = [p["phone"] for p in people_map["PER_A_KP_01"]["phones"]]
    lt_a1_phones = [p["phone"] for p in people_map["PER_A_LT_01"]["phones"]]
    lt_a2_phones = [p["phone"] for p in people_map["PER_A_LT_02"]["phones"]]
    op_a_phones = [p["phone"] for pid in ["PER_A_OP_01", "PER_A_OP_02", "PER_A_OP_03", "PER_A_OP_04", "PER_A_OP_05", "PER_A_OP_06"] for p in people_map[pid]["phones"]]

    kp_b_phones = [p["phone"] for p in people_map["PER_B_KP_01"]["phones"]]
    lt_b1_phones = [p["phone"] for p in people_map["PER_B_LT_01"]["phones"]]
    lt_b2_phones = [p["phone"] for p in people_map["PER_B_LT_02"]["phones"]]
    op_b_phones = [p["phone"] for pid in ["PER_B_OP_01", "PER_B_OP_02", "PER_B_OP_03", "PER_B_OP_04", "PER_B_OP_05", "PER_B_OP_06"] for p in people_map[pid]["phones"]]

    cr1_phones = [p["phone"] for p in people_map["PER_CR_01"]["phones"]]
    cr2_phones = [p["phone"] for p in people_map["PER_CR_02"]["phones"]]

    # Phone to (IMEI, IMSI) mapping
    phone_hardware = {}
    for p in entities_data["truth"]["phones"]:
        phone_hardware[p["phone"]] = (p["imei"], p["imsi"])

    cdr_rows = []

    def make_cdr(a_num: str, b_num: str, dt: datetime.datetime):
        imei, imsi = phone_hardware[a_num]
        call_type = "VOICE" if rng.random() < 0.85 else "SMS"
        dur = rng.randint(20, 800) if call_type == "VOICE" else 0
        tower = rng.choice(DELHI_TOWERS)
        cdr_rows.append({
            "a_party": a_num,
            "b_party": b_num,
            "imei_a": imei,
            "imsi_a": imsi,
            "start_time": dt.isoformat(),
            "duration_sec": dur,
            "call_type": call_type,
            "tower_id": tower["tower_id"],
            "lat": f"{tower['lat'] + rng.uniform(-0.005, 0.005):.5f}",
            "lon": f"{tower['lon'] + rng.uniform(-0.005, 0.005):.5f}",
            "_sort_dt": dt,
        })

    # 1. Kingpin A calls (Rare! ONLY to Lieutenants A1 and A2)
    # Total ~14 calls across the entire 30 days
    kp_a_call_days = rng.sample(range(1, total_days + 1), k=min(12, total_days))
    for d in kp_a_call_days:
        hour = rng.randint(21, 23)
        minute = rng.randint(0, 59)
        dt = BASE_DATE + datetime.timedelta(days=d - 1, hours=hour, minutes=minute, seconds=rng.randint(0, 59))
        target_lt = rng.choice([lt_a1_phones[0], lt_a2_phones[0]])
        if rng.random() < 0.5:
            make_cdr(kp_a_phones[0], target_lt, dt)
        else:
            make_cdr(target_lt, kp_a_phones[0], dt)

    # 2. Kingpin B calls (Rare! ONLY to Lieutenants B1 and B2)
    # Total ~14 calls across the entire 30 days
    kp_b_call_days = rng.sample(range(1, total_days + 1), k=min(12, total_days))
    for d in kp_b_call_days:
        hour = rng.randint(20, 23)
        minute = rng.randint(0, 59)
        dt = BASE_DATE + datetime.timedelta(days=d - 1, hours=hour, minutes=minute, seconds=rng.randint(0, 59))
        target_lt = rng.choice([lt_b1_phones[0], lt_b2_phones[0]])
        if rng.random() < 0.5:
            make_cdr(kp_b_phones[0], target_lt, dt)
        else:
            make_cdr(target_lt, kp_b_phones[0], dt)

    # 3. Bridge Courier 1 (The ONLY bridge between LT_A1 and LT_B1)
    # Calls on ~20 days
    cr1_days = sorted(rng.sample(range(1, total_days + 1), k=min(22, total_days)))
    for d in cr1_days:
        dt1 = BASE_DATE + datetime.timedelta(days=d - 1, hours=rng.randint(9, 14), minutes=rng.randint(0, 59))
        dt2 = dt1 + datetime.timedelta(hours=rng.randint(1, 3), minutes=rng.randint(1, 45))
        # Courier 1 talks to LT A1
        if rng.random() < 0.5:
            make_cdr(cr1_phones[0], lt_a1_phones[0], dt1)
        else:
            make_cdr(lt_a1_phones[0], cr1_phones[0], dt1)
        # Courier 1 talks to LT B1
        if rng.random() < 0.5:
            make_cdr(cr1_phones[0], lt_b1_phones[0], dt2)
        else:
            make_cdr(lt_b1_phones[0], cr1_phones[0], dt2)

    # 4. Bridge Courier 2 (The ONLY bridge between LT_A2 and LT_B2)
    # Calls on ~20 days
    cr2_days = sorted(rng.sample(range(1, total_days + 1), k=min(22, total_days)))
    for d in cr2_days:
        dt1 = BASE_DATE + datetime.timedelta(days=d - 1, hours=rng.randint(10, 16), minutes=rng.randint(0, 59))
        dt2 = dt1 + datetime.timedelta(hours=rng.randint(1, 3), minutes=rng.randint(1, 45))
        # Courier 2 talks to LT A2
        if rng.random() < 0.5:
            make_cdr(cr2_phones[0], lt_a2_phones[0], dt1)
        else:
            make_cdr(lt_a2_phones[0], cr2_phones[0], dt1)
        # Courier 2 talks to LT B2
        if rng.random() < 0.5:
            make_cdr(cr2_phones[0], lt_b2_phones[0], dt2)
        else:
            make_cdr(lt_b2_phones[0], cr2_phones[0], dt2)

    # 5. Burner Phones (4 burners, active 3-8 days, calls only 1-2 numbers)
    for b_rec in burner_records:
        act_d = b_rec["activation_day"]
        span = b_rec["lifespan_days"]
        b_num = b_rec["phone"]
        
        # Get target partner phones (strictly 1-2 distinct numbers)
        partner_phones = []
        for pid in b_rec["partners"]:
            if people_map[pid]["phones"]:
                partner_phones.append(people_map[pid]["phones"][0]["phone"])
        partner_phones = partner_phones[:2]

        # Distribute calls strictly across act_d to act_d + span - 1
        for day_offset in range(span):
            cur_day = act_d + day_offset
            if cur_day > total_days:
                break
            # 6-8 calls per active day
            calls_today = rng.randint(6, 8)
            for _ in range(calls_today):
                dt = BASE_DATE + datetime.timedelta(
                    days=cur_day - 1,
                    hours=rng.randint(8, 22),
                    minutes=rng.randint(0, 59),
                    seconds=rng.randint(0, 59)
                )
                dest = rng.choice(partner_phones)
                if rng.random() < 0.7:
                    make_cdr(b_num, dest, dt)
                else:
                    make_cdr(dest, b_num, dt)

    # 6. Decoy Pizza Shop: Innocent civilian hub
    # Must have >= 20 distinct contacts: 20 outside customers + at most 3 operatives from ONE gang (Gang A)
    # Must rank in top 3 by call count, while both kingpins stay in the bottom 3
    gang_a_pizza_operatives = ["PER_A_OP_01", "PER_A_OP_02", "PER_A_OP_03"]
    gang_a_pizza_callers = [people_map[pid]["phones"][0]["phone"] for pid in gang_a_pizza_operatives]

    # 6a. 20 outside customer phones order regularly (~1200 calls total, ~60 per customer)
    for c_ph in decoy_customers:
        for d in range(1, total_days + 1):
            cust_calls_today = rng.randint(1, 3)
            for _ in range(cust_calls_today):
                dt = BASE_DATE + datetime.timedelta(
                    days=d - 1,
                    hours=rng.choice([11, 12, 13, 14, 18, 19, 20, 21, 22]),
                    minutes=rng.randint(0, 59),
                    seconds=rng.randint(0, 59)
                )
                if rng.random() < 0.7:
                    make_cdr(c_ph, pizza_phone, dt)
                else:
                    make_cdr(pizza_phone, c_ph, dt)

    # 6b. At most 3 operatives from Gang A order food (~180 calls total across 30 days)
    for d in range(1, total_days + 1):
        op_calls_today = rng.randint(5, 7)
        for _ in range(op_calls_today):
            caller = rng.choice(gang_a_pizza_callers)
            dt = BASE_DATE + datetime.timedelta(
                days=d - 1,
                hours=rng.choice([12, 13, 14, 20, 21, 22]),
                minutes=rng.randint(0, 59),
                seconds=rng.randint(0, 59)
            )
            if rng.random() < 0.75:
                make_cdr(caller, pizza_phone, dt)
            else:
                make_cdr(pizza_phone, caller, dt)

    # 7. Internal Traffic for Gang A (Lieutenants <-> Operatives <-> Operatives)
    # Scaled to maintain ~7500-8000 total CDR rows
    gang_a_pool = lt_a1_phones + lt_a2_phones + op_a_phones
    for d in range(1, total_days + 1):
        daily_a_calls = rng.randint(94, 98)
        for _ in range(daily_a_calls):
            # Lieutenants make a lot of calls
            if rng.random() < 0.6:
                caller = rng.choice(lt_a1_phones + lt_a2_phones)
                receiver = rng.choice(op_a_phones + lt_a1_phones + lt_a2_phones)
            else:
                caller = rng.choice(op_a_phones)
                receiver = rng.choice(gang_a_pool)
            
            if caller == receiver:
                # pick a different receiver
                receiver = rng.choice([x for x in gang_a_pool if x != caller])

            dt = BASE_DATE + datetime.timedelta(
                days=d - 1,
                hours=rng.randint(7, 23),
                minutes=rng.randint(0, 59),
                seconds=rng.randint(0, 59)
            )
            make_cdr(caller, receiver, dt)

    # 8. Internal Traffic for Gang B (Lieutenants <-> Operatives <-> Operatives)
    # Scaled to maintain ~7500-8000 total CDR rows
    gang_b_pool = lt_b1_phones + lt_b2_phones + op_b_phones
    for d in range(1, total_days + 1):
        daily_b_calls = rng.randint(96, 100)
        for _ in range(daily_b_calls):
            if rng.random() < 0.6:
                caller = rng.choice(lt_b1_phones + lt_b2_phones)
                receiver = rng.choice(op_b_phones + lt_b1_phones + lt_b2_phones)
            else:
                caller = rng.choice(op_b_phones)
                receiver = rng.choice(gang_b_pool)

            if caller == receiver:
                receiver = rng.choice([x for x in gang_b_pool if x != caller])

            dt = BASE_DATE + datetime.timedelta(
                days=d - 1,
                hours=rng.randint(7, 23),
                minutes=rng.randint(0, 59),
                seconds=rng.randint(0, 59)
            )
            make_cdr(caller, receiver, dt)

    # Deterministic chronological sort
    cdr_rows.sort(key=lambda r: (r["_sort_dt"], r["a_party"], r["b_party"]))
    for r in cdr_rows:
        del r["_sort_dt"]

    return cdr_rows


def generate_bank_records(
    rng: random.Random,
    entities_data: Dict[str, Any],
    total_days: int = 30
) -> List[Dict[str, Any]]:
    """
    Generates ~1500 Bank transaction rows strictly enforcing:
    - 4 Mule Accounts: small incoming deposits, some just under STRUCTURING_THRESHOLD (50000).
    - Onward transfer within hours to a kingpin-controlled account, leaving near-zero balance.
    - One mule dormant for 15+ days (Mule 4 active only Day 17-30).
    - Regular network payouts and petty cash transfers.
    """
    mule_accounts = entities_data["mule_accounts"]  # 4 mules
    kp_a_acct = entities_data["kp_a_acct"]
    kp_b_acct = entities_data["kp_b_acct"]

    # Mapping of which kingpin account receives funds from which mule
    # Mule 0 & 1 -> KP A; Mule 2 & 3 -> KP B
    mule_to_kp = {
        mule_accounts[0]: kp_a_acct,
        mule_accounts[1]: kp_a_acct,
        mule_accounts[2]: kp_b_acct,
        mule_accounts[3]: kp_b_acct,
    }

    # Non-mule accounts for general routine transactions so mule patterns remain pure
    general_accounts = [a["account_number"] for a in entities_data["truth"]["accounts"] if not a["is_mule"]]

    # Pre-generate external client accounts for deposits
    external_accounts = [f"9900{rng.randint(10000000, 99999999)}" for _ in range(50)]

    bank_rows = []
    txn_counter = 1

    def make_txn(dt: datetime.datetime, from_acc: str, to_acc: str, amt: float, mode: str, ifsc: str, narr: str):
        nonlocal txn_counter
        bank_rows.append({
            "txn_id": f"TXN{txn_counter:06d}",
            "datetime": dt.isoformat(),
            "from_acct": from_acc,
            "to_acct": to_acc,
            "amount": f"{amt:.2f}",
            "mode": mode,
            "ifsc": ifsc,
            "narration": narr,
            "_sort_dt": dt,
        })
        txn_counter += 1

    # Structured deposit amounts just under 50,000 INR
    UNDER_THRESHOLD_AMOUNTS = [48500.0, 49000.0, 49200.0, 49500.0, 47800.0, 49800.0]
    SMALL_DEPOSIT_AMOUNTS = [8000.0, 12000.0, 15000.0, 22000.0, 25000.0, 31000.0]

    # 1. Mule Account Activity
    # Mules 0, 1, 2 are active throughout (every 2-3 days)
    # Mule 3 is DORMANT for 15+ days (Day 1-16 inactive, active Day 17-30)
    for m_idx, m_acc in enumerate(mule_accounts):
        is_dormant_mule = (m_idx == 3)
        start_day = 17 if is_dormant_mule else 1

        active_days = [d for d in range(start_day, total_days + 1) if d % 2 == (m_idx % 2)]

        for d in active_days:
            # Day batch of incoming deposits
            deposit_count = rng.randint(2, 4)
            batch_total = 0.0
            last_deposit_dt = None

            for i in range(deposit_count):
                dt_dep = BASE_DATE + datetime.timedelta(
                    days=d - 1,
                    hours=rng.randint(9, 14),
                    minutes=rng.randint(0, 59),
                    seconds=rng.randint(0, 59)
                )
                last_deposit_dt = dt_dep if (last_deposit_dt is None or dt_dep > last_deposit_dt) else last_deposit_dt

                # Structuring: alternate between just under 50k and smaller deposits
                if rng.random() < 0.65:
                    amt = rng.choice(UNDER_THRESHOLD_AMOUNTS)
                else:
                    amt = rng.choice(SMALL_DEPOSIT_AMOUNTS)

                batch_total += amt
                from_client = rng.choice(external_accounts)
                mode = rng.choice(["CASH", "UPI", "IMPS"])
                narr = "Cash Deposit CDM" if mode == "CASH" else "UPI / P2P Settlement"
                make_txn(dt_dep, from_client, m_acc, amt, mode, "SBIN0004521", narr)

            # Onward transfer within hours (1 to 3 hours later) to the Kingpin
            hours_later = rng.randint(1, 3)
            minutes_later = rng.randint(5, 50)
            dt_onward = last_deposit_dt + datetime.timedelta(hours=hours_later, minutes=minutes_later)
            kp_target = mule_to_kp[m_acc]

            # Leaves near-zero balance (retains exactly 0.00 or nominal fee)
            onward_amt = batch_total  # 100% transfer leaves zero balance
            mode = "IMPS" if onward_amt <= 200000 else "NEFT"
            make_txn(dt_onward, m_acc, kp_target, onward_amt, mode, "HDFC0001020", "Immediate Onward Settlement / Hawala")

    # 2. General Syndicate & Petty Cash Transactions (~1250 transactions across 30 days)
    # ~41-43 transactions per day
    for d in range(1, total_days + 1):
        daily_txns = rng.randint(41, 44)
        for _ in range(daily_txns):
            dt = BASE_DATE + datetime.timedelta(
                days=d - 1,
                hours=rng.randint(8, 22),
                minutes=rng.randint(0, 59),
                seconds=rng.randint(0, 59)
            )
            # Mix of operative expense payouts, civilian transfers, etc.
            f_acc = rng.choice(general_accounts + external_accounts)
            t_acc = rng.choice(general_accounts + external_accounts)
            if f_acc == t_acc:
                t_acc = rng.choice([a for a in general_accounts if a != f_acc])

            amt = round(rng.uniform(500.0, 35000.0), 2)
            mode = rng.choice(["UPI", "IMPS", "NEFT"])
            narr = rng.choice(["Operational Payout", "Travel Expense", "Logistics Fuel", "Mobile Recharge Bill", "Vendor Settlement"])
            make_txn(dt, f_acc, t_acc, amt, mode, "ICIC0003040", narr)

    # Sort deterministically
    bank_rows.sort(key=lambda r: (r["_sort_dt"], r["txn_id"]))
    for r in bank_rows:
        del r["_sort_dt"]

    return bank_rows


def generate_case(seed: int = 42, days: int = 30, out_dir: str = "data/synthetic/out/case_demo") -> Dict[str, Any]:
    """
    Main orchestration routine to generate deterministic synthetic case files.
    Writes:
      - truth.json
      - cdr.csv
      - bank.csv
    Returns metadata dictionary with generated row counts and paths.
    """
    rng = random.Random(seed)
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    # 1. Build Entities & Truth Hierarchy
    entities_data = build_crime_ring_entities(rng)

    # 2. Generate CDR records (~8000 rows)
    cdr_records = generate_cdr_records(rng, entities_data, total_days=days)

    # 3. Generate Bank records (~1500 rows)
    bank_records = generate_bank_records(rng, entities_data, total_days=days)

    # 4. Write truth.json (ensuring byte-deterministic sorting & formatting)
    truth_file = out_path / "truth.json"
    with open(truth_file, "w", encoding="utf-8", newline="\n") as f:
        json.dump(entities_data["truth"], f, indent=2, ensure_ascii=False)

    # 5. Write cdr.csv
    cdr_file = out_path / "cdr.csv"
    cdr_headers = ["a_party", "b_party", "imei_a", "imsi_a", "start_time", "duration_sec", "call_type", "tower_id", "lat", "lon"]
    with open(cdr_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=cdr_headers, lineterminator="\n")
        writer.writeheader()
        writer.writerows(cdr_records)

    # 6. Write bank.csv
    bank_file = out_path / "bank.csv"
    bank_headers = ["txn_id", "datetime", "from_acct", "to_acct", "amount", "mode", "ifsc", "narration"]
    with open(bank_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=bank_headers, lineterminator="\n")
        writer.writeheader()
        writer.writerows(bank_records)

    return {
        "people_count": len(entities_data["truth"]["people"]),
        "phones_count": len(entities_data["truth"]["phones"]),
        "accounts_count": len(entities_data["truth"]["accounts"]),
        "cdr_rows": len(cdr_records),
        "bank_rows": len(bank_records),
        "out_dir": str(out_path),
    }


def main():
    parser = argparse.ArgumentParser(description="Seeded synthetic crime case generator")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    parser.add_argument("--days", type=int, default=30, help="Simulation duration in days")
    parser.add_argument("--out", type=str, default="data/synthetic/out/case_demo", help="Output directory")
    args = parser.parse_args()

    stats = generate_case(seed=args.seed, days=args.days, out_dir=args.out)
    print(f"Synthetic case generated successfully in '{args.out}':")
    print(f"  People Count   : {stats['people_count']}")
    print(f"  Phones Count   : {stats['phones_count']}")
    print(f"  Accounts Count : {stats['accounts_count']}")
    print(f"  CDR Rows       : {stats['cdr_rows']:,}")
    print(f"  Bank Rows      : {stats['bank_rows']:,}")


if __name__ == "__main__":
    main()
