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


