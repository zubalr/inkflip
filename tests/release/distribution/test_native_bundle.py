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
import os
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



class ApplicationWheelImageTests(unittest.TestCase):
    """The application-wheel / complete-image audit interface: absence,
    mismatch and image-without-wheel cases (recovery review item)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.write("NOTICE", b"NOTICE\n")

    def write(self, rel: str, content: bytes):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def base_manifest(self, wheel=None, image=None):
        self.write(".private/distribution/native-bundle/.prepared", b"")  # context prepared
        self.write(
            "release/native-requirements.lock", b"# generated\n"
        )
        self.write(
            "release/native-wheels.manifest.json",
            json.dumps({"wheels": []}).encode(),
        )
        self.write(
            "release/node/node.stamp.json",
            json.dumps({"version": "22.23.2", "sha256": "a" * 64, "url": "u",
                        "shasums256_source": "s"}).encode(),
        )
        self.write(
            "release/models/model.stamp.json",
            json.dumps({"name": "m", "sha256": "b" * 64, "license": "Apache-2.0",
                        "source": "s"}).encode(),
        )
        manifest = {
            "distribution": {"shipped_roots": []},
            "groups": [],
            "notice": "NOTICE",
            "native_bundle": {
                "requirements_lock": "release/native-requirements.lock",
                "wheels_manifest": "release/native-wheels.manifest.json",
                "expected_runtime_packages": [],
                "context_dir": ".private/distribution/native-bundle",
                "node_stamp": "release/node/node.stamp.json",
                "model_stamp": "release/models/model.stamp.json",
                "notices_dir": "release/notices/",
                "application_wheel": wheel,
                "application_image": image,
            },
        }
        self.write("distribution.json", json.dumps(manifest).encode())

    def run_checker(self) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(CHECKER), "--release", "--manifest", "distribution.json",
             "--root", str(self.root)],
            capture_output=True, text=True, timeout=60,
        )

    def test_undeclared_wheel_stays_explicitly_incomplete(self):
        self.base_manifest(
            wheel={"declared": False, "path": None, "sha256": None},
            image={"declared": False, "image_lock": None, "expected_image_digest": None},
        )
        proc = self.run_checker()
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
        self.assertIn("no application wheel is declared", proc.stdout)

    def test_declared_wheel_missing_fails(self):
        self.base_manifest(
            wheel={"declared": True, "path": "native/dist/inkflip-1.0-py3-none-any.whl",
                   "sha256": "c" * 64},
            image={"declared": False, "image_lock": None, "expected_image_digest": None},
        )
        proc = self.run_checker()
        self.assertEqual(proc.returncode, 1, msg=proc.stdout)
        self.assertIn("declared application wheel missing", proc.stdout)

    def test_declared_wheel_digest_mismatch_fails(self):
        self.write("native/dist/inkflip-1.0-py3-none-any.whl", b"actual wheel bytes")
        self.base_manifest(
            wheel={"declared": True, "path": "native/dist/inkflip-1.0-py3-none-any.whl",
                   "sha256": "c" * 64},
            image={"declared": False, "image_lock": None, "expected_image_digest": None},
        )
        proc = self.run_checker()
        self.assertEqual(proc.returncode, 1, msg=proc.stdout)
        self.assertIn("application wheel digest mismatch", proc.stdout)

    def test_declared_wheel_with_matching_digest_passes(self):
        wheel_bytes = b"real wheel bytes"
        digest = hashlib.sha256(wheel_bytes).hexdigest()
        self.write("native/dist/inkflip-1.0-py3-none-any.whl", wheel_bytes)
        self.base_manifest(
            wheel={"declared": True, "path": "native/dist/inkflip-1.0-py3-none-any.whl",
                   "sha256": digest},
            image={"declared": False, "image_lock": None, "expected_image_digest": None},
        )
        proc = self.run_checker()
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)

    def test_image_declared_without_wheel_fails(self):
        self.base_manifest(
            wheel={"declared": False, "path": None, "sha256": None},
            image={"declared": True, "image_lock": None, "expected_image_digest": "sha256:d" * 1},
        )
        proc = self.run_checker()
        self.assertEqual(proc.returncode, 1, msg=proc.stdout)
        self.assertIn("not a complete shipped application image", proc.stdout)

    def test_image_declared_without_digest_fails(self):
        self.base_manifest(
            wheel={"declared": False, "path": None, "sha256": None},
            image={"declared": True, "image_lock": None, "expected_image_digest": None},
        )
        proc = self.run_checker()
        self.assertEqual(proc.returncode, 1, msg=proc.stdout)
        self.assertIn("without expected_image_digest", proc.stdout)


class ApplicationWheelStampTests(unittest.TestCase):
    """Stamp-interface audit (Cursor's app.wheel.json / BUILD-CONTEXT.json):
    read-only verification of the assembled-context identity when present."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.write("NOTICE", b"NOTICE\n")
        self.write("release/native-requirements.lock", b"# generated\n")
        self.write("release/native-wheels.manifest.json", json.dumps({"wheels": []}).encode())
        self.write("release/node/node.stamp.json", json.dumps(
            {"version": "22.23.2", "sha256": "a" * 64, "url": "u", "shasums256_source": "s"}).encode())
        self.write("release/models/model.stamp.json", json.dumps(
            {"name": "m", "sha256": "b" * 64, "license": "Apache-2.0", "source": "s"}).encode())
        self.write(".private/distribution/native-bundle/.prepared", b"")
        wheel = b"PY_LENGTH_ZERO_WHEN_EMPTY"
        self.write("native/dist/wheels/inkflip-0.0.0-py3-none-any.whl", wheel)
        self.write("native/dist/app.wheel.json", json.dumps({
            "assembled_path": "native/dist/wheels/inkflip-0.0.0-py3-none-any.whl",
            "filename": "inkflip-0.0.0-py3-none-any.whl",
            "sha256": hashlib.sha256(wheel).hexdigest(),
            "bytes": len(wheel),
            "wheel_tag": "py3-none-any",
        }).encode())
        self.write("native/dist/BUILD-CONTEXT.json", json.dumps({
            "kind": "inkflip-native-image-context",
            "docker_platform": "linux/amd64",
            "dockerfile": "build/native/Dockerfile",
        }).encode())
        manifest = {
            "distribution": {"shipped_roots": []},
            "groups": [],
            "notice": "NOTICE",
            "native_bundle": {
                "requirements_lock": "release/native-requirements.lock",
                "wheels_manifest": "release/native-wheels.manifest.json",
                "expected_runtime_packages": [],
                "context_dir": ".private/distribution/native-bundle",
                "node_stamp": "release/node/node.stamp.json",
                "model_stamp": "release/models/model.stamp.json",
                "notices_dir": "release/notices/",
                "application_wheel": {"declared": False, "path": None, "sha256": None},
                "application_image": {"declared": False, "image_lock": None,
                                      "expected_image_digest": None},
                "application_wheel_stamp": "native/dist/app.wheel.json",
                "build_context_identity": "native/dist/BUILD-CONTEXT.json",
            },
        }
        self.write("distribution.json", json.dumps(manifest).encode())

    def write(self, rel, content):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def run_checker(self):
        return subprocess.run(
            [sys.executable, str(CHECKER), "--release", "--manifest", "distribution.json",
             "--root", str(self.root)],
            capture_output=True, text=True, timeout=60,
        )

    def test_consistent_stamp_passes(self):
        proc = self.run_checker()
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)

    def test_tampered_wheel_fails_against_stamp(self):
        self.write("native/dist/wheels/inkflip-0.0.0-py3-none-any.whl", b"tampered")
        proc = self.run_checker()
        self.assertEqual(proc.returncode, 1, msg=proc.stdout)
        self.assertIn("application wheel digest mismatch", proc.stdout)

    def test_stamp_missing_field_fails(self):
        stamp = json.loads((self.root / "native/dist/app.wheel.json").read_text())
        del stamp["wheel_tag"]
        self.write("native/dist/app.wheel.json", json.dumps(stamp).encode())
        proc = self.run_checker()
        self.assertEqual(proc.returncode, 1, msg=proc.stdout)
        self.assertIn("lacks 'wheel_tag'", proc.stdout)

    def test_stamped_wheel_missing_fails(self):
        (self.root / "native/dist/wheels/inkflip-0.0.0-py3-none-any.whl").unlink()
        proc = self.run_checker()
        self.assertEqual(proc.returncode, 1, msg=proc.stdout)
        self.assertIn("stamped application wheel missing", proc.stdout)

    def test_absent_stamp_is_scope_note_not_failure(self):
        (self.root / "native/dist/app.wheel.json").unlink()
        proc = self.run_checker()
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
        self.assertIn("application wheel stamp not present yet", proc.stdout)

    def test_build_context_missing_fields_fail(self):
        self.write("native/dist/BUILD-CONTEXT.json", json.dumps({"kind": "x"}).encode())
        proc = self.run_checker()
        self.assertEqual(proc.returncode, 1, msg=proc.stdout)
        self.assertIn("build-context identity lacks", proc.stdout)


class ProductionImageDockerTests(unittest.TestCase):
    """--docker production-image verification against a stub docker binary:
    identity/arch mismatch, missing wheel, tesseract version and notice
    inventory negatives (labels are not proof)."""

    IMAGE_ID = "sha256:" + "1" * 64
    WHEEL_SHA = hashlib.sha256(b"app wheel").hexdigest()
    MODEL_SHA = hashlib.sha256(b"model").hexdigest()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.bin_dir = self.root / "bin"
        self.bin_dir.mkdir(parents=True)
        self.index = {"entries": [
            {"id": "inkflip-mit", "path": "notices/inkflip-MIT.txt",
             "sha256": hashlib.sha256(b"MIT text").hexdigest()},
            {"id": "pdfium-binary-appendix", "path": "notices/pdfium.txt",
             "sha256": hashlib.sha256(b"pdfium appendix").hexdigest()},
            {"id": "node-license", "path": "notices/node/LICENSE",
             "sha256": hashlib.sha256(b"node license").hexdigest()},
            {"id": "tesseract-apache", "path": "notices/tesseract.txt",
             "sha256": hashlib.sha256(b"tesseract apache").hexdigest()},
        ]}
        self.state = {
            "inspect": {"id": self.IMAGE_ID, "architecture": "amd64", "os": "linux"},
            "run_sha": {
                "inkflip-0.0.0-py3-none-any.whl": self.WHEEL_SHA,
                "eng.traineddata": self.MODEL_SHA,
                "inkflip-MIT.txt": self.index["entries"][0]["sha256"],
                "pdfium.txt": self.index["entries"][1]["sha256"],
                "LICENSE": self.index["entries"][2]["sha256"],
                "tesseract.txt": self.index["entries"][3]["sha256"],
            },
            "run_index": self.index,
            "run_tesseract": "tesseract 5.5.0",
        }

    def write(self, rel, content):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content if isinstance(content, bytes) else content.encode())
        return path

    def write_stub(self):
        """Write a stub `docker` script driven entirely by DOCKER_STUB_STATE
        (JSON): {'inspect': {...}, 'run_sha': {basename: sha}, 'run_index': {...},
        'run_tesseract': 'version line'} — word-matching on sha256sum args."""
        stub_src = (
            "#!/usr/bin/env python3\n"
            "import json, os, sys\n"
            "state = json.loads(os.environ['DOCKER_STUB_STATE'])\n"
            "args = sys.argv[1:]\n"
            "joined = ' '.join(args)\n"
            "if args and args[0] == 'inspect':\n"
            "    i = state['inspect']\n"
            "    print(i['id']); print(i['architecture']); print(i['os']); sys.exit(0)\n"
            "if 'INDEX.json' in joined:\n"
            "    sys.stdout.write(json.dumps(state['run_index'])); sys.exit(0)\n"
            "if 'sha256sum' in joined:\n"
            "    import re\n"
            "    seen = set()\n"
            "    for word in joined.split():\n"
            "        base = os.path.basename(word)\n"
            "        if '*' in word:\n"
            "            pattern = re.escape(base).replace(re.escape('*'), '.*')\n"
            "            for name, sha in state['run_sha'].items():\n"
            "                if re.fullmatch(pattern, name) and name not in seen:\n"
            "                    seen.add(name); print(sha, name)\n"
            "        elif base in state['run_sha'] and base not in seen:\n"
            "            seen.add(base); print(state['run_sha'][base], base)\n"
            "    if '--version' in joined:\n"
            "        print(state['run_tesseract'])\n"
            "    sys.exit(0)\n"
            "if '--version' in joined:\n"
            "    print(state['run_tesseract']); sys.exit(0)\n"
            "sys.exit(0)\n"
        )
        stub = self.bin_dir / "docker"
        stub.write_text(stub_src)
        stub.chmod(0o755)
        return str(stub)

    def base_manifest(self):
        self.write("NOTICE", b"NOTICE\n")
        self.write("release/native-requirements.lock", b"# generated\n")
        self.write("release/native-wheels.manifest.json", json.dumps({"wheels": []}))
        self.write("release/node/node.stamp.json", json.dumps(
            {"version": "22.23.2", "sha256": "a" * 64, "url": "u", "shasums256_source": "s"}))
        self.write("release/models/model.stamp.json", json.dumps(
            {"name": "m", "sha256": "b" * 64, "license": "Apache-2.0", "source": "s"}))
        self.write(".private/distribution/native-bundle/.prepared", b"")
        self.write("release/tesseract/tesseract.stamp.json", json.dumps({
            "kind": "inkflip-native-tesseract-debs", "package": "tesseract-ocr",
            "version": "5.5.0-1+b1", "arch": "amd64",
            "license": "Apache-2.0 (Tesseract)",
            "packages": [{"filename": "a.deb", "sha256": "c" * 64, "bytes": 10}]}))
        manifest = {
            "distribution": {"shipped_roots": []},
            "groups": [],
            "notice": "NOTICE",
            "native_bundle": {
                "requirements_lock": "release/native-requirements.lock",
                "wheels_manifest": "release/native-wheels.manifest.json",
                "expected_runtime_packages": [],
                "context_dir": ".private/distribution/native-bundle",
                "node_stamp": "release/node/node.stamp.json",
                "model_stamp": "release/models/model.stamp.json",
                "notices_dir": "release/notices/",
                "tesseract_stamp": {
                    "path": "release/tesseract/tesseract.stamp.json",
                    "expected_package": "tesseract-ocr",
                    "expected_version": "5.5.0-1+b1",
                    "expected_arch": "amd64",
                    "debs_dir": None,
                },
                "application_wheel": {"declared": False, "path": None, "sha256": None},
                "production_image": {
                    "declared": True,
                    "image_ref": "inkflip-native:pc-prod",
                    "expected_image_digest": self.IMAGE_ID,
                    "architecture": "amd64",
                    "os": "linux",
                    "expected_wheel_sha256": self.WHEEL_SHA,
                    "expected_model_sha256": self.MODEL_SHA,
                    "expected_tesseract_version": "5.5.0",
                    "required_notice_ids": ["inkflip-mit", "pdfium-binary-appendix",
                                            "node-license", "tesseract-apache"],
                },
            },
        }
        self.write("distribution.json", json.dumps(manifest))

    def run_with_stub(self):
        self.write_stub()
        return subprocess.run(
            [sys.executable, str(CHECKER), "--release", "--manifest", "distribution.json",
             "--root", str(self.root), "--docker", "inkflip-native:pc-prod"],
            capture_output=True, text=True, timeout=120,
            env={**os.environ,
                 "PATH": f"{self.bin_dir}:{os.environ['PATH']}",
                 "DOCKER_STUB_STATE": json.dumps(self.state)},
        )

    def expect(self, proc, code, needle):
        self.assertEqual(proc.returncode, code, msg=proc.stdout + proc.stderr)
        self.assertIn(needle, proc.stdout)

    # ---- cases ----

    def test_consistent_image_passes(self):
        self.base_manifest()
        self.expect(self.run_with_stub(), 0, "production image verified via docker")

    def test_wrong_identity_fails(self):
        self.base_manifest()
        self.state["inspect"]["id"] = "sha256:" + "2" * 64
        self.expect(self.run_with_stub(), 1, "identity mismatch")

    def test_wrong_architecture_fails(self):
        self.base_manifest()
        self.state["inspect"]["architecture"] = "arm64"
        self.expect(self.run_with_stub(), 1, "architecture is 'arm64'")

    def test_missing_wheel_fails(self):
        self.base_manifest()
        self.state["run_sha"]["inkflip-0.0.0-py3-none-any.whl"] = "0" * 64
        self.expect(self.run_with_stub(), 1, "application wheel digest mismatch")

    def test_tesseract_version_mismatch_fails(self):
        self.base_manifest()
        self.state["run_tesseract"] = "tesseract 5.3.0"
        self.expect(self.run_with_stub(), 1, "tesseract version line missing/mismatched")

    def test_missing_notice_id_fails(self):
        self.base_manifest()
        self.state["run_index"] = {"entries": self.index["entries"][:3]}
        self.expect(self.run_with_stub(), 1, "tesseract-apache")

    def test_notice_bytes_mismatch_fails(self):
        self.base_manifest()
        self.state["run_sha"]["tesseract.txt"] = "0" * 64
        self.expect(self.run_with_stub(), 1, "notice 'tesseract-apache' bytes do not match")

    def test_tesseract_stamp_version_mismatch_is_config_error(self):
        self.base_manifest()
        stamp = json.loads((self.root / "release/tesseract/tesseract.stamp.json").read_text())
        stamp["version"] = "5.3.0"
        self.write("release/tesseract/tesseract.stamp.json", json.dumps(stamp))
        proc = self.run_with_stub()
        self.assertEqual(proc.returncode, 1, msg=proc.stdout)
        self.assertIn("tesseract stamp version is '5.3.0', expected '5.5.0-1+b1'", proc.stdout)


if __name__ == "__main__":
    unittest.main()
