"""Unit tests for scripts/prepare_assets.py (T02 / TEST-02).

Negative controls required by the acceptance contract live here:
  - a substituted model/asset fails its checksum (staged or downloaded),
  - a missing asset fails closed,
  - manifest schema violations (unknown keys, traversal, remote paths) are
    rejected before interpretation — fixture family F22 strict-JSON behavior,
  - fail-closed staging: bad bytes are never written to the staging root.
"""
from __future__ import annotations

import hashlib
import io
import json
import sys
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import prepare_assets  # noqa: E402

STAGING = prepare_assets.STAGING_ROOT


def make_manifest() -> dict:
    return {
        "schema_version": "1.0.0",
        "recorded_by": "T02-test",
        "recorded_at": "2026-09-12",
        "staging_root": STAGING,
        "public_base": "/",
        "assets": [
            {
                "id": "test-model",
                "kind": "ocr-model",
                "version": "v0-test",
                "source": "upstream-url",
                "license": "Apache-2.0",
                "rights": "synthetic test asset",
                "serve_prefix": "/models/test/",
                "delivery": "same-origin static",
                "files": [
                    {
                        "staged_path": "models/test/blob.bin",
                        "sha256": hashlib.sha256(b"expected-bytes").hexdigest(),
                        "bytes": len(b"expected-bytes"),
                        "source_url": "https://example.invalid/model.bin",
                    }
                ],
            }
        ],
    }


def stage_bytes(tmp: Path, manifest: dict, content: bytes) -> Path:
    entry = manifest["assets"][0]["files"][0]
    target = tmp / STAGING / entry["staged_path"]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return target


class TempWorkspace:
    """Point prepare_assets at a throwaway checkout root."""

    def __init__(self, test: unittest.TestCase, tmp: Path):
        self._patcher = mock.patch.object(prepare_assets, "ROOT", tmp)
        test.addCleanup(self._patcher.stop)
        self._patcher.start()


class ManifestValidationTests(unittest.TestCase):
    def test_valid_manifest_passes(self):
        manifest = make_manifest()
        assets = prepare_assets.validate_manifest(manifest)
        self.assertEqual(len(assets), 1)
        self.assertEqual(assets[0]["id"], "test-model")

    def test_unknown_top_level_key_rejected(self):
        manifest = make_manifest()
        manifest["surprise"] = True
        with self.assertRaises(prepare_assets.AssetError):
            prepare_assets.validate_manifest(manifest)

    def test_unknown_asset_key_rejected(self):
        manifest = make_manifest()
        manifest["assets"][0]["callback"] = "x"
        with self.assertRaises(prepare_assets.AssetError):
            prepare_assets.validate_manifest(manifest)

    def test_unknown_file_key_rejected(self):
        manifest = make_manifest()
        manifest["assets"][0]["files"][0]["eval"] = "x"
        with self.assertRaises(prepare_assets.AssetError):
            prepare_assets.validate_manifest(manifest)

    def test_missing_required_key_rejected(self):
        manifest = make_manifest()
        del manifest["assets"][0]["license"]
        with self.assertRaises(prepare_assets.AssetError):
            prepare_assets.validate_manifest(manifest)

    def test_bad_sha256_rejected(self):
        manifest = make_manifest()
        manifest["assets"][0]["files"][0]["sha256"] = "zz" * 32
        with self.assertRaises(prepare_assets.AssetError):
            prepare_assets.validate_manifest(manifest)

    def test_short_sha256_rejected(self):
        manifest = make_manifest()
        manifest["assets"][0]["files"][0]["sha256"] = "abcd"
        with self.assertRaises(prepare_assets.AssetError):
            prepare_assets.validate_manifest(manifest)

    def test_zero_bytes_rejected(self):
        manifest = make_manifest()
        manifest["assets"][0]["files"][0]["bytes"] = 0
        with self.assertRaises(prepare_assets.AssetError):
            prepare_assets.validate_manifest(manifest)

    def test_duplicate_staged_path_rejected(self):
        manifest = make_manifest()
        manifest["assets"][0]["files"].append(dict(manifest["assets"][0]["files"][0]))
        with self.assertRaises(prepare_assets.AssetError):
            prepare_assets.validate_manifest(manifest)

    def test_path_traversal_rejected(self):
        for bad in ("../escape.bin", "/abs/path.bin", "models\\evil.bin",
                    "outside/blob.bin"):
            manifest = make_manifest()
            manifest["assets"][0]["files"][0]["staged_path"] = bad
            with self.assertRaises(prepare_assets.AssetError, msg=bad):
                prepare_assets.validate_manifest(manifest)

    def test_serve_prefix_remote_rejected(self):
        for bad in ("https://cdn.example.com/x/", "//cdn.example.com/x/", "models/no-slash"):
            manifest = make_manifest()
            manifest["assets"][0]["serve_prefix"] = bad
            with self.assertRaises(prepare_assets.AssetError, msg=bad):
                prepare_assets.validate_manifest(manifest)

    def test_unknown_source_rejected(self):
        manifest = make_manifest()
        manifest["assets"][0]["source"] = "mystery"
        with self.assertRaises(prepare_assets.AssetError):
            prepare_assets.validate_manifest(manifest)


class VerifyTests(unittest.TestCase):
    def test_matching_staged_file_passes(self):
        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            TempWorkspace(self, tmp)
            manifest = make_manifest()
            stage_bytes(tmp, manifest, b"expected-bytes")
            self.assertEqual(prepare_assets.verify(manifest), 1)

    def test_missing_asset_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            TempWorkspace(self, tmp)
            manifest = make_manifest()
            with self.assertRaises(prepare_assets.AssetError) as ctx:
                prepare_assets.verify(manifest)
            self.assertIn("missing staged file", str(ctx.exception))

    def test_substituted_model_fails_checksum(self):
        """The F20/F22 negative control: wrong bytes under the right name fail."""
        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            TempWorkspace(self, tmp)
            manifest = make_manifest()
            stage_bytes(tmp, manifest, b"substituted-attacker-bytes")
            with self.assertRaises(prepare_assets.AssetError) as ctx:
                prepare_assets.verify(manifest)
            self.assertIn("checksum", str(ctx.exception).lower())


class StageTests(unittest.TestCase):
    def _fake_response(self, data: bytes):
        response = mock.Mock()
        response.read.return_value = data
        response.__enter__ = lambda s: s
        response.__exit__ = lambda s, *a: False
        return response

    def test_stage_writes_verified_bytes(self):
        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            TempWorkspace(self, tmp)
            manifest = make_manifest()
            with mock.patch.object(prepare_assets.urllib.request, "urlopen",
                                   return_value=self._fake_response(b"expected-bytes")):
                self.assertEqual(prepare_assets.stage(manifest), 1)
            target = tmp / STAGING / "models/test/blob.bin"
            self.assertEqual(target.read_bytes(), b"expected-bytes")

    def test_stage_checksum_mismatch_writes_nothing(self):
        """A download whose bytes fail the manifest checksum leaves no file."""
        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            TempWorkspace(self, tmp)
            manifest = make_manifest()
            with mock.patch.object(prepare_assets.urllib.request, "urlopen",
                                   return_value=self._fake_response(b"forged-model")):
                with self.assertRaises(prepare_assets.AssetError):
                    prepare_assets.stage(manifest)
            self.assertFalse((tmp / STAGING / "models/test/blob.bin").exists())

    def test_stage_network_error_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            TempWorkspace(self, tmp)
            manifest = make_manifest()
            with mock.patch.object(prepare_assets.urllib.request, "urlopen",
                                   side_effect=urllib.error.URLError("offline")):
                with self.assertRaises(prepare_assets.AssetError):
                    prepare_assets.stage(manifest)
            self.assertFalse((tmp / STAGING / "models/test/blob.bin").exists())


class CliTests(unittest.TestCase):
    def test_verify_action_on_live_checkout(self):
        """The committed staged assets verify in the real checkout."""
        stdout = io.StringIO()
        argv = sys.argv
        sys.argv = ["prepare_assets.py", "verify"]
        try:
            with redirect_stdout(stdout):
                code = prepare_assets.main()
        finally:
            sys.argv = argv
        self.assertEqual(code, 0)
        self.assertIn("verified", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
