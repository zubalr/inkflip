"""TEST-36 frozen-manifest integrity and CLI honesty.

The committed corpus manifests are frozen from fixtures/manifest.json:
byte drift, dropped entries or group retagging fail verification, and the
contract CorpusManifest shape is enforced.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import helpers
from helpers import EVALUATOR, MANIFESTS, ROOT

from evaluation.protocol import manifest


def cli(*argv: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(EVALUATOR), *argv],
        capture_output=True, text=True, cwd=ROOT, timeout=60)


class TestFrozenCorpusManifests(unittest.TestCase):
    def test_committed_manifests_match_fixture_regeneration(self):
        fixture = json.loads((ROOT / "fixtures/manifest.json").read_text())
        for split, committed_name in (
                ("development", "development.corpus.json"),
                ("public", "public.corpus.json")):
            built = manifest.build_corpus_manifest(fixture, split)
            committed = manifest.load_manifest(MANIFESTS / committed_name)
            self.assertEqual(committed, built, committed_name)

    def test_corpus_manifests_are_contract_shaped(self):
        for name in ("development.corpus.json", "public.corpus.json"):
            data = manifest.load_manifest(MANIFESTS / name)
            self.assertEqual(data["kind"], "corpus_manifest")
            self.assertEqual(data["source_root_policy"],
                             "explicit_local_root_no_symlinks")
            for entry in data["entries"]:
                self.assertTrue((ROOT / entry["source_path"]).is_file(),
                                entry["source_path"])

    def test_every_entry_sha256_matches_the_fixture_bytes(self):
        for name in ("development.corpus.json", "public.corpus.json"):
            data = manifest.load_manifest(MANIFESTS / name)
            for entry in data["entries"]:
                payload = (ROOT / entry["source_path"]).read_bytes()
                import hashlib
                self.assertEqual(
                    hashlib.sha256(payload).hexdigest(), entry["sha256"],
                    entry["source_path"])

    def test_group_ids_carry_fixture_lineage(self):
        data = manifest.load_manifest(MANIFESTS / "development.corpus.json")
        groups = {e["key"]: e["group_id"] for e in data["entries"]}
        # Control and variant siblings share one group id.
        for stem in ("scan-correct", "scan-raster-only", "scan-shifted"):
            self.assertEqual(groups[stem], "f03-searchable-scan", stem)
        for stem in ("userunit-0-5", "userunit-1", "userunit-2", "userunit-10"):
            self.assertEqual(groups[stem], "f08-userunit", stem)

    def test_emit_corpus_check_detects_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            drifted = Path(tmp) / "drifted.json"
            result = cli("emit-corpus", "--split", "development",
                         "--out", str(drifted))
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(drifted.read_text())
            data["entries"][0]["sha256"] = "0" * 64
            drifted.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
            result = cli("emit-corpus", "--split", "development",
                         "--out", str(drifted), "--check")
            self.assertEqual(result.returncode, 1)
            self.assertIn("CHECK FAIL", result.stdout)

    def test_emit_corpus_check_passes_on_committed(self):
        for split, name in (("development", "development.corpus.json"),
                            ("public", "public.corpus.json")):
            result = cli("emit-corpus", "--split", split,
                         "--out", str(MANIFESTS / name), "--check")
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_plan_pins_the_committed_manifest_digests(self):
        plan = manifest.load_manifest(MANIFESTS / "evaluation.plan.json")
        for split, name in (("development", "development.corpus.json"),
                            ("public_demo", "public.corpus.json")):
            ref = plan["split_manifests"][split]
            self.assertEqual(ref["path"], f"evaluation/manifests/{name}")
            self.assertEqual(ref["sha256"], manifest.file_digest(MANIFESTS / name),
                             f"{split} pinned digest drifted from {name}")

    def test_evaluate_cli_verify_splits_passes_on_committed(self):
        result = cli("verify-splits",
                     str(MANIFESTS / "development.corpus.json"),
                     str(MANIFESTS / "public.corpus.json"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("no sibling straddles", result.stdout)


class TestCorpusManifestValidation(unittest.TestCase):
    def test_rejects_open_and_malformed_entries(self):
        base = manifest.build_corpus_manifest(
            json.loads((ROOT / "fixtures/manifest.json").read_text()), "public")
        extra = dict(base)
        extra["note"] = "not closed"
        with self.assertRaises(manifest.ManifestError):
            manifest.validate_corpus_manifest(extra)
        bad_key = json.loads(json.dumps(base))
        bad_key["entries"][0]["key"] = "BAD KEY!"
        with self.assertRaises(manifest.ManifestError):
            manifest.validate_corpus_manifest(bad_key)
        traversal = json.loads(json.dumps(base))
        traversal["entries"][0]["source_path"] = "../escape.pdf"
        with self.assertRaises(manifest.ManifestError):
            manifest.validate_corpus_manifest(traversal)

    def test_page_keys_and_groups_are_content_addressed(self):
        data = manifest.load_manifest(MANIFESTS / "public.corpus.json")
        keys = manifest.corpus_page_keys(data)
        groups = manifest.corpus_groups(data)
        for entry in data["entries"]:
            for page in entry["pages"]:
                key = f"{entry['sha256']}:{page}"
                self.assertIn(key, keys)
                self.assertIn(groups[key], {e["group_id"] for e in data["entries"]})

    def test_identical_bytes_collapse_to_one_sample_and_group(self):
        # mapping-control and geometry-control are byte-identical in the
        # committed corpus: the same document must be one sample unit and
        # one bootstrap group, never two independent observations.
        data = manifest.load_manifest(MANIFESTS / "public.corpus.json")
        mapping = next(e for e in data["entries"] if e["key"] == "mapping-control")
        geometry = next(e for e in data["entries"] if e["key"] == "geometry-control")
        self.assertEqual(mapping["sha256"], geometry["sha256"])
        keys = manifest.corpus_page_keys(data)
        self.assertEqual(len(keys), len(set(keys)))
        shared_key = f"{mapping['sha256']}:0"
        groups = manifest.corpus_groups(data)
        # Byte identity unions whole declared families transitively: the
        # geometry-control bytes are the mapping-control bytes, so all F07
        # rotation siblings share F01's source ancestry and resample as ONE
        # cluster under the canonical (smallest) group id.
        self.assertEqual(groups[shared_key], "f01-mapping-amount")
        for entry in data["entries"]:
            if entry["group_id"] in ("f01-mapping-amount", "f07-origins-rotation"):
                for page in entry["pages"]:
                    self.assertEqual(
                        groups[f"{entry['sha256']}:{page}"],
                        "f01-mapping-amount", entry["key"])
            else:
                for page in entry["pages"]:
                    self.assertEqual(
                        groups[f"{entry['sha256']}:{page}"], entry["group_id"],
                        entry["key"])


if __name__ == "__main__":
    unittest.main()
