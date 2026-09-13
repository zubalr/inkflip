"""G3 scenario preflight: real CLI against a disposable output root (T52).

This is not the authoritative gate.py G3 run. Prerequisite receipts and
acceptance remain Devin's. Do not treat these passing scenarios as a gate
receipt.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NATIVE = ROOT / "native"
FIXTURES = ROOT / "fixtures" / "public"
EXAMPLE = ROOT / "examples" / "reader-upgrade"

import sys

if str(NATIVE) not in sys.path:
    sys.path.insert(0, str(NATIVE))

from inkflip.cli.main import (  # noqa: E402
    EXIT_INVALID_ARGS,
    EXIT_OK,
    EXIT_PARTIAL_RUN,
    EXIT_POLICY_FAILURE,
    EXIT_READ_FAILURE,
    main,
)
from inkflip.contracts import core  # noqa: E402


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest(entries, directory: Path) -> Path:
    body = {
        "kind": "corpus_manifest",
        "schema_version": "1.0.0",
        "entries": entries,
        "source_root_policy": "explicit_local_root_no_symlinks",
        "split": "development",
    }
    path = directory / "corpus.json"
    path.write_text(json.dumps(body))
    return path


class TestG3Scenarios(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="inkflip-g3-")
        self.td = Path(self.tmp.name)
        self.src = self.td / "src"
        self.src.mkdir()
        shutil.copyfile(FIXTURES / "mapping-control.pdf", self.src / "mapping-control.pdf")
        shutil.copyfile(FIXTURES / "mapping-amount.pdf", self.src / "mapping-amount.pdf")
        (self.src / "bad.pdf").write_bytes(b"%PDF-1.4\nbroken")

    def tearDown(self):
        self.tmp.cleanup()

    def test_inspect_named_readers(self):
        pdfium_out = self.td / "pdfium.json"
        pypdf_out = self.td / "pypdf.json"
        self.assertEqual(
            main(["inspect", str(self.src / "mapping-control.pdf"), "--out", str(pdfium_out), "--reader", "pdfium"]),
            EXIT_OK,
        )
        self.assertEqual(
            main(["inspect", str(self.src / "mapping-control.pdf"), "--out", str(pypdf_out), "--reader", "pypdf"]),
            EXIT_OK,
        )
        left = json.loads(pdfium_out.read_text())
        right = json.loads(pypdf_out.read_text())
        core.validate(left)
        core.validate(right)
        self.assertEqual(left["document"]["sha256"], right["document"]["sha256"])
        self.assertNotEqual(left["readers"][0]["id"], right["readers"][0]["id"])

    def test_corpus_partial_failure_keeps_success_and_resume(self):
        entries = [
            {
                "key": "ok-file",
                "source_path": "mapping-control.pdf",
                "sha256": _sha(self.src / "mapping-control.pdf"),
                "group_id": "g3",
                "pages": [0],
            },
            {
                "key": "bad-file",
                "source_path": "bad.pdf",
                "sha256": _sha(self.src / "bad.pdf"),
                "group_id": "g3",
                "pages": [0],
            },
        ]
        man = _manifest(entries, self.td)
        out = self.td / "corpus-out"
        code = main(
            [
                "corpus",
                "run",
                "--manifest",
                str(man),
                "--source-root",
                str(self.src),
                "--profile",
                "native-default",
                "--out",
                str(out),
            ]
        )
        self.assertEqual(code, EXIT_PARTIAL_RUN)
        good = out / "reports" / "ok-file.json"
        self.assertTrue(good.is_file())
        good_bytes = good.read_bytes()
        core.validate(json.loads(good_bytes))
        index = json.loads((out / "index.json").read_text())
        self.assertEqual(index["jobs"]["ok-file"]["status"], "completed")
        self.assertNotEqual(index["jobs"]["bad-file"]["status"], "completed")

        resume = main(
            [
                "corpus",
                "run",
                "--manifest",
                str(man),
                "--source-root",
                str(self.src),
                "--profile",
                "native-default",
                "--out",
                str(out),
                "--resume",
            ]
        )
        self.assertEqual(resume, EXIT_PARTIAL_RUN)
        self.assertEqual(good.read_bytes(), good_bytes)

    def test_immutable_baseline_and_declared_regression(self):
        man = _manifest(
            [
                {
                    "key": "mapping-control",
                    "source_path": "mapping-control.pdf",
                    "sha256": _sha(self.src / "mapping-control.pdf"),
                    "group_id": "g3",
                    "pages": [0],
                }
            ],
            self.td,
        )
        run_out = self.td / "before-run"
        self.assertEqual(
            main(
                [
                    "corpus",
                    "run",
                    "--manifest",
                    str(man),
                    "--source-root",
                    str(self.src),
                    "--profile",
                    "native-default",
                    "--out",
                    str(run_out),
                ]
            ),
            EXIT_OK,
        )
        rules = EXAMPLE / "upgrade-rules.json"
        baseline = self.td / "baseline.json"
        self.assertEqual(
            main(
                [
                    "baseline",
                    "create",
                    "--run",
                    str(run_out),
                    "--rules",
                    str(rules),
                    "--out",
                    str(baseline),
                    "--approved-by",
                    "g3-preflight",
                    "--rationale",
                    "Disposable G3 scenario baseline",
                ]
            ),
            EXIT_OK,
        )
        before = baseline.read_bytes()
        again = main(
            [
                "baseline",
                "create",
                "--run",
                str(run_out),
                "--rules",
                str(rules),
                "--out",
                str(baseline),
                "--approved-by",
                "g3-preflight",
                "--rationale",
                "should refuse",
            ]
        )
        self.assertEqual(again, EXIT_INVALID_ARGS)
        self.assertEqual(baseline.read_bytes(), before)

        mutated = self.td / "mutated"
        shutil.copytree(run_out, mutated)
        report_path = mutated / "reports" / "mapping-control.json"
        report = json.loads(report_path.read_text())
        for occ in report.get("occurrences", []):
            occ["raw_text"] = occ.get("raw_text", "").replace("$100", "$999")
            occ["normalized_text"], occ["normalization_map"] = core.normalize(occ["raw_text"])
        report = core.seal(report)
        report_path.write_text(json.dumps(report, indent=2) + "\n")
        cmp_out = self.td / "cmp"
        code = main(
            [
                "compare",
                str(baseline),
                str(mutated),
                "--rules",
                str(rules),
                "--out",
                str(cmp_out),
            ]
        )
        self.assertEqual(code, EXIT_POLICY_FAILURE)
        self.assertEqual(baseline.read_bytes(), before)
        self.assertTrue((cmp_out / "comparison.html").is_file() or (cmp_out / "comparison.json").is_file())

    def test_report_transfer_identities_and_html(self):
        report = self.td / "r.json"
        html = self.td / "r.html"
        self.assertEqual(main(["inspect", str(self.src / "mapping-control.pdf"), "--out", str(report)]), EXIT_OK)
        self.assertEqual(main(["report", str(report), "--format", "html", "--out", str(html)]), EXIT_OK)
        body = html.read_text()
        self.assertIn("Content-Security-Policy", body)
        self.assertNotIn("<script", body.lower())
        data = json.loads(report.read_text())
        self.assertIn(data["document"]["sha256"], body)
        transferred = self.td / "copy.json"
        shutil.copyfile(report, transferred)
        copied = json.loads(transferred.read_text())
        self.assertEqual(copied["document"]["sha256"], data["document"]["sha256"])
        self.assertEqual(copied["readers"][0]["id"], data["readers"][0]["id"])
        self.assertEqual(copied["execution"]["environment"], data["execution"]["environment"])

    def test_documented_exit_code_categories(self):
        self.assertEqual(
            main(["inspect", str(self.src / "no-such.pdf"), "--out", str(self.td / "x.json")]),
            EXIT_READ_FAILURE,
        )
        self.assertEqual(main(["validate", str(self.td / "missing.json")]), EXIT_READ_FAILURE)
        bogus = self.td / "bogus.json"
        bogus.write_text("{")
        self.assertIn(main(["validate", str(bogus)]), {EXIT_INVALID_ARGS, EXIT_READ_FAILURE})
        self.assertEqual(EXIT_OK, 0)
        self.assertEqual(EXIT_INVALID_ARGS, 2)
        self.assertEqual(EXIT_PARTIAL_RUN, 3)
        self.assertEqual(EXIT_READ_FAILURE, 4)
        self.assertEqual(EXIT_POLICY_FAILURE, 5)

    def test_local_reader_upgrade_example_script_is_present(self):
        script = EXAMPLE / "run.sh"
        self.assertTrue(script.is_file())
        text = script.read_text()
        self.assertIn("native/.venv/bin", text)
        self.assertIn("5.9.0", text)
        self.assertIn("6.18.0", text)
