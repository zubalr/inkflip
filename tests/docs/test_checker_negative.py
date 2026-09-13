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
        "required_phrases": {},
        "version_pins": [
            {
                "name": "pdfjs-dist",
                "doc_pattern": r"PDF\.js\s+([0-9]+\.[0-9]+\.[0-9]+)",
                "pin_file": "apps/web/package.json",
                "pin_json_path": "dependencies.pdfjs-dist",
            }
        ],
        "snapshot_facts_file": "tests/docs/snapshot-facts.json",
    }
    rules.update(overrides)
    return rules


def write_widget_fact(root: Path, *, available: bool, as_of: str = "2026-09-13"):
    """Write a coherent fact set (evidence + facts file + doc) for one state."""
    if available:
        evidence = "# Widget log\n\nwidget-status: available as of 2026-09-14\n"
        doc_state = "The widget works now."
        must_contain = ["widget works"]
        must_not_contain = ["widget is unavailable"]
    else:
        evidence = "# Widget log\n\nwidget-status: unavailable as of 2026-09-13\n"
        doc_state = "The widget is unavailable."
        must_contain = ["widget is unavailable"]
        must_not_contain = ["widget works"]
    (root / "evidence" / "widget.log").parent.mkdir(parents=True, exist_ok=True)
    (root / "evidence" / "widget.log").write_text(evidence)
    facts = {
        "facts": [
            {
                "id": "widget-state",
                "as_of": as_of,
                "claim": "widget availability state",
                "evidence": "evidence/widget.log",
                "evidence_marker": f"widget-status: {'available' if available else 'unavailable'}",
                "per_doc": {
                    "README.md": {
                        "must_contain": must_contain,
                        "must_not_contain": must_not_contain,
                    }
                },
            }
        ]
    }
    (root / "tests" / "docs").mkdir(parents=True, exist_ok=True)
    (root / "tests" / "docs" / "snapshot-facts.json").write_text(json.dumps(facts))
    (root / "README.md").write_text(doc_state)


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

    def test_snapshot_fact_missing_evidence_marker_fails(self):
        write_widget_fact(self.root, available=False)
        # Evidence no longer carries the marker the fact cites (stale fact).
        (self.root / "evidence" / "widget.log").write_text("# Widget log\n\n(empty)\n")
        problems = check_claims.check_snapshot_facts(self.root, make_rules())
        self.assertTrue(any("lacks marker" in p for p in problems), msg=problems)

    def test_snapshot_fact_doc_omits_recorded_fact_fails(self):
        write_widget_fact(self.root, available=False)
        self.write("README.md", "nothing about the widget")
        problems = check_claims.check_snapshot_facts(self.root, make_rules())
        self.assertTrue(any("no longer states the fact" in p for p in problems), msg=problems)

    def test_snapshot_fact_doc_contradicts_recorded_state_fails(self):
        write_widget_fact(self.root, available=False)
        self.write("README.md", "The widget is unavailable. The widget works.")
        problems = check_claims.check_snapshot_facts(self.root, make_rules())
        self.assertTrue(any("contradicts the recorded state" in p for p in problems), msg=problems)

    def test_snapshot_fact_consistent_state_passes(self):
        write_widget_fact(self.root, available=False)
        self.assertEqual(check_claims.check_snapshot_facts(self.root, make_rules()), [])

    def test_snapshot_fact_legitimate_state_transition_passes(self):
        """A reviewed state change must not be blocked by the checker: update
        evidence, facts file and docs together and the check passes."""
        write_widget_fact(self.root, available=False)
        self.assertEqual(check_claims.check_snapshot_facts(self.root, make_rules()), [])
        # The widget ships for real: evidence gains a dated entry, the facts
        # file records the new state, and the doc is rewritten to match.
        write_widget_fact(self.root, available=True, as_of="2026-09-14")
        self.assertEqual(check_claims.check_snapshot_facts(self.root, make_rules()), [])

    def test_transition_without_updating_facts_file_fails(self):
        """Doc and evidence move to the new state but the facts file still
        records the old one — a mismatched state must fail."""
        write_widget_fact(self.root, available=False)
        (self.root / "evidence" / "widget.log").write_text(
            "# Widget log\n\nwidget-status: available as of 2026-09-14\n"
        )
        self.write("README.md", "The widget works now.")
        problems = check_claims.check_snapshot_facts(self.root, make_rules())
        self.assertTrue(problems, msg="stale facts file must be detected")
        self.assertTrue(
            any("lacks marker" in p or "no longer states" in p for p in problems), msg=problems
        )

    def test_clean_tree_passes_all_checks(self):
        self.write(
            "apps/web/package.json",
            json.dumps({"dependencies": {"pdfjs-dist": "6.3.289"}}),
        )
        (self.root / "config").mkdir()
        (self.root / "config" / "acceptance-commands.json").write_text(
            json.dumps({"commands": {"verify": {}}})
        )
        write_widget_fact(self.root, available=False)
        self.write(
            "README.md",
            "The widget is unavailable. not a claim about PDFs in general. "
            "run `bun run verify`.\n## Heading\n[internal](#heading)\n",
        )
        rules = make_rules()
        for name, fn in check_claims.CHECKS:
            self.assertEqual(fn(self.root, rules), [], msg=f"{name} should be clean")


if __name__ == "__main__":
    unittest.main()
