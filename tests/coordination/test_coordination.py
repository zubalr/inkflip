import copy
import importlib.util
import json
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("coordination", ROOT / "scripts/coordination.py")
c = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(c)


class CoordinationTests(unittest.TestCase):
    def setUp(self):
        self.tasks, self.overrides = c.load_contracts()
        self.accepted = {
            "status": "closed",
            "metadata": {
                "disposition": "accepted",
                "accepted_commit": "a" * 40,
                "accepted_receipt": "artifacts/tasks/T01/acceptance.json",
            },
        }

    def test_bun_overrides_preserve_frozen_task(self):
        original = copy.deepcopy(self.tasks["T01"])
        result = c.effective_task(original, self.overrides)
        self.assertEqual(original, self.tasks["T01"])
        self.assertIn("bunfig.toml", result["allowed_scope"])
        self.assertNotIn("pnpm-workspace.yaml", result["allowed_scope"])
        self.assertNotIn("status", result)
        self.assertIn("tests/bootstrap/", result["allowed_scope"])
        self.assertNotIn("execution/state.json", json.dumps(result))
        self.assertEqual(c.effective_task(self.tasks["T02"], self.overrides)["deliverables"][0]["path"], "bun.lock")

    def test_commands_keep_test_intent_without_package_auto_install(self):
        self.assertEqual(c.adapt_command("pnpm exec playwright test gate.spec.ts", self.overrides),
                         "bun x --no-install playwright test gate.spec.ts")
        self.assertEqual(c.adapt_command("pnpm test:visual -- tests/visual/foundation.spec.ts", self.overrides),
                         "bun run test:visual -- tests/visual/foundation.spec.ts")
        self.assertEqual(c.adapt_command("node --test tests/*.mjs", self.overrides), "node --test tests/*.mjs")
        for task in self.tasks.values():
            for command in c.effective_task(task, self.overrides)["commands"]:
                self.assertNotIn("pnpm", command)

    def test_closed_without_acceptance_is_blocked(self):
        with self.assertRaises(ValueError):
            c.acceptance_reference("T01", {"status": "closed"})
        with self.assertRaises(ValueError):
            c.acceptance_reference("T01", {**self.accepted, "status": "in_progress"})

    def test_rejection_cannot_complete_required_capability(self):
        self.accepted["metadata"]["disposition"] = "rejected_experiment"
        with self.assertRaises(ValueError):
            c.acceptance_reference("T01", self.accepted)
        self.accepted["metadata"]["accepted_receipt"] = "artifacts/tasks/T41/rejection.json"
        self.assertEqual(c.acceptance_reference("T41", self.accepted)[0], "a" * 40)

    def test_receipt_namespace_and_commit_are_checked(self):
        for bad in ["/tmp/x", "artifacts/tasks/T01/../../T02/x", "artifacts/tasks/T02/x", "artifacts/tasks/T01/", ""]:
            with self.subTest(receipt=bad):
                issue = copy.deepcopy(self.accepted)
                issue["metadata"]["accepted_receipt"] = bad
                with self.assertRaises(ValueError):
                    c.acceptance_reference("T01", issue)
        self.accepted["metadata"]["accepted_commit"] = "HEAD"
        with self.assertRaises(ValueError):
            c.acceptance_reference("T01", self.accepted)

    def test_unmerged_accepted_predecessor_is_blocked(self):
        with patch.object(c, "run", side_effect=ValueError("not an ancestor")):
            with self.assertRaises(ValueError):
                c.check_predecessors(self.tasks["T02"], {"pdf-t01": self.accepted}, ref="HEAD")

    def test_missing_committed_receipt_is_blocked(self):
        with patch.object(c, "run", side_effect=["", ValueError("missing receipt")]):
            with self.assertRaises(ValueError):
                c.check_predecessors(self.tasks["T02"], {"pdf-t01": self.accepted}, ref="HEAD")

    def test_receipt_must_be_a_file_not_a_tree(self):
        with patch.object(c, "run", side_effect=["", "tree"]):
            with self.assertRaises(ValueError):
                c.check_predecessors(self.tasks["T02"], {"pdf-t01": self.accepted}, ref="HEAD")
        with patch.object(c, "run", side_effect=["", "blob"]):
            c.check_predecessors(self.tasks["T02"], {"pdf-t01": self.accepted}, ref="HEAD")

    def test_beads_readiness_is_required_even_with_accepted_parents(self):
        self.assertFalse(c.task_ready(self.tasks["T02"], {"pdf-t01": self.accepted}, set()))
        self.assertTrue(c.task_ready(self.tasks["T01"], {}, {"pdf-t01"}))

    def test_correct_clean_task_can_be_admitted(self):
        self.assertEqual(c.admission_errors("T01", {"status": "open"}, branch="work/pdf-t01",
                         dirty=False, fresh=True, active=4, maximum=5), [])

    def test_each_ownership_failure_prevents_admission(self):
        defaults = dict(branch="work/pdf-t01", dirty=False, fresh=True, active=0, maximum=5)
        for changed in [dict(branch="main"), dict(dirty=True), dict(fresh=False), dict(active=5)]:
            with self.subTest(changed=changed):
                self.assertTrue(c.admission_errors("T01", {"status": "open"}, **(defaults | changed)))
        self.assertTrue(c.admission_errors("T01", {"status": "in_progress"}, **defaults))
        self.assertTrue(c.admission_errors("T01", {"status": "open", "assignee": "other"}, **defaults))

    def test_first_parallel_pass_has_disjoint_scopes(self):
        tasks = [c.effective_task(self.tasks[x], self.overrides) for x in ["T02", "T03", "T05", "T06"]]
        for index, left in enumerate(tasks):
            self.assertEqual(left["dependencies"], ["T01"])
            for right in tasks[index + 1:]:
                for a in left["allowed_scope"]:
                    for b in right["allowed_scope"]:
                        self.assertFalse(a == b or a.startswith(b.rstrip("/") + "/") or b.startswith(a.rstrip("/") + "/"))

    def test_required_initial_test_and_token_paths_are_owned(self):
        required = {"T01": "apps/web/src/styles/", "T02": "tests/build/", "T03": "native/tests/contracts/"}
        for tid, path in required.items():
            self.assertIn(path, c.effective_task(self.tasks[tid], self.overrides)["allowed_scope"])

    def test_later_nested_writer_is_rejected(self):
        issue = {"id": "pdf-t09", "status": "in_progress", "labels": ["execution:worker"]}
        candidate = c.effective_task(self.tasks["T33"], self.overrides)
        with self.assertRaisesRegex(ValueError, "pdf-t09"):
            c.check_scope_ownership(candidate, [issue], self.tasks, self.overrides)

    def test_scope_check_handles_wildcards_and_unscoped_workers(self):
        self.assertTrue(c.scopes_overlap("packages/*/package.json", "packages/contracts/"))
        self.assertFalse(c.scopes_overlap("tests/build/", "tests/contracts/"))
        issue = {"id": "pdf-unknown", "status": "in_progress", "labels": ["execution:worker"]}
        with self.assertRaisesRegex(ValueError, "scope"):
            c.check_scope_ownership(self.tasks["T01"], [issue], self.tasks, self.overrides)
        issue["labels"].append("execution:review")
        c.check_scope_ownership(self.tasks["T01"], [issue], self.tasks, self.overrides)

    def test_clean_branch_ahead_of_main_is_not_a_fresh_assignment(self):
        values = {("git", "branch", "--show-current"): "work/pdf-t01",
                  ("git", "status", "--porcelain"): "",
                  ("git", "rev-parse", "HEAD"): "b" * 40,
                  ("git", "rev-parse", "main"): "a" * 40}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / ".beads").mkdir()
            with patch.object(c, "canonical_root", return_value=root), \
                 patch.object(c, "issues_by_id", return_value={"pdf-t01": {"status": "open"}}), \
                 patch.object(c, "bd", return_value=[{"id": "pdf-t01"}]) as beads, \
                 patch.object(c, "run", side_effect=lambda argv: values[tuple(argv)]):
                with self.assertRaisesRegex(ValueError, "main"):
                    c.start(c.effective_task(self.tasks["T01"], self.overrides), "test-worker", self.overrides)
                self.assertFalse(any(call.kwargs.get("write") for call in beads.call_args_list))

    def test_review_and_product_claims_share_atomic_capacity_admission(self):
        issues = {f"pdf-active-{n}": {"id": f"pdf-active-{n}", "status": "in_progress",
                  "labels": ["execution:worker", "execution:review"]} for n in range(4)}
        issues["pdf-t01"] = {"id": "pdf-t01", "status": "open", "labels": ["execution:worker"]}
        issues["pdf-review"] = {"id": "pdf-review", "status": "open",
                                "labels": ["execution:worker", "execution:review"]}
        product_snapshot = threading.Event()
        review_attempt = threading.Event()
        release_product = threading.Event()
        outcomes = []
        real_flock = c.fcntl.flock

        def flock(handle, operation):
            if threading.current_thread().name == "review":
                review_attempt.set()
            return real_flock(handle, operation)

        def snapshot():
            current = copy.deepcopy(issues)
            if threading.current_thread().name == "product":
                product_snapshot.set()
                if not release_product.wait(5):
                    raise RuntimeError("Test did not release product admission")
            return current

        def beads(argv, **kwargs):
            if argv[0] == "list":
                return [i for i in issues.values() if i["status"] == "open"]
            self.assertTrue(kwargs["write"])
            issues[argv[1]]["status"] = "in_progress"
            return [issues[argv[1]]]

        def admit(kind):
            try:
                if kind == "product":
                    c.start(c.effective_task(self.tasks["T01"], self.overrides), "product", self.overrides)
                else:
                    c.start_review("pdf-review", "reviewer", self.overrides)
                outcomes.append((kind, "claimed"))
            except ValueError as error:
                outcomes.append((kind, str(error)))

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / ".beads").mkdir()
            values = {("git", "branch", "--show-current"): "work/pdf-t01",
                      ("git", "status", "--porcelain"): "",
                      ("git", "rev-parse", "HEAD"): "a" * 40,
                      ("git", "rev-parse", "main"): "a" * 40}
            with patch.object(c, "ROOT", root), patch.object(c, "canonical_root", return_value=root), \
                 patch.object(c, "load_contracts", return_value=(self.tasks, self.overrides)), \
                 patch.object(c, "issues_by_id", side_effect=snapshot), patch.object(c, "bd", side_effect=beads), \
                 patch.object(c.fcntl, "flock", side_effect=flock), \
                 patch.object(c, "run", side_effect=lambda argv: values[tuple(argv)]), redirect_stdout(StringIO()):
                product = threading.Thread(target=admit, args=("product",), name="product")
                review = threading.Thread(target=admit, args=("review",), name="review")
                product.start()
                try:
                    self.assertTrue(product_snapshot.wait(5))
                    review.start()
                    self.assertTrue(review_attempt.wait(5))
                finally:
                    release_product.set()
                    product.join(5)
                    if review.ident is not None:
                        review.join(5)
                self.assertFalse(product.is_alive())
                self.assertFalse(review.is_alive())
        self.assertIn(("product", "claimed"), outcomes)
        self.assertEqual(sum(i["status"] == "in_progress" for i in issues.values()), 5)
        self.assertTrue(any(kind == "review" and "slots" in result for kind, result in outcomes))

    def test_all_original_tasks_and_gates_are_retained(self):
        self.assertEqual(set(self.tasks), {f"T{n:02}" for n in range(1, 56)})
        gates = json.loads((ROOT / "planning/execution/gates.json").read_text())
        self.assertEqual({g["id"] for g in gates}, {f"G{n}" for n in range(1, 6)})
        self.assertFalse((ROOT / "execution/state.json").exists())

    def test_generated_prompts_use_separate_worktrees_and_guarded_claims(self):
        with patch.object(c, "canonical_root", return_value=ROOT):
            for tid in ["T01", "T02", "T03", "T05", "T06"]:
                actor = "worker-" + tid.lower()
                prompt = c.render_prompt(c.effective_task(self.tasks[tid], self.overrides), actor, self.overrides)
                self.assertIn(str(ROOT.parent / "worktrees" / c.bead_id(tid)), prompt)
                self.assertIn(f"start {tid} --actor {actor}", prompt)
                self.assertIn(f"work/{c.bead_id(tid)}", prompt)
                self.assertIn("Then stop for independent review", prompt)

    def test_prompt_session_label_cannot_inject_shell_instructions(self):
        for actor in ["", "worker; ls", "worker\nls", "$(whoami)", "x" * 65]:
            with self.subTest(actor=actor), self.assertRaises(ValueError):
                c.render_prompt(self.tasks["T01"], actor, self.overrides)


if __name__ == "__main__":
    unittest.main()
