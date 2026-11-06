# Crimi-Nex Evaluation Results

<!-- STEP1:BEGIN -->
## Step 1: Synthetic Case Generator Evaluation

### Results Card
- **Purpose**: Generation of synthetic criminal syndicate communication records, financial transaction ledgers, and reference ground truth metadata for benchmarking intelligence extraction pipelines.
- **Exact Command**: `python data/synthetic/generate_case.py --seed 42 --days 30 --out results/2026-11-06_step1_synthetic_r2/run1`
- **Exact Pytest Command**: `C:\Users\Kirthan\AppData\Local\Programs\Python\Python313\python.exe -m pytest -v tests/test_generate_case.py`
- **Input Files**:
  - `data/synthetic/generate_case.py` (SHA-256: `1a9df2680772d7b72a3ae0988f2b894007aeb545266864bf2bcffe6b8ad19465`)
  - `tests/test_generate_case.py` (SHA-256: `2c854c931ac99deea8a92ddb77853793310fbb7d095664f5790ea12a45997376`)
- **Output Files (Run 1)**:
  - `run1/truth.json` (SHA-256: `3d4f26976a62c4920311ef52bf320d9fa3acb204076dec5c7880d02123a8fa96`)
  - `run1/cdr.csv` (SHA-256: `6bccbd88c50b1b671eb1da0a963e9c20d001d40c68f6fb1ad9048db827a2dc80`)
  - `run1/bank.csv` (SHA-256: `77ef80ba091133793089fa6883ce6333000c0b8362fc066afc58b6a9215801e3`)
- **Key Numbers**:
  - `run1/cdr.csv`: 7469 rows (columns: `a_party`, `b_party`, `imei_a`, `imsi_a`, `start_time`, `duration_sec`, `call_type`, `tower_id`, `lat`, `lon`)
  - `run1/bank.csv`: 1482 rows (columns: `txn_id`, `datetime`, `from_acct`, `to_acct`, `amount`, `mode`, `ifsc`, `narration`)
  - `run1/truth.json`: 21 people (key: `people`), 49 phones (key: `phones`), 19 accounts (key: `accounts`), 48 IMEIs (key: `imeis`)

### Tables

#### Table 1: Dataset Volume and Entity Summary
| File / Key | Metric Type | Count | Notes |
| :--- | :--- | :--- | :--- |
| `run1/cdr.csv` | Total Communication Rows | 7469 | Excludes CSV header row |
| `run1/bank.csv` | Total Transaction Rows | 1482 | Excludes CSV header row |
| `run1/truth.json` | People Entities | 21 | Top-level array `people` |
| `run1/truth.json` | Telephone Numbers | 49 | Top-level array `phones` |
| `run1/truth.json` | Bank Accounts | 19 | Top-level array `accounts` |
| `run1/truth.json` | IMEI Identifiers | 48 | Top-level array `imeis` |

#### Table 2: Determinism Comparison Across Runs
| Output File | Run 1 SHA-256 | Run 2 SHA-256 | Bitwise Match |
| :--- | :--- | :--- | :--- |
| `truth.json` | `3d4f26976a62c492...` | `3d4f26976a62c492...` | **True** |
| `cdr.csv` | `6bccbd88c50b1b67...` | `6bccbd88c50b1b67...` | **True** |
| `bank.csv` | `77ef80ba09113379...` | `77ef80ba09113379...` | **True** |

#### Table 3: Top Telephone Numbers by Call Count
| Rank | Phone Number | Call Count | Classification |
| :--- | :--- | :--- | :--- |
| 1 | `7394210470` | 1402 | `DECOY_CIVILIAN` |
| 2 | `9705466889` | 1148 | `LIEUTENANT` |
| 3 | `6727889579` | 1110 | `LIEUTENANT` |
| 4 | `8192832764` | 943 | `LIEUTENANT` |
| 5 | `8303911718` | 908 | `LIEUTENANT` |

#### Table 4: Syndicate Hierarchy and Civilian Hub Metrics
| Entity Role | Phone Number | Call Count | Rank | Distinct Contacts | Classification |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Decoy Civilian Hub | `7394210470` | 1402 | 1 | 23 | `DECOY_CIVILIAN` |
| Kingpin (`PER_A_KP_01`) | `7389083863` | 12 | 48 | 2 | `KINGPIN` |
| Kingpin (`PER_B_KP_01`) | `8680443699` | 12 | 49 | 2 | `KINGPIN` |

### Test List
| Test Function | Description | Test Outcome |
| :--- | :--- | :--- |
| `test_determinism_by_seed` | Same seed must produce byte-identical truth.json, cdr.csv, and bank.csv. | **PASSED** |
| `test_all_imeis_luhn_valid` | All generated IMEIs in truth metadata and CDR records must be 15 digits and pass Luhn. | **PASSED** |
| `test_phone_format` | All phone numbers in truth.json and cdr.csv must be 10 digits starting with 6, 7, 8, or 9. | **PASSED** |
| `test_kingpin_phone_not_top_by_call_count` | Kingpin calls rarely; raw call count must NOT rank a kingpin phone first. | **PASSED** |
| `test_removing_bridge_couriers_disconnects_gang_a_from_b` | Removing the 2 bridge couriers must completely disconnect Gang A from Gang B in CDR. | **PASSED** |
| `test_burner_life_3_to_8_days` | Each burner phone must be active for 3-8 days and call only 1-2 numbers. | **PASSED** |
| `test_row_counts_within_range` | Row counts for the CDR and bank files must fall within the bounds asserted in this test. | **PASSED** |
| `test_mule_accounts_and_structuring` | 4 mule accounts with deposits just under STRUCTURING_THRESHOLD (50000) and 1 dormant 15+ days. | **PASSED** |
| `test_decoys_metadata` | Checks presence and correctness of all decoy elements in truth.json. | **PASSED** |
| `test_pizza_shop_at_least_20_distinct_contacts` | Pizza shop must have at least 20 distinct contacts (customers + operatives). | **PASSED** |
| `test_pizza_shop_is_top_3_by_call_count` | Pizza shop must rank in the top 3 phones by call count, and both kingpins in the bottom 3. | **PASSED** |
| `test_pizza_shop_no_contact_with_both_gangs` | Pizza shop must never be linked to members of both gangs (at most 3 operatives from ONE gang). | **PASSED** |

### Glossary
- call count = rows where the phone is a_party or b_party
- rank = position by descending call count (ties are ordered by ascending phone number identifier string)
- distinct contacts = number of other phones it has a call with

### Design Decisions
- Kingpin call restraint: Kingpins make very few calls and have very few distinct contacts, so their call count ranks near the bottom (see the hierarchy table).
- Innocent civilian hub: A pizza shop has many distinct contacts: outside civilian customers and a small number of operatives from one syndicate only. It has no contact with members of both syndicates, so it is not an extra link between them.
- Bridge courier routing: Dedicated bridge couriers form the exclusive telephonic connection between the separate syndicates, preventing direct inter-syndicate operative or lieutenant calls.
- Financial layering: Some deposits to mule accounts are placed just below a configurable threshold constant defined in the generator, and one mule account stays dormant before becoming active.

### Caveats
- data is synthetic
- fixed 2-gang structure
- The call-count ranks of the pizza shop and the kingpins are set by the generator's design, not discovered from the data.
- runs used Python 3.13.7

### What This Does Not Show
- Detection performance: These results show only that the generator produces the designed structure. They do not show that any extraction or analysis method works on it.
- Carrier-level transport anomalies: The dataset does not model packet loss, tower handover latencies, or network drops.
- Multi-modal surveillance: Excludes physical location tracking, vehicular tailing, and room audio intercepts.
- Alternative communication channels: Excludes encrypted application messaging, secure webmail, and in-person meetings.
- Dynamic syndicate evolution: Syndicate membership, hierarchy, and operational roles remain static rather than adapting to law enforcement intervention.
<!-- STEP1:END -->
