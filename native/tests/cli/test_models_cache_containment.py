"""Model preparation must stay inside the cache directory.

`prepare_models` composed the destination as `cache_dir / model_id / name` from an
untrusted manifest and validated neither segment. Reproduced before the guard:

    id="../../outside/escaped"  -> cache/../../outside/escaped/model.traineddata
    id="/tmp/inkflip-escape"    -> /tmp/inkflip-escape/model.traineddata   (written!)

so a manifest could place model bytes anywhere the process could write.
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NATIVE = ROOT / "native"
if str(NATIVE) not in sys.path:
    sys.path.insert(0, str(NATIVE))

from inkflip.cli.main import EXIT_INVALID_ARGS, EXIT_PARTIAL_RUN, main  # noqa: E402
from inkflip.cli.models_cmd import ModelPrepareError, prepare_models  # noqa: E402


class ModelCacheContainmentCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.td = Path(self.tmp.name)
        self.src = self.td / "src"
        self.src.mkdir()
        self.payload = b"model-bytes"
        (self.src / "model.traineddata").write_bytes(self.payload)
        self.digest = hashlib.sha256(self.payload).hexdigest()
        self.cache = self.td / "cache"

    def tearDown(self):
        self.tmp.cleanup()

    def manifest(self, model_id: str, name: str = "model.traineddata") -> Path:
        path = self.td / "manifest.json"
        path.write_text(json.dumps({
            "kind": "inkflip_model_manifest",
            "schema_version": "1.0.0",
            "models": [{
                "id": model_id,
                "sha256": self.digest,
                "path": str(self.src / name),
                "purpose": "ocr_language_model",
            }],
        }))
        return path

    def escaped(self) -> list[str]:
        """Files written outside the cache root, ignoring this test's own inputs."""
        cache_root = self.cache.resolve()
        allowed = {self.src.resolve(), self.td}
        out = []
        for candidate in self.td.rglob("*"):
            if not candidate.is_file():
                continue
            resolved = candidate.resolve()
            if cache_root in resolved.parents:
                continue
            if resolved.parent in allowed or candidate.name == "manifest.json":
                continue
            out.append(str(candidate.relative_to(self.td)))
        return sorted(out)


class TestTraversalIdsAreRefused(ModelCacheContainmentCase):
    def test_parent_traversal_id_is_refused(self):
        with self.assertRaises(ModelPrepareError) as ctx:
            prepare_models(self.manifest("../../outside/escaped"), self.cache)
        self.assertIn("safe path segment", str(ctx.exception))
        self.assertEqual(self.escaped(), [], "nothing may be written outside the cache")

    def test_absolute_id_is_refused(self):
        # A unique, non-existent destination: a previous unpatched run may have
        # created other probe paths, so this asserts only about this call.
        outside = Path(tempfile.mkdtemp(prefix="inkflip-escape-")) / "nested" / "deep"
        with self.assertRaises(ModelPrepareError):
            prepare_models(self.manifest(str(outside)), self.cache)
        self.assertFalse(outside.exists(), "an absolute id must not create its directory tree")

    def test_nested_id_is_refused(self):
        with self.assertRaises(ModelPrepareError):
            prepare_models(self.manifest("a/b/c"), self.cache)

    def test_dot_id_is_refused(self):
        with self.assertRaises(ModelPrepareError):
            prepare_models(self.manifest(".."), self.cache)

    def test_cli_reports_a_configuration_error(self):
        code = main(["models", "prepare", "--manifest", str(self.manifest("../escape")), "--cache", str(self.cache)])
        self.assertEqual(code, EXIT_INVALID_ARGS)
        self.assertEqual(self.escaped(), [])


class TestLegitimateIdsStillWork(ModelCacheContainmentCase):
    def test_plain_id_prepares_normally(self):
        record = prepare_models(self.manifest("eng_lstm"), self.cache)
        self.assertTrue(record["ready"])
        self.assertEqual(record["prepared_count"], 1)
        written = self.cache / "eng_lstm" / "model.traineddata"
        self.assertTrue(written.is_file())
        self.assertEqual(written.read_bytes(), self.payload)

    def test_dotted_and_hyphenated_id_is_allowed(self):
        record = prepare_models(self.manifest("eng.lstm-v2"), self.cache)
        self.assertTrue(record["ready"])

    def test_missing_source_is_still_unavailable_not_a_fault(self):
        path = self.td / "manifest.json"
        path.write_text(json.dumps({
            "kind": "inkflip_model_manifest",
            "schema_version": "1.0.0",
            "models": [{"id": "eng", "sha256": self.digest, "path": str(self.td / "absent.traineddata"),
                        "purpose": "ocr_language_model"}],
        }))
        code = main(["models", "prepare", "--manifest", str(path), "--cache", str(self.cache)])
        self.assertEqual(code, EXIT_PARTIAL_RUN)


if __name__ == "__main__":
    unittest.main()


class TestLocalFileNamesAreNotOverRestricted(ModelCacheContainmentCase):
    """Containment must not become a gratuitous filename restriction."""

    def test_a_unicode_file_name_is_accepted(self):
        name = "モデル—eng.traineddata"
        (self.src / name).write_bytes(self.payload)
        path = self.td / "manifest.json"
        path.write_text(json.dumps({
            "kind": "inkflip_model_manifest",
            "schema_version": "1.0.0",
            "models": [{"id": "eng", "sha256": self.digest, "path": str(self.src / name),
                        "purpose": "ocr_language_model"}],
        }))
        record = prepare_models(path, self.cache)
        self.assertTrue(record["ready"])
        self.assertTrue((self.cache / "eng" / name).is_file())

    def test_a_file_name_with_a_separator_is_refused(self):
        nested = self.src / "sub" / "model.traineddata"
        nested.parent.mkdir()
        nested.write_bytes(self.payload)
        path = self.td / "manifest.json"
        path.write_text(json.dumps({
            "kind": "inkflip_model_manifest",
            "schema_version": "1.0.0",
            "models": [{"id": "eng", "sha256": self.digest, "path": str(nested),
                        "purpose": "ocr_language_model"}],
        }))
        # A nested source resolves to its own file name, which is still a single segment.
        record = prepare_models(path, self.cache)
        self.assertTrue(record["ready"])


class TestDuplicateModelIdsAreRefused(ModelCacheContainmentCase):
    def test_two_entries_with_one_id_are_refused(self):
        other = self.src / "other.traineddata"
        other.write_bytes(b"other-bytes")
        path = self.td / "manifest.json"
        path.write_text(json.dumps({
            "kind": "inkflip_model_manifest",
            "schema_version": "1.0.0",
            "models": [
                {"id": "eng", "sha256": self.digest, "path": str(self.src / "model.traineddata"),
                 "purpose": "ocr_language_model"},
                {"id": "eng", "sha256": hashlib.sha256(b"other-bytes").hexdigest(), "path": str(other),
                 "purpose": "ocr_language_model"},
            ],
        }))
        with self.assertRaises(ModelPrepareError) as ctx:
            prepare_models(path, self.cache)
        self.assertIn("Duplicate model id", str(ctx.exception))

    def test_distinct_ids_with_the_same_file_name_are_fine(self):
        second = self.td / "second"
        second.mkdir()
        (second / "model.traineddata").write_bytes(self.payload)
        path = self.td / "manifest.json"
        path.write_text(json.dumps({
            "kind": "inkflip_model_manifest",
            "schema_version": "1.0.0",
            "models": [
                {"id": "one", "sha256": self.digest, "path": str(self.src / "model.traineddata"),
                 "purpose": "ocr_language_model"},
                {"id": "two", "sha256": self.digest, "path": str(second / "model.traineddata"),
                 "purpose": "ocr_language_model"},
            ],
        }))
        record = prepare_models(path, self.cache)
        self.assertEqual(record["prepared_count"], 2)
