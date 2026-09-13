"""TEST-35: documented reader-upgrade example commands, identities, exit 5, baseline bytes."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NATIVE = ROOT / "native"
if str(NATIVE) not in sys.path:
    sys.path.insert(0, str(NATIVE))

from inkflip.contracts import core  # noqa: E402

README = ROOT / "examples" / "reader-upgrade" / "README.md"
VERBATIM = [
    "python scripts/install_reader_profile.py --name before --reader pypdf --version 5.9.0",
    "python scripts/install_reader_profile.py --name after --reader pypdf --version 6.18.0",
    "inkflip corpus run --manifest examples/reader-upgrade/corpus.json --source-root planning/fixtures --profile before --out runs/before",
    "inkflip corpus run --manifest examples/reader-upgrade/corpus.json --source-root planning/fixtures --profile after --out runs/after",
    "inkflip baseline create --run runs/before --rules examples/reader-upgrade/upgrade-rules.json --out baselines/before.json --approved-by local-reviewer --rationale 'Explicit local reader upgrade acceptance policy'",
    "inkflip compare baselines/before.json runs/after --rules examples/reader-upgrade/upgrade-rules.json --out comparisons/upgrade",
    "inkflip report runs/after/reports/mapping-control.json --format html --out runs/after/mapping-control.html --replace-output",
]


def _readme_commands() -> list[str]:
    text = README.read_text(encoding="utf-8")
    blocks = re.findall(r"```sh\n(.*?)```", text, flags=re.S)
    commands = []
    for block in blocks:
        for line in block.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped == "sh examples/reader-upgrade/run.sh":
                continue
            commands.append(stripped)
    return commands


class TestReadmeCommandsCopiedVerbatim(unittest.TestCase):
    def test_readme_contains_each_documented_command(self):
        text = README.read_text(encoding="utf-8")
        for command in VERBATIM:
            self.assertIn(command, text)
        extracted = _readme_commands()
        for command in VERBATIM:
            self.assertIn(command, extracted)


@unittest.skipUnless(shutil.which("python") or True, "python launcher")
class TestReaderUpgradeExample(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sandbox = Path(tempfile.mkdtemp(prefix="inkflip-t35-"))
        for name in ("scripts", "native", "planning", "examples", "packages"):
            os.symlink(ROOT / name, cls.sandbox / name)
        python = sys.executable
        env = os.environ.copy()
        env["PYTHONPATH"] = str(cls.sandbox / "native")
        env["INKFLIP_PROFILES_DIR"] = str(cls.sandbox / "profiles")
        env["INKFLIP_PYTHON"] = python
        env["PATH"] = (
            str(cls.sandbox / "examples" / "reader-upgrade" / "bin")
            + os.pathsep
            + str(Path(python).parent)
            + os.pathsep
            + env.get("PATH", "")
        )
        wrapper = cls.sandbox / "examples" / "reader-upgrade" / "bin" / "inkflip"
        wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR)
        cls.env = env
        cls.setup_error = None
        cls.logs = []
        for command in _readme_commands():
            if command.startswith("export "):
                continue
            proc = subprocess.run(
                command,
                shell=True,
                cwd=cls.sandbox,
                env=cls.env,
                capture_output=True,
                text=True,
            )
            cls.logs.append((command, proc.returncode, proc.stdout, proc.stderr))
            allowed = (0, 5) if command.startswith("inkflip compare baselines/before.json runs/after ") else (0,)
            if proc.returncode not in allowed:
                cls.setup_error = f"{command}\nexit {proc.returncode}\n{proc.stdout}\n{proc.stderr}"
                return

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.sandbox, ignore_errors=True)

    def setUp(self):
        if getattr(self, "setup_error", None):
            self.fail(self.setup_error)

    def test_example_runs_end_to_end_locally(self):
        self.assertTrue((self.sandbox / "runs" / "before" / "index.json").is_file())
        self.assertTrue((self.sandbox / "runs" / "after" / "index.json").is_file())
        self.assertTrue((self.sandbox / "baselines" / "before.json").is_file())
        self.assertTrue((self.sandbox / "comparisons" / "upgrade" / "comparison.json").is_file())
        self.assertTrue((self.sandbox / "runs" / "after" / "mapping-control.html").is_file())

    def test_before_after_identities_differ(self):
        before = json.loads((self.sandbox / "runs" / "before" / "reports" / "mapping-control.json").read_text())
        after = json.loads((self.sandbox / "runs" / "after" / "reports" / "mapping-control.json").read_text())
        core.validate(before)
        core.validate(after)
        self.assertEqual(before["readers"][0]["version"], "5.9.0")
        self.assertEqual(after["readers"][0]["version"], "6.18.0")
        self.assertNotEqual(before["execution"]["environment"], after["execution"]["environment"])
        self.assertIn("5.9.0", before["execution"]["environment"])
        self.assertIn("6.18.0", after["execution"]["environment"])

    def test_output_reopens_as_script_free_html(self):
        html = (self.sandbox / "runs" / "after" / "mapping-control.html").read_text()
        self.assertIn("<!doctype html>", html.lower())
        self.assertIn("Content-Security-Policy", html)
        self.assertNotIn("<script", html.lower())
        comparison_html = (self.sandbox / "comparisons" / "upgrade" / "comparison.html").read_text()
        self.assertIn("<!doctype html>", comparison_html.lower())
        self.assertNotIn("<script", comparison_html.lower())

    def test_known_rule_failing_mutation_exits_5_without_modifying_baseline(self):
        baseline = self.sandbox / "baselines" / "before.json"
        before_bytes = baseline.read_bytes()
        before_digest = hashlib.sha256(before_bytes).hexdigest()
        mutated_dir = self.sandbox / "runs" / "after-mutated"
        shutil.copytree(self.sandbox / "runs" / "after", mutated_dir)
        report_path = mutated_dir / "reports" / "mapping-control.json"
        report = json.loads(report_path.read_text())
        for occ in report["occurrences"]:
            occ["raw_text"] = occ["raw_text"].replace("$100", "$999")
            occ["normalized_text"], occ["normalization_map"] = core.normalize(occ["raw_text"])
        report = core.seal(report)
        core.validate(report)
        report_path.write_text(json.dumps(report, indent=2) + "\n")
        out = self.sandbox / "comparisons" / "mutated"
        command = (
            "inkflip compare baselines/before.json runs/after-mutated "
            "--rules examples/reader-upgrade/upgrade-rules.json "
            f"--out {out}"
        )
        proc = subprocess.run(command, shell=True, cwd=self.sandbox, env=self.env, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 5, proc.stdout + proc.stderr)
        self.assertEqual(hashlib.sha256(baseline.read_bytes()).hexdigest(), before_digest)
        self.assertEqual(baseline.read_bytes(), before_bytes)


if __name__ == "__main__":
    unittest.main()
