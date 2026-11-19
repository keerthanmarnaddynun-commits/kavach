# KAVACH delivery runbook: RULES (read this fully at the start of every session)

You are the AI coding tool ("AG"). You build the KAVACH (CRIMI-NEX) delivery in CHUNKS.
A chunk is a list of numbered STEPS. The human-readable text of a chunk is
`docs/runbook/chunk_<X>.md`. The machine-readable limits of each step (which files you may
create or edit, which checks must pass) are in `docs/runbook/chunk_<X>.steps.json`.
A tool, `scripts/runbook/step_tool.py`, enforces the order, the file limits, the tests, the
logging, the commits and the pushes. You do not need to remember anything between sessions:
the tool and the log files remember for you.

These rules exist because of mistakes made in earlier work (typed numbers, self-declared
"verified" results, overwritten outputs, fix loops, scratch scripts left in the project).
Follow them literally. When a rule and your own judgment disagree, follow the rule and write
the disagreement in the worklog.

------------------------------------------------------------------------------------------
## 1. Start of every session (also after a crash or a lost connection)

1. Read this file completely, then `docs/runbook/chunk_<X>.md`.
2. Run:  `.\.venv311\Scripts\python.exe scripts\runbook\step_tool.py status --chunk <X>`
3. Continue with the step shown as NEXT.
   - If a step shows `begun`, run `begin` for it again (it RESUMES; it does not reset). Read the end of
     `runbook_logs/<X>/worklog.txt` to see what was already done, then continue.
   - Never redo a step that shows `done`.
   - If a step shows `held`, STOP: the user must release it. Do not work around it.

## 2. The loop for each step (always the same)

```
step_tool.py begin   --chunk <X> <STEP>        # prints the step contract (allowed files, checks)
   ... read the step text in chunk_<X>.md, then implement ...
step_tool.py run     --chunk <X> --name <label> <STEP> -- PY <command...>     # for every command whose output matters
step_tool.py worklog --chunk <X> <STEP> "what you decided / noticed / could not do"
step_tool.py gate    --chunk <X> <STEP>        # runs all checks; saves raw logs
step_tool.py commit  --chunk <X> <STEP>        # stages ONLY the step's files, commits, pushes the work branch
```

- In every command, `PY` means "the python that runs the tool". Always start the tool itself with
  `.\.venv311\Scripts\python.exe` (never plain `python`; plain python is 3.13 and has no torch).
- Put the options BEFORE the step id and put the command after `--`, for example:
  `.\.venv311\Scripts\python.exe scripts\runbook\step_tool.py run --chunk A --name unit A3 -- PY -m pytest -q tests/test_api_ingest.py`
- Use `run` for: unit tests of the step, any check you will quote later, any command that fails.
  The tool saves the raw output to `runbook_logs/<X>/raw/` with a hash. Do not paste results from memory.
- `gate` fails -> read the failure, fix THE CAUSE ONCE, run `gate` again. You have 2 attempts per step.
  After the second failure the tool locks the step: write the problem in the worklog and STOP.
- After `commit` succeeds, immediately `begin` the next step. Continue until a STOP rule applies or the chunk ends.

## 3. STOP rules (write the reason in the worklog, then end your turn with a short message)

STOP and do not continue if any of these happens:
1. The gate fails twice for the same step (the tool tells you).
2. You think you must edit a file that is not in the step's `allow_edit` list, or create a file that is not in `allow_create`.
3. A package must be installed or a version pinned differently. (Never install anything yourself. Write the exact `pip install` line
   you would need in the worklog, run `hold` for the step, and stop.)
4. A result contradicts the step text (a count, a hash, a schema rule, a test that should pass but cannot).
5. A contract or schema would force the API to state something this project does not claim (see section 6, "claims").
6. A command would delete, move, rename or overwrite any committed file or any result folder.
7. You are unsure what a requirement means. Do not guess and do not pick the easy reading: log the question and `hold`.
8. The step is marked `hold_before` and the user has not released it (the tool refuses to begin it).
9. You find a defect in a FROZEN area (section 5). Log it with evidence and continue only if the step does not depend on it.
10. Anything surprising: a test that was passing starts failing without a change of yours, files you did not create appear in
    `git status`, the branch is not the work branch.

To stop with a hold:  `step_tool.py hold --chunk <X> <STEP> "reason"`  and then end your turn.
Never run `release` or `unlock`. Those commands belong to the user only.

## 4. Things you must never do

- Never delete, move, rename or overwrite an existing file or folder. (Create new files; edit only what the step allows.)
- Never use `git add -A`, `git add .`, `git commit -a`, `git reset`, `git checkout -- <file>` on files you did not create,
  `git stash`, `git rebase`, `git push --force`, or any command that rewrites history. Only the tool commits and pushes.
- Never commit to `main` or to `phase-a-ag`. The work branch is named in the steps file.
- Never install packages, upgrade packages, or change `requirements.txt` unless the step explicitly allows it and the user approved.
- Never type a result number into a document by hand. Never write the words "verified", "confirmed" or "audited" about your own work.
- Never write scratch, audit, fix, apply or check scripts to patch documents. Scratch files go in the git-ignored folder `scratch/`
  (never in the project) and are never committed.
- Never read, copy or paste the answer keys or `truth.json` into any module under `kavach_api/`, `case_graph/`, `case_analytics/`
  or `case_detectors/`. (Evaluation scripts may read them; the product code may not.)
- Never put machine-specific paths (your user name, drive letters, home folders) in code, docs, tests or JSON.
- Never use the words: optimal, sweet spot, robust, decisively, catastrophic, proves, guarantees, perfect, excellent,
  state-of-the-art in code, comments, docs or printed output. The gate scans for them.
- Never start a long background process and leave it running; never leave a server running at the end of a step.

## 5. Frozen areas (read-only; import from them, do not edit)

`ai_pipeline/` (the extractor), `contracts/`, `case_graph/`, `case_analytics/`, `case_detectors/`, `case_simulation/`,
`llm_firs/`, `config/`, `scoring.py`, `scripts/` that already exist, `tests/` that already exist, everything under `data/` and
`results/`, the legacy folders `backend/` and `frontend/` and the old `extractor.py`, `regex_engine.py`, `model_engine.py`.
If you believe something frozen is wrong, log it (with the command output that shows it) and continue without changing it.

## 6. Project decisions that override any older plan or document

These come from measured results. Do not "improve" them.

- **Wording.** The system produces LEADS for an investigator. It is decision support. It never says a person "is" a kingpin, "is guilty"
  or "should be arrested". Use: lead, priority lead, chip, unidentified, unobserved. Every leads response carries a fixed disclaimer
  string (defined in the chunk text).
- **Ranking.** The priority-lead ordering of persons is by MONEY FLOW (financial control through accounts the documents say the person controls).
  The structural scores (degree, betweenness, eigenvector, composite) are EXPLANATION only; never use them to order the main list and never
  present them as a probability. (Measured result: centrality alone ranked the planted kingpins low; the money-flow ordering did not.)
- **Anonymous nodes.** CDR and bank files carry no names. A phone or account has an owner only if an FIR text states ownership or control.
  Everything else is shown as unidentified. Never guess owners.
- **Person merging.** Use the existing frozen merge rules. Never merge two people on a shared phone alone.
- **Courier break.** The "network break" runs on the CALL layer only, between two groups the analyst chooses. Terminals (group members)
  are never cut. A result of "no finite cut" or an empty cut means "no observed link", never "the groups are unconnected".
  Every break response carries the note that unobserved links are ignored.
- **Unowned bridging phones** are leads ("who holds this number?"), not findings.
- **Mule and burner leads** come from the frozen detectors with the thresholds in `config/detector_defaults.json`. Their reasons and
  evidence rows are always returned. The 0.70 chip threshold was chosen after looking at one case and is labelled "not evaluated".
- **Limits to state next to results** (also returned in API responses where the chunk text says so): relation extraction from FIR text
  measured F1 0.32 on an independent held-out set; identifiers (phone, Aadhaar, PAN, UPI, vehicle) were strong; IFSC codes are not
  extracted; no OCR (typed text only); CDR and bank CSV must use the exact column names in the chunk text; all tuning data was synthetic.
- **Legal wording** for later chunks: Bharatiya Sakshya Adhiniyam 2023, Section 63(4)(c) certificate with hash (never "Section 65B").
- **No Neo4j.** Graphs live in memory and in JSON files for now.
- **Extractor is frozen.** The API wraps `ai_pipeline.pipeline` as it is. Offline model files are used (`HF_HUB_OFFLINE=1`).

## 7. Logging duties

- The tool logs begin, run, gate and commit automatically. YOU must add worklog lines (`worklog`) for: every decision you made where the
  step text allowed a choice; every deviation from the step text (and why); every surprising observation; every command that failed
  and what you did about it; anything you could not check.
- Do not summarise results from memory. When you need a number, read it from the saved raw log or the output file and quote the file name.
- Never edit or delete anything in `runbook_logs/` or `runbook_state/` by hand. They are append-only records.
- At the end of each chunk you write `runbook_logs/<X>/SUMMARY_FOR_USER.txt` (format in the chunk text). Do not claim more than the logs show.
  List what you did not check.

## 8. Honest-results rules (from the lessons note of an earlier project)

R1. Raw output files are the only source of truth. Every number in a document is produced by a script from a saved output file.
R2. You may not label your own work "verified". The user and a separate checker compare the documents with the raw files.
R3. Each run writes to a NEW folder (date and id) and never reuses a file name for different content; outputs are read-only afterwards
    and get a SHA-256 list. (Applies to any experiment or evaluation output; the runbook tool already does this for its logs.)
R4. No fix loops: if a number or text is wrong, fix the generating code once, regenerate once. Do not patch generated text.
R5. Name inputs by version; two different contents never share a name.
R6. Every metric has one glossary line (formula, numerator, denominator).
R7. State anything structural, tied, noisy or uncounted next to the number it affects.
R8. No overclaim words (list in section 4). Printed output and comments must not state conclusions the code cannot support.
R9. README and docs list only facts that can be checked: exact script names, how to run them, inputs, outputs. No file counts, no "zero changes".
R10. Keep experiment and product scripts in the project; scratch only in `scratch/`.

## 9. Code rules

- Python 3.11, standard library first. Type hints on public functions. Short docstrings that say what, not why-it-is-good.
- Use `pathlib`. Open every text file with `encoding="utf-8"`. WRITE DOCUMENT TEXT AND CSV UPLOADS AS BYTES (`write_bytes`) so that
  Windows does not change line endings: character offsets of evidence spans depend on the exact characters.
- JSON files: write atomically (write a temp file in the same folder, then `os.replace`). Sorted keys and indent 2 for files that are committed.
  Runtime JSON may use compact form.
- No global mutable state without a lock. Per-case writes are serialised with a per-case lock.
- Library code uses the `logging` module, never `print`. Never log passwords, tokens, secrets or full document text.
- Never build a path from user input without validating it first (see the chunk text for the id and filename rules).
- Never use `pickle`, `eval`, `exec`, or shell=True with user data.
- Tests: small, deterministic, no network, no real model unless the step says so (and then only when the environment variable named in the
  step is set). Use temporary directories for every test that writes. Tests never write into the repository tree.
- Time stamps are allowed in runtime data (jobs, audit log). They are NOT allowed in committed result files.
- Randomness only from `secrets` (security) or a seeded `random.Random` / numpy RandomState (anything reproducible).

## 10. Git rules (enforced by the tool)

- Work branch only (named in the steps file). One commit per step, made by the tool. Commit messages come from the steps file.
- The tool stages exactly the files the step created or edited (plus `runbook_logs/` and `runbook_state/`). It refuses to commit if a file
  outside the allow-list changed, if anything was deleted, if the test count dropped, or if files changed after the gate passed.
- The tool pushes the work branch after each commit. If a push fails, the commit stays local and the failure is logged: do not retry in a loop,
  note it in the worklog and continue.

## 11. What to say when you stop or finish

Keep the final message under 15 lines: the step id you stopped at, the status line from `status`, the exact reason, and the file in
`runbook_logs/` where the details are. Do not paste long logs into the chat; the files are the record.
