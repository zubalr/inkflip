"""Path shapes, directory-vs-file handling, and cache recovery.

Every case runs the shipped CLI as a real subprocess, so exit status, streams and
on-disk effects are the contract. Behaviour here was verified by probing first and
is now pinned; no product change was needed for these cases.
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

EXIT_OK = 0
EXIT_INVALID_ARGS = 2
EXIT_READ_FAILURE = 4


def _env() -> dict[str, str]:
    env = dict(os.environ)
    prior = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(NATIVE) + (os.pathsep + prior if prior else "")
    return env


def cli(*argv: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "inkflip.cli", *argv],
        cwd=str(ROOT), capture_output=True, text=True, env=_env(), timeout=180,
    )


class PathShapeCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.td = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()


class TestUnicodeAndSpacePaths(PathShapeCase):
    def test_inspect_round_trips_through_unicode_spaced_paths(self):
        directory = self.td / "дір with spaces — 中文 🚀"
        directory.mkdir()
        source = directory / "файл — test.pdf"
        source.write_bytes(AMOUNT.read_bytes())
        out = directory / "报告 report.json"

        result = cli("inspect", str(source), "--out", str(out))
        self.assertEqual(result.returncode, EXIT_OK, result.stderr)
        self.assertTrue(out.is_file())
        payload = json.loads(out.read_text())
        self.assertEqual(payload["document"]["sha256"], hashlib.sha256(source.read_bytes()).hexdigest())
        self.assertEqual(payload["document"]["display_name"], source.name)

    def test_validate_accepts_the_unicode_artefact(self):
        directory = self.td / "ünïcode"
        directory.mkdir()
        out = directory / "réport.json"
        self.assertEqual(cli("inspect", str(AMOUNT), "--out", str(out)).returncode, EXIT_OK)
        self.assertEqual(cli("validate", str(out)).returncode, EXIT_OK)


class TestDirectoryVersusFile(PathShapeCase):
    def test_source_directory_is_a_read_failure(self):
        directory = self.td / "a-directory"
        directory.mkdir()
        out = self.td / "o.json"
        result = cli("inspect", str(directory), "--out", str(out))
        self.assertEqual(result.returncode, EXIT_READ_FAILURE)
        self.assertTrue(result.stderr.startswith("Error: "), result.stderr)
        self.assertFalse(out.exists(), "a failed inspect must not leave an output")

    def test_output_directory_is_an_argument_error_and_is_untouched(self):
        directory = self.td / "existing-dir"
        directory.mkdir()
        (directory / "keep.txt").write_text("keep me")
        result = cli("inspect", str(AMOUNT), "--out", str(directory))
        self.assertEqual(result.returncode, EXIT_INVALID_ARGS)
        self.assertEqual([p.name for p in directory.iterdir()], ["keep.txt"])


class TestReplayAndRemoteRefusals(PathShapeCase):
    def test_replay_with_a_changed_profile_is_refused(self):
        report = self.td / "r.json"
        self.assertEqual(cli("inspect", str(AMOUNT), "--out", str(report)).returncode, EXIT_OK)
        out = self.td / "replay.json"
        result = cli("replay", str(report), "--source", str(AMOUNT), "--profile", "not-the-recorded-one", "--out", str(out))
        self.assertEqual(result.returncode, EXIT_INVALID_ARGS)
        self.assertIn("profile mismatch", result.stderr)
        self.assertFalse(out.exists())

    def test_remote_source_is_refused(self):
        result = cli("inspect", "https://example.com/x.pdf", "--out", str(self.td / "o.json"))
        self.assertEqual(result.returncode, EXIT_INVALID_ARGS)
        self.assertIn("not permitted", result.stderr)


class TestIncompleteCopyRecovery(PathShapeCase):
    def test_a_stale_partial_cache_file_is_replaced_by_the_verified_copy(self):
        source = self.td / "src" / "model.traineddata"
        source.parent.mkdir()
        complete = b"complete-model-bytes"
        source.write_bytes(complete)
        cache = self.td / "cache"
        stale = cache / "eng_lstm" / "model.traineddata"
        stale.parent.mkdir(parents=True)
        stale.write_bytes(b"PARTIAL")  # an interrupted earlier copy
        manifest = self.td / "manifest.json"
        manifest.write_text(json.dumps({
            "kind": "inkflip_model_manifest",
            "schema_version": "1.0.0",
            "models": [{
                "id": "eng_lstm",
                "sha256": hashlib.sha256(complete).hexdigest(),
                "path": str(source),
                "purpose": "ocr_language_model",
            }],
        }))

        result = cli("models", "prepare", "--manifest", str(manifest), "--cache", str(cache))
        self.assertEqual(result.returncode, EXIT_OK, result.stderr)
        self.assertEqual(stale.read_bytes(), complete, "the verified copy must replace the partial one")
        index = json.loads((cache / "index.json").read_text())
        self.assertTrue(index["ready"])
        self.assertEqual(index["prepared"][0]["sha256"], hashlib.sha256(complete).hexdigest())

    def test_a_digest_mismatch_leaves_the_cache_not_ready(self):
        source = self.td / "bad.traineddata"
        source.write_bytes(b"not-the-recorded-bytes")
        cache = self.td / "cache2"
        manifest = self.td / "bad.json"
        manifest.write_text(json.dumps({
            "kind": "inkflip_model_manifest",
            "schema_version": "1.0.0",
            "models": [{"id": "eng", "sha256": "0" * 64, "path": str(source), "purpose": "ocr_language_model"}],
        }))
        result = cli("models", "prepare", "--manifest", str(manifest), "--cache", str(cache))
        self.assertNotEqual(result.returncode, EXIT_OK)
        index = json.loads((cache / "index.json").read_text())
        self.assertFalse(index["ready"])
        self.assertEqual(index["prepared_count"], 0)


if __name__ == "__main__":
    unittest.main()
