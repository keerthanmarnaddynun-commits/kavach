#!/usr/bin/env python3
"""Runbook step tool (standard library only).

Purpose: make a long, multi-step build resumable and checkable. It does not write
project code. It records progress, runs the gate for a step, stages ONLY the files
a step is allowed to touch, commits, and pushes to the work branch.

Run it with the project virtual environment's python, from the repository root:

  python scripts/runbook/step_tool.py status  --chunk A
  python scripts/runbook/step_tool.py begin   --chunk A A3
  python scripts/runbook/step_tool.py run     --chunk A --name unit A3 -- PY -m pytest -q tests/test_x.py
  python scripts/runbook/step_tool.py worklog --chunk A A3 "decision or observation"
  python scripts/runbook/step_tool.py gate    --chunk A A3
  python scripts/runbook/step_tool.py commit  --chunk A A3
  python scripts/runbook/step_tool.py hold    --chunk A A3 "reason"
  python scripts/runbook/step_tool.py bundle  --chunk A

User-only commands (the AI tool must never run these): release, unlock.

Exit codes: 0 ok, 1 check failed, 2 usage or precondition error, 3 attempt limit reached.
In a command line the token PY stands for the python that runs this tool.
"""
import argparse
import fnmatch
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(os.environ.get("KAVACH_RUNBOOK_ROOT") or Path(__file__).resolve().parents[2]).resolve()
INFRA_PREFIXES = ("runbook_state/", "runbook_logs/")
RUNTIME = ROOT / "runtime" / "runbook"
TEXT_EXT = {".py", ".md", ".txt", ".json", ".yml", ".yaml", ".toml", ".cfg", ".ini",
            ".js", ".jsx", ".ts", ".tsx", ".css", ".html"}


class ToolError(Exception):
    def __init__(self, message, code=2):
        super().__init__(message)
        self.code = code


# ----------------------------------------------------------------------------- helpers
def now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, indent=2, sort_keys=True, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


def read_json(path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def git(*args, check=True):
    r = None
    for _attempt in range(8):
        r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if r.returncode != 0 and "index.lock" in (r.stderr or ""):
            time.sleep(1.0)  # another process (an editor or a status poller) holds the lock; wait and retry
            continue
        break
    if check and r.returncode != 0:
        raise ToolError("git %s failed: %s" % (" ".join(args), (r.stderr or r.stdout).strip()))
    return r


def is_noise(path):
    return ("/__pycache__/" in "/" + path) or path.endswith(".pyc") or path.startswith(".pytest_cache/")


def porcelain():
    """Return list of (xy, path) for the working tree (all untracked files listed)."""
    out = git("status", "--porcelain=v1", "--untracked-files=all", "-z").stdout
    parts = out.split("\0")
    entries, i = [], 0
    while i < len(parts):
        p = parts[i]
        i += 1
        if not p:
            continue
        xy, path = p[:2], p[3:]
        if xy[0] in "RC":
            i += 1  # skip original path
        if not is_noise(path):
            entries.append((xy, path))
    return entries


def is_infra(path):
    return path.startswith(INFRA_PREFIXES)


def match(path, patterns):
    return any(fnmatch.fnmatchcase(path, pat) for pat in patterns)


def py_argv(argv):
    return [sys.executable if tok == "PY" else tok for tok in argv]


# ----------------------------------------------------------------------------- config / state
def steps_path(chunk):
    return ROOT / "docs" / "runbook" / ("chunk_%s.steps.json" % chunk)


def progress_path(chunk):
    return ROOT / "runbook_state" / ("PROGRESS_%s.json" % chunk)


def log_dir(chunk):
    return ROOT / "runbook_logs" / chunk


def load_cfg(chunk):
    cfg = read_json(steps_path(chunk))
    if cfg is None:
        raise ToolError("steps file not found: %s" % steps_path(chunk))
    return cfg


def load_prog(chunk):
    return read_json(progress_path(chunk), {"chunk": chunk, "baseline_tests": 0, "steps": {}})


def save_prog(chunk, prog):
    write_json(progress_path(chunk), prog)


def find_step(cfg, step_id):
    for i, s in enumerate(cfg["steps"]):
        if s["id"] == step_id:
            return i, s
    raise ToolError("unknown step id: %s" % step_id)


def step_state(prog, step_id):
    return prog["steps"].setdefault(step_id, {"status": "pending", "attempts": 0})


def append_worklog(chunk, step_id, text):
    d = log_dir(chunk)
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "worklog.txt", "a", encoding="utf-8", newline="\n") as f:
        for line in str(text).splitlines() or [""]:
            f.write("%s [%s] %s\n" % (now(), step_id, line))


def save_raw(chunk, step_id, name, text):
    d = log_dir(chunk) / "raw"
    d.mkdir(parents=True, exist_ok=True)
    seq = len([p for p in d.iterdir() if p.name.startswith(step_id + "_")]) + 1
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", name)[:60] or "cmd"
    p = d / ("%s_%02d_%s.txt" % (step_id, seq, safe))
    data = text.encode("utf-8", errors="replace")
    with open(p, "wb") as f:
        f.write(data)
    with open(d / "SHA256SUMS.txt", "a", encoding="utf-8", newline="\n") as f:
        f.write("%s  %s\n" % (sha256_bytes(data), p.name))
    return p


def execute(argv, env_extra=None):
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if env_extra:
        env.update(env_extra)
    t0 = time.time()
    r = subprocess.run(py_argv(argv), cwd=ROOT, capture_output=True, env=env)
    out = (r.stdout or b"").decode("utf-8", errors="replace") + (r.stderr or b"").decode("utf-8", errors="replace")
    return r.returncode, out, time.time() - t0


def parse_passed(text):
    m = re.findall(r"(\d+) passed", text)
    return int(m[-1]) if m else 0


# ----------------------------------------------------------------------------- commands
def cmd_status(a):
    cfg, prog = load_cfg(a.chunk), load_prog(a.chunk)
    print("chunk %s  branch %s  baseline tests %s" % (a.chunk, cfg["branch"], prog.get("baseline_tests", 0)))
    nxt = None
    for s in cfg["steps"]:
        st = prog["steps"].get(s["id"], {"status": "pending", "attempts": 0})
        if nxt is None and st["status"] != "done":
            nxt = s["id"]
        print("  %-5s %-8s attempts=%s commit=%s pushed=%s  %s" % (
            s["id"], st["status"], st.get("attempts", 0), (st.get("commit") or "-")[:10],
            st.get("pushed", "-"), s["title"]))
    print("NEXT: %s" % (nxt or "none (chunk complete)"))
    return 0


def cmd_begin(a):
    cfg, prog = load_cfg(a.chunk), load_prog(a.chunk)
    idx, step = find_step(cfg, a.step)
    st = step_state(prog, a.step)
    maxa = cfg["global"].get("max_attempts", 2)
    if st["status"] == "done":
        raise ToolError("step %s is already done" % a.step)
    if st["status"] == "held":
        raise ToolError("step %s is on HOLD: stop and wait for the user (%s)" % (a.step, st.get("hold_reason", "")))
    for prev in cfg["steps"][:idx]:
        if step_state(prog, prev["id"])["status"] != "done":
            raise ToolError("previous step %s is not done; steps must run in order" % prev["id"])
    if st.get("attempts", 0) >= maxa:
        raise ToolError("attempt limit reached for %s: STOP and report to the user" % a.step, 3)
    if step.get("hold_before") and not (RUNTIME / (a.step + ".released")).exists():
        raise ToolError("step %s needs the user's release before it can start: STOP and wait" % a.step)
    branch = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if branch != cfg["branch"]:
        raise ToolError("wrong branch: on '%s', expected '%s'" % (branch, cfg["branch"]))
    dirty = [p for xy, p in porcelain() if xy != "??" and not is_infra(p)]
    snap_path = RUNTIME / (a.step + ".begin.json")
    resuming = st["status"] in ("begun", "gated") and snap_path.exists()
    if dirty and not resuming:
        raise ToolError("tracked files are modified before the step started: %s" % ", ".join(dirty[:10]))
    if not resuming:
        untracked = sorted(p for xy, p in porcelain() if xy == "??")
        write_json(snap_path, {"head": git("rev-parse", "HEAD").stdout.strip(), "untracked": untracked, "time": now()})
        st["begin_head"] = git("rev-parse", "HEAD").stdout.strip()
    st["status"] = "begun"
    save_prog(a.chunk, prog)
    append_worklog(a.chunk, a.step, "BEGIN%s: %s" % (" (resuming)" if resuming else "", step["title"]))
    print("%s %s: %s" % ("RESUMING" if resuming else "BEGIN", a.step, step["title"]))
    print("allow_create:", json.dumps(step.get("allow_create", [])))
    print("allow_edit  :", json.dumps(step.get("allow_edit", [])))
    print("done_when    :", json.dumps([d["name"] for d in step.get("done_when", [])]))
    print("Read the step text in docs/runbook/chunk_%s.md. Use `run` for every command whose output matters." % a.chunk)
    return 0


def cmd_run(a):
    cfg, prog = load_cfg(a.chunk), load_prog(a.chunk)
    find_step(cfg, a.step)
    cmd = list(a.cmd)
    if not cmd:
        raise ToolError("no command given")
    code, out, secs = execute(cmd)
    header = "COMMAND: %s\nEXIT: %s\nSECONDS: %.1f\n--- OUTPUT ---\n" % (" ".join(cmd), code, secs)
    raw = save_raw(a.chunk, a.step, a.name, header + out)
    append_worklog(a.chunk, a.step, "RUN %s -> exit %s (%s)" % (" ".join(cmd)[:200], code, raw.name))
    tail = out.strip().splitlines()[-40:]
    print("\n".join(tail))
    print("[saved %s, exit %s]" % (raw.relative_to(ROOT).as_posix(), code))
    return code


def cmd_worklog(a):
    cfg = load_cfg(a.chunk)
    find_step(cfg, a.step)
    append_worklog(a.chunk, a.step, a.text)
    print("logged")
    return 0


def scan_banned(paths, cfg):
    g = cfg["global"]
    excl = g.get("scan_exclude", [])
    all_re = re.compile(r"\b(%s)\b" % "|".join(re.escape(w) for w in g.get("banned_all", [])), re.I) if g.get("banned_all") else None
    doc_re = re.compile(r"\b(%s)\b" % "|".join(re.escape(w) for w in g.get("banned_docs", [])), re.I) if g.get("banned_docs") else None
    hits = []
    for p in paths:
        if match(p, excl) or Path(p).suffix.lower() not in TEXT_EXT:
            continue
        fp = ROOT / p
        if not fp.exists():
            continue
        text = fp.read_text(encoding="utf-8", errors="replace")
        is_doc = p.startswith("docs/") and p.endswith(".md")
        for rx in (all_re, doc_re if is_doc else None):
            if rx:
                for m in rx.finditer(text):
                    line = text.count("\n", 0, m.start()) + 1
                    hits.append("%s:%d banned word '%s'" % (p, line, m.group(0)))
        flat = text.replace("\\\\", "\\")
        for frag in g.get("forbidden_path_fragments", []):
            if frag in text or frag in flat:
                hits.append("%s contains machine-specific text '%s'" % (p, frag))
    return hits


def current_changes(snap):
    snap_set = set(snap.get("untracked", []))
    new, modified, problems = [], [], []
    for xy, path in porcelain():
        if is_infra(path):
            continue
        if xy == "??":
            if path not in snap_set:
                new.append(path)
        elif "D" in xy:
            problems.append("deleted file: %s" % path)
        elif "R" in xy or "C" in xy:
            problems.append("renamed or copied file: %s" % path)
        elif xy[0] == "A":
            new.append(path)
        else:
            modified.append(path)
    return sorted(set(new)), sorted(set(modified)), problems


def fingerprint(paths):
    h = hashlib.sha256()
    for p in sorted(paths):
        h.update(("%s\t%s\n" % (p, sha256_file(ROOT / p))).encode("utf-8"))
    return h.hexdigest()


def cmd_gate(a):
    cfg, prog = load_cfg(a.chunk), load_prog(a.chunk)
    idx, step = find_step(cfg, a.step)
    st = step_state(prog, a.step)
    maxa = cfg["global"].get("max_attempts", 2)
    if st["status"] not in ("begun", "gated"):
        raise ToolError("step %s has not been begun (status %s)" % (a.step, st["status"]))
    if st.get("attempts", 0) >= maxa:
        raise ToolError("attempt limit reached for %s: STOP and report to the user" % a.step, 3)
    snap = read_json(RUNTIME / (a.step + ".begin.json"))
    if not snap:
        raise ToolError("begin snapshot missing; run `begin` again")
    results, problems = [], []

    head = git("rev-parse", "HEAD").stdout.strip()
    if head != snap["head"]:
        problems.append("commits were made outside the tool since begin (HEAD moved)")
    new, modified, prob2 = current_changes(snap)
    problems += prob2
    allow_c, allow_e = step.get("allow_create", []), step.get("allow_edit", [])
    for p in new:
        if not match(p, allow_c + allow_e):
            problems.append("new file outside the allow-list: %s" % p)
    for p in modified:
        if not match(p, allow_e):
            problems.append("existing file edited without permission: %s" % p)
    results.append({"check": "allow-list and no deletions", "ok": not problems, "detail": problems[:30]})

    changed = new + modified
    hits = scan_banned(changed, cfg)
    results.append({"check": "banned words / machine paths", "ok": not hits, "detail": hits[:30]})

    bad_py = []
    for p in changed:
        if p.endswith(".py"):
            code, out, _ = execute(["PY", "-m", "py_compile", p])
            if code != 0:
                bad_py.append("%s: %s" % (p, out.strip()[-200:]))
    results.append({"check": "python files compile", "ok": not bad_py, "detail": bad_py})

    test_cmd = step.get("test_command") or cfg["global"].get("test_command") or ["PY", "-m", "pytest", "-q"]
    code, out, secs = execute(test_cmd)
    raw = save_raw(a.chunk, a.step, "gate_full_suite", "COMMAND: %s\nEXIT: %s\n--- OUTPUT ---\n%s" % (" ".join(test_cmd), code, out))
    passed = parse_passed(out)
    baseline = prog.get("baseline_tests", 0)
    ok_tests = code == 0 and passed >= max(baseline, 1) and not re.search(r"\b\d+ (failed|error)", out)
    results.append({"check": "full test suite", "ok": ok_tests,
                    "detail": ["exit %s, passed %s, baseline %s, log %s" % (code, passed, baseline, raw.name)]})

    for d in step.get("done_when", []):
        code, out, secs = execute(d["argv"], d.get("env"))
        raw = save_raw(a.chunk, a.step, "done_" + d["name"], "COMMAND: %s\nEXIT: %s\n--- OUTPUT ---\n%s" % (" ".join(d["argv"]), code, out))
        ok = code == d.get("expect_exit", 0) and (d.get("must_contain") is None or d["must_contain"] in out)
        results.append({"check": "done_when: " + d["name"], "ok": ok,
                        "detail": ["exit %s, log %s" % (code, raw.name)]})

    all_ok = all(r["ok"] for r in results)
    gate = {"step": a.step, "time": now(), "ok": all_ok, "results": results, "tests_passed": passed,
            "files": changed, "fingerprint": fingerprint(changed) if all_ok else None}
    write_json(RUNTIME / (a.step + ".gate.json"), gate)
    write_json(log_dir(a.chunk) / ("gate_%s_attempt%d.json" % (a.step, st.get("attempts", 0) + 1)), gate)
    for r in results:
        print("[%s] %s%s" % ("PASS" if r["ok"] else "FAIL", r["check"],
                             ("  -> " + "; ".join(r["detail"][:5])) if (not r["ok"] and r["detail"]) else ""))
    append_worklog(a.chunk, a.step, "GATE %s: %s" % (a.step, "PASS" if all_ok else "FAIL"))
    if all_ok:
        st["status"] = "gated"
        st["tests_passed"] = passed
        save_prog(a.chunk, prog)
        print("GATE PASSED. Next: commit %s" % a.step)
        return 0
    st["attempts"] = st.get("attempts", 0) + 1
    save_prog(a.chunk, prog)
    if st["attempts"] >= maxa:
        print("ATTEMPT LIMIT REACHED (%d). STOP. Write the problem in the worklog and wait for the user." % st["attempts"])
        append_worklog(a.chunk, a.step, "ATTEMPT LIMIT REACHED; stopped")
        return 3
    print("GATE FAILED (attempt %d of %d). Fix the cause once, then run the gate again." % (st["attempts"], maxa))
    return 1


def cmd_commit(a):
    cfg, prog = load_cfg(a.chunk), load_prog(a.chunk)
    idx, step = find_step(cfg, a.step)
    st = step_state(prog, a.step)
    if st["status"] != "gated":
        raise ToolError("step %s has not passed the gate (status %s)" % (a.step, st["status"]))
    gate = read_json(RUNTIME / (a.step + ".gate.json"))
    snap = read_json(RUNTIME / (a.step + ".begin.json"))
    if not gate or not gate.get("ok"):
        raise ToolError("no passing gate record; run the gate again")
    new, modified, problems = current_changes(snap)
    if problems:
        raise ToolError("problems since the gate: %s" % "; ".join(problems))
    changed = new + modified
    if fingerprint(changed) != gate["fingerprint"]:
        raise ToolError("files changed after the gate passed; run the gate again")
    for p in changed:
        git("add", "--", p)
    for d in ("runbook_logs", "runbook_state"):
        if (ROOT / d).exists():
            git("add", "--", d)
    msg = "%s\n\nRunbook step %s/%s; gate passed; tests passed: %s" % (step["commit_message"], a.chunk, a.step, gate["tests_passed"])
    r = git("commit", "-m", msg, check=False)
    if r.returncode != 0:
        raise ToolError("commit failed: %s" % (r.stderr or r.stdout).strip())
    head = git("rev-parse", "HEAD").stdout.strip()
    pushed = False
    if not a.no_push:
        pr = git("push", "origin", cfg["branch"], check=False)
        pushed = pr.returncode == 0
        if not pushed:
            append_worklog(a.chunk, a.step, "PUSH FAILED: %s" % (pr.stderr or pr.stdout).strip()[:300])
    st.update({"status": "done", "commit": head, "pushed": pushed, "done_at": now()})
    prog["baseline_tests"] = max(prog.get("baseline_tests", 0), gate["tests_passed"])
    save_prog(a.chunk, prog)
    append_worklog(a.chunk, a.step, "COMMIT %s pushed=%s" % (head[:10], pushed))
    nxt = [s["id"] for s in cfg["steps"] if step_state(prog, s["id"])["status"] != "done"]
    print("COMMITTED %s (%s) pushed=%s. Next step: %s" % (a.step, head[:10], pushed, nxt[0] if nxt else "none"))
    if not pushed and not a.no_push:
        print("NOTE: push did not succeed; the commit is local. The user can push later.")
    return 0


def cmd_hold(a):
    cfg, prog = load_cfg(a.chunk), load_prog(a.chunk)
    find_step(cfg, a.step)
    st = step_state(prog, a.step)
    st["status"] = "held"
    st["hold_reason"] = a.reason
    save_prog(a.chunk, prog)
    append_worklog(a.chunk, a.step, "HOLD: %s" % a.reason)
    print("HOLD set for %s. STOP NOW and wait for the user. Do not run any other step." % a.step)
    return 0


def cmd_release(a):
    cfg, prog = load_cfg(a.chunk), load_prog(a.chunk)
    find_step(cfg, a.step)
    st = step_state(prog, a.step)
    RUNTIME.mkdir(parents=True, exist_ok=True)
    (RUNTIME / (a.step + ".released")).write_text(now(), encoding="utf-8")
    if st["status"] == "held":
        st["status"] = "begun" if (RUNTIME / (a.step + ".begin.json")).exists() else "pending"
        st.pop("hold_reason", None)
    save_prog(a.chunk, prog)
    append_worklog(a.chunk, a.step, "RELEASED by the user")
    print("released %s" % a.step)
    return 0


def cmd_unlock(a):
    cfg, prog = load_cfg(a.chunk), load_prog(a.chunk)
    find_step(cfg, a.step)
    st = step_state(prog, a.step)
    st["attempts"] = 0
    save_prog(a.chunk, prog)
    append_worklog(a.chunk, a.step, "ATTEMPTS RESET by the user")
    print("attempts reset for %s" % a.step)
    return 0


def cmd_bundle(a):
    cfg, prog = load_cfg(a.chunk), load_prog(a.chunk)
    out_dir = RUNTIME.parent / "bundles"
    out_dir.mkdir(parents=True, exist_ok=True)
    n = len(list(out_dir.glob("%s_bundle_*.zip" % a.chunk))) + 1
    zpath = out_dir / ("%s_bundle_%02d.zip" % (a.chunk, n))
    first = next((prog["steps"][s["id"]].get("begin_head") for s in cfg["steps"] if prog["steps"].get(s["id"], {}).get("begin_head")), None)
    lines = ["branch: " + git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip(),
             "head: " + git("rev-parse", "HEAD").stdout.strip(),
             "start: %s" % first, ""]
    if first:
        lines += ["--- git log (start..HEAD) ---", git("log", "--oneline", "%s..HEAD" % first, check=False).stdout,
                  "--- git diff --stat (start..HEAD) ---", git("diff", "--stat", "%s..HEAD" % first, check=False).stdout]
    lines += ["--- git status (short) ---", git("status", "--short", check=False).stdout]
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("GIT_SUMMARY.txt", "\n".join(lines))
        for base in (log_dir(a.chunk),):
            if base.exists():
                for p in sorted(base.rglob("*")):
                    if p.is_file():
                        z.write(p, p.relative_to(ROOT).as_posix())
        for p in (progress_path(a.chunk), steps_path(a.chunk)):
            if p.exists():
                z.write(p, p.relative_to(ROOT).as_posix())
        if RUNTIME.exists():
            for p in sorted(RUNTIME.glob("*.gate.json")):
                z.write(p, "gate_records/" + p.name)
    print("bundle written: %s" % zpath)
    return 0


def build_parser():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)

    def add(name, fn, step=True, extra=None):
        sp = sub.add_parser(name)
        sp.add_argument("--chunk", required=True)
        if step:
            sp.add_argument("step")
        if extra:
            extra(sp)
        sp.set_defaults(fn=fn)
        return sp

    add("status", cmd_status, step=False)
    add("begin", cmd_begin)
    add("gate", cmd_gate)
    add("commit", cmd_commit, extra=lambda s: s.add_argument("--no-push", action="store_true"))
    add("hold", cmd_hold, extra=lambda s: s.add_argument("reason"))
    add("release", cmd_release)
    add("unlock", cmd_unlock)
    add("worklog", cmd_worklog, extra=lambda s: s.add_argument("text"))
    add("bundle", cmd_bundle, step=False)

    def run_extra(s):
        s.add_argument("--name", default="cmd")

    add("run", cmd_run, extra=run_extra)
    return p


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    tail = []
    if argv and argv[0] == "run":
        if "--" not in argv:
            print("ERROR: run needs the command after '--', for example: run --chunk A --name unit A3 -- PY -m pytest -q")
            return 2
        cut = argv.index("--")
        argv, tail = argv[:cut], argv[cut + 1:]
    args = build_parser().parse_args(argv)
    args.cmd = tail
    try:
        return args.fn(args)
    except ToolError as e:
        print("ERROR: %s" % e)
        chunk, step = getattr(args, "chunk", None), getattr(args, "step", None)
        if chunk and step and steps_path(chunk).exists():
            try:
                append_worklog(chunk, step, "TOOL ERROR (exit %s): %s" % (e.code, str(e)[:500]))
            except Exception:
                pass
        return e.code


if __name__ == "__main__":
    sys.exit(main())
