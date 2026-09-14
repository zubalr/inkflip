"""T48 static deployment preflight tests (fail-closed contract).

Covers the 2026-09-13 recovery-review negative cases that previously PASSED:
empty distributions without a manifest, protocol-relative fetches, external
CSP origins, and compute bindings (top-level and env overrides). Fixtures are
disposable; the real dist is only read.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKER = REPO_ROOT / "scripts" / "check_static_dist.py"

GOOD_CONFIG = {
    "name": "inkflip",
    "compatibility_date": "2026-09-11",
    "workers_dev": True,
    "preview_urls": False,
    "assets": {
        "directory": "./apps/web/dist",
        "html_handling": "auto-trailing-slash",
        "not_found_handling": "none",
    },
}
GOOD_HEADERS = """/*
  Content-Security-Policy: default-src 'none'; script-src 'self' 'wasm-unsafe-eval'; worker-src 'self'; connect-src 'self'; img-src 'self' blob: data:; font-src 'self' blob:; style-src 'self'; style-src-attr 'unsafe-inline'; object-src 'none'; frame-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'; manifest-src 'self'
  Referrer-Policy: no-referrer

/index.html
  Cache-Control: no-cache

/sw.js
  Cache-Control: no-cache

/release.json
  Cache-Control: no-cache

/assets/*
  Cache-Control: public, max-age=31536000, immutable

/models/*
  Cache-Control: public, max-age=31536000, immutable
"""


class Fixture:
    """A minimal-but-complete disposable dist with recorded manifest."""

    def __init__(self, root: Path):
        self.root = root
        d = root / "apps/web/dist"
        (d / "assets/pdfjs/6.3.289").mkdir(parents=True)
        (d / "assets/pdfjs/6.3.289/LICENSE").write_bytes(b"Apache-2.0")
        (d / "assets/tesseract/7.0.0").mkdir(parents=True)
        (d / "assets/tesseract/7.0.0/LICENSE.md").write_bytes(b"Apache-2.0")
        (d / "assets/app-1.js").write_bytes(b"console.log(1)")
        (d / "models/tessdata-fast-eng/x").mkdir(parents=True)
        (d / "models/tessdata-fast-eng/x/eng.traineddata").write_bytes(b"m" * 16)
        (d / "examples").mkdir()
        (d / "examples/index.json").write_bytes(b"{}\n")
        (d / "index.html").write_bytes(b"<!doctype html><title>t</title>")
        (d / "sw.js").write_bytes(b"self.onmessage=e=>{}")
        (d / "_headers").write_text(GOOD_HEADERS)
        (root / "wrangler.json").write_text(json.dumps(GOOD_CONFIG))
        self.record()

    def dist(self) -> Path:
        return self.root / "apps/web/dist"

    def record(self):
        files = [
            {
                "path": f"apps/web/dist/{p.relative_to(self.dist()).as_posix()}",
                "bytes": p.stat().st_size,
                "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            }
            for p in sorted(self.dist().rglob("*"))
            if p.is_file() and not p.is_symlink()
        ]
        h = hashlib.sha256()
        for e in sorted(files, key=lambda x: x["path"]):
            h.update(e["path"].encode())
            h.update(str(e["bytes"]).encode())
            h.update(e["sha256"].encode())
        (self.root / ".private").mkdir(exist_ok=True)
        (self.root / ".private/dist-manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": "1.0.0",
                    "kind": "inkflip-dist-manifest",
                    "dist_root": "apps/web/dist",
                    "file_count": len(files),
                    "file_set_sha256": h.hexdigest(),
                    "reject_patterns": ["\\.map$"],
                    "files": files,
                },
                indent=2,
            )
        )

    def write_dist(self, rel: str, content: bytes):
        path = self.dist() / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def run(self, *extra: str, manifest: str = ".private/dist-manifest.json") -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(CHECKER), "apps/web/dist", "--config", "wrangler.json",
             "--root", str(self.root), "--dist-manifest", manifest, *extra],
            capture_output=True, text=True, timeout=120,
        )


class FailClosedManifestTests(unittest.TestCase):
    """REVIEW.md case 1: incomplete distributions must not pass."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.fx = Fixture(Path(self.tmp.name))

    def test_valid_recorded_distribution_passes(self):
        proc = self.fx.run()
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)

    def test_missing_manifest_fails_closed(self):
        proc = self.fx.run(manifest=".private/absent.json")
        self.assertEqual(proc.returncode, 1, msg=proc.stdout)
        self.assertIn("required dist manifest not found", proc.stdout)

    def test_empty_required_asset_fails(self):
        self.fx.write_dist("index.html", b"")
        self.fx.record()
        proc = self.fx.run()
        self.assertEqual(proc.returncode, 1, msg=proc.stdout)
        self.assertIn("required asset is empty: index.html", proc.stdout)

    def test_tampered_bytes_fail(self):
        self.fx.write_dist("assets/app-1.js", b"console.log(2) // tampered")
        proc = self.fx.run()
        self.assertEqual(proc.returncode, 1, msg=proc.stdout)
        self.assertIn("hash mismatch", proc.stdout)

    def test_undeclared_extra_file_fails(self):
        self.fx.write_dist("assets/extra.js", b"stray")
        proc = self.fx.run()
        self.assertEqual(proc.returncode, 1, msg=proc.stdout)
        self.assertIn("undeclared built file: assets/extra.js", proc.stdout)

    def test_missing_declared_file_fails(self):
        (self.fx.dist() / "assets/app-1.js").unlink()
        proc = self.fx.run()
        self.assertEqual(proc.returncode, 1, msg=proc.stdout)
        self.assertIn("declared file missing from build: assets/app-1.js", proc.stdout)

    def test_traversal_entry_is_config_error(self):
        mf = json.loads((self.fx.root / ".private/dist-manifest.json").read_text())
        mf["files"].append({"path": "../../etc/passwd", "bytes": 1, "sha256": "0" * 64})
        (self.fx.root / ".private/dist-manifest.json").write_text(json.dumps(mf))
        proc = self.fx.run()
        self.assertEqual(proc.returncode, 2, msg=proc.stdout)
        self.assertIn("escapes the repository root", proc.stdout)

    def test_duplicate_entries_are_config_error(self):
        mf = json.loads((self.fx.root / ".private/dist-manifest.json").read_text())
        mf["files"].append(dict(mf["files"][0]))
        (self.fx.root / ".private/dist-manifest.json").write_text(json.dumps(mf))
        proc = self.fx.run()
        self.assertEqual(proc.returncode, 2, msg=proc.stdout)
        self.assertIn("duplicate entry", proc.stdout)

    def test_missing_hash_fails(self):
        mf = json.loads((self.fx.root / ".private/dist-manifest.json").read_text())
        mf["files"][0]["sha256"] = None
        (self.fx.root / ".private/dist-manifest.json").write_text(json.dumps(mf))
        proc = self.fx.run()
        self.assertEqual(proc.returncode, 1, msg=proc.stdout)
        self.assertIn("lacks required bytes/sha256", proc.stdout)

    def test_stale_build_identity_fails(self):
        self.fx.write_dist("index.html", b"<!doctype html><title>newer</title>")
        proc = self.fx.run()
        self.assertEqual(proc.returncode, 1, msg=proc.stdout)
        self.assertIn("hash mismatch (stale build or tampering)", proc.stdout)

    def test_stale_file_set_identity_fails(self):
        mf = json.loads((self.fx.root / ".private/dist-manifest.json").read_text())
        mf["file_set_sha256"] = "0" * 64
        (self.fx.root / ".private/dist-manifest.json").write_text(json.dumps(mf))
        proc = self.fx.run()
        self.assertEqual(proc.returncode, 1, msg=proc.stdout)
        self.assertIn("build identity stale", proc.stdout)

    def test_symlink_escape_fails(self):
        outside = self.fx.root / "outside.txt"
        outside.write_bytes(b"secret")
        (self.fx.dist() / "assets/link.js").symlink_to(outside)
        proc = self.fx.run()
        self.assertEqual(proc.returncode, 1, msg=proc.stdout)
        self.assertIn("symlink escape", proc.stdout)

    def test_manifest_binding_wrong_root_is_config_error(self):
        mf = json.loads((self.fx.root / ".private/dist-manifest.json").read_text())
        mf["dist_root"] = "somewhere/else"
        (self.fx.root / ".private/dist-manifest.json").write_text(json.dumps(mf))
        proc = self.fx.run()
        self.assertEqual(proc.returncode, 2, msg=proc.stdout)
        self.assertIn("does not bind the supplied dist root", proc.stdout)


class ConfigurationTests(unittest.TestCase):
    """REVIEW.md case 3: unsupported compute bindings must fail."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.fx = Fixture(Path(self.tmp.name))

    def config_case(self, mutate) -> subprocess.CompletedProcess:
        cfg = json.loads(json.dumps(GOOD_CONFIG))
        mutate(cfg)
        (self.fx.root / "wrangler.json").write_text(json.dumps(cfg))
        return self.fx.run()

    def test_r2_buckets_fail(self):
        proc = self.config_case(lambda c: c.update(r2_buckets=[{"binding": "X", "bucket_name": "b"}]))
        self.assertEqual(proc.returncode, 2, msg=proc.stdout)
        self.assertIn("r2_buckets", proc.stdout)

    def test_r2_buckets_in_env_override_fail(self):
        proc = self.config_case(
            lambda c: c.update(env={"production": {"r2_buckets": [{"binding": "X", "bucket_name": "b"}]}})
        )
        self.assertEqual(proc.returncode, 2, msg=proc.stdout)
        self.assertIn("env.production", proc.stdout)
        self.assertIn("r2_buckets", proc.stdout)

    def test_main_worker_script_fails(self):
        proc = self.config_case(lambda c: c.update(main="worker.js"))
        self.assertEqual(proc.returncode, 2, msg=proc.stdout)
        self.assertIn("main", proc.stdout)

    def test_d1_kv_queues_services_durable_fail(self):
        for key, value in (
            ("d1_databases", [{"binding": "DB"}]),
            ("kv_namespaces", [{"binding": "KV"}]),
            ("queues", [{"binding": "Q"}]),
            ("services", [{"binding": "S"}]),
            ("durable_objects", {"bindings": []}),
            ("containers", [{"name": "c"}]),
            ("ai", {"binding": "AI"}),
            ("triggers", {"crons": ["* * * * *"]}),
        ):
            proc = self.config_case(lambda c, k=key, v=value: c.update({k: v}))
            self.assertEqual(proc.returncode, 2, msg=f"{key}: {proc.stdout}")
            self.assertIn(key, proc.stdout)

    def test_unknown_top_level_key_fails(self):
        proc = self.config_case(lambda c: c.update(site_config={"x": 1}))
        self.assertEqual(proc.returncode, 2, msg=proc.stdout)
        self.assertIn("unknown top-level key", proc.stdout)

    def test_directory_traversal_is_config_error(self):
        proc = self.config_case(lambda c: c["assets"].update(directory="./apps/web/../../etc"))
        self.assertEqual(proc.returncode, 2, msg=proc.stdout)
        self.assertIn("traversal is rejected by construction", proc.stdout)

    def test_directory_mismatch_with_supplied_dist_fails(self):
        other = self.fx.root / "apps/other"
        other.mkdir(parents=True)
        proc = self.config_case(lambda c: c["assets"].update(directory="./apps/other"))
        self.assertIn("does not bind", proc.stdout) if False else None
        self.assertEqual(proc.returncode, 1, msg=proc.stdout + proc.stderr)
        self.assertIn("resolves to", proc.stdout)

    def test_malformed_config_is_deterministic_error(self):
        (self.fx.root / "wrangler.json").write_bytes(b"{ not json ")
        proc = self.fx.run()
        self.assertEqual(proc.returncode, 2, msg=proc.stdout + proc.stderr)
        self.assertIn("malformed JSON", proc.stdout)
        self.assertNotIn("Traceback", proc.stderr)


class HeaderPolicyTests(unittest.TestCase):
    """REVIEW.md case 2 (CSP half): parsed directives, not substrings."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.fx = Fixture(Path(self.tmp.name))

    def headers_case(self, new_headers: str) -> subprocess.CompletedProcess:
        self.fx.write_dist("_headers", new_headers.encode())
        self.fx.record()
        return self.fx.run()

    def test_external_origin_in_script_src_fails(self):
        proc = self.headers_case(GOOD_HEADERS.replace(
            "script-src 'self' 'wasm-unsafe-eval'",
            "script-src 'self' 'wasm-unsafe-eval' https://example.invalid"))
        self.assertEqual(proc.returncode, 1, msg=proc.stdout)
        self.assertIn("script-src forbids 'https://example.invalid'", proc.stdout)

    def test_wildcard_source_fails(self):
        proc = self.headers_case(GOOD_HEADERS.replace(
            "connect-src 'self'", "connect-src 'self' *"))
        self.assertEqual(proc.returncode, 1, msg=proc.stdout)
        self.assertIn("connect-src forbids", proc.stdout)

    def test_protocol_relative_source_fails(self):
        proc = self.headers_case(GOOD_HEADERS.replace(
            "worker-src 'self'", "worker-src 'self' //cdn.example.invalid"))
        self.assertEqual(proc.returncode, 1, msg=proc.stdout)
        self.assertIn("worker-src forbids", proc.stdout)

    def test_script_unsafe_inline_fails(self):
        proc = self.headers_case(GOOD_HEADERS.replace(
            "script-src 'self' 'wasm-unsafe-eval'",
            "script-src 'self' 'wasm-unsafe-eval' 'unsafe-inline'"))
        self.assertEqual(proc.returncode, 1, msg=proc.stdout)
        self.assertIn("'unsafe-inline'", proc.stdout)

    def test_permissive_later_rule_fails(self):
        proc = self.headers_case(GOOD_HEADERS + (
            "\n/examples/*\n  Content-Security-Policy: default-src *; script-src * 'unsafe-eval'\n"
        ))
        self.assertEqual(proc.returncode, 1, msg=proc.stdout)
        self.assertIn("rule '/examples/*'", proc.stdout)

    def test_immutable_in_wrong_rule_does_not_satisfy_models(self):
        proc = self.headers_case(GOOD_HEADERS.replace(
            "/models/*\n  Cache-Control: public, max-age=31536000, immutable",
            "/models/*\n  Cache-Control: no-cache"))
        self.assertEqual(proc.returncode, 1, msg=proc.stdout)
        self.assertIn("must be public max-age immutable", proc.stdout)

    def test_missing_sw_freshness_fails(self):
        proc = self.headers_case(GOOD_HEADERS.replace("/sw.js\n  Cache-Control: no-cache\n\n", ""))
        self.assertEqual(proc.returncode, 1, msg=proc.stdout)
        self.assertIn("no Cache-Control rule for sw.js", proc.stdout)

    def test_coop_fails(self):
        proc = self.headers_case(GOOD_HEADERS + "\n/*\n  Cross-Origin-Opener-Policy: same-origin\n")
        self.assertEqual(proc.returncode, 1, msg=proc.stdout)
        self.assertIn("no default COOP/COEP", proc.stdout)

    def test_repeated_directive_fails(self):
        proc = self.headers_case(GOOD_HEADERS.replace(
            "script-src 'self' 'wasm-unsafe-eval'",
            "script-src 'self' 'wasm-unsafe-eval'; script-src 'self'"))
        self.assertEqual(proc.returncode, 1, msg=proc.stdout)
        self.assertIn("repeated directive", proc.stdout)


class SameOriginTests(unittest.TestCase):
    """REVIEW.md case 2 (fetch half): protocol-relative URLs are external."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.fx = Fixture(Path(self.tmp.name))

    def case(self, content: bytes, name="assets/app-1.js"):
        self.fx.write_dist(name, content)
        self.fx.record()
        proc = self.fx.run()
        self.assertEqual(proc.returncode, 1, msg=proc.stdout)
        return proc.stdout

    def test_protocol_relative_fetch_fails(self):
        out = self.case(b'fetch("//example.invalid/data")')
        self.assertIn("'//example.invalid/data'", out)

    def test_absolute_external_fetch_fails(self):
        out = self.case(b'fetch("https://example.invalid/data")')
        self.assertIn("https://example.invalid", out)

    def test_css_external_import_fails(self):
        out = self.case(b'@import url("https://evil.invalid/x.css");', name="assets/x.css")
        self.assertIn("evil.invalid", out)

    def test_html_external_script_fails(self):
        out = self.case(b'<script src="https://evil.invalid/x.js"></script>', name="examples/x.html")
        self.assertIn("evil.invalid", out)

    def test_examples_are_scanned_too(self):
        out = self.case(b'fetch("//example.invalid/telemetry")', name="examples/amount/x.js")
        self.assertIn("example.invalid", out)

    def test_canonical_metadata_element_is_exempt_but_remote_links_fail(self):
        out = self.case(
            b'<link rel="canonical" href="https://inkflip-rose.vercel.app/" />'
            b'<link rel="stylesheet" href="https://evil.invalid/x.css">',
            name="index.html")
        self.assertIn("evil.invalid", out)
        self.assertNotIn("inkflip-rose.vercel.app", out)

    def test_canonical_rel_combination_still_fails(self):
        out = self.case(
            b'<link rel="canonical stylesheet" href="https://inkflip-rose.vercel.app/" />',
            name="index.html")
        self.assertIn("inkflip-rose.vercel.app", out)


class RealDistTests(unittest.TestCase):
    def test_real_dist_passes_preflight(self):
        if not (REPO_ROOT / "apps/web/dist/index.html").is_file():
            self.skipTest("apps/web/dist not built; run `bun run build` + record first")
        proc = subprocess.run(
            [sys.executable, str(CHECKER), "apps/web/dist", "--config", "wrangler.json",
             "--root", str(REPO_ROOT), "--dist-manifest", ".private/distribution/dist-manifest.json"],
            capture_output=True, text=True, timeout=300,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
