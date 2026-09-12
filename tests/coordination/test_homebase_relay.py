"""Relay safety with real local Git transport; no SSH, GitHub, or Beads writes."""
from contextlib import redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import homebase_relay as relay


class RelayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        # Ignore user transport/config/hooks and disallow every network protocol.
        self.env = patch.dict(os.environ, {
            "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_ALLOW_PROTOCOL": "file", "GIT_TERMINAL_PROMPT": "0",
            "GIT_AUTHOR_NAME": "Worker Actual", "GIT_AUTHOR_EMAIL": "worker@example.test",
            "GIT_COMMITTER_NAME": "Local Test", "GIT_COMMITTER_EMAIL": "test@example.test",
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.origin = root / "origin.git"
        self.homebase = root / "homebase.git"
        self.mac = root / "mac"
        self.worker = root / "worker"
        for bare in (self.origin, self.homebase):
            self.run_git(root, "init", "--bare", str(bare))
        self.run_git(root, "init", "-b", "main", str(self.mac))
        self.base = self.commit(self.mac, "initial")
        self.run_git(self.mac, "remote", "add", "origin", str(self.origin))
        self.run_git(self.mac, "remote", "add", "homebase", str(self.homebase))
        self.run_git(self.mac, "config", "inkflip.role", "integrator")
        self.run_git(self.mac, "push", "origin", "main", f"{self.base}:refs/dolt/data")
        self.run_git(root, "clone", "--branch", "main", str(self.origin), str(self.worker))
        self.settings = {"canonical_root": str(self.mac), "remotes": {
            "origin": str(self.origin), "homebase": str(self.homebase)}}
        self.issues = {"pdf-t27": {"status": "in_progress", "metadata": {"execution": {
            "app": "zcode", "branch": "work/zcode/t27", "base": self.base}}}}
        beads_patch = patch.object(relay.c, "bd", return_value=[])
        self.beads = beads_patch.start()
        self.addCleanup(beads_patch.stop)
        for replacement in (patch.object(relay.c, "ROOT", self.mac),
                            patch.object(relay, "config", return_value=self.settings),
                            patch.object(relay.c, "issues_by_id", return_value=self.issues)):
            replacement.start()
            self.addCleanup(replacement.stop)

    def run_git(self, cwd, *args):
        result = subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def commit(self, cwd, text):
        (cwd / "evidence.txt").write_text(text)
        self.run_git(cwd, "add", "evidence.txt")
        self.run_git(cwd, "commit", "-m", text)
        return self.run_git(cwd, "rev-parse", "HEAD")

    def incoming(self, task="t27"):
        self.run_git(self.worker, "checkout", "-b", f"work/zcode/{task}")
        candidate = self.commit(self.worker, "worker and reviewer evidence")
        self.run_git(self.worker, "push", str(self.homebase), f"{candidate}:refs/heads/hb/inkflip/{task}")
        return candidate

    def followup(self):
        grant = {"kind": "followup", "app": "zcode", "branch": "work/zcode/pdf-g78",
                 "base": self.base, "pass": 1, "mode": "audit",
                 "allowed_scope": ["artifacts/followups/pdf-g78"], "instructions": "Audit relay"}
        self.issues["pdf-g78"] = {"status": "in_progress", "metadata": {"execution": grant}}
        config = {"apps": {"zcode": {"branch_prefix": "work/zcode/", "tasks": ["T27"]}},
                  "passes": [{"id": 1, "tasks": ["T27"]}]}
        replacement = patch.object(relay.p, "plan", return_value=config)
        replacement.start()
        self.addCleanup(replacement.stop)
        return grant

    def test_followup_collect_explicit_and_discovered_preserves_checkpoint(self):
        self.followup()
        candidate = self.incoming("pdf-g78")
        result = relay.collect("pdf-g78")["results"]
        self.assertEqual(result, [{"task": "pdf-g78", "status": "collected",
                                  "branch": "work/zcode/pdf-g78", "commit": candidate}])
        self.assertEqual(relay.collect()["results"], [
            {"task": "T27", "status": "waiting"}, {**result[0], "status": "unchanged"}])
        self.assertEqual(self.refs(self.homebase)["refs/heads/hb/inkflip/pdf-g78"], candidate)
        self.assertEqual(self.refs(self.origin)["refs/heads/work/zcode/pdf-g78"], candidate)

    def test_followup_implementation_grant_waits_for_exact_checkpoint(self):
        grant = self.followup()
        grant.update(mode="implementation", allowed_scope=["scripts/homebase_relay.py"])
        self.assertEqual(relay.collect("pdf-g78")["results"], [
            {"task": "pdf-g78", "status": "waiting"}])

    def test_followup_invalid_grants_fail_before_transport(self):
        grant = self.followup()
        for key, value in (("kind", "product"), ("app", "devin"), ("branch", "work/zcode/g78"),
                           ("branch", "work/zcode/pdf-g78-extra"), ("branch", "work/zcode/pdf-g78:main"),
                           ("base", "HEAD"), ("pass", 99), ("pass", True), ("mode", "review"),
                           ("allowed_scope", []), ("allowed_scope", ["../scripts"]),
                           ("instructions", "")):
            with self.subTest(key=key, value=value), patch.dict(grant, {key: value}), \
                    patch.object(relay, "collect_one") as collect:
                with self.assertRaises(ValueError):
                    relay.collect("pdf-g78")
                collect.assert_not_called()
        self.issues["pdf-g78"]["status"] = "closed"
        with self.assertRaises(ValueError):
            relay.collect("pdf-g78")

    def test_followup_identity_and_metadata_are_authoritative(self):
        grant = self.followup()
        for task in ("G78", "PDF-G78", "pdf-t27", "pdf-pass1", "pdf-../g78"):
            with self.subTest(task=task), patch.dict(self.issues, {
                    task: {"status": "in_progress", "metadata": {"execution": grant}}}):
                with self.assertRaises(ValueError):
                    relay.collect(task)
        self.issues["pdf-g78"] = {"status": "in_progress", "execution": grant}
        with self.assertRaises(ValueError):
            relay.collect("pdf-g78")

    def test_followup_rejects_unrelated_history(self):
        self.followup()
        self.run_git(self.worker, "checkout", "--orphan", "unrelated")
        candidate = self.commit(self.worker, "unrelated")
        self.run_git(self.worker, "push", str(self.homebase), f"{candidate}:refs/heads/hb/inkflip/pdf-g78")
        with self.assertRaisesRegex(ValueError, "grant base"):
            relay.collect("pdf-g78")
        self.assertNotIn("refs/heads/work/zcode/pdf-g78", self.refs(self.origin))

    def test_followup_rejects_published_divergence_and_concurrent_update(self):
        self.followup()
        self.incoming("pdf-g78")
        competing = self.commit(self.mac, "competing followup")
        original_git = relay.git

        def race(*args):
            if args[0] == "push":
                self.run_git(self.mac, "push", "origin", f"{competing}:refs/heads/work/zcode/pdf-g78")
            return original_git(*args)

        with patch.object(relay, "git", side_effect=race), self.assertRaises(ValueError):
            relay.collect("pdf-g78")
        with self.assertRaisesRegex(ValueError, "published branch"):
            relay.collect("pdf-g78")
        self.assertEqual(self.refs(self.origin)["refs/heads/work/zcode/pdf-g78"], competing)

    def refs(self, remote):
        output = self.run_git(self.mac, "ls-remote", "--refs", str(remote))
        return {ref: sha for sha, ref in (line.split() for line in output.splitlines())}

    def test_publish_only_published_code_and_native_state_preserving_incoming(self):
        candidate = self.incoming()
        for branch in ("work/zcode/t27", "review/t27", "hb/inkflip/t01", "__dolt_remote_info__"):
            self.run_git(self.mac, "push", "origin", f"{self.base}:refs/heads/{branch}")
        self.run_git(self.mac, "branch", "work/unpublished")
        self.assertEqual(relay.publish()["status"], "published")
        refs = self.refs(self.homebase)
        self.assertEqual(refs, {
            "refs/heads/main": self.base, "refs/heads/work/zcode/t27": self.base,
            "refs/heads/review/t27": self.base, "refs/dolt/data": self.base,
            "refs/heads/hb/inkflip/t27": candidate})
        self.assertEqual(self.run_git(self.mac, "rev-parse", "refs/inkflip/relay/origin/dolt/data"), self.base)
        self.assertEqual(relay.publish()["status"], "published")

    def test_publish_divergence_leaves_all_remote_refs_unchanged(self):
        relay.publish()
        other = self.commit(self.worker, "homebase ahead")
        self.run_git(self.worker, "push", str(self.homebase), f"{other}:refs/heads/main")
        self.run_git(self.mac, "push", "origin", f"{self.base}:refs/heads/work/new")
        before = self.refs(self.homebase)
        with self.assertRaisesRegex(ValueError, "divergence"):
            relay.publish()
        self.assertEqual(self.refs(self.homebase), before)

    def test_publish_rejects_dirty_unpublished_or_non_main(self):
        (self.mac / "dirty").write_text("preserve")
        with self.assertRaisesRegex(ValueError, "clean"):
            relay.publish()
        (self.mac / "dirty").unlink()
        self.commit(self.mac, "unpublished")
        with self.assertRaisesRegex(ValueError, "published main"):
            relay.publish()
        self.run_git(self.mac, "checkout", "-b", "other")
        with self.assertRaisesRegex(ValueError, "requires main"):
            relay.publish()
        self.assertEqual(self.refs(self.homebase), {})

    def test_collect_preserves_sha_author_evidence_and_original_branch(self):
        candidate = self.incoming()
        self.run_git(self.mac, "push", "origin", f"{self.base}:refs/heads/work/zcode/t27")
        result = relay.collect("T27")["results"][0]
        self.assertEqual(result, {"task": "T27", "status": "collected",
                                 "branch": "work/zcode/t27", "commit": candidate})
        self.assertEqual(self.refs(self.origin)["refs/heads/work/zcode/t27"], candidate)
        self.assertNotIn("refs/heads/hb/inkflip/t27", self.refs(self.origin))
        self.assertEqual(self.run_git(self.origin, "show", "-s", "--format=%an <%ae>", candidate),
                         "Worker Actual <worker@example.test>")
        self.assertEqual(self.run_git(self.origin, "show", f"{candidate}:evidence.txt"),
                         "worker and reviewer evidence")
        self.assertEqual(relay.collect()["results"][0]["status"], "unchanged")
        self.assertEqual(self.run_git(self.mac, "rev-parse", "HEAD"), self.base)

    def test_collect_creates_original_branch_when_absent(self):
        candidate = self.incoming()
        relay.collect("T27")
        self.assertEqual(self.refs(self.origin)["refs/heads/work/zcode/t27"], candidate)

    def test_waiting_is_not_transport_failure(self):
        self.assertEqual(relay.collect("T27")["results"], [{"task": "T27", "status": "waiting"}])
        missing = str(self.homebase.parent / "missing.git")
        self.run_git(self.mac, "remote", "set-url", "homebase", missing)
        self.settings["remotes"]["homebase"] = missing
        with self.assertRaises(ValueError):
            relay.collect("T27")

    def test_wrong_app_status_task_branch_and_base_are_rejected(self):
        grant = self.issues["pdf-t27"]["metadata"]["execution"]
        for key, value in (("app", "devin"), ("branch", "main"),
                           ("branch", "work/zcode/t28"), ("branch", "work/zcode/t27:main"),
                           ("base", "HEAD"), ("base", "abc")):
            with self.subTest(key=key, value=value), patch.dict(grant, {key: value}):
                with self.assertRaises(ValueError):
                    relay.collect("T27")
        for task in ("T00", "T56", "t27", "--all"):
            with self.subTest(task=task), self.assertRaises(ValueError):
                relay.collect(task)
        self.issues["pdf-t27"]["status"] = "closed"
        with self.assertRaises(ValueError):
            relay.collect("T27")
        self.assertEqual(relay.collect()["results"], [])

    def test_collect_rejects_non_descendant_of_grant(self):
        self.run_git(self.worker, "checkout", "--orphan", "unrelated")
        unrelated = self.commit(self.worker, "unrelated history")
        self.run_git(self.worker, "push", str(self.homebase), f"{unrelated}:refs/heads/hb/inkflip/t27")
        with self.assertRaisesRegex(ValueError, "grant base"):
            relay.collect("T27")
        self.assertNotIn("refs/heads/work/zcode/t27", self.refs(self.origin))

    def test_collect_rejects_divergent_published_branch(self):
        self.incoming()
        newer = self.commit(self.mac, "independent published work")
        self.run_git(self.mac, "push", "origin", f"{newer}:refs/heads/work/zcode/t27")
        with self.assertRaisesRegex(ValueError, "published branch"):
            relay.collect("T27")
        self.assertEqual(self.refs(self.origin)["refs/heads/work/zcode/t27"], newer)

    def test_remote_identity_and_role_guards(self):
        self.run_git(self.mac, "config", "inkflip.role", "worker")
        with self.assertRaisesRegex(ValueError, "integrator"):
            relay.collect("T27")
        self.run_git(self.mac, "config", "inkflip.role", "integrator")
        self.run_git(self.mac, "remote", "set-url", "--push", "origin", str(self.homebase))
        with self.assertRaisesRegex(ValueError, "push target"):
            relay.collect("T27")
        self.assertEqual(self.refs(self.homebase), {})

    def test_publish_requires_native_state(self):
        self.run_git(self.origin, "update-ref", "-d", "refs/dolt/data")
        with self.assertRaisesRegex(ValueError, "bd dolt push"):
            relay.publish()
        self.assertEqual(self.refs(self.homebase), {})

    def test_publish_rejects_locally_committed_unpublished_grant(self):
        # A pre-existing refs/dolt/data is insufficient: the coordinator's
        # new grant exists in local Beads but was never pushed to origin.
        self.beads.return_value = [{"IssueID": "pdf-g78", "DiffType": "modified"}]
        with self.assertRaisesRegex(ValueError, "bd dolt push"):
            relay.publish()
        self.assertEqual(self.refs(self.homebase), {})
        self.beads.assert_called_with(["diff", "origin/main", "HEAD"])

    def test_publish_fails_closed_when_beads_comparison_is_unavailable(self):
        for value in (None, {}, False, ""):
            with self.subTest(value=value):
                self.beads.return_value = value
                with self.assertRaisesRegex(ValueError, "Beads"):
                    relay.publish()
                self.assertEqual(self.refs(self.homebase), {})
        self.beads.side_effect = ValueError("Beads origin/main unavailable")
        with self.assertRaisesRegex(ValueError, "Beads"):
            relay.publish()
        self.assertEqual(self.refs(self.homebase), {})

    def test_beads_change_during_publication_cannot_report_success(self):
        changed = [{"IssueID": "pdf-g78", "DiffType": "modified"}]
        self.beads.side_effect = [[], changed]
        with self.assertRaisesRegex(ValueError, "bd dolt push"):
            relay.publish()
        self.assertEqual(self.refs(self.homebase), {})
        # A change after the atomic transfer still requires a retry, not a
        # claim that the worker received the newest grant.
        self.beads.side_effect = [[], [], changed]
        with self.assertRaisesRegex(ValueError, "bd dolt push"):
            relay.publish()
        self.assertEqual(self.refs(self.homebase)["refs/dolt/data"], self.base)

    def test_publication_advances_code_and_state_without_following_tags(self):
        relay.publish()
        next_commit = self.commit(self.mac, "published advance")
        self.run_git(self.mac, "push", "origin", "main", f"{next_commit}:refs/dolt/data")
        self.run_git(self.mac, "tag", "-a", "local-only", "-m", "not for relay")
        self.run_git(self.mac, "config", "push.followTags", "true")
        relay.publish()
        refs = self.refs(self.homebase)
        self.assertEqual(refs["refs/dolt/data"], next_commit)
        self.assertEqual(refs["refs/heads/main"], next_commit)
        self.assertNotIn("refs/tags/local-only", refs)

    def test_parentless_native_state_rollover_and_repeat_publication(self):
        relay.publish()
        tree = self.run_git(self.mac, "rev-parse", "HEAD^{tree}")
        rollover = self.run_git(self.mac, "commit-tree", tree, "-m", "Dolt transport rollover")
        self.assertEqual(self.run_git(self.mac, "rev-list", "--parents", "-n", "1", rollover), rollover)
        self.run_git(self.mac, "push", f"--force-with-lease=refs/dolt/data:{self.base}",
                     "origin", f"{rollover}:refs/dolt/data")
        self.assertEqual(relay.publish()["status"], "published")
        expected = self.refs(self.homebase)
        self.assertEqual(expected["refs/dolt/data"], rollover)
        self.assertEqual(expected["refs/heads/main"], self.base)
        self.assertEqual(self.run_git(self.mac, "rev-parse", "refs/inkflip/relay/origin/dolt/data"), rollover)
        self.assertEqual(relay.publish()["status"], "published")
        self.assertEqual(self.refs(self.homebase), expected)
        self.assertEqual(self.run_git(self.mac, "rev-parse", "refs/inkflip/relay/homebase/dolt/data"), rollover)

    def assert_state_lease_race(self, existing):
        if existing:
            relay.publish()
        before = self.refs(self.homebase)
        tree = self.run_git(self.mac, "rev-parse", "HEAD^{tree}")
        rollover = self.run_git(self.mac, "commit-tree", tree, "-m", "published state rollover")
        competing = self.run_git(self.worker, "commit-tree", tree, "-m", "concurrent state rollover")
        self.run_git(self.mac, "push", f"--force-with-lease=refs/dolt/data:{self.base}",
                     "origin", f"{rollover}:refs/dolt/data")
        new_main = self.commit(self.mac, "next main")
        self.run_git(self.mac, "push", "origin", "main")
        original_git = relay.git

        def race(*args):
            if args[0] == "push":
                old = before.get("refs/dolt/data", "")
                self.run_git(self.worker, "push", f"--force-with-lease=refs/dolt/data:{old}",
                             str(self.homebase), f"{competing}:refs/dolt/data")
                # Even refreshing the local cache must not weaken the exact lease.
                self.run_git(self.mac, "fetch", "--no-tags", "homebase",
                             "+refs/dolt/data:refs/inkflip/relay/homebase/dolt/data")
            return original_git(*args)

        with patch.object(relay, "git", side_effect=race), self.assertRaises(ValueError):
            relay.publish()
        self.assertEqual(self.refs(self.homebase), {**before, "refs/dolt/data": competing})
        self.assertEqual(relay.publish()["status"], "published")
        expected = {"refs/heads/main": new_main, "refs/dolt/data": rollover}
        self.assertEqual(self.refs(self.homebase), expected)
        self.assertEqual(relay.publish()["status"], "published")
        self.assertEqual(self.refs(self.homebase), expected)

    def test_existing_state_lease_race_is_atomic_and_retryable(self):
        self.assert_state_lease_race(existing=True)

    def test_missing_state_lease_race_is_atomic_and_retryable(self):
        self.assert_state_lease_race(existing=False)

    def test_state_lease_does_not_force_concurrent_source_branch(self):
        relay.publish()
        tree = self.run_git(self.mac, "rev-parse", "HEAD^{tree}")
        rollover = self.run_git(self.mac, "commit-tree", tree, "-m", "state rollover")
        self.run_git(self.mac, "push", f"--force-with-lease=refs/dolt/data:{self.base}",
                     "origin", f"{rollover}:refs/dolt/data")
        self.commit(self.mac, "published main advance")
        self.run_git(self.mac, "push", "origin", "main")
        competing = self.commit(self.worker, "concurrent main advance")
        original_git = relay.git

        def race(*args):
            if args[0] == "push":
                self.run_git(self.worker, "push", str(self.homebase), f"{competing}:refs/heads/main")
            return original_git(*args)

        with patch.object(relay, "git", side_effect=race), self.assertRaises(ValueError):
            relay.publish()
        self.assertEqual(self.refs(self.homebase), {
            "refs/heads/main": competing, "refs/dolt/data": self.base})

    def test_collect_normal_push_rejects_concurrent_origin_update(self):
        self.incoming()
        competing = self.commit(self.mac, "concurrent candidate")
        original_git = relay.git

        def race(*args):
            if args[0] == "push":
                self.run_git(self.mac, "push", "origin", f"{competing}:refs/heads/work/zcode/t27")
            return original_git(*args)

        with patch.object(relay, "git", side_effect=race), self.assertRaises(ValueError):
            relay.collect("T27")
        self.assertEqual(self.refs(self.origin)["refs/heads/work/zcode/t27"], competing)

    def test_canonical_path_guard(self):
        self.settings["canonical_root"] = str(self.worker)
        with self.assertRaisesRegex(ValueError, "canonical"):
            relay.collect("T27")

    def test_real_linked_checkout_is_rejected_with_matching_config(self):
        self.assertEqual(relay.c.canonical_root(), self.mac.resolve())
        linked = self.mac.parent / "linked"
        self.run_git(self.mac, "worktree", "add", "-b", "linked-review", str(linked))
        self.settings["canonical_root"] = str(linked)
        with patch.object(relay.c, "ROOT", linked):
            self.assertEqual(relay.c.canonical_root(), self.mac.resolve())
            with self.assertRaisesRegex(ValueError, "linked worktree"):
                relay.publish()
            with self.assertRaisesRegex(ValueError, "linked worktree"):
                relay.collect("T27")
        self.assertEqual(self.refs(self.homebase), {})

    def test_publish_atomic_rejection_and_json_failure(self):
        # A receiving hook rejects state: no branch is published by atomic push.
        hook = self.homebase / "hooks/update"
        hook.write_text('#!/bin/sh\n[ "$1" != "refs/dolt/data" ]\n')
        hook.chmod(0o755)
        output = StringIO()
        with patch.object(sys, "argv", ["homebase_relay.py", "publish"]), redirect_stdout(output):
            self.assertEqual(relay.main(), 1)
        self.assertEqual(json.loads(output.getvalue())["status"], "error")
        self.assertEqual(self.refs(self.homebase), {})


class FollowupDiscoveryTests(unittest.TestCase):
    def test_discovery_preserves_followup_id_and_product_name(self):
        issues = {key: {"status": "in_progress", "metadata": {"execution": {"app": "zcode"}}}
                  for key in ("pdf-g78", "pdf-t27")}
        with patch.object(relay, "validate_clone"), patch.object(relay.c, "issues_by_id", return_value=issues), \
                patch.object(relay, "grant_for", return_value={}) as grant, \
                patch.object(relay, "collect_one", return_value={}) as collect:
            relay.collect()
        self.assertEqual([call.args[0] for call in grant.call_args_list], ["T27", "pdf-g78"])
        self.assertEqual([call.args[0] for call in collect.call_args_list], ["T27", "pdf-g78"])

    def test_malformed_records_fail_before_any_collection(self):
        for record in (None, [], {"status": "in_progress", "metadata": []},
                       {"status": "in_progress", "metadata": {"execution": []}},
                       {"status": "in_progress", "metadata": {"execution": None}},
                       {"status": "in_progress", "metadata": {"execution": {}}}):
            with self.subTest(record=record), patch.object(relay, "validate_clone"), \
                    patch.object(relay.c, "issues_by_id", return_value={"pdf-g78": record}), \
                    patch.object(relay, "collect_one") as collect:
                with self.assertRaises(ValueError):
                    relay.collect()
                collect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
