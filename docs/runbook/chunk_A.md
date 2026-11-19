# CHUNK A: backend API (new package `kavach_api/`)

Read `docs/runbook/RULES.md` first. This file is the step text. The allowed files and the checks of each step are in
`docs/runbook/chunk_A.steps.json` (the tool enforces them). Work branch: `phase-d-ag`.

## A.0 What this chunk builds

A local web API (FastAPI) that wraps code that already exists and is frozen:

- `ai_pipeline.pipeline` (text -> entities and relations, contract v1.1),
- `case_graph.builder` (FIR analyses + CDR csv + bank csv -> one case graph),
- `case_analytics` (financial control, projection, structural scores) and `case_detectors` (mule, burner, call-layer cut, role chips),
- `contracts/v1_1` (JSON schemas and `validate.py`).

The API lets a user create a case, upload FIR text files and two CSV files, run the extraction and the analysis, and read back: a graph
(for drawing), priority leads, mule and burner leads, a network-break result, evidence for every node and edge, a timeline, and the original
document texts with highlighted spans. Every upload is hashed. Every action is written to a hash-chained audit log. Login uses roles.

A separate chunk (C) builds a new web front end on top of this API. A later chunk builds the dossier export. Neither is part of chunk A,
but the API shapes below are what that front end will use, so keep them exactly.

This chunk does NOT add: OCR, Neo4j, a database server, cross-case search, user self-registration, e-mail, or any cloud call.

## A.1 Fixed layout on disk (all runtime data is git-ignored under `runtime/`)

```
runtime/
  auth/users.json            users (password hashes only), written atomically
  auth/secret.key            random signing secret, created at first start (32 random bytes, hex)
  audit/audit.log.jsonl      append-only, one JSON object per line, hash-chained
  jobs/<job_id>.json         one file per job
  cases/<case_id>/
     case.json               {case_id, name, created_at, created_by, synthetic: bool}
     documents/<doc_id>.txt  exact decoded text (UTF-8, written as BYTES, no newline translation)
     documents/<doc_id>.meta.json   {doc_id, filename, sha256_raw, sha256_text, chars, uploaded_at, uploaded_by, status, error}
     analyses/<doc_id>.analysis.json   output of the extractor (contract v1.1)
     cdr.csv  bank.csv       stored exactly as uploaded
     files.json              {cdr: {sha256, rows, columns, uploaded_at}|null, bank: {...}|null}
     derived/graph.json  derived/leads.json  derived/fingerprint.json
```

- `case_id` format: `C-` + 10 lowercase hex characters (from `secrets.token_hex(5)`). Validate with `^C-[0-9a-f]{10}$` EVERYWHERE a case id
  enters the code (URL path, JSON body, function argument).
- `doc_id`: the file name stem if it matches `^[A-Za-z0-9_-]{1,40}$`, otherwise `DOC-0001`, `DOC-0002`, ... (per case, in upload order).
  If the stem is already used in this case, append `-2`, `-3`, ...
- `job_id` format: `J-` + 12 lowercase hex characters.
- Never use an uploaded file name as a path. Store under the generated ids only. Keep the original name only as text in `meta.json`.
- `runtime/` is created on demand. The runtime directory can be overridden by the environment variable `KAVACH_RUNTIME_DIR` (tests use a temp dir).

## A.2 Fixed API surface (v1)

All paths start with `/api`. JSON in, JSON out, errors always as `{"error": {"code": "<snake_case>", "message": "<text>"}}`.
Roles: `viewer` < `analyst` < `admin`. "A" below means "that role or higher".

| Method and path | Role | Purpose |
|---|---|---|
| GET `/api/health` | none | `{status, model_loaded, queue_length, version}` |
| POST `/api/auth/login` | none | body `{username, password}` -> `{access_token, token_type: "bearer", expires_in, username, role}` |
| GET `/api/auth/me` | viewer | `{username, role}` |
| POST `/api/admin/users` | admin | body `{username, password, role}`; password at least 10 characters |
| GET `/api/admin/audit?limit=&offset=` | admin | audit entries |
| GET `/api/admin/audit/verify` | admin | `{ok, entries, first_bad_index}` |
| GET `/api/cases` | viewer | list: `{case_id, name, created_at, synthetic, counts: {documents, cdr_rows, bank_rows}, analyzed}` |
| POST `/api/cases` | analyst | body `{name}` -> case |
| GET `/api/cases/{id}` | viewer | detail: case, documents (meta), files, latest jobs |
| POST `/api/cases/{id}/documents` | analyst | multipart `files` (one or more `.txt`) and/or form field `text` (+ optional `name`) -> `{job_id, documents: [meta]}`; starts an extract job |
| POST `/api/cases/{id}/cdr` | analyst | multipart `file` -> `{ok, rows, errors: [...]}`; stored only if `ok` |
| POST `/api/cases/{id}/bank` | analyst | same for the bank file |
| POST `/api/cases/{id}/analyze` | analyst | -> `{job_id}`; builds graph and leads from the stored analyses and files |
| GET `/api/jobs/{job_id}` | viewer | job state |
| GET `/api/jobs/{job_id}/events` | viewer | server-sent events (see A.8) |
| GET `/api/cases/{id}/graph` | viewer | contract 2 JSON (Cytoscape elements), schema-valid |
| GET `/api/cases/{id}/leads` | viewer | priority leads and detector leads (shape in A.6) |
| GET `/api/cases/{id}/people` | viewer | list of person nodes with aliases, roles, owned phones, controlled accounts, document references |
| GET `/api/cases/{id}/nodes/{node_id}` | viewer | node detail with evidence and neighbours |
| GET `/api/cases/{id}/edges/{edge_id}` | viewer | edge detail with evidence |
| GET `/api/cases/{id}/documents/{doc_id}` | viewer | `{doc_id, filename, text, sha256_raw, sha256_text, spans: [...]}` |
| GET `/api/cases/{id}/rows?file=cdr\|bank&rows=1,2,3` | viewer | raw rows (at most 200) with the file hash |
| GET `/api/cases/{id}/timeline?bucket=day\|hour` | viewer | calls, transfers and first-seen events per bucket |
| POST `/api/cases/{id}/break` | analyst | body `{group_a: [person_id...], group_b: [person_id...]}` -> break result |

Required status codes: 400 bad request, 401 not logged in or bad token, 403 role too low, 404 unknown id, 409 conflict (duplicate document),
413 upload too large, 422 validation failed, 429 too many failed logins. Never return a Python traceback or a server path.

## A.3 Fixed limits and defaults (in `settings.py`, all overridable by environment variables)

- FIR text: UTF-8 only, at most 5000 characters after removing a byte-order mark, not empty or only white space.
- CSV upload: at most 50 MB, at most 500000 data rows, at most 50 error entries returned.
- Token lifetime 480 minutes. Password at least 10 characters. Password hash: PBKDF2-HMAC-SHA256, 600000 iterations by default
  (tests set a small number through the settings object, never through a global).
- Login limiter: 5 failed logins per username within 5 minutes -> 429 with a `Retry-After` header (kept in memory).
- CORS allowed origins default: `http://localhost:5173` and `http://127.0.0.1:5173`; configurable with `KAVACH_CORS_ORIGINS`.
- Disclaimer string used by `/leads` and `/break` (define once as a constant and reuse):
  `"Leads are decision support derived only from the uploaded records. They are not findings of guilt and not proof."`

## A.4 Steps

Each step: do exactly what is written, add the tests listed, run the gate, commit. Names of modules below are the intended names;
if the inventory (step A0) shows a real conflict, keep the intent, choose a clean alternative and write the deviation in the worklog.

---

### A0. Preflight (no application code)

Goal: record the facts you will rely on, so nothing later is guessed.

Do:
1. `status`, then `begin`. Check `git branch --show-current` is `phase-d-ag` (the user created it). If not, STOP.
2. With `run`, save to `runbook_logs/A/A0_environment.txt` (use one `run` per command, then write a short combined file by running a
   Python one-liner that concatenates the raw logs; do not retype outputs): Python version; `pip list` lines for fastapi, uvicorn,
   python-multipart, pydantic, starlette, httpx, networkx, numpy, torch, transformers; whether `import httpx` works; the result of
   `pytest --collect-only -q` (last line only); `git log --oneline -5`; whether the Hugging Face cache folder for
   `Davlan/xlm-roberta-base-ner-hrl` exists (only check that the folder exists; do NOT load the model).
3. If `httpx` cannot be imported: write the exact line `pip install httpx==0.25.2` (and the line to add to `requirements.txt`) in the worklog,
   run `hold`, and STOP. (FastAPI's test client needs it. The user will install it and release you.)
4. Build `runbook_logs/A/A0_api_inventory.txt` with a small throw-away script in `scratch/` that IMPORTS these modules and prints, for each
   public function or class used by this chunk, its name and `inspect.signature` and the first line of its docstring:
   `ai_pipeline.pipeline` (process/analyze functions, exceptions), `case_graph.builder`, `case_graph.validate`, `case_analytics.*`,
   `case_detectors.*` (mule, burner, cut_calls, roles), `case_simulation.v2` (financial control and projection helpers, if they live there),
   `contracts.v1_1.validate`. Also print the names of the keys at the top level of one saved analysis file
   `results/2026-11-11_step6_extraction_r2/run1/FIR_01.analysis.json`, of `data/graph/out/case_demo_v2_r2/graph.json`, and of
   `contracts/v1_1/graph_render_schema.json` (its `required` lists and whether `additionalProperties` is false anywhere).
   Importing must not load the neural model. If importing a module loads the model or takes more than 20 seconds, log it.
5. Check in the inventory (write the answers as lines in the file): (a) does `case_graph.builder.build_case_graph` find analysis files only
   by the pattern `FIR_*.analysis.json`? (b) which function computes financial control per person? (c) which function turns CDR rows into
   the call-layer person graph? (d) what exact exception classes does the extractor raise for empty, too long and no-entity text?
6. Edit `.gitignore` (additive only): add the lines `runtime/`, `scratch/`, `models/` (only if not already present).
7. Edit `requirements.txt` ONLY if the user approved a new pin through a hold/release cycle (additive line only).

Done when: the gate passes (imports work, Python is 3.11, ignore rules present, the two log files exist).

---

### A1. Settings and storage (no HTTP)

Create `kavach_api/__init__.py`, `kavach_api/settings.py`, `kavach_api/storage.py`, `tests/test_api_settings_storage.py`.

`settings.py`: a frozen dataclass `Settings` with: `runtime_dir`, `cors_origins`, `jwt_ttl_minutes`, `pbkdf2_iterations`,
`max_upload_bytes`, `max_fir_chars`, `max_csv_rows`, `login_fail_limit`, `login_fail_window_seconds`; and `load_settings(env=None)` that
reads the environment variables (names: `KAVACH_RUNTIME_DIR`, `KAVACH_CORS_ORIGINS`, `KAVACH_JWT_TTL_MIN`, `KAVACH_PBKDF2_ITERATIONS`,
`KAVACH_MAX_UPLOAD_BYTES`). Defaults from A.3. `repo_root()` returns the repository root from `__file__`. No import-time side effects.

`storage.py`: class `Store(settings)` with at least: `create_case(name, created_by, synthetic=False)`, `list_cases()`, `get_case(case_id)`,
`add_document(case_id, filename, raw_bytes, uploaded_by) -> meta`, `get_document(case_id, doc_id) -> (meta, text)`, `list_documents(case_id)`,
`save_analysis(case_id, doc_id, analysis)`, `load_analyses(case_id)`, `set_document_status(case_id, doc_id, status, error=None)`,
`save_csv(case_id, kind, raw_bytes, report)`, `csv_path(case_id, kind)`, `files_info(case_id)`, `derived_path(case_id, name)`,
`case_lock(case_id)` (a `threading.RLock` per case id). Helper functions `validate_case_id`, `validate_doc_id`, `safe_stem(filename)`.

Rules: `add_document` stores `text = raw_bytes.decode("utf-8-sig")` as UTF-8 BYTES; `sha256_raw` is the hash of the uploaded bytes,
`sha256_text` is the hash of the stored text bytes; reject a second upload of the same `sha256_raw` in the same case with a typed error
(`DuplicateDocument`, carrying the existing doc id). All JSON writes atomic. All ids validated before any path is built.

Tests required: create/list/get case; id validation rejects `../x`, `C-1`, upper-case hex, absolute paths, unicode look-alikes; document store
keeps exact characters including a Hindi text with CRLF newlines (read back equals sent, and `sha256_text` equals the hash of the bytes on disk);
duplicate detection; doc id generation for odd file names (spaces, unicode, `..`, very long); atomic write leaves no temp file; two threads
adding documents to the same case never produce the same doc id; a case directory is never created outside the runtime dir.

---

### A2. Security primitives and audit log (no HTTP)

Create `kavach_api/security.py`, `kavach_api/audit.py`, `scripts/create_user.py`, `tests/test_api_security.py`, `tests/test_api_audit.py`.
Standard library only (no new package).

`security.py`:
- `hash_password(password, iterations)` -> string `pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>` (16 random bytes salt); `verify_password(password, stored)`
  using `hmac.compare_digest`.
- HS256 tokens built by hand (base64url header and payload, HMAC-SHA256 signature): `create_token(secret, username, role, ttl_seconds, now=None)`,
  `decode_token(secret, token, now=None)` -> claims; raises `TokenError` for: wrong number of parts, bad base64, bad signature, `alg` other than `HS256`
  (including `none`), expired token, missing claims, unknown role. Compare signatures with `hmac.compare_digest`.
- `ROLES = ("viewer", "analyst", "admin")`, `role_at_least(role, minimum)`.
- `UserStore(path, iterations)`: `create_user`, `authenticate` (always spends similar time for unknown users: hash a dummy password), `get`, `list_users`
  (never returns hashes), atomic writes, rejects duplicate usernames (case-insensitive) and usernames not matching `^[A-Za-z0-9_.-]{3,40}$`.
- `LoginLimiter(limit, window_seconds)` with an injectable clock.
- `load_or_create_secret(path)`: 32 random bytes as hex, created once, file permissions best effort.

`audit.py`: `AuditLog(path)` with `append(actor, role, action, case_id=None, detail=None)` -> entry, `read(limit, offset)`, `verify()` -> `(ok, count, first_bad_index)`.
Entry fields: `seq`, `ts`, `actor`, `role`, `action`, `case_id`, `detail` (small dict; never passwords, tokens or document text), `prev_hash`, `hash`.
`hash = sha256(prev_hash + "\n" + canonical_json(entry_without_hash))` where canonical JSON has sorted keys and no spaces; first `prev_hash` is 64 zeros.
Appends are serialised with a lock and flushed to disk. `verify` recomputes the whole chain.

`scripts/create_user.py`: command line, reads the password with `getpass` (never from an argument), writes through `UserStore`, uses `load_settings()`.

Tests required: password round trip; wrong password fails; two hashes of the same password differ; token round trip; tampered payload fails; tampered
signature fails; `alg: none` rejected; expired rejected; token signed with another secret rejected; role ordering; user store duplicate and invalid names; hashes
never returned; limiter blocks the 6th failure and releases after the window (fake clock); audit chain verifies; changing one character in the middle line
makes `verify` fail with the index of that line; deleting a middle line fails; appending from 8 threads gives sequence numbers 1..N without gaps and a valid chain.

---

### A3. Ingestion validation

Create `kavach_api/ingest.py`, `tests/test_api_ingest.py`.

- `decode_fir(raw_bytes, max_chars)` -> `str`; raises `IngestError(code, message)` with codes `invalid_encoding` (not valid UTF-8), `empty_text`, `text_too_long`.
  A UTF-8 byte-order mark is removed. Do not change newlines or strip the text (offsets depend on the exact characters).
- CDR validation `validate_cdr(raw_bytes, settings)` and bank validation `validate_bank(raw_bytes, settings)` -> `CsvReport(ok, rows, columns, errors)`.
  Read everything as strings with the `csv` module (never type-convert on read: leading zeros must survive). Required columns (exact names, any order, extra columns allowed):
  - CDR: `a_party, b_party, imei_a, imsi_a, start_time, duration_sec, call_type, tower_id, lat, lon`
  - bank: `txn_id, datetime, from_acct, to_acct, amount, mode, ifsc, narration`
  Row rules, reported as `{row, column, code, message}` with `row` = the 1-based DATA row number (the same numbering the case graph builder uses for evidence rows):
  - CDR: `a_party` and `b_party` match `^[6-9][0-9]{9}$`; `imei_a` empty or 15 digits; `start_time` ISO date-time; `duration_sec` integer >= 0; `call_type` is `VOICE` or `SMS`.
  - bank: `from_acct` and `to_acct` are digits, 5 to 20 characters; `amount` a positive decimal with at most 2 decimal places; `datetime` ISO date-time; `mode` not empty.
  Stop collecting after 50 errors but still count them (`error_count`). Reject: empty file, header only, more rows than the limit, size over the limit, non-UTF-8 bytes, a BOM is allowed.
  Other layouts (other header names, phone numbers with `+91`, scanned files) are NOT supported yet: the error text must say which required column is missing.

Tests required: valid minimal files pass; each rule fails with the right code and row number; leading zeros kept; BOM and CRLF accepted; a 10 MB generated file passes quickly
(under 5 seconds); the real files `data/synthetic/out/case_demo_v2/cdr.csv` and `bank.csv` pass with zero errors and the row counts 7483 and 1489 (read the expected counts from
`data/graph/out/case_demo_v2_r2/stats.json`, keys `cdr_rows_read` and `bank_rows_read`; do not type them); a file with a missing column names that column; Hindi text decodes; invalid bytes rejected.

---

### A4. Jobs and extraction service

Create `kavach_api/jobs.py`, `kavach_api/extract_service.py`, `tests/test_api_jobs.py`, `tests/test_api_extract.py`.

`jobs.py`: `JobStore(runtime_dir)` (one JSON file per job, atomic writes) with `create(kind, case_id, total)`, `update(job_id, **fields)`, `get(job_id)`, `list_for_case(case_id)`;
job fields: `job_id, kind ("extract"|"analyze"), case_id, status ("queued"|"running"|"done"|"failed"), created_at, updated_at, progress {done, total, current}, errors [ {doc_id, code, message} ], result {}`.
`JobRunner`: ONE worker thread with a queue; `submit(fn, job_id)`; the worker catches every exception, marks the job `failed` with a short message (no traceback to clients; the full
traceback goes to the log); `queue_length()`; clean `shutdown()` used by tests.

`extract_service.py`:
- `extract_document(store, case_id, doc_id, extractor)` reads the stored text and calls `extractor(text, doc_id, case_id)`. The default extractor is
  `ai_pipeline.pipeline.analyze_text(text, doc_id=doc_id, case_id=case_id)`, which returns a dict with the keys `aux`, `doc` and `info`.
  Store that WHOLE dict as `analyses/<doc_id>.analysis.json` (the case graph builder reads exactly this format). Validate `result["doc"]` with
  `contracts.v1_1.validate.validate_ai_output`. Save the analysis and set the document status `extracted`. The extractor's typed errors are classes of
  `ai_pipeline.pipeline`: `EmptyText`, `TextTooLong`, `NoEntitiesFound`; map them to the document status `failed` with the codes `empty_text`,
  `text_too_long`, `no_entities_found` by matching the CLASS NAME of the exception (`type(exc).__name__`), so that the module does not have to import the
  pipeline (which takes about 10 seconds and loads torch). A contract-invalid output sets `failed` with `invalid_output`. One failing document never stops the others.
- `default_extractor()` returns a callable that imports `ai_pipeline.pipeline` LAZILY, sets `HF_HUB_OFFLINE=1`, and serialises calls with a lock (the model is not thread-safe).
  `model_loaded()` tells whether the lazy import has happened. Importing `extract_service` must NOT import torch or transformers.
- `run_extract_job(...)` processes the listed documents in order, updating job progress after each, and finishes with a summary `{extracted, failed}`.

Tests required: fake extractor (a plain function) for all job tests; job lifecycle; a document that raises each typed error ends `failed` with the right code and the next document still runs;
runner survives an exception; progress counts; `import kavach_api.extract_service` does not put `torch` in `sys.modules` (test in a subprocess).
Real-model test (named with `real_model` in its name, runs ONLY when the environment variable `KAVACH_RUN_MODEL_TESTS=1` is set, otherwise skipped): run the real extractor on the texts
`data/synthetic/out/firs_v5/FIR_01.txt`, `FIR_45.txt` and `FIR_60.txt` (if a file name differs, use the first three files in that folder and log which) and assert that the parsed JSON (all three keys `aux`, `doc`, `info`)
equals the parsed JSON of the matching files in `results/2026-11-11_step6_extraction_r2/run1/` (dictionary equality, not byte equality). Call the extractor with
`doc_id` = the file stem and with the `case_id` value that the saved file contains inside its `doc` section.
If it is not equal, STOP (rule 4): do not change anything; log the first differing key.

---

### A5. Case graph service, contract 2 rendering, evidence, timeline

Create `kavach_api/analysis_service.py` (graph part), `kavach_api/render.py`, `kavach_api/evidence.py`, `kavach_api/timeline.py`, `tests/test_api_graph.py`, `tests/test_api_evidence.py`.
Do NOT edit `case_graph/builder.py`: the inventory shows that `build_case_graph(fir_dir, cdr_path, bank_path)` already reads every `*.analysis.json` file in the folder
(sorted), whatever the file name. First prove that building from a case's `analyses/` folder with the demo files equals the committed
`data/graph/out/case_demo_v2_r2/graph.json` (loaded dict equality). If it differs, STOP.

`analysis_service.build_graph(store, case_id)`: calls the builder with the case's analyses directory and CSV files (if a CSV is missing, use only the FIR data; if both are missing and there are
no analyses, raise a typed error `nothing_to_analyze`). Saves `derived/graph.json` and `derived/fingerprint.json` (hashes of all inputs); a later call with an unchanged fingerprint returns the cached graph.

`render.py`: `render_graph(graph) -> dict` in contract 2 (Cytoscape `elements` + `summary`). The contract 2 validator is
`contracts.v1_1.validate.validate_graph` (do not confuse it with `case_graph.validate.validate_graph`, which checks the internal graph). The inventory shows that
`contracts/v1_1/graph_render_schema.json` has `additionalProperties: false` at every level. Required fields: `summary`: `schema_version, total_nodes, total_edges,
kingpin_node_id, document_hash`; node `data`: `id, label, type, isKingpin, centrality_score, ai_confidence` (plus an optional `scores` object); edge `data`: `id, source, target, label`.
READ the schema file itself before writing the code, and write its exact field types and any enumerations of node types and edge labels at the top of your worklog entry.
- NEVER add a field the schema does not list. Flags such as "hide this vehicle node", "non-suspect person" or "suggested same person" therefore go into the `/people`
  and `/leads` responses, not into `/graph`. `SAME_AS_CANDIDATE` edges are included in `/graph` only if the schema's edge label list allows them; otherwise they are
  returned in `/people` as `suggested_same_person` pairs with their reasons.
- Node ids are the graph node ids. Edge ids are `E-` + first 12 hex characters of sha1 of `source|target|relation|source_kind`.
- `summary`: `schema_version` from the contract; `total_nodes`, `total_edges`; `document_hash` = sha256 of the sorted list of all input hashes joined by newline.
- Claims. `isKingpin` is false for EVERY node (this system does not assert kingpins). `kingpin_node_id` is REQUIRED by the schema: if its type allows null, use null;
  if it must be a string, use the empty string if the schema allows it; if the schema forbids both (a pattern or a minimum length), STOP (rule 5) and hold.
  `centrality_score` = the structural composite from the person projection (0 to 1, `case_analytics.projection.compute_projection_scores`) for PERSON nodes and 0 for the
  other node types (explanation only). `ai_confidence` is required by the schema: fill it from the extractor's entity confidence where one exists and with the schema's neutral value otherwise;
  the front end will not draw it on the canvas. Use the optional `scores` object only if its allowed property names fit the structural components; otherwise leave it out.
- Every response is validated with `contracts.v1_1.validate.validate_graph` in the tests and in the service (a failure becomes a typed server error, not a broken response).

`evidence.py`: `node_evidence(store, case_id, graph, node_id)` -> for FIR evidence: list of `{doc_id, sha256_raw, char_span, surface, entity_id, ai_confidence, excerpt}` where `excerpt` is up to 80
characters either side of the span; for CSV evidence: `{file, sha256, row_numbers (first 50), row_count}`; neighbours. `edge_evidence(...)` similarly (FIR spans or CSV rows with aggregate fields).
`document_view(...)` -> text, hashes and the span list for highlighting. `rows(...)` -> the requested raw rows (max 200) read from the stored CSV with the same row numbering as the builder.

`timeline.py`: `build_timeline(store, case_id, bucket)` -> `{bucket, calls: [{t, count, voice, sms}], transfers: [{t, count, paise}], first_seen: [{phone, t}]}` using the CSV times as written (no time-zone
conversion). Buckets `day` and `hour` only.

Tests required (use a temp runtime; build the demo-like case from the real files `data/synthetic/out/case_demo_v2/*.csv` and the analyses in `results/2026-11-11_step6_extraction_r2/run1/` with the texts
from `data/synthetic/out/firs_v5/`): graph equals the committed `data/graph/out/case_demo_v2_r2/graph.json`; rendered JSON validates; ids stable across two builds; the cache is used when nothing changed and
rebuilt when a document is added; EVERY FIR evidence span slices the stored document text back to the recorded surface (all nodes, all edges); a response with an extra field fails validation (prove it with a deliberately broken copy); every CSV evidence row number exists in the stored file and the
file hash equals the recorded hash; `rows` returns the same values as reading the CSV by hand for 5 chosen rows; no node has `isKingpin` true; the summary has `kingpin_node_id` as decided above; timeline counts sum to the CSV row counts; FIR-only case (no CSV) works.

---

### A6. Analytics service

Extend `kavach_api/analysis_service.py` (or add `kavach_api/leads.py`) and add `tests/test_api_analytics.py`. Only IMPORT and CALL the frozen analytics modules; do not copy their code.

Compute and cache in `derived/leads.json` (keyed by the same fingerprint):
1. `money_flow`: persons ordered by financial control, best first. Financial control comes from `case_analytics.projection.build_person_projection` /
   `compute_projection_scores` (paise sent plus received on the accounts the documents say the person controls, divided by the maximum). Ranks come from the frozen
   `case_analytics.projection.compute_pessimistic_ranks` (persons with equal scores all get the worst rank of their tie group); set `tied: true` when another person has the same score after
   rounding to 9 decimals. Return at most 25. Each item: `{rank, tied, person_id, name, score, accounts: [...], reasons: [...], evidence: {...}}`.
   `reasons` are generated from numbers (for example total paise in and out, number of controlled accounts) as short strings; no adjectives.
2. `structural_explanation`: per person `{degree, betweenness, eigenvector, composite}` from `case_analytics.projection.compute_projection_scores` (explanation only; do not use `case_analytics.scores`, which is the older mixed-graph version).
3. `mule_accounts` and `burner_phones`: the full ranked lists from `case_detectors.mule.detect_mules(bank_csv_path, config)` and `case_detectors.burner.detect_burners(cdr_csv_path, config)`, called with the stored CSV paths and the config dict loaded from `config/detector_defaults.json` (read it; never hard-code weights); each item `{id, score, flagged, reasons, evidence_rows: {file, sha256, rows: [...]}, controlled_by or owned_by: [person ids]}`; `flagged` = score at or above the configured chip threshold; at most 25 each.
4. `role_chips`: from `case_detectors.roles.assign_role_chips(person_nodes, financial_rank, cut_members, mule_accounts_flagged, burner_phones_flagged, owner_maps, mule_min_score, burner_min_score)` using the flagged items, the money-flow ranks, and the chip thresholds read from the config. Build `owner_maps` from the OWNS_DEVICE and CONTROLS_ACCOUNT edges of the case graph and log its exact shape in the worklog.
5. `limitations`: a fixed list of strings (define once): persons appear only when a document states ownership or control; phones and accounts without a stated owner are unidentified; scores are decision support; relation extraction from text was measured at F1 0.32 on an independent held-out set; no scanned documents.
6. `generated_from`: document ids and hashes, CDR and bank hashes.
`run_break(store, case_id, group_a, group_b)`: validate that the groups are non-empty, disjoint, contain known person ids, and each has at most 200 members (typed errors otherwise); build the call-layer person graph with `case_detectors.cut_calls.call_layer_graph(cdr_rows, owners)` (`owners` maps a phone number to the list of person node ids that own it, taken from the OWNS_DEVICE edges); call `break_groups(graph, group_a, group_b)`; also list `unowned_bridging_phones(cdr_rows, owners, group_a, group_b)` (with call counts to each side and up to 10 evidence rows). Return `{finite, size, cut: [{person_id, name}], direct_link, bridging_unowned_phones, groups_used, note}` where `note` states that only observed calls are used and unobserved links are ignored; plus the disclaimer.

Tests required: on the demo-like case the money-flow list is non-empty, sorted, ranks equal the frozen pessimistic ranks, scores equal the frozen function's output; detectors' top items equal a direct call of the frozen detectors; chips follow the configured threshold (change the threshold in a temp copy of the config and see the flags change); `run_break` with two disjoint groups returns a result and never includes a terminal in the cut; empty, overlapping, unknown and oversized groups are rejected with typed errors; the note and disclaimer are always present; `leads.json` is reused when the fingerprint is unchanged. Do NOT assert that any particular person is the top lead or a kingpin.

---

### A7. HTTP app factory, authentication and read endpoints

Create `kavach_api/app.py` (and route modules if you like), `tests/test_api_http_read.py`, `tests/test_api_auth_http.py`.
`create_app(settings=None, extractor=None)` builds the FastAPI app: CORS from settings; one `Store`, `UserStore`, `AuditLog`, `JobStore`, `JobRunner` per app (created in a lifespan handler, shut down cleanly);
a dependency that reads `Authorization: Bearer <token>`, decodes it, checks the user still exists, and enforces the minimum role per endpoint; consistent error format (A.2) through exception handlers (unknown exceptions return 500 with
code `internal_error` and no details). Implement: health, login (with the limiter and an audit entry for success and failure), me, admin create user, admin audit and verify, and ALL read endpoints of A.2 (cases, case detail, graph, leads, people,
nodes, edges, documents, rows, timeline). The write endpoints come in A8; until then their routes may be absent.
Audit entries for: login success and failure, user created, case opened (GET case detail), leads viewed (GET leads) — nothing else on reads.
`/api/health` is public and must not reveal paths or versions of libraries.

Tests required (FastAPI `TestClient`, temp runtime, a fast `pbkdf2_iterations` in the test settings, a fake extractor): no token -> 401 on every protected route (loop over the route table); viewer cannot call analyst or admin routes (403); wrong password -> 401, six wrong passwords -> 429; token for a deleted user is rejected;
all read endpoints return the documented shapes for a case built from the real demo files; unknown case id -> 404, malformed case id -> 400 (never reaches the file system); error format is always the documented one; audit chain verifies after a sequence of calls and the admin verify endpoint says ok; `/api/health` has no path-like strings.

---

### A8. Write endpoints, jobs and progress stream

Extend the app (new route module is fine) and add `tests/test_api_http_write.py`.
Implement: create case; upload documents (multipart files and/or `text` form field; each validated with `decode_fir`; duplicates -> 409 with the existing doc id; creates ONE extract job for the new documents and returns `{job_id, documents}`);
upload CDR and bank (validated; stored only if ok; 422 with the error list otherwise); analyze (creates a job: builds graph and leads, marks the case `analyzed` when finished); job state; the event stream; the break endpoint.
Event stream (`/api/jobs/{job_id}/events`): `text/event-stream`; send `event: progress` with the job JSON on every change, a comment line `: keepalive` every 15 seconds, and close after the job is done or failed; requires the same bearer header (the front end uses fetch streaming, not `EventSource`).
Size limits are enforced WHILE reading the upload (stop reading at the limit and answer 413); never read an unbounded body into memory. Audit entries for: case created, each upload (with sha256 and size, no content), job started and finished, analyze, break run.
Only one analyze job per case at a time (second request while one is queued or running -> 409).

Tests required: full flow with the fake extractor and the real demo CSVs: create case, upload 3 FIR texts, upload both CSVs, wait for the extract job, analyze, read graph and leads; invalid CSV -> 422 with row numbers and nothing stored; oversized upload -> 413; duplicate upload -> 409; non-UTF-8 text -> 422; wrong extension/content -> 422; viewer cannot upload (403); the event stream delivers at least a `progress` event and ends; audit contains one entry per upload with the hash; break endpoint accepts valid groups and rejects invalid ones with 422.

---

### A9. Demo case, run script, OpenAPI export, end-to-end test

Create `scripts/load_demo_case.py`, `scripts/run_api.py`, `scripts/export_openapi.py`, `docs/api/openapi.json` (generated by the script, not typed), `docs/api/RUNNING.md` (facts only: commands to start the server, to create the first user, to load the demo case; no marketing text), `tests/test_api_demo_e2e.py`.

- `load_demo_case.py`: uses the SAME service functions as the HTTP path (no shortcuts around `Store`). Creates a case named `Demo (synthetic case_demo_v2)` with `synthetic: true`, stores the 100 FIR texts from `data/synthetic/out/firs_v5/`, stores the saved analyses from `results/2026-11-11_step6_extraction_r2/run1/` (check that each analysis' recorded text hash or source id matches the stored text; refuse on mismatch), stores `cdr.csv` and `bank.csv` from `data/synthetic/out/case_demo_v2/`, marks all documents `extracted`, then builds graph and leads. Refuses to run if a case with that name already exists in the runtime dir. Writes an audit entry (`demo_loaded`).
- `run_api.py`: starts uvicorn programmatically on `127.0.0.1:8000` (`--port` option), sets `HF_HUB_OFFLINE=1`, serves `create_app()`.
- `export_openapi.py <path>`: writes `app.openapi()` as sorted-key JSON.
- Run the export once with `run` and keep the generated file. Do not edit it by hand.

Tests required (`test_api_demo_e2e.py`): load the demo case into a temp runtime; through HTTP: login, list cases, graph validates, node counts per type equal those in the committed `data/graph/out/case_demo_v2_r2/stats.json` (read from the file), leads present, evidence spans slice back, timeline sums equal CSV rows; the OpenAPI document contains every path in A.2 (compare against a list in the test).

---

### A10. HTTP security pass

Create `tests/test_api_security_http.py` and fix what it finds INSIDE `kavach_api/` (one fix per failing test, no loops).
Tests required: path traversal attempts in case id, doc id, node id, file names (`../`, `..\`, absolute paths, encoded `%2e%2e`, null byte) never read or write outside the runtime dir (check the file system) and answer 400/404; upload filename with control characters stored only as text; a 1 MB JSON body to a small endpoint is rejected or ignored without memory blow-up; token tampering and `alg: none` -> 401; expired token -> 401; role escalation by editing the token payload -> 401; an admin cannot be created by an analyst; passwords never appear in the audit log, job files or responses (search the runtime dir for the test password); the secret key file is not served by any route; CORS answers only for allowed origins; error responses contain no paths, no tracebacks, no library names; the audit chain is valid after all of the above; the app starts with a read-only copy of the repository data folders (no writes outside `runtime/`: compare `git status --short` before and after the whole test file).

---

### A11. Chunk end

No new code. Do:
1. `run` the whole test suite once and the three real-model tests (`KAVACH_RUN_MODEL_TESTS=1`).
2. Write `runbook_logs/A/SUMMARY_FOR_USER.txt` (plain text, at least 600 characters) with these headings, filled only from logs and files: STEPS (id, status, commit hash for each, read from `status`); TEST COUNTS (read from the last gate logs); DEVIATIONS from the step text (copy from the worklog); FAILURES AND WHAT YOU DID; THINGS I COULD NOT CHECK; QUESTIONS FOR THE USER; HOW TO START THE SERVER (copy the commands from `docs/api/RUNNING.md`).
3. `gate`, `commit`, then run `step_tool.py bundle --chunk A` and print the bundle path.
4. STOP. The user reviews the bundle with an independent checker and decides whether to merge. Do not start another chunk.
