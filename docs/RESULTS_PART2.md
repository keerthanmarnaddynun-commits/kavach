# Crimi-Nex Evaluation Results — Part 2

This document continues the experimental and evaluation record of the Crimi-Nex project
from Step 7b onward. All prior baseline milestones, methodology notes, and benchmark stages
(Step 1 through Step 7) remain documented in [RESULTS.md](RESULTS.md).

<!-- STEP7B:BEGIN -->
## Step 7b: Post-Hoc Gap Analysis of Held-Out Extraction Results

This post-hoc gap analysis was conducted strictly after the held-out evaluation scores were recorded.
The primary headline evaluation numbers remain those documented in Step 7d of `docs/RESULTS.md`.
Zero modifications, parameter retunings, or rule adjustments have been made to the extraction pipeline.
All diagnostic categorizations below are purely structural, established via character span coordinates
and token containment without semantic or lexical rule lists.

### Diagnostic Results Card
- **Analysis Scope**: 72 person mention false positives, 13 person false negatives, 23 relation false positives, and 67 relation false negatives.
- **Repeat Short Form Mentions**: 48 of 72 person false positives match subsequent untagged mentions of individuals established earlier in the text.
- **Boundary Span Variations**: 8 person false positives match reference persons with preceding rank or title annotations included in gold spans.
- **Relation Name Surface Variations**: 11 of 23 relation false positives match reference relations where person entity endpoints reflect surface name variations.
- **Amount re-scoring check**: Exact concordance between re-scored amount extraction and recorded evaluation metrics (8 false positives, 1 false negative).
- **Uncontracted Identifiers**: 4 gold IFSC codes recorded in reference data; zero extracted under contract schemas.

### Key Numbers
  - `gap_analysis.json` (`mention_classes.fp_counts.REPEAT_SHORT_FORM`): 48 person false positives matching repeat short form mentions
  - `gap_analysis.json` (`mention_classes.fp_counts.INSIDE_GOLD_RIGHT`): 8 person false positives nested inside gold mentions with shared end offset
  - `gap_analysis.json` (`mention_classes.fp_counts.INSIDE_GOLD_LEFT`): 2 person false positives nested inside gold mentions with shared start offset
  - `gap_analysis.json` (`mention_classes.fp_counts.EXTENDS_GOLD`): 2 person false positives extending beyond gold boundaries
  - `gap_analysis.json` (`mention_classes.fp_counts.OTHER`): 12 unclassified person false positives
  - `gap_analysis.json` (`mention_classes.fn_counts.UNPAIRED`): 1 person false negatives without matching false positive boundary overlap
  - `gap_analysis.json` (`relation_classes.fp_counts.NAME_FORM_MISMATCH`): 11 relation false positives due to person source name surface variation
  - `gap_analysis.json` (`relation_classes.fp_counts.SOURCE_DIFFERS`): 6 relation false positives where predicted source person differs from gold
  - `gap_analysis.json` (`relation_classes.fp_counts.OTHER`): 5 unclassified relation false positives
  - `gap_analysis.json` (`post_hoc_adjusted.person.after.f1`): 0.8923 post-hoc adjusted strict score for person mentions
  - `gap_analysis.json` (`post_hoc_adjusted.headline_micro.after.f1`): 0.9052 post-hoc adjusted headline micro strict score across ten categories
  - `gap_analysis.json` (`post_hoc_adjusted.relations_micro.after.f1`): 0.4848 post-hoc adjusted relation micro score

### Structural Analysis Tables

#### Table 1: Mention Structural Classification Breakdown (PERSON Category)
| Error Type | Structural Category | Incident Count | Share of Type | Structural Diagnostic Criteria |
| :--- | :--- | :--- | :--- | :--- |
| False Positive | REPEAT_SHORT_FORM | 48 | 0.6667 | Untagged repeat occurrences of people already defined earlier in narrative |
| False Positive | INSIDE_GOLD_RIGHT | 8 | 0.1111 | Boundary difference where reference includes preceding title or rank |
| False Positive | INSIDE_GOLD_LEFT | 2 | 0.0278 | Boundary difference where prediction omits trailing characters |
| False Positive | INSIDE_GOLD_MIDDLE | 0 | 0.0000 | Boundary difference where prediction lies inside reference interior |
| False Positive | EXTENDS_GOLD | 2 | 0.0278 | Prediction strictly contains reference person span |
| False Positive | OTHER | 12 | 0.1667 | False positive mentions not matching structural boundary categories |
| False Negative | PAIRED_WITH_FP (INSIDE_GOLD_RIGHT) | 8 | 0.6154 | Reference person omitted due to title inclusion boundary mismatch |
| False Negative | PAIRED_WITH_FP (INSIDE_GOLD_LEFT) | 2 | 0.1538 | Reference person omitted due to trailing boundary mismatch |
| False Negative | PAIRED_WITH_FP (EXTENDS_GOLD) | 2 | 0.1538 | Reference person omitted due to extended prediction boundary |
| False Negative | UNPAIRED | 1 | 0.0769 | Reference person entirely omitted with zero boundary overlap |

#### Table 2: Relation Structural Classification Breakdown (Shipped HYBRID Extractor)
| Error Type | Structural Category | Incident Count | Share of Type | Structural Diagnostic Criteria |
| :--- | :--- | :--- | :--- | :--- |
| False Positive | NAME_FORM_MISMATCH | 11 | 0.4783 | Predicted relation matches gold relation except for person name surface variant |
| False Positive | SOURCE_DIFFERS | 6 | 0.2609 | Target identifier and amount match reference but source person differs |
| False Positive | AMOUNT_MISSING | 1 | 0.0435 | Transfer endpoints match reference but predicted amount is null |
| False Positive | OTHER | 5 | 0.2174 | Relation false positives without matching structural category |
| False Negative | PAIRED_WITH_FP | 18 | 0.2687 | Reference relations paired with predicted relation variants |
| False Negative | UNPAIRED | 49 | 0.7313 | Reference relations omitted with zero prediction counterpart |

#### Table 3: Unclassified False Positives (Category OTHER)
Of the 12 unclassified PERSON false positives, 4 overlap a gold ALIAS mention, 0 overlap a gold FATHER mention, and 8 overlap no gold mention.

| Anomaly Type | Document Identifier | Entity or Relation | Surface Text | Character Span or Endpoints | Diagnostic Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Mention | D_04 | PERSON | चिंटू | 51-56 | overlaps a gold ALIAS mention |
| Mention | H_02 | PERSON | ASI | 333-336 | overlaps no gold mention |
| Mention | H_04 | PERSON | Chomu | 388-393 | overlaps no gold mention |
| Mention | H_05 | PERSON | Lamba | 97-102 | overlaps a gold ALIAS mention |
| Mention | H_07 | PERSON | Hadapsar | 34-42 | overlaps no gold mention |
| Mention | H_08 | PERSON | Barwala | 54-61 | overlaps no gold mention |
| Mention | H_09 | PERSON | Rocky | 103-108 | overlaps a gold ALIAS mention |
| Mention | H_10 | PERSON | Dabri | 125-130 | overlaps no gold mention |
| Mention | H_11 | PERSON | Din | 24-27 | overlaps a gold ALIAS mention |
| Mention | H_14 | PERSON | ASI | 42-45 | overlaps no gold mention |
| Mention | H_14 | PERSON | Mehrauli | 104-112 | overlaps no gold mention |
| Mention | H_14 | PERSON | Aadhaar | 243-250 | overlaps no gold mention |
| Relation | D_02 | TRANSFERRED_FUNDS | दीपक -> 1234000100567890 | — | Unpaired relation prediction |
| Relation | E_02 | COMMUNICATED_WITH | 9900112233 -> 9448099887 | — | Unpaired relation prediction |
| Relation | H_05 | ASSOCIATED_IMEI | 9415098765 -> 917020045512345 | — | Unpaired relation prediction |
| Relation | H_13 | OWNS_DEVICE | Sonu Pathak -> 8527341290 | — | Unpaired relation prediction |
| Relation | H_15 | OWNS_DEVICE | Arjun Menon -> 9847012345 | — | Unpaired relation prediction |

#### Table 4: Supplementary Post-Hoc Adjusted Performance
| Evaluation Metric | Diagnostic Status | TP | FP | FN | Precision | Recall | F1 Score | Evaluation Framework Notes |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| PERSON Strict Mentions | Unchanged Frozen Metric | 79 | 72 | 13 | 0.5232 | 0.8587 | 0.6502 | Official frozen evaluation metric |
| PERSON Strict Mentions | Post-Hoc Diagnostic Adjusted | 87 | 16 | 5 | 0.8447 | 0.9457 | 0.8923 | post-hoc; uses knowledge of gold-labelling gaps; NOT a held-out result and never used as a headline |
| Headline Micro Mentions | Unchanged Frozen Metric | 202 | 78 | 30 | 0.7214 | 0.8707 | 0.7891 | Official frozen evaluation metric |
| Headline Micro Mentions | Post-Hoc Diagnostic Adjusted | 210 | 22 | 22 | 0.9052 | 0.9052 | 0.9052 | post-hoc; uses knowledge of gold-labelling gaps; NOT a held-out result and never used as a headline |
| Relations Micro Hybrid | Unchanged Frozen Metric | 21 | 23 | 67 | 0.4773 | 0.2386 | 0.3182 | Official frozen evaluation metric |
| Relations Micro Hybrid | Post-Hoc Diagnostic Adjusted | 32 | 12 | 56 | 0.7273 | 0.3636 | 0.4848 | post-hoc; uses knowledge of gold-labelling gaps; NOT a held-out result and never used as a headline |

These adjusted numbers use knowledge of the labelling gaps and are optimistic; they are not held-out results.

### Disclosed Diagnostic Facts
- **Post-Hoc Status**: This analysis examines discrepancies retrospectively using character span and token coordinates after frozen evaluation completion.
- **Reference Tagging Density**: In 48 instances, reference annotations omitted repeated mentions of established persons, causing repeat mentions of persons that the reference did not tag to register as false positives under strict offset evaluation.
- **Title Inclusion Shift**: In 8 instances, reference annotations enclosed police ranks or courtesy titles within person spans, whereas the pipeline consistently isolated the core name tokens.
- **Endpoint Alignment Impact**: In 12 instances, valid relationships linked entities whose name surfaces reflected short-form variants, preventing strict endpoint alignment under Contract v1.1.
- **Amount Consistency**: Exactly 8 amount false positives and 1 amount false negative were recorded; causes were not analysed.

### Glossary
- structural category = classification defined exclusively by character offset containment, token subsequence match, or endpoint identifier equality without lexical word lists
- REPEAT_SHORT_FORM = predicted mention span that does not overlap reference spans but whose tokens form a contiguous subsequence of a known individual
- INSIDE_GOLD_RIGHT = predicted mention span nested within a reference span sharing the end offset and omitting preceding characters
- NAME_FORM_MISMATCH = predicted relationship matching reference type and target but whose source reflects an unaligned person surface variant
- post-hoc adjustment = diagnostic recomputation illustrating the mathematical impact of structural annotation differences, strictly distinguished from frozen benchmark metrics

### Caveats
- post-hoc numbers incorporate retrospective structural knowledge and must not be cited as held-out generalization benchmarks
- structural token subsequence matching does not substitute for cross-document entity coreference
- diagnostic groupings examine surface string alignment without modifying contract validation rules
- small sample counts in specific structural categories reflect the 25 document evaluation corpus size

### What This Does Not Show
- Extractor retraining impact: The pipeline remains frozen; no model weights or heuristics were altered based on these findings.
- End-to-end station deployment: Diagnostic resolution of digital text annotations does not address OCR or physical noise in station documents.
- Open-domain relation coverage: Structural error analysis is confined to the five contracted financial and communication relationship types.
<!-- STEP7B:END -->
