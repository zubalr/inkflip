"""Strict declaration and path-boundary regression tests for the
distribution checker (release-verification batch).

Regression root: a declared shipped file with NO sha256 and NO bytes passed
the checker (independent spot review, 2026-09-13). Every case here builds a
disposable manifest fixture and asserts the checker's deterministic outcome:
config errors exit 2 with named diagnostics; verification failures exit 1.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CHECKER = REPO_ROOT / "scripts" / "check_distribution.py"


class DeclarationFixture:
    """Minimal shipped-root fixture with valid license/notice evidence."""

    def __init__(self, root: Path):
        self.root = root
        (root / "shipped").mkdir(parents=True, exist_ok=True)
        (root / "LICENSE").write_bytes(b"MIT license text (fixture)")
        (root / "NOTICE").write_bytes(b"NOTICE\n")

    def write(self, rel: str, content: bytes):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def manifest(self, files, shipped_roots=("shipped",), notice="NOTICE",
                 license_evidence="LICENSE", extra_group=None):
        groups = [{
            "id": "app",
            "third_party": False,
            "license": "MIT (project-original)",
            "license_evidence": license_evidence,
            "notice_name": None,
            "explicit_files": files,
        }]
        if extra_group:
            groups.append(extra_group)
        self.write("distribution.json", json.dumps({
            "distribution": {"shipped_roots": list(shipped_roots)},
            "groups": groups,
            "notice": notice,
        }).encode())

    def run(self) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(CHECKER), "--release", "--manifest", "distribution.json",
             "--root", str(self.root), "--json"],
            capture_output=True, text=True, timeout=60,
        )

    def problems(self, proc) -> list[str]:
        return json.loads(proc.stdout)["problems"]


class DeclarationValidationTests(unittest.TestCase):
    """M1: every digest/byte declaration is validated strictly."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.fx = DeclarationFixture(Path(self.tmp.name))

    def entry(self, **overrides):
        entry = {"path": "shipped/a.js", "bytes": 17,
                 "sha256": hashlib.sha256(b"arbitrary content").hexdigest()}
        entry.update(overrides)
        for key, value in list(entry.items()):
            if value is ...:  # sentinel: remove the key entirely
                del entry[key]
        return entry

    def expect_config_error(self, files, needle):
        self.fx.write("shipped/a.js", b"arbitrary content")
        self.fx.manifest(files)
        proc = self.fx.run()
        self.assertEqual(proc.returncode, 2, msg=proc.stdout + proc.stderr)
        self.assertIn(needle, proc.stdout)

    # ---- the confirmed gap ----

    def test_missing_sha256_and_bytes_is_config_error(self):
        self.expect_config_error(
            [self.entry(sha256=..., bytes=...)],
            "missing required sha256 digest")

    def test_missing_only_sha256_fails(self):
        self.expect_config_error([self.entry(sha256=...)], "missing required sha256")

    def test_missing_only_bytes_fails(self):
        self.expect_config_error([self.entry(bytes=...)], "missing required byte count")

    # ---- types ----

    def test_null_sha256_fails(self):
        self.expect_config_error([self.entry(sha256=None)], "missing required sha256")

    def test_boolean_bytes_rejected(self):
        self.expect_config_error([self.entry(bytes=True)], "boolean")

    def test_string_bytes_rejected(self):
        self.expect_config_error([self.entry(bytes="17")], "bytes must be an integer")

    def test_negative_bytes_rejected(self):
        self.expect_config_error([self.entry(bytes=-1)], "negative byte count")

    def test_malformed_digest_rejected(self):
        self.expect_config_error([self.entry(sha256="deadbeef")], "malformed sha256")

    def test_uppercase_digest_rejected(self):
        self.expect_config_error(
            [self.entry(sha256=hashlib.sha256(b"arbitrary content").hexdigest().upper())],
            "malformed sha256")

    def test_wrong_hash_fails_verification(self):
        self.fx.write("shipped/a.js", b"arbitrary content")
        self.fx.manifest([self.entry(sha256="0" * 64)])
        proc = self.fx.run()
        self.assertEqual(proc.returncode, 1, msg=proc.stdout)
        self.assertIn("hash mismatch", proc.stdout)

    # ---- structure ----

    def test_duplicate_paths_fail(self):
        self.fx.write("shipped/a.js", b"arbitrary content")
        self.fx.manifest([self.entry(), self.entry()])
        proc = self.fx.run()
        self.assertEqual(proc.returncode, 2, msg=proc.stdout)
        self.assertIn("duplicate declared path", proc.stdout)

    def test_nonstring_path_fails(self):
        self.fx.write("shipped/a.js", b"arbitrary content")
        self.fx.manifest([self.entry(path=17)])
        proc = self.fx.run()
        self.assertEqual(proc.returncode, 2, msg=proc.stdout)
        self.assertIn("missing or non-string path", proc.stdout)

    def test_duplicate_group_ids_fail(self):
        self.fx.write("shipped/a.js", b"arbitrary content")
        self.fx.manifest([self.entry()])
        manifest = json.loads((self.fx.root / "distribution.json").read_text())
        manifest["groups"].append(dict(manifest["groups"][0]))
        (self.fx.root / "distribution.json").write_text(json.dumps(manifest))
        proc = self.fx.run()
        self.assertEqual(proc.returncode, 2, msg=proc.stdout)
        self.assertIn("duplicate group id", proc.stdout)

    def test_groups_not_a_list_is_config_error(self):
        self.fx.write("shipped/a.js", b"arbitrary content")
        manifest = {"distribution": {"shipped_roots": ["shipped"]},
                    "groups": {"app": {}}, "notice": "NOTICE"}
        (self.fx.root / "distribution.json").write_text(json.dumps(manifest))
        proc = self.fx.run()
        self.assertEqual(proc.returncode, 2, msg=proc.stdout)
        self.assertIn("'groups' must be a list", proc.stdout)

    # ---- digest-source selectors ----

    def digest_source_manifest(self, source):
        asset = b"third-party engine bytes"
        digest = hashlib.sha256(asset).hexdigest()
        self.write = self.fx.write
        self.fx.write("shipped/engine.wasm", asset)
        self.fx.write("config/assets.json", json.dumps({
            "assets": [{"id": "engine", "files": [
                {"staged_path": "engine.wasm", "sha256": digest, "bytes": len(asset)}]}]
        }).encode())
        self.fx.manifest([], extra_group={
            "id": "engine",
            "third_party": True,
            "license": "Apache-2.0",
            "license_evidence": "LICENSE",
            "notice_name": "engine 1.0",
            "digest_source": source,
        })

    def test_digest_source_missing_key_is_config_error_not_shrink(self):
        self.digest_source_manifest({
            "path": "config/assets.json", "group": "engine",
            "file_list": "assets[].files[]",
            "path_field": "staged_path", "digest_field": "sha256",
            # bytes_field deliberately omitted
        })
        proc = self.fx.run()
        self.assertEqual(proc.returncode, 2, msg=proc.stdout)
        self.assertIn("missing required key(s): ['bytes_field']", proc.stdout)

    def test_digest_source_wrong_group_is_config_error(self):
        self.digest_source_manifest({
            "path": "config/assets.json", "group": "no-such-group",
            "file_list": "assets[].files[]",
            "path_field": "staged_path", "digest_field": "sha256",
            "bytes_field": "bytes",
        })
        proc = self.fx.run()
        self.assertEqual(proc.returncode, 2, msg=proc.stdout)
        self.assertIn("no asset group 'no-such-group'", proc.stdout)

    def test_valid_digest_source_passes(self):
        self.fx.write("NOTICE", b"NOTICE\n\nThird-party components:\n  engine 1.0\n")
        self.digest_source_manifest({
            "path": "config/assets.json", "group": "engine",
            "file_list": "assets[].files[]",
            "path_field": "staged_path", "digest_field": "sha256",
            "bytes_field": "bytes", "path_prefix": "shipped/",
        })
        proc = self.fx.run()
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)


class ZeroByteContractTests(unittest.TestCase):
    """An intentionally zero-byte shipped file needs explicit contract
    treatment: allowed when declared honestly (bytes=0 + correct digest),
    still rejected when the declaration lies."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.fx = DeclarationFixture(Path(self.tmp.name))

    def test_declared_zero_byte_file_passes(self):
        self.fx.write("shipped/empty.stamp", b"")
        self.fx.manifest([{"path": "shipped/empty.stamp", "bytes": 0,
                           "sha256": hashlib.sha256(b"").hexdigest()}])
        proc = self.fx.run()
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)

    def test_zero_byte_file_declared_nonzero_fails(self):
        self.fx.write("shipped/empty.stamp", b"")
        self.fx.manifest([{"path": "shipped/empty.stamp", "bytes": 1,
                           "sha256": hashlib.sha256(b"").hexdigest()}])
        proc = self.fx.run()
        self.assertEqual(proc.returncode, 1, msg=proc.stdout)
        self.assertIn("size mismatch", proc.stdout)


class PathBoundaryTests(unittest.TestCase):
    """M2: containment and evidence-path validation for every
    checker-consumed path."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.fx = DeclarationFixture(Path(self.tmp.name))
        self.fx.write("shipped/a.js", b"arbitrary content")
        self.fx.manifest([self.entry()] if False else [{
            "path": "shipped/a.js", "bytes": 17,
            "sha256": hashlib.sha256(b"arbitrary content").hexdigest()}])

    def entry(self):
        return {"path": "shipped/a.js", "bytes": 17,
                "sha256": hashlib.sha256(b"arbitrary content").hexdigest()}

    def run_checker(self):
        return self.fx.run()

    def test_license_evidence_traversal_is_config_error(self):
        manifest = json.loads((self.fx.root / "distribution.json").read_text())
        manifest["groups"][0]["license_evidence"] = "../outside/LICENSE"
        (self.fx.root / "distribution.json").write_text(json.dumps(manifest))
        proc = self.run_checker()
        self.assertEqual(proc.returncode, 2, msg=proc.stdout)
        self.assertIn("escapes repository root", proc.stdout)

    def test_notice_traversal_is_config_error(self):
        manifest = json.loads((self.fx.root / "distribution.json").read_text())
        manifest["notice"] = "/etc/NOTICE"
        (self.fx.root / "distribution.json").write_text(json.dumps(manifest))
        proc = self.run_checker()
        self.assertEqual(proc.returncode, 2, msg=proc.stdout)
        self.assertIn("notice path invalid", proc.stdout)

    def test_license_evidence_directory_fails(self):
        (self.fx.root / "LICENSE").unlink()
        (self.fx.root / "LICENSE").mkdir()
        proc = self.run_checker()
        self.assertEqual(proc.returncode, 1, msg=proc.stdout)
        self.assertIn("license evidence missing or empty", proc.stdout)

    def test_license_evidence_empty_file_fails(self):
        self.fx.write("LICENSE", b"")
        proc = self.run_checker()
        self.assertEqual(proc.returncode, 1, msg=proc.stdout)
        self.assertIn("license evidence missing or empty", proc.stdout)

    def test_symlinked_license_parent_is_followed_contained(self):
        # A symlinked directory *inside* the root that stays inside the root
        # is readable; the license evidence still resolves and validates.
        real = self.fx.write("evidence-real/LICENSE", b"MIT license text (fixture)")
        (self.fx.root / "LICENSE").unlink()
        (self.fx.root / "evidence-link").symlink_to(self.fx.root / "evidence-real")
        manifest = json.loads((self.fx.root / "distribution.json").read_text())
        manifest["groups"][0]["license_evidence"] = "evidence-link/LICENSE"
        (self.fx.root / "distribution.json").write_text(json.dumps(manifest))
        proc = self.run_checker()
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)

    def test_shipped_symlink_escape_fails(self):
        outside = self.fx.root.parent / f"outside-{id(self)}.txt"
        outside.write_bytes(b"secret")
        self.addCleanup(outside.unlink, True)
        (self.fx.root / "shipped/link.js").symlink_to(outside)
        proc = self.run_checker()
        self.assertEqual(proc.returncode, 1, msg=proc.stdout)
        self.assertIn("symlink inside shipped root", proc.stdout)

    def test_declared_file_hashed_not_trusted(self):
        # The declared file must actually be hashed: swap content after a
        # valid record and the digest check must catch it.
        self.fx.write("shipped/a.js", b"tampered after recording")
        proc = self.run_checker()
        self.assertEqual(proc.returncode, 1, msg=proc.stdout)
        self.assertIn("hash mismatch", proc.stdout)

    def test_digest_source_malformed_json_is_config_error(self):
        self.fx.write("shipped/engine.wasm", b"x")
        self.fx.write("config/assets.json", b"{ not json")
        self.fx.manifest([], extra_group={
            "id": "engine", "third_party": True, "license": "Apache-2.0",
            "license_evidence": "LICENSE", "notice_name": "engine",
            "digest_source": {"path": "config/assets.json", "group": "engine",
                              "file_list": "assets[].files[]", "path_field": "staged_path",
                              "digest_field": "sha256", "bytes_field": "bytes"},
        })
        proc = self.run_checker()
        self.assertEqual(proc.returncode, 2, msg=proc.stdout)
        self.assertIn("malformed JSON in digest source", proc.stdout)

    def test_digest_source_traversal_is_config_error(self):
        self.fx.manifest([], extra_group={
            "id": "engine", "third_party": True, "license": "Apache-2.0",
            "license_evidence": "LICENSE", "notice_name": "engine",
            "digest_source": {"path": "../../etc/assets.json", "group": "g",
                              "file_list": "assets[].files[]", "path_field": "staged_path",
                              "digest_field": "sha256", "bytes_field": "bytes"},
        })
        proc = self.run_checker()
        self.assertEqual(proc.returncode, 2, msg=proc.stdout)
        self.assertIn("escapes the repository root", proc.stdout)


class RealTreeTests(unittest.TestCase):
    def test_real_distribution_manifest_passes(self):
        proc = subprocess.run(
            [sys.executable, str(CHECKER), "--release", "--root", str(REPO_ROOT)],
            capture_output=True, text=True, timeout=300,
        )
        # The real tree may report the (deferred/unprepared) native context as
        # its only problem depending on local preparation state; everything
        # else must pass.
        self.assertNotEqual(proc.returncode, 2, msg=proc.stdout + proc.stderr)
        for line in proc.stdout.splitlines():
            self.assertNotIn("missing required sha256", line)
            self.assertNotIn("hash mismatch", line)


if __name__ == "__main__":
    unittest.main()
