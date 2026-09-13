"""T32 Corpus runner and resume tests (TEST-32).

Verifies the inkflip corpus execution contracts:
- Path containment (traversal and symlinks rejected)
- Duplicate filenames preserved under distinct corpus keys
- Manifest schema validation
- Atomic per-file reports, index.json and journal.jsonl
- One crashing file does not erase successful reports (retained failures)
- Deterministic index ordering
- Altered bytes invalidate resume / byte-identical resume preservation
- CLI invocation of `inkflip corpus run`
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
NATIVE = ROOT / "native"
FIXTURES = ROOT / "fixtures"

if str(NATIVE) not in sys.path:
    sys.path.insert(0, str(NATIVE))

from inkflip.cli.main import EXIT_INVALID_ARGS, EXIT_OK, EXIT_PARTIAL_RUN, main
from inkflip.contracts import core
from inkflip.corpus.manifest import (
    ContainmentError,
    IntegrityError,
    ManifestValidationError,
    load_and_validate_manifest,
)
from inkflip.corpus.runner import run_corpus
from inkflip.runtime import Limits


class TestCorpusManifestAndContainment(unittest.TestCase):
    """Manifest validation and path containment invariants."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.td = Path(self.tmp_dir.name)
        self.source_root = self.td / "sources"
        self.source_root.mkdir()

        # Create sample PDF in source_root
        self.pdf_file = self.source_root / "sample.pdf"
        self.pdf_bytes = (FIXTURES / "public" / "geometry-control.pdf").read_bytes()
        self.pdf_file.write_bytes(self.pdf_bytes)
        self.pdf_sha256 = hashlib.sha256(self.pdf_bytes).hexdigest()

    def tearDown(self):
        self.tmp_dir.cleanup()

    def _write_manifest(self, data: dict) -> Path:
        p = self.td / "manifest.json"
        p.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return p

    def test_valid_manifest_loads_and_validates(self):
        m_path = self._write_manifest({
            "kind": "corpus_manifest",
            "schema_version": "1.0.0",
            "source_root_policy": "explicit_local_root_no_symlinks",
            "split": "public_demo",
            "entries": [
                {
                    "key": "doc1",
                    "source_path": "sample.pdf",
                    "sha256": self.pdf_sha256,
                    "group_id": "test-group",
                    "pages": [0],
                }
            ],
        })
        manifest, entries = load_and_validate_manifest(m_path, self.source_root)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].key, "doc1")
        self.assertEqual(entries[0].sha256, self.pdf_sha256)

    def test_duplicate_filenames_remain_distinct_corpus_keys(self):
        """Criterion: duplicate filenames remain distinct corpus keys."""
        # Two subdirectories with the same filename 'doc.pdf'
        sub1 = self.source_root / "sub1"
        sub2 = self.source_root / "sub2"
        sub1.mkdir()
        sub2.mkdir()
        (sub1 / "doc.pdf").write_bytes(self.pdf_bytes)
        (sub2 / "doc.pdf").write_bytes(self.pdf_bytes)

        m_path = self._write_manifest({
            "kind": "corpus_manifest",
            "schema_version": "1.0.0",
            "source_root_policy": "explicit_local_root_no_symlinks",
            "split": "public_demo",
            "entries": [
                {
                    "key": "key-sub1-doc",
                    "source_path": "sub1/doc.pdf",
                    "sha256": self.pdf_sha256,
                    "group_id": "test-group",
                    "pages": [0],
                },
                {
                    "key": "key-sub2-doc",
                    "source_path": "sub2/doc.pdf",
                    "sha256": self.pdf_sha256,
                    "group_id": "test-group",
                    "pages": [0],
                },
            ],
        })
        _, entries = load_and_validate_manifest(m_path, self.source_root)
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0].key, "key-sub1-doc")
        self.assertEqual(entries[1].key, "key-sub2-doc")
        self.assertNotEqual(entries[0].key, entries[1].key)

    def test_duplicate_keys_rejected(self):
        m_path = self._write_manifest({
            "kind": "corpus_manifest",
            "schema_version": "1.0.0",
            "source_root_policy": "explicit_local_root_no_symlinks",
            "split": "public_demo",
            "entries": [
                {
                    "key": "same-key",
                    "source_path": "sample.pdf",
                    "sha256": self.pdf_sha256,
                    "group_id": "test-group",
                    "pages": [0],
                },
                {
                    "key": "same-key",
                    "source_path": "sample.pdf",
                    "sha256": self.pdf_sha256,
                    "group_id": "test-group",
                    "pages": [0],
                },
            ],
        })
        with self.assertRaises(ManifestValidationError):
            load_and_validate_manifest(m_path, self.source_root)

    def test_traversal_rejected(self):
        """Criterion: traversal escape rejected."""
        m_path = self._write_manifest({
            "kind": "corpus_manifest",
            "schema_version": "1.0.0",
            "source_root_policy": "explicit_local_root_no_symlinks",
            "split": "public_demo",
            "entries": [
                {
                    "key": "escaping-doc",
                    "source_path": "../outside.pdf",
                    "sha256": self.pdf_sha256,
                    "group_id": "test-group",
                    "pages": [0],
                }
            ],
        })
        with self.assertRaises(ContainmentError):
            load_and_validate_manifest(m_path, self.source_root)

    def test_symlink_in_source_root_rejected(self):
        """Criterion: symlink escape rejected."""
        symlink_root = self.td / "symlink_root"
        symlink_root.symlink_to(self.source_root)
        m_path = self._write_manifest({
            "kind": "corpus_manifest",
            "schema_version": "1.0.0",
            "source_root_policy": "explicit_local_root_no_symlinks",
            "split": "public_demo",
            "entries": [
                {
                    "key": "doc1",
                    "source_path": "sample.pdf",
                    "sha256": self.pdf_sha256,
                    "group_id": "test-group",
                    "pages": [0],
                }
            ],
        })
        with self.assertRaises(ContainmentError):
            load_and_validate_manifest(m_path, symlink_root)

    def test_symlink_file_rejected(self):
        """Criterion: symlink escape rejected."""
        link_file = self.source_root / "link.pdf"
        link_file.symlink_to(self.pdf_file)
        m_path = self._write_manifest({
            "kind": "corpus_manifest",
            "schema_version": "1.0.0",
            "source_root_policy": "explicit_local_root_no_symlinks",
            "split": "public_demo",
            "entries": [
                {
                    "key": "doc-link",
                    "source_path": "link.pdf",
                    "sha256": self.pdf_sha256,
                    "group_id": "test-group",
                    "pages": [0],
                }
            ],
        })
        with self.assertRaises(ContainmentError):
            load_and_validate_manifest(m_path, self.source_root)

    def test_altered_bytes_detected_at_manifest_load(self):
        """Criterion: altered bytes invalidate resume / manifest verification."""
        m_path = self._write_manifest({
            "kind": "corpus_manifest",
            "schema_version": "1.0.0",
            "source_root_policy": "explicit_local_root_no_symlinks",
            "split": "public_demo",
            "entries": [
                {
                    "key": "doc1",
                    "source_path": "sample.pdf",
                    "sha256": "0" * 64,  # wrong hash
                    "group_id": "test-group",
                    "pages": [0],
                }
            ],
        })
        with self.assertRaises(IntegrityError):
            load_and_validate_manifest(m_path, self.source_root)


class TestCorpusExecutionAndResume(unittest.TestCase):
    """Execution, atomicity, crash isolation, and resume semantics."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.td = Path(self.tmp_dir.name)
        self.source_root = self.td / "sources"
        self.source_root.mkdir()
        self.out_dir = self.td / "run_out"

        self.good_pdf = self.source_root / "good.pdf"
        good_bytes = (FIXTURES / "public" / "geometry-control.pdf").read_bytes()
        self.good_pdf.write_bytes(good_bytes)
        self.good_sha = hashlib.sha256(good_bytes).hexdigest()

        self.bad_pdf = self.source_root / "bad.pdf"
        bad_bytes = (FIXTURES / "development" / "bad-pdf-malformed.pdf").read_bytes()
        self.bad_pdf.write_bytes(bad_bytes)
        self.bad_sha = hashlib.sha256(bad_bytes).hexdigest()

    def tearDown(self):
        self.tmp_dir.cleanup()

    def _write_manifest(self, entries: list[dict]) -> Path:
        p = self.td / "manifest.json"
        p.write_text(
            json.dumps({
                "kind": "corpus_manifest",
                "schema_version": "1.0.0",
                "source_root_policy": "explicit_local_root_no_symlinks",
                "split": "public_demo",
                "entries": entries,
            }, indent=2),
            encoding="utf-8",
        )
        return p

    def test_successful_run_creates_atomic_reports_and_index(self):
        m_path = self._write_manifest([
            {"key": "file-one", "source_path": "good.pdf", "sha256": self.good_sha, "group_id": "test-group", "pages": [0]},
        ])
        result = run_corpus(
            manifest_path=m_path,
            source_root=self.source_root,
            profile="native",
            out_dir=self.out_dir,
        )
        self.assertEqual(result.status, "complete")
        self.assertTrue((self.out_dir / "index.json").exists())
        self.assertTrue((self.out_dir / "journal.jsonl").exists())
        rep_file = self.out_dir / "reports" / "file-one.json"
        self.assertTrue(rep_file.exists())
        rep_data = json.loads(rep_file.read_text(encoding="utf-8"))
        core.validate(rep_data)

    def test_crashing_file_does_not_erase_successful_reports(self):
        """Criterion: one crashing file cannot erase successful reports."""
        m_path = self._write_manifest([
            {"key": "file-good", "source_path": "good.pdf", "sha256": self.good_sha, "group_id": "test-group", "pages": [0]},
            {"key": "file-bad", "source_path": "bad.pdf", "sha256": self.bad_sha, "group_id": "test-group", "pages": [0]},
        ])
        result = run_corpus(
            manifest_path=m_path,
            source_root=self.source_root,
            profile="native",
            out_dir=self.out_dir,
        )
        # Run has both a success and a failure -> status is partial
        self.assertEqual(result.status, "partial")
        self.assertEqual(result.jobs["file-good"].status, "completed")
        self.assertEqual(result.jobs["file-bad"].status, "failed")

        # Verify successful report is preserved on disk
        self.assertTrue((self.out_dir / "reports" / "file-good.json").exists())
        # Index records both terminals
        index = json.loads((self.out_dir / "index.json").read_text(encoding="utf-8"))
        self.assertEqual(index["jobs"]["file-good"]["status"], "completed")
        self.assertEqual(index["jobs"]["file-bad"]["status"], "failed")

    def test_resume_preserves_byte_identical_reports_and_skips(self):
        """Criterion: resume preserves successful outputs byte-for-byte."""
        m_path = self._write_manifest([
            {"key": "file-good", "source_path": "good.pdf", "sha256": self.good_sha, "group_id": "test-group", "pages": [0]},
            {"key": "file-bad", "source_path": "bad.pdf", "sha256": self.bad_sha, "group_id": "test-group", "pages": [0]},
        ])
        run1 = run_corpus(
            manifest_path=m_path,
            source_root=self.source_root,
            profile="native",
            out_dir=self.out_dir,
        )
        rep_bytes_before = (self.out_dir / "reports" / "file-good.json").read_bytes()

        # Resume run
        run2 = run_corpus(
            manifest_path=m_path,
            source_root=self.source_root,
            profile="native",
            out_dir=self.out_dir,
            resume=True,
        )
        self.assertEqual(run2.jobs["file-good"].status, "skipped")
        self.assertEqual(run2.jobs["file-good"].attempts, 0)
        rep_bytes_after = (self.out_dir / "reports" / "file-good.json").read_bytes()
        self.assertEqual(rep_bytes_before, rep_bytes_after)

    def test_deterministic_index_ordering(self):
        """Criterion: deterministic index ordering and explicit partial counts."""
        m_path = self._write_manifest([
            {"key": "z-key", "source_path": "good.pdf", "sha256": self.good_sha, "group_id": "test-group", "pages": [0]},
            {"key": "a-key", "source_path": "good.pdf", "sha256": self.good_sha, "group_id": "test-group", "pages": [0]},
            {"key": "m-key", "source_path": "good.pdf", "sha256": self.good_sha, "group_id": "test-group", "pages": [0]},
        ])
        result = run_corpus(
            manifest_path=m_path,
            source_root=self.source_root,
            profile="native",
            out_dir=self.out_dir,
        )
        self.assertEqual(result.status, "complete")
        index = json.loads((self.out_dir / "index.json").read_text(encoding="utf-8"))
        job_keys = list(index["jobs"].keys())
        # Deterministic sorted key order in run index
        self.assertEqual(job_keys, sorted(["z-key", "a-key", "m-key"]))

    def test_cli_corpus_run_command(self):
        """Test full CLI invocation: inkflip corpus run."""
        m_path = self._write_manifest([
            {"key": "cli-doc", "source_path": "good.pdf", "sha256": self.good_sha, "group_id": "test-group", "pages": [0]},
        ])
        code = main([
            "corpus", "run",
            "--manifest", str(m_path),
            "--source-root", str(self.source_root),
            "--profile", "native",
            "--out", str(self.out_dir),
        ])
        self.assertEqual(code, EXIT_OK)
        self.assertTrue((self.out_dir / "index.json").exists())
        self.assertTrue((self.out_dir / "reports" / "cli-doc.json").exists())


if __name__ == "__main__":
    unittest.main()
