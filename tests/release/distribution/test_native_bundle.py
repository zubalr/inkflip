"""T47 preparation: native-bundle and dist-surface checker tests.

Builds disposable native-bundle fixtures (wheels manifest + stamps + fake
prepared artifacts) and dist fixtures in temporary directories and proves:

  - a valid prepared bundle passes;
  - wrong-platform wheel filenames, duplicate entries, absent required
    components, unexpected packages, missing license evidence, missing or
    incomplete node/model stamps, and missing prepared artifacts FAIL;
  - a recorded dist manifest passes and tampered/undeclared dist files FAIL;
  - the producer and the consumer resolve one canonical prepared context, and
    an alternate cache directory can never shadow it.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CHECKER = REPO_ROOT / "scripts" / "check_distribution.py"
ASSEMBLE = REPO_ROOT / "scripts" / "distribution" / "assemble_native_image.py"
PREPARE = REPO_ROOT / "scripts" / "distribution" / "prepare_native_bundle.py"

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
    """--docker production-image verification (final-integrity contract).

    Requested Docker verification must never pass by skipping: a missing,
    malformed, wrong-kind or incomplete candidate is a nonzero, actionable
    failure. The candidate's ref is the inspected target; --docker IMAGE
    must match it or the run fails with a stable diagnostic. Expected
    identity comes only from the declared candidate file.
    """

    IMAGE_ID = "sha256:" + "1" * 64
    WHEEL_SHA = hashlib.sha256(b"app wheel").hexdigest()
    MODEL_SHA = hashlib.sha256(b"model").hexdigest()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.bin_dir = self.root / "bin"
        self.bin_dir.mkdir(parents=True)
        notices = [
            ("inkflip-mit", "notices/inkflip-MIT.txt", b"MIT text"),
            ("pdfium-binary-appendix", "notices/pdfium.txt", b"pdfium appendix"),
            ("node-license", "notices/node/LICENSE", b"node license"),
            ("tesseract-apache", "notices/tesseract.txt", b"tesseract apache"),
        ]
        # declared digest and byte count are modelled from the same content the
        # stub reports, so the healthy fixture is self-consistent
        self.index = {"entries": [
            {"id": notice_id, "path": path, "sha256": hashlib.sha256(content).hexdigest(),
             "bytes": len(content)}
            for notice_id, path, content in notices
        ]}
        self.state = {
            "inspect": {"id": self.IMAGE_ID, "architecture": "amd64", "os": "linux"},
            "run_sha": {
                "inkflip-0.0.0-py3-none-any.whl": self.WHEEL_SHA,
                "eng.traineddata": self.MODEL_SHA,
                **{Path(path).name: hashlib.sha256(content).hexdigest()
                   for _, path, content in notices},
            },
            "run_size": {Path(path).name: len(content)
                         for _, path, content in notices},
            "run_index": self.index,
            "run_tesseract": "tesseract 5.5.0",
        }

    def write(self, rel, content):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content if isinstance(content, bytes) else content.encode())
        return path

    def write_stub(self):
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
            "if '--entrypoint stat' in joined:\n"
            "    base = os.path.basename(args[-1])\n"
            "    if base in state['run_size']:\n"
            "        print(state['run_size'][base]); sys.exit(0)\n"
            "    sys.exit(1)\n"
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
            "    if '--version' in joined and 'tesseract' in joined:\n"
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
            {"version": "22.23.2", "sha256": "a" * 64, "url": "u",
             "shasums256_source": "s"}))
        self.write("release/models/model.stamp.json", json.dumps(
            {"name": "m", "sha256": "b" * 64, "license": "Apache-2.0",
             "source": "s"}))
        self.write(".private/distribution/native-bundle/.prepared", b"")
        self.write("release/tesseract/tesseract.stamp.json", json.dumps({
            "kind": "inkflip-native-tesseract-debs",
            "package": "tesseract-ocr",
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
                "application_wheel": {"declared": False, "path": None,
                                      "sha256": None},
                "production_image": {
                    "declared": True,
                    "candidate_file": "config/release-candidate.json",
                    "architecture": "amd64",
                    "os": "linux",
                    "required_notice_ids": ["inkflip-mit",
                                            "pdfium-binary-appendix",
                                            "node-license",
                                            "tesseract-apache"],
                },
            },
        }
        self.write("distribution.json", json.dumps(manifest))

    def bound_candidate(self, ref="inkflip-native:pc-prod", digest=None,
                        wheel=None, model=None, tesseract="5.5.0", **overrides):
        wheel_value = self.WHEEL_SHA if wheel is None else wheel
        model_value = self.MODEL_SHA if model is None else model
        cand = {
            "kind": "inkflip-release-candidate",
            "schema_version": "1.0.0",
            "recorded_by": "devin-integrator",
            "recorded_at": "2026-09-14T00:00:00Z",
            "production_image": {
                "ref": ref,
                "digest": digest or self.IMAGE_ID,
                "architecture": "amd64",
                "wheel_sha256": wheel_value,
                "model_sha256": model_value,
                "tesseract_version": tesseract,
            },
        }
        if wheel is ...:
            del cand["production_image"]["wheel_sha256"]
        cand["production_image"].update(overrides)
        self.write("config/release-candidate.json", json.dumps(cand))

    def run_with_stub(self):
        self.write_stub()
        return subprocess.run(
            [sys.executable, str(CHECKER), "--release", "--manifest",
             "distribution.json", "--root", str(self.root),
             "--candidate", "config/release-candidate.json",
             "--docker", "inkflip-native:pc-prod"],
            capture_output=True, text=True, timeout=120,
            env={**os.environ,
                 "PATH": f"{self.bin_dir}:{os.environ['PATH']}",
                 "DOCKER_STUB_STATE": json.dumps(self.state)},
        )

    def expect(self, proc, code, needle):
        self.assertEqual(proc.returncode, code, msg=proc.stdout + proc.stderr)
        self.assertIn(needle, proc.stdout)

    # ---- R1: skipped verification must fail ----

    def test_unbound_candidate_fails_requested_docker_check(self):
        self.base_manifest()
        proc = self.run_with_stub()
        self.assertEqual(proc.returncode, 1, msg=proc.stdout + proc.stderr)
        self.assertIn("required release candidate not found", proc.stdout)
        self.assertNotIn("verified via docker", proc.stdout)

    def test_partial_candidate_fails_requested_docker_check(self):
        self.base_manifest()
        self.bound_candidate(digest="pending")
        proc = self.run_with_stub()
        self.assertEqual(proc.returncode, 2, msg=proc.stdout)
        self.assertIn("digest must be", proc.stdout)
        self.assertNotIn("verified via docker", proc.stdout)

    def test_malformed_candidate_is_config_error(self):
        self.base_manifest()
        self.write("config/release-candidate.json", b"{ not json ")
        proc = self.run_with_stub()
        self.assertEqual(proc.returncode, 2, msg=proc.stdout)
        self.assertIn("malformed JSON", proc.stdout)

    def test_wrong_kind_candidate_is_config_error(self):
        self.base_manifest()
        self.bound_candidate()
        cand = json.loads((self.root / "config/release-candidate.json").read_text())
        cand["kind"] = "something-else"
        self.write("config/release-candidate.json", json.dumps(cand))
        proc = self.run_with_stub()
        self.assertEqual(proc.returncode, 2, msg=proc.stdout)
        self.assertIn("wrong kind", proc.stdout)

    def test_unknown_key_candidate_is_config_error(self):
        self.base_manifest()
        self.bound_candidate()
        cand = json.loads((self.root / "config/release-candidate.json").read_text())
        cand["unexpected"] = True
        self.write("config/release-candidate.json", json.dumps(cand))
        proc = self.run_with_stub()
        self.assertEqual(proc.returncode, 2, msg=proc.stdout)
        self.assertIn("unknown top-level key", proc.stdout)

    def test_duplicate_key_candidate_is_config_error(self):
        self.base_manifest()
        self.bound_candidate()
        raw = (self.root / "config/release-candidate.json").read_text()
        raw = raw.replace('"production_image"', '"recorded_by"\n  "dupe", "x": 1, "production_image"', 1)
        self.write("config/release-candidate.json", raw.encode())
        proc = self.run_with_stub()
        self.assertEqual(proc.returncode, 2, msg=proc.stdout + proc.stderr)
        self.assertTrue("duplicate key" in proc.stdout or "malformed" in proc.stdout)

    def test_missing_recorded_by_is_config_error(self):
        self.base_manifest()
        self.bound_candidate()
        cand = json.loads((self.root / "config/release-candidate.json").read_text())
        del cand["recorded_by"]
        self.write("config/release-candidate.json", json.dumps(cand))
        proc = self.run_with_stub()
        self.assertEqual(proc.returncode, 2, msg=proc.stdout)
        self.assertIn("recorded_by", proc.stdout)

    def test_missing_wheel_identity_is_config_error(self):
        self.base_manifest()
        self.write("release/tesseract/tesseract.stamp.json",
                   (self.root / "release/tesseract/tesseract.stamp.json").read_bytes())
        cand = {
            "kind": "inkflip-release-candidate", "schema_version": "1.0.0",
            "recorded_by": "devin", "recorded_at": "2026-09-14T00:00:00Z",
            "production_image": {"ref": "inkflip-native:pc-prod",
                                 "digest": self.IMAGE_ID,
                                 "architecture": "amd64",
                                 "model_sha256": self.MODEL_SHA,
                                 "tesseract_version": "5.5.0"},
        }
        self.write("config/release-candidate.json", json.dumps(cand))
        self.write("config/release-candidate.json", json.dumps(cand))
        proc = self.run_with_stub()
        self.assertEqual(proc.returncode, 2, msg=proc.stdout)
        self.assertIn("wheel_sha256", proc.stdout)

    def test_missing_tesseract_version_is_config_error(self):
        self.base_manifest()
        self.bound_candidate()
        cand = json.loads((self.root / "config/release-candidate.json").read_text())
        cand["production_image"]["tesseract_version"] = ""
        self.write("config/release-candidate.json", json.dumps(cand))
        proc = self.run_with_stub()
        self.assertEqual(proc.returncode, 2, msg=proc.stdout)
        self.assertIn("tesseract_version", proc.stdout)

    # ---- R2: exact target ----

    def test_requested_target_mismatch_fails(self):
        self.base_manifest()
        self.bound_candidate(ref="inkflip-native:merged",
                             digest="sha256:" + "d" * 64)
        self.state["inspect"]["id"] = "sha256:" + "d" * 64
        self.state["run_sha"]["inkflip-0.0.0-py3-none-any.whl"] = self.WHEEL_SHA
        proc = self.run_with_stub()  # --docker pc-prod vs candidate merged
        self.assertEqual(proc.returncode, 1, msg=proc.stdout)
        self.assertIn("does not match declared candidate ref", proc.stdout)

    def test_matching_target_verifies(self):
        self.base_manifest()
        self.bound_candidate(ref="inkflip-native:pc-prod")
        proc = self.run_with_stub()
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
        self.assertIn("production image verified via docker", proc.stdout)
        self.assertIn("inkflip-native:pc-prod", proc.stdout)

    # ---- R3: identity negatives against bound candidate ----

    def test_wrong_identity_fails(self):
        self.base_manifest()
        self.bound_candidate()
        self.state["inspect"]["id"] = "sha256:" + "2" * 64
        proc = self.run_with_stub()
        self.assertEqual(proc.returncode, 1, msg=proc.stdout)
        self.assertIn("identity mismatch", proc.stdout)

    def test_wrong_architecture_fails(self):
        self.base_manifest()
        self.bound_candidate()
        self.state["inspect"]["architecture"] = "arm64"
        proc = self.run_with_stub()
        self.assertEqual(proc.returncode, 1, msg=proc.stdout)
        self.assertIn("architecture is 'arm64'", proc.stdout)

    def test_missing_wheel_hash_fails(self):
        self.base_manifest()
        self.bound_candidate()
        del self.state["run_sha"]["inkflip-0.0.0-py3-none-any.whl"]
        proc = self.run_with_stub()
        self.assertEqual(proc.returncode, 1, msg=proc.stdout)
        self.assertIn("application wheel digest mismatch", proc.stdout)

    def test_tesseract_version_mismatch_fails(self):
        self.base_manifest()
        self.bound_candidate()
        self.state["run_tesseract"] = "tesseract 5.3.0"
        proc = self.run_with_stub()
        self.assertEqual(proc.returncode, 1, msg=proc.stdout)
        self.assertIn("tesseract version line missing/mismatched", proc.stdout)

    def test_missing_notice_id_fails(self):
        self.base_manifest()
        self.bound_candidate()
        self.state["run_index"] = {"entries": self.index["entries"][:3]}
        proc = self.run_with_stub()
        self.assertEqual(proc.returncode, 1, msg=proc.stdout)
        self.assertIn("tesseract-apache", proc.stdout)

    def test_notice_bytes_mismatch_fails(self):
        self.base_manifest()
        self.bound_candidate()
        self.state["run_sha"]["tesseract.txt"] = "0" * 64
        proc = self.run_with_stub()
        self.assertEqual(proc.returncode, 1, msg=proc.stdout)
        self.assertIn("bytes do not match INDEX", proc.stdout)

    def test_notice_length_mismatch_fails(self):
        # the digest still matches: the declared byte count is wrong
        self.base_manifest()
        self.bound_candidate()
        self.state["run_size"]["tesseract.txt"] += 1
        proc = self.run_with_stub()
        self.assertEqual(proc.returncode, 1, msg=proc.stdout)
        self.assertIn("byte length mismatch", proc.stdout)
        self.assertIn("tesseract-apache", proc.stdout)

    def test_tesseract_stamp_version_drift_is_failure(self):
        self.base_manifest()
        self.bound_candidate()
        stamp = json.loads(
            (self.root / "release/tesseract/tesseract.stamp.json").read_text())
        stamp["version"] = "5.3.0"
        self.write("release/tesseract/tesseract.stamp.json", json.dumps(stamp))
        proc = self.run_with_stub()
        self.assertEqual(proc.returncode, 1, msg=proc.stdout)
        self.assertIn("tesseract stamp version", proc.stdout)


class NativeBundlePathTests(unittest.TestCase):
    """The prepared third-party context has exactly one canonical location.

    prepare_native_bundle.py writes .private/distribution/native-bundle (also
    declared by config/distribution-manifest.json) and assemble_native_image.py
    must consume that same directory: an empty or stale alternate cache at
    .private/cache/native-bundle can never shadow freshly prepared output, and
    an explicit --bundle path stays authoritative."""

    CANONICAL = Path(".private") / "distribution" / "native-bundle"
    STALE = Path(".private") / "cache" / "native-bundle"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        spec = importlib.util.spec_from_file_location("assemble_native_image", ASSEMBLE)
        self.assemble = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.assemble)

    def write(self, rel, content):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def load_producer(self):
        spec = importlib.util.spec_from_file_location("prepare_native_bundle", PREPARE)
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except ModuleNotFoundError as exc:  # tomllib needs Python 3.11+
            self.skipTest(f"prepare_native_bundle cannot import here: {exc}")
        return module

    def run_main(self, *argv):
        """Run the real main() against the disposable fixture root, with the
        module path globals redirected (as the producer tests do). The fixture
        models the bundle check, so only the release manifests need to exist;
        an exception is reported as a failure of the run, not of the test."""
        module = self.assemble
        saved = module.ROOT, module.PRIVATE, module.RELEASE, module.DIST
        module.ROOT = self.root
        module.PRIVATE = self.root / self.CANONICAL
        module.RELEASE = self.root / "release"
        module.DIST = self.root / "dist"
        self.write("release/native-requirements.lock", b"# generated\n")
        self.write("release/native-wheels.manifest.json",
                   json.dumps({"wheels": []}).encode())
        captured = io.StringIO()
        saved_argv = sys.argv
        sys.argv = ["assemble_native_image.py", *argv]
        try:
            with contextlib.redirect_stderr(captured):
                code = module.main()
        except Exception as exc:
            code = f"raised {type(exc).__name__}: {exc}"
        finally:
            sys.argv = saved_argv
            module.ROOT, module.PRIVATE, module.RELEASE, module.DIST = saved
        return code, captured.getvalue()

    def test_canonical_default_is_the_shared_prepared_context(self):
        manifest = json.loads(
            (REPO_ROOT / "config" / "distribution-manifest.json").read_text())
        self.assertEqual(manifest["native_bundle"]["context_dir"], str(self.CANONICAL))
        self.assertEqual(self.assemble.PRIVATE, REPO_ROOT / self.CANONICAL)
        self.assertEqual(self.assemble.resolve_bundle(None), REPO_ROOT / self.CANONICAL)

    def test_producer_and_consumer_agree_on_the_context(self):
        producer = self.load_producer()
        self.assertEqual(producer.PRIVATE, self.assemble.PRIVATE)

    def test_empty_alternate_cache_cannot_mask_prepared_output(self):
        (self.root / self.CANONICAL).mkdir(parents=True)  # freshly prepared
        (self.root / self.STALE).mkdir(parents=True)      # empty leftover cache
        self.assertEqual(self.assemble.resolve_bundle(None, self.root),
                         self.root / self.CANONICAL)

    def test_stale_alternate_cache_cannot_shadow_prepared_output(self):
        (self.root / self.CANONICAL).mkdir(parents=True)
        self.write(self.STALE / "wheels" / "pillow-12.3.0-cp313-cp313-manylinux_2_28_x86_64.whl",
                   b"stale wheel bytes")
        self.assertEqual(self.assemble.resolve_bundle(None, self.root),
                         self.root / self.CANONICAL)

    def test_absent_bundle_names_the_canonical_path_not_the_stale_cache(self):
        self.write(self.STALE / "wheels" / "stale.whl", b"stale wheel bytes")
        code, err = self.run_main()
        self.assertEqual(code, 2, msg=err)
        self.assertIn(str(self.root / self.CANONICAL), err)
        self.assertNotIn(str(self.root / self.STALE), err)

    def test_explicit_bundle_is_authoritative(self):
        explicit = self.root / "explicit-bundle"
        (self.root / self.CANONICAL).mkdir(parents=True)
        self.write(self.STALE / "wheels" / "stale.whl", b"stale wheel bytes")
        code, err = self.run_main("--bundle", str(explicit))
        self.assertEqual(code, 2, msg=err)
        self.assertIn(str(explicit), err)
        self.assertNotIn(str(self.root / self.CANONICAL), err)

    def test_explicit_bundle_is_used_verbatim(self):
        explicit = self.root / "elsewhere" / "explicit-bundle"
        explicit.mkdir(parents=True)
        (self.root / self.CANONICAL).mkdir(parents=True)
        self.assertEqual(self.assemble.resolve_bundle(explicit, self.root), explicit)

    def test_help_documents_the_canonical_default(self):
        proc = subprocess.run([sys.executable, str(ASSEMBLE), "--help"],
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        self.assertIn(str(self.CANONICAL), proc.stdout)


if __name__ == "__main__":
    unittest.main()
