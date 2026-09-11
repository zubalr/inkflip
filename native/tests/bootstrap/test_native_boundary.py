"""T01 native boundary checks: stdlib only, no installed dependencies required."""
import re
import sys
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NATIVE = ROOT / "native"


class NativeBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(NATIVE))

    @classmethod
    def tearDownClass(cls):
        sys.path.remove(str(NATIVE))

    def test_pyproject_declares_project_and_planned_pins(self):
        data = tomllib.loads((NATIVE / "pyproject.toml").read_text())
        project = data["project"]
        self.assertEqual(project["name"], "inkflip")
        self.assertIn("requires-python", project)
        deps = project["dependencies"]
        for expected in ("pypdfium2", "pypdf", "Pillow", "jsonschema"):
            self.assertTrue(any(d.startswith(expected + "==") for d in deps),
                            f"{expected} planned pin missing")
        for dep in deps:
            self.assertRegex(dep, re.compile(r"^[A-Za-z0-9_.-]+==\S+$"),
                             "native dependencies must be exact pins, not floating ranges")

    def test_inkflip_imports_without_third_party_dependencies(self):
        import inkflip
        self.assertEqual(inkflip.__version__, "0.0.0")


if __name__ == "__main__":
    unittest.main()
