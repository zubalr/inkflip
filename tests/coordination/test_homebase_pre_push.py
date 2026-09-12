"""Exercise the actual pre-push hook with disposable Git repositories."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import homebase_pre_push as hook


class PrePushTests(unittest.TestCase):
    task = "t27"

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.repo = self.root / "worker"
        self.remote = self.root / "relay.git"
        environment = patch.dict(os.environ, {
            "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_ALLOW_PROTOCOL": "file", "GIT_TERMINAL_PROMPT": "0",
            "GIT_AUTHOR_NAME": "Worker", "GIT_AUTHOR_EMAIL": "worker@example.test",
            "GIT_COMMITTER_NAME": "Worker", "GIT_COMMITTER_EMAIL": "worker@example.test",
        })
        environment.start()
        self.addCleanup(environment.stop)
        self.git("init", "--bare", str(self.remote), cwd=self.root)
        self.git("init", "-b", f"work/zcode/{self.task}", str(self.repo), cwd=self.root)
        self.base = self.commit("base")
        self.git("remote", "add", "handoff", str(self.remote))
        self.git("remote", "add", "origin", str(self.remote))
        hooks = self.root / "hooks"
        hooks.mkdir()
        self.wrapper = hooks / "pre-push"
        # Only the test harness changes the fixed URL to a disposable local path.
        # The production module is imported by absolute location, outside the branch.
        self.wrapper.write_text(
            f"#!{sys.executable}\nimport sys\nsys.path.insert(0, {str(SCRIPTS)!r})\n"
            f"import homebase_pre_push as h\nh.REMOTE_URL = {str(self.remote)!r}\n"
            "sys.exit(h.main())\n")
        self.wrapper.chmod(0o755)
        self.git("config", "core.hooksPath", str(hooks))
        self.target = f"refs/heads/hb/inkflip/{self.task}"

    def git(self, *args, cwd=None, success=True):
        result = subprocess.run(["git", *args], cwd=cwd or self.repo,
                                text=True, capture_output=True)
        if success:
            self.assertEqual(result.returncode, 0, result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Homebase push blocked:", result.stderr)
        return result.stdout.strip()

    def commit(self, text):
        (self.repo / "evidence").write_text(text)
        self.git("add", "evidence")
        self.git("commit", "-m", text)
        return self.git("rev-parse", "HEAD")

    def refs(self):
        return self.git("for-each-ref", "--format=%(objectname) %(refname)", cwd=self.remote)

    def invoke(self, text, remote="handoff", url=None):
        return subprocess.run([str(self.wrapper), remote, url or str(self.remote)],
                              cwd=self.repo, input=text, text=True, capture_output=True)

    def test_valid_create_and_fast_forward_through_hook(self):
        self.git("push", "handoff", f"HEAD:{self.target}")
        self.assertEqual(self.git("rev-parse", self.target, cwd=self.remote), self.base)
        candidate = self.commit("candidate and evidence")
        self.git("push", "handoff", f"refs/heads/work/zcode/{self.task}:{self.target}")
        self.assertEqual(self.git("rev-parse", self.target, cwd=self.remote), candidate)
        self.assertEqual(self.git("show", f"{candidate}:evidence", cwd=self.remote), "candidate and evidence")

    def test_repeated_same_sha_push_is_allowed(self):
        self.git("push", "handoff", f"HEAD:{self.target}")
        before = self.refs()
        self.git("push", "handoff", f"HEAD:{self.target}")
        self.assertEqual(self.refs(), before)

    def test_empty_updates_still_require_allowed_remote_and_task_branch(self):
        for text in ("", "\n\n"):
            with self.subTest(text=text):
                self.assertEqual(self.invoke(text).returncode, 0)
                self.assertNotEqual(self.invoke(text, remote="origin").returncode, 0)
                self.assertNotEqual(self.invoke(text, url="file://" + str(self.remote)).returncode, 0)
        for branch in ("main", "work/zcode/t00", "work/zcode/t56", "work/devin/t27"):
            with self.subTest(branch=branch):
                self.git("checkout", "-b", branch)
                self.assertNotEqual(self.invoke("").returncode, 0)
        self.git("checkout", "--detach")
        self.assertNotEqual(self.invoke("").returncode, 0)

    def test_wrong_targets_and_extra_refs_leave_remote_empty(self):
        for target in ("refs/heads/main", "refs/heads/hb/inkflip/t28", "refs/tags/t27", "refs/dolt/data"):
            with self.subTest(target=target):
                self.git("push", "handoff", f"HEAD:{target}", success=False)
        self.git("push", "handoff", f"HEAD:{self.target}", "HEAD:refs/heads/hb/inkflip/t28", success=False)
        self.assertEqual(self.refs(), "")

    def test_origin_and_direct_url_are_rejected(self):
        for remote in ("origin", str(self.remote)):
            with self.subTest(remote=remote):
                self.git("push", remote, f"HEAD:{self.target}", success=False)
        self.assertEqual(self.refs(), "")

    def test_delete_and_forced_rewind_are_rejected(self):
        candidate = self.commit("advance")
        self.git("push", "handoff", f"HEAD:{self.target}")
        self.git("push", "handoff", f":{self.target}", success=False)
        # Move the disposable checkout back without reset or overwriting a branch.
        self.git("checkout", "-b", "work/zcode/t01", self.base)
        self.git("branch", "-m", f"work/zcode/{self.task}", "saved-candidate")
        self.git("branch", "-m", f"work/zcode/{self.task}")
        for flag in ("--force", f"--force-with-lease={self.target}:{candidate}"):
            with self.subTest(flag=flag):
                self.git("push", flag, "handoff", f"HEAD:{self.target}", success=False)
        self.git("push", "handoff", f"+HEAD:{self.target}", success=False)
        self.assertEqual(self.git("rev-parse", self.target, cwd=self.remote), candidate)

    def test_wrong_current_branch_and_detached_head_are_rejected(self):
        for branch in ("main", "work/zcode/t00", "work/zcode/t56", "work/devin/t27"):
            with self.subTest(branch=branch):
                self.git("checkout", "-b", branch)
                self.git("push", "handoff", f"HEAD:{self.target}", success=False)
        self.git("checkout", "--detach")
        self.git("push", "handoff", f"HEAD:{self.target}", success=False)
        self.assertEqual(self.refs(), "")

    def test_other_local_branch_and_raw_sha_are_rejected_even_at_head(self):
        self.git("branch", "other")
        for source in ("refs/heads/other", self.base):
            with self.subTest(source=source):
                self.git("push", "handoff", f"{source}:{self.target}", success=False)
        self.assertEqual(self.refs(), "")

    def test_protocol_rejects_malformed_oversized_missing_and_wrong_objects(self):
        line = f"HEAD {self.base} {self.target} {hook.ZERO_SHA}"
        invalid = ["HEAD", line + " extra", line + "\n" + line,
                   "x" * (hook.MAX_INPUT + 1),
                   f"HEAD {hook.ZERO_SHA} {self.target} {hook.ZERO_SHA}",
                   f"HEAD {self.base} {self.target} {'f' * 40}",
                   f"HEAD not-a-sha {self.target} {hook.ZERO_SHA}"]
        for text in invalid:
            with self.subTest(text=text[:100]):
                self.assertNotEqual(self.invoke(text).returncode, 0)
        self.commit("new head")
        self.assertNotEqual(self.invoke(line).returncode, 0)

    def test_first_and_last_task_branches_are_allowed(self):
        for task in ("t01", "t55"):
            with self.subTest(task=task):
                self.git("checkout", "-b", f"work/zcode/{task}")
                target = f"refs/heads/hb/inkflip/{task}"
                self.git("push", "handoff", f"HEAD:{target}")
                self.assertEqual(self.git("rev-parse", target, cwd=self.remote), self.base)

    def test_exact_url_and_production_constant(self):
        self.assertEqual(hook.REMOTE_URL, "/home/wertyp/.local/share/homebase-factory/git/inkflip.git")
        line = f"HEAD {self.base} {self.target} {hook.ZERO_SHA}"
        self.assertNotEqual(self.invoke(line, url="file://" + str(self.remote)).returncode, 0)
        self.assertEqual(self.invoke("\n" + line + "\n\n").returncode, 0)


class FollowupPrePushTests(PrePushTests):
    """Run the same installed-hook transport protections for a full follow-up ID."""
    task = "pdf-g78"

    def test_followup_identity_is_exact(self):
        for target in ("refs/heads/hb/inkflip/g78", "refs/heads/hb/inkflip/PDF-G78",
                       "refs/heads/hb/inkflip/pdf-g79", "refs/heads/work/zcode/pdf-g78"):
            with self.subTest(target=target):
                self.git("push", "handoff", f"HEAD:{target}", success=False)
        for branch in ("work/zcode/g78", "work/zcode/PDF-G78", "work/devin/pdf-g78",
                       "work/zcode/pdf-t27", "work/zcode/pdf-pass1", "work/zcode/pdf-g78/extra"):
            with self.subTest(branch=branch):
                self.git("branch", "-m", branch)
                self.git("push", "handoff", f"HEAD:{self.target}", success=False)
                self.assertNotEqual(self.invoke("").returncode, 0)
        self.assertEqual(self.refs(), "")


if __name__ == "__main__":
    unittest.main()
