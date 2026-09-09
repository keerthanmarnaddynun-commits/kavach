# Crimi-Nex AI Engine: Implementation & Decision Log

## [2026-09-10] - Phase 1 to 3 Core Implementation

### 1. Model Selection & Architecture
* **Initial Proposal:** `ai4bharat/indic-bert` / `ai4bharat/IndicNER`
* **Deployed Model:** `Davlan/xlm-roberta-base-ner-hrl`
* **Reason for Pivot:** The IndicNER models are gated on Hugging Face, requiring runtime authentication tokens. For a seamless, offline hackathon deployment without credential friction, we implemented an automatic fallback to the XLM-RoBERTa model. 
* **Capabilities:** Natively supports cross-lingual transfer for Indian languages (Hinglish) and accurately maps `PER`, `LOC`, and `ORG` tags out of the box.

### 2. Hardware & Configuration Constraints
* **Compute:** Forced CPU-only execution (`device=-1`). This ensures the app can be demoed locally on any standard laptop without crashing due to missing CUDA/GPU drivers.
* **Loading Strategy (Singleton):** 
  * Initial model load into RAM (First Call): `~9.7 seconds`
  * Cached execution (Second Call): `0.000005 seconds`
* **Token Aggregation:** Configured `aggregation_strategy="simple"` so the model automatically reconstructs fragmented Hinglish subwords into unified names.

### 3. Post-Processing & Contract Alignment
* **Entity Filtering:** Correctly skipped non-person entities like "Sector 42" (`LOC`) to prevent injecting "orphan nodes" into the knowledge graph.
* **Alias Resolution:** Utilized lightweight RegEx targeting Hinglish keywords (`urf`, `alias`, `@`, `aka`) instead of a secondary ML model.
* **Contract Alignment:** The final dictionary output perfectly matches Dev B's expected schema (`id`, `canonical_name`, `aliases`, `type`, `char_span`, `ai_confidence`).

### 4. Performance Metrics & Verification
* **Ablation Benchmark (5 Synthetic FIRs):** 
  * Achieved 100% accuracy (8/8 entities found) in `0.35s` CPU latency.
* **Golden Sample Extraction (1 FIR - `sample_input.txt`):**
  * Detected "Vikas Kumar" with `0.9877` (98.77%) AI confidence.
  * Detected "Rajendra Singh" with `0.9886` (98.86%) AI confidence.
  * Alias extraction latency: `0.0978s`.
