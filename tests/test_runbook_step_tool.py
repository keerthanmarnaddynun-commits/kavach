"""Tests for scripts/runbook/step_tool.py using throw-away git repositories."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1] / "scripts" / "runbook" / "step_tool.py"

CFG = {
    "chunk": "T",
    "branch": "phase-test",
    "global": {
        "max_attempts": 2,
        "test_command": ["PY", "-c", "print('5 passed in 0.01s')"],
        "banned_all": ["optimal", "proves"],
        "banned_docs": ["verified"],
        "scan_exclude": ["docs/runbook/*", "runbook_logs/*", "runbook_state/*"],
        "forbidden_path_fragments": ["C:\\Users", "/home/"],
    },
    "steps": [
        {"id": "T0", "title": "first", "allow_create": ["pkg/*", "tests/test_t0.py"], "allow_edit": [],
         "done_when": [{"name": "ok", "argv": ["PY", "-c", "print('fine')"], "must_contain": "fine"}],
         "commit_message": "T0 done"},
        {"id": "T1", "title": "second", "allow_create": ["pkg2/*"], "allow_edit": ["README.md"],
         "test_command": ["PY", "-c", "print('3 passed in 0.01s')"], "done_when": [], "commit_message": "T1 done"},
        {"id": "T2", "title": "needs release", "hold_before": True, "allow_create": ["pkg3/*"], "allow_edit": [],
         "done_when": [], "commit_message": "T2 done"},
    ],
}


class StepToolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.env = dict(os.environ, KAVACH_RUNBOOK_ROOT=str(self.tmp))
        self.git("init", "-b", "phase-test")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "t")
        (self.tmp / "docs" / "runbook").mkdir(parents=True)
        (self.tmp / "docs" / "runbook" / "chunk_T.steps.json").write_text(json.dumps(CFG), encoding="utf-8")
        (self.tmp / "README.md").write_text("hello\n", encoding="utf-8")
        (self.tmp / ".gitignore").write_text("runtime/\n", encoding="utf-8")
        (self.tmp / "old_untracked").mkdir()
        (self.tmp / "old_untracked" / "x.txt").write_text("pre-existing untracked file\n", encoding="utf-8")
        self.git("add", ".gitignore", "README.md", "docs")
        self.git("commit", "-m", "init")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.tmp, capture_output=True, text=True)

    def tool(self, *args):
        r = subprocess.run([sys.executable, str(TOOL), *args], cwd=self.tmp, capture_output=True, text=True, env=self.env)
        return r.returncode, r.stdout + r.stderr

    def write(self, rel, text="x = 1\n"):
        p = self.tmp / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def start_t0(self):
        code, out = self.tool("begin", "--chunk", "T", "T0")
        self.assertEqual(code, 0, out)

    def test_happy_path_commits_only_step_files(self):
        self.start_t0()
        self.write("pkg/a.py")
        code, out = self.tool("gate", "--chunk", "T", "T0")
        self.assertEqual(code, 0, out)
        code, out = self.tool("commit", "--chunk", "T", "T0", "--no-push")
        self.assertEqual(code, 0, out)
        files = self.git("show", "--name-only", "--format=", "HEAD").stdout
        self.assertIn("pkg/a.py", files)
        self.assertNotIn("old_untracked", files)
        self.assertIn("runbook_state/PROGRESS_T.json", files)
        status = json.loads((self.tmp / "runbook_state" / "PROGRESS_T.json").read_text(encoding="utf-8"))
        self.assertEqual(status["steps"]["T0"]["status"], "done")

    def test_file_outside_allow_list_fails_and_attempt_limit_locks(self):
        self.start_t0()
        self.write("other.txt", "not allowed\n")
        code, out = self.tool("gate", "--chunk", "T", "T0")
        self.assertEqual(code, 1, out)
        self.assertIn("outside the allow-list", out)
        code, out = self.tool("gate", "--chunk", "T", "T0")
        self.assertEqual(code, 3, out)
        code, out = self.tool("gate", "--chunk", "T", "T0")
        self.assertEqual(code, 3, out)
        code, out = self.tool("unlock", "--chunk", "T", "T0")
        self.assertEqual(code, 0, out)
        (self.tmp / "other.txt").unlink()
        self.write("pkg/a.py")
        code, out = self.tool("gate", "--chunk", "T", "T0")
        self.assertEqual(code, 0, out)

    def test_editing_existing_file_without_permission_fails(self):
        self.start_t0()
        self.write("README.md", "changed\n")
        code, out = self.tool("gate", "--chunk", "T", "T0")
        self.assertEqual(code, 1, out)
        self.assertIn("edited without permission", out)

    def test_deleting_a_file_fails(self):
        self.start_t0()
        (self.tmp / "README.md").unlink()
        code, out = self.tool("gate", "--chunk", "T", "T0")
        self.assertEqual(code, 1, out)
        self.assertIn("deleted file", out)

    def test_banned_word_detected_whole_word_only(self):
        self.start_t0()
        self.write("pkg/a.py", "# this proves it\n")
        code, out = self.tool("gate", "--chunk", "T", "T0")
        self.assertEqual(code, 1, out)
        self.assertIn("banned word", out)
        self.write("pkg/a.py", "# it approves the request\n")
        code, out = self.tool("gate", "--chunk", "T", "T0")
        self.assertEqual(code, 0, out)  # 'approves' is not the banned whole word 'proves'
        self.assertNotIn("banned word 'proves'", out)

    def test_machine_specific_path_detected(self):
        self.start_t0()
        self.write("pkg/a.py", "P = 'C:\\\\Users\\\\someone\\\\x'\n")
        code, out = self.tool("gate", "--chunk", "T", "T0")
        self.assertEqual(code, 1, out)
        self.assertIn("machine-specific", out)

    def test_step_order_enforced(self):
        code, out = self.tool("begin", "--chunk", "T", "T1")
        self.assertEqual(code, 2, out)
        self.assertIn("previous step T0", out)

    def test_commit_refused_if_files_change_after_gate(self):
        self.start_t0()
        self.write("pkg/a.py")
        self.assertEqual(self.tool("gate", "--chunk", "T", "T0")[0], 0)
        self.write("pkg/a.py", "x = 2\n")
        code, out = self.tool("commit", "--chunk", "T", "T0", "--no-push")
        self.assertEqual(code, 2, out)
        self.assertIn("changed after the gate", out)

    def test_commit_refused_without_gate(self):
        self.start_t0()
        code, out = self.tool("commit", "--chunk", "T", "T0", "--no-push")
        self.assertEqual(code, 2, out)

    def test_test_count_must_not_decrease(self):
        self.start_t0()
        self.write("pkg/a.py")
        self.assertEqual(self.tool("gate", "--chunk", "T", "T0")[0], 0)
        self.assertEqual(self.tool("commit", "--chunk", "T", "T0", "--no-push")[0], 0)
        self.assertEqual(self.tool("begin", "--chunk", "T", "T1")[0], 0)
        self.write("pkg2/b.py")
        code, out = self.tool("gate", "--chunk", "T", "T1")
        self.assertEqual(code, 1, out)
        self.assertIn("baseline 5", out)

    def test_hold_blocks_begin_until_release(self):
        self.start_t0()
        code, out = self.tool("hold", "--chunk", "T", "T0", "need the user")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.tool("begin", "--chunk", "T", "T0")[0], 2)
        self.assertEqual(self.tool("release", "--chunk", "T", "T0")[0], 0)
        self.assertEqual(self.tool("begin", "--chunk", "T", "T0")[0], 0)

    def test_hold_before_requires_release(self):
        self.start_t0()
        self.write("pkg/a.py")
        self.assertEqual(self.tool("gate", "--chunk", "T", "T0")[0], 0)
        self.assertEqual(self.tool("commit", "--chunk", "T", "T0", "--no-push")[0], 0)
        self.write("README.md", "changed\n")  # allowed edit for T1 only
        self.git("checkout", "--", "README.md")
        self.assertEqual(self.tool("begin", "--chunk", "T", "T1")[0], 0)
        self.write("pkg2/b.py")
        (self.tmp / "runbook_state" / "PROGRESS_T.json").exists()
        prog = json.loads((self.tmp / "runbook_state" / "PROGRESS_T.json").read_text(encoding="utf-8"))
        prog["steps"]["T1"]["status"] = "done"
        (self.tmp / "runbook_state" / "PROGRESS_T.json").write_text(json.dumps(prog), encoding="utf-8")
        code, out = self.tool("begin", "--chunk", "T", "T2")
        self.assertEqual(code, 2, out)
        self.assertIn("release", out)

    def test_run_saves_raw_output_and_returns_exit_code(self):
        self.start_t0()
        code, out = self.tool("run", "--chunk", "T", "--name", "failing", "T0", "--", "PY", "-c",
                              "import sys; print('boom'); sys.exit(7)")
        self.assertEqual(code, 7, out)
        raws = list((self.tmp / "runbook_logs" / "T" / "raw").glob("T0_01_failing.txt"))
        self.assertEqual(len(raws), 1)
        self.assertIn("boom", raws[0].read_text(encoding="utf-8"))
        sums = (self.tmp / "runbook_logs" / "T" / "raw" / "SHA256SUMS.txt").read_text(encoding="utf-8")
        self.assertIn("T0_01_failing.txt", sums)

    def test_run_option_order_does_not_matter(self):
        self.start_t0()
        code, out = self.tool("run", "--chunk", "T", "T0", "--name", "after", "--", "PY", "-c", "print('ok')")
        self.assertEqual(code, 0, out)
        self.assertTrue(list((self.tmp / "runbook_logs" / "T" / "raw").glob("T0_01_after.txt")))
        code, out = self.tool("run", "--chunk", "T", "T0", "PY", "-c", "print('x')")
        self.assertEqual(code, 2, out)  # missing '--' is refused, not executed

    def test_bytecode_and_cache_files_are_ignored(self):
        self.start_t0()
        self.write("pkg/a.py")
        self.write("pkg/__pycache__/a.cpython-312.pyc", "junk")
        self.write(".pytest_cache/v/cache/x", "junk")
        code, out = self.tool("gate", "--chunk", "T", "T0")
        self.assertEqual(code, 0, out)
        code, out = self.tool("commit", "--chunk", "T", "T0", "--no-push")
        self.assertEqual(code, 0, out)
        files = self.git("show", "--name-only", "--format=", "HEAD").stdout
        self.assertNotIn("__pycache__", files)

    def test_wrong_branch_refused(self):
        self.git("checkout", "-b", "somewhere-else")
        code, out = self.tool("begin", "--chunk", "T", "T0")
        self.assertEqual(code, 2, out)
        self.assertIn("wrong branch", out)

    def test_modified_tracked_file_before_begin_refused(self):
        self.write("README.md", "dirty\n")
        code, out = self.tool("begin", "--chunk", "T", "T0")
        self.assertEqual(code, 2, out)

    def test_bundle_contains_logs(self):
        self.start_t0()
        self.tool("worklog", "--chunk", "T", "T0", "an observation")
        code, out = self.tool("bundle", "--chunk", "T")
        self.assertEqual(code, 0, out)
        zips = list((self.tmp / "runtime" / "bundles").glob("T_bundle_*.zip"))
        self.assertEqual(len(zips), 1)
        with zipfile.ZipFile(zips[0]) as z:
            names = z.namelist()
        self.assertIn("GIT_SUMMARY.txt", names)
        self.assertIn("runbook_logs/T/worklog.txt", names)


if __name__ == "__main__":
    unittest.main()
