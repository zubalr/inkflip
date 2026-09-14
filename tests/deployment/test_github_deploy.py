"""Guardrails for the GitHub → Vercel production path.

This does not talk to Vercel. It pins the workflow so production deploys
only follow a successful `verify` push to main, use --prebuilt, and never
run on pull_request.
"""
from __future__ import annotations

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "deploy-web.yml"


class GitHubDeployWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = WORKFLOW.read_text()

    def test_workflow_file_exists(self) -> None:
        self.assertTrue(WORKFLOW.is_file(), WORKFLOW)

    def test_triggered_only_after_verify_on_main_push(self) -> None:
        self.assertIn("workflow_run:", self.text)
        self.assertIn("workflows: [verify]", self.text)
        self.assertIn("github.event.workflow_run.head_branch == 'main'", self.text)
        self.assertIn("github.event.workflow_run.event == 'push'", self.text)
        self.assertIn("github.event.workflow_run.conclusion == 'success'", self.text)
        self.assertNotIn("pull_request:", self.text)
        self.assertNotIn("vercel git connect", self.text)

    def test_uses_frozen_bun_python_prebuilt_path(self) -> None:
        self.assertIn("bun-version: 1.4.0", self.text)
        self.assertIn("bun install --frozen-lockfile", self.text)
        self.assertIn("bun run build", self.text)
        self.assertIn("scripts/vercel_output.py prepare", self.text)
        self.assertIn("scripts/vercel_output.py check", self.text)
        self.assertIn("deploy --prebuilt --prod --yes", self.text)
        self.assertNotIn("npm install", self.text)
        self.assertNotIn("npm run build", self.text)

    def test_least_privilege_and_concurrency(self) -> None:
        self.assertIn("contents: read", self.text)
        self.assertIn("group: vercel-production", self.text)
        self.assertIn("cancel-in-progress: true", self.text)
        self.assertIn("environment: production", self.text)
        self.assertIn("secrets.VERCEL_TOKEN", self.text)
        self.assertNotIn("echo $VERCEL_TOKEN", self.text)
        self.assertNotIn("echo \"$VERCEL_TOKEN\"", self.text)

    def test_pins_the_existing_inkflip_project(self) -> None:
        self.assertIn("prj_sEtj12msmLcppTxQu8qpbqiXJrL0", self.text)
        self.assertIn("team_2UPHADaxTemfNa0cbgC08Eyy", self.text)
        self.assertIn("ref: ${{ github.event.workflow_run.head_sha }}", self.text)


if __name__ == "__main__":
    unittest.main()
