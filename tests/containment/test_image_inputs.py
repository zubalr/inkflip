"""Preflight for production native image inputs."""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check_native_image_inputs.py"


class TestNativeImageInputs(unittest.TestCase):
    def test_current_tree_fails_closed_without_inventing_wheels(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(SCRIPT)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        combined = proc.stdout + proc.stderr
        self.assertIn("incomplete", combined)
        self.assertTrue(
            "no .whl files" in combined
            or "missing wheel directory" in combined
            or "Inkflip application wheel missing" in combined,
            combined,
        )

    def test_inventory_lists_gaps_without_certifying(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--inventory"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertTrue(proc.stdout.strip())
        self.assertNotIn("native image inputs: complete", proc.stdout)


if __name__ == "__main__":
    unittest.main()
