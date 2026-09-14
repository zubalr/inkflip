"""Section J — the combined native lifecycle, end to end as one real run.

corpus run -> corpus resume -> baseline create -> corpus run -> compare -> HTML report -> replay,
each step a real subprocess on the pinned interpreter, with the artefacts of every
step asserted. Captured first (evidence/secJ-lifecycle.log), then pinned here.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NATIVE = ROOT / "native"
FIXTURES = ROOT / "fixtures"
PUBLIC = FIXTURES / "public"
if str(NATIVE) not in sys.path:
    sys.path.insert(0, str(NATIVE))

from inkflip.contracts import core  # noqa: E402

SOURCES = (("amount", "mapping-amount.pdf"), ("control", "mapping-control.pdf"), ("covered", "covered-amount.pdf"))
EXIT_OK = 0


def _env() -> dict[str, str]:
    env = dict(os.environ)
    prior = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(NATIVE) + (os.pathsep + prior if prior else "")
    return env


def cli(*argv: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "inkflip.cli", *argv],
        cwd=str(ROOT), capture_output=True, text=True, env=_env(), timeout=600,
    )


class TestCombinedNativeLifecycle(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.td = Path(self.tmp.name)
        entries = [
            {
                "key": key,
                "source_path": name,
                "sha256": hashlib.sha256((PUBLIC / name).read_bytes()).hexdigest(),
                "group_id": key,
                "pages": [0],
            }
            for key, name in SOURCES
        ]
        self.manifest = self.td / "corpus.json"
        self.manifest.write_text(json.dumps({
            "kind": "corpus_manifest",
            "schema_version": "1.0.0",
            "split": "public_demo",
            "source_root_policy": "explicit_local_root_no_symlinks",
            "entries": entries,
        }))
        self.run = self.td / "run"

    def tearDown(self):
        self.tmp.cleanup()

    def corpus(self, out: Path, *extra: str) -> dict:
        result = cli("corpus", "run", "--manifest", str(self.manifest), "--source-root", str(PUBLIC),
                     "--profile", "native-default", "--out", str(out), *extra)
        self.assertEqual(result.returncode, EXIT_OK, result.stderr)
        return json.loads((out / "index.json").read_text())

    def test_full_lifecycle(self):
        # 1. corpus run
        index = self.corpus(self.run)
        self.assertEqual({k: v["status"] for k, v in index["jobs"].items()},
                         {k: "completed" for k, _ in SOURCES})
        for key, _ in SOURCES:
            report = json.loads((self.run / "reports" / f"{key}.json").read_text())
            core.validate(report)

        # 2. resume reuses the committed evidence rather than rerunning
        resumed = self.corpus(self.run, "--resume")
        self.assertEqual({k: v["status"] for k, v in resumed["jobs"].items()},
                         {k: "skipped" for k, _ in SOURCES})
        self.assertTrue(all(v.get("resumed") for v in resumed["jobs"].values()))

        # 3. baseline create commits a manifest and its verified backing reports
        baseline = self.td / "baseline.json"
        result = cli("baseline", "create", "--run", str(self.run), "--out", str(baseline),
                     "--approved-by", "lifecycle", "--rationale", "combined lifecycle")
        self.assertEqual(result.returncode, EXIT_OK, result.stderr)
        record = json.loads(baseline.read_text())
        core.validate(record)
        self.assertEqual(len(record["report_ids"]), len(SOURCES))
        sidecar = baseline.with_suffix(baseline.suffix + ".reports")
        self.assertTrue(sidecar.is_dir())
        self.assertEqual(len(list(sidecar.glob("*.json"))), len(SOURCES))

        # 4. a fresh run compares against the baseline
        fresh = self.td / "run2"
        self.corpus(fresh)
        comparison_dir = self.td / "cmp"
        result = cli("compare", str(baseline), str(fresh), "--out", str(comparison_dir))
        self.assertEqual(result.returncode, EXIT_OK, result.stderr)
        comparison = json.loads((comparison_dir / "comparison.json").read_text())
        core.validate(comparison)
        self.assertEqual(comparison["status"], "unchanged")
        self.assertTrue((comparison_dir / "comparison.html").is_file())

        # 5. HTML export is script-free and carries its policy
        html = self.td / "report.html"
        result = cli("report", str(self.run / "reports" / "amount.json"), "--format", "html", "--out", str(html))
        self.assertEqual(result.returncode, EXIT_OK, result.stderr)
        text = html.read_text()
        self.assertNotIn("<script", text.lower())
        self.assertIn("Content-Security-Policy", text)
        self.assertGreater(len(text), 1000)

        # 6. replay preserves the recorded document identity
        replay = self.td / "replay.json"
        result = cli("replay", str(self.run / "reports" / "amount.json"),
                     "--source", str(PUBLIC / "mapping-amount.pdf"), "--profile", "native-default", "--out", str(replay))
        self.assertEqual(result.returncode, EXIT_OK, result.stderr)
        original = json.loads((self.run / "reports" / "amount.json").read_text())
        replayed = json.loads(replay.read_text())
        core.validate(replayed)
        self.assertEqual(replayed["document"]["sha256"], original["document"]["sha256"])
        # The replay records which report it came from in the export block.
        self.assertEqual(replayed["export"]["origin_report_id"], original["report_id"])


if __name__ == "__main__":
    unittest.main()
