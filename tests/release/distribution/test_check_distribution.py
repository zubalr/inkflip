"""T47 preparation: distribution-checker tests against disposable
distributions.

Each test builds a minimal, self-contained distribution tree (manifest +
shipped roots + license evidence + NOTICE) in a temporary directory and runs
scripts/check_distribution.py against it, proving:

  - a valid distribution passes;
  - byte/hash tampering, missing files, undeclared shipped assets, missing
    or empty license evidence, deleted/empty NOTICE, notice inconsistencies,
    private content, symlinks and path escapes all FAIL with the specific
    reported reason.

These fixtures are generated per run and never committed.
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


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class DistributionCheckerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    # ---------- fixture builders ----------

    def write(self, rel: str, data: bytes):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def write_manifest(self, manifest: dict):
        (self.root / "distribution.json").write_text(json.dumps(manifest, indent=2))

    def build_valid_distribution(self) -> dict:
        """A tiny but complete distribution: one third-party staged asset
        group (with a digest source), one project-original explicit file,
        license evidence, and a consistent NOTICE."""
        asset_bytes = b"third-party wasm engine bytes"
        asset_sha = sha256_bytes(asset_bytes)
        self.write("apps/web/public/assets/engine/7.0.0/engine.wasm", asset_bytes)
        # The digest source the manifest references.
        self.write(
            "config/resolved-assets.json",
            json.dumps(
                {
                    "assets": [
                        {
                            "id": "engine-core",
                            "files": [
                                {
                                    "staged_path": "assets/engine/7.0.0/engine.wasm",
                                    "sha256": asset_sha,
                                    "bytes": len(asset_bytes),
                                }
                            ],
                        }
                    ]
                }
            ).encode(),
        )
        self.write("licenses/engine-7.0.0/LICENSE.txt", b"Apache License 2.0 (fixture text)\n")
        example_bytes = b"project-original example support file"
        self.write("apps/web/public/examples/demo/index.html", example_bytes)
        self.write("NOTICE", b"NOTICE\n\nThird-party components:\n  engine-core 7.0.0\n")
        manifest = {
            "schema_version": "1.0.0",
            "distribution": {"shipped_roots": ["apps/web/public/assets", "apps/web/public/examples"]},
            "groups": [
                {
                    "id": "engine-core",
                    "third_party": True,
                    "license": "Apache-2.0",
                    "license_evidence": "licenses/engine-7.0.0/LICENSE.txt",
                    "notice_name": "engine-core 7.0.0",
                    "digest_source": {
                        "path": "config/resolved-assets.json",
                        "group": "engine-core",
                        "file_list": "assets[].files[]",
                        "path_field": "staged_path",
                        "path_prefix": "apps/web/public/",
                        "digest_field": "sha256",
                        "bytes_field": "bytes",
                    },
                },
                {
                    "id": "demo-example",
                    "third_party": False,
                    "license": "MIT (project-original)",
                    "license_evidence": "apps/web/public/examples/demo/index.html",
                    "notice_name": None,
                    "explicit_files": [
                        {
                            "path": "apps/web/public/examples/demo/index.html",
                            "sha256": sha256_bytes(example_bytes),
                            "bytes": len(example_bytes),
                        }
                    ],
                },
            ],
            "notice": "NOTICE",
            "private_content_patterns": ["\\.private", "canary", "\\.log$"],
            "symlink_policy": "reject",
        }
        self.write_manifest(manifest)
        return manifest

    # ---------- helpers ----------

    def run_checker(self, *extra: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(CHECKER), "--release", "--manifest", "distribution.json", "--root", str(self.root), *extra],
            capture_output=True,
            text=True,
            timeout=60,
        )

    def assert_failure_reason(self, proc: subprocess.CompletedProcess, needle: str):
        self.assertEqual(proc.returncode, 1, msg=proc.stdout + proc.stderr)
        self.assertIn(needle, proc.stdout, msg=proc.stdout)

    # ---------- tests ----------

    def test_valid_distribution_passes(self):
        self.build_valid_distribution()
        proc = self.run_checker()
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
        self.assertIn("PASSED for", proc.stdout)

    def test_hash_tampering_fails(self):
        self.build_valid_distribution()
        self.write("apps/web/public/assets/engine/7.0.0/engine.wasm", b"tampered bytes")
        proc = self.run_checker()
        self.assert_failure_reason(proc, "hash mismatch")

    def test_size_tampering_fails(self):
        self.build_valid_distribution()
        self.write("apps/web/public/assets/engine/7.0.0/engine.wasm", b"third-party wasm engine bytes!")
        proc = self.run_checker()
        self.assert_failure_reason(proc, "size mismatch")

    def test_missing_declared_file_fails(self):
        self.build_valid_distribution()
        (self.root / "apps/web/public/assets/engine/7.0.0/engine.wasm").unlink()
        proc = self.run_checker()
        self.assert_failure_reason(proc, "missing declared file")

    def test_undeclared_shipped_asset_fails(self):
        self.build_valid_distribution()
        self.write("apps/web/public/assets/engine/7.0.0/extra.bin", b"unlisted payload")
        proc = self.run_checker()
        self.assert_failure_reason(proc, "undeclared shipped asset")

    def test_missing_license_evidence_fails(self):
        self.build_valid_distribution()
        (self.root / "licenses/engine-7.0.0/LICENSE.txt").unlink()
        proc = self.run_checker()
        self.assert_failure_reason(proc, "license evidence missing or empty")

    def test_empty_license_evidence_fails(self):
        self.build_valid_distribution()
        self.write("licenses/engine-7.0.0/LICENSE.txt", b"")
        proc = self.run_checker()
        self.assert_failure_reason(proc, "license evidence missing or empty")

    def test_missing_license_declaration_fails(self):
        manifest = self.build_valid_distribution()
        manifest["groups"][0]["license"] = ""
        self.write_manifest(manifest)
        proc = self.run_checker()
        self.assert_failure_reason(proc, "no license declared")

    def test_deleted_notice_fails(self):
        self.build_valid_distribution()
        (self.root / "NOTICE").unlink()
        proc = self.run_checker()
        self.assert_failure_reason(proc, "NOTICE missing or empty")

    def test_notice_not_naming_third_party_group_fails(self):
        self.build_valid_distribution()
        self.write("NOTICE", b"NOTICE\n\n(missing the engine-core entry)\n")
        proc = self.run_checker()
        self.assert_failure_reason(proc, "notice inconsistency")

    def test_private_content_in_shipped_root_fails(self):
        self.build_valid_distribution()
        self.write("apps/web/public/assets/engine/7.0.0/canary-capture.json", b"{}")
        proc = self.run_checker()
        self.assert_failure_reason(proc, "private/development content")

    def test_symlink_in_shipped_root_fails(self):
        self.build_valid_distribution()
        target = self.write("outside/secret.txt", b"x")
        link = self.root / "apps/web/public/assets/engine/7.0.0/linked.bin"
        link.symlink_to(target)
        proc = self.run_checker()
        self.assert_failure_reason(proc, "symlink inside shipped root")

    def test_path_escape_is_config_error(self):
        self.build_valid_distribution()
        manifest = json.loads((self.root / "distribution.json").read_text())
        manifest["groups"][1]["explicit_files"][0]["path"] = "../../outside/secret.txt"
        self.write_manifest(manifest)
        proc = self.run_checker()
        self.assertEqual(proc.returncode, 2, msg=proc.stdout)
        self.assertIn("escapes repository root", proc.stdout)

    def test_absolute_path_is_config_error(self):
        self.build_valid_distribution()
        manifest = json.loads((self.root / "distribution.json").read_text())
        manifest["groups"][1]["explicit_files"][0]["path"] = "/etc/passwd"
        self.write_manifest(manifest)
        proc = self.run_checker()
        self.assertEqual(proc.returncode, 2, msg=proc.stdout)
        self.assertIn("escapes repository root", proc.stdout)

    def test_missing_manifest_is_config_error(self):
        proc = self.run_checker()
        self.assertEqual(proc.returncode, 2, msg=proc.stdout + proc.stderr)

    def test_json_report_is_deterministic(self):
        self.build_valid_distribution()
        self.write("apps/web/public/assets/engine/7.0.0/extra.bin", b"unlisted")
        out1 = self.run_checker("--json").stdout
        out2 = self.run_checker("--json").stdout
        self.assertEqual(out1, out2)
        payload = json.loads(out1)
        self.assertFalse(payload["ok"])
        self.assertTrue(any("undeclared shipped asset" in p for p in payload["problems"]))


if __name__ == "__main__":
    unittest.main()
