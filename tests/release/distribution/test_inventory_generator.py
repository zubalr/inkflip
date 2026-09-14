"""Inventory-generator honesty tests (release-volume batch).

Each test builds a disposable repository tree in a temporary directory, points
the generator's ROOT at it, and runs the real main(). Three defect classes are
proven closed:

  - the installed-license lookup resolves the *locked* identity: metadata that
    is absent or declares another version is a named failure (exit 1) instead
    of being reported as the locked package or recorded as `license: null`,
    while a declared expression — including npm's legacy `{"type": ...}`
    object form — is recorded verbatim;
  - the digest map accounts for every consumed input (the tracked manifests,
    the notice index, the three release stamps and each bundled package.json),
    sorted and repository-relative, and each digest moves with its bytes;
  - a malformed required tracked input is a named config error (exit 2) with
    no output written, never a silently empty `notice_inventory`, a skipped
    stamp or a crash.

Disposable trees only: no network, no dependency on the real node_modules,
no Docker.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = REPO_ROOT / "scripts" / "distribution" / "build_inventory.py"

_spec = importlib.util.spec_from_file_location("build_inventory", MODULE_PATH)
bi = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bi)

DIGEST = "a" * 64
NODE_SHA = "b" * 64
MODEL_SHA = "c" * 64
DEB_SHA = "d" * 64

PROD_PACKAGES = ("demo-pkg", "pdfjs-dist", "transitive-pkg")


class InventoryGeneratorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self._original_root = bi.ROOT
        bi.ROOT = self.root
        self.addCleanup(self.restore_root)
        self.out = "out"
        self.write_healthy_tree()

    def restore_root(self):
        bi.ROOT = self._original_root

    # ---------- fixture construction ----------

    def write(self, rel: str, content):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content if isinstance(content, bytes) else content.encode())
        return path

    def write_json(self, rel: str, doc) -> Path:
        return self.write(rel, json.dumps(doc, indent=2))

    def installed_path(self, name: str, version: str) -> Path:
        """The bun isolated store shape: node_modules/.bun/<name>@<ver>/…."""
        return (self.root / "node_modules" / ".bun" / f"{name}@{version}"
                / "node_modules" / name / "package.json")

    def store_dir(self, name: str, version: str) -> Path:
        return self.root / "node_modules" / ".bun" / f"{name}@{version}"

    def write_healthy_tree(self):
        """A minimal but complete tree: two locked production packages plus a
        transitive one, one dev-only package, one staged asset, one fixture."""
        self.write_json(
            "bun.lock",
            {
                "lockfileVersion": 1,
                "workspaces": {
                    "": {"devDependencies": {"vitest": "3.1.0"}},
                    "apps/web": {"dependencies": {"demo-pkg": "^1.0.0", "pdfjs-dist": "6.3.289"}},
                },
                "packages": {
                    "demo-pkg": ["demo-pkg@1.0.0", "", {"dependencies": {"transitive-pkg": "^2.0.0"}}, "sha512-DEMO"],
                    "transitive-pkg": ["transitive-pkg@2.0.0", "", {}, "sha512-TRANS"],
                    "pdfjs-dist": ["pdfjs-dist@6.3.289", "", {}, "sha512-PDF"],
                    "vitest": ["vitest@3.1.0", "", {}, "sha512-VITEST"],
                },
            },
        )
        self.write(
            "native/uv.lock",
            '[[package]]\nname = "inkflip"\nversion = "0.0.0"\n\n'
            '[[package]]\nname = "pillow"\nversion = "12.3.0"\n',
        )
        self.write_json("package.json", {"name": "inkflip", "version": "0.0.0", "private": True})
        self.write_json("apps/web/package.json", {"name": "inkflip-web", "version": "0.0.0", "private": True})
        self.write_json(
            "config/resolved-assets.json",
            {
                "schema_version": "1.0.0",
                "staging_root": "apps/web/public",
                "assets": [
                    {
                        "id": "demo-runtime",
                        "kind": "third-party-runtime",
                        "version": "1.0.0",
                        "source": "fixture source",
                        "package": {"name": "demo-pkg", "version": "1.0.0", "integrity": "sha512-DEMO"},
                        "license": "MIT",
                        "rights": "fixture rights",
                        "serve_prefix": "/assets/",
                        "files": [
                            {
                                "package_path": "dist/runtime.js",
                                "staged_path": "assets/demo/runtime.js",
                                "sha256": DIGEST,
                                "bytes": 10,
                            }
                        ],
                    }
                ],
            },
        )
        self.write("apps/web/public/assets/demo/runtime.js", b"demo bytes")
        self.write_json(
            "fixtures/manifest.json",
            {
                "schema_version": "1.0.0",
                "seed": 1,
                "entries": [
                    {
                        "fixture_id": "demo-fixture",
                        "family": "amount",
                        "split": "public",
                        "path": "public/demo.pdf",
                        "bytes": 12,
                        "sha256": DIGEST,
                        "rights": "project fixture",
                    }
                ],
            },
        )
        self.write_json(
            "licenses/notice-index.json",
            {
                "kind": "inkflip-notice-index",
                "schema_version": "1.0.0",
                "recorded": "2026-09-14",
                "entries": [{"id": "inkflip-mit", "path": "LICENSE", "sha256": DIGEST, "bytes": 10}],
            },
        )
        self.write_json(
            "release/node/node.stamp.json",
            {
                "name": "node",
                "version": "22.23.2",
                "purpose": "comparison-bridge runtime",
                "filename": "node-v22.23.2-linux-x64.tar.xz",
                "sha256": NODE_SHA,
            },
        )
        self.write_json(
            "release/models/model.stamp.json",
            {
                "name": "tessdata_fast (eng.traineddata)",
                "sha256": MODEL_SHA,
                "bytes": 4113088,
                "license": "Apache-2.0",
                "source": "fixture source",
            },
        )
        self.write_json(
            "release/tesseract/tesseract.stamp.json",
            {
                "kind": "inkflip-native-tesseract-debs",
                "package": "tesseract-ocr",
                "version": "5.5.0-1+b1",
                "license": "Apache-2.0 (Tesseract)",
                "packages": [{"filename": "libtesseract5_5.5.0-1+b1_amd64.deb", "sha256": DEB_SHA, "bytes": 318308}],
            },
        )
        # Installed distributions: the demo dependency carries a compound
        # expression, the PDF.js pin the legacy object form.
        self.write_json(self.installed_rel("demo-pkg", "1.0.0"),
                        {"name": "demo-pkg", "version": "1.0.0", "license": "Apache-2.0 OR MIT"})
        self.write_json(self.installed_rel("transitive-pkg", "2.0.0"),
                        {"name": "transitive-pkg", "version": "2.0.0", "license": "MIT"})
        self.write_json(self.installed_rel("pdfjs-dist", "6.3.289"),
                        {"name": "pdfjs-dist", "version": "6.3.289",
                         "license": {"type": "MIT", "url": "https://example.invalid/LICENSE"}})

    def installed_rel(self, name: str, version: str) -> str:
        return f"node_modules/.bun/{name}@{version}/node_modules/{name}/package.json"

    def clear_out(self):
        shutil.rmtree(self.root / self.out, ignore_errors=True)

    # ---------- running the generator ----------

    def run_main(self, *argv):
        """Run the real main() against the disposable root (module ROOT
        redirected), returning (exit code, stdout, stderr)."""
        stdout, stderr = io.StringIO(), io.StringIO()
        saved_argv = sys.argv
        sys.argv = ["build_inventory.py", *argv]
        try:
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = bi.main()
        finally:
            sys.argv = saved_argv
        return code, stdout.getvalue(), stderr.getvalue()

    def run_build(self, *extra):
        return self.run_main("--out", self.out, *extra)

    def inventory(self, out: str | None = None) -> dict:
        return json.loads((self.root / (out or self.out) / "inventory.json").read_text())

    def inputs(self, out: str | None = None) -> dict:
        return self.inventory(out)["inputs"]

    def read_doc(self, rel: str) -> dict:
        return json.loads((self.root / rel).read_text())

    def mutate_doc(self, rel: str, **changes):
        doc = self.read_doc(rel)
        doc.update(changes)
        self.write_json(rel, doc)

    def assert_no_traceback(self, err: str):
        self.assertNotIn("Traceback", err, msg=err)

    # ---------- D1: the locked identity decides the license ----------

    def test_missing_installed_metadata_is_a_named_failure(self):
        self.installed_path("demo-pkg", "1.0.0").unlink()
        code, out, err = self.run_build()
        self.assertEqual(code, 1, msg=err)
        self.assertIn("verification failure", err)
        self.assertIn("demo-pkg@1.0.0", err)
        self.assertNotIn("wrote", out)
        self.assertFalse((self.root / self.out / "inventory.json").exists())
        self.assert_no_traceback(err)

    def test_absent_install_names_the_package_and_checked_paths(self):
        shutil.rmtree(self.store_dir("transitive-pkg", "2.0.0"))
        code, _, err = self.run_build()
        self.assertEqual(code, 1, msg=err)
        self.assertIn("transitive-pkg@2.0.0", err)
        self.assertIn("no candidate package.json exists", err)
        self.assert_no_traceback(err)

    def test_installed_version_mismatch_names_expected_and_installed(self):
        self.mutate_doc(self.installed_rel("demo-pkg", "1.0.0"), version="0.9.0")
        code, out, err = self.run_build()
        self.assertEqual(code, 1, msg=err)
        self.assertIn("demo-pkg@1.0.0", err)          # the locked identity
        self.assertIn("0.9.0", err)                   # what is actually installed
        self.assertNotIn("wrote", out)
        self.assertFalse((self.root / self.out / "inventory.json").exists())

    def test_stale_installed_version_is_never_accepted_as_evidence(self):
        """The locked 1.0.0 is gone; only a stale 0.9.0 install remains. It
        must not be reported as the locked package."""
        shutil.rmtree(self.store_dir("demo-pkg", "1.0.0"))
        self.write_json(self.installed_rel("demo-pkg", "0.9.0"),
                        {"name": "demo-pkg", "version": "0.9.0", "license": "MIT"})
        code, _, err = self.run_build()
        self.assertEqual(code, 1, msg=err)
        self.assertIn("demo-pkg@1.0.0", err)
        self.assertIn("demo-pkg@0.9.0", err)
        self.assert_no_traceback(err)

    def test_license_expression_is_recorded_verbatim(self):
        code, _, err = self.run_build()
        self.assertEqual(code, 0, msg=err)
        by_name = {p["name"]: p["license"] for p in self.inventory()["bundled_npm_packages"]}
        # compound SPDX expression kept exactly: not normalized, rewritten or
        # simplified
        self.assertEqual(by_name["demo-pkg"], "Apache-2.0 OR MIT")
        # legacy object form: the declared expression, not a discarded value
        self.assertEqual(by_name["pdfjs-dist"], "MIT")
        self.assertEqual(by_name["transitive-pkg"], "MIT")

    def test_missing_license_field_is_a_named_failure(self):
        doc = self.read_doc(self.installed_rel("demo-pkg", "1.0.0"))
        del doc["license"]
        self.write_json(self.installed_rel("demo-pkg", "1.0.0"), doc)
        code, out, err = self.run_build()
        self.assertEqual(code, 1, msg=err)
        self.assertIn("demo-pkg@1.0.0", err)
        self.assertIn("declares no license expression", err)
        self.assertIn("node_modules/.bun/demo-pkg@1.0.0", err)
        self.assertNotIn("wrote", out)

    def test_license_object_form_without_type_is_a_named_failure(self):
        self.mutate_doc(self.installed_rel("pdfjs-dist", "6.3.289"),
                        license={"url": "https://example.invalid/LICENSE"})
        code, _, err = self.run_build()
        self.assertEqual(code, 1, msg=err)
        self.assertIn("pdfjs-dist@6.3.289", err)
        self.assertIn("declares no license expression", err)
        self.assert_no_traceback(err)

    # ---------- D3: required tracked inputs fail loudly ----------

    def test_malformed_notice_index_is_a_config_error(self):
        self.write("licenses/notice-index.json", "{ this is not json")
        code, out, err = self.run_build()
        self.assertEqual(code, 2, msg=err)
        self.assertIn("config error: licenses/notice-index.json", err)
        self.assertIn("invalid JSON", err)
        self.assertNotIn("wrote", out)
        # no silently empty notice inventory: nothing is emitted at all
        self.assertFalse((self.root / self.out / "inventory.json").exists())
        self.assert_no_traceback(err)

    def test_notice_index_shape_violations_are_named(self):
        cases = [
            ([{"id": "x"}], "root must be a JSON object"),
            ("x", "root must be a JSON object"),
            (None, "root must be a JSON object"),
            ({}, "'entries' must be a list"),
            ({"entries": {}}, "'entries' must be a list"),
            ({"entries": ["nope", 7]}, "entries[0] is malformed (not a JSON object)"),
            ({"entries": [{"id": "x", "path": "LICENSE"}]}, "entries[0] is missing a 64-hex 'sha256' digest"),
            ({"entries": [{"id": "x", "path": "LICENSE", "sha256": "zz" * 32}]},
             "entries[0] is missing a 64-hex 'sha256' digest"),
            ({"entries": [{"id": "", "path": "LICENSE", "sha256": DIGEST}]},
             "entries[0] is missing a non-empty string 'id'"),
            ({"entries": [{"id": "x", "path": "", "sha256": DIGEST}]},
             "entries[0] is missing a non-empty string 'path'"),
        ]
        for doc, needle in cases:
            with self.subTest(doc=doc):
                self.write_healthy_tree()
                self.clear_out()
                self.write_json("licenses/notice-index.json", doc)
                code, out, err = self.run_build()
                self.assertEqual(code, 2, msg=err)
                self.assertIn(f"config error: licenses/notice-index.json", err)
                self.assertIn(needle, err)
                self.assertFalse((self.root / self.out / "inventory.json").exists())
                self.assert_no_traceback(err)

    def test_malformed_stamps_are_named_config_errors(self):
        stamps = (
            "release/node/node.stamp.json",
            "release/models/model.stamp.json",
            "release/tesseract/tesseract.stamp.json",
        )
        for rel in stamps:
            for content, needle in (
                ("{ not json", "invalid JSON"),
                ("[1, 2]", "root must be a JSON object"),
                ('"a string"', "root must be a JSON object"),
                ("null", "root must be a JSON object"),
            ):
                with self.subTest(rel=rel, content=content):
                    self.write_healthy_tree()
                    self.clear_out()
                    self.write(rel, content)
                    code, out, err = self.run_build()
                    self.assertEqual(code, 2, msg=err)
                    self.assertIn(f"config error: {rel}: {needle}", err)
                    self.assertFalse((self.root / self.out / "inventory.json").exists())
                    self.assert_no_traceback(err)

    def test_stamp_without_usable_digest_is_a_named_failure(self):
        cases = [
            ("release/node/node.stamp.json", {}, "missing a 64-hex 'sha256' digest"),
            ("release/node/node.stamp.json", {"sha256": "short"}, "missing a 64-hex 'sha256' digest"),
            ("release/models/model.stamp.json", {"sha256": None}, "missing a 64-hex 'sha256' digest"),
        ]
        for rel, doc, needle in cases:
            with self.subTest(rel=rel, doc=doc):
                self.write_healthy_tree()
                self.clear_out()
                self.write_json(rel, doc)
                code, _, err = self.run_build()
                self.assertEqual(code, 2, msg=err)
                self.assertIn(f"config error: {rel}: {needle}", err)
                self.assertFalse((self.root / self.out / "inventory.json").exists())
                self.assert_no_traceback(err)

    def test_tesseract_closure_shape_violations_are_named(self):
        cases = [
            ({"package": "tesseract-ocr"}, "'packages' must be a list"),
            ({"packages": {}}, "'packages' must be a list"),
            ({"packages": ["nope"]}, "packages[0] is malformed (not a JSON object)"),
            ({"packages": [{"sha256": DEB_SHA}]}, "packages[0] is missing a non-empty string 'filename'"),
            ({"packages": [{"filename": "lib.deb"}]}, "packages[0] is missing a 64-hex 'sha256' digest"),
        ]
        for doc, needle in cases:
            with self.subTest(doc=doc):
                self.write_healthy_tree()
                self.clear_out()
                self.write_json("release/tesseract/tesseract.stamp.json", doc)
                code, _, err = self.run_build()
                self.assertEqual(code, 2, msg=err)
                self.assertIn("config error: release/tesseract/tesseract.stamp.json", err)
                self.assertIn(needle, err)
                self.assert_no_traceback(err)

    def test_missing_required_inputs_are_named_config_errors(self):
        required = (
            "licenses/notice-index.json",
            "release/node/node.stamp.json",
            "release/models/model.stamp.json",
            "release/tesseract/tesseract.stamp.json",
            "config/resolved-assets.json",
            "fixtures/manifest.json",
            "native/uv.lock",
        )
        for rel in required:
            with self.subTest(rel=rel):
                self.write_healthy_tree()
                self.clear_out()
                (self.root / rel).unlink()
                code, out, err = self.run_build()
                self.assertEqual(code, 2, msg=err)
                self.assertIn("config error", err)
                self.assertIn(rel, err)
                self.assertIn("missing", err)
                self.assertFalse((self.root / self.out / "inventory.json").exists())
                self.assert_no_traceback(err)

    # ---------- D2: complete, stable input identity ----------

    def test_inputs_map_accounts_for_every_consumed_input(self):
        code, _, err = self.run_build()
        self.assertEqual(code, 0, msg=err)
        digests = self.inputs()
        for rel in (
            "config/resolved-assets.json",
            "bun.lock",
            "native/uv.lock",
            "fixtures/manifest.json",
            "package.json",
            "apps/web/package.json",
            "licenses/notice-index.json",
            "release/node/node.stamp.json",
            "release/models/model.stamp.json",
            "release/tesseract/tesseract.stamp.json",
        ):
            self.assertIn(rel, digests)
        installed = {k for k in digests if "/node_modules/" in k}
        self.assertEqual(installed, {self.installed_rel(name, version) for name, version in (
            ("demo-pkg", "1.0.0"), ("transitive-pkg", "2.0.0"), ("pdfjs-dist", "6.3.289"),
        )})
        # the dev-only lock entry is not part of the shipped closure
        self.assertNotIn(self.installed_rel("vitest", "3.1.0"), digests)
        # repository-relative keys only, in a stable (sorted) order
        self.assertEqual(list(digests), sorted(digests))
        self.assertFalse([k for k in digests if k.startswith("/")])
        self.assertNotIn(str(self.root), json.dumps(digests))

    def test_each_consumed_input_moves_the_identity(self):
        code, _, err = self.run_build()
        self.assertEqual(code, 0, msg=err)
        baseline = self.inputs()
        installed = self.installed_rel("demo-pkg", "1.0.0")
        mutations = [
            ("licenses/notice-index.json", {"recorded": "2026-09-15"}),
            ("release/node/node.stamp.json", {"purpose": "mutated purpose"}),
            ("release/models/model.stamp.json", {"source": "mutated source"}),
            ("release/tesseract/tesseract.stamp.json", {"note": "mutated note"}),
            ("fixtures/manifest.json", {"seed": 2}),
            (installed, {"description": "mutated description"}),
        ]
        for rel, changes in mutations:
            with self.subTest(rel=rel):
                original = (self.root / rel).read_bytes()
                self.mutate_doc(rel, **changes)
                try:
                    code, _, err = self.run_main("--out", "mutated")
                    self.assertEqual(code, 0, msg=err)
                    after = self.inputs("mutated")
                    self.assertNotEqual(after[rel], baseline[rel], msg=f"{rel} digest did not move")
                    for other in baseline:
                        if other != rel:
                            self.assertEqual(after[other], baseline[other], msg=other)
                finally:
                    (self.root / rel).write_bytes(original)
                    shutil.rmtree(self.root / "mutated", ignore_errors=True)

    def test_two_runs_over_identical_inputs_are_byte_identical(self):
        code, _, err = self.run_build()
        self.assertEqual(code, 0, msg=err)
        first = {p.name: p.read_bytes() for p in (self.root / self.out).iterdir()}
        self.clear_out()
        code, _, err = self.run_build()
        self.assertEqual(code, 0, msg=err)
        second = {p.name: p.read_bytes() for p in (self.root / self.out).iterdir()}
        self.assertEqual(first, second)
        self.assertEqual(list(self.inputs()), sorted(self.inputs()))

    def test_changed_input_changes_identity_and_check_reports_changed(self):
        code, out, err = self.run_build("--surface-doc", "SURFACE.md")
        self.assertEqual(code, 0, msg=err)
        self.assertIn("wrote", out)
        before = (self.root / self.out / "inventory.json").read_bytes()
        surface_before = (self.root / "SURFACE.md").read_bytes()
        serial_before = json.loads((self.root / self.out / "sbom.cdx.json").read_text())["serialNumber"]

        self.mutate_doc("fixtures/manifest.json", seed=2)

        code, out, err = self.run_main("--out", self.out, "--check", "--surface-doc", "SURFACE.md")
        self.assertEqual(code, 1, msg=err)
        self.assertIn("CHANGED", err)
        self.assertNotIn("wrote", out)
        # check mode reports; it never rewrites the differing output
        self.assertEqual((self.root / self.out / "inventory.json").read_bytes(), before)
        self.assertEqual((self.root / "SURFACE.md").read_bytes(), surface_before)

        self.assertEqual(self.run_build()[0], 0)
        serial_after = json.loads((self.root / self.out / "sbom.cdx.json").read_text())["serialNumber"]
        self.assertNotEqual(serial_before, serial_after)

    def test_check_passes_when_outputs_already_match(self):
        self.assertEqual(self.run_build()[0], 0)
        code, _, err = self.run_build("--check")
        self.assertEqual(code, 0, msg=err)
        self.assertNotIn("CHANGED", err)

    # ---------- the positive path ----------

    def test_healthy_tree_writes_a_complete_inventory(self):
        code, out, err = self.run_build()
        self.assertEqual(code, 0, msg=err)
        self.assertIn("wrote", out)
        inventory = self.inventory()
        counts = inventory["counts"]
        self.assertEqual(counts["bundled_npm_packages"], 3)
        self.assertEqual(counts["runtime_stamp_inputs"], 2)
        self.assertEqual(counts["notice_inventory_entries"], 1)
        self.assertEqual(counts["native_deb_packages"], 1)
        self.assertEqual(counts["fixture_entries"], 1)
        self.assertEqual(counts["shipped_asset_files"], 1)
        self.assertEqual(counts["unknown"], 0)
        self.assertEqual([p["name"] for p in inventory["bundled_npm_packages"]],
                         sorted(PROD_PACKAGES))
        self.assertTrue(all(p["license"] for p in inventory["bundled_npm_packages"]))
        self.assertEqual([e["id"] for e in inventory["notice_inventory"]], ["inkflip-mit"])
        self.assertEqual([s["kind"] for s in inventory["runtime_stamp_inputs"]],
                         ["node-runtime", "ocr-model"])

        sbom = json.loads((self.root / self.out / "sbom.cdx.json").read_text())
        self.assertEqual(sbom["bomFormat"], "CycloneDX")
        self.assertEqual(sbom["metadata"]["timestamp"], "2026-09-13T00:00:00Z")
        self.assertEqual({c["name"] for c in sbom["components"]}, set(PROD_PACKAGES) | {"pillow"})


class CheckModeReadOnlyTests(InventoryGeneratorTests):
    """--check must never write: bytes, mtimes and the directory-entry set of
    the whole fixture tree are unchanged on success and on every failure."""

    def tree_state(self) -> dict:
        """{(kind, relative path): (bytes | None, mtime_ns)} under the root."""
        state = {}
        for path in sorted(self.root.rglob("*")):
            rel = path.relative_to(self.root).as_posix()
            if path.is_dir():
                state[("dir", rel)] = (None, path.stat().st_mtime_ns)
            else:
                state[("file", rel)] = (path.read_bytes(), path.stat().st_mtime_ns)
        return state

    def test_check_missing_output_directory_creates_nothing(self):
        before = self.tree_state()
        code, out, err = self.run_build("--check")
        self.assertEqual(code, 1, msg=err)
        self.assertIn("MISSING:", err)
        self.assertIn("inventory.json", err)
        self.assertIn("sbom.cdx.json", err)
        self.assertNotIn("wrote", out)
        # the output directory itself was never created, and no file appeared
        # anywhere else under the fixture root
        self.assertFalse((self.root / self.out).exists())
        self.assertEqual(self.tree_state(), before)

    def test_check_one_missing_output_names_it_and_leaves_the_rest(self):
        self.assertEqual(self.run_build()[0], 0)
        (self.root / self.out / "sbom.cdx.json").unlink()
        inv = self.root / self.out / "inventory.json"
        inv_bytes, inv_mtime = inv.read_bytes(), inv.stat().st_mtime_ns
        code, out, err = self.run_build("--check")
        self.assertEqual(code, 1, msg=err)
        self.assertIn("MISSING:", err)
        self.assertIn("sbom.cdx.json", err)
        self.assertNotIn("CHANGED", err)
        # exactly the absent file is named; the present file draws no failure
        self.assertEqual(err.count("MISSING:"), 1)
        self.assertFalse((self.root / self.out / "sbom.cdx.json").exists())
        self.assertEqual(inv.read_bytes(), inv_bytes)
        self.assertEqual(inv.stat().st_mtime_ns, inv_mtime)

    def test_check_all_matching_outputs_is_read_only(self):
        self.assertEqual(self.run_build()[0], 0)
        before = self.tree_state()
        code, out, err = self.run_build("--check")
        self.assertEqual(code, 0, msg=err)
        self.assertNotIn("wrote", out)
        self.assertNotIn("CHANGED", err)
        self.assertEqual(self.tree_state(), before)

    def test_check_partial_mismatch_leaves_untouched_outputs(self):
        self.assertEqual(self.run_build()[0], 0)
        inv = self.root / self.out / "inventory.json"
        inv.write_text(inv.read_text().replace("inkflip-distribution-inventory", "tampered", 1))
        inv_bytes, inv_mtime = inv.read_bytes(), inv.stat().st_mtime_ns
        sbom = self.root / self.out / "sbom.cdx.json"
        sbom_bytes, sbom_mtime = sbom.read_bytes(), sbom.stat().st_mtime_ns
        code, out, err = self.run_build("--check")
        self.assertEqual(code, 1, msg=err)
        self.assertIn("CHANGED:", err)
        self.assertIn("inventory.json", err)
        self.assertNotIn("sbom.cdx.json", err)
        # the differing file is reported, never rewritten; the matching file
        # is left byte-for-byte and mtime-for-mtime untouched
        self.assertEqual(inv.read_bytes(), inv_bytes)
        self.assertEqual(inv.stat().st_mtime_ns, inv_mtime)
        self.assertEqual(sbom.read_bytes(), sbom_bytes)
        self.assertEqual(sbom.stat().st_mtime_ns, sbom_mtime)

    def test_check_surface_doc_missing_is_named_and_not_created(self):
        self.assertEqual(self.run_build()[0], 0)
        before = self.tree_state()
        code, out, err = self.run_main("--out", self.out, "--check", "--surface-doc", "SURFACE.md")
        self.assertEqual(code, 1, msg=err)
        self.assertIn("MISSING:", err)
        self.assertIn("SURFACE.md", err)
        self.assertFalse((self.root / "SURFACE.md").exists())
        self.assertEqual(self.tree_state(), before)

    def test_check_surface_doc_differing_is_named_and_not_rewritten(self):
        self.assertEqual(self.run_build("--surface-doc", "SURFACE.md")[0], 0)
        surface = self.root / "SURFACE.md"
        surface.write_text(surface.read_text().replace("Distribution surface digest", "TAMPERED", 1))
        before = self.tree_state()
        code, out, err = self.run_main("--out", self.out, "--check", "--surface-doc", "SURFACE.md")
        self.assertEqual(code, 1, msg=err)
        self.assertIn("CHANGED:", err)
        self.assertIn("SURFACE.md", err)
        # the differing doc is reported, never rewritten — and neither is any
        # other output (a check must not repair matching files either)
        self.assertEqual(self.tree_state(), before)

    def test_check_directory_in_place_of_output_is_named_and_untouched(self):
        self.assertEqual(self.run_build()[0], 0)
        inv = self.root / self.out / "inventory.json"
        inv.unlink()
        inv.mkdir()
        marker = inv / "keep.txt"
        marker.write_text("keep")
        sbom = self.root / self.out / "sbom.cdx.json"
        sbom_bytes, sbom_mtime = sbom.read_bytes(), sbom.stat().st_mtime_ns
        code, out, err = self.run_build("--check")
        self.assertEqual(code, 1, msg=err)
        self.assertIn("NOT-A-FILE:", err)
        self.assertIn("inventory.json", err)
        self.assertTrue(marker.exists())
        self.assertEqual(sbom.read_bytes(), sbom_bytes)
        self.assertEqual(sbom.stat().st_mtime_ns, sbom_mtime)

    def test_check_unreadable_output_is_named(self):
        self.assertEqual(self.run_build()[0], 0)
        inv = self.root / self.out / "inventory.json"
        inv.chmod(0o000)
        self.addCleanup(inv.chmod, 0o644)
        code, out, err = self.run_build("--check")
        self.assertEqual(code, 1, msg=err)
        self.assertIn("UNREADABLE:", err)
        self.assertIn("inventory.json", err)


class MalformedWorkspaceTests(InventoryGeneratorTests):
    """The consumed workspace/dependency values are validated before use: a
    malformed shape is a named config error (exit 2, no traceback, no
    partial output); absent, null and empty tables stay valid."""

    def rewrite_workspaces(self, **entries):
        lock = self.read_doc("bun.lock")
        for key, value in entries.items():
            lock["workspaces"][key] = value
        self.write_json("bun.lock", lock)

    def test_malformed_workspace_values_are_named_config_errors(self):
        cases = [
            ({"apps/web": []}, 'bun.lock: workspaces["apps/web"] must be a JSON object'),
            ({"apps/web": "x"}, 'bun.lock: workspaces["apps/web"] must be a JSON object'),
            ({"apps/web": {"dependencies": []}},
             'bun.lock: workspaces["apps/web"].dependencies must be a JSON object'),
            ({"apps/web": {"dependencies": "x"}},
             'bun.lock: workspaces["apps/web"].dependencies must be a JSON object'),
            ({"": {"devDependencies": []}},
             'bun.lock: workspaces[""].devDependencies must be a JSON object'),
        ]
        for entries, needle in cases:
            with self.subTest(entries=entries):
                self.write_healthy_tree()
                self.clear_out()
                self.rewrite_workspaces(**entries)
                code, out, err = self.run_build()
                self.assertEqual(code, 2, msg=err)
                self.assertIn(f"config error: {needle}", err)
                self.assertNotIn("wrote", out)
                # no partial output: nothing was written, not even a directory
                self.assertFalse((self.root / self.out).exists())
                self.assert_no_traceback(err)

    def test_null_or_empty_dependency_tables_stay_valid(self):
        prod = sorted(PROD_PACKAGES)
        cases = [
            ({"apps/web": None}, [], ["vitest"]),
            ({"apps/web": {"dependencies": None}}, [], ["vitest"]),
            ({"apps/web": {"dependencies": {}}}, [], ["vitest"]),
            ({"apps/web": {}}, [], ["vitest"]),
            ({"": {"devDependencies": None}}, prod, []),
            ({"": {}}, prod, []),
        ]
        for entries, bundled, dev in cases:
            with self.subTest(entries=entries):
                self.write_healthy_tree()
                self.clear_out()
                self.rewrite_workspaces(**entries)
                code, out, err = self.run_build()
                self.assertEqual(code, 0, msg=err)
                inv = self.inventory()
                self.assertEqual([p["name"] for p in inv["bundled_npm_packages"]], bundled)
                self.assertEqual(inv["development_only_npm"], dev)


if __name__ == "__main__":
    unittest.main()
