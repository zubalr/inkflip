"""Coverage and safety boundaries for cross-app pass dispatch."""
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
        self.assertEqual(sum(self.config["worker_budgets"].values()), 5)

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
        stage = self.config["passes"][0]
        issue = {"status": "open"}
        self.assertEqual(p.dispatch_errors(self.config, stage, "T05", issue, [], "zcode"), [])
        own = [{"metadata": {"execution": {"app": "zcode"}}}]
        self.assertIn("App worker capacity is occupied", p.dispatch_errors(self.config, stage, "T05", issue, own, "zcode"))
        self.assertIn("Global worker capacity is occupied", p.dispatch_errors(self.config, stage, "T05", issue, [{}] * 5, "zcode"))

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


if __name__ == "__main__":
    unittest.main()
