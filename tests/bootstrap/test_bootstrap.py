"""TEST-01 bootstrap contract tests.

Assert the honest-harness behavior a clean checkout relies on: documented
commands exist, empty or missing test registrations fail loudly, the origin
license is preserved byte-exact, planning inputs are intact, and nothing here
performs a network action or claims acceptance that was not granted.

Never invoke `run verify` or `task T01` from this suite — they re-discover
these same tests and would recurse.
"""
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "scripts/task_acceptance.py"
GATE = ROOT / "scripts/gate.py"
ORIGIN_LICENSE_SHA256 = "3f1e48ee93685ecf2c49f768ad888dc47859b057f3b90c9f04f132315edf0c6d"


def run_tool(*args, cwd=ROOT):
    return subprocess.run([sys.executable, *args], cwd=cwd, text=True,
                          capture_output=True, check=False)


def load_registry():
    return json.loads((ROOT / "config/acceptance-commands.json").read_text())


class DocumentedCommandTests(unittest.TestCase):
    """A clean checkout exposes the documented commands."""

    def test_registry_defines_the_documented_surface(self):
        commands = load_registry()["commands"]
        for name in ("verify", "self-check", "test:bootstrap", "test:native-bootstrap",
                     "check:coordination", "build", "test:browser", "test:privacy",
                     "test:a11y", "test:visual", "test:fixtures", "test:regression",
                     "test:native", "check:static-dist"):
            self.assertIn(name, commands, f"documented command {name} missing from registry")

    def test_every_command_has_a_bun_script_through_the_harness(self):
        scripts = json.loads((ROOT / "package.json").read_text())["scripts"]
        for name in load_registry()["commands"]:
            self.assertIn(name, scripts, f"no package.json script for {name}")
            self.assertIn("task_acceptance.py", scripts[name])

    def test_list_reports_the_surface(self):
        result = run_tool(HARNESS, "list")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("verify", result.stdout)
        self.assertIn("unavailable", result.stdout)  # declared suites show as not yet runnable

    def test_self_check_passes_on_a_clean_checkout(self):
        result = run_tool(HARNESS, "self-check")
        self.assertEqual(result.returncode, 0, result.stderr)


class EmptyRegistrationFailsTests(unittest.TestCase):
    """Empty/missing test registration must fail explicitly."""

    def test_missing_registry_file_fails(self):
        result = run_tool(HARNESS, "--registry", "config/no-such.json", "run", "verify")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("registry missing", result.stderr)

    def test_empty_registry_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = Path(tmp) / "reg.json"
            reg.write_text(json.dumps({"commands": {}}))
            result = run_tool(HARNESS, "--registry", str(reg), "list")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("no commands", result.stderr)

    def test_unknown_command_fails(self):
        result = run_tool(HARNESS, "run", "test:does-not-exist")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not a documented command", result.stderr)

    def test_declared_suite_with_missing_runner_fails(self):
        # Pin the guarantee to a synthetic declared entry: any real command's
        # prerequisites are lifecycle-bound (T02 installs test:browser's
        # playwright), so a fixed name would silently stop exercising the check.
        with tempfile.TemporaryDirectory() as tmp:
            reg = Path(tmp) / "reg.json"
            reg.write_text(json.dumps({"commands": {"x": {
                "kind": "test", "status": "declared", "collection": "harness-unittest",
                "argv": [sys.executable, "-c", "pass"],
                "requires": ["path/that/never/exists"]}}}))
            result = run_tool(HARNESS, "--registry", str(reg), "run", "x")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("prerequisites missing", result.stderr)

    def test_declared_suite_with_no_implementation_fails(self):
        # The registry reserves per-owner registration (T05 registered
        # test:fixtures when its suite landed), so pin this guarantee to a
        # synthetic null-argv entry instead of another task's lifecycle.
        with tempfile.TemporaryDirectory() as tmp:
            reg = Path(tmp) / "reg.json"
            reg.write_text(json.dumps({"commands": {"x": {
                "kind": "test", "status": "active", "collection": "harness-unittest",
                "argv": None}}}))
            result = run_tool(HARNESS, "--registry", str(reg), "run", "x")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("no implementation registered", result.stderr)

    def test_zero_collected_unittest_suite_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "empty_suite"
            empty.mkdir()
            reg = Path(tmp) / "reg.json"
            reg.write_text(json.dumps({"commands": {"x": {
                "kind": "test", "status": "active", "collection": "harness-unittest",
                "argv": [sys.executable, "-m", "unittest", "discover", "-s", str(empty)]}}}))
            result = run_tool(HARNESS, "--registry", str(reg), "run", "x")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("zero tests collected", result.stderr)

    def test_nonempty_unittest_suite_passes(self):
        # Guards against a harness that fails everything: a real suite must pass.
        with tempfile.TemporaryDirectory() as tmp:
            suite = Path(tmp) / "real_suite"
            suite.mkdir()
            (suite / "test_one.py").write_text(
                "import unittest\nclass T(unittest.TestCase):\n"
                "    def test_ok(self): self.assertTrue(True)\n")
            reg = Path(tmp) / "reg.json"
            reg.write_text(json.dumps({"commands": {"x": {
                "kind": "test", "status": "active", "collection": "harness-unittest",
                "argv": [sys.executable, "-m", "unittest", "discover", "-s", str(suite)]}}}))
            result = run_tool(HARNESS, "--registry", str(reg), "run", "x")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Ran 1 test", result.stderr)

    def test_gate_refuses_unaccepted_prerequisites(self):
        result = run_tool(GATE, "G1")
        self.assertNotEqual(result.returncode, 0)
        self.assertRegex(result.stderr, r"prerequisite unmet|gate blocked")

    def test_gate_lists_registered_gates(self):
        result = run_tool(GATE, "--list")
        self.assertEqual(result.returncode, 0, result.stderr)
        for gate in ("G1", "G2", "G3", "G4", "G5"):
            self.assertIn(gate, result.stdout)


class WorkspaceBoundaryTests(unittest.TestCase):
    def test_bunfig_uses_isolated_linker(self):
        config = tomllib.loads((ROOT / "bunfig.toml").read_text())
        self.assertEqual(config["install"]["linker"], "isolated")

    def test_root_manifest_declares_workspaces_without_install_side_effects(self):
        package = json.loads((ROOT / "package.json").read_text())
        self.assertTrue(package["private"])
        self.assertIn("apps/*", package["workspaces"])
        self.assertIn("packages/*", package["workspaces"])
        self.assertEqual(package.get("trustedDependencies"), [])
        self.assertNotIn("postinstall", package.get("scripts", {}))
        for spec in package.get("devDependencies", {}).values():
            self.assertRegex(spec, re.compile(r"^\d+\.\d+\.\d+$"),
                             "declared versions must be exact pins")

    def test_package_boundaries_exist_and_match_root_references(self):
        root_ts = json.loads((ROOT / "tsconfig.json").read_text())
        referenced = {r["path"] for r in root_ts["references"]}
        packages = {p.name for p in (ROOT / "packages").iterdir() if p.is_dir()}
        self.assertEqual(referenced, {f"packages/{p}" for p in packages})
        self.assertGreaterEqual(len(packages), 8)
        for name in packages:
            manifest = json.loads((ROOT / "packages" / name / "package.json").read_text())
            self.assertEqual(manifest["name"], f"@inkflip/{name}")
            self.assertTrue(manifest["private"])
            tsconfig = json.loads((ROOT / "packages" / name / "tsconfig.json").read_text())
            self.assertEqual(tsconfig["extends"], "../../tsconfig.json")
            self.assertTrue(tsconfig["compilerOptions"]["composite"])

    def test_web_entry_is_local_strict_port_and_egress_free(self):
        vite = (ROOT / "apps/web/vite.config.ts").read_text()
        self.assertIn("5181", vite)
        self.assertIn("strictPort", vite)
        html = (ROOT / "apps/web/index.html").read_text()
        self.assertNotRegex(html, re.compile(r"https?://"), "index.html must not reference remote resources")
        for path in ("apps/web/src/main.tsx", "apps/web/src/App.tsx",
                     "apps/web/src/styles/tokens.css", "apps/web/src/styles/README.md"):
            self.assertTrue((ROOT / path).is_file(), f"{path} missing")

    def test_styles_contract_uses_central_tokens(self):
        tokens = (ROOT / "apps/web/src/styles/tokens.css").read_text()
        design = json.loads((ROOT / "planning/product/design-tokens.json").read_text())
        for token in design["color"]:
            self.assertIn(f"--color-{token}:", tokens.lower())
        module = (ROOT / "apps/web/src/styles/App.module.css").read_text()
        self.assertNotRegex(module, re.compile(r"#[0-9a-fA-F]{3,8}\b"),
                            "component CSS must consume tokens, not raw colors")


class OriginAndHonestyTests(unittest.TestCase):
    def test_origin_license_is_byte_exact(self):
        license_bytes = (ROOT / "third_party/origin/mib-intake/LICENSE").read_bytes()
        self.assertEqual(hashlib.sha256(license_bytes).hexdigest(), ORIGIN_LICENSE_SHA256)

    def test_origin_doc_records_source_commit(self):
        origin = (ROOT / "docs/ORIGIN.md").read_text()
        self.assertIn("94f35ce9f9beb1640ddebdc2c72aa379ecebb004", origin)
        self.assertIn("third_party/origin/mib-intake/LICENSE", origin)

    def test_planning_snapshot_is_byte_identical(self):
        sums = (ROOT / "planning/SHA256SUMS.txt").read_text().splitlines()
        checked = 0
        for line in sums:
            digest, _, rel = line.partition("  ")
            path = ROOT / "planning" / rel.strip()
            self.assertTrue(path.is_file(), f"missing planning file {rel}")
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest,
                             f"planning file changed: {rel}")
            checked += 1
        self.assertGreater(checked, 250)

    def test_no_json_task_state_file_exists(self):
        self.assertFalse((ROOT / "execution/state.json").exists(),
                         "Beads is the task-state authority; no execution/state.json")

    def test_no_network_action_in_commands_or_ci(self):
        forbidden = ("install --", "pnpm install", "bun install", "uv sync",
                     "curl ", "wget ", "npm install", "pull_request_target")
        ci = (ROOT / ".github/workflows/ci.yml").read_text()
        for token in forbidden:
            self.assertNotIn(token, ci)
        for name, entry in load_registry()["commands"].items():
            for arg in entry.get("argv") or []:
                self.assertNotIn(arg, ("install", "sync", "add", "fetch"),
                                 f"{name} performs a network-capable step")

    def test_no_achievement_claim_in_worker_evidence(self):
        artifacts = ROOT / "artifacts/tasks/T01"
        for receipt in artifacts.glob("*.json"):
            data = json.loads(receipt.read_text())
            if "disposition" in data:
                self.assertTrue(
                    receipt.name.startswith("acceptance") or
                    data["disposition"] not in ("accepted", "rejected_experiment"),
                    f"{receipt.name} records a disposition only the coordinator may grant")


if __name__ == "__main__":
    unittest.main()
