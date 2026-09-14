"""Guardrails for the GitHub → Vercel production path.

Exercises the real decision script with current vs stale SHAs and rejected
source events. A SKIP/REJECT result is what prevents publish — not a search
of workflow YAML for cancel-in-progress.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import github_deploy_guard as guard  # noqa: E402

WORKFLOW = REPO_ROOT / ".github" / "workflows" / "deploy-web.yml"
GUARD = REPO_ROOT / "scripts" / "github_deploy_guard.py"
SMOKE = REPO_ROOT / "tests" / "deployment" / "prepublish-smoke.cjs"
CURRENT = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
OLDER = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


def run_guard(**kwargs: str) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, str(GUARD)]
    for key, value in kwargs.items():
        cmd.extend([f"--{key.replace('_', '-')}", value])
    return subprocess.run(cmd, capture_output=True, text=True, timeout=20)


class DeployGuardDecisionTests(unittest.TestCase):
    def test_current_main_may_continue(self) -> None:
        self.assertEqual(
            guard.decide(
                trigger_event="push",
                trigger_branch="main",
                trigger_conclusion="success",
                trigger_sha=CURRENT,
                current_main_sha=CURRENT,
                phase="before_work",
            ),
            guard.CONTINUE,
        )

    def test_stale_sha_skips_before_expensive_work(self) -> None:
        self.assertEqual(
            guard.decide(
                trigger_event="push",
                trigger_branch="main",
                trigger_conclusion="success",
                trigger_sha=OLDER,
                current_main_sha=CURRENT,
                phase="before_work",
            ),
            guard.SKIP,
        )

    def test_stale_sha_skips_immediately_before_promote(self) -> None:
        self.assertEqual(
            guard.decide(
                trigger_event="push",
                trigger_branch="main",
                trigger_conclusion="success",
                trigger_sha=OLDER,
                current_main_sha=CURRENT,
                phase="before_promote",
                candidate_id="dpl_ReadyCandidate",
            ),
            guard.SKIP,
        )

    def test_pull_request_is_rejected(self) -> None:
        self.assertEqual(
            guard.decide(
                trigger_event="pull_request",
                trigger_branch="main",
                trigger_conclusion="success",
                trigger_sha=CURRENT,
                current_main_sha=CURRENT,
                phase="before_work",
            ),
            guard.REJECT,
        )

    def test_feature_branch_push_is_rejected(self) -> None:
        self.assertEqual(
            guard.decide(
                trigger_event="push",
                trigger_branch="work/cursor/launch-polish",
                trigger_conclusion="success",
                trigger_sha=CURRENT,
                current_main_sha=CURRENT,
                phase="before_work",
            ),
            guard.REJECT,
        )

    def test_failed_verify_is_rejected(self) -> None:
        self.assertEqual(
            guard.decide(
                trigger_event="push",
                trigger_branch="main",
                trigger_conclusion="failure",
                trigger_sha=CURRENT,
                current_main_sha=CURRENT,
                phase="before_work",
            ),
            guard.REJECT,
        )

    def test_promote_without_candidate_is_rejected(self) -> None:
        self.assertEqual(
            guard.decide(
                trigger_event="push",
                trigger_branch="main",
                trigger_conclusion="success",
                trigger_sha=CURRENT,
                current_main_sha=CURRENT,
                phase="before_promote",
            ),
            guard.REJECT,
        )

    def test_promote_of_current_candidate_continues(self) -> None:
        self.assertEqual(
            guard.decide(
                trigger_event="push",
                trigger_branch="main",
                trigger_conclusion="success",
                trigger_sha=CURRENT,
                current_main_sha=CURRENT,
                phase="before_promote",
                candidate_id="https://inkflip-candidate.vercel.app",
            ),
            guard.CONTINUE,
        )


class DeployGuardCliTests(unittest.TestCase):
    def test_cli_skip_is_success_and_not_continue(self) -> None:
        proc = run_guard(
            phase="before_work",
            trigger_event="push",
            trigger_branch="main",
            trigger_conclusion="success",
            trigger_sha=OLDER,
            current_main_sha=CURRENT,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), guard.SKIP)
        self.assertNotEqual(proc.stdout.strip(), guard.CONTINUE)

    def test_cli_rejected_event_fails_closed(self) -> None:
        proc = run_guard(
            phase="before_work",
            trigger_event="pull_request",
            trigger_branch="main",
            trigger_conclusion="success",
            trigger_sha=CURRENT,
            current_main_sha=CURRENT,
        )
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertEqual(proc.stdout.strip(), guard.REJECT)

    def test_cli_writes_github_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "github_output"
            env = os.environ.copy()
            env["GITHUB_OUTPUT"] = str(output)
            proc = subprocess.run(
                [
                    sys.executable,
                    str(GUARD),
                    "--phase",
                    "before_work",
                    "--trigger-event",
                    "push",
                    "--trigger-branch",
                    "main",
                    "--trigger-conclusion",
                    "success",
                    "--trigger-sha",
                    CURRENT,
                    "--current-main-sha",
                    CURRENT,
                ],
                capture_output=True,
                text=True,
                timeout=20,
                env=env,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(output.read_text(), "decision=CONTINUE\n")

    def test_cli_refuses_promote_when_candidate_missing(self) -> None:
        proc = run_guard(
            phase="before_promote",
            trigger_event="push",
            trigger_branch="main",
            trigger_conclusion="success",
            trigger_sha=CURRENT,
            current_main_sha=CURRENT,
        )
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout.strip(), guard.REJECT)


class WorkflowWiresTheGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = WORKFLOW.read_text()

    def test_workflow_invokes_the_guard_twice(self) -> None:
        self.assertGreaterEqual(self.text.count("scripts/github_deploy_guard.py"), 2)
        self.assertIn("--phase before_work", self.text)
        self.assertIn("--phase before_promote", self.text)
        self.assertIn("steps.guard.outputs.decision == 'CONTINUE'", self.text)

    def test_candidate_is_not_aliased_until_promote(self) -> None:
        self.assertIn("deploy --prebuilt --prod --skip-domain --yes", self.text)
        self.assertIn("vercel@59.16.0 promote", self.text)
        self.assertNotIn("deploy --prebuilt --prod --yes", self.text)
        self.assertIn("cancel-in-progress: false", self.text)
        self.assertIn("group: vercel-production-promote", self.text)

    def test_prepublish_smoke_runs_before_upload(self) -> None:
        self.assertTrue(SMOKE.is_file(), SMOKE)
        self.assertIn("tests/deployment/prepublish-smoke.cjs", self.text)
        smoke_at = self.text.index("tests/deployment/prepublish-smoke.cjs")
        deploy_at = self.text.index("deploy --prebuilt --prod --skip-domain")
        self.assertLess(smoke_at, deploy_at)

    def test_pr_and_npm_defaults_remain_ineligible(self) -> None:
        self.assertIn("workflow_run:", self.text)
        self.assertIn("workflows: [verify]", self.text)
        self.assertNotIn("pull_request:", self.text)
        self.assertNotIn("vercel git connect", self.text)
        self.assertNotIn("npm install", self.text)
        self.assertIn("contents: read", self.text)
        self.assertIn("secrets.VERCEL_TOKEN", self.text)
        self.assertNotIn("echo $VERCEL_TOKEN", self.text)
        self.assertNotIn('echo "$VERCEL_TOKEN"', self.text)


if __name__ == "__main__":
    unittest.main()
