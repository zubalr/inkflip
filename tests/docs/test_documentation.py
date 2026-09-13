"""Documentation checks for the public Inkflip docs (T49).

The real assertions live in scripts/check_claims.py and its data file
tests/docs/claims-rules.json; this suite invokes the actual CLI so the tests
exercise the same tool a contributor runs. The negative cases in
test_checker_negative.py prove the checker can fail, so a green run here is
meaningful rather than self-approving.
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKER = REPO_ROOT / "scripts" / "check_claims.py"


class DocumentationChecks(unittest.TestCase):
    """The public documentation must pass the mechanical claims checks."""

    def test_check_claims_cli_passes_on_this_tree(self):
        proc = subprocess.run(
            [sys.executable, str(CHECKER)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(
            proc.returncode,
            0,
            f"check_claims.py reported problems:\n{proc.stdout}\n{proc.stderr}",
        )

    def test_check_claims_json_report_is_wellformed_and_ok(self):
        proc = subprocess.run(
            [sys.executable, str(CHECKER), "--json"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["ok"], msg=json.dumps(payload["report"], indent=2))
        for check in ("required_docs", "links", "referenced_files", "version_pins",
                      "registry_commands", "forbidden_phrases", "required_phrases",
                      "snapshot_facts"):
            self.assertIn(check, payload["report"])
            self.assertEqual(payload["report"][check], [], msg=f"{check} reported problems")

    def test_rules_file_covers_the_required_surface(self):
        rules = json.loads((REPO_ROOT / "tests" / "docs" / "claims-rules.json").read_text())
        self.assertTrue(rules["required_docs"], "no required docs configured")
        self.assertTrue(rules["forbidden_phrases"], "forbidden claim list is empty")
        self.assertGreaterEqual(len(rules["version_pins"]), 3, "too few version pin rules")
        self.assertTrue(rules["snapshot_facts_file"], "snapshot facts file not configured")

    def test_snapshot_facts_are_dated_and_source_bound(self):
        facts = json.loads((REPO_ROOT / "tests" / "docs" / "snapshot-facts.json").read_text())
        self.assertTrue(facts["facts"], "no snapshot facts configured")
        for fact in facts["facts"]:
            self.assertIn("as_of", fact, f"fact {fact.get('id')} lacks as_of date")
            self.assertIn("evidence", fact, f"fact {fact.get('id')} lacks evidence path")
            self.assertTrue(
                (REPO_ROOT / fact["evidence"]).is_file(),
                f"fact {fact.get('id')} evidence file does not exist",
            )


if __name__ == "__main__":
    unittest.main()
