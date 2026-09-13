import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
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
        with patch("evidence_store.require_ancestry", side_effect=ValueError("not an ancestor")):
            with self.assertRaises(ValueError):
                c.check_predecessors(self.tasks["T02"], {"pdf-t01": self.accepted}, ref="HEAD")

    def test_missing_committed_receipt_is_blocked(self):
        with patch("evidence_store.require_ancestry"), \
             patch.object(c, "run", side_effect=ValueError("missing receipt")):
            with self.assertRaises(ValueError):
                c.check_predecessors(self.tasks["T02"], {"pdf-t01": self.accepted}, ref="HEAD")

    def test_receipt_must_be_a_file_not_a_tree(self):
        with patch("evidence_store.require_ancestry"), patch.object(c, "run", return_value="tree"):
            with self.assertRaises(ValueError):
                c.check_predecessors(self.tasks["T02"], {"pdf-t01": self.accepted}, ref="HEAD")
        with patch("evidence_store.require_ancestry"), patch.object(c, "run", return_value="blob"):
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

    def test_stale_base_is_rejected_by_the_admission_helper(self):
        # The retired CLI refuses before git inspection; the surviving generic
        # helper still encodes the stale-base rule for any coordinator reuse.
        errors = c.admission_errors("T01", {"status": "open"}, branch="work/pdf-t01",
                                    dirty=False, fresh=False, active=0, maximum=5)
        self.assertTrue(any("starting point" in e for e in errors), errors)

    def test_deprecated_local_admission_refuses_without_beads_write(self):
        # The historical worker self-claim path is retired: start/start-review
        # must fail closed with native_pass coordinator guidance and never
        # reach the admission lock or a Beads mutation, regardless of state.
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / ".beads").mkdir()
            with patch.object(c, "ROOT", root), patch.object(c, "canonical_root", return_value=root), \
                 patch.object(c, "issues_by_id", return_value={"pdf-t01": {"status": "open"}}), \
                 patch.object(c, "bd") as beads, patch.object(c, "run") as git:
                with self.assertRaisesRegex(ValueError, "native_pass.py dispatch"):
                    c.start(c.effective_task(self.tasks["T01"], self.overrides), "worker", self.overrides)
                with self.assertRaisesRegex(ValueError, "independent review assignment"):
                    c.start_review("pdf-review", "reviewer", self.overrides)
                self.assertFalse(any(call.kwargs.get("write") for call in beads.call_args_list))
                self.assertFalse(git.called)

    def test_all_original_tasks_and_gates_are_retained(self):
        self.assertEqual(set(self.tasks), {f"T{n:02}" for n in range(1, 56)})
        gates = json.loads((ROOT / "planning/execution/gates.json").read_text())
        self.assertEqual({g["id"] for g in gates}, {f"G{n}" for n in range(1, 6)})
        self.assertFalse((ROOT / "execution/state.json").exists())

    def test_generated_prompts_use_saved_grants_and_guarded_claims(self):
        # Prompts must point at the saved Beads execution grant and the
        # coordinator-assigned checkout, never a fabricated branch or
        # worktree — the grant survives static allocation changes.
        for tid in ["T01", "T02", "T03", "T05", "T06"]:
            actor = "worker-" + tid.lower()
            prompt = c.render_prompt(c.effective_task(self.tasks[tid], self.overrides), actor, self.overrides)
            self.assertIn("the exact branch saved in your Beads execution grant", prompt)
            self.assertIn("assigned separately by the coordinator", prompt)
            self.assertIn(f"task {tid}", prompt)
            self.assertIn("native_pass.py dispatch", prompt)
            self.assertNotIn(f"start {tid} --actor", prompt)
            self.assertNotIn("work/pdf-", prompt)
            self.assertIn("Then stop for independent review", prompt)

    def test_prompt_session_label_cannot_inject_shell_instructions(self):
        for actor in ["", "worker; ls", "worker\nls", "$(whoami)", "x" * 65]:
            with self.subTest(actor=actor), self.assertRaises(ValueError):
                c.render_prompt(self.tasks["T01"], actor, self.overrides)


if __name__ == "__main__":
    unittest.main()
