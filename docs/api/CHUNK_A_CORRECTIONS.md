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
