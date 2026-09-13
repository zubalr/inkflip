"""Preflight for production native image inputs."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check_native_image_inputs.py"


def run_checker(root: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root), *extra],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def write(root: Path, rel: str, content: bytes) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_wheel(path: Path, *, name: str, version: str, plat: str, extra: dict[str, bytes] | None = None) -> bytes:
    dist = name.replace("-", "_")
    tag = f"py3-none-{plat}" if plat == "any" else f"cp313-cp313-{plat}"
    filename = f"{dist}-{version}-{tag}.whl"
    dest = path / filename
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest, "w") as zf:
        if name == "inkflip":
            zf.writestr(
                f"{dist}-{version}.dist-info/entry_points.txt",
                "[console_scripts]\ninkflip = inkflip.cli.main:main\n",
            )
            zf.writestr("inkflip/cli/main.py", "def main():\n    return 0\n")
            zf.writestr("inkflip/contracts/schema/inkflip.schema.json", "{}\n")
            zf.writestr(
                "inkflip/resources/packages/compare/node/bridge.mjs",
                "console.log('bridge')\n",
            )
        else:
            zf.writestr(f"{dist}-{version}.dist-info/METADATA", f"Name: {name}\nVersion: {version}\n")
        if extra:
            for rel, data in extra.items():
                zf.writestr(rel, data)
    return dest.read_bytes()


class TestNativeImageInputs(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_arbitrary_whl_filename_is_not_enough(self) -> None:
        write(self.root, "native/dist/not-a-real.whl", b"PK\x03\x04fake")
        write(self.root, "native/dist/requirements.lock", b"inkflip mentioned\n")
        write(self.root, "release/node/node.stamp.json", b"{}")
        write(self.root, "release/models/model.stamp.json", b"{}")
        write(self.root, "release/native-wheels.manifest.json", b'{"wheels":[]}')
        proc = run_checker(self.root)
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        combined = proc.stdout + proc.stderr
        self.assertIn("not a PEP 427 tag", combined)
        self.assertIn("does not pin inkflip", combined)

    def test_lock_substring_and_empty_asset_dirs_fail(self) -> None:
        (self.root / "native/dist").mkdir(parents=True)
        (self.root / "release/node").mkdir(parents=True)
        (self.root / "release/models").mkdir(parents=True)
        (self.root / "release/notices").mkdir(parents=True)
        write(self.root, "native/dist/requirements.lock", b"# inkflip== is a comment\n")
        write(self.root, "release/native-wheels.manifest.json", b'{"wheels":[{"name":"pypdf"}]}')
        proc = run_checker(self.root)
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        combined = proc.stdout + proc.stderr
        self.assertIn("no .whl files", combined)
        self.assertIn("empty placeholder", combined.lower() + combined)

    def test_complete_context_passes(self) -> None:
        dist = self.root / "native/dist"
        wheels_dir = dist / "wheels"
        ink_bytes = make_wheel(wheels_dir, name="inkflip", version="0.0.0", plat="any")
        pillow_bytes = make_wheel(
            wheels_dir,
            name="pillow",
            version="12.3.0",
            plat="manylinux_2_28_x86_64",
        )
        ink_sha = sha256(ink_bytes)
        pillow_sha = sha256(pillow_bytes)
        tarball = b"node-runtime-bytes"
        model = b"traineddata-bytes"
        write(
            self.root,
            "native/dist/requirements.lock",
            (
                f"pillow==12.3.0 --hash=sha256:{pillow_sha}\n"
                f"inkflip==0.0.0 --hash=sha256:{ink_sha}\n"
            ).encode(),
        )
        write(self.root, "native/dist/node/node-v22.23.2-linux-x64.tar.xz", tarball)
        write(self.root, "native/dist/models/tessdata/eng.traineddata", model)
        write(self.root, "release/notices/pillow/LICENSE", b"MIT\n")
        write(
            self.root,
            "release/native-wheels.manifest.json",
            json.dumps({"wheels": [{"name": "pillow", "sha256": pillow_sha, "filename": "pillow-12.3.0-cp313-cp313-manylinux_2_28_x86_64.whl"}]}).encode(),
        )
        write(
            self.root,
            "release/node/node.stamp.json",
            json.dumps(
                {
                    "version": "22.23.2",
                    "sha256": sha256(tarball),
                    "filename": "node-v22.23.2-linux-x64.tar.xz",
                    "url": "https://nodejs.org/dist/v22.23.2/node-v22.23.2-linux-x64.tar.xz",
                }
            ).encode(),
        )
        write(
            self.root,
            "release/models/model.stamp.json",
            json.dumps({"name": "tessdata", "sha256": sha256(model)}).encode(),
        )
        proc = run_checker(self.root)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("complete", proc.stdout)

    def test_tampered_and_wrong_arch_and_wrong_stamps_fail(self) -> None:
        dist = self.root / "native/dist/wheels"
        ink_bytes = make_wheel(dist, name="inkflip", version="0.0.0", plat="any")
        make_wheel(dist, name="pillow", version="12.3.0", plat="manylinux_2_28_aarch64")
        write(
            self.root,
            "native/dist/requirements.lock",
            (
                f"pillow==12.3.0 --hash=sha256:{'a' * 64}\n"
                f"inkflip==0.0.0 --hash=sha256:{'b' * 64}\n"
            ).encode(),
        )
        write(self.root, "native/dist/node/node-v22.23.2-linux-x64.tar.xz", b"wrong-node")
        write(self.root, "native/dist/models/tessdata/eng.traineddata", b"wrong-model")
        write(self.root, "release/notices/x/LICENSE", b"x\n")
        write(
            self.root,
            "release/native-wheels.manifest.json",
            json.dumps({"wheels": [{"name": "pillow"}, {"name": "pypdf"}]}).encode(),
        )
        write(
            self.root,
            "release/node/node.stamp.json",
            json.dumps(
                {
                    "version": "18.0.0",
                    "sha256": "c" * 64,
                    "filename": "node-v22.23.2-linux-x64.tar.xz",
                    "url": "https://example.invalid",
                }
            ).encode(),
        )
        write(
            self.root,
            "release/models/model.stamp.json",
            json.dumps({"name": "tessdata", "sha256": "d" * 64}).encode(),
        )
        proc = run_checker(self.root)
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        combined = proc.stdout + proc.stderr
        self.assertIn("wrong architecture", combined)
        self.assertIn("hash mismatch", combined)
        self.assertIn("incomplete transitive closure", combined)
        self.assertIn("incorrect Node stamp version", combined)
        self.assertIn("incorrect model hash", combined)

    def test_inventory_lists_gaps_without_certifying(self) -> None:
        (self.root / "native/dist").mkdir(parents=True)
        proc = run_checker(self.root, "--inventory")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertTrue(proc.stdout.strip())
        self.assertNotIn("native image inputs: complete", proc.stdout)

    def test_real_tree_fail_closed_or_honest_complete(self) -> None:
        proc = run_checker(ROOT)
        combined = proc.stdout + proc.stderr
        if proc.returncode == 0:
            self.assertIn("complete", proc.stdout)
            dist = ROOT / "native" / "dist"
            wheels = list((dist / "wheels").glob("inkflip-*.whl")) or list(dist.glob("inkflip-*.whl"))
            self.assertTrue(wheels, "complete status requires a real inkflip wheel")
            self.assertTrue(zipfile.is_zipfile(wheels[0]))
        else:
            self.assertEqual(proc.returncode, 2, combined)
            self.assertIn("incomplete", combined)


if __name__ == "__main__":
    unittest.main()
