"""T32 corpus tests (TEST-32)."""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NATIVE = ROOT / "native"
FIXTURES = ROOT / "fixtures"
if str(NATIVE) not in sys.path:
    sys.path.insert(0, str(NATIVE))

from inkflip.cli.main import EXIT_OK, main  # noqa: E402
from inkflip.contracts import core  # noqa: E402
from inkflip.corpus.manifest import ContainmentError, IntegrityError, load_and_validate_manifest  # noqa: E402
from inkflip.corpus.runner import run_corpus  # noqa: E402


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


class TestCorpusContainment(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.td = Path(self.tmp.name)
        self.root = self.td / "root"
        self.root.mkdir()
        src = FIXTURES / "public" / "mapping-amount.pdf"
        (self.root / "mapping-amount.pdf").write_bytes(src.read_bytes())

    def tearDown(self):
        self.tmp.cleanup()

    def test_duplicate_basenames_distinct_keys(self):
        a = self.root / "a"
        b = self.root / "b"
        a.mkdir()
        b.mkdir()
        pdf = (self.root / "mapping-amount.pdf").read_bytes()
        (a / "doc.pdf").write_bytes(pdf)
        (b / "doc.pdf").write_bytes(pdf)
        digest = hashlib.sha256(pdf).hexdigest()
        manifest = _manifest(
            [
                {
                    "key": "left-doc",
                    "source_path": "a/doc.pdf",
                    "sha256": digest,
                    "group_id": "pair",
                    "pages": [0],
                },
                {
                    "key": "right-doc",
                    "source_path": "b/doc.pdf",
                    "sha256": digest,
                    "group_id": "pair",
                    "pages": [0],
                },
            ],
            self.td,
        )
        _data, entries, _sha = load_and_validate_manifest(manifest, self.root)
        self.assertEqual([e.key for e in entries], ["left-doc", "right-doc"])
        self.assertEqual(Path(entries[0].resolved_path).name, Path(entries[1].resolved_path).name)

    def test_traversal_rejected(self):
        digest = _sha(self.root / "mapping-amount.pdf")
        manifest = _manifest(
            [
                {
                    "key": "escape",
                    "source_path": "../mapping-amount.pdf",
                    "sha256": digest,
                    "group_id": "g",
                    "pages": [0],
                }
            ],
            self.td,
        )
        with self.assertRaises(ContainmentError):
            load_and_validate_manifest(manifest, self.root)

    def test_symlink_rejected(self):
        link = self.root / "link.pdf"
        os.symlink(self.root / "mapping-amount.pdf", link)
        digest = _sha(self.root / "mapping-amount.pdf")
        manifest = _manifest(
            [
                {
                    "key": "linked",
                    "source_path": "link.pdf",
                    "sha256": digest,
                    "group_id": "g",
                    "pages": [0],
                }
            ],
            self.td,
        )
        with self.assertRaises(ContainmentError):
            load_and_validate_manifest(manifest, self.root)

    def test_altered_bytes_without_manifest_update_rejected(self):
        digest = _sha(self.root / "mapping-amount.pdf")
        manifest = _manifest(
            [
                {
                    "key": "good-file",
                    "source_path": "mapping-amount.pdf",
                    "sha256": digest,
                    "group_id": "g",
                    "pages": [0],
                }
            ],
            self.td,
        )
        (self.root / "mapping-amount.pdf").write_bytes(b"%PDF-1.4\nchanged")
        with self.assertRaises(IntegrityError):
            load_and_validate_manifest(manifest, self.root)


class TestCorpusRun(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.td = Path(self.tmp.name)
        self.root = self.td / "root"
        self.root.mkdir()
        good = FIXTURES / "public" / "mapping-amount.pdf"
        (self.root / "good.pdf").write_bytes(good.read_bytes())
        (self.root / "bad.pdf").write_bytes(b"%PDF-1.4\nbroken")

    def tearDown(self):
        self.tmp.cleanup()

    def _entries(self):
        return [
            {
                "key": "good-file",
                "source_path": "good.pdf",
                "sha256": _sha(self.root / "good.pdf"),
                "group_id": "g",
                "pages": [0],
            },
            {
                "key": "bad-file",
                "source_path": "bad.pdf",
                "sha256": _sha(self.root / "bad.pdf"),
                "group_id": "g",
                "pages": [0],
            },
        ]

    def test_crash_does_not_erase_success(self):
        manifest = _manifest(self._entries(), self.td)
        out = self.td / "run"
        result = run_corpus(manifest, self.root, "native-default", out, jobs=1)
        self.assertIn(result.status, {"partial", "failed"})
        good_report = out / "reports" / "good-file.json"
        self.assertTrue(good_report.is_file())
        core.validate(json.loads(good_report.read_text()))
        index = json.loads((out / "index.json").read_text())
        jobs = index["jobs"]
        self.assertEqual(jobs["good-file"]["status"], "completed")
        self.assertNotEqual(jobs["bad-file"]["status"], "completed")
        self.assertIn("partial", result.status + json.dumps(index))

    def test_resume_refuses_changed_source_and_manifest(self):
        manifest = _manifest(self._entries()[:1], self.td)
        out = self.td / "run"
        first = run_corpus(manifest, self.root, "native-default", out, jobs=1)
        self.assertEqual(first.status, "complete")
        report = (out / "reports" / "good-file.json").read_bytes()
        (self.root / "good.pdf").write_bytes((FIXTURES / "public" / "covered-amount.pdf").read_bytes())
        manifest = _manifest(self._entries()[:1], self.td)
        with self.assertRaises(Exception):
            run_corpus(manifest, self.root, "native-default", out, jobs=1, resume=True)
        self.assertEqual((out / "reports" / "good-file.json").read_bytes(), report)

    def test_cli_corpus_run(self):
        manifest = _manifest(self._entries()[:1], self.td)
        out = self.td / "cli-run"
        code = main(
            [
                "corpus",
                "run",
                "--manifest",
                str(manifest),
                "--source-root",
                str(self.root),
                "--profile",
                "native-default",
                "--out",
                str(out),
            ]
        )
        self.assertEqual(code, EXIT_OK)
        self.assertTrue((out / "index.json").is_file())
        self.assertTrue((out / "journal.jsonl").is_file())

    def test_index_orders_keys_and_keeps_partial_counts(self):
        manifest = _manifest(self._entries(), self.td)
        out = self.td / "counts"
        result = run_corpus(manifest, self.root, "native-default", out, jobs=1)
        self.assertEqual(result.status, "partial")
        index = json.loads((out / "index.json").read_text())
        keys = list(index["jobs"])
        self.assertEqual(keys, sorted(keys))
        statuses = [job["status"] for job in index["jobs"].values()]
        self.assertIn("completed", statuses)
        self.assertTrue(any(status in {"failed", "timeout"} for status in statuses))
        self.assertEqual(
            index["status"],
            "partial",
        )
        self.assertEqual(len(index["jobs"]), 2)

    def test_resume_skips_unchanged_completed_report(self):
        manifest = _manifest(self._entries()[:1], self.td)
        out = self.td / "resume-ok"
        first = run_corpus(manifest, self.root, "native-default", out, jobs=1)
        self.assertEqual(first.status, "complete")
        report = (out / "reports" / "good-file.json").read_bytes()
        second = run_corpus(manifest, self.root, "native-default", out, jobs=1, resume=True)
        self.assertEqual(second.status, "complete")
        self.assertEqual((out / "reports" / "good-file.json").read_bytes(), report)
        index = json.loads((out / "index.json").read_text())
        self.assertEqual(index["jobs"]["good-file"]["status"], "skipped")


if __name__ == "__main__":
    unittest.main()
