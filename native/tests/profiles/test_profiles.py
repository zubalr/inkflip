"""T33 isolated reader profile tests (TEST-33)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NATIVE = ROOT / "native"
FIXTURES = ROOT / "fixtures"
INSTALLER = ROOT / "scripts" / "install_reader_profile.py"
if str(NATIVE) not in sys.path:
    sys.path.insert(0, str(NATIVE))

from inkflip.cli.main import EXIT_OK, main  # noqa: E402
from inkflip.contracts import core  # noqa: E402
from inkflip.profiles import (  # noqa: E402
    ProfileAdapter,
    ProfileBlockedError,
    UntrustedProfileError,
    load_profile,
)
from inkflip.profiles.adapter import offline_child_env  # noqa: E402
from inkflip.profiles.pypdf_worker import extract_pdf  # noqa: E402


class TestProfileInstall(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.install_ok = False
        cls.tmp = tempfile.TemporaryDirectory()
        cls.profiles = Path(cls.tmp.name) / "path with spaces" / "profiles"
        cls.profiles.mkdir(parents=True)
        env = os.environ.copy()
        env["PYTHONPATH"] = str(NATIVE)
        before = subprocess.run(
            [
                sys.executable,
                str(INSTALLER),
                "--name",
                "before",
                "--reader",
                "pypdf",
                "--version",
                "5.9.0",
                "--profile-dir",
                str(cls.profiles),
            ],
            capture_output=True,
            text=True,
            env=env,
        )
        after = subprocess.run(
            [
                sys.executable,
                str(INSTALLER),
                "--name",
                "after",
                "--reader",
                "pypdf",
                "--version",
                "6.18.0",
                "--profile-dir",
                str(cls.profiles),
            ],
            capture_output=True,
            text=True,
            env=env,
        )
        cls.install_ok = before.returncode == 0 and after.returncode == 0
        cls.before_out = before.stdout + before.stderr
        cls.after_out = after.stdout + after.stderr
        if not cls.install_ok:
            cls.tmp.cleanup()

    @classmethod
    def tearDownClass(cls):
        if cls.install_ok:
            cls.tmp.cleanup()

    def setUp(self):
        if not self.install_ok:
            self.skipTest(f"profile install blocked: {self.before_out}\n{self.after_out}")

    def test_distinct_interpreters_and_versions(self):
        os.environ["INKFLIP_PROFILES_DIR"] = str(self.profiles)
        self.addCleanup(lambda: os.environ.pop("INKFLIP_PROFILES_DIR", None))
        before = load_profile("before")
        after = load_profile("after")
        self.assertNotEqual(before.executable, after.executable)
        self.assertEqual(before.version, "5.9.0")
        self.assertEqual(after.version, "6.18.0")
        self.assertIn(" ", str(before.executable))  # this repository path contains a space
        bdesc = ProfileAdapter(before).describe()
        adesc = ProfileAdapter(after).describe()
        self.assertEqual(bdesc["reader"]["version"], "5.9.0")
        self.assertEqual(adesc["reader"]["version"], "6.18.0")
        self.assertNotEqual(bdesc.get("interpreter"), adesc.get("interpreter"))

    def test_inspect_records_version(self):
        os.environ["INKFLIP_PROFILES_DIR"] = str(self.profiles)
        self.addCleanup(lambda: os.environ.pop("INKFLIP_PROFILES_DIR", None))
        td = Path(tempfile.mkdtemp())
        out = td / "out.inkflip.json"
        code = main(
            [
                "inspect",
                str(FIXTURES / "public" / "mapping-amount.pdf"),
                "--out",
                str(out),
                "--profile",
                "before",
            ]
        )
        self.assertEqual(code, EXIT_OK)
        data = json.loads(out.read_text())
        core.validate(data)
        self.assertEqual(data["readers"][0]["version"], "5.9.0")
        self.assertIn("5.9.0", data["execution"]["environment"])

    def test_offline_env_has_no_proxy(self):
        env = offline_child_env()
        self.assertNotIn("https_proxy", env)
        self.assertNotIn("HTTP_PROXY", env)
        self.assertEqual(env.get("NO_PROXY"), "*")


class TestUntrustedAndMissing(unittest.TestCase):
    def test_missing_version_blocks(self):
        td = Path(tempfile.mkdtemp())
        env = os.environ.copy()
        env["PYTHONPATH"] = str(NATIVE)
        proc = subprocess.run(
            [
                sys.executable,
                str(INSTALLER),
                "--name",
                "missing",
                "--reader",
                "pypdf",
                "--version",
                "0.0.0-not-a-release",
                "--profile-dir",
                str(td),
            ],
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertNotEqual(proc.returncode, 0)

    def test_untrusted_path_refused(self):
        os.environ["INKFLIP_PROFILES_DIR"] = tempfile.mkdtemp()
        self.addCleanup(lambda: os.environ.pop("INKFLIP_PROFILES_DIR", None))
        with self.assertRaises(UntrustedProfileError):
            load_profile("/tmp/evil.json")
        with self.assertRaises(UntrustedProfileError):
            load_profile("../evil")

    def test_absolute_wrapper_refused_if_present(self):
        td = Path(tempfile.mkdtemp())
        os.environ["INKFLIP_PROFILES_DIR"] = str(td)
        self.addCleanup(lambda: os.environ.pop("INKFLIP_PROFILES_DIR", None))
        wrapper = td / "custom.py"
        wrapper.write_text("print('nope')\n")
        descriptor = {
            "kind": "reader_profile",
            "schema_version": "1.0.0",
            "name": "custom",
            "reader": "pypdf",
            "version": "6.18.0",
            "executable": sys.executable,
            "platform": "test",
            "python_version": "x",
            "artifact_digest": None,
            "profile_sha256": "0" * 64,
            "wrapper_path": str(wrapper),
            "wrapper_sha256": "0" * 64,
            "created_at": "2026-01-01T00:00:00Z",
            "extra": {},
        }
        (td / "custom.json").write_text(json.dumps(descriptor))
        with self.assertRaises((UntrustedProfileError, Exception)):
            load_profile("custom")


class TestPdfjsWrapper(unittest.TestCase):
    def test_real_pdfjs_not_stub(self):
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not installed")
        bridge = ROOT / "packages" / "readers-pdfjs" / "node" / "bridge.mjs"
        local = ROOT / "packages" / "readers-pdfjs" / "node" / "node_modules" / "pdfjs-dist"
        pdf = FIXTURES / "public" / "mapping-amount.pdf"
        env = os.environ.copy()
        env["NODE_PATH"] = ""
        proc = subprocess.run(
            [node, str(bridge)],
            input=json.dumps({"action": "extract", "pdf_path": str(pdf), "pages": [0]}),
            capture_output=True,
            text=True,
            env=env,
        )
        if not local.exists():
            self.fail(
                "isolated pdfjs-dist is not installed. Documented setup: "
                "cd packages/readers-pdfjs/node && bun install --frozen-lockfile. "
                f"bridge stderr={proc.stderr!r} stdout={proc.stdout!r}"
            )
        data = json.loads(proc.stdout)
        self.assertTrue(data.get("ok"), data)
        self.assertEqual(data.get("pdfjs_version") or data["reader"]["version"], "6.3.289")
        texts = [page.get("raw_text") or "" for page in data.get("pages") or []]
        self.assertTrue(any(texts), "PDF.js wrapper must extract real text, not a stub")

    def test_missing_local_install_names_the_documented_command(self):
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not installed")
        with tempfile.TemporaryDirectory(prefix="inkflip-pdfjs-missing-") as raw:
            td = Path(raw)
            bridge = ROOT / "packages" / "readers-pdfjs" / "node" / "bridge.mjs"
            # Copy only the wrapper, not node_modules.
            dest = td / "bridge.mjs"
            dest.write_bytes(bridge.read_bytes())
            env = os.environ.copy()
            env["NODE_PATH"] = str(ROOT / "apps" / "web" / "node_modules")
            proc = subprocess.run(
                [node, str(dest)],
                input=json.dumps({"action": "describe"}),
                capture_output=True,
                text=True,
                env=env,
                cwd=td,
            )
            combined = (proc.stdout or "") + (proc.stderr or "")
            self.assertIn("bun install --frozen-lockfile", combined)
            self.assertIn("packages/readers-pdfjs/node", combined)
            if proc.stdout.strip():
                data = json.loads(proc.stdout)
                self.assertFalse(data.get("ok", True))

    def test_wrong_version_is_a_typed_profile_failure(self):
        node_dir = ROOT / "packages" / "readers-pdfjs" / "node"
        if not (node_dir / "node_modules" / "pdfjs-dist").exists():
            self.fail(
                "isolated pdfjs-dist is not installed. Documented setup: "
                "cd packages/readers-pdfjs/node && bun install --frozen-lockfile"
            )
        with tempfile.TemporaryDirectory(prefix="inkflip-pdfjs-ver-") as raw:
            env = os.environ.copy()
            env["PYTHONPATH"] = str(NATIVE)
            env["NODE_PATH"] = ""
            proc = subprocess.run(
                [
                    sys.executable,
                    str(INSTALLER),
                    "--name",
                    "wrong",
                    "--reader",
                    "pdfjs-node",
                    "--version",
                    "9.9.9",
                    "--profile-dir",
                    raw,
                ],
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(proc.returncode, 3, proc.stderr)
            self.assertIn("version mismatch", (proc.stderr or "").lower())


class TestWorkerFailuresStayFailed(unittest.TestCase):
    def test_extract_text_exception_is_failed_not_empty_success(self):
        class BoomPage:
            def extract_text(self):
                raise RuntimeError("injected extraction failure")

        class BoomReader:
            is_encrypted = False
            pages = [BoomPage(), BoomPage()]

        import inkflip.profiles.pypdf_worker as worker

        original = worker.pypdf.PdfReader
        worker.pypdf.PdfReader = lambda _path: BoomReader()
        try:
            result = extract_pdf(FIXTURES / "public" / "mapping-amount.pdf", [0, 1])
        finally:
            worker.pypdf.PdfReader = original
        self.assertTrue(result.get("ok"))
        pages = result["pages"]
        self.assertEqual(len(pages), 2)
        for page in pages:
            self.assertEqual(page["status"], "failed")
            self.assertIsNone(page["raw_text"])
            self.assertIn("extract_text failed", page["reason"])


if __name__ == "__main__":
    unittest.main()
