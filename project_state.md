# Crimi-Nex — Local Codebase Snapshot

**Audience:** Incoming developer + architectural AI  
**Scope:** Current local working tree only. No new application code was added as part of this snapshot.  
**Date of scan:** 2026-10-23  
**Agent:** AJ (local coding agent)

---

## 1. What is actually functioning

The live product surface is **Team 2 NLP extraction**, not a full-stack app. The only implemented engine is person NER plus alias post-processing.

### 1.1 XLM-RoBERTa entity extraction (`ai_pipeline/model_engine.py`)

- **Primary intended model:** `ai4bharat/IndicNER` (`NER_PRIMARY_MODEL`, gated; loaded with `HF_TOKEN` if present).
- **Active deployed path in practice:** fallback `Davlan/xlm-roberta-base-ner-hrl` (`NER_FALLBACK_MODEL`). `MODEL_CARD.md` records this pivot because IndicNER is gated on Hugging Face.
- **Task:** Hugging Face `ner` pipeline, `aggregation_strategy="simple"`.
- **Hardware:** CPU only (`device=-1`). No GPU path.
- **Lifecycle:** Global lazy singleton (`_NER_PIPELINE`). Reload only if `force_reload=True`.
- **Output of `extract_persons(text)`:** PERSON-only records matching Contract 1 person fields:
  - `id` (`ent_01`, `ent_02`, …)
  - `canonical_name`
  - `aliases`
  - `type` (always `"PERSON"`)
  - `char_span` `[start, end]`
  - `ai_confidence` (score rounded to 4 decimals)
- **Filtering:** Labels `PER` / `PERSON` only. LOC/ORG (e.g. “Sector 42”) are dropped.
- **Alias post-processing (working):** lightweight regex immediately after a person span for `urf` / `alias` / `@` / `aka` (1–3 word alias). This is **not** structured-identifier regex (phone/IMEI/account).
- **Self-check:** `python -m ai_pipeline.model_engine` (or running the file) loads the pipeline and asserts aliases on a Hinglish sample (`Vikas Kumar urf Bicky` → `["Bicky"]`).

Documented golden-sample metrics (`MODEL_CARD.md`):

- Load: ~9.7s first call; cached subsequent call ~0s.
- `contracts/sample_input.txt`: Vikas Kumar ~0.9877, Rajendra Singh ~0.9886; alias extract ~0.0978s.

### 1.2 dotenv security

- `python-dotenv` `load_dotenv()` is called at import time in:
  - `ai_pipeline/model_engine.py`
  - `ai_pipeline/benchmark.py`
  - `ai_pipeline/benchmark_indic.py`
- Secrets are read from the environment, notably `HF_TOKEN` for gated IndicNER.
- `.env` and `.env.local` are gitignored (`.gitignore` lists `.env` twice).
- **Gap:** `python-dotenv` is **used in code but not listed** in `requirements.txt`. A new environment that only `pip install -r requirements.txt` will miss it unless it was installed by hand.

### 1.3 Ablation / A-B testing

| Script | What it measures | Documented result (`BENCHMARK_RESULTS.md`, 2026-10-09) |
|---|---|---|
| `ai_pipeline/benchmark.py` | 5 synthetic **Hinglish/Romanized** FIRs; 8 ground-truth PER names; exact/partial string match; CPU | XLM-R **100.0% (8/8)** in 0.31s; IndicNER **87.5% (7/8)** in 0.32s (requires `HF_TOKEN`) |
| `ai_pipeline/benchmark_indic.py` | 6 **native Devanagari** Hindi FIR sentences; side-by-side entities + latency; UTF-8 stdout | XLM-R: intact names, total 0.2615s (avg 0.0436s/sent). IndicNER: subword/matra fragmentation (e.g. `विकास कमार`, `##ाजदर सिह`), total 0.3717s (avg 0.0619s/sent) |

Both scripts load models independently (they do **not** reuse `model_engine.load_pipeline()`). IndicNER is skipped or errors without `HF_TOKEN`.

### 1.4 Contracts (schemas only, not runtime)

- `contracts/ai_output_schema.json` — Contract 1 example: PERSON + PHONE + IMEI + ACCOUNT + relationships (`OWNS_DEVICE`, `ASSOCIATED_IMEI`, `COMMUNICATED_WITH`, `TRANSFERRED_FUNDS`, `CONTROLS_ACCOUNT`).
- `contracts/graph_render_schema.json` — Contract 2 / Cytoscape-style graph payload (nodes, edges, kingpin, centrality). **No producer in this repo.**
- `contracts/sample_input.txt` — Hinglish FIR used as the golden narrative (persons, phones, IMEIs, SBI account).

---

## 2. Explicitly missing / non-functional components

These directories/files exist as empty placeholders or broken wiring. They must not be treated as implemented.

### 2.1 Regex for structured identifiers — **not implemented**

- `ai_pipeline/regex_engine.py` is **empty**.
- `ai_pipeline/extractor.py` is the intended Team 3 entrypoint (`process_text`) and **imports symbols that do not exist**:
  - `extract_regex_entities`
  - `compile_contract_1`
- Therefore **PHONE / IMEI / ACCOUNT** extraction, relationship compilation, and Contract 1 assembly **cannot run**. Calling `process_text` will fail at import.
- Alias regex in `model_engine.py` does **not** cover identifiers in `sample_input.txt` (`9876543210`, IMEIs, `SBI Account 30291827465`).

### 2.2 Neo4j graph DB integration — **not implemented**

- `neo4j==5.14.1` is listed in `requirements.txt` under “Team 3: Backend & Database”.
- `backend/database.py` is **empty**. There is **no** driver usage, Cypher, graph write path, or kingpin/centrality logic anywhere in Python.
- Contract 2 (`graph_render_schema.json`) has no implementation.

### 2.3 UI / API — **not implemented**

- `frontend/package.json` is **empty**; `frontend/src/` exists with **no files**.
- `backend/main.py` is **empty**. FastAPI / Uvicorn are declared in requirements but unused.
- No README, no routes, no upload/extract UI.

### 2.4 Orchestration gap

`extractor.py` documents the intended pipeline (persons → regex objects → Contract 1 JSON with hardcoded `source_doc_id="FIR_45_2026"`), but only step 1 (`extract_persons`) has an implementation.

---

## 3. Active dependencies

Pinned in `requirements.txt`. Status is **declared vs actually imported**.

### Used by current AI pipeline

| Package | Pin | Used by |
|---|---|---|
| `torch` | `2.1.0` | Hugging Face backend via `model_engine.py` (`import torch`) |
| `transformers` | `4.35.2` | NER `pipeline` in `model_engine.py`, `benchmark.py`, `benchmark_indic.py` |
| `sentencepiece` | `0.1.99` | Tokenizer support for the transformer models (not imported directly) |

### Used in code, **not** pinned

| Package | Used by |
|---|---|
| `python-dotenv` | `load_dotenv()` in model + both benchmarks |

### Declared, **not** used by any non-empty module

| Package | Pin | Intended team |
|---|---|---|
| `fastapi` | `0.104.1` | Team 3 backend |
| `uvicorn` | `0.24.0` | Team 3 backend |
| `neo4j` | `5.14.1` | Team 3 database |
| `python-multipart` | `0.0.6` | Team 3 file uploads |

**Runtime models (downloaded, not pip packages):**

- `Davlan/xlm-roberta-base-ner-hrl` — open, active fallback / documented production model.
- `ai4bharat/IndicNER` — gated; optional if `HF_TOKEN` is set.

**Stdlib only:** `json`, `logging`, `os`, `re`, `time`, `sys`, `typing`.

---

## 4. Architectural facts for the next developer

1. **Working unit:** CPU NER person extractor + alias regex + two benchmark harnesses + decision/results docs.
2. **Not a runnable product:** no API, no UI, no graph store, no identifier regex, no Contract 1 compiler.
3. **Do not assume IndicNER is live.** Default successful path is XLM-R; IndicNER is gated and lost the Devanagari integrity comparison in the logged A/B run.
4. **Contracts are the spec.** Implement regex + relationships against `contracts/ai_output_schema.json` and `contracts/sample_input.txt`; graph UI against `contracts/graph_render_schema.json`.
5. **Security posture today:** `.env` gitignored; token never hardcoded. Still add `python-dotenv` to requirements before handoff.

---

## 5. Current file tree

Empty files/dirs are marked. `__pycache__` and `.git` omitted.

```
crimi-nex/
├── .env                          # local secrets (gitignored; present on this machine)
├── .gitignore
├── requirements.txt
├── project_state.md              # this snapshot
├── ai_pipeline/
│   ├── MODEL_CARD.md             # implementation & decision log (Phases 1–3)
│   ├── BENCHMARK_RESULTS.md      # logged Hinglish + Devanagari results
│   ├── model_engine.py           # FUNCTIONING: NER singleton + person + alias regex
│   ├── extractor.py              # BROKEN wiring: imports missing regex_engine APIs
│   ├── regex_engine.py           # EMPTY — structured ID regex not implemented
│   ├── benchmark.py              # FUNCTIONING: Hinglish ablation vs IndicNER
│   └── benchmark_indic.py        # FUNCTIONING: Devanagari A/B vs IndicNER
├── contracts/
│   ├── ai_output_schema.json     # Contract 1 example (entities + relationships)
│   ├── graph_render_schema.json  # Contract 2 example (graph render payload)
│   └── sample_input.txt          # golden Hinglish FIR narrative
├── backend/
│   ├── main.py                   # EMPTY — FastAPI app missing
│   ├── database.py               # EMPTY — Neo4j integration missing
│   └── c_engine/                 # EMPTY directory
└── frontend/
    ├── package.json              # EMPTY
    └── src/                      # EMPTY — no UI source
```

---

## 6. Source notes (for architectural AI)

- `model_engine.py` header: “Dev A - Phase 3”; NER + alias resolution complete; CPU singleton.
- `extractor.py` comment: “Main function called by Team 3 (Backend)”; Dev A persons, Dev B numbers/accounts + Contract 1 compile — Dev B side absent.
- `MODEL_CARD.md` date: 2026-10-09; documents XLM-R pivot, CPU constraint, alias regex, 100% Hinglish ablation.
- `BENCHMARK_RESULTS.md` date: 2026-10-09; includes IndicNER Hinglish 87.5% and full Devanagari side-by-side log.
