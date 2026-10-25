# Kavach: AI-Powered Criminal Network Analysis & Extraction Engine (SIH26189)

An end-to-end NLP and Graph Intelligence system designed to extract complex criminal syndicates, entity hierarchies, and transaction topologies from unstructured, code-mixed (Hinglish/Devanagari) police First Information Reports (FIRs) and surveillance logs.

---

## 1. Problem Statement & Architecture
Analyzing police records in multilingual environments poses distinct NLP challenges:
- **Code-Mixing & Transliteration:** Blending Romanized Hindi (Hinglish) with formal legal terminology.
- **Underworld Aliases & Operative Handles:** Linking contextual street names (`urf`, `alias`, `@`, `aka`) to formal canonical names.
- **Entity Fragmentation:** Sub-token splits breaking downstream relational graphs.

### Technical Architecture Overview
Raw FIR Narrative (Hinglish / Devanagari)
│
▼
┌──────────────────────────────┐
│    Hybrid Extraction Layer   │
├──────────────────────────────┤
│  1. Multilingual NER Engine  │ ──► Davlan/xlm-roberta-base-ner-hrl (CPU Singleton)
│  2. Contextual Alias Parser  │ ──► Lookahead window for street names ('urf', 'alias')
│  3. Regex Identifier Engine  │ ──► PHONE (10d), IMEI (15d), ACCOUNT (9-18d)
└──────────────────────────────┘
│
▼
┌──────────────────────────────┐
│  Entity Resolution & Dedup   │ ──► Merges sub-tokens & associates identifiers
└──────────────────────────────┘
│
▼ Contract 1 (ai_output_schema.json)
┌──────────────────────────────┐
│  Graph Intelligence Engine   │ ──► NetworkX Centrality (Degree + Betweenness)
│     (backend/database.py)    │ ──► Automated Syndicate Kingpin Detection
└──────────────────────────────┘
│
▼ Contract 2 (graph_render_schema.json)
┌──────────────────────────────┐
│   Interactive Dashboard UI   │ ──► Cytoscape.js Dark-Mode Visualizer
└──────────────────────────────┘


---

## 2. Quantitative Performance & Ablation Results

Evaluated across synthetic Hinglish FIR datasets and native Devanagari reports:

| Pipeline Variant | Hinglish Extraction Accuracy | Devanagari Name Integrity | CPU Inference Latency |
| :--- | :---: | :---: | :---: |
| **XLM-RoBERTa (Current Active)** | **100.0% (8/8)** | **Intact (No Subword Loss)** | **~0.043s / sentence** |
| IndicNER (Baseline) | 87.5% (7/8) | Subword fragmentation | ~0.062s / sentence |

---

## 3. Quickstart & Execution

### 1. Installation
Clone the repository and install dependencies:
```bash
pip install -r requirements.txt