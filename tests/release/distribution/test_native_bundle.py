"""T47 preparation: native-bundle and dist-surface checker tests.

Builds disposable native-bundle fixtures (wheels manifest + stamps + fake
prepared artifacts) and dist fixtures in temporary directories and proves:

  - a valid prepared bundle passes;
  - wrong-platform wheel filenames, duplicate entries, absent required
    components, unexpected packages, missing license evidence, missing or
    incomplete node/model stamps, and missing prepared artifacts FAIL;
  - a recorded dist manifest passes and tampered/undeclared dist files FAIL.
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

WHEEL_SHA = hashlib.sha256(b"fake wheel bytes").hexdigest()


class NativeBundleCheckerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.write("NOTICE", b"NOTICE\n")
        self.write(
            "release/native-requirements.lock",
            b"# generated\npillow==12.3.0 --hash=sha256:deadbeef\n",
        )

    def write(self, rel: str, content: bytes):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def write_wheels_manifest(self, wheels):
        self.write(
            "release/native-wheels.manifest.json",
            json.dumps({"wheels": wheels}, indent=2).encode(),
        )

    def write_bundle(self, wheels, *, context=True, node=True, model=True):
        self.write_wheels_manifest(wheels)
        self.write("release/native-wheels.manifest.json", json.dumps({"wheels": wheels}).encode())
        if node:
            self.write(
                "release/node/node.stamp.json",
                json.dumps(
                    {
                        "version": "22.23.2",
                        "sha256": "a" * 64,
                        "url": "https://nodejs.org/dist/v22.23.2/node-v22.23.2-linux-x64.tar.xz",
                        "shasums256_source": "https://nodejs.org/dist/v22.23.2/SHASUMS256.txt",
                    }
                ).encode(),
            )
        if model:
            self.write(
                "release/models/model.stamp.json",
                json.dumps(
                    {
                        "name": "tessdata_fast (eng.traineddata)",
                        "sha256": "b" * 64,
                        "license": "Apache-2.0",
                        "source": "config/resolved-assets.json",
                    }
                ).encode(),
            )
        if context:
            for w in wheels:
                if w.get("path_in_context"):
                    self.write(
                        f".private/distribution/native-bundle/{w['path_in_context']}",
                        bytes.fromhex(w["sha256"][: len(w["sha256"])]) if False else b"fake wheel bytes",
                    )

    def base_wheel(self, **overrides):
        wheel = {
            "name": "pillow",
            "version": "12.3.0",
            "filename": "pillow-12.3.0-cp313-cp313-manylinux_2_28_x86_64.whl",
            "url": "https://files.pythonhosted.org/packages/x/pillow-12.3.0-cp313-cp313-manylinux_2_28_x86_64.whl",
            "sha256": WHEEL_SHA,
            "path_in_context": "wheels/pillow-12.3.0-cp313-cp313-manylinux_2_28_x86_64.whl",
            "license_evidence": "release/notices/pillow-12.3.0/LICENSE.txt",
        }
        wheel.update(overrides)
        self.write(wheel["license_evidence"], b"MIT license text (fixture)")
        return wheel

    def write_manifest(self, expected=("pillow",)):
        self.write(
            "distribution.json",
            json.dumps(
                {
                    "distribution": {"shipped_roots": []},
                    "groups": [],
                    "notice": "NOTICE",
                    "native_bundle": {
                        "requirements_lock": "release/native-requirements.lock",
                        "wheels_manifest": "release/native-wheels.manifest.json",
                        "expected_runtime_packages": list(expected),
                        "context_dir": ".private/distribution/native-bundle",
                        "node_stamp": "release/node/node.stamp.json",
                        "model_stamp": "release/models/model.stamp.json",
                        "notices_dir": "release/notices/",
                    },
                }
            ).encode(),
        )

    def run_checker(self, *extra: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(CHECKER), "--release", "--manifest", "distribution.json", "--root", str(self.root), *extra],
            capture_output=True,
            text=True,
            timeout=60,
        )

    def assert_failure(self, proc, needle):
        self.assertEqual(proc.returncode, 1, msg=proc.stdout + proc.stderr)
        self.assertIn(needle, proc.stdout)

    # ---------- tests ----------

    def test_valid_prepared_bundle_passes(self):
        self.write_bundle([self.base_wheel()])
        self.write_manifest()
        proc = self.run_checker()
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)

    def test_wrong_platform_wheel_fails(self):
        self.write_bundle(
            [self.base_wheel(filename="pillow-12.3.0-cp313-cp313-musllinux_1_2_x86_64.whl",
                             path_in_context="wheels/pillow-12.3.0-cp313-cp313-musllinux_1_2_x86_64.whl")]
        )
        self.write_manifest()
        proc = self.run_checker()
        self.assert_failure(proc, "platform/ABI tag check")

    def test_wrong_arch_wheel_fails(self):
        self.write_bundle(
            [self.base_wheel(filename="pillow-12.3.0-cp313-cp313-manylinux_2_28_aarch64.whl",
                             path_in_context="wheels/pillow-12.3.0-cp313-cp313-manylinux_2_28_aarch64.whl")]
        )
        self.write_manifest()
        proc = self.run_checker()
        self.assert_failure(proc, "platform/ABI tag check")

    def test_duplicate_entries_fail(self):
        self.write_bundle([self.base_wheel(), self.base_wheel()])
        self.write_manifest()
        proc = self.run_checker()
        self.assert_failure(proc, "duplicate entries for pillow")

    def test_absent_required_component_fails(self):
        self.write_bundle([self.base_wheel()])
        self.write_manifest(expected=("pillow", "pypdf"))
        proc = self.run_checker()
        self.assert_failure(proc, "required component absent: pypdf")

    def test_unexpected_package_fails(self):
        self.write_bundle([self.base_wheel(), self.base_wheel(name="mystery", version="1.0",
                                                               filename="mystery-1.0-py3-none-any.whl",
                                                               url="https://files.pythonhosted.org/packages/x/mystery-1.0-py3-none-any.whl",
                                                               path_in_context="wheels/mystery-1.0-py3-none-any.whl")])
        self.write_manifest()
        proc = self.run_checker()
        self.assert_failure(proc, "unexpected package in wheels manifest: mystery")

    def test_missing_license_evidence_fails(self):
        wheel = self.base_wheel()
        self.write_bundle([wheel])
        (self.root / wheel["license_evidence"]).unlink()
        self.write_manifest()
        proc = self.run_checker()
        self.assert_failure(proc, "license evidence missing")

    def test_incomplete_node_stamp_fails(self):
        self.write_bundle([self.base_wheel()])
        self.write(
            "release/node/node.stamp.json",
            json.dumps({"version": "22.23.2"}).encode(),
        )
        self.write_manifest()
        proc = self.run_checker()
        self.assert_failure(proc, "node_stamp lacks")

    def test_missing_prepared_artifact_fails(self):
        wheel = self.base_wheel()
        self.write_bundle([wheel])
        (self.root / ".private/distribution/native-bundle" / wheel["path_in_context"]).unlink()
        self.write_manifest()
        proc = self.run_checker()
        self.assert_failure(proc, "prepared wheel missing from context")

    def test_tampered_prepared_artifact_fails(self):
        wheel = self.base_wheel()
        self.write_bundle([wheel])
        self.write(
            f".private/distribution/native-bundle/{wheel['path_in_context']}",
            b"tampered wheel bytes",
        )
        self.write_manifest()
        proc = self.run_checker()
        self.assert_failure(proc, "prepared wheel hash mismatch")

    def test_unprepared_context_is_a_named_failure(self):
        self.write_bundle([self.base_wheel()], context=False)
        self.write_manifest()
        proc = self.run_checker()
        self.assert_failure(proc, "build context not prepared locally")


class DistCheckerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def write(self, rel: str, content: bytes):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def record_dist(self):
        index = b"<!doctype html><title>dist fixture</title>"
        asset = b"console.log(1)"
        self.write("apps/web/dist/index.html", index)
        self.write("apps/web/dist/assets/app-ABC123.js", asset)
        manifest = {
            "dist_root": "apps/web/dist",
            "reject_patterns": ["\\.map$", "\.log$"],
            "files": [
                {"path": "apps/web/dist/index.html", "bytes": len(index),
                 "sha256": hashlib.sha256(index).hexdigest()},
                {"path": "apps/web/dist/assets/app-ABC123.js", "bytes": len(asset),
                 "sha256": hashlib.sha256(asset).hexdigest()},
            ],
        }
        self.write(".private/distribution/dist-manifest.json", json.dumps(manifest).encode())

    def run_checker(self, *extra: str) -> subprocess.CompletedProcess:
        self.write(
            "distribution.json",
            json.dumps({"distribution": {"shipped_roots": []}, "groups": [], "notice": "NOTICE"}).encode(),
        )
        self.write("NOTICE", b"NOTICE\n")
        return subprocess.run(
            [sys.executable, str(CHECKER), "--release", "--manifest", "distribution.json", "--root", str(self.root), *extra],
            capture_output=True,
            text=True,
            timeout=60,
        )

    def test_valid_dist_passes(self):
        self.record_dist()
        proc = self.run_checker("--dist-manifest", ".private/distribution/dist-manifest.json")
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)

    def test_tampered_dist_fails(self):
        self.record_dist()
        self.write("apps/web/dist/index.html", b"tampered")
        proc = self.run_checker("--dist-manifest", ".private/distribution/dist-manifest.json")
        self.assertEqual(proc.returncode, 1, msg=proc.stdout)
        self.assertIn("dist: hash mismatch", proc.stdout)

    def test_undeclared_dist_file_fails(self):
        self.record_dist()
        self.write("apps/web/dist/assets/extra-XYZ.js", b"stray")
        proc = self.run_checker("--dist-manifest", ".private/distribution/dist-manifest.json")
        self.assertEqual(proc.returncode, 1, msg=proc.stdout)
        self.assertIn("dist: undeclared file", proc.stdout)

    def test_source_map_in_dist_fails(self):
        self.record_dist()
        self.write("apps/web/dist/assets/app-ABC123.js.map", b"{\"sources\":[]}")
        proc = self.run_checker("--dist-manifest", ".private/distribution/dist-manifest.json")
        self.assertEqual(proc.returncode, 1, msg=proc.stdout)
        self.assertIn("prohibited development material present", proc.stdout)

    def test_missing_dist_manifest_fails(self):
        self.record_dist()
        proc = self.run_checker("--dist-manifest", ".private/distribution/absent.json")
        self.assertEqual(proc.returncode, 1, msg=proc.stdout)
        self.assertIn("dist manifest missing", proc.stdout)


if __name__ == "__main__":
    unittest.main()
