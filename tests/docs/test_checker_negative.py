"""Negative tests: the claims checker must FAIL on broken documentation.

A checker that cannot fail is decoration. Each case builds a minimal
documentation tree with one deliberate defect and asserts the corresponding
check reports it. This is what keeps a green run of test_documentation.py
meaningful — the same functions are used against the real tree.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKER_PATH = REPO_ROOT / "scripts" / "check_claims.py"

_spec = importlib.util.spec_from_file_location("check_claims", CHECKER_PATH)
check_claims = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_claims)


def make_rules(**overrides) -> dict:
    rules = {
        "required_docs": ["README.md"],
        "checked_docs": ["README.md"],
        "forbidden_phrases": ["what AI sees"],
        "version_pins": [
            {
                "name": "pdfjs-dist",
                "doc_pattern": r"PDF\.js\s+([0-9]+\.[0-9]+\.[0-9]+)",
                "pin_file": "apps/web/package.json",
                "pin_json_path": "dependencies.pdfjs-dist",
            }
        ],
        "license_rules": {
            "must_match": {"README.md": "pending"},
            "must_not_match": {"README.md": r"licen[cs]ed under (the )?MIT"},
        },
        "doc_facts": {
            "README.md": {"must_contain": ["the widget works"], "must_not_contain": ["the widget is perfect"]}
        },
    }
    rules.update(overrides)
    return rules


class CheckerNegativeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "docs").mkdir()

    def write(self, rel: str, content: str):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def test_missing_required_doc_fails(self):
        problems = check_claims.check_required_docs(self.root, make_rules())
        self.assertTrue(any("missing required documentation file: README.md" in p for p in problems))

    def test_broken_local_link_fails(self):
        self.write("README.md", "[guide](docs/guide.md)")
        problems = check_claims.check_links(self.root, make_rules())
        self.assertTrue(any("broken link target" in p for p in problems))

    def test_missing_anchor_fails(self):
        self.write("README.md", "[section](README.md#no-such-heading)\n\n## Real heading\n")
        problems = check_claims.check_links(self.root, make_rules())
        self.assertTrue(any("missing heading #no-such-heading" in p for p in problems))

    def test_broken_internal_anchor_fails(self):
        self.write("README.md", "[section](#nope)\n\n## Real heading\n")
        problems = check_claims.check_links(self.root, make_rules())
        self.assertTrue(any("missing internal heading #nope" in p for p in problems))

    def test_missing_artifact_reference_fails(self):
        self.write("README.md", "see artifacts/gates/G9/receipt.md for details")
        problems = check_claims.check_referenced_files(self.root, make_rules())
        self.assertTrue(any("referenced evidence path does not exist" in p for p in problems))

    def test_wrong_quoted_version_fails(self):
        self.write(
            "apps/web/package.json",
            json.dumps({"dependencies": {"pdfjs-dist": "6.3.289"}}),
        )
        self.write("README.md", "built on PDF.js 9.9.9 rendering")
        problems = check_claims.check_versions(self.root, make_rules())
        self.assertTrue(
            any("quotes pdfjs-dist version 9.9.9" in p for p in problems),
            msg=problems,
        )

    def test_command_not_in_registry_fails(self):
        (self.root / "config").mkdir()
        (self.root / "config" / "acceptance-commands.json").write_text(
            json.dumps({"commands": {"verify": {}}})
        )
        self.write("README.md", "run `bun run make-money` now")
        problems = check_claims.check_registry_commands(self.root, make_rules())
        self.assertTrue(any("'bun run make-money' is not in the command registry" in p for p in problems))

    def test_web_context_command_checked_against_apps_web(self):
        (self.root / "config").mkdir()
        (self.root / "config" / "acceptance-commands.json").write_text(json.dumps({"commands": {}}))
        (self.root / "apps" / "web").mkdir(parents=True)
        (self.root / "apps" / "web" / "package.json").write_text(json.dumps({"scripts": {"dev": "vite"}}))
        self.write("README.md", "cd apps/web && bun run dev")
        problems = check_claims.check_registry_commands(self.root, make_rules())
        self.assertEqual(problems, [])

    def test_forbidden_phrase_fails(self):
        self.write("README.md", "our OCR shows what AI sees inside your document")
        problems = check_claims.check_forbidden_phrases(self.root, make_rules())
        self.assertTrue(any("what AI sees" in p for p in problems))

    def test_asserted_license_fails(self):
        self.write("README.md", "pending decision note. Inkflip is licensed under MIT.")
        problems = check_claims.check_pending_license_recorded(self.root, make_rules())
        self.assertTrue(any("asserts a completed license" in p for p in problems))

    def test_missing_pending_license_record_fails(self):
        self.write("README.md", "no licensing status mentioned here at all")
        problems = check_claims.check_pending_license_recorded(self.root, make_rules())
        self.assertTrue(any("pending licensing decision is not recorded" in p for p in problems))

    def test_contradicted_doc_fact_fails(self):
        self.write("README.md", "the widget is perfect")
        problems = check_claims.check_doc_facts(self.root, make_rules())
        self.assertTrue(any("contradicted fact pattern present" in p for p in problems))

    def test_missing_required_fact_fails(self):
        self.write("README.md", "nothing about the widget")
        problems = check_claims.check_doc_facts(self.root, make_rules())
        self.assertTrue(any("required fact pattern absent" in p for p in problems))

    def test_clean_tree_passes_all_checks(self):
        self.write(
            "apps/web/package.json",
            json.dumps({"dependencies": {"pdfjs-dist": "6.3.289"}}),
        )
        (self.root / "config").mkdir()
        (self.root / "config" / "acceptance-commands.json").write_text(
            json.dumps({"commands": {"verify": {}}})
        )
        self.write(
            "README.md",
            "pending licensing note. the widget works. run `bun run verify`.\n"
            "## Heading\n[internal](#heading)\n",
        )
        rules = make_rules()
        for name, fn in check_claims.CHECKS:
            self.assertEqual(fn(self.root, rules), [], msg=f"{name} should be clean")


if __name__ == "__main__":
    unittest.main()
