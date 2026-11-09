# Crimi-Nex Evaluation Results

<!-- STEP1:BEGIN -->
## Step 1: Synthetic Case Generator Evaluation

### Results Card
- **Purpose**: Generation of synthetic criminal syndicate communication records, financial transaction ledgers, and reference ground truth metadata for benchmarking intelligence extraction pipelines.
- **Exact Command**: `python data/synthetic/generate_case.py --seed 42 --days 30 --out results/2026-11-07_step1_synthetic_r3/run1`
- **Exact Pytest Command**: `C:\Users\Kirthan\AppData\Local\Programs\Python\Python313\python.exe -m pytest -v tests/test_generate_case.py`
- **Input Files**:
- `data/synthetic/generate_case.py` (SHA-256: `1d08790ca5109fce8196106a3a5703eb4838664b6e594452113265df5cc47f8e`)
- `tests/test_generate_case.py` (SHA-256: `e5e18539d55db30924546dc2b8859e6f9d1a9e95d3643760567139c432334e60`)
- **Output Files (Run 1)**:
- `run1/truth.json` (SHA-256: `0a9fe54a0f13801e1cf042fe198c8bbfca57a974ef039ea01df2ce681996aa99`)
- `run1/cdr.csv` (SHA-256: `60cd24e6d69b1713f54a0ca07b6f98815462396cfcab64885e1793d8aea12c94`)
- `run1/bank.csv` (SHA-256: `c776b41b5ba17b868adaf425c34972471dee1c7fea6fdc321c133240b6197ba5`)
- **Key Numbers**:
- `run1/cdr.csv`: 7483 rows (columns: `a_party`, `b_party`, `imei_a`, `imsi_a`, `start_time`, `duration_sec`, `call_type`, `tower_id`, `lat`, `lon`)
- `run1/bank.csv`: 1489 rows (columns: `txn_id`, `datetime`, `from_acct`, `to_acct`, `amount`, `mode`, `ifsc`, `narration`)
- `run1/truth.json`: 21 people (key: `people`), 50 phones (key: `phones`), 21 accounts (key: `accounts`), 49 IMEIs (key: `imeis`)
- `run1/bank.csv` account lengths: `from_acct` counts by digit length: 11 digits: 386, 12 digits: 281, 14 digits: 499, 16 digits: 323; `to_acct` counts by digit length: 11 digits: 352, 12 digits: 323, 14 digits: 491, 16 digits: 323
- `run1/bank.csv` rows whose ifsc does not match `^[A-Z]{4}0[A-Z0-9]{6}$`: 0
- `run1/bank.csv` rows whose to_acct is in truth.json and whose ifsc differs from that account's ifsc: 0
- `run1/bank.csv` rows whose to_acct is not in truth.json: 942
- Account numbers (truth.json and bank.csv) that equal any phone number or IMEI value: 0

### Tables

#### Table 1: Dataset Volume and Entity Summary
| File / Key | Metric Type | Count | Notes |
| :--- | :--- | :--- | :--- |
| `run1/cdr.csv` | Total Communication Rows | 7483 | Excludes CSV header row |
| `run1/bank.csv` | Total Transaction Rows | 1489 | Excludes CSV header row |
| `run1/truth.json` | People Entities | 21 | Top-level array `people` |
| `run1/truth.json` | Telephone Numbers | 50 | Top-level array `phones` |
| `run1/truth.json` | Bank Accounts | 21 | Top-level array `accounts` |
| `run1/truth.json` | IMEI Identifiers | 49 | Top-level array `imeis` |

#### Table 2: Determinism Comparison Across Runs
| Output File | Run 1 SHA-256 | Run 2 SHA-256 | Bitwise Match |
| :--- | :--- | :--- | :--- |
| `truth.json` | `0a9fe54a0f13801e...` | `0a9fe54a0f13801e...` | **True** |
| `cdr.csv` | `60cd24e6d69b1713...` | `60cd24e6d69b1713...` | **True** |
| `bank.csv` | `c776b41b5ba17b86...` | `c776b41b5ba17b86...` | **True** |

#### Table 3: Top Telephone Numbers by Call Count
| Rank | Phone Number | Call Count | Classification |
| :--- | :--- | :--- | :--- |
| 1 | `6604817549` | 1400 | `DECOY_CIVILIAN` |
| 2 | `9065627298` | 914 | `LIEUTENANT` |
| 3 | `6531003309` | 866 | `LIEUTENANT` |
| 4 | `9165726284` | 864 | `LIEUTENANT` |
| 5 | `8255341928` | 858 | `LIEUTENANT` |

#### Table 4: Syndicate Hierarchy and Civilian Hub Metrics
| Entity Role | Phone Number | Call Count | Rank | Distinct Contacts | Classification |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Decoy Civilian Hub | `6604817549` | 1400 | 1 | 23 | `DECOY_CIVILIAN` |
| Kingpin (`PER_A_KP_01`) | `7389083863` | 12 | 49 | 2 | `KINGPIN` |
| Kingpin (`PER_B_KP_01`) | `9277434873` | 12 | 50 | 2 | `KINGPIN` |

#### Table 5: Bank Accounts by Bank (truth.json)
| Bank | Account Length(s) | IFSC Prefix(es) | Number of Accounts |
| :--- | :--- | :--- | :--- |
| SBI | 11 | SBIN | 6 |
| ICICI | 12 | ICIC | 6 |
| HDFC | 14 | HDFC | 5 |
| PNB | 16 | PUNB | 4 |

#### Table 6: Bank Transaction Ledger Properties (run1/bank.csv)
| Metric | Value |
| :--- | :--- |
| `from_acct` counts by digit length | 11 digits: 386, 12 digits: 281, 14 digits: 499, 16 digits: 323 |
| `to_acct` counts by digit length | 11 digits: 352, 12 digits: 323, 14 digits: 491, 16 digits: 323 |
| Rows whose IFSC does not match `^[A-Z]{4}0[A-Z0-9]{6}$` | 0 |
| Rows whose `to_acct` is in `truth.json` and whose IFSC differs | 0 |
| Rows whose `to_acct` is not in `truth.json` | 942 |
| Account numbers that equal any phone number or IMEI value | 0 |

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
| `test_ifsc_format_in_truth_and_bank` | Every IFSC in truth.json and bank.csv matches ^[A-Z]{4}0[A-Z0-9]{6}$. | **PASSED** |
| `test_ifsc_prefix_matches_bank` | IFSC prefix matches the bank (SBIN for SBI, ICIC for ICICI, HDFC for HDFC, PUNB for PNB). | **PASSED** |
| `test_account_length_matches_bank` | Account length matches the bank: SBI 11 digits, ICICI 12, HDFC 14, PNB 16. Digits only. | **PASSED** |
| `test_no_account_has_10_or_15_digits` | No account may have 10 or 15 digits (to prevent confusion with phone number or IMEI). | **PASSED** |
| `test_bank_csv_ifsc_equals_receiving_account_ifsc` | In bank.csv the ifsc column is the IFSC of the RECEIVING account (to_acct). | **PASSED** |
| `test_no_account_number_equals_any_phone_or_imei` | No account number equals any phone number or IMEI value. | **PASSED** |

### Glossary
- call count = rows where the phone is a_party or b_party
- rank = position by descending call count (ties are ordered by ascending phone number identifier string)
- distinct contacts = number of other phones it has a call with

### Design Decisions
- Kingpin call restraint: Kingpins make very few calls and have very few distinct contacts, so their call count ranks near the bottom (see the hierarchy table).
- Innocent civilian hub: A pizza shop has many distinct contacts: outside civilian customers and a small number of operatives from one syndicate only. It has no contact with members of both syndicates, so it is not an extra link between them.
- Bridge courier routing: Dedicated bridge couriers form the exclusive telephonic connection between the separate syndicates, preventing direct inter-syndicate operative or lieutenant calls.
- Financial layering: Some deposits to mule accounts are placed just below a configurable threshold constant defined in the generator, and one mule account stays dormant before becoming active.
- Bank account numbers have a fixed length per bank, each account has one fixed IFSC, and the ifsc column of the bank file holds the receiving account's IFSC.

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

<!-- STEP2:BEGIN -->
## Step 2: FIR Generator and Ground Truth Extraction Evaluation

### Results Card
- **Purpose**: Generation of synthetic First Information Report (FIR) narrative texts across multiple languages and investigation typologies, paired with exact span annotations and relational answer keys for intelligence extraction benchmarking.
- **Exact Command**: `python data/synthetic/generate_firs.py --case-dir data/synthetic/out/case_demo_v2 --seed 42 --count 100 --out results/2026-11-07_step2_firs_r2/run1`
- **Exact Pytest Command**: `C:\Users\Kirthan\AppData\Local\Programs\Python\Python313\python.exe -m pytest -v tests/test_generate_firs.py`
- **Input Files**:
  - `data/synthetic/generate_firs.py` (SHA-256: `7957cfb5674c62da8826f98d7203fa9a890447fbeff42344b5123ec9495735d2`)
  - `tests/test_generate_firs.py` (SHA-256: `5680a51b5f730028fb132153c011bd488e0145bc61d7a4edfb4e4fc51758967f`)
  - `data/synthetic/out/case_demo_v2/truth.json` (SHA-256: `0a9fe54a0f13801e1cf042fe198c8bbfca57a974ef039ea01df2ce681996aa99`)
  - `data/synthetic/out/case_demo_v2/cdr.csv` (SHA-256: `60cd24e6d69b1713f54a0ca07b6f98815462396cfcab64885e1793d8aea12c94`)
  - `data/synthetic/out/case_demo_v2/bank.csv` (SHA-256: `c776b41b5ba17b868adaf425c34972471dee1c7fea6fdc321c133240b6197ba5`)
- **Output Files (Run 1)**:
  - `run1/index.json` (SHA-256: `a21ef522c2a21a8f098ae317742ecb2bb99d4f17b27ffeb6854a4b86e5c38f85`)
  - `run1/` narrative text documents and answer keys (total 201 files)
- **Key Numbers**:
  - `run1/index.json`: 100 total FIRs across 3 partition splits (keys: `doc_id`, `split`, `fir_type`, `language`, `txt_file`, `json_file`, `char_length`, `entities_count`, `relationships_count`, `template_ids`)
  - `run1/` answer keys: 1235 total entity mentions (keys: `id`, `entity_key`, `label`, `text`, `char_span`, `role`)
  - `run1/` answer keys: 54 total financial transfers (keys: `type`, `source_key`, `target_key`, `source_mention`, `target_mention`, `amount`)
  - `run1/texts`: 100 documents containing BNS and 0 containing IPC
- **Environment**: Python 3.13.7

### Tables

#### Table 1: Case Data Dependencies and Step 1 Alignment
| Input File | Step 2 Input Hash | Step 1 Latest Hash | Bitwise Match |
| :--- | :--- | :--- | :--- |
| `truth.json` | `0a9fe54a0f13801e...` | `0a9fe54a0f13801e...` | **True** |
| `cdr.csv` | `60cd24e6d69b1713...` | `60cd24e6d69b1713...` | **True** |
| `bank.csv` | `c776b41b5ba17b86...` | `c776b41b5ba17b86...` | **True** |

#### Table 2: Determinism Comparison Across Runs
| Output File Set | Total Files Checked | Matching Files | Bitwise Match |
| :--- | :--- | :--- | :--- |
| `run1/` vs `run2/` | 201 | 201 | **True** |

#### Table 3: Corpus Partition and Typology Distribution
| Partition Split | Total FIRs | Hinglish | Hindi | English | FULL | CALLS_ONLY | MONEY_ONLY | DEVICE_ONLY | MULTI_SUSPECT | ALIAS_ONLY |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `train` | 60 | 40 | 10 | 10 | 7 | 10 | 8 | 9 | 17 | 9 |
| `dev` | 20 | 13 | 4 | 3 | 3 | 3 | 3 | 2 | 5 | 4 |
| `test` | 20 | 13 | 3 | 4 | 3 | 3 | 3 | 2 | 5 | 4 |
| **Total** | 100 | 66 | 17 | 17 | 13 | 16 | 14 | 13 | 27 | 17 |

#### Table 4: Document Length and Entity Density per Partition Split
| Partition Split | Min Entities | Mean Entities | Max Entities | Min Narrative Chars | Max Narrative Chars |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `train` | 4 | 12.52 | 22 | 526 | 1393 |
| `dev` | 4 | 12.05 | 22 | 539 | 1406 |
| `test` | 4 | 12.15 | 22 | 539 | 1435 |

#### Table 5: Entity Mention Counts by Classification Type
| Partition Split | PERSON | ALIAS | PHONE | IMEI | ACCOUNT | AMOUNT | Total Mentions |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `train` | 308 | 95 | 157 | 46 | 80 | 65 | 751 |
| `dev` | 101 | 29 | 49 | 14 | 27 | 21 | 241 |
| `test` | 101 | 31 | 49 | 14 | 27 | 21 | 243 |
| **Total** | 510 | 155 | 255 | 74 | 134 | 107 | 1235 |

#### Table 6: Financial Transfers by Type per Partition Split
| Partition Split | ACCOUNT->ACCOUNT | PERSON->ACCOUNT | Total Transfers |
| :--- | :--- | :--- | :--- |
| `train` | 16 | 16 | 32 |
| `dev` | 5 | 6 | 11 |
| `test` | 5 | 6 | 11 |
| **Total** | 26 | 28 | 54 |

#### Table 7: Monetary Amount Formatting Styles
| Formatting Style | Mention Count |
| :--- | :--- |
| Indian number grouping (`1,57,400`) | 43 |
| Currency prefix and suffix (`Rs. .../-`) | 28 |
| ISO currency prefix (`INR ...`) | 26 |
| Lakh word notation (`... lakh` / `... लाख`) | 10 |

#### Table 8: Templates Used Only by Test FIRs
| Template Identifier | Partition Restriction | Reserved (id ends with _05 or _06) |
| :--- | :--- | :--- |
| `T_ALREC_EN_06` | Test Split Exclusive | Yes |
| `T_ALREC_HG_05` | Test Split Exclusive | Yes |
| `T_ALREC_HG_06` | Test Split Exclusive | Yes |
| `T_CALL_HG_05` | Test Split Exclusive | Yes |
| `T_CALL_HG_06` | Test Split Exclusive | Yes |
| `T_CTRL_HG_05` | Test Split Exclusive | Yes |
| `T_IMEI_EN_06` | Test Split Exclusive | Yes |
| `T_IMEI_HG_06` | Test Split Exclusive | Yes |
| `T_IMEI_HI_06` | Test Split Exclusive | Yes |
| `T_OWNS_EN_05` | Test Split Exclusive | Yes |
| `T_OWNS_EN_06` | Test Split Exclusive | Yes |
| `T_OWNS_HG_05` | Test Split Exclusive | Yes |
| `T_OWNS_HG_06` | Test Split Exclusive | Yes |
| `T_OWNS_HI_05` | Test Split Exclusive | Yes |
| `T_TXNA_HI_05` | Test Split Exclusive | Yes |
| `T_TXN_EN_05` | Test Split Exclusive | Yes |
| `T_TXN_HG_05` | Test Split Exclusive | Yes |
| `T_TXN_HI_02` | Test Split Exclusive | No |

#### Table 9: FIR Types per Partition Split
| Partition Split | FULL | CALLS_ONLY | MONEY_ONLY | DEVICE_ONLY | MULTI_SUSPECT | ALIAS_ONLY | Total |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `train` | 7 | 10 | 8 | 9 | 17 | 9 | 60 |
| `dev` | 3 | 3 | 3 | 2 | 5 | 4 | 20 |
| `test` | 3 | 3 | 3 | 2 | 5 | 4 | 20 |
| **Total** | 13 | 16 | 14 | 13 | 27 | 17 | 100 |

#### Table 10: Test FIRs with 6 or Fewer Entity Mentions
| Document ID | Partition Split | FIR Type | Language | Entity Mention Count |
| :--- | :--- | :--- | :--- | :--- |
| `FIR_86` | `test` | `ALIAS_ONLY` | `hinglish` | 4 |
| `FIR_92` | `test` | `ALIAS_ONLY` | `hinglish` | 4 |
| `FIR_98` | `test` | `ALIAS_ONLY` | `english` | 4 |
| `FIR_100` | `test` | `ALIAS_ONLY` | `english` | 4 |
| **Total Test FIRs with <= 6 mentions** | `test` | — | — | **4** |

#### Table 11: First and Last Sentence Diversity by Language
| Language | Total FIRs | Most Frequent First Sentence | First Count | First Share (%) | Most Frequent Last Sentence | Last Count | Last Share (%) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `hinglish` | 66 | Police Station Special Staff ke tahat FIR No.201/2026 u/s 318(4)/61(2) BNS ke antargat mukadma darj kiya gaya | 14 | 21.21% | Zabt shuda material ko sealed pullanda mein safe custody hetu police malkhana mein jamah kiya gaya | 14 | 21.21% |
| `hindi` | 17 | थाना अपराध शाखा के अंतर्गत मुकदमा अपराध संख्या २०१/२०२६ धारा ३१८(४)/६१(२) BNS में विधिक कार्यवाही प्रारंभ की गई | 4 | 23.53% | बरामद सामग्री को नियमानुसार सील कर सुरक्षित अभिरक्षा में मालखाना जमा कराया गया | 4 | 23.53% |
| `english` | 17 | Case proceedings were formally initiated under FIR No.201/2026 u/s 318(4)/61(2) BNS at Special Crime Branch | 4 | 23.53% | All seized evidentiary items were sealed in cloth pullandas and lodged into the police repository | 4 | 23.53% |

#### Table 12: Most Frequent Recurring Sentences Across Corpus
| Rank | Document Frequency | Sentence Segment |
| :--- | :--- | :--- |
| 1 | 14 | Police Station Special Staff ke tahat FIR No.201/2026 u/s 318(4)/61(2) BNS ke antargat mukadma darj kiya gaya |
| 2 | 14 | Zabt shuda material ko sealed pullanda mein safe custody hetu police malkhana mein jamah kiya gaya |
| 3 | 13 | Baramad shuda sabooton ko seal-bandh karke aage ki legal proceeding ke liye safe store kiya gaya |
| 4 | 13 | Crime branch investigation unit dwara ukt FIR No.302/2026 u/s 318(4)/61(2) BNS ke tahat prathmiki register hui |
| 5 | 13 | Maukai baramadgi ke tamam items ko proper seizure memo ke sath police custody mein rakha gaya |

#### Table 13: Statutory Terminology Incidence
| Statutory Term | Document Count |
| :--- | :--- |
| BNS | 100 |
| IPC | 0 |

### Test List
| Test Function | Description | Test Outcome |
| :--- | :--- | :--- |
| `test_entity_surface_exact_offset` | Checks that text[start:end] matches both ent['text'] and ent['surface'] exactly. | **PASSED** |
| `test_no_overlapping_spans` | Checks that entity character spans are strictly positive and non-overlapping. | **PASSED** |
| `test_relation_types_and_labels_valid` | Checks that all relation labels and entity type pairs strictly adhere to contract rules. | **PASSED** |
| `test_same_entity_key_same_normalized_value` | Checks that all mentions sharing the same entity_key have the identical normalized value. | **PASSED** |
| `test_relation_mentions_inside_evidence_span_and_match_keys` | Checks relation mentions lie strictly inside evidence_char_span and match source_key/target_key. | **PASSED** |
| `test_aliases_and_father_name_labelled` | Checks that every alias and father name in suspect sentences has a labelled span. | **PASSED** |
| `test_transfers_match_bank_row` | Checks that every TRANSFERRED_FUNDS relation matches one bank.csv row on sender, receiver, and amount. | **PASSED** |
| `test_amount_surface_parses_to_numeric_value` | Checks that each AMOUNT mention's surface string parses to its numeric value. | **PASSED** |
| `test_amount_parser_known_pairs` | Checks parse_amount_surface against a fixed hand-written lookup table of known surfaces. | **PASSED** |
| `test_no_ipc_and_bns_present` | Checks that no FIR contains 'IPC' and every FIR contains 'BNS'. | **PASSED** |
| `test_split_counts_and_language_coverage` | Checks 60 train, 20 dev, 20 test, 3-language coverage per split, and language totals. | **PASSED** |
| `test_held_out_templates_only_in_test` | Checks that held-out templates (_05, _06) appear ONLY in test, and each test FIR has >= 1. | **PASSED** |
| `test_fir_types_and_entity_count_extremes` | Checks that all 6 FIR types are present, entity count min < 5 and max > 11, and char lengths valid. | **PASSED** |
| `test_no_golden_fir_8word_sequences` | Checks that zero 8-word sequences from contracts/sample_input.txt appear in any generated FIR. | **PASSED** |
| `test_decoys_not_labelled` | Checks plain-text decoys (FIR, section, date, vehicle) are unlabelled, and cash amounts have no relations. | **PASSED** |
| `test_person_roles_present` | Checks valid roles on all PERSON entities, with officers/witnesses having null truth_id and 0 relations. | **PASSED** |
| `test_vikas_and_bikas_never_linked` | Checks that look-alike suspects Vikas and Bikas have different keys, and special cases are present. | **PASSED** |
| `test_determinism_by_seed` | Checks that running the generator twice with seed 42 produces byte-identical files. | **PASSED** |
| `test_transfers_per_split_counts` | Checks that every split contains BOTH ACCOUNT->ACCOUNT and PERSON->ACCOUNT with required minimums. | **PASSED** |
| `test_fir_types_per_split_coverage` | Checks that all 6 FIR types appear in every split, and test has at least 2 ALIAS_ONLY. | **PASSED** |
| `test_fir_length_and_short_firs` | Checks short FIRs (<= 6 entity mentions) in test split and entity count minimums <= 5 per split. | **PASSED** |
| `test_boilerplate_opening_closing_diversity` | Checks >= 5 distinct openings and closings per language, with max share <= 30% per language. | **PASSED** |

### Glossary
- mention = individual labeled entity span occurrence in narrative text with start and end character offsets
- entity_key = canonical identifier resolving multiple co-referent mentions across documents to a single real-world entity
- held-out template = phrasing template restricted exclusively to test split documents and excluded from train and dev splits
- reserved templates = phrasing templates whose identifier ends with _05 or _06; other templates can be test-only by chance
- sentence splitting = segmentation on period-space followed by uppercase letter or Devanagari danda; sentence splitting is approximate
- repeated sentence = recurring text segment appearing in multiple documents; sentence splitting on period-space followed by uppercase letter is approximate

### Design Decisions
- Partition isolation: Held-out templates are reserved exclusively for the evaluation split, ensuring that benchmark evaluations encounter unseen sentence formulations.
- Unified key normalization: Mentions of suspects and recurring civilians map to stable canonical keys while non-suspect witnesses and officials receive per-document identifiers.
- Entity variety: Synthesized narratives span multiple investigation archetypes across regional languages to reflect varied operational reporting styles.
- Empirical relation grounding: Every communicative contact and monetary transfer corresponds directly to an entry in the syndicate communication and ledger datasets.

### Caveats
- text is generated from templates, so vocabulary is narrower than real FIRs
- the test split is small
- labels are exact by construction and are not human annotations
- nothing here measures an extractor

### What This Does Not Show
- Extraction performance: These results document dataset properties and do not measure the accuracy or recall of any natural language extraction model.
- Grammatical naturalness: Template-based synthesis does not reflect the grammatical idiosyncrasies, typing errors, or colloquial dialect variations of real police station diaries.
- Full jurisdictional breadth: Terminology is aligned to modern statutory codes and NCR jurisdictions rather than encompassing all state-specific procedural formats.
- Forensic audio or image ground truth: Document packages provide textual narrative annotations without corresponding scanned document images or audio recordings.
<!-- STEP2:END -->

<!-- STEP5A:BEGIN -->
## Step 5a: Identifier Baseline and Scoring Evaluation

### Results Card
- **Purpose**: Baseline evaluation of Indian identifier extraction against synthetic First Information Report narrative texts and relational ground truth using strict and lenient scoring metrics.
- **Exact Command**: `python scripts/report/step5_baseline.py --run-id step5a_baseline_r2`
- **Exact Pytest Command**: `C:\Users\Kirthan\Desktop\crimi-nex\.venv311\Scripts\python.exe -m pytest -v tests/test_scoring.py`
- **Input Files**:
  - `ai_pipeline/scoring.py` (SHA-256: `f756585451c5d2724a65c6dd48962ecf7e4ccc1b1cbdf259cb9c7b147301b94b`)
  - `ai_pipeline/identifiers.py` (SHA-256: `3dc5b861b5f048ae675608915853b78fa745ded9c9f900604930ac7abdf01d99`)
  - `ai_pipeline/validators.py` (SHA-256: `e1413ab1e636514c74041490eed35ebaebaa17d6d2c8e4891e890e612c3a2c99`)
  - `ai_pipeline/normalizer.py` (SHA-256: `d1cfa0fa1c8480c9d55f7b0ccb6dbc31f0305deb73b7343a2c039d6a7d3a4123`)
  - `tests/test_scoring.py` (SHA-256: `68198b177b1cf6d3e335d43028e27a3c91dedc9f7835447ea94eeabd0f84c8e8`)
  - `data/synthetic/out/firs_v5/index.json` (SHA-256: `a21ef522c2a21a8f098ae317742ecb2bb99d4f17b27ffeb6854a4b86e5c38f85`)
  - Combined `firs_v5` texts and answer keys (SHA-256: `4d6dc4b3fe3c4bd50040f797fb65ebd7e684f813f6d7ada946760e66e4ac8949`)
  - Combined `firs_v5_contract` documents (SHA-256: `98cd05e846ee59c9be4bde1877f84fde630dc3c2c232f8b8ed347b81d46e90c6`)
- **Output Files**:
  - `metrics.json` (SHA-256: `def9e3ee53d6ddd8eb678281012a1df5012149ab58b146e191d1eebfb8582ca7`)
  - `pytest_raw.txt` (SHA-256: `0546b36cf70db0fe43fd6a9a89a1428430543560b252fe8ad8cea28e8a20bf3b`)
  - `SHA256SUMS.txt` (SHA-256: `d929002832a961e257ca4835c7c9b6a0ec101eebdbf006e81a10fcb6aa1e99b2`)
- **Key Numbers**:
  - `metrics.json` (`dataset_counts.total_firs`): 100 total documents
  - `metrics.json` (`dataset_counts.total_gold_mentions`): 1235 total ground truth mentions
  - `metrics.json` (`dataset_counts.total_gold_relations`): 312 total ground truth relations
  - `metrics.json` (`harness_checks.gold_mentions.f1`): 1.0000 reference mention F1
  - `metrics.json` (`harness_checks.empty_mentions.recall`): 0.0000 empty mention recall
  - `metrics.json` (`harness_checks.gold_relations.f1`): 1.0000 reference relation F1
  - `metrics.json` (`rules_evaluation.overall.PHONE.strict.f1`): 1.0000 RULES PHONE strict F1
  - `metrics.json` (`rules_evaluation.overall.ACCOUNT.strict.f1`): 1.0000 RULES ACCOUNT strict F1
  - `metrics.json` (`naive_evaluation.overall.ACCOUNT.strict.f1`): 0.4718 NAIVE ACCOUNT strict F1
  - `metrics.json` (`naive_evaluation.overall.AMOUNT.lenient.f1`): 0.6708 NAIVE AMOUNT lenient F1
- **Environment**: Python 3.11.9

### Tables

#### Table A: Overall Performance by Extractor and Type
| Extractor | Entity Type | Strict P | Strict R | Strict F1 | Lenient P | Lenient R | Lenient F1 | Strict TP | Strict FP | Strict FN |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| RULES | PHONE | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 255 | 0 | 0 |
| RULES | IMEI | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 74 | 0 | 0 |
| RULES | ACCOUNT | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 134 | 0 | 0 |
| RULES | AMOUNT | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 107 | 0 | 0 |
| NAIVE | PHONE | 0.8717 | 0.7725 | 0.8191 | 1.0000 | 0.8863 | 0.9397 | 197 | 29 | 58 |
| NAIVE | IMEI | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 74 | 0 | 0 |
| NAIVE | ACCOUNT | 0.3088 | 1.0000 | 0.4718 | 0.3088 | 1.0000 | 0.4718 | 134 | 300 | 0 |
| NAIVE | AMOUNT | 0.0000 | 0.0000 | 0.0000 | 1.0000 | 0.5047 | 0.6708 | 0 | 54 | 107 |

#### Table B: Strict F1 by Entity Type Across Dataset Partition Splits
| Extractor | Entity Type | Train Split Strict F1 | Dev Split Strict F1 | Test Split Strict F1 | Overall Strict F1 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| RULES | PHONE | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| RULES | IMEI | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| RULES | ACCOUNT | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| RULES | AMOUNT | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| NAIVE | PHONE | 0.8367 | 0.7789 | 0.8043 | 0.8191 |
| NAIVE | IMEI | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| NAIVE | ACCOUNT | 0.4665 | 0.4737 | 0.4865 | 0.4718 |
| NAIVE | AMOUNT | 0.0000 | 0.0000 | 0.0000 | 0.0000 |

#### Table C: Strict F1 by Entity Type Across Narrative Languages
| Extractor | Entity Type | Hinglish Strict F1 | Hindi Strict F1 | English Strict F1 | Overall Strict F1 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| RULES | PHONE | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| RULES | IMEI | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| RULES | ACCOUNT | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| RULES | AMOUNT | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| NAIVE | PHONE | 0.8037 | 0.8200 | 0.9000 | 0.8191 |
| NAIVE | IMEI | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| NAIVE | ACCOUNT | 0.4724 | 0.4464 | 0.5067 | 0.4718 |
| NAIVE | AMOUNT | 0.0000 | 0.0000 | 0.0000 | 0.0000 |

#### Table D: Evaluation Harness Checks
| Evaluation Suite | Condition Tested | Strict TP | Strict FP | Strict FN | Precision | Recall | F1 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Reference Mentions | Gold Predictions | 1235 | 0 | 0 | 1.0000 | 1.0000 | 1.0000 |
| Reference Mentions | Empty Predictions | 0 | 0 | 1235 | — | 0.0000 | — |
| Contract Relations | Gold Predictions | 312 | 0 | 0 | 1.0000 | 1.0000 | 1.0000 |
| Contract Relations | Empty Predictions | 0 | 0 | 312 | — | 0.0000 | — |

#### Table E: Input Hashes
| Component File | SHA-256 Digest | Evaluation Role |
| :--- | :--- | :--- |
| `ai_pipeline/scoring.py` | `f756585451c5d2724a65c6dd48962ecf7e4ccc1b1cbdf259cb9c7b147301b94b` | Mention and relational scoring harness |
| `ai_pipeline/identifiers.py` | `3dc5b861b5f048ae675608915853b78fa745ded9c9f900604930ac7abdf01d99` | Precedence-based identifier extraction |
| `ai_pipeline/validators.py` | `e1413ab1e636514c74041490eed35ebaebaa17d6d2c8e4891e890e612c3a2c99` | Pattern finders and checksum validators |
| `ai_pipeline/normalizer.py` | `d1cfa0fa1c8480c9d55f7b0ccb6dbc31f0305deb73b7343a2c039d6a7d3a4123` | Length-preserving Unicode normalization |
| `tests/test_scoring.py` | `68198b177b1cf6d3e335d43028e27a3c91dedc9f7835447ea94eeabd0f84c8e8` | Scoring test suite |
| `data/synthetic/out/firs_v5/index.json` | `a21ef522c2a21a8f098ae317742ecb2bb99d4f17b27ffeb6854a4b86e5c38f85` | Corpus split and language index |
| `firs_v5 (narratives & keys)` | `4d6dc4b3fe3c4bd50040f797fb65ebd7e684f813f6d7ada946760e66e4ac8949` | Combined hash across all FIR text and JSON files |
| `firs_v5_contract (contracts)` | `98cd05e846ee59c9be4bde1877f84fde630dc3c2c232f8b8ed347b81d46e90c6` | Combined hash across all contract files |

### Test List
| Test Function | Description | Test Outcome |
| :--- | :--- | :--- |
| `test_perfect_predictions_give_one` | Perfect predictions give 1.0 everywhere (precision, recall, f1). | **PASSED** |
| `test_empty_predictions_give_recall_zero_and_precision_none` | Empty predictions give recall 0 and precision None. | **PASSED** |
| `test_span_shifted_by_one_character_strict_miss_lenient_hit` | A span shifted by one character is a strict miss but a lenient hit. | **PASSED** |
| `test_wrong_type_is_fp_and_fn` | Wrong type is both an FP and an FN. | **PASSED** |
| `test_duplicate_prediction_is_one_tp_plus_one_fp` | Duplicate prediction is one TP plus one FP. | **PASSED** |
| `test_three_gold_two_correct_one_extra_precision_and_recall_two_thirds` | A 3-gold 2-correct 1-extra example gives exact precision 2/3 and recall 2/3. | **PASSED** |
| `test_group_by_split_and_language_add_up_to_overall` | group_by split and language add up to the overall totals. | **PASSED** |
| `test_relations_gold_used_as_predictions_gives_one` | Relations: gold used as predictions gives 1.0 everywhere. | **PASSED** |
| `test_relations_dropping_one_relation_lowers_recall` | Dropping one relation lowers recall. | **PASSED** |
| `test_relations_wrong_label_gives_fp_and_fn` | Wrong label gives FP and FN. | **PASSED** |
| `test_relations_swapped_source_and_target_is_wrong` | Swapped source and target is wrong. | **PASSED** |
| `test_relations_wrong_amount_is_wrong` | Wrong amount on TRANSFERRED_FUNDS is wrong. | **PASSED** |
| `test_entity_alignment_one_to_one` | Entity alignment is strictly one-to-one. | **PASSED** |
| `test_load_gold_mentions_total_and_counts` | load_gold_mentions on firs_v5 returns 1235 mentions in total minus nothing silently dropped. | **PASSED** |

### Glossary
- strict = evaluation matching criterion requiring exact identity of entity category and character boundary offsets
- lenient = evaluation matching criterion requiring matching entity category and character overlap resolved greedily by shared span length
- precision = ratio of true positive extractions to total predicted extractions
- recall = ratio of true positive extractions to total reference ground truth extractions
- F1 = harmonic mean of precision and recall providing a balanced performance metric
- TP = true positive extraction matching reference ground truth under the active criterion
- FP = false positive extraction predicted by the extractor without corresponding ground truth match
- FN = false negative extraction present in ground truth that was omitted by the extractor
- RULES = rule-based disambiguation pipeline applying length-preserving normalization, pattern finders, checksum validation, and precedence resolution
- NAIVE = baseline regex patterns evaluated without boundary resolution or precedence: PHONE `(?<!\d)\d{10}(?!\d)`, IMEI `(?<!\d)\d{15}(?!\d)`, ACCOUNT `(?<!\d)\d{9,18}(?!\d)`, AMOUNT `(?:Rs\.?|INR|₹)\s*[\d,]+`

### Design Decisions
- Disambiguation precedence hierarchy: Extraction conflicts between overlapping entity patterns are resolved via fixed precedence ordering to favor specialized identifiers over ambiguous digit sequences.
- Length-preserving normalization: Multilingual and script variations are converted using one-to-one character substitutions to maintain character span offsets against raw document text.
- Dual-mode evaluation harness: Performance is assessed under strict boundary requirements alongside lenient span overlap to isolate boundary clipping from complete extraction omissions.
- Negative baseline comparison: Unfiltered naive regular expressions are evaluated alongside prioritized extraction to demonstrate penalty handling on conflicting matches.

### Caveats
- RULES patterns were tuned while reading these same FIR texts, so its scores are development scores
- the generated FIRs come from templates
- NAIVE exists to show that the scorer reacts to errors
- the gold has no vehicle labels
- person names are not scored here because no model has run

### What This Does Not Show
- Machine learning generalization: These evaluations assess rule-based pattern matching and do not reflect the statistical generalization of neural language models.
- Complex linguistic ambiguity: Template narratives do not encompass the syntactical irregularities, handwriting transcriptions, or informal shorthand typical of raw station entries.
- Unstructured relationship inference: Relational benchmarks evaluate schema consistency but do not test open-domain relation extraction across unconstrained prose.
- Operational runtime latency: Evaluation focuses exclusively on extraction accuracy without profiling real-time stream throughput or memory scaling.
<!-- STEP5A:END -->

<!-- STEP5B:BEGIN -->
## Step 5b: Off-the-Shelf NER Baseline Evaluation

### Results Card
- **Purpose**: Baseline evaluation of pre-trained multilingual and Indic Named Entity Recognition models against synthetic First Information Report narratives and ground truth name entities.
- **Exact Command**: `python scripts/report/step5b_ner_baseline.py --run-id step5b_ner_baseline`
- **Exact Pytest Command**: `C:\Users\Kirthan\Desktop\crimi-nex\.venv311\Scripts\python.exe -m pytest -v tests/test_ner_baseline.py`
- **Input Files**:
  - `ai_pipeline/ner_baseline.py` (SHA-256: `fce2f5061807bf99e4ac69a0f121c609dc7783b1ee023ec86be6bd436c73465b`)
  - `ai_pipeline/scoring.py` (SHA-256: `f756585451c5d2724a65c6dd48962ecf7e4ccc1b1cbdf259cb9c7b147301b94b`)
  - `tests/test_ner_baseline.py` (SHA-256: `fed7cc9b594cc45cea122bd44c41d0cbb29d084dab03236afa45346598e570f8`)
  - `data/synthetic/out/firs_v5/index.json` (SHA-256: `a21ef522c2a21a8f098ae317742ecb2bb99d4f17b27ffeb6854a4b86e5c38f85`)
  - Combined `firs_v5` texts and answer keys (SHA-256: `4d6dc4b3fe3c4bd50040f797fb65ebd7e684f813f6d7ada946760e66e4ac8949`)
- **Output Files**:
  - `metrics.json` (SHA-256: `c02e32ee18c59574ee22722513b35c8e4da9012735d00aa842d9d4ae1883d053`)
  - `pytest_raw.txt` (SHA-256: `dff513f93439c92719cf5dbce52a7db1f9aed742dae77af1178af4e7c314b05c`)
  - `raw_davlan_xlm_roberta_base_ner_hrl_run1.json` (SHA-256: `bcd2d21bd44cf8dd9f5d8421ccae0bc2303ad2945b11250af63abdcb2cdac2ea`)
  - `raw_davlan_xlm_roberta_base_ner_hrl_run2.json` (SHA-256: `bcd2d21bd44cf8dd9f5d8421ccae0bc2303ad2945b11250af63abdcb2cdac2ea`)
  - `raw_ai4bharat_indicner_run1.json` (SHA-256: `5b53a73634412b11cbe7c73299bba9d346f4c94e1f259302d4b6886d71637b96`)
  - `raw_ai4bharat_indicner_run2.json` (SHA-256: `5b53a73634412b11cbe7c73299bba9d346f4c94e1f259302d4b6886d71637b96`)
  - `SHA256SUMS.txt` (SHA-256: `e8aa8c1b9e369f86278d6149cf340c248d40f253d52601428e59d7d51244ac49`)
- **Key Numbers**:
  - `metrics.json` (`determinism.davlan_xlm_roberta_base_ner_hrl.match`): True XLM-R determinism match between runs
  - `metrics.json` (`determinism.ai4bharat_indicner.match`): True IndicNER determinism match between runs
  - `metrics.json` (`stride_and_runtime.ai4bharat_indicner.texts_needing_stride`): 2 IndicNER texts requiring fast tokenizer stride
  - `metrics.json` (`models.davlan_xlm_roberta_base_ner_hrl.overall.POSTPROCESSED.ALL_NAMES.strict.f1`): 0.8995 XLM-R postprocessed ALL_NAMES strict F1
  - `metrics.json` (`models.davlan_xlm_roberta_base_ner_hrl.overall.POSTPROCESSED.ALL_NAMES.lenient.f1`): 0.9685 XLM-R postprocessed ALL_NAMES lenient F1
  - `metrics.json` (`models.ai4bharat_indicner.overall.POSTPROCESSED.ALL_NAMES.strict.f1`): 0.1182 IndicNER postprocessed ALL_NAMES strict F1
  - `metrics.json` (`models.ai4bharat_indicner.overall.POSTPROCESSED.ALL_NAMES.lenient.f1`): 0.6186 IndicNER postprocessed ALL_NAMES lenient F1
  - `metrics.json` (`models.davlan_xlm_roberta_base_ner_hrl.gold_classification.ALIAS.missed`): 33 XLM-R missed alias count
  - `metrics.json` (`models.ai4bharat_indicner.decoded_word_check.by_language.hindi.mismatches`): 98 IndicNER Hindi decoded word vowel mismatches
  - `metrics.json` (`models.davlan_xlm_roberta_base_ner_hrl.decoded_word_check.by_language.hindi.mismatches`): 0 XLM-R Hindi decoded word vowel mismatches
- **Environment**: Python 3.11.9, PyTorch 2.1.0+cpu, Transformers 4.35.2

### Tables

#### Table A: Overall Performance by Extractor and Type
| Model | Form | Mode | Strict P | Strict R | Strict F1 | Strict TP | Strict FP | Strict FN | Lenient P | Lenient R | Lenient F1 | Len TP | Len FP | Len FN |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Davlan/xlm-roberta-base-ner-hrl | RAW | PERSON_ONLY | 0.0043 | 0.0078 | 0.0056 | 3 | 693 | 380 | 0.5503 | 1.0000 | 0.7099 | 383 | 313 | 0 |
| Davlan/xlm-roberta-base-ner-hrl | RAW | ALL_NAMES | 0.0101 | 0.0105 | 0.0103 | 7 | 689 | 658 | 0.9066 | 0.9489 | 0.9273 | 631 | 65 | 34 |
| Davlan/xlm-roberta-base-ner-hrl | POSTPROCESSED | PERSON_ONLY | 0.5893 | 0.9817 | 0.7365 | 376 | 262 | 7 | 0.6003 | 1.0000 | 0.7502 | 383 | 255 | 0 |
| Davlan/xlm-roberta-base-ner-hrl | POSTPROCESSED | ALL_NAMES | 0.9185 | 0.8812 | 0.8995 | 586 | 52 | 79 | 0.9890 | 0.9489 | 0.9685 | 631 | 7 | 34 |
| ai4bharat/IndicNER | RAW | PERSON_ONLY | 0.0472 | 0.1097 | 0.0660 | 42 | 848 | 341 | 0.3180 | 0.7389 | 0.4446 | 283 | 607 | 100 |
| ai4bharat/IndicNER | RAW | ALL_NAMES | 0.0562 | 0.0752 | 0.0643 | 50 | 840 | 615 | 0.5056 | 0.6767 | 0.5788 | 450 | 440 | 215 |
| ai4bharat/IndicNER | POSTPROCESSED | PERSON_ONLY | 0.0911 | 0.1880 | 0.1228 | 72 | 718 | 311 | 0.3582 | 0.7389 | 0.4825 | 283 | 507 | 100 |
| ai4bharat/IndicNER | POSTPROCESSED | ALL_NAMES | 0.1089 | 0.1293 | 0.1182 | 86 | 704 | 579 | 0.5696 | 0.6767 | 0.6186 | 450 | 340 | 215 |

#### Table B: Strict and Lenient F1 by Language and Split
| Model | Group Type | Category | Strict F1 | Lenient F1 |
| :--- | :--- | :--- | :--- | :--- |
| Davlan/xlm-roberta-base-ner-hrl | Language | hinglish | 0.9125 | 0.9872 |
| Davlan/xlm-roberta-base-ner-hrl | Language | hindi | 0.8622 | 0.8711 |
| Davlan/xlm-roberta-base-ner-hrl | Language | english | 0.8869 | 0.9955 |
| Davlan/xlm-roberta-base-ner-hrl | Split | train | 0.9010 | 0.9670 |
| Davlan/xlm-roberta-base-ner-hrl | Split | dev | 0.8933 | 0.9644 |
| Davlan/xlm-roberta-base-ner-hrl | Split | test | 0.9008 | 0.9771 |
| ai4bharat/IndicNER | Language | hinglish | 0.0336 | 0.5184 |
| ai4bharat/IndicNER | Language | hindi | 0.1971 | 0.7883 |
| ai4bharat/IndicNER | Language | english | 0.3772 | 0.8333 |
| ai4bharat/IndicNER | Split | train | 0.1112 | 0.6251 |
| ai4bharat/IndicNER | Split | dev | 0.1131 | 0.6219 |
| ai4bharat/IndicNER | Split | test | 0.1465 | 0.5934 |

#### Table C: Decoded Word Check with Examples
| Model | Language | Total Spans | Mismatches | First Error Examples |
| :--- | :--- | :--- | :--- | :--- |
| Davlan/xlm-roberta-base-ner-hrl | hinglish | 463 | 0 | None |
| Davlan/xlm-roberta-base-ner-hrl | hindi | 117 | 0 | None |
| Davlan/xlm-roberta-base-ner-hrl | english | 116 | 0 | None |
| ai4bharat/IndicNER | hinglish | 540 | 437 | `vik` vs `Vik` (213:216); `hari` vs `Hari` (260:264) |
| ai4bharat/IndicNER | hindi | 202 | 98 | `सनील कमार` vs `सुनील कुमार` (196:207); `भगवान कमार` vs `भगवान कुमार` (228:239) |
| ai4bharat/IndicNER | english | 148 | 147 | `sure` vs `Sure` (208:212); `pal` vs `Pal` (215:218) |

#### Table D: Misses by Gold Type
| Model | Gold Type | Total Mentions | Strict Hit (TP) | Lenient Only | Missed (FN) | Strict + Lenient | Lenient TP |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Davlan/xlm-roberta-base-ner-hrl | PERSON | 383 | 376 | 7 | 0 | 383 | — |
| Davlan/xlm-roberta-base-ner-hrl | ALIAS | 155 | 95 | 27 | 33 | 122 | — |
| Davlan/xlm-roberta-base-ner-hrl | FATHER | 127 | 115 | 12 | 0 | 127 | — |
| Davlan/xlm-roberta-base-ner-hrl | TOTAL | 665 | 586 | 46 | 33 | 632 | 631 |
| ai4bharat/IndicNER | PERSON | 383 | 72 | 211 | 100 | 283 | — |
| ai4bharat/IndicNER | ALIAS | 155 | 6 | 53 | 96 | 59 | — |
| ai4bharat/IndicNER | FATHER | 127 | 8 | 101 | 18 | 109 | — |
| ai4bharat/IndicNER | TOTAL | 665 | 86 | 365 | 214 | 451 | 450 |

#### Table E: Error Examples
| Model | Error Category | Document ID | Gold Type | Gold Text | Predicted Text |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Davlan/xlm-roberta-base-ner-hrl | STRICT_MISS_LENIENT_HIT | `FIR_02` | NAME | `Pandit` | `Pand` |
| Davlan/xlm-roberta-base-ner-hrl | STRICT_MISS_LENIENT_HIT | `FIR_02` | NAME | `Madan Tiwari` | `Shri Madan Tiwari` |
| Davlan/xlm-roberta-base-ner-hrl | STRICT_MISS_LENIENT_HIT | `FIR_05` | NAME | `Shyam Verma` | `Shri Shyam Verma` |
| Davlan/xlm-roberta-base-ner-hrl | STRICT_MISS_LENIENT_HIT | `FIR_05` | NAME | `Madan Tiwari` | `Shri Madan Tiwari` |
| Davlan/xlm-roberta-base-ner-hrl | STRICT_MISS_LENIENT_HIT | `FIR_08` | NAME | `Kallu` | `lu` |
| Davlan/xlm-roberta-base-ner-hrl | MISSED | `FIR_03` | ALIAS | `Sunny` | — |
| Davlan/xlm-roberta-base-ner-hrl | MISSED | `FIR_04` | ALIAS | `Shooter` | — |
| Davlan/xlm-roberta-base-ner-hrl | MISSED | `FIR_20` | ALIAS | `Hawai` | — |
| Davlan/xlm-roberta-base-ner-hrl | MISSED | `FIR_24` | ALIAS | `Shooter` | — |
| Davlan/xlm-roberta-base-ner-hrl | MISSED | `FIR_40` | ALIAS | `Hawai` | — |
| Davlan/xlm-roberta-base-ner-hrl | FALSE_POSITIVE | `FIR_30` | — | — | `Shri` |
| Davlan/xlm-roberta-base-ner-hrl | FALSE_POSITIVE | `FIR_31` | — | — | `Zabt` |
| Davlan/xlm-roberta-base-ner-hrl | FALSE_POSITIVE | `FIR_31` | — | — | `Zabt` |
| Davlan/xlm-roberta-base-ner-hrl | FALSE_POSITIVE | `FIR_45` | — | — | `श्री` |
| Davlan/xlm-roberta-base-ner-hrl | FALSE_POSITIVE | `FIR_75` | — | — | `श्री` |
| ai4bharat/IndicNER | STRICT_MISS_LENIENT_HIT | `FIR_01` | NAME | `Vikas Sharma` | `Vik` |
| ai4bharat/IndicNER | STRICT_MISS_LENIENT_HIT | `FIR_01` | NAME | `Harish Sharma` | `Hari` |
| ai4bharat/IndicNER | STRICT_MISS_LENIENT_HIT | `FIR_01` | NAME | `Vikas Sharma` | `Vik` |
| ai4bharat/IndicNER | STRICT_MISS_LENIENT_HIT | `FIR_01` | NAME | `Vikas Sharma` | `Vik` |
| ai4bharat/IndicNER | STRICT_MISS_LENIENT_HIT | `FIR_01` | NAME | `Arvind Swaminathan` | `Arv` |
| ai4bharat/IndicNER | MISSED | `FIR_01` | ALIAS | `Bicky` | — |
| ai4bharat/IndicNER | MISSED | `FIR_01` | ALIAS | `Viku` | — |
| ai4bharat/IndicNER | MISSED | `FIR_01` | ALIAS | `Kallu` | — |
| ai4bharat/IndicNER | MISSED | `FIR_01` | PERSON | `Rajendra Singh` | — |
| ai4bharat/IndicNER | MISSED | `FIR_01` | ALIAS | `Biku` | — |
| ai4bharat/IndicNER | FALSE_POSITIVE | `FIR_01` | — | — | `Za` |
| ai4bharat/IndicNER | FALSE_POSITIVE | `FIR_01` | — | — | `kar` |
| ai4bharat/IndicNER | FALSE_POSITIVE | `FIR_02` | — | — | `za` |
| ai4bharat/IndicNER | FALSE_POSITIVE | `FIR_03` | — | — | `Mau` |
| ai4bharat/IndicNER | FALSE_POSITIVE | `FIR_05` | — | — | `za` |

#### Table F: Stride and Runtime Summary
| Model | Texts Evaluated | Texts Needing Stride | Model Max Length | Stride Parameter | Runtime Seconds |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Davlan/xlm-roberta-base-ner-hrl | 100 | 0 | 512 | 64 | 52.56 |
| ai4bharat/IndicNER | 100 | 2 | 512 | 64 | 97.79 |

#### Table G: Input Hashes
| Component File | SHA-256 Digest | Evaluation Role |
| :--- | :--- | :--- |
| `ai_pipeline/ner_baseline.py` | `fce2f5061807bf99e4ac69a0f121c609dc7783b1ee023ec86be6bd436c73465b` | NER pipeline, post-processing, and evaluation harness |
| `ai_pipeline/scoring.py` | `f756585451c5d2724a65c6dd48962ecf7e4ccc1b1cbdf259cb9c7b147301b94b` | Mention and relational scoring functions |
| `tests/test_ner_baseline.py` | `fed7cc9b594cc45cea122bd44c41d0cbb29d084dab03236afa45346598e570f8` | NER unit test suite |
| `data/synthetic/out/firs_v5/index.json` | `a21ef522c2a21a8f098ae317742ecb2bb99d4f17b27ffeb6854a4b86e5c38f85` | Corpus partition and metadata index |
| `firs_v5 (narratives & keys)` | `4d6dc4b3fe3c4bd50040f797fb65ebd7e684f813f6d7ada946760e66e4ac8949` | Combined SHA-256 digest of corpus files |

### Test List
| Test Function | Description | Test Outcome |
| :--- | :--- | :--- |
| `test_trims_leading_space` | Verify postprocess trims leading and trailing whitespace on original text. | **PASSED** |
| `test_merges_touching_word_pieces` | Verify postprocess merges ' B' + 'icky' into one span with right offsets. | **PASSED** |
| `test_does_not_merge_names_separated_by_space` | Verify postprocess does not merge two names separated by one space. | **PASSED** |
| `test_drops_all_whitespace_span` | Verify postprocess drops a span that contains only whitespace. | **PASSED** |
| `test_output_sorted_and_non_overlapping` | Verify output spans are strictly sorted by start position and have no overlaps. | **PASSED** |
| `test_person_only_removes_father_and_alias` | Verify PERSON_ONLY mode keeps PERSON gold and removes FATHER and ALIAS. | **PASSED** |
| `test_all_names_maps_all_three_to_name` | Verify ALL_NAMES mode maps PERSON, ALIAS and FATHER to NAME and deduplicates positions. | **PASSED** |
| `test_end_to_end_evaluate_with_fake_predictions` | Verify evaluate end-to-end yields hand-computed precision, recall, and F1. | **PASSED** |
| `test_decoded_word_check_counts_deliberately_damaged_word` | Verify decoded_word_check identifies altered words against original text slices. | **PASSED** |

### Glossary
- strict = evaluation matching criterion requiring exact identity of entity category and character boundary offsets
- lenient = evaluation matching criterion requiring matching entity category and character overlap resolved greedily by shared span length
- precision = ratio of true positive extractions to total predicted extractions
- recall = ratio of true positive extractions to total reference ground truth extractions
- F1 = harmonic mean of precision and recall providing a balanced performance metric
- TP = true positive extraction matching reference ground truth under the active criterion
- FP = false positive extraction predicted by the extractor without corresponding ground truth match
- FN = false negative extraction present in ground truth that was omitted by the extractor
- RAW = direct predictions from Hugging Face token-classification pipeline prior to boundary adjustment
- POSTPROCESSED = predictions refined by whitespace boundary trimming and zero-gap fragment merging
- PERSON_ONLY = evaluation mode restricting reference and prediction entities to primary person names
- ALL_NAMES = evaluation mode unifying person names, aliases, and paternal references under a common name category
- STRICT_HIT = gold mention whose start and end character boundaries match a predicted mention exactly
- LENIENT_ONLY = gold mention whose span overlaps a predicted mention but whose character boundaries differ
- MISSED = gold mention having no character overlap with any predicted mention
- One-to-one matching note: total of STRICT_HIT plus LENIENT_ONLY can differ from lenient TP because greedy bipartite matching pairs each prediction with at most one gold mention

### Design Decisions
- Two-stage evaluation: Evaluating both unadjusted pipeline outputs and postprocessed spans isolates tokenization boundary artifacts from underlying entity detection capability.
- Offline execution boundary: Pipeline initialization enforces offline execution constraints using cached model weights to guarantee reproducible evaluation without external network dependencies.
- Zero-gap token piece fusion: Boundary postprocessing joins touching subword fragments while preserving whitespace boundaries between distinct names.
- Unified name category benchmark: Evaluating suspect names, aliases, and paternal references under a shared category tests open-domain name extraction where fine-grained legal roles cannot be distinguished by off-the-shelf NER models.

### Caveats
- the models are used off the shelf without any training on our data
- the FIR texts come from templates
- the post-processing steps were designed after seeing raw model output
- runtime is a single measurement and varies between runs
- the gold name labels come from the generator
- the models cannot tell suspects, fathers and aliases apart

### What This Does Not Show
- Domain fine-tuning potential: Results reflect pre-trained performance rather than the ceiling achievable after task-specific fine-tuning on Indian police narratives.
- Fine-grained role classification: Off-the-shelf NER extractors do not assign investigative roles such as suspect, complainant, or witness.
- Cross-lingual coreference resolution: Benchmarks evaluate mention extraction within single documents and do not resolve aliases across multiple case narratives.
- Production throughput under concurrency: Single-thread CPU latency measurements do not evaluate batch inference scaling across distributed serving workers.
<!-- STEP5B:END -->