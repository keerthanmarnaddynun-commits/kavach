# Crimi-Nex — Local Codebase Snapshot

**Audience:** Incoming developer + architectural AI  
**Scope:** Current local working tree only.  
**Date of scan:** 2026-10-25  
**Branch:** `ai-extraction`

---

## 1. What is Functioning

The end-to-end criminal intelligence pipeline is fully operational across extraction, graph intelligence, and interactive visualization.

### 1.1 Indic / XLM-R NER & Alias Engine (`ai_pipeline/model_engine.py`)
- Lazy singleton pipeline executing on CPU.
- Uses `Davlan/xlm-roberta-base-ner-hrl` as the primary active fallback engine.
- Extracts `PERSON` entities with exact character spans, confidence scores, and contextual alias discovery (`urf`, `alias`, `@`, `aka`).

### 1.2 Structured Regex Identifier Engine (`ai_pipeline/regex_engine.py`)
- Complete regex extraction for `PHONE` (10 digits), `IMEI` (15 digits), and `ACCOUNT` (bank-prefixed numbers).
- Substring deduplication and alias-merging logic prevents partial sub-tokens (e.g., `icky`, `Raju Bhai`) from producing orphan nodes.
- Full compilation into Contract 1 schema (`source_doc_id="FIR_45_2026"`, 7 deterministic entities, 6 valid relationships).

### 1.3 Pipeline Orchestration (`ai_pipeline/extractor.py`)
- `process_text()` unifies Dev A (`extract_persons`) and Dev B (`extract_regex_entities` + `compile_contract_1`) into a single call.
- Validated standalone and via backend imports.

### 1.4 Backend & Graph Intelligence (`backend/main.py`, `backend/database.py`)
- FastAPI application running on port 8000 with CORS enabled for frontend integration.
- `GraphService` computes degree and betweenness centrality using NetworkX to identify the syndicate Kingpin.
- Outputs Contract 2 payload compliant with `contracts/graph_render_schema.json`.

### 1.5 Frontend Visualization (`frontend/index.html`)
- Interactive Cytoscape.js dark-mode dashboard.
- Successfully renders 7 nodes and 6 edges from API responses.
- Visually badges and renders the identified Kingpin (`ent_02` / `Rajendra Singh (Raju Bhai)`) with a prominent red node and gold halo ring.

---

## 2. Dependencies
- Pinned and tracked in `requirements.txt`: `torch`, `transformers`, `sentencepiece`, `python-dotenv`, `fastapi`, `uvicorn`, `neo4j`, `python-multipart`, `networkx`.
- `.env` configured for local environment secrets.
