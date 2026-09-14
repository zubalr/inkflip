"""Host-mount guard for scripts/run_native_container.sh (pdf-c5v).

Validates refused home/root/etc mounts and accepted disposable Mac
workflows using isolated trees. Does not mount a user's home or private
data. Uses --check-mounts so tests never start a container.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "run_native_container.sh"
FIXTURE_DIR = ROOT / "fixtures" / "public"
HOME = Path.home().resolve()


def run_guard(source: str | Path, out: str | Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(SCRIPT), "--source-root", str(source), "--out", str(out), "--check-mounts"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


class TestNativeContainerMountGuard(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="inkflip-c5v-")
        self.td = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_refuses_users_and_home_volume_roots(self) -> None:
        out = self.td / "out"
        out.mkdir()
        for source in ("/Users", "/home", "/"):
            proc = run_guard(source, out)
            self.assertEqual(proc.returncode, 2, f"{source}: {proc.stderr}")
            self.assertIn("refusing", proc.stderr.lower())

    def test_refuses_current_home_directory(self) -> None:
        out = self.td / "out"
        out.mkdir()
        proc = run_guard(HOME, out)
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertIn("home directory", proc.stderr)

    def test_refuses_home_via_symlink(self) -> None:
        link = self.td / "link-to-home"
        os.symlink(HOME, link)
        out = self.td / "out"
        out.mkdir()
        proc = run_guard(link, out)
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertIn("refusing", proc.stderr.lower())

    def test_refuses_parent_traversal_to_home(self) -> None:
        candidate = self.td / "climb"
        candidate.mkdir()
        rel = os.path.relpath(HOME, candidate)
        proc = run_guard(candidate / rel, self.td / "out")
        self.assertEqual(proc.returncode, 2, proc.stderr)

    def test_refuses_etc(self) -> None:
        out = self.td / "out"
        out.mkdir()
        proc = run_guard("/etc", out)
        self.assertEqual(proc.returncode, 2, proc.stderr)

    def test_refuses_home_as_writable_output(self) -> None:
        source = self.td / "src"
        source.mkdir()
        proc = run_guard(source, HOME)
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertIn("output", proc.stderr)

    def test_allows_path_with_spaces(self) -> None:
        source = self.td / "source with spaces"
        out = self.td / "out with spaces"
        source.mkdir()
        (source / "file.pdf").write_bytes(b"%PDF-1.4\n")
        proc = run_guard(source, out)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("mount guard ok", proc.stderr)

    def test_allows_repo_fixture_directory(self) -> None:
        out = self.td / "fixture-out"
        proc = run_guard(FIXTURE_DIR, out)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("mount guard ok", proc.stderr)
        self.assertTrue(out.is_dir())

    def test_symlink_to_allowed_tree_is_accepted(self) -> None:
        real = self.td / "real-src"
        real.mkdir()
        link = self.td / "alias src"
        os.symlink(real, link)
        out = self.td / "out"
        proc = run_guard(link, out)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("mount guard ok", proc.stderr)

    def test_source_is_readonly_in_script(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("dst=/input,readonly", text)
        self.assertIn("--read-only", text)
        self.assertIn("--network none", text)


if __name__ == "__main__":
    unittest.main()
