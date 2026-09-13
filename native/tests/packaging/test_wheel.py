"""Inkflip wheel and console_scripts entry point (packaging lane)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import tomllib
import unittest
import zipfile
from pathlib import Path

NATIVE = Path(__file__).resolve().parents[2]
ROOT = NATIVE.parent
PYPROJECT = NATIVE / "pyproject.toml"
FIXTURE = ROOT / "fixtures" / "public" / "mapping-control.pdf"


def _build_wheel(out: Path) -> Path:
    proc = subprocess.run(
        ["uv", "build", "--project", str(NATIVE), "--wheel", "--out-dir", str(out)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise AssertionError(proc.stdout + proc.stderr)
    wheels = list(out.glob("inkflip-0.0.0-*.whl"))
    if len(wheels) != 1:
        raise AssertionError(list(out.iterdir()))
    return wheels[0]


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

    def test_uv_build_emits_wheel_with_schema_and_compare_bridge(self) -> None:
        with tempfile.TemporaryDirectory(prefix="inkflip-wheel-") as raw:
            wheel = _build_wheel(Path(raw))
            with zipfile.ZipFile(wheel) as zf:
                names = zf.namelist()
                self.assertTrue(any(n.startswith("inkflip/cli/main.py") for n in names), names[:20])
                self.assertIn("inkflip/contracts/schema/inkflip.schema.json", names)
                self.assertIn("inkflip/resources/packages/compare/node/bridge.mjs", names)
                self.assertTrue(
                    any(n.startswith("inkflip/resources/packages/contracts/src/") for n in names),
                    names,
                )
                entry = [n for n in names if n.endswith("entry_points.txt")]
                self.assertTrue(entry, names)
                text = zf.read(entry[0]).decode("utf-8")
                self.assertIn("inkflip = inkflip.cli.main:main", text)
                self.assertFalse(any(n.endswith(".so") for n in names))

    def test_production_dockerfile_installs_hashed_complete_lock(self) -> None:
        text = (ROOT / "build" / "native" / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("COPY native/dist/wheels/ /wheels/", text)
        self.assertIn("COPY native/dist/requirements.lock /locks/requirements.lock", text)
        self.assertIn("--require-hashes", text)
        self.assertIn('ENTRYPOINT ["inkflip"]', text)
        self.assertIn("USER 65532:65532", text)
        self.assertIn("python:3.13.15-slim-trixie@sha256:", text)
        self.assertIn("INKFLIP_NODE=/opt/node/bin/node", text)
        self.assertIn("filter=\"data\"", text)
        self.assertNotIn("COPY native/dist/ /wheels/", text)


class TestInstalledWheelCli(unittest.TestCase):
    """Install the wheel outside the checkout and run real commands."""

    def test_installed_entry_point_from_unrelated_cwd_with_spaces(self) -> None:
        self.assertTrue(FIXTURE.is_file(), FIXTURE)
        outside = Path(tempfile.mkdtemp(prefix="inkflip-clean-env-", dir="/tmp"))
        spacey = outside / "work dir"
        spacey.mkdir()
        try:
            wheel_dir = spacey / "built"
            wheel_dir.mkdir()
            wheel = _build_wheel(wheel_dir)
            venv = outside / "venv"
            proc = subprocess.run(
                ["uv", "venv", "--python", "3.13.15", str(venv)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            python = venv / "bin" / "python"
            inkflip = venv / "bin" / "inkflip"
            install = subprocess.run(
                [
                    "uv",
                    "pip",
                    "install",
                    "--python",
                    str(python),
                    str(wheel),
                    "pypdfium2==5.8.0",
                    "pypdf==6.18.0",
                    "Pillow==12.3.0",
                    "jsonschema==4.26.0",
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(install.returncode, 0, install.stdout + install.stderr)
            self.assertTrue(inkflip.is_file())
            help_proc = subprocess.run(
                [str(inkflip), "--help"],
                cwd="/tmp",
                capture_output=True,
                text=True,
            )
            self.assertEqual(help_proc.returncode, 0, help_proc.stdout + help_proc.stderr)
            self.assertIn("inspect", help_proc.stdout)

            pdf = spacey / "mapping control.pdf"
            shutil.copy2(FIXTURE, pdf)
            report = spacey / "out report.json"
            inspect = subprocess.run(
                [str(inkflip), "inspect", str(pdf), "--out", str(report), "--pages", "1", "--replace-output"],
                cwd="/tmp",
                capture_output=True,
                text=True,
            )
            self.assertEqual(inspect.returncode, 0, inspect.stdout + inspect.stderr)
            data = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(data["kind"], "report")
            self.assertGreaterEqual(len(data.get("occurrences") or []), 1)

            html = spacey / "out report.html"
            rendered = subprocess.run(
                [str(inkflip), "report", str(report), "--format", "html", "--out", str(html), "--replace-output"],
                cwd="/tmp",
                capture_output=True,
                text=True,
            )
            self.assertEqual(rendered.returncode, 0, rendered.stdout + rendered.stderr)
            self.assertIn("INKFLIP", html.read_text(encoding="utf-8"))

            replay_out = spacey / "replay.json"
            replay = subprocess.run(
                [
                    str(inkflip),
                    "replay",
                    str(report),
                    "--source",
                    str(pdf),
                    "--profile",
                    "native-default",
                    "--out",
                    str(replay_out),
                    "--replace-output",
                ],
                cwd="/tmp",
                capture_output=True,
                text=True,
            )
            self.assertEqual(replay.returncode, 0, replay.stdout + replay.stderr)

            tes_env = os.environ.copy()
            tes_env["TESSDATA_PREFIX"] = str(spacey / "empty-tessdata")
            (spacey / "empty-tessdata").mkdir()
            tes = subprocess.run(
                [
                    str(inkflip),
                    "inspect",
                    str(pdf),
                    "--reader",
                    "tesseract",
                    "--out",
                    str(spacey / "ocr.json"),
                    "--ocr-pages",
                    "1",
                    "--replace-output",
                ],
                cwd="/tmp",
                capture_output=True,
                text=True,
                env=tes_env,
            )
            ocr_report = json.loads((spacey / "ocr.json").read_text(encoding="utf-8"))
            ocr_reasons = " ".join(
                str(check.get("reason") or check.get("status"))
                for check in ocr_report.get("checks") or []
            )
            self.assertIn("missing_model", ocr_reasons)
            self.assertTrue(
                tes.returncode in {0, 3, 4},
                tes.stdout + tes.stderr,
            )

            corpus_dir = spacey / "corpus"
            corpus_dir.mkdir()
            shutil.copy2(pdf, corpus_dir / "mapping-control.pdf")
            manifest = {
                "kind": "corpus_manifest",
                "schema_version": "1.0.0",
                "source_root_policy": "explicit_local_root_no_symlinks",
                "split": "development",
                "entries": [
                    {
                        "key": "mapping-control",
                        "source_path": "mapping-control.pdf",
                        "sha256": data["document"]["sha256"],
                        "group_id": "mapping-family",
                        "pages": [0],
                    }
                ],
            }
            manifest_path = spacey / "corpus.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            run_dir = spacey / "run"
            corpus = subprocess.run(
                [
                    str(inkflip),
                    "corpus",
                    "run",
                    "--manifest",
                    str(manifest_path),
                    "--source-root",
                    str(corpus_dir),
                    "--profile",
                    "native-default",
                    "--out",
                    str(run_dir),
                ],
                cwd="/tmp",
                capture_output=True,
                text=True,
            )
            self.assertIn(
                corpus.returncode,
                {0, 3, 4},
                corpus.stdout + corpus.stderr,
            )
        finally:
            shutil.rmtree(outside, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
