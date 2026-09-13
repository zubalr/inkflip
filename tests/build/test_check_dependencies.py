"""Unit tests for scripts/check_dependencies.py (T02 / TEST-02).

Covers the frozen-state verifiers: JSONC lockfile parsing, manifest/lock
coverage, immutable OCI/action revisions, pin agreement and the live
acceptance path itself.
"""
from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import check_dependencies  # noqa: E402


def reset_state() -> None:
    check_dependencies.FAILURES.clear()
    check_dependencies.CHECKS = 0


def run_quiet(fn) -> None:
    with redirect_stdout(io.StringIO()):
        fn()


class JsoncTests(unittest.TestCase):
    def test_comments_and_trailing_commas_stripped(self):
        text = '{\n  // line comment\n  "a": [1, 2,], /* block */ "b": "x",\n}'
        self.assertEqual(json.loads(check_dependencies.jsonc_to_json(text)),
                         {"a": [1, 2], "b": "x"})

    def test_double_slash_inside_string_preserved(self):
        text = '{"u": "https://example.com//x", "v": "a//b",}'
        self.assertEqual(json.loads(check_dependencies.jsonc_to_json(text)),
                         {"u": "https://example.com//x", "v": "a//b"})

    def test_escaped_quote_inside_string(self):
        text = '{"q": "a\\"b // not a comment",}'
        self.assertEqual(json.loads(check_dependencies.jsonc_to_json(text)),
                         {"q": 'a"b // not a comment'})


class PinTests(unittest.TestCase):
    def test_single_version_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            pin = Path(tmp) / ".node-version"
            pin.write_text("22.23.2\n")
            self.assertEqual(check_dependencies.read_pin(pin), "22.23.2")

    def test_multiline_pin_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            pin = Path(tmp) / ".python-version"
            pin.write_text("3.13.15\n3.13.9\n")
            self.assertIsNone(check_dependencies.read_pin(pin))

    def test_missing_pin(self):
        self.assertIsNone(check_dependencies.read_pin(Path("/nonexistent/.x")))


class BunLockCoverageTests(unittest.TestCase):
    def _workspace(self, tmp: Path, lock_packages: dict, dep_spec: str = "1.2.3"):
        (tmp / "apps/web").mkdir(parents=True)
        (tmp / "apps/web/package.json").write_text(json.dumps({
            "name": "@inkflip/web", "dependencies": {"pdfjs-dist": dep_spec}}))
        (tmp / "package.json").write_text(json.dumps({
            "name": "inkflip", "workspaces": ["apps/*"],
            "trustedDependencies": [], "devDependencies": {}}))
        (tmp / "bunfig.toml").write_text(
            'linker = "isolated"\nexact = true\nminimumReleaseAge = 604800\n')
        (tmp / "bun.lock").write_text(json.dumps({
            "lockfileVersion": 2,
            "workspaces": {"apps/web": {"dependencies": {"pdfjs-dist": dep_spec}}},
            "packages": lock_packages}))

    def test_hashed_entry_passes(self):
        reset_state()
        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            self._workspace(tmp, {"pdfjs-dist": ["pdfjs-dist@1.2.3", "", {}, "sha512-abc="]})
            with mock.patch.object(check_dependencies, "ROOT", tmp):
                run_quiet(check_dependencies.check_bun_lock)
        self.assertFalse(check_dependencies.FAILURES)

    def test_missing_entry_fails(self):
        reset_state()
        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            self._workspace(tmp, {})
            with mock.patch.object(check_dependencies, "ROOT", tmp):
                run_quiet(check_dependencies.check_bun_lock)
        self.assertTrue(any("absent" in f for f in check_dependencies.FAILURES))

    def test_entry_without_integrity_fails(self):
        reset_state()
        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            self._workspace(tmp, {"pdfjs-dist": ["pdfjs-dist@1.2.3", "", {}]})
            with mock.patch.object(check_dependencies, "ROOT", tmp):
                run_quiet(check_dependencies.check_bun_lock)
        self.assertTrue(any("integrity" in f for f in check_dependencies.FAILURES))

    def test_manifest_lock_spec_drift_fails(self):
        reset_state()
        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            self._workspace(tmp, {"pdfjs-dist": ["pdfjs-dist@1.2.3", "", {}, "sha512-abc="]},
                            dep_spec="1.2.3")
            # Drift the lock's recorded spec without touching the manifest.
            lock = json.loads((tmp / "bun.lock").read_text())
            lock["workspaces"]["apps/web"]["dependencies"]["pdfjs-dist"] = "9.9.9"
            (tmp / "bun.lock").write_text(json.dumps(lock))
            with mock.patch.object(check_dependencies, "ROOT", tmp):
                run_quiet(check_dependencies.check_bun_lock)
        self.assertTrue(check_dependencies.FAILURES)


class BaseImageTests(unittest.TestCase):
    def _write(self, tmp: Path, data: dict, workflow: str | None = "x.yml"):
        (tmp / "build").mkdir(parents=True)
        (tmp / "build/base-image.lock.json").write_text(json.dumps(data))
        if workflow:
            wf = tmp / ".github/workflows"
            wf.mkdir(parents=True)
            (wf / workflow).write_text("steps:\n  - uses: actions/checkout@v4\n")

    def _base(self, **overrides) -> dict:
        data = {
            "schema_version": "1.0.0",
            "oci_images": [{
                "ref": "python:3.13.15-slim-trixie",
                "index_digest": "sha256:" + "a" * 64,
                "platform_digests": {"linux/arm64": "sha256:" + "b" * 64},
            }],
            "github_actions": [{
                "uses": "actions/checkout@v4",
                "resolved_sha": "11d5960a326750d5838078e36cf38b85af677262",
            }],
        }
        data.update(overrides)
        return data

    def test_valid_lock_passes(self):
        reset_state()
        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            self._write(tmp, self._base())
            with mock.patch.object(check_dependencies, "ROOT", tmp):
                run_quiet(check_dependencies.check_base_image_lock)
        self.assertFalse(check_dependencies.FAILURES)

    def test_mutable_tag_rejected(self):
        reset_state()
        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            data = self._base()
            data["oci_images"][0]["ref"] = "python:latest"
            data["oci_images"][0]["index_digest"] = "sha256:" + "a" * 64
            self._write(tmp, data)
            with mock.patch.object(check_dependencies, "ROOT", tmp):
                run_quiet(check_dependencies.check_base_image_lock)
        self.assertTrue(any("mutable" in f for f in check_dependencies.FAILURES))

    def test_short_digest_rejected(self):
        reset_state()
        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            data = self._base()
            data["oci_images"][0]["index_digest"] = "sha256:abcd"
            self._write(tmp, data)
            with mock.patch.object(check_dependencies, "ROOT", tmp):
                run_quiet(check_dependencies.check_base_image_lock)
        self.assertTrue(check_dependencies.FAILURES)

    def test_unrecorded_action_fails(self):
        reset_state()
        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            data = self._base(github_actions=[])
            self._write(tmp, data)
            with mock.patch.object(check_dependencies, "ROOT", tmp):
                run_quiet(check_dependencies.check_base_image_lock)
        self.assertTrue(any("checkout" in f for f in check_dependencies.FAILURES))

    def test_tag_pinned_action_rejected(self):
        """A recorded action must resolve to a full 40-hex commit SHA."""
        reset_state()
        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            data = self._base()
            data["github_actions"][0]["resolved_sha"] = "v4"
            self._write(tmp, data)
            with mock.patch.object(check_dependencies, "ROOT", tmp):
                run_quiet(check_dependencies.check_base_image_lock)
        self.assertTrue(check_dependencies.FAILURES)


class NoCdnTests(unittest.TestCase):
    def _mock_manifest(self):
        return mock.patch("prepare_assets.load_manifest", return_value={"schema_version": "1.0.0", "assets": []})

    def test_remote_worker_reference_fails(self):
        reset_state()
        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            (tmp / "apps/web/src").mkdir(parents=True)
            (tmp / "apps/web/src/x.ts").write_text(
                'new Worker("https://cdn.jsdelivr.net/npm/tesseract.js/dist/worker.min.js")')
            with mock.patch.object(check_dependencies, "ROOT", tmp):
                run_quiet(check_dependencies.check_no_runtime_download)
        self.assertTrue(any("no-cdn" in f for f in check_dependencies.FAILURES))

    def test_dynamic_import_fails(self):
        reset_state()
        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            (tmp / "apps/web/src").mkdir(parents=True)
            (tmp / "apps/web/src/loader.ts").write_text('const mod = await import("https://example.com/module.mjs");')
            with mock.patch.object(check_dependencies, "ROOT", tmp), self._mock_manifest():
                run_quiet(check_dependencies.check_no_runtime_download)
        self.assertTrue(any("no-cdn.sources" in f for f in check_dependencies.FAILURES))

    def test_staged_asset_dynamic_import_and_fetch_fail(self):
        reset_state()
        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            (tmp / "apps/web/public/assets").mkdir(parents=True)
            (tmp / "apps/web/public/assets/vendor.js").write_text('import("https://cdn.example.com/plugin.js");')
            with mock.patch.object(check_dependencies, "ROOT", tmp), self._mock_manifest():
                run_quiet(check_dependencies.check_no_runtime_download)
        self.assertTrue(any("no-cdn.sources" in f for f in check_dependencies.FAILURES))

    def test_staged_asset_remote_fetch_fails(self):
        reset_state()
        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            (tmp / "apps/web/public/assets").mkdir(parents=True)
            (tmp / "apps/web/public/assets/fetcher.js").write_text('fetch("https://remote.cdn/data.wasm");')
            with mock.patch.object(check_dependencies, "ROOT", tmp), self._mock_manifest():
                run_quiet(check_dependencies.check_no_runtime_download)
        self.assertTrue(any("no-cdn.sources" in f for f in check_dependencies.FAILURES))

    def test_harmless_comments_and_notices_pass(self):
        reset_state()
        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            (tmp / "apps/web/src").mkdir(parents=True)
            (tmp / "apps/web/public/assets").mkdir(parents=True)
            (tmp / "apps/web/src/safe.ts").write_text(
                '// Upstream: https://cdn.jsdelivr.net/npm/package\n'
                '/* License notice: see https://unpkg.com/browse/foo/LICENSE */\n'
                '// Dynamic import example in comment: import("https://example.com")\n'
                'export const localValue = 42;\n'
            )
            (tmp / "apps/web/public/assets/staged_safe.js").write_text(
                '/*! Bundled from https://unpkg.com/pdfjs-dist under Apache-2.0 */\n'
                '// http://www.apache.org/licenses/LICENSE-2.0\n'
                'console.log("ready");\n'
            )
            with mock.patch.object(check_dependencies, "ROOT", tmp), self._mock_manifest():
                run_quiet(check_dependencies.check_no_runtime_download)
        self.assertFalse([f for f in check_dependencies.FAILURES if "no-cdn.sources" in f])

    def test_same_origin_relative_paths_pass(self):
        reset_state()
        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            (tmp / "apps/web/src").mkdir(parents=True)
            (tmp / "apps/web/public/assets").mkdir(parents=True)
            (tmp / "apps/web/src/app.ts").write_text(
                'const worker = new Worker("/assets/worker.js");\n'
                'const res = await fetch("/assets/model.bin");\n'
                'const mod = await import("./local_feature.js");\n'
            )
            (tmp / "apps/web/public/assets/helper.js").write_text(
                'fetch("/assets/sub.wasm");\n'
            )
            with mock.patch.object(check_dependencies, "ROOT", tmp), self._mock_manifest():
                run_quiet(check_dependencies.check_no_runtime_download)
        self.assertFalse([f for f in check_dependencies.FAILURES if "no-cdn.sources" in f])


class LiveCheckoutTests(unittest.TestCase):
    def test_frozen_acceptance_passes_on_this_checkout(self):
        """The real acceptance command's first segment passes here."""
        reset_state()
        argv = sys.argv
        sys.argv = ["check_dependencies.py", "--frozen"]
        try:
            with redirect_stdout(io.StringIO()) as out:
                code = check_dependencies.main()
        finally:
            sys.argv = argv
        self.assertEqual(code, 0, msg=out.getvalue())

    def test_committed_lock_files_exist(self):
        for path in ("bun.lock", "native/uv.lock", "config/resolved-assets.json",
                     "build/base-image.lock.json", ".node-version", ".python-version"):
            self.assertTrue((ROOT / path).is_file(), f"{path} must be committed")


if __name__ == "__main__":
    unittest.main()
