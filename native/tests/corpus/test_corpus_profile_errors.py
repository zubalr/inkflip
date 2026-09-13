"""Corpus profile selection faults are configuration errors, not runtime failures.

Regression for the reported gap where `inkflip corpus run --profile <unknown>`
escaped as an untranslated `Unexpected error: Profile ... not found` with exit 4
instead of the documented exit 2 (invalid arguments, configuration, or imported
contract; docs/CLI.md).

A named profile that is missing, path-like, symlinked or blocked is invalid
configuration. A refused run must not create its output directory.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NATIVE = ROOT / "native"
FIXTURES = ROOT / "fixtures"
AMOUNT = FIXTURES / "public" / "mapping-amount.pdf"

if str(NATIVE) not in sys.path:
    sys.path.insert(0, str(NATIVE))

from inkflip.corpus.manifest import CorpusError  # noqa: E402
from inkflip.corpus.runner import run_corpus  # noqa: E402

EXIT_OK = 0
EXIT_INVALID_ARGS = 2


def _env() -> dict[str, str]:
    env = dict(os.environ)
    prior = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(NATIVE) + (os.pathsep + prior if prior else "")
    return env


def _cli(*argv: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "inkflip.cli", *argv],
        cwd=str(ROOT), capture_output=True, text=True, env=_env(), timeout=300,
    )


def _manifest(directory: Path) -> Path:
    payload = {
        "kind": "corpus_manifest",
        "schema_version": "1.0.0",
        "split": "public_demo",
        "source_root_policy": "explicit_local_root_no_symlinks",
        "entries": [
            {
                "key": "amount",
                "source_path": "mapping-amount.pdf",
                "sha256": hashlib.sha256(AMOUNT.read_bytes()).hexdigest(),
                "group_id": "amount",
                "pages": [0],
            }
        ],
    }
    path = directory / "manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class TestCorpusProfileSelection(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.td = Path(self.tmp.name)
        self.manifest = _manifest(self.td)
        self.source_root = FIXTURES / "public"

    def tearDown(self):
        self.tmp.cleanup()

    def test_unknown_profile_is_exit_2_and_creates_no_output(self):
        out = self.td / "out-unknown"
        result = _cli(
            "corpus", "run", "--manifest", str(self.manifest),
            "--source-root", str(self.source_root), "--profile", "bogus", "--out", str(out),
        )
        self.assertEqual(result.returncode, EXIT_INVALID_ARGS, msg=f"stderr={result.stderr!r}")
        self.assertNotIn("Unexpected error", result.stderr)
        self.assertTrue(result.stderr.startswith("Error: "), result.stderr)
        self.assertIn("profile", result.stderr.lower())
        self.assertFalse(out.exists(), "a refused profile must not create the output directory")

    def test_path_like_profile_is_exit_2(self):
        out = self.td / "out-path"
        result = _cli(
            "corpus", "run", "--manifest", str(self.manifest),
            "--source-root", str(self.source_root), "--profile", "/tmp/custom.json", "--out", str(out),
        )
        self.assertEqual(result.returncode, EXIT_INVALID_ARGS, msg=f"stderr={result.stderr!r}")
        self.assertFalse(out.exists())

    def test_unknown_profile_raises_corpus_error_from_the_runner(self):
        with self.assertRaises(CorpusError):
            run_corpus(
                manifest_path=self.manifest,
                source_root=self.source_root,
                profile="definitely-not-installed",
                out_dir=self.td / "out-api",
                jobs=1,
            )
        self.assertFalse((self.td / "out-api").exists())

    def test_valid_builtin_profile_still_runs(self):
        out = self.td / "out-ok"
        result = _cli(
            "corpus", "run", "--manifest", str(self.manifest),
            "--source-root", str(self.source_root), "--profile", "native-default", "--out", str(out),
        )
        self.assertEqual(result.returncode, EXIT_OK, msg=f"stdout={result.stdout!r} stderr={result.stderr!r}")
        self.assertTrue((out / "identity.json").is_file(), "a completed run records its identity")
        self.assertTrue((out / "index.json").is_file(), "a completed run records its index")


class TestCorpusManifestNegativeContracts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.td = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_manifest_is_exit_2(self):
        out = self.td / "out"
        result = _cli(
            "corpus", "run", "--manifest", str(self.td / "absent.json"),
            "--source-root", str(FIXTURES / "public"), "--profile", "native-default", "--out", str(out),
        )
        self.assertEqual(result.returncode, EXIT_INVALID_ARGS)
        self.assertTrue(result.stderr.startswith("Error: "), result.stderr)
        self.assertFalse(out.exists())

    def test_duplicate_corpus_key_is_exit_2(self):
        payload = json.loads(_manifest(self.td).read_text())
        payload["entries"].append(dict(payload["entries"][0]))
        path = self.td / "dup.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        out = self.td / "out-dup"
        result = _cli(
            "corpus", "run", "--manifest", str(path),
            "--source-root", str(FIXTURES / "public"), "--profile", "native-default", "--out", str(out),
        )
        self.assertEqual(result.returncode, EXIT_INVALID_ARGS)
        self.assertIn("Duplicate corpus key", result.stderr)
        self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
