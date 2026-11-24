# CHUNK G: graph page defects found in the user's walk-through

Read `docs/runbook/RULES.md` and `docs/runbook/chunk_C.md` sections C.1 to C.4 first. Limits per step: `docs/runbook/chunk_G.steps.json`. Work branch: `phase-d-ag`. No new packages. `web/package.json` is never edited.

## G.0 The two reports (from the user, who runs the app by hand)
1. On the graph page the filter bar says "0 isolated nodes" (case not named; the user works with a case called `Practice` made of one pasted FIR plus the two demo CSV files, and also with the Demo case).
   In the committed screenshot `screenshots/10_graph_default.png` (leads-only view of the demo case) the same text appears and is probably correct there, because leads-only shows only connected nodes. It must be checked, not assumed: is the number right in every view (leads-only on and off, each case)?
2. Clicking a PERSON node only highlights it in blue; the inspector panel on the right does not open or does not show details. (In `screenshots/12_graph_node_selected.png`, taken by an earlier tool run on the demo case, the inspector did open.)

## G.1 Steps

### G0. Diagnose (no source edits; findings only)
Edit nothing under `web/`, `kavach_api/`, `scripts/` or `tests/`. Write `runbook_logs/G/G0_diagnosis.txt` (use `step_tool.py run` with a small command that writes it, or the worklog; one file, at least 600 characters) and a worklog entry.
1. Copy the user's `runtime/` folder to `scratch/runtime_copy/` (never run the server on the original `runtime/`, never touch it). Start the API with `KAVACH_RUNTIME_DIR` pointing at the copy and the dev server (ports 8000 and 5173). Create a diagnosis user inside the copy through `kavach_api.security.UserStore` with `load_settings` for the copy (no token forging, no password reuse); stop both servers at the end.
2. With headless Chrome (a temporary `.mjs` script in `scratch/`, deleted afterwards, as in the earlier screenshot task), for BOTH the case named `Practice` (if it exists in the copy; if not, say so and build an equivalent in the copy: one FIR text `contracts/sample_input.txt`, the two demo CSV files, then analyze) and the Demo case:
   - open the graph page; record the text of the isolated-nodes control and the number of isolated nodes you can compute from the `/graph` response (nodes with no edge) for leads-only on and off;
   - click a PERSON node; record: whether the inspector element exists and is visible, its CSS width/display/collapsed state, the HTTP requests made (URL and status, especially `/api/cases/<id>/nodes/<node_id>`), the response body if it is an error, and every console error or page error.
3. State the root cause for each report with the evidence (file and line in `web/src` or `kavach_api`, and the observed request/response or console text). If a report is not a defect (for example the number is correct), say why with numbers from the response.
4. If the root cause is in `kavach_api/` or in the data (not in `web/`), write it and `hold` G0 (RULES STOP rule 2). If it is in `web/`, continue.

### G1. Fix (web/* only)
Fix THE ROOT CAUSE found in G0, once, for each report that is a defect. Rules: no new packages; keep all design rules of chunk C (palette, no animation, no raw colours); put the decision logic in a pure function and test it; add a render smoke test (`renderToString`, real fixtures) for the case that failed, in the existing view test files.
- Report 2 must be fixed so that after a click on any node type the inspector opens (if collapsed it expands) and shows either the details or a visible error text with the HTTP code (never a silent empty panel).
- Report 1: if the number is wrong in some view, fix it; if it is right, change the text so it cannot be misread (for example "isolated nodes hidden: N (leads-only view hides them)") and show the control only when it is meaningful.
- Re-run the headless check of G0 step 2 for both cases after the fix and log the result (inspector visible, request status 200, no console errors). Save two screenshots (a PERSON node selected in the Practice case and in the Demo case) in `scratch/` only (not committed), and write their file names in the worklog.
Run `scripts/web_check.py` build and test with `step_tool.py run`. If an existing test fails, STOP and hold.

### G2. Chunk end
No new code. (1) `run` the whole Python suite once and `scripts/web_check.py` build, test, size. (2) `runbook_logs/G/SUMMARY_FOR_USER.txt` (at least 600 characters) with the headings STEPS, TEST COUNTS, DEVIATIONS, FAILURES AND WHAT YOU DID (every failed run or gate attempt with the raw file name, every commit retry, any edit of a runtime snapshot file: there must be none), ROOT CAUSES (one paragraph each with the evidence), THINGS I COULD NOT CHECK. Do not use the words verified, confirmed, audited. (3) `gate`, `commit`, `step_tool.py bundle --chunk G`, print the path. STOP.
