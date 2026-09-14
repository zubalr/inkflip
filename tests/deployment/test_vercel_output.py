"""Vercel Build Output adapter tests.

The wrangler.json preflight stays in test_static_preflight.py. These cases
cover only the Vercel translation: effective header routes, no SPA fallback,
no Functions, and a file set that matches the production dist minus maps.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import vercel_output as vo  # noqa: E402

CHECKER = REPO_ROOT / "scripts" / "vercel_output.py"
PUBLIC_HEADERS = (REPO_ROOT / "apps/web/public/_headers").read_text()

GOOD_HEADERS = PUBLIC_HEADERS


class Fixture:
    def __init__(self, root: Path):
        self.root = root
        d = root / "apps/web/dist"
        (d / "assets/pdfjs/6.3.289").mkdir(parents=True)
        (d / "assets/pdfjs/6.3.289/LICENSE").write_bytes(b"Apache-2.0")
        (d / "assets/tesseract/7.0.0").mkdir(parents=True)
        (d / "assets/tesseract/7.0.0/LICENSE.md").write_bytes(b"Apache-2.0")
        (d / "assets/tesseract/7.0.0/worker.min.js").write_bytes(b"/* worker */")
        (d / "assets/app-1.js").write_bytes(b"console.log(1)")
        (d / "models/tessdata-fast-eng/x").mkdir(parents=True)
        (d / "models/tessdata-fast-eng/x/eng.traineddata").write_bytes(b"m" * 16)
        (d / "examples").mkdir()
        (d / "examples/index.json").write_bytes(b"{}\n")
        (d / "index.html").write_bytes(b"<!doctype html><title>t</title>")
        (d / "sw.js").write_bytes(b"self.onmessage=e=>{}")
        (d / "release.json").write_bytes(b"{}\n")
        (d / "_headers").write_text(GOOD_HEADERS)
        (d / "assets/app-1.js.map").write_bytes(b'{"version":3}')
        rules = vo.load_header_rules(d / "_headers")
        (root / "vercel.json").write_text(json.dumps(vo.expected_vercel_json(rules), indent=2))

    def dist(self) -> Path:
        return self.root / "apps/web/dist"

    def output(self) -> Path:
        return self.root / ".vercel/output"

    def run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(CHECKER), "--root", str(self.root), *args],
            capture_output=True, text=True, timeout=60,
        )


class TranslationTests(unittest.TestCase):
    def test_committed_vercel_json_matches_public_headers(self):
        rules = vo.load_header_rules(REPO_ROOT / "apps/web/public/_headers")
        actual = json.loads((REPO_ROOT / "vercel.json").read_text())
        self.assertEqual(actual, vo.expected_vercel_json(rules))

    def test_splat_and_exact_paths(self):
        self.assertEqual(vo.cf_pattern_to_src("/*"), "/(.*)")
        self.assertEqual(vo.cf_pattern_to_src("/assets/*"), "/assets/(.*)")
        self.assertEqual(vo.cf_pattern_to_src("/index.html"), r"/index\.html")
        self.assertEqual(vo.cf_pattern_to_vercel_source("/index.html"), "/index.html")
        self.assertEqual(vo.cf_pattern_to_vercel_source("/assets/*"), "/assets/(.*)")

    def test_index_document_gets_a_root_cache_route(self):
        rules = vo.load_header_rules(REPO_ROOT / "apps/web/public/_headers")
        srcs = [r["src"] for r in vo.routes_from_rules(rules)]
        self.assertIn("/", srcs)
        self.assertIn(r"/index\.html", srcs)


class PrepareAndCheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.fx = Fixture(Path(self.tmp.name))

    def test_prepare_and_check_pass(self):
        prep = self.fx.run("prepare")
        self.assertEqual(prep.returncode, 0, prep.stdout + prep.stderr)
        chk = self.fx.run("check")
        self.assertEqual(chk.returncode, 0, chk.stdout + chk.stderr)
        self.assertIn("PASS", chk.stdout)

    def test_source_maps_are_not_uploaded(self):
        self.assertEqual(self.fx.run("prepare").returncode, 0)
        static = self.fx.output() / "static"
        maps = list(static.rglob("*.map"))
        self.assertEqual(maps, [])
        self.assertTrue((static / "assets/app-1.js").is_file())
        self.assertTrue((self.fx.dist() / "assets/app-1.js.map").is_file())

    def test_static_bytes_match_dist(self):
        self.assertEqual(self.fx.run("prepare").returncode, 0)
        worker = "assets/tesseract/7.0.0/worker.min.js"
        expected = hashlib.sha256((self.fx.dist() / worker).read_bytes()).hexdigest()
        actual = hashlib.sha256((self.fx.output() / "static" / worker).read_bytes()).hexdigest()
        self.assertEqual(actual, expected)
        headers = json.loads((self.fx.output() / "config.json").read_text())
        csp = headers["routes"][0]["headers"]["Content-Security-Policy"]
        self.assertIn("default-src 'none'", csp)
        self.assertIn("'wasm-unsafe-eval'", csp)
        self.assertNotIn("'unsafe-eval'", csp.replace("'wasm-unsafe-eval'", ""))
        self.assertTrue(all(r.get("continue") is True for r in headers["routes"]))
        self.assertTrue(all("dest" not in r for r in headers["routes"]))

    def test_headers_text_file_alone_is_not_enough(self):
        self.assertEqual(self.fx.run("prepare").returncode, 0)
        config_path = self.fx.output() / "config.json"
        config_path.write_text(json.dumps({"version": 3, "routes": []}) + "\n")
        chk = self.fx.run("check")
        self.assertEqual(chk.returncode, 1, chk.stdout)
        self.assertIn("_headers was not translated", chk.stdout)
        self.assertTrue((self.fx.output() / "static" / "_headers").is_file())

    def test_spa_fallback_is_rejected(self):
        self.assertEqual(self.fx.run("prepare").returncode, 0)
        config_path = self.fx.output() / "config.json"
        config = json.loads(config_path.read_text())
        config["routes"].append({"src": "/(.*)", "dest": "/index.html"})
        config_path.write_text(json.dumps(config) + "\n")
        chk = self.fx.run("check")
        self.assertNotEqual(chk.returncode, 0, chk.stdout)
        self.assertIn("SPA fallback", chk.stdout)

    def test_functions_directory_is_rejected(self):
        self.assertEqual(self.fx.run("prepare").returncode, 0)
        func = self.fx.output() / "functions" / "api.func"
        func.mkdir(parents=True)
        (func / ".vc-config.json").write_text("{}")
        chk = self.fx.run("check")
        self.assertEqual(chk.returncode, 2, chk.stdout)
        self.assertIn("functions", chk.stdout)

    def test_images_and_crons_are_rejected(self):
        self.assertEqual(self.fx.run("prepare").returncode, 0)
        config_path = self.fx.output() / "config.json"
        config = json.loads(config_path.read_text())
        config["images"] = {"sizes": [640], "domains": []}
        config["crons"] = [{"path": "/api", "schedule": "* * * * *"}]
        config_path.write_text(json.dumps(config) + "\n")
        chk = self.fx.run("check")
        self.assertNotEqual(chk.returncode, 0, chk.stdout)
        self.assertIn("images", chk.stdout)
        self.assertIn("crons", chk.stdout)

    def test_missing_worker_is_an_identity_error(self):
        self.assertEqual(self.fx.run("prepare").returncode, 0)
        worker = self.fx.output() / "static/assets/tesseract/7.0.0/worker.min.js"
        worker.unlink()
        chk = self.fx.run("check")
        self.assertEqual(chk.returncode, 1, chk.stdout)
        self.assertIn("missing dist file", chk.stdout)

    def test_vercel_json_next_framework_is_rejected(self):
        (self.fx.root / "vercel.json").write_text(json.dumps({
            "framework": "nextjs",
            "buildCommand": "next build",
            "outputDirectory": ".next",
        }))
        self.assertEqual(self.fx.run("prepare").returncode, 0)
        chk = self.fx.run("check")
        self.assertNotEqual(chk.returncode, 0, chk.stdout)
        self.assertIn("framework must be null", chk.stdout)
        self.assertIn("buildCommand must be null", chk.stdout)

    def test_header_continue_required(self):
        self.assertEqual(self.fx.run("prepare").returncode, 0)
        config_path = self.fx.output() / "config.json"
        config = json.loads(config_path.read_text())
        config["routes"][0].pop("continue")
        config_path.write_text(json.dumps(config) + "\n")
        chk = self.fx.run("check")
        self.assertNotEqual(chk.returncode, 0, chk.stdout)
        self.assertIn("continue=true", chk.stdout)

    def test_prepare_replaces_previous_output_only(self):
        link = self.fx.root / ".vercel"
        link.mkdir()
        (link / "project.json").write_text('{"projectId":"prj_test"}')
        first = self.fx.run("prepare")
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        stale = self.fx.output() / "static" / "stale.txt"
        stale.write_text("nope")
        second = self.fx.run("prepare")
        self.assertEqual(second.returncode, 0, second.stdout)
        self.assertFalse(stale.exists())
        self.assertEqual((link / "project.json").read_text(), '{"projectId":"prj_test"}')

    def test_check_without_prepare_is_config_error(self):
        chk = self.fx.run("check")
        self.assertEqual(chk.returncode, 2, chk.stdout)
        self.assertIn("run prepare first", chk.stdout)


class RealDistTests(unittest.TestCase):
    def test_real_dist_prepare_check_when_built(self):
        if not (REPO_ROOT / "apps/web/dist/index.html").is_file():
            self.skipTest("apps/web/dist not built; run bun run build first")
        output = REPO_ROOT / ".vercel" / "output"
        if output.exists():
            shutil.rmtree(output)
        prep = subprocess.run(
            [sys.executable, str(CHECKER), "prepare", "--root", str(REPO_ROOT)],
            capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(prep.returncode, 0, prep.stdout + prep.stderr)
        chk = subprocess.run(
            [sys.executable, str(CHECKER), "check", "--root", str(REPO_ROOT)],
            capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(chk.returncode, 0, chk.stdout + chk.stderr)


if __name__ == "__main__":
    unittest.main()
