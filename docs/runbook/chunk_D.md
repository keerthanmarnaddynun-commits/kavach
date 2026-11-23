# CHUNK D: minimal dossier (print page in `web/`)

Read `docs/runbook/RULES.md` and `docs/runbook/chunk_C.md` sections C.1 to C.4 first (stack, design rules, API facts, rules: all still apply).
The machine-readable limits of each step are in `docs/runbook/chunk_D.steps.json`. Work branch: `phase-d-ag`.

## D.0 What this chunk builds

One new page in the existing web app: `#/case/<id>/dossier`. It is a print-styled summary of the case that the user saves as PDF with the browser's Print command
(Ctrl+P, "Save as PDF"). No PDF library, no new package, no backend change, no file download code. The page is built only from data that existing endpoints return
(`/api/cases/{id}`, `/leads`, `/graph`, `/people`). Nothing is typed by hand: every number, id and hash comes from the API response.

NOT in this chunk: any change to `kavach_api/`, new packages, server-side PDF, signing, a legal opinion. `web/package.json` is never edited.

## D.1 Content of the dossier (in this order; each part is its own `<section>` with a heading)

1. Title block: "Case dossier (draft for review)"; case name, case id, "synthetic" if the case is synthetic; the case fingerprint (the `document_hash` of the `/leads` response, FULL value in mono, wrapped, not shortened);
   generation time (browser time, passed to the view as a prop so tests are deterministic); user name and role. If the case is not analyzed: show only this part, the case facts, the document hash table and the limits, and the sentence "Case not analyzed: no leads or graph summary."
2. The disclaimer string of the `/leads` response, verbatim.
3. Case facts: documents, CDR rows, bank rows (from `/cases/{id}`).
4. Graph summary: total nodes and total edges and the count per node type, computed from `/graph` (`summary` and `elements.nodes[].data.type`); schema version from `summary`.
5. Priority leads (the first 10 items of `money_flow`, in the order the server sends them; never re-sorted): rank, name, person id (mono), money-flow score, accounts, chips (use `chipLabel`), reasons (verbatim),
   evidence references as PLAIN TEXT (a printed page has no links): for FIR evidence "doc id, char span" for each item; for CSV evidence "file, first 10 row numbers, total row count". Line: "Ordered by money flow; structural scores are explanation only".
6. Flagged detector leads: mule accounts and burner phones with `flagged` true (id, score, reasons, evidence rows as text). If none are flagged, the sentence "No flagged items."
7. Hash table (the evidence inventory): one row per document (doc id, file name, `sha256_raw`, `sha256_text`, characters), one row for the CDR file and one for the bank file (name, rows, sha256), and the case fingerprint. Full 64-character hashes in mono, wrapped (CSS `overflow-wrap: anywhere`).
   Under the table: "SHA-256 values were computed by the system when each file was stored. `sha256_raw` is the hash of the uploaded bytes; `sha256_text` is the hash of the stored text."
8. Limits: the `limitations` strings of `/leads` verbatim, plus "Typed text only: no OCR", plus "Same person may appear as several entries (same name in different FIRs, or Hindi and Roman spellings)".
9. Certificate, Part A: DRAFT TEMPLATE (text in D.2). Directly under it, Part B with the sentence "Part B (expert) is not completed by this system."

Print rules (CSS in `web/src/styles/app.css` under `@media print`, colours only through existing CSS variables, no raw colour values): paper A4 portrait (`@page { size: A4; margin: 14mm; }`), hide status bar, case rail, footer, Limits button and the
Print button itself; main area full width, no inner scroll; black text on white; tables `page-break-inside: avoid` per row, heading `break-after: avoid`; each of parts 5, 7 and 9 starts on a new page only if the content does not fit
(use `break-inside: avoid` on the certificate block). Screen view: the same page inside the normal shell, plus a button "Print / Save as PDF" calling `window.print()` and the text "Use Save as PDF in the print dialog."

## D.2 Text of the certificate block (use exactly; the sentences in square brackets become blank lines `________` for the signatory)

```
CERTIFICATE UNDER SECTION 63(4)(c) OF THE BHARATIYA SAKSHYA ADHINIYAM, 2023: PART A (DRAFT TEMPLATE)
This is a draft template produced by KAVACH from recorded values. It is not a signed certificate. The format of the Schedule to the Act governs and the final text must be reviewed by a legal officer before use.

I, [name], [designation], [organisation], state as follows:
1. The electronic records listed in the hash table of this dossier were taken from the KAVACH case named above (case id and fingerprint as printed in the title block).
2. Identification of each record: the file name, the SHA-256 value of the uploaded bytes and the SHA-256 value of the stored text are listed in the hash table. The algorithm used is SHA-256.
3. The system that produced this dossier is the KAVACH application. The stored texts and CSV files are kept exactly as uploaded; the system computes the hash values when the file is stored.
4. Particulars of the computer or device used to produce this printout: [device description, operating system, location].
5. Statement on lawful control and regular use of the device during the relevant period: [to be completed by the signatory].
6. Date and time of this printout: [as printed in the title block].

Place: [place]     Date: [date]     Signature: [signature]
Name and designation: [name and designation]

Hash value (SHA-256) of this case fingerprint: [the full fingerprint value from the title block, filled in by the system]
```
Never write "Section 65B". Never write that the records are authentic, genuine, accurate, proven or admissible. Never use the words verified, confirmed, audited (also in the code and tests).

## D.3 Steps

### D0. Dossier view model (pure functions, tests, no page yet)
Create `web/src/lib/dossier.js` and `web/src/lib/dossier.test.js` (path and name may follow the existing folder layout; if the layout differs, keep the intent and log the choice).
`buildDossier({caseDetail, leads, graph, user, generatedAt})` returns a plain object with one field per part of D.1: `title`, `disclaimer`, `facts`, `graphSummary` (counts per type, sorted by type name), `priorityLeads` (first 10, order untouched),
`detectorLeads` (flagged only, mule and burner), `hashTable` (documents, cdr, bank, fingerprint), `limits`, `certificateText` (D.2 lines with the blanks as the text `________`), `analyzed` (boolean). Helper `formatEvidenceRefs(evidence)` returns an array of plain strings.
First READ the real shapes in `web/src/fixtures/` (case_detail, leads, graph) and in `kavach_api/` (the evidence object of a money-flow lead, the shape of `files` in case_detail). Write the exact field names you found at the top of your worklog entry. Do not guess a field.
Tests (vitest, node, pure): with the real fixtures: ten leads at most and same order as the fixture; counts per type sum to the number of nodes; every hash in the table equals the value in the fixture; full 64-character fingerprint present (no shortening);
a not-analyzed case (leads missing) returns `analyzed` false with no leads; evidence text for a FIR item and a CSV item; certificate text contains "63(4)(c)" and not "65B"; no function reads the clock (time comes in as a parameter).

### D1. Dossier page, route, navigation, print CSS
Create/edit under `web/*`. Add the route `#/case/<id>/dossier` to the hash router and a navigation entry "Dossier" in the case rail (visible to all roles). Split the page as in C6-0: a loading wrapper (fetches `/api/cases/{id}`, `/leads`, `/graph` with the existing client; error text on failure; the existing 401 handling)
and a presentational view that takes the output of `buildDossier` as props. Add a vitest SSR smoke test with `renderToString` for the view using the real fixtures (analyzed and not analyzed). Add the print CSS of D.1.
Static lint must stay green (no raw colours outside `tokens.css`, no banned words, no external URLs). Do not edit `kavach_api/`.
Optional, only if you have a browser tool or headless Chrome: start the backend on a temp runtime with the demo case, open the dossier page at 1366x768 and write the printed-page result into `scratch/dossier_preview.pdf` using Chrome `--print-to-pdf` (not committed); write in the worklog what you could and could not check.
If you have none, write that. Stop all servers afterwards. Do not claim the layout "looks right".

### D2. Chunk end
No new code except `docs/web/DOSSIER.md` (facts only: what the page contains, which endpoints feed it, how to open it and save as PDF, what is not included). Do: (1) `run` the whole Python suite once and `scripts/web_check.py` build, test, size;
(2) write `runbook_logs/D/SUMMARY_FOR_USER.txt` (at least 800 characters) with the headings of the C8 summary: STEPS, TEST COUNTS, DEVIATIONS, FAILURES AND WHAT YOU DID, THINGS I COULD NOT CHECK, QUESTIONS FOR THE USER, LIMITS TO STATE (copy the items of `docs/api/CHUNK_A_CORRECTIONS.md` item 1 and the chunk C limits from `runbook_logs/C/SUMMARY_FOR_USER.txt`; add: the certificate is a draft template, not legal advice; the dossier is only as complete as the API data).
FAILURES must list EVERY failed gate attempt (read the count from the `gate_*.json` files) and every commit retry, in plain words. Do not write that a step "passed cleanly" unless the gate files show one attempt. Do not use the words verified, confirmed, audited.
(3) `gate`, `commit`, then `step_tool.py bundle --chunk D` and print the path. STOP.
