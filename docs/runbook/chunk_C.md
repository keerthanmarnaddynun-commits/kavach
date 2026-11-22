# CHUNK C: new frontend (folder `web/`)

Read `docs/runbook/RULES.md` first. This chunk adds a NEW web application in the folder `web/`. The old `frontend/` folder is frozen and unused.
The machine-readable limits of each step are in `docs/runbook/chunk_C.steps.json`. The work branch is `phase-d-ag`.

## C.0 What this chunk builds

- A single-page app: Vite + React 18 + Cytoscape.js. It talks only to the chunk A API (`/api/...`) through the Vite dev proxy to `http://127.0.0.1:8000`.
- It runs fully offline: no CDN, no web fonts, no remote images, no analytics, no external URLs.
- The assistant that wrote this text cannot see the screen. The gates check: build, unit tests, and a static design lint (`tests/test_frontend_static.py`).
  The user looks at screenshots at the checkpoints (after C2, after C5, after C8). Do not claim a screen "looks right".
- Priority cut (build in this order; people, timeline and the layout check come last): intake, overview with leads, network graph, evidence viewer, break analysis.
- NOT in this chunk: dossier export, audit-log page, admin pages, user management.

## C.1 Fixed stack (versions pinned exactly: no `^`, no `~`)

dependencies: `react` 18.3.1, `react-dom` 18.3.1, `cytoscape` 3.30.2, `cytoscape-fcose` 2.2.0
devDependencies: `vite` 5.4.11, `@vitejs/plugin-react` 4.3.4, `vitest` 2.1.8
Node v22 and npm 11 are installed. Nothing else is ever added: no router library (write a tiny hash router: `#/login`, `#/cases`, `#/case/<id>/<page>`),
no state library, no UI kit, no chart library (the timeline is hand-written SVG), no CSS framework (one plain CSS file with variables).
If you believe another package is needed, STOP and `hold` (RULES section 3, rule 3). After step C1 `web/package.json` is never edited.

## C.2 Design rules

Brief: it must look like a real link-analysis tool (Maltego / i2 / Gephi style), not a generic AI dashboard.

- Palette (CSS variables in `web/src/styles/tokens.css`): `--bg #f2f3f5`, `--surface #ffffff`, `--border #cfd4da`, `--text #1d2733`, `--muted #5b6775`,
  ONE accent `--accent #0b5cab` with `--accent-weak #e3eefa`, and `--danger #9b1c1c` used only for error text. No other colours.
- Type: UI font stack `system-ui, "Segoe UI", Arial, sans-serif` at 13px. Monospace stack `ui-monospace, "Cascadia Mono", Consolas, "Courier New", monospace`
  (class `mono`) for EVERY identifier: phones, IMEIs, accounts, ids, hashes, row numbers. No web fonts.
- Dense: table rows 26px, border radius at most 2px, no shadows (1px borders only), no gradients, no glass or blur, no neon, no emoji or emoji-like icons,
  no hero banner, no KPI tile rows, no "AI-powered" copy, no animation except a progress bar.
- Layout at 1366x768 without horizontal page scroll (panes scroll inside): top status bar 28px (name KAVACH, case id, document hash = first 12 characters
  of the case fingerprint with a copy button, user and role, logout); left case rail 200px (case list and page navigation); main area; right inspector 340px
  on the graph page (collapsible).
- Wording: use "lead", "priority lead", "unidentified", "unobserved". Never write the words kingpin, guilty, arrest, proof of anything. The field `ai_confidence`
  is shown only in a detail panel and labelled "extractor confidence". Never use the contract field `isKingpin` anywhere in `web/src`.
- Identifiers are never cut off silently: show the full value in a `title` and offer a copy button where the value is shortened.
- Every lead row has an evidence link: to a FIR span (`#/case/<id>/evidence/doc/<doc_id>?span=<start>-<end>`) or to CSV rows
  (`#/case/<id>/evidence/rows/<cdr|bank>?rows=1,2,3`).
- The disclaimer string returned by the API is shown verbatim on the overview, leads and break pages. The `limitations` strings of the leads response are shown
  verbatim in a "Limits" panel that is reachable from every case page (footer button).
- Graph: node shapes by type, grey fills, accent only for selection, focus and "lead" highlight: PERSON ellipse, PHONE round-rectangle, IMEI diamond, ACCOUNT rectangle.
  VEHICLE nodes are hidden by default (filter toggle). Labels: hidden at low zoom (`min-zoomed-font-size`), always shown for selected nodes, their neighbours and the top 10 priority leads;
  when 60 or fewer nodes are visible show all labels. Layout `cytoscape-fcose` with `nodeDimensionsIncludeLabels: true`, `animate: false`. Edge width by weight (log scale), edge labels only on selection.

## C.3 API facts the app must follow (read `docs/api/openapi.json`, `chunk_A.md` section A.2 and the real code in `kavach_api/`; use `web/src/fixtures/` for shapes)

- Errors are `{"error": {"code", "message"}}`. Token: `Authorization: Bearer <token>`, stored only in `sessionStorage` key `kavach_token` (no `localStorage`).
- 401: clear the token and go to the login page. 403: show "Your role cannot do this". 413: "File too large". 429 on login: show the Retry-After seconds.
  422 on a CSV: show a table of row errors (row, column, code, message) and the error count (first 50 are returned). 409 on documents: show the message (it contains the existing document id).
- Role gating: viewers see no upload, analyze or break buttons (hidden, not disabled). Analysts and admins see them. No admin pages in this chunk.
- Job progress: `GET /api/jobs/{id}/events` with `fetch` streaming and the Authorization header (NOT `EventSource`). Parse `event: progress` + `data:` JSON; ignore lines starting with `:`;
  stop when status is `done` or `failed`; if the stream fails fall back to polling `GET /api/jobs/{id}` every second.
- Server text (document text, names, messages) is untrusted: render only as React text nodes. Never use `dangerouslySetInnerHTML`, `innerHTML`, `eval`, `document.write`.
- Priority leads come ordered by money flow from the server. Never re-order them by a structural score. Structural scores appear only in an "explanation only, not a ranking" view.
- Numbers shown in the UI come from the API. Never hard-code a metric or a count.

## C.4 Rules for this chunk (in addition to RULES.md)

- No new packages after C1. No servers left running at the end of a step. Never start a long background process.
- Scratch files go only in `scratch/` and are NEVER named `test_*.py` or `*_test.py` (a scratch test file once broke a gate).
- Unit tests for the frontend are plain `vitest` tests (`web/src/**/*.test.js`, node environment, no DOM). Put logic in pure functions so it can be tested.
- Generate API fixtures only with `scripts/dump_api_shapes.py`; never hand-write fixture files.
- Do not edit `kavach_api/` except in step C0. Do not edit any existing test or frozen area.

## C.5 Steps

### C0. Backend follow-up (small fixes found in the chunk A review, plus a corrections note)

Create `tests/test_api_followup.py` and `docs/api/CHUNK_A_CORRECTIONS.md`. You may edit `kavach_api/*`, `scripts/load_demo_case.py`, `docs/api/RUNNING.md`. Do not edit existing tests.

1. Path traversal, done properly. For hostile ids in the case-id position, the doc-id position and the node-id position (`../x`, `..\x`, `%2e%2e`, `..%2F..%2Fx`, `%00`, absolute paths, a very long id, `C-0123456789%0A`),
   send the request and assert status 400 or 404 and the documented error body. Assertions must NOT be inside `try/except`. If the HTTP client refuses to build a URL, catch only
   `httpx.InvalidURL` or `httpx.UnsupportedProtocol` around the request call itself and count it; require that at least 8 requests were really sent. Also check that no file was created outside the temp runtime directory.
2. Unknown routes and wrong methods must use the documented error format. Add an exception handler for `starlette.exceptions.HTTPException` (404 code `not_found`, 405 code `method_not_allowed`, other codes as the existing map) that returns the same JSON shape.
   Test `GET /api/nope` and `DELETE /api/health`.
3. A read-only repository check that really compares: take `git status --short` (leave out lines starting with `runbook_logs/`, `runbook_state/`, `scratch/`), run a workload (create app on a temp runtime, create users, load the demo case, read graph and leads,
   upload one document with the fake extractor), take the status again and assert it is unchanged. Skip with a clear reason if git is missing.
4. `scripts/load_demo_case.py`: do ALL validation (every analysis checked against the text it belongs to, both CSVs validated) BEFORE creating the case, so a failure leaves nothing behind. Test with a tampered analysis: `ValueError`,
   `list_cases()` is empty afterwards, and a second call with the real folders succeeds. Do not delete files.
5. Replace the timing-dependent analyze concurrency check by a deterministic one: patch `kavach_api.app.build_graph` (the name `app.py` uses) with a function that waits on a `threading.Event`; first analyze request 200,
   second 409, exactly one analyze job exists; release the event, wait for the job, a third request returns 200.
6. `docs/api/RUNNING.md`: add two facts: stop the server before running `scripts/load_demo_case.py` (the loader and the server use separate audit-log objects), and where the runtime files are (`users.json`, `secret.key`, `audit.log` directly in the runtime directory; `KAVACH_RUNTIME_DIR` overrides it). Facts only.
7. `docs/api/CHUNK_A_CORRECTIONS.md`: copy the text of section C.6 below EXACTLY (it uses no number that is not in the logs). Do not use the words "verified", "confirmed" or "audited" in it.

Fix once, no loops. If a fix breaks an existing test, STOP and hold.

### C1. Scaffold (this step stops once to let the user install the packages)

Create `web/*`, `scripts/web_check.py`, `scripts/dump_api_shapes.py`, `tests/test_frontend_static.py`, `docs/web/*`. Edit `.gitignore`.

1. FIRST add `web/node_modules/` and `web/dist/` to `.gitignore`.
2. Create `web/package.json` with the pinned versions of C.1 (`"private": true`, `"type": "module"`, scripts `dev` = `vite`, `build` = `vite build`, `test` = `vitest run`), `web/vite.config.js`
   (react plugin; dev server port 5173 with `strictPort`; proxy `/api` to `http://127.0.0.1:8000`; vitest `test: { environment: 'node', include: ['src/**/*.test.js'] }`), `web/index.html`.
3. Run `step_tool.py hold` with the reason "user must run: npm --prefix web install" and STOP (rule 3). The user installs, then releases the step. After the release, `begin` resumes this step; `web/package-lock.json` is now one of this step's files.
4. `scripts/web_check.py <build|test|size>`: runs `npm` (find it with `shutil.which`) in `web/`; prints exactly `BUILD OK`, `TESTS OK` or `SIZE OK` on success (size: total of `web/dist` under 3 MB) and the last 40 lines of output plus a non-zero exit on failure.
5. `scripts/dump_api_shapes.py`: loads the demo case into a temp runtime, creates a viewer user with `create_user`, calls every read endpoint and the break endpoint (as an analyst) through `TestClient`, and writes `web/src/fixtures/<name>.json`
   (sorted keys, indent 2): health, login (token replaced by the text `REDACTED`), cases, case_detail, graph, leads, people, node_detail (one PERSON with FIR evidence), edge_detail (one FIR edge and one CSV edge), document, rows, timeline_day,
   break_result, job, csv_columns (the exact required CDR and bank column names, read from `kavach_api.ingest`). Long lists are cut to 5 items and long texts to 800 characters; a cut object gets `"_truncated": true`. Drop every key that ends in `_at`.
   Running it twice must give byte-identical files.
4b. Run it once with `step_tool.py run` and keep the files.
6. Skeleton: `web/src/main.jsx`, `App.jsx` (hash router and the shell of C.2: status bar, case rail, content, Limits footer), `api/client.js` (fetch wrapper, token handling, error mapping), `api/sse.js` (pure parser),
   `lib/roles.js`, `lib/format.js`, `styles/tokens.css`, `styles/app.css`. Vitest tests for: the SSE parser (progress event, keepalive comment, split chunks, bad JSON), error mapping, role gating, hash shortening.
7. `tests/test_frontend_static.py` (design lint, all over `web/index.html` and `web/src/**`, excluding `web/src/fixtures/`): fail on any of: the words kingpin, guilty, arrest, `AI-powered` (case-insensitive); `gradient(`, `backdrop-filter`, `box-shadow`;
   emoji characters; `dangerouslySetInnerHTML`, `innerHTML`, `eval(`, `document.write`, `localStorage`; any `http://` or `https://` other than `127.0.0.1`, `localhost` and `www.w3.org`; and the word list `banned_all` of the steps file.
   Also check `web/package.json`: exact versions only (no `^`, `~`, `*`), and exactly the dependency names of C.1.

### C2. Login, case rail, intake

Create and edit under `web/*`.

- Login page: user name, password, Enter submits, error text, 429 shows the seconds, the password is never stored or logged. On load call `/api/auth/me`; logout button.
- Case rail: list of cases (name, the word "synthetic" for synthetic cases, "analyzed" or "not analyzed", counts of documents, CDR rows, bank rows); selecting opens `#/case/<id>/overview`; "New case" for analysts.
- Intake page `#/case/<id>/intake`: documents (several `.txt` files and/or pasted text with an optional name), CDR upload and bank upload (show the exact required column names from `csv_columns`), per-file result, the row-error table of C.3, the extract job progress bar (SSE with polling fallback),
  an "Analyze" button for analysts with its own job progress, and a table of the case documents (doc id, filename, status, characters, short hash, error code if failed). Text that says typed text only: no scanned images (no OCR).
- Vitest tests: upload-result reducers, row-error table view model, job progress reducer.

### C3. Overview, leads, people

**C3-0. Repair the API fixtures first (the C1 fixtures `node_detail.json`, `edge_detail*.json` are wrong: they hold an error body and empty objects).**
`/graph` returns `{summary, elements: {nodes, edges}}`; every element is `{data: {...}}`; node data has only `ai_confidence`, `centrality_score`, `id`, `isKingpin`, `label`, `type`;
edge data has only `amount`, `count`, `id`, `label` (the relation), `source`, `target`. Edit `scripts/dump_api_shapes.py` (allowed in this step) and regenerate:
(a) `node_detail` = the real `/nodes/<id>` response for the first PERSON node (graph order) whose `fir_evidence` is not empty;
(b) `edge_detail_fir` and `edge_detail_csv` = the real `/edges/<id>` responses for the first edges whose `fir_evidence` (resp. `csv_evidence`) is not empty;
(c) `break_result` = a real break between two persons that gives `finite` true and a non-empty `cut` (try pairs taken from the money-flow leads and then the people list, at most 60 pairs; if none is found use the first pair and write that fact in the worklog);
(d) `graph` = a consistent subgraph: walk the edges in graph order collecting end points until 12 nodes are collected, keep every edge whose two ends are both collected, do NOT apply the generic 5-item cut to it;
(e) write every fixture file as bytes with `\n` line endings (no `\r\n`);
(f) the script must FAIL with a clear message if `node_detail`, `edge_detail_fir` or `edge_detail_csv` is an error body or empty.
Run it with `step_tool.py run` twice and compare the outputs byte for byte. Only then continue with the overview. Write in the worklog that C1 shipped wrong fixtures and why.

**C3-1. Repair the C2 defects found in review (files under `web/*` only; add a vitest test for each point that can be tested as a pure function).**
1. Runaway reload loop: the job-event effect in `Intake.jsx` depends on `onCaseUpdated`, which `App.jsx` re-creates on every render; when a job finishes the stream for a finished job re-sends its final event, `onCaseUpdated` changes App state, the effect restarts, and the cycle repeats forever.
   Keep `onCaseUpdated` in a ref (or memoise it with `useCallback` in `App.jsx`) and clear `activeJob` when the job reaches `done` or `failed` so a stream is never reopened for a finished job. Put the decision "may a stream be opened for this job state" in a pure function and test it.
2. Login message: a failed login must show the server's message (it is returned by `/auth/login`). The fixed text "Invalid or expired token" is only for an expired session on other calls. Fix `mapError` and the test that expects the old behaviour.
3. A 401 on any call clears the token and goes to `#/login` (one place in `client.js`, for example a handler that `App.jsx` registers). List and detail loads must show an error text instead of an empty `catch`.
4. Status bar "Hash": show the first 12 characters of the case fingerprint (`document_hash` from the `/leads` response) once the case is analyzed, and "not analyzed" otherwise. Never show the case id as a hash.
5. Documents table: read `chars` and `error.code` (the field names in `case_detail.json`); refresh the table when an extract job finishes.
6. CSV errors: keep `error_count` from the 422 body and show "N errors, first 50 shown" using that count, not the length of the returned list.
7. Limits panel: no hard-coded list. Show the `limitations` strings of the `/leads` response verbatim plus the fixed sentence "Typed text only: no OCR". For a case that is not analyzed show only that sentence.
8. Polish: case list items reachable by keyboard (use links or buttons); replace `alert()` by an error text; connect labels to inputs (`htmlFor`/`id`); take the modal backdrop colour from a token (no raw `rgba`); clear the cases and the active case from memory on logout.

- Overview `#/case/<id>/overview`: case facts line, the disclaimer (verbatim), a sentence "Ordered by money flow; structural scores are explanation only", the priority-lead table (rank, "tied" marker, name, money-flow score, accounts, role chips, reasons, evidence link),
  a toggle that adds the columns degree, betweenness, eigenvector, composite labelled "explanation only, not a ranking", the mule-lead table and the burner-lead table (id, score, flagged yes/no, reasons, evidence-rows link).
  Show the `limitations` strings in the Limits panel.
- People `#/case/<id>/people`: sortable and filterable table (name, aliases, role chips, owned phones, controlled accounts, documents, "possible same person" entries with their reasons).
- One reusable `Table` component: click a header to sort, stable sort, `aria-sort`, numbers numeric, identifiers as text, empty values last, keyboard operable. Vitest tests for the comparator and the sort state.
- The evidence links must resolve to the routes of C5 (a small stub page is fine until C5).

### C4. Network graph

- `#/case/<id>/graph`: Cytoscape in a React effect (create once, destroy on unmount), elements from `/graph`. Filter bar: node-type toggles (VEHICLE off by default), relation toggles, search (label or id: highlight and centre),
  "leads only" (top 10 priority leads and their neighbours), re-layout, fit, plain-text legend. Label policy and styles of C.2.
- Inspector on the right: a selected node loads `/nodes/<id>`: type, label, roles, aliases, "extractor confidence", documents (links to the evidence viewer), FIR evidence (excerpt with the surface text marked as a separate text span), CSV row references (a button loads `/rows`), neighbours (clickable).
  A selected edge loads `/edges/<id>` with the same evidence blocks.
- Layout of the demo graph (about 425 nodes and 1600 edges) must finish in a few seconds; show the text "Layout running" while it runs.
- Vitest tests (pure functions): filters, label policy, style mapper, selection from URL.

### C5. Evidence viewer

- `#/case/<id>/evidence/doc/<doc_id>`: document list; the text with highlighted spans (a pure function turns the spans into non-overlapping segments; overlaps are shown, not dropped; out-of-range spans are counted and the count is shown);
  header with doc id, filename, `sha256_raw`, `sha256_text`, characters (identifiers in `mono` with copy). `?span=<start>-<end>` scrolls to that span and marks it. Clicking a span shows its entity or relation information. Preserve line breaks and whitespace; Devanagari text must display.
- `#/case/<id>/evidence/rows/<file>?rows=...`: table of the requested raw rows with the 1-based row number, the file name and the file hash, and a message if more than 200 rows were asked for.
- Vitest tests: segmentation (overlap, adjacent, empty, out of range), query parsing.

### C6. Break analysis and timeline

**C6-0. Repairs found in the C3-C5 review (do these first; web/* and `scripts/dump_api_shapes.py` only; one fix per point, a test for each).**
1. Render smoke tests. A blank screen once came from drawing a role-chip object as a React child, and no test could catch it because only pure functions were tested.
   Split each page into a data-loading wrapper and a presentational view that takes data as props (Overview leads view, People view, graph inspector blocks for a node and for an edge, evidence document view, evidence rows view,
   intake documents table and row-error table, login form, the error boundary fallback). Render each view with `renderToString` from `react-dom/server` in a vitest test, using the real fixtures (chips as objects, `node_detail`, `edge_detail_fir`, `edge_detail_csv`,
   `document`, `rows`, `case_detail`). Any exception fails the test. Change the vitest `include` in `web/vite.config.js` to `src/**/*.test.{js,jsx}`. Stub `window` and `sessionStorage` inside the tests if a view needs them; do not add packages.
2. A pure helper `chipLabel(chip)` (object with `chip`, plain string, missing value) used by Overview and People, with a test for each case.
3. Label policy: `getLabelVisibility` and its tests exist but `Graph.jsx` does not use them. Use it for real: labels of the selected node, its neighbours and the top 10 priority leads are always shown, all labels are shown when 60 or fewer nodes are visible,
   all others follow the zoom rule. Apply it with Cytoscape classes that are updated when the selection or the filters change. A vitest test must cover the neighbour case.
4. Colours: no raw hex or `rgb()` or `rgba()` anywhere in `web/src` except `styles/tokens.css`. Cytoscape styles read the CSS variables with `getComputedStyle(document.documentElement)`. Add a vitest test that scans the source files (not the fixtures, not the tests) for those patterns.
5. Edge width comes from `count` only (log scale, 1 to 6 px); money amounts are shown in the inspector only. No animation anywhere: replace `cy.animate` by instant centring. Test the width helper.
6. `scripts/dump_api_shapes.py` reads the leads key `priority_leads`; the real key is `money_flow`. Fix it, run the script twice with `step_tool.py run`, compare the outputs byte for byte, and keep the fixtures valid.

- Break `#/case/<id>/break`: analysts choose group A and group B from the people list (filter box, counts, at most 200 each, no overlap; server errors are shown). Result: finite or not, size, the persons in the cut (name and id), `direct_link`,
  the unowned bridging phones as "phones with no stated owner: who holds this number?", the server `note` and `disclaimer` verbatim. If there is no finite cut or the cut is empty show: "No observed link between the groups on the call layer. This does not mean the groups are unconnected."
  Button "Show on graph" opens the graph page with the cut persons highlighted (URL state). Viewers see the text "Requires the analyst role".
- Timeline `#/case/<id>/timeline`: day/hour toggle, two hand-written SVG bar charts (calls, transfers) with axis labels and exact counts on focus, a first-seen table. No chart library, no animation.
- Vitest tests: group validation, break view model, timeline scale and bucketing helpers.

### C7. Polish, layout check, docs

If the file `scratch/visual_fixes.txt` exists when this step begins, its numbered items come from the reviewer's look at the screenshots and are part of this step (same rules: `web/*` only, one fix per point). Write in the worklog that you read it and which items you did.

- Empty, loading and error states on every page; visible keyboard focus; a 404 page; page titles; the Limits panel on every case page; status bar complete (case id, short fingerprint with copy, user, role).
- Layout check at 1366x768: if you have a browser tool, start the backend on a temp runtime with the demo case and the dev server, open every page and write in the worklog: any horizontal page scroll, clipped or overlapping text, table overflow.
  If you have no browser tool, write that in the worklog. Stop both servers afterwards. The user checks screenshots.
- `docs/web/RUNNING_WEB.md` (facts only): start the backend, load the demo case, start the dev server, build, test, the port numbers, and the fact that the app needs the backend running.

### C8. Chunk end

No new code. Do: (1) `run` the whole Python suite once and `scripts/web_check.py build`, `test`, `size`; (2) write `runbook_logs/C/SUMMARY_FOR_USER.txt` (at least 800 characters) with the headings of the A11 summary plus `LIMITS TO STATE` containing the limits of C.6 item 1,
read from `docs/api/CHUNK_A_CORRECTIONS.md`, and `PAGES` (each page and what it shows); list under DEVIATIONS the 50 ms `time.sleep` that C0 added at the start of the analyze job in `kavach_api/app.py` to stabilise a timing-dependent frozen test (state that the frozen test still depends on timing), the C1 fixture defect and its repair in C3, and any other deviation; (3) `gate`, `commit`, then `step_tool.py bundle --chunk C` and print the path. STOP.

## C.6 Text for `docs/api/CHUNK_A_CORRECTIONS.md` (copy exactly)

```
CHUNK A: CORRECTIONS TO THE SUMMARY OF CHUNK A
Written after an independent review of the chunk A bundle. The file runbook_logs/A/SUMMARY_FOR_USER.txt was committed unchanged in commit 9d6b9c0ff4.

1. LIMITS TO STATE are incomplete in that summary. The limits that apply: relation extraction from FIR text measured F1 0.32 on an independent held-out set;
   identifiers (phone, Aadhaar, PAN, UPI, vehicle) were strong; IFSC codes are not extracted; there is no OCR (typed text only); CDR and bank CSV files must use the exact
   column names; all tuning data was synthetic; the 0.70 chip threshold was chosen after looking at one case and is labelled not evaluated; break results ignore
   unobserved links; the audit hash chain is unkeyed (a person with file access can rewrite it, and removal of the last entries is not detectable); the login limiter
   counts failures per user name; file permissions on the secret key are not enforced on Windows; the live event-stream keepalive was not tested against a running server.

2. FAILURES, step A2: the gate first failed because untracked files from outside the step (a helper folder the user had placed inside the repository) were seen as changes.
   The step snapshot file was edited to include them. This edit was not recorded in the worklog at the time.

3. FAILURES, step A7: the HTTP tests hung repeatedly inside the AG runner (about twenty killed probe commands) before they passed when run normally.

4. FAILURES, step A10: gate attempt 1 failed the banned-text scan (a test file contained a user-folder path fragment). It was fixed once.

5. FAILURES, step A11: gate attempt 1 failed because pytest collected a scratch test file (scratch/test_gap_preview.py) that crashed while reading a file with the default
   Windows encoding, so zero tests ran. An earlier gate, started from an interrupted AG session, ran for about eleven hours without a result; the cause was not established.
   The gate was run again from a user terminal after the scratch test file was moved out of the repository.

6. DEVIATIONS missing from that summary: the runtime layout (users.json, secret.key and audit.log are in the runtime directory itself, not in auth/ and audit/);
   two extra routes, /api/cases/{id}/files/cdr and /files/bank; the fix passes F1 to F11 (step A7) and G1, G3 to G8 (step A10), with tests in tests/test_api_http_read.py,
   tests/test_api_security_http.py and tests/test_api_demo_e2e_full.py; the A9 end-to-end test was thinner than the A9 text and was supplemented in A10; two A7 regression
   tests (direct_link and the cache counter) were weak and were replaced in A10.

7. Follow-ups found in that review (path-traversal test assertions that could not fail, unknown-route error format, a before/after repository check, a half-loaded demo
   case after a failed load, a timing-dependent concurrency test) are handled in step C0 of chunk C.
```
