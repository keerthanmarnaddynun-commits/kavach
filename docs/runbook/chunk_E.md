# CHUNK E: small fixes after the chunk D review

Read `docs/runbook/RULES.md` and `docs/runbook/chunk_C.md` sections C.1 to C.4 first (all still apply). Limits per step: `docs/runbook/chunk_E.steps.json`. Work branch: `phase-d-ag`. No new packages. `web/package.json` is never edited.

## E.0 Why this chunk exists

1. In step D2 the first full Python run failed once: `tests/test_api_security_http.py::test_g5_concurrency_audit_duplicate_checks` (raw log `runbook_logs/D/raw/D2_01_python_suite.txt`).
   Cause in the traceback: on Windows `os.replace(temp, target)` in `kavach_api/jobs.py` (`_atomic_write_json`) raised `PermissionError: [WinError 5]` while another thread had the target file open for reading (`JobStore.get` called by the test's polling loop). The worker thread died and the job ended `failed`.
   The same replace pattern exists in `kavach_api/storage.py` (JSON and bytes writers) and `kavach_api/security.py` (user store and secret file). The D2 worklog did not mention this failure; E0 must record it.
2. The dossier shows, per priority lead, only accounts and paise flow as "evidence". The leads response has no text spans. The people response has `document_references` (FIR ids that name the person).
3. The dossier hash table prints the fixed names `cdr.csv` and `bank.csv`; the API does not record the uploaded names of the CSV files.

## E.1 Steps

### E0. Retry on replace (Windows file lock), with tests
Create `kavach_api/atomic.py` and `tests/test_api_atomic.py`. Edit `kavach_api/jobs.py`, `kavach_api/storage.py`, `kavach_api/security.py` (only the replace calls). Do not edit existing tests.
- `atomic.replace_with_retry(src, dst, attempts=20, delay=0.01)`: calls `os.replace(src, dst)` (look the name up as `os.replace` at call time so tests can patch it); on `PermissionError` waits `delay` seconds and tries again, up to `attempts` calls in total; after the last failure it re-raises the original error. Retry ONLY `PermissionError`; other errors propagate at once. Library code uses `logging`, never `print`; log one debug line per retry (no paths from user input beyond the file name).
- Use it at every `os.replace` of `jobs.py`, `storage.py` (JSON and bytes writers) and `security.py` (both places). The temp-file clean-up in the `finally` blocks stays.
- Tests (new file only, temp directories, no sleeps longer than 0.05 s in total per test): (a) patched `os.replace` raising `PermissionError` twice then working: the target holds the new content, exactly 3 calls; (b) always raising: error re-raised after exactly `attempts` calls and no `.tmp_` file is left in the folder (go through `jobs._atomic_write_json`); (c) `OSError` that is not a `PermissionError` is raised at once (1 call); (d) stress: one thread calls `JobStore.update` 300 times on one job while another thread calls `JobStore.get` for the same job in a loop until the writer is done; no exception in either thread and the last read equals the last write (a real file test; on Linux it cannot fail, on Windows it is the case that failed in D2); (e) the same for `storage` JSON write vs read of one file.
- Worklog (required): quote the D2_01 failure (test name, the `PermissionError` line, the log file name) and say that D2 did not log it.
- Run the three test files that touch these writers once more after the change (`tests/test_api_jobs.py`, `tests/test_api_settings_storage.py`, `tests/test_api_security.py`) with `step_tool.py run`. Then the gate runs the whole suite. If any existing test fails, STOP and hold.

### E1. Dossier: FIR documents per lead, honest CSV file labels
Edit under `web/*` and `docs/web/DOSSIER.md` (create nothing new except tests inside existing test files). The loader in `web/src/pages/Dossier.jsx` also fetches `/api/cases/{id}/people` (existing client; error text on failure like the other calls).
- `buildDossier` gets a new optional input `people` (the people response, a list). For each priority lead find the person with the same `person_id`; the lead gets `firDocuments`: the first 10 ids of `document_references` (the order the server sends) and `firDocumentTotal` (count). If the person is not found or `people` is missing: empty list, total 0. Do not sort.
- In the printed evidence column of each priority lead add a line "FIR documents naming this person: FIR_05, FIR_07, ... (N total)" before the accounts/paise text, or "none recorded" when empty. Never call this a span or a proof; it only lists the documents.
- The CDR and bank rows of the hash table show the file label "uploaded file name not recorded" instead of `cdr.csv`/`bank.csv` (keep the row title "CDR" / "Bank Transactions"). Certificate item 2 stays as it is.
- Update `web/src/lib/dossier.test.js` and the dossier SSR test in `web/src/pages/views.test.jsx` (real fixtures: `people.json`): documents listed for a known person in the same order as the fixture; at most 10; total equals the full length; missing person -> empty; the rendered page contains "FIR documents naming this person"; the hash table no longer contains the text `cdr.csv`.
- Update `docs/web/DOSSIER.md` (facts only) to match; its endpoint list gets `GET /api/cases/{case_id}/people`. Static lint stays green. Optional preview PDF in `scratch/` as in D1 (not committed); if you have no browser tool say so.

### E2. Chunk end
No new code. (1) `run` the whole Python suite once and `scripts/web_check.py` build, test, size. (2) Write `runbook_logs/E/SUMMARY_FOR_USER.txt` (at least 600 characters) with the headings STEPS, TEST COUNTS, DEVIATIONS, FAILURES AND WHAT YOU DID (every failed run or gate attempt, with the raw file name; every commit retry), THINGS I COULD NOT CHECK, LIMITS TO STATE (include: the lead evidence column lists documents and accounts, not text spans; the retry fixes the observed Windows failure but a lock held longer than the retry window still fails), QUESTIONS FOR THE USER. Do not use the words verified, confirmed, audited. (3) `gate`, `commit`, then `step_tool.py bundle --chunk E` and print the path. STOP.
