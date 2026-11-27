# KAVACH (CRIMI-NEX)

**Smart India Hackathon 2026, Problem Statement 189 · Team Nexora**

KAVACH turns unstructured police FIRs plus call-detail and bank records into a navigable case: who is connected to whom, which phone numbers and accounts behave suspiciously, and what the evidence behind each finding is. It supports the investigator. It produces **leads**, not verdicts.

---

## What it does

- **Reads FIRs with NLP.** A multilingual pipeline (Hindi, Hinglish, English) extracts people, aliases, fathers' names, phones, IMEIs, bank accounts, vehicles, amounts and the relations between them. Every fact keeps the exact text span it came from.
- **Fuses FIRs with CDR and bank CSVs** into a single case graph.
- **Flags leads.** Burner-phone and mule-account detectors, ranked by money flow. Structural scores are shown only as explanation.
- **Break analysis.** Given two groups of people, finds the smallest set of people whose removal cuts the call link between them.
- **Timeline and Insights.** Call and transfer volume over time, first-seen identifiers, and rule-based patterns worth a look.
- **Evidence handling.** Every uploaded file is hashed (SHA-256). A printable dossier carries the case fingerprint, the evidence inventory and a Section 63(4)(c) BSA 2023 certificate (Part A filled, Part B left for the expert).
- **Access control and audit.** Roles (viewer, analyst, admin) and a hash-chained audit log with chain verification.
- **Admin pages.** Model performance (extraction metrics from the official evaluation runs) and a step-by-step "How it works" walkthrough of the NLP pipeline.

## How it works

```
FIR text ──► NLP extraction ──► entities + relations (with text spans) ─┐
                                                                        ├─► case graph ─► leads, break analysis,
CDR / bank CSV ─► validation ─► records ────────────────────────────────┘   timeline, insights, dossier
```

1. **Intake.** FIR text files and the two CSVs (exact column formats are validated on upload).
2. **Extraction.** A neural NER model plus rule-based extractors for identifiers (with checksum checks), entity assembly, and relation extraction.
3. **Case graph.** Persons, phones, IMEIs, accounts and vehicles with typed edges. Numbers and accounts that appear only in the CSVs stay anonymous unless a FIR states who holds them.
4. **Analysis.** Detectors, call-layer break analysis, timeline statistics and insights.
5. **Output.** Web app and a printable dossier.

## Tech stack

| Layer | Technology |
|---|---|
| NLP | Python, PyTorch, Hugging Face Transformers (`Davlan/xlm-roberta-base-ner-hrl`), rule-based extractors |
| Backend | FastAPI, Uvicorn, NetworkX, JSON-file storage under `runtime/` |
| Frontend | React 18, Vite, Cytoscape.js (fCoSE layout) |
| Tests | pytest, Vitest |

## Repository layout

```
ai_pipeline/      NLP extraction pipeline
case_graph/       case graph construction
case_detectors/   burner-phone and mule-account detectors, call-layer break analysis
case_analytics/   projection scores and ranking support
contracts/        data contracts (schemas) between stages
kavach_api/       FastAPI backend (auth, storage, jobs, evidence, leads, timeline, insights, audit)
web/              React frontend
scripts/          run, load, evaluation and report scripts
tests/            backend tests
results/          evaluation runs
docs/             run guides, results write-ups
```

## Getting started

### Prerequisites

- Python 3.11
- Node.js 18 or newer
- The Hugging Face NER model weights available locally (downloaded once; the backend then runs offline)

### 1. Set up

Commands are for Windows PowerShell, from the project root.

```powershell
python -m venv .venv311
.\.venv311\Scripts\python.exe -m pip install -r requirements.txt
npm --prefix web install
```

### 2. Create a user

The login page needs an account. The script asks for a password (at least 10 characters). Roles are `admin`, `analyst` and `viewer`.

```powershell
.\.venv311\Scripts\python.exe scripts/create_user.py --username <name> --role admin
```

### 3. Start the backend (API on http://127.0.0.1:8000)

```powershell
.\.venv311\Scripts\python.exe scripts/run_api.py
```

### 4. Start the frontend (http://localhost:5173)

In a second terminal:

```powershell
npm --prefix web run dev
```

Open http://localhost:5173 and log in.

### Loading cases

You can create a new case from the app by uploading FIRs and the CDR and bank CSVs. To load the prepared synthetic demo case instead, stop the backend and run `scripts/load_demo_case.py`. Details and options are in `docs/api/RUNNING.md` and `docs/web/RUNNING_WEB.md`.

## Roles

| Role | Can do |
|---|---|
| viewer | Open cases, graph, leads, timeline and dossier; run break analysis |
| analyst | Everything a viewer can, plus upload documents and run analysis |
| admin | Everything an analyst can, plus delete cases, view the audit log, and the admin pages |

## Tests

```powershell
.\.venv311\Scripts\python.exe -m pytest -q
npm --prefix web test
```

## Scope

The data in this repository is synthetic. The system works on text input (no OCR), expects the exact CSV column formats, and keeps people with the same name in different FIRs as separate people unless shared identifiers link them.
