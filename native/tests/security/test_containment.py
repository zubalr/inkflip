"""T40 native containment: launched workloads, not Docker argv strings."""
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
WORKER = Path(__file__).resolve().parent / "workload.py"

if str(NATIVE) not in sys.path:
    sys.path.insert(0, str(NATIVE))

from inkflip.cli.main import EXIT_INVALID_ARGS, EXIT_OK, main  # noqa: E402
from inkflip.contracts import core  # noqa: E402
from inkflip.corpus.manifest import ContainmentError, load_and_validate_manifest  # noqa: E402
from inkflip.runtime import (  # noqa: E402
    KIND_CRASH,
    KIND_OUTPUT_LIMIT,
    KIND_WALL,
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_TIMEOUT,
    JobSpec,
    Limits,
    Supervisor,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _limits(**overrides) -> Limits:
    base = dict(
        wall_seconds=3.0,
        memory_bytes=256 << 20,
        max_stdout_bytes=8 << 10,
        max_stderr_bytes=8 << 10,
        max_report_bytes=1 << 20,
        scratch_bytes=8 << 20,
        retries=0,
        jobs=1,
        kill_grace_seconds=0.2,
        poll_interval_seconds=0.02,
        rss_probe_interval_seconds=0.05,
    )
    base.update(overrides)
    return Limits(**base)


def _spec(key: str, *args: str) -> JobSpec:
    return JobSpec(key=key, argv=[sys.executable, str(WORKER), *args], produces="report.json")


class TestSourceBytesUnchanged(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="t40-src-")
        self.td = Path(self.tmp.name)
        self.pdf = self.td / "synthetic.pdf"
        self.pdf.write_bytes((FIXTURES / "public" / "mapping-control.pdf").read_bytes())
        self.before = _sha(self.pdf)

    def tearDown(self):
        self.tmp.cleanup()

    def test_inspect_does_not_modify_source(self):
        out = self.td / "report.json"
        code = main(["inspect", str(self.pdf), "--out", str(out), "--pages", "1"])
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(_sha(self.pdf), self.before)
        report = json.loads(out.read_text())
        core.validate(report)
        self.assertEqual(report["document"]["sha256"], self.before)


class TestPathEscape(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="t40-esc-")
        self.td = Path(self.tmp.name)
        self.root = self.td / "root"
        self.root.mkdir()
        (self.root / "doc.pdf").write_bytes((FIXTURES / "public" / "mapping-amount.pdf").read_bytes())

    def tearDown(self):
        self.tmp.cleanup()

    def test_corpus_rejects_symlink_and_traversal(self):
        outside = self.td / "outside.pdf"
        outside.write_bytes((self.root / "doc.pdf").read_bytes())
        link = self.root / "link.pdf"
        os.symlink(outside, link)
        digest = _sha(self.root / "doc.pdf")
        manifest = {
            "kind": "corpus_manifest",
            "schema_version": "1.0.0",
            "entries": [
                {
                    "key": "escape",
                    "source_path": "link.pdf",
                    "sha256": digest,
                    "group_id": "t40",
                    "pages": [0],
                }
            ],
            "source_root_policy": "explicit_local_root_no_symlinks",
            "split": "development",
        }
        path = self.td / "corpus.json"
        path.write_text(json.dumps(manifest))
        with self.assertRaises(ContainmentError):
            load_and_validate_manifest(path, self.root)

        manifest["entries"][0]["source_path"] = "../outside.pdf"
        path.write_text(json.dumps(manifest))
        with self.assertRaises(ContainmentError):
            load_and_validate_manifest(path, self.root)


class TestLaunchedWorkloads(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="t40-sup-")
        self.td = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_hang_is_process_group_terminated(self):
        out = self.td / "hang"
        result = Supervisor(out, _limits(wall_seconds=1.0)).run([_spec("hang", "hang")])
        rec = result.jobs["hang"]
        self.assertIn(rec.status, {STATUS_TIMEOUT, STATUS_FAILED})
        self.assertIn(rec.failure_kind, {KIND_WALL, KIND_CRASH})
        scratch = out / "scratch"
        if scratch.exists():
            self.assertEqual(list(scratch.iterdir()), [])

    def test_crash_retains_unrelated_success(self):
        out = self.td / "mix"
        result = Supervisor(out, _limits(wall_seconds=4.0)).run(
            [
                _spec("good", "ok", "keep-me"),
                _spec("bad", "crash"),
            ]
        )
        self.assertEqual(result.jobs["good"].status, STATUS_COMPLETED)
        good = json.loads((out / "reports" / "good.json").read_text())
        self.assertEqual(good["text"], "keep-me")
        self.assertEqual(result.jobs["bad"].status, STATUS_FAILED)
        self.assertEqual(result.jobs["bad"].failure_kind, KIND_CRASH)
        self.assertTrue((out / "reports" / "good.json").is_file())

    def test_stdout_flood_is_killed(self):
        out = self.td / "flood"
        result = Supervisor(out, _limits(max_stdout_bytes=2048, wall_seconds=3.0)).run(
            [_spec("flood", "flood")]
        )
        rec = result.jobs["flood"]
        self.assertEqual(rec.status, STATUS_FAILED)
        self.assertEqual(rec.failure_kind, KIND_OUTPUT_LIMIT)

    def test_child_default_writes_use_private_scratch(self):
        out = self.td / "scratch-bound"
        result = Supervisor(out, _limits()).run([_spec("tmp", "tmpdir-write")])
        self.assertEqual(result.jobs["tmp"].status, STATUS_COMPLETED)
        report = json.loads((out / "reports" / "tmp.json").read_text())
        tmpdir = Path(report["tmpdir"]).resolve()
        self.assertTrue(str(tmpdir).startswith(str((out / "scratch").resolve())))
        # Native OS is not a chroot: corpus/CLI path checks refuse symlink
        # escape. Absolute host writes are a container restriction (T40 recipe).

    def test_cleanup_after_failure_and_cancel(self):
        out = self.td / "cancel"
        result = Supervisor(out, _limits(wall_seconds=8.0)).run(
            [
                _spec("good", "ok", "survives"),
                _spec("slow", "sigint-parent"),
                _spec("queued", "ok", "should-cancel"),
            ]
        )
        self.assertIn(result.status, {"cancelled", "partial", "failed"})
        self.assertEqual(result.jobs["good"].status, STATUS_COMPLETED)
        self.assertEqual(json.loads((out / "reports" / "good.json").read_text())["text"], "survives")
        self.assertTrue((out / "index.json").is_file())
        index = json.loads((out / "index.json").read_text())
        self.assertIn("rlimit_support", index)
        scratch = out / "scratch"
        if scratch.exists():
            self.assertEqual(list(scratch.iterdir()), [])
        self.assertTrue(
            result.jobs["slow"].status in {STATUS_CANCELLED, STATUS_TIMEOUT, STATUS_FAILED}
            or result.jobs["queued"].status == STATUS_CANCELLED
        )

    def test_unsupported_os_limits_are_reported(self):
        out = self.td / "limits"
        result = Supervisor(out, _limits()).run([_spec("good", "ok", "limit-probe")])
        self.assertEqual(result.jobs["good"].status, STATUS_COMPLETED)
        index = json.loads((out / "index.json").read_text())
        support = index["rlimit_support"]
        self.assertIsInstance(support, dict)
        self.assertTrue(support, "rlimit_support must record what the OS accepted or rejected")


class TestNoUntrustedExecution(unittest.TestCase):
    def test_imported_report_cannot_select_an_executable(self):
        tmp = tempfile.TemporaryDirectory(prefix="t40-imp-")
        td = Path(tmp.name)
        try:
            report = td / "evil.json"
            report.write_text(json.dumps({"kind": "not-a-report", "executable": "/bin/sh"}))
            code = main(["validate", str(report)])
            self.assertEqual(code, EXIT_INVALID_ARGS)
        finally:
            tmp.cleanup()
