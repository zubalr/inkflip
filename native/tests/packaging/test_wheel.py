"""Inkflip wheel and console_scripts entry point (packaging lane)."""
from __future__ import annotations

import subprocess
import tempfile
import tomllib
import unittest
import zipfile
from pathlib import Path

NATIVE = Path(__file__).resolve().parents[2]
ROOT = NATIVE.parent
PYPROJECT = NATIVE / "pyproject.toml"


class TestNativeWheel(unittest.TestCase):
    def test_pyproject_declares_entry_point_and_build_backend(self) -> None:
        data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
        self.assertEqual(data["project"]["scripts"]["inkflip"], "inkflip.cli.main:main")
        self.assertEqual(data["build-system"]["build-backend"], "hatchling.build")
        self.assertEqual(data["project"]["requires-python"], "==3.13.15")
        requires = data["build-system"]["requires"]
        self.assertTrue(any(r.startswith("hatchling==") for r in requires), requires)
        self.assertNotIn("package", data.get("tool", {}).get("uv", {}))
        runtime = data["project"]["dependencies"]
        self.assertEqual(
            runtime,
            [
                "pypdfium2==5.8.0",
                "pypdf==6.18.0",
                "Pillow==12.3.0",
                "jsonschema==4.26.0",
            ],
        )

    def test_uv_build_emits_wheel_with_inkflip_console_script(self) -> None:
        with tempfile.TemporaryDirectory(prefix="inkflip-wheel-") as raw:
            out = Path(raw)
            proc = subprocess.run(
                ["uv", "build", "--project", str(NATIVE), "--wheel", "--out-dir", str(out)],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            wheels = list(out.glob("inkflip-0.0.0-*.whl"))
            self.assertEqual(len(wheels), 1, list(out.iterdir()))
            with zipfile.ZipFile(wheels[0]) as zf:
                names = zf.namelist()
                self.assertTrue(any(n.startswith("inkflip/cli/main.py") for n in names), names[:20])
                entry = [n for n in names if n.endswith("entry_points.txt")]
                self.assertTrue(entry, names)
                text = zf.read(entry[0]).decode("utf-8")
                self.assertIn("inkflip = inkflip.cli.main:main", text)
                self.assertFalse(any(n.endswith(".so") for n in names))

    def test_production_dockerfile_expects_hashed_wheels_and_inkflip(self) -> None:
        text = (ROOT / "build" / "native" / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("COPY native/dist/ /wheels/", text)
        self.assertIn("--require-hashes", text)
        self.assertIn('ENTRYPOINT ["inkflip"]', text)
        self.assertIn("USER 65532:65532", text)
        self.assertIn("python:3.13.15-slim-trixie@sha256:", text)


if __name__ == "__main__":
    unittest.main()
