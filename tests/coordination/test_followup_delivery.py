"""Non-product grants must reach the same native inbox as product work."""
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import native_pass as p
import native_followups as f


class FollowupDeliveryTests(unittest.TestCase):
    def grant(self, **changes):
        return dict(kind="followup", app="zcode", branch="work/zcode/pdf-g78",
                    base="a" * 40, **{"pass": 1}, mode="audit",
                    allowed_scope=["artifacts/followups/pdf-g78/"],
                    instructions="Inventory missing fixture families; return evidence only.",
                    **changes)

    def status(self, issues):
        with patch.object(p.c, "admission_lock"), \
             patch.object(p.c, "issues_by_id", return_value=issues), \
             patch.object(p.c, "bd") as bd, redirect_stdout(StringIO()) as out:
            p.status("zcode", False)
            bd.assert_not_called()
        return json.loads(out.getvalue())

    def test_explicit_followup_reaches_worker_with_saved_scope_and_branch(self):
        grant = self.grant()
        issues = {"pdf-g78": {"status": "in_progress", "assignee": "zcode-pdf-g78",
                              "metadata": {"execution": grant}}}
        before = json.dumps(issues, sort_keys=True)
        inbox = self.status(issues)
        self.assertEqual(len(inbox["assignments"]), 1)
        self.assertEqual(inbox["assignments"][0]["task"], "pdf-g78")
        self.assertEqual(inbox["assignments"][0]["branch"], grant["branch"])
        self.assertEqual(inbox["assignments"][0]["allowed_scope"], grant["allowed_scope"])
        self.assertEqual(json.dumps(issues, sort_keys=True), before)

    def test_note_only_assignment_is_reported_as_undelivered_not_authority(self):
        inbox = self.status({"pdf-g78": {"status": "open", "assignee": "zcode",
                                        "metadata": None, "notes": "Please audit fixtures"}})
        self.assertEqual(inbox["assignments"], [])
        self.assertEqual(inbox["undelivered"][0]["issue"], "pdf-g78")

    def test_invalid_followup_is_an_error_not_empty_inbox(self):
        grant = self.grant()
        grant["branch"] = "main"
        with self.assertRaisesRegex(ValueError, "branch"):
            self.status({"pdf-g78": {"status": "in_progress", "metadata": {"execution": grant}}})

    def test_unlabelled_grants_count_toward_capacity(self):
        issues = {"pdf-g78": {"id": "pdf-g78", "status": "in_progress",
                              "metadata": {"execution": self.grant()}}}
        self.assertEqual(p.c.active_workers(issues), list(issues.values()))

    def test_scope_validation_rejects_escape_and_audit_product_writes(self):
        for scope in ("../outside", "/tmp/output", ".", "planning/a", ".beads/x", ".git/config",
                      "artifacts//followups/pdf-g78", "artifacts/*", "apps/web/"):
            grant = self.grant()
            grant["allowed_scope"] = [scope]
            with self.subTest(scope=scope), self.assertRaises(ValueError):
                f.validate_grant("pdf-g78", grant, p.plan())

    def test_followup_cannot_impersonate_product_or_checkpoint(self):
        for issue_id in ("T05", "pdf-t05", "pdf-t54", "pdf-pass1", "pdf-../main"):
            with self.subTest(issue_id=issue_id), self.assertRaises(ValueError):
                f.validate_grant(issue_id, self.grant(), p.plan())

    def test_product_dispatch_respects_active_followup_writer_scope(self):
        grant = self.grant()
        grant.update(mode="implementation", allowed_scope=["fixtures/"])
        workers = [{"id": "pdf-g78", "metadata": {"execution": grant}}]
        tasks, overrides = p.c.load_contracts()
        with self.assertRaisesRegex(ValueError, "overlaps pdf-g78"):
            p.c.check_scope_ownership({"allowed_scope": ["fixtures/public/"]}, workers, tasks, overrides)
        p.c.check_scope_ownership({"allowed_scope": ["apps/web/"]}, workers, tasks, overrides)
        workers[0]["labels"] = ["execution:worker", "execution:review"]
        with self.assertRaisesRegex(ValueError, "overlaps pdf-g78"):
            p.c.check_scope_ownership({"allowed_scope": ["fixtures/public/"]}, workers, tasks, overrides)

    def test_malformed_metadata_cannot_report_empty_inbox(self):
        for metadata in (["malformed"], {"execution": []}, {"execution": False},
                         {"execution": None}, {"execution": {}}, {"execution": {"branch": "main"}}):
            with self.subTest(metadata=metadata), self.assertRaisesRegex(ValueError, "malformed"):
                self.status({"pdf-g78": {"status": "in_progress", "metadata": metadata}})

    def dispatch(self, issues, *, ready=True, publish_error=None):
        def git(argv):
            if argv[1:3] == ["config", "--get"]:
                return "integrator"
            if argv[1:3] == ["branch", "--show-current"]:
                return "main"
            return "a" * 40 if argv[1] == "rev-parse" else ""
        def bd(argv, **kwargs):
            if argv[0] == "list":
                return [{"id": "pdf-g78"}] if ready else []
            self.assertEqual(argv[:3], ["update", "pdf-g78", "--claim"])
            issue = issues["pdf-g78"]
            issue.update(status="in_progress", assignee=kwargs["actor"])
            issue["metadata"] = json.loads(argv[argv.index("--metadata") + 1])
        with patch.object(p.c, "canonical_root", return_value=p.c.ROOT), \
             patch.object(p.c, "run", side_effect=git), patch.object(p.c, "bd", side_effect=bd), \
             patch.object(p.c, "issues_by_id", return_value=issues), patch.object(p.c, "admission_lock"), \
             patch.object(p, "sync_state"), patch.object(p, "publish_state", side_effect=publish_error), \
             redirect_stdout(StringIO()) as out:
            p.dispatch_followup("pdf-g78", "zcode", "audit", ["artifacts/followups/pdf-g78/"], "Inventory fixtures.")
        return json.loads(out.getvalue())

    def test_dispatch_roundtrip_preserves_existing_metadata(self):
        issues = {"pdf-g78": {"id": "pdf-g78", "status": "open", "metadata": {"existing": True}}}
        result = self.dispatch(issues)
        self.assertEqual(result["branch"], "work/zcode/pdf-g78")
        self.assertTrue(issues["pdf-g78"]["metadata"]["existing"])
        self.assertEqual(self.status(issues)["assignments"][0]["task"], "pdf-g78")

    def test_no_redispatch_or_dependency_bypass(self):
        for issue in ({"status": "closed"}, {"status": "open", "assignee": "existing"},
                      {"status": "in_progress", "assignee": "zcode-pdf-g78"}):
            with self.subTest(issue=issue), self.assertRaises(ValueError):
                self.dispatch({"pdf-g78": issue})
        with self.assertRaisesRegex(ValueError, "dependencies"):
            self.dispatch({"pdf-g78": {"status": "open"}}, ready=False)

    def test_publication_failure_retains_claim_without_success_response(self):
        issues = {"pdf-g78": {"status": "open"}}
        with self.assertRaisesRegex(ValueError, "offline"):
            self.dispatch(issues, publish_error=ValueError("offline"))
        self.assertEqual(issues["pdf-g78"]["status"], "in_progress")
        self.assertEqual(issues["pdf-g78"]["metadata"]["execution"]["branch"], "work/zcode/pdf-g78")

    def test_worker_or_linked_checkout_cannot_dispatch(self):
        with patch.object(p.c, "canonical_root", return_value=p.c.ROOT / "elsewhere"), \
             patch.object(p.c, "bd") as bd, self.assertRaisesRegex(ValueError, "canonical"):
            p.dispatch_followup("pdf-g78", "zcode", "audit", [], "Audit")
        bd.assert_not_called()


if __name__ == "__main__":
    unittest.main()
