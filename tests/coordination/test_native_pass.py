"""Coverage and safety boundaries for cross-app pass dispatch."""
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import native_pass as p


class PassTests(unittest.TestCase):
    def setUp(self):
        self.config = p.plan()
        self.tasks, _ = p.c.load_contracts()

    def test_passes_cover_every_product_task_once(self):
        planned = [t for stage in self.config["passes"] for t in stage["tasks"]]
        planned += self.config["completed_bootstrap"] + self.config["owner_release"]
        self.assertEqual(len(planned), len(set(planned)))
        self.assertEqual(set(planned), set(self.tasks))

    def test_task_owners_are_unique_and_complete(self):
        owned = [t for app in self.config["apps"].values() for t in app["tasks"]]
        planned = [t for stage in self.config["passes"] for t in stage["tasks"]]
        self.assertEqual(len(owned), len(set(owned)))
        self.assertEqual(set(owned), set(planned))
        self.assertEqual(len(owned), 53)
        self.assertEqual(self.config["integration_owner"], "codex")
        self.assertEqual(self.config["worker_budgets"], {
            "codex": None, "devin": None, "antigravity": 0, "zcode": None})
        self.assertIsNone(self.config["max_active_workers"])
        self.assertEqual(self.config["apps"]["codex"]["tasks"],
                         "T03 T04 T11 T15 T23 T24 T25 T29 T30 T32 T33 T34 T40 T46 T48 T51 T52 T55".split())
        self.assertEqual(self.config["apps"]["zcode"]["tasks"],
                         "T05 T17 T21 T26 T27 T28 T35 T37 T38 T41 T42 T44 T45 T47 T49 T50".split())
        self.assertEqual(self.config["apps"]["antigravity"]["tasks"], [])

    def test_no_pass_depends_on_future_work(self):
        seen = set(self.config["completed_bootstrap"])
        for stage in self.config["passes"]:
            seen.update(stage["tasks"])
            for task in stage["tasks"]:
                self.assertLessEqual(set(self.tasks[task]["dependencies"]), seen, task)

    def test_gate_checkpoint_blocks_advance_after_tasks_close(self):
        issues = {p.c.bead_id(t): {"status": "closed"} for t in self.tasks}
        self.assertEqual(p.current_pass(self.config, issues)["id"], 1)
        issues["pdf-pass1"] = {"status": "closed"}
        self.assertEqual(p.current_pass(self.config, issues)["id"], 2)
        issues.update({f"pdf-pass{i}": {"status": "closed"} for i in (2, 3)})
        self.assertIsNone(p.current_pass(self.config, issues))

    def test_wrong_app_cannot_receive_task(self):
        with self.assertRaisesRegex(ValueError, "not owned"):
            p.assignment(self.config, "T05", "devin", "a" * 40, 1)
        self.assertEqual(p.assignment(self.config, "T05", "zcode", "a" * 40, 1)["branch"], "work/zcode/t05")

    def test_closed_or_assigned_or_future_tasks_cannot_dispatch(self):
        stage = self.config["passes"][0]
        for tid, issue in (("T05", {"status": "closed"}),
                           ("T05", {"status": "open", "assignee": "other"}),
                           ("T54", {"status": "open"})):
            self.assertTrue(p.dispatch_errors(self.config, stage, tid, issue, [], "zcode"))

    def test_local_app_budget_and_global_capacity_both_apply(self):
        self.config["max_active_workers"] = 3
        self.config["worker_budgets"]["zcode"] = 1
        stage = self.config["passes"][0]
        issue = {"status": "open"}
        self.assertEqual(p.dispatch_errors(self.config, stage, "T05", issue, [], "zcode"), [])
        own = [{"metadata": {"execution": {"app": "zcode"}}}]
        self.assertIn("App worker capacity is occupied", p.dispatch_errors(self.config, stage, "T05", issue, own, "zcode"))
        self.assertIn("Global worker capacity is occupied", p.dispatch_errors(self.config, stage, "T05", issue, [{}] * 3, "zcode"))

    def test_adaptive_capacity_has_no_numeric_ceiling_but_preserves_admission(self):
        stage = self.config["passes"][0]
        for app, task in (("codex", "T03"), ("devin", "T10"), ("zcode", "T27")):
            workers = [{"metadata": {"execution": {"app": app}}}] * 100
            with self.subTest(app=app):
                self.assertEqual(p.dispatch_errors(self.config, stage, task,
                                                  {"status": "open"}, workers, app), [])
                self.assertTrue(p.dispatch_errors(self.config, stage, task,
                                                 {"status": "in_progress"}, workers, app))
                self.assertTrue(p.dispatch_errors(self.config, None, task,
                                                 {"status": "open"}, workers, app))
        self.assertIn("App worker capacity is occupied", p.dispatch_errors(
            self.config, stage, "T03", {"status": "open"}, [], "antigravity"))

    def test_finite_global_and_app_limits_work_independently_of_null(self):
        stage = self.config["passes"][0]
        workers = [{"metadata": {"execution": {"app": "zcode"}}}] * 3
        self.config["max_active_workers"] = 3
        self.assertEqual(p.dispatch_errors(self.config, stage, "T27", {"status": "open"}, workers, "zcode"),
                         ["Global worker capacity is occupied"])
        self.config["max_active_workers"] = None
        self.config["worker_budgets"]["zcode"] = 3
        self.assertEqual(p.dispatch_errors(self.config, stage, "T27", {"status": "open"}, workers, "zcode"),
                         ["App worker capacity is occupied"])

    def test_new_codex_assignment_and_existing_grants_keep_their_original_app_and_branch(self):
        grant = p.assignment(self.config, "T03", "codex", "a" * 40, 1)
        self.assertEqual(grant["branch"], "work/codex/t03")
        issues = {}
        for task, app in (("T10", "devin"), ("T27", "zcode"), ("T03", "devin")):
            issues[p.c.bead_id(task)] = {"status": "in_progress", "assignee": "saved-worker",
                "metadata": {"execution": {"app": app, "branch": f"work/{app}/{task.lower()}",
                                           "base": "b" * 40, "pass": 1}}}
        before = json.dumps(issues, sort_keys=True)
        with patch.object(p.c, "admission_lock"), patch.object(p.c, "issues_by_id", return_value=issues), \
             patch.object(p.c, "bd") as bd:
            for app, expected in (("devin", {"T10", "T03"}), ("zcode", {"T27"}), ("codex", set())):
                with redirect_stdout(StringIO()) as output:
                    p.status(app, False)
                inbox = json.loads(output.getvalue())
                self.assertIsNone(inbox["worker_budget"])
                self.assertEqual({item["task"] for item in inbox["assignments"]}, expected)
                for item in inbox["assignments"]:
                    self.assertEqual(item["branch"], f"work/{app}/{item['task'].lower()}")
                    self.assertEqual(item["base"], "b" * 40)
            bd.assert_not_called()
        self.assertEqual(json.dumps(issues, sort_keys=True), before)

    def test_sync_failure_does_not_report_empty_inbox(self):
        with patch.object(p.c, "admission_lock"), patch.object(p, "sync_state", side_effect=ValueError("offline")), patch.object(p.c, "issues_by_id") as read:
            with self.assertRaisesRegex(ValueError, "offline"):
                p.status("zcode", True)
            read.assert_not_called()

    def test_worker_clone_cannot_dispatch(self):
        with patch.object(p.c, "run", return_value="worker"), patch.object(p.c, "bd") as bd:
            with self.assertRaisesRegex(ValueError, "designated"):
                p.dispatch("T05", "zcode")
            bd.assert_not_called()

    def test_dispatched_assignment_round_trips_as_an_object_without_losing_metadata(self):
        # Beads 1.2.2 --set-metadata values are strings, even when they look like JSON.
        issues = {"pdf-t02": {"status": "open", "metadata": {"existing": {"preserve": True}}}}
        def git(argv):
            if argv[1:3] == ["config", "--get"]:
                return "integrator"
            if argv[1:3] == ["branch", "--show-current"]:
                return "main"
            return "a" * 40 if argv[1] == "rev-parse" else ""
        def bd(argv, **kwargs):
            if argv[0] == "list":
                return [{"id": "pdf-t02"}]
            issue = issues[argv[1]]
            if "--metadata" in argv:
                issue["metadata"] = json.loads(argv[argv.index("--metadata") + 1])
            else:
                key, value = argv[argv.index("--set-metadata") + 1].split("=", 1)
                issue["metadata"][key] = value
            issue.update(status="in_progress", assignee=kwargs["actor"])
        with patch.object(p.c, "run", side_effect=git), patch.object(p.c, "bd", side_effect=bd), \
             patch.object(p.c, "issues_by_id", return_value=issues), patch.object(p.c, "admission_lock"), \
             patch.object(p.c, "check_predecessors"), patch.object(p, "sync_state"), \
             patch.object(p, "publish_state") as publish, redirect_stdout(StringIO()):
            p.dispatch("T02", "devin")
            publish.assert_called_once()
            with redirect_stdout(StringIO()) as output:
                p.status("devin", False)
        inbox = json.loads(output.getvalue())
        self.assertEqual(inbox["assignments"][0]["branch"], "work/devin/t02")
        self.assertEqual(issues["pdf-t02"]["metadata"]["existing"], {"preserve": True})


if __name__ == "__main__":
    unittest.main()
