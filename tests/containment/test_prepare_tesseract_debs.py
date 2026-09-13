"""Digest-pinned tesseract retrieval: missing/tampered/incomplete-cache."""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from urllib.error import URLError

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "distribution" / "prepare_tesseract_debs.py"


def load_prepare():
    import importlib.util

    spec = importlib.util.spec_from_file_location("prepare_tesseract_debs", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeResponse:
    def __init__(self, data: bytes, status: int = 200) -> None:
        self._data = data
        self.status = status

    def read(self) -> bytes:
        return self._data

    def getcode(self) -> int:
        return self.status

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args) -> None:
        return None


class TestPrepareTesseractDebs(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = load_prepare()
        self.tmp = tempfile.TemporaryDirectory(prefix="inkflip-tess-")
        self.root = Path(self.tmp.name)
        self.cache = self.root / ".private" / "cache" / "tesseract" / "debs"
        self.stamp = self.root / "release" / "tesseract" / "tesseract.stamp.json"
        payload = b"deb-bytes-for-test"
        self.sha256 = hashlib.sha256(payload).hexdigest()
        self.sha1 = hashlib.sha1(payload).hexdigest()
        self.payload = payload
        self.stamp.parent.mkdir(parents=True)
        self.stamp.write_text(
            json.dumps(
                {
                    "kind": "inkflip-native-tesseract-debs",
                    "schema_version": "1.1.0",
                    "packages": [
                        {
                            "filename": "tesseract-ocr_5.5.0-1+b1_amd64.deb",
                            "sha256": self.sha256,
                            "sha1": self.sha1,
                            "bytes": len(payload),
                            "snapshot_url": f"https://snapshot.debian.org/file/{self.sha1}",
                        }
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_script_does_not_invoke_apt_get(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("apt-get update", text)
        self.assertNotIn("apt-get install", text)
        self.assertIn("snapshot.debian.org/file", text)

    def test_check_missing_is_distinct_from_tampered(self) -> None:
        code, lines = self.mod.prepare(
            stamp_path=self.stamp,
            cache=self.cache,
            root=self.root,
            download_missing=False,
        )
        self.assertEqual(code, 2)
        joined = "\n".join(lines)
        self.assertIn("missing", joined)
        self.assertNotIn("tampered", joined)

        self.cache.mkdir(parents=True, exist_ok=True)
        (self.cache / "tesseract-ocr_5.5.0-1+b1_amd64.deb").write_bytes(b"not-the-deb")
        code, lines = self.mod.prepare(
            stamp_path=self.stamp,
            cache=self.cache,
            root=self.root,
            download_missing=False,
        )
        self.assertEqual(code, 2)
        joined = "\n".join(lines)
        self.assertIn("tampered", joined)

    def test_fetch_from_snapshot_url_then_offline_verify(self) -> None:
        def opener(request, timeout=0):
            self.assertIn("snapshot.debian.org/file/", request.full_url)
            return FakeResponse(self.payload)

        code, lines = self.mod.prepare(
            stamp_path=self.stamp,
            cache=self.cache,
            root=self.root,
            download_missing=True,
            opener=opener,
        )
        self.assertEqual(code, 0, lines)
        self.assertTrue((self.cache / "tesseract-ocr_5.5.0-1+b1_amd64.deb").is_file())
        code, lines = self.mod.prepare(
            stamp_path=self.stamp,
            cache=self.cache,
            root=self.root,
            download_missing=False,
        )
        self.assertEqual(code, 0, lines)

    def test_incomplete_cache_when_fetch_fails(self) -> None:
        def opener(request, timeout=0):
            raise URLError("snapshot unavailable")

        code, lines = self.mod.prepare(
            stamp_path=self.stamp,
            cache=self.cache,
            root=self.root,
            download_missing=True,
            opener=opener,
        )
        self.assertEqual(code, 2)
        self.assertTrue(any("incomplete-cache" in line for line in lines), lines)

    def test_external_symlink_cache_is_rejected(self) -> None:
        outside = Path(self.tmp.name + "-outside")
        outside.mkdir()
        (outside / "secret.deb").write_bytes(self.payload)
        self.cache.parent.mkdir(parents=True)
        self.cache.symlink_to(outside)
        with self.assertRaises(RuntimeError):
            self.mod.prepare(
                stamp_path=self.stamp,
                cache=self.cache,
                root=self.root,
                download_missing=False,
            )


if __name__ == "__main__":
    unittest.main()
