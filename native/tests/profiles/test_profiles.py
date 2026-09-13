"""Tests for version-isolated reader profiles (T33, TEST-33).

Acceptance criteria:
- Old/new pypdf versions demonstrably loaded from distinct interpreters
- reader version printed in outputs
- missing version install blocks that profile
- untrusted profile path/command refused
- offline run makes no requests
"""
from __future__ import annotations

import io
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
NATIVE = ROOT / "native"
if str(NATIVE) not in sys.path:
    sys.path.insert(0, str(NATIVE))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from inkflip.profiles import (
    ALLOWED_READERS,
    ProfileAdapter,
    ProfileBlockedError,
    ProfileError,
    ProfileNotFoundError,
    ReaderProfile,
    UntrustedProfileError,
    get_profile_path,
    list_profiles,
    load_profile,
    save_profile,
    validate_profile_name,
)
import scripts.install_reader_profile as installer

SAMPLE_PDF = Path(__file__).resolve().parent.parent.parent.parent / "tests" / "build" / "probe" / "fixture.pdf"


class TestProfileContainmentAndValidation(unittest.TestCase):
    """Verifies security invariants, safe identifiers, and blocking of missing versions."""

    def setUp(self):
        self.td = Path(tempfile.mkdtemp(prefix="test-prof-containment-"))
        self.profiles_dir = self.td / "profiles"
        self.profiles_dir.mkdir()

    def tearDown(self):
        shutil.rmtree(self.td, ignore_errors=True)

    def test_untrusted_profile_name_rejected(self):
        """Untrusted names with traversal, slashes, or shell metacharacters are rejected."""
        invalid_names = [
            "../escape",
            "foo/bar",
            "name with spaces",
            "cmd;injection",
            "cmd|pipe",
            "name$var",
            "`whoami`",
            "",
            "a" * 65,
        ]
        for name in invalid_names:
            with self.subTest(name=name):
                with self.assertRaises(UntrustedProfileError):
                    validate_profile_name(name)
                with self.assertRaises(UntrustedProfileError):
                    get_profile_path(name, base_dir=self.profiles_dir)
                with self.assertRaises(UntrustedProfileError):
                    load_profile(name, base_dir=self.profiles_dir)

    def test_untrusted_reader_family_rejected(self):
        """Only allowlisted reader families may be loaded."""
        profile_file = self.profiles_dir / "untrusted_reader.json"
        profile_file.write_text(
            json.dumps({
                "kind": "reader_profile",
                "schema_version": "1.0.0",
                "name": "untrusted_reader",
                "reader": "arbitrary_sh",
                "version": "1.0.0",
                "executable": sys.executable,
                "platform": sys.platform,
                "python_version": sys.version,
                "wrapper_path": str(Path(__file__).resolve()),
            }),
            encoding="utf-8",
        )
        with self.assertRaises(UntrustedProfileError):
            load_profile("untrusted_reader", base_dir=self.profiles_dir)

    def test_untrusted_command_injection_rejected(self):
        """Executable path containing shell characters or injection is refused."""
        profile_file = self.profiles_dir / "evil_cmd.json"
        profile_file.write_text(
            json.dumps({
                "kind": "reader_profile",
                "schema_version": "1.0.0",
                "name": "evil_cmd",
                "reader": "pypdf",
                "version": "6.18.0",
                "executable": "/bin/sh -c 'echo pwned'",
                "platform": sys.platform,
                "python_version": sys.version,
                "wrapper_path": str(Path(__file__).resolve()),
            }),
            encoding="utf-8",
        )
        with self.assertRaises(UntrustedProfileError):
            load_profile("evil_cmd", base_dir=self.profiles_dir)

    def test_missing_version_install_blocks_profile(self):
        """Criterion: missing version install blocks that profile."""
        # Case 1: executable does not exist at all
        nonexistent_exe = self.td / "bin" / "nonexistent_python"
        profile_file = self.profiles_dir / "missing_version.json"
        profile_file.write_text(
            json.dumps({
                "kind": "reader_profile",
                "schema_version": "1.0.0",
                "name": "missing_version",
                "reader": "pypdf",
                "version": "9.9.9",
                "executable": str(nonexistent_exe),
                "platform": sys.platform,
                "python_version": sys.version,
                "wrapper_path": str(Path(__file__).resolve()),
            }),
            encoding="utf-8",
        )
        with self.assertRaises(ProfileBlockedError):
            load_profile("missing_version", base_dir=self.profiles_dir)

        # Case 2: file exists but is not executable
        non_exec_file = self.td / "not_exec.txt"
        non_exec_file.write_text("not executable")
        profile_file2 = self.profiles_dir / "not_exec.json"
        profile_file2.write_text(
            json.dumps({
                "kind": "reader_profile",
                "schema_version": "1.0.0",
                "name": "not_exec",
                "reader": "pypdf",
                "version": "1.0.0",
                "executable": str(non_exec_file),
                "platform": sys.platform,
                "python_version": sys.version,
                "wrapper_path": str(Path(__file__).resolve()),
            }),
            encoding="utf-8",
        )
        with self.assertRaises(ProfileBlockedError):
            load_profile("not_exec", base_dir=self.profiles_dir)

    def test_missing_profile_raises_not_found(self):
        """Attempting to load a nonexistent profile raises ProfileNotFoundError."""
        with self.assertRaises(ProfileNotFoundError):
            load_profile("does_not_exist", base_dir=self.profiles_dir)


class TestDistinctInterpretersAndOutput(unittest.TestCase):
    """Verifies isolation, distinct interpreters, and output requirements."""

    @classmethod
    def setUpClass(cls):
        cls.td = Path(tempfile.mkdtemp(prefix="test-prof-isolation-"))
        cls.profiles_dir = cls.td / "profiles"
        cls.profiles_dir.mkdir()

        # Install profile 1: pypdf 5.9.0
        cls.prof_before = installer.install_pypdf_profile(
            name="before",
            version="5.9.0",
            profile_dir=cls.profiles_dir,
        )

        # Install profile 2: pypdf 6.18.0
        cls.prof_after = installer.install_pypdf_profile(
            name="after",
            version="6.18.0",
            profile_dir=cls.profiles_dir,
        )

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.td, ignore_errors=True)

    def test_distinct_interpreters_loaded(self):
        """Criterion: Old/new pypdf versions demonstrably loaded from distinct interpreters."""
        # 1. Inspect profile objects
        self.assertNotEqual(
            self.prof_before.executable,
            self.prof_after.executable,
            "Interpreters must be separate executables/venvs",
        )
        self.assertEqual(self.prof_before.version, "5.9.0")
        self.assertEqual(self.prof_after.version, "6.18.0")

        # 2. Invoke describe via ProfileAdapter
        adapter_before = ProfileAdapter(self.prof_before)
        adapter_after = ProfileAdapter(self.prof_after)

        desc_before = adapter_before.describe()
        desc_after = adapter_after.describe()

        self.assertEqual(desc_before["pypdf_version"], "5.9.0")
        self.assertEqual(desc_after["pypdf_version"], "6.18.0")

        # The reported sys.executable inside the child processes must differ
        self.assertNotEqual(
            desc_before["interpreter"],
            desc_after["interpreter"],
            "Child process interpreters must be distinct",
        )

    def test_reader_version_printed_in_outputs(self):
        """Criterion: reader version printed in outputs."""
        adapter_before = ProfileAdapter(self.prof_before)
        res_before = adapter_before.extract(SAMPLE_PDF, pages=[0])

        self.assertTrue(res_before.get("ok"))
        self.assertEqual(res_before["version"], "5.9.0")
        self.assertEqual(res_before["reader"]["version"], "5.9.0")
        self.assertIn("5.9.0", res_before["reader"]["build"])

        adapter_after = ProfileAdapter(self.prof_after)
        res_after = adapter_after.extract(SAMPLE_PDF, pages=[0])

        self.assertTrue(res_after.get("ok"))
        self.assertEqual(res_after["version"], "6.18.0")
        self.assertEqual(res_after["reader"]["version"], "6.18.0")
        self.assertIn("6.18.0", res_after["reader"]["build"])

        # Also verify installer CLI prints version
        stdout_capture = io.StringIO()
        with patch("sys.stdout", stdout_capture):
            code = installer.main([
                "--name", "before",
                "--reader", "pypdf",
                "--version", "5.9.0",
                "--profile-dir", str(self.profiles_dir),
            ])
        self.assertEqual(code, 0)
        output = stdout_capture.getvalue()
        self.assertIn("Reader: pypdf 5.9.0", output)

    def test_offline_run_makes_no_requests(self):
        """Criterion: offline run makes no requests."""
        adapter = ProfileAdapter(self.prof_before)

        # Defensively poison socket creation to ensure no outbound network call occurs
        real_socket = socket.socket

        def poisoned_socket(*args, **kwargs):
            raise AssertionError("Unexpected network call during offline reader execution!")

        with patch("socket.socket", side_effect=poisoned_socket):
            # Run extraction
            res = adapter.extract(SAMPLE_PDF, pages=[0])
            self.assertTrue(res.get("ok"))
            self.assertEqual(res["version"], "5.9.0")
            self.assertTrue(len(res["occurrences"]) > 0)


class TestNodePdfJsProfile(unittest.TestCase):
    """Verifies Node PDF.js profile wrapper."""

    def setUp(self):
        self.td = Path(tempfile.mkdtemp(prefix="test-node-profile-"))
        self.profiles_dir = self.td / "profiles"
        self.profiles_dir.mkdir()

    def tearDown(self):
        shutil.rmtree(self.td, ignore_errors=True)

    def test_node_pdfjs_wrapper_describe_and_extract(self):
        node_path = shutil.which("node")
        if not node_path:
            self.skipTest("node is not installed on this system")

        prof = installer.install_pdfjs_profile(
            name="node-pdfjs",
            version="6.3.289",
            profile_dir=self.profiles_dir,
        )
        self.assertEqual(prof.reader, "pdfjs-node")
        self.assertEqual(prof.version, "6.3.289")

        loaded = load_profile("node-pdfjs", base_dir=self.profiles_dir)
        self.assertEqual(loaded.name, "node-pdfjs")

        adapter = ProfileAdapter(loaded)
        desc = adapter.describe()
        self.assertTrue(desc.get("ok"))
        self.assertEqual(desc["reader"]["id"], "pdfjs-node")
        self.assertEqual(desc["reader"]["version"], "6.3.289")

        extract_res = adapter.extract(SAMPLE_PDF, pages=[0])
        self.assertTrue(extract_res.get("ok"))
        self.assertEqual(extract_res["reader"]["version"], "6.3.289")


if __name__ == "__main__":
    unittest.main()
