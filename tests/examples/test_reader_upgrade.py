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
NATIVE_PYTHON = ROOT / "native" / ".venv" / "bin" / "python"


def _reexec_native() -> None:
    """The T35 command is `python -m unittest`; this host maps that to
    system python3, which lacks the frozen native extras. Re-enter the
    committed native interpreter so the test process can import inkflip.
    Subprocess example routes use the README/run.sh PATH setup instead of
    this re-exec.
    """
    if not NATIVE_PYTHON.is_file():
        return
    if Path(sys.executable).resolve() == NATIVE_PYTHON.resolve():
        return
    os.execv(str(NATIVE_PYTHON), [str(NATIVE_PYTHON), *sys.argv])


_reexec_native()
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
SETUP_EXPORTS = [
    'export PATH="$PWD/native/.venv/bin:$PWD/examples/reader-upgrade/bin:$PATH"',
    'export PYTHONPATH="$PWD/native"',
    'export INKFLIP_PROFILES_DIR="$PWD/profiles"',
]
RUN_SH = "sh examples/reader-upgrade/run.sh"


def _readme_sh_blocks() -> list[str]:
    text = README.read_text(encoding="utf-8")
    return re.findall(r"```sh\n(.*?)```", text, flags=re.S)


def _readme_lines() -> list[str]:
    commands = []
    for block in _readme_sh_blocks():
        for line in block.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            commands.append(stripped)
    return commands


def ordinary_env() -> dict[str, str]:
    """Login-like env: python3/uv may exist; `python` is not on PATH."""
    path_parts = [
        "/usr/bin",
        "/bin",
        "/usr/sbin",
        "/sbin",
        "/usr/local/bin",
        str(Path.home() / ".local" / "bin"),
        "/opt/homebrew/bin",
    ]
    env = {
        "HOME": os.environ.get("HOME", ""),
        "USER": os.environ.get("USER", ""),
        "LOGNAME": os.environ.get("LOGNAME", ""),
        "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "LC_ALL": os.environ.get("LC_ALL", "en_US.UTF-8"),
        "PATH": os.pathsep.join(path_parts),
        "CDPATH": "",
    }
    for key in ("UV_CACHE_DIR", "XDG_CACHE_HOME", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE"):
        if key in os.environ:
            env[key] = os.environ[key]
    return env


def make_sandbox() -> Path:
    parent = Path(tempfile.mkdtemp(prefix="inkflip-t35-"))
    sandbox = parent / "checkout with spaces"
    sandbox.mkdir()
    for name in ("scripts", "native", "planning", "packages"):
        os.symlink(ROOT / name, sandbox / name)
    dest = sandbox / "examples" / "reader-upgrade"
    dest.parent.mkdir()
    shutil.copytree(ROOT / "examples" / "reader-upgrade", dest, symlinks=True)
    wrapper = dest / "bin" / "inkflip"
    wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR)
    script = dest / "run.sh"
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return sandbox


def run_sh(script: str, cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["/bin/sh", "-c", script],
        cwd=cwd,
        env=env if env is not None else ordinary_env(),
        capture_output=True,
        text=True,
    )


def assert_example_outputs(test: unittest.TestCase, sandbox: Path) -> None:
    test.assertTrue((sandbox / "runs" / "before" / "index.json").is_file())
    test.assertTrue((sandbox / "runs" / "after" / "index.json").is_file())
    test.assertTrue((sandbox / "baselines" / "before.json").is_file())
    test.assertTrue((sandbox / "comparisons" / "upgrade" / "comparison.json").is_file())
    test.assertTrue((sandbox / "runs" / "after" / "mapping-control.html").is_file())
    test.assertTrue((sandbox / "comparisons" / "upgrade" / "comparison.html").is_file())


def assert_named_profile_identities(test: unittest.TestCase, sandbox: Path) -> None:
    before = json.loads((sandbox / "runs" / "before" / "reports" / "mapping-control.json").read_text())
    after = json.loads((sandbox / "runs" / "after" / "reports" / "mapping-control.json").read_text())
    core.validate(before)
    core.validate(after)
    test.assertEqual(before["readers"][0]["version"], "5.9.0")
    test.assertEqual(after["readers"][0]["version"], "6.18.0")
    test.assertNotEqual(before["execution"]["environment"], after["execution"]["environment"])
    test.assertIn("5.9.0", before["execution"]["environment"])
    test.assertIn("6.18.0", after["execution"]["environment"])
    html = (sandbox / "runs" / "after" / "mapping-control.html").read_text()
    test.assertIn("6.18.0", html)
    test.assertNotIn("chk_pdfium_text_p0", html)


class TestReadmeCommandsCopiedVerbatim(unittest.TestCase):
    def test_readme_contains_each_documented_command(self):
        text = README.read_text(encoding="utf-8")
        for command in VERBATIM:
            self.assertIn(command, text)
        extracted = _readme_lines()
        for command in SETUP_EXPORTS + VERBATIM:
            self.assertIn(command, extracted)
        self.assertIn(RUN_SH, extracted)
        self.assertIn("native/.venv/bin", extracted[0])

    def test_ordinary_shell_has_no_python_until_frozen_path(self):
        sandbox = make_sandbox()
        try:
            missing = run_sh("command -v python >/dev/null; printf 'python_exit:%s\\n' $?", sandbox)
            self.assertEqual(missing.returncode, 0, missing.stdout + missing.stderr)
            self.assertIn("python_exit:1", missing.stdout + missing.stderr)
            with_setup = run_sh(
                "\n".join(SETUP_EXPORTS + ["command -v python", "python -c 'import sys; print(sys.executable)'"]),
                sandbox,
            )
            self.assertEqual(with_setup.returncode, 0, with_setup.stdout + with_setup.stderr)
            self.assertIn(".venv", with_setup.stdout.replace("\\", "/"))
        finally:
            shutil.rmtree(sandbox.parent, ignore_errors=True)


class TestDocumentedRoutesFailClosed(unittest.TestCase):
    def test_python_command_missing_without_readme_exports(self):
        sandbox = make_sandbox()
        try:
            proc = run_sh(VERBATIM[0], sandbox)
            self.assertEqual(proc.returncode, 127)
            combined = proc.stdout + proc.stderr
            self.assertTrue(
                "python: not found" in combined or "python: command not found" in combined,
                combined,
            )
        finally:
            shutil.rmtree(sandbox.parent, ignore_errors=True)

    def test_run_sh_fails_when_frozen_interpreter_missing(self):
        sandbox = make_sandbox()
        try:
            (sandbox / "native").unlink()
            native = sandbox / "native"
            native.mkdir()
            proc = run_sh(RUN_SH, sandbox)
            self.assertEqual(proc.returncode, 127)
            self.assertIn("frozen native interpreter missing", proc.stderr)
            self.assertIn("uv sync --project native", proc.stderr)
        finally:
            shutil.rmtree(sandbox.parent, ignore_errors=True)


class TestReaderUpgradeManualSequence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sandbox = make_sandbox()
        cls.env = ordinary_env()
        script_lines = list(SETUP_EXPORTS)
        for command in VERBATIM:
            if command.startswith("inkflip compare "):
                script_lines.append(command + "; compare_status=$?")
                script_lines.append("case $compare_status in 0|5) ;; *) exit $compare_status ;; esac")
            else:
                script_lines.append(command)
        cls.proc = run_sh("\n".join(script_lines), cls.sandbox, cls.env)
        cls.setup_error = None
        if cls.proc.returncode not in (0, 5):
            cls.setup_error = (
                f"manual sequence\nexit {cls.proc.returncode}\n{cls.proc.stdout}\n{cls.proc.stderr}"
            )

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.sandbox.parent, ignore_errors=True)

    def setUp(self):
        if getattr(self, "setup_error", None):
            self.fail(self.setup_error)

    def test_example_runs_end_to_end_locally(self):
        assert_example_outputs(self, self.sandbox)
        self.assertIn("checkout with spaces", str(self.sandbox))

    def test_before_after_identities_differ(self):
        assert_named_profile_identities(self, self.sandbox)

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
            f"--out '{out}'"
        )
        proc = run_sh("\n".join(SETUP_EXPORTS + [command]), self.sandbox, self.env)
        self.assertEqual(proc.returncode, 5, proc.stdout + proc.stderr)
        self.assertEqual(hashlib.sha256(baseline.read_bytes()).hexdigest(), before_digest)
        self.assertEqual(baseline.read_bytes(), before_bytes)

    def test_corpus_processing_is_offline_after_install(self):
        env = dict(self.env)
        env.update(
            {
                "http_proxy": "http://127.0.0.1:1",
                "https_proxy": "http://127.0.0.1:1",
                "HTTP_PROXY": "http://127.0.0.1:1",
                "HTTPS_PROXY": "http://127.0.0.1:1",
                "ALL_PROXY": "http://127.0.0.1:1",
            }
        )
        command = (
            "inkflip corpus run --manifest examples/reader-upgrade/corpus.json "
            "--source-root planning/fixtures --profile after --out runs/after-offline"
        )
        proc = run_sh("\n".join(SETUP_EXPORTS + [command]), self.sandbox, env)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertTrue((self.sandbox / "runs" / "after-offline" / "index.json").is_file())


class TestReaderUpgradeRunSh(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sandbox = make_sandbox()
        cls.proc = run_sh(RUN_SH, cls.sandbox)
        cls.setup_error = None
        if cls.proc.returncode not in (0, 5):
            cls.setup_error = (
                f"{RUN_SH}\nexit {cls.proc.returncode}\n{cls.proc.stdout}\n{cls.proc.stderr}"
            )

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.sandbox.parent, ignore_errors=True)

    def setUp(self):
        if getattr(self, "setup_error", None):
            self.fail(self.setup_error)

    def test_run_sh_from_ordinary_shell_with_spaces(self):
        assert_example_outputs(self, self.sandbox)
        assert_named_profile_identities(self, self.sandbox)
        self.assertIn("checkout with spaces", str(self.sandbox))
        html = (self.sandbox / "runs" / "after" / "mapping-control.html").read_text()
        self.assertNotIn("<script", html.lower())


if __name__ == "__main__":
    unittest.main()
