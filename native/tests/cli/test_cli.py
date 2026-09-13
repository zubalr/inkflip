"""T30 native CLI tests (TEST-30), including independent-review regressions."""
from __future__ import annotations

import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
NATIVE = ROOT / "native"
FIXTURES = ROOT / "fixtures"
if str(NATIVE) not in sys.path:
    sys.path.insert(0, str(NATIVE))

from inkflip.cli.main import (  # noqa: E402
    EXIT_CANCELLED,
    EXIT_INCOMPARABLE,
    EXIT_INVALID_ARGS,
    EXIT_OK,
    EXIT_PARTIAL_RUN,
    EXIT_READ_FAILURE,
    main,
)
from inkflip.contracts import core  # noqa: E402


def _pdf(name: str = "mapping-amount.pdf") -> Path:
    return FIXTURES / "public" / name


def _two_page_pdf(directory: Path) -> Path:
    from pypdf import PdfWriter

    writer = PdfWriter()
    for _ in range(2):
        writer.add_blank_page(width=200, height=200)
    path = directory / "two-page.pdf"
    writer.write(path)
    # Ensure %PDF header and enough bytes for inspect.
    data = path.read_bytes()
    if not data.startswith(b"%PDF"):
        raise AssertionError("expected a PDF")
    return path


class TestCliReadersList(unittest.TestCase):
    def test_readers_list_json(self):
        buf = io.StringIO()
        with mock.patch("sys.stdout", buf):
            code = main(["readers", "list", "--json"])
        self.assertEqual(code, EXIT_OK)
        data = json.loads(buf.getvalue())
        ids = [item["reader"]["id"] for item in data["readers"]]
        self.assertIn("pdfium-native", ids)
        self.assertIn("pypdf-native", ids)
        self.assertIn("tesseract-native", ids)


class TestCliInspect(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.td = Path(self.tmp.name)
        self.pdf = _pdf()

    def tearDown(self):
        self.tmp.cleanup()

    def test_inspect_default_pdfium_validates(self):
        out = self.td / "out.inkflip.json"
        code = main(["inspect", str(self.pdf), "--out", str(out)])
        self.assertEqual(code, EXIT_OK)
        data = json.loads(out.read_text())
        core.validate(data)
        self.assertEqual(data["readers"][0]["id"], "pdfium-native")
        self.assertGreaterEqual(len(data["occurrences"]), 1)

    def test_inspect_pypdf(self):
        out = self.td / "pypdf.inkflip.json"
        code = main(["inspect", str(self.pdf), "--out", str(out), "--reader", "pypdf"])
        self.assertEqual(code, EXIT_OK)
        data = json.loads(out.read_text())
        core.validate(data)
        self.assertEqual(data["readers"][0]["id"], "pypdf-native")

    def test_refuses_source_alias_even_with_replace(self):
        code = main(
            ["inspect", str(self.pdf), "--out", str(self.pdf), "--replace-output"]
        )
        self.assertEqual(code, EXIT_INVALID_ARGS)
        self.assertTrue(self.pdf.read_bytes().startswith(b"%PDF"))

    def test_refuses_symlink_alias(self):
        link = self.td / "alias.pdf"
        os.symlink(self.pdf, link)
        code = main(["inspect", str(self.pdf), "--out", str(link), "--replace-output"])
        self.assertEqual(code, EXIT_INVALID_ARGS)

    def test_refuses_hardlink_alias(self):
        hard = self.td / "hard.pdf"
        os.link(self.pdf, hard)
        code = main(["inspect", str(self.pdf), "--out", str(hard), "--replace-output"])
        self.assertEqual(code, EXIT_INVALID_ARGS)

    def test_refuses_overwrite_without_flag(self):
        out = self.td / "existing.json"
        out.write_text("{}", encoding="utf-8")
        code = main(["inspect", str(self.pdf), "--out", str(out)])
        self.assertEqual(code, EXIT_INVALID_ARGS)

    def test_refuses_url(self):
        code = main(["inspect", "https://example.com/x.pdf", "--out", str(self.td / "o.json")])
        self.assertEqual(code, EXIT_INVALID_ARGS)

    def test_unknown_reader(self):
        code = main(
            ["inspect", str(self.pdf), "--out", str(self.td / "o.json"), "--reader", "evil"]
        )
        self.assertEqual(code, EXIT_INVALID_ARGS)

    def test_missing_profile_fails_closed(self):
        code = main(
            [
                "inspect",
                str(self.pdf),
                "--out",
                str(self.td / "o.json"),
                "--profile",
                "before",
            ]
        )
        self.assertEqual(code, EXIT_INVALID_ARGS)

    def test_untrusted_profile_path_refused(self):
        code = main(
            [
                "inspect",
                str(self.pdf),
                "--out",
                str(self.td / "o.json"),
                "--profile",
                "/tmp/custom.json",
            ]
        )
        self.assertEqual(code, EXIT_INVALID_ARGS)

    def test_region_is_recorded_and_filters(self):
        out = self.td / "region.inkflip.json"
        code = main(
            [
                "inspect",
                str(self.pdf),
                "--out",
                str(out),
                "--pages",
                "1",
                "--region",
                "0,0,1,1",
            ]
        )
        self.assertEqual(code, EXIT_OK)
        data = json.loads(out.read_text())
        core.validate(data)
        self.assertEqual(len(data["plan"]["regions"]), 1)
        self.assertLess(len(data["occurrences"]), 20)

    def test_multipage_distinct_transforms(self):
        pdf = _two_page_pdf(self.td)
        out = self.td / "multi.inkflip.json"
        code = main(["inspect", str(pdf), "--out", str(out), "--pages", "all"])
        self.assertEqual(code, EXIT_OK, msg="multipage inspect must not emit duplicate transform ids")
        data = json.loads(out.read_text())
        core.validate(data)
        ids = [item["id"] for item in data["transforms"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(data["pages"]), 2)

    def test_path_with_spaces(self):
        spaced = self.td / "dir with spaces"
        spaced.mkdir()
        target = spaced / "doc with spaces.pdf"
        target.write_bytes(self.pdf.read_bytes())
        out = spaced / "out.inkflip.json"
        code = main(["inspect", str(target), "--out", str(out)])
        self.assertEqual(code, EXIT_OK)
        core.validate(json.loads(out.read_text()))

    def test_missing_file_exit_4(self):
        code = main(["inspect", str(self.td / "nope.pdf"), "--out", str(self.td / "o.json")])
        self.assertEqual(code, EXIT_READ_FAILURE)


class TestValidateAndReport(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.td = Path(self.tmp.name)
        self.report = self.td / "r.inkflip.json"
        code = main(["inspect", str(_pdf()), "--out", str(self.report)])
        self.assertEqual(code, EXIT_OK)

    def tearDown(self):
        self.tmp.cleanup()

    def test_validate_ok(self):
        self.assertEqual(main(["validate", str(self.report)]), EXIT_OK)

    def test_html_uses_full_validation(self):
        data = json.loads(self.report.read_text())
        data["forbidden_extra"] = True
        bad = self.td / "bad.inkflip.json"
        bad.write_text(json.dumps(data))
        html = self.td / "out.html"
        self.assertEqual(main(["validate", str(bad)]), EXIT_INVALID_ARGS)
        self.assertEqual(
            main(["report", str(bad), "--format", "html", "--out", str(html)]),
            EXIT_INVALID_ARGS,
        )

    def test_report_html(self):
        html = self.td / "out.html"
        self.assertEqual(main(["report", str(self.report), "--format", "html", "--out", str(html)]), EXIT_OK)
        text = html.read_text()
        self.assertIn("Content-Security-Policy", text)
        self.assertNotIn("<script", text.lower())


class TestReplay(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.td = Path(self.tmp.name)
        self.pdf = _pdf()
        self.report = self.td / "r.inkflip.json"
        code = main(
            ["inspect", str(self.pdf), "--out", str(self.report), "--embed-source", "--reader", "pdfium"]
        )
        self.assertEqual(code, EXIT_OK)

    def tearDown(self):
        self.tmp.cleanup()

    def test_replay_ok(self):
        out = self.td / "replay.inkflip.json"
        code = main(
            ["replay", str(self.report), "--source", str(self.pdf), "--profile", "native-default", "--out", str(out)]
        )
        self.assertEqual(code, EXIT_OK)
        core.validate(json.loads(out.read_text()))

    def test_replay_hash_mismatch(self):
        other = _pdf("covered-amount.pdf")
        out = self.td / "replay.inkflip.json"
        code = main(
            ["replay", str(self.report), "--source", str(other), "--profile", "native-default", "--out", str(out)]
        )
        self.assertEqual(code, EXIT_INVALID_ARGS)

    def test_replay_refuses_source_as_out(self):
        code = main(
            [
                "replay",
                str(self.report),
                "--source",
                str(self.pdf),
                "--profile",
                "native-default",
                "--out",
                str(self.pdf),
                "--replace-output",
            ]
        )
        self.assertEqual(code, EXIT_INVALID_ARGS)
        self.assertTrue(self.pdf.read_bytes().startswith(b"%PDF"))

    def test_replay_refuses_fake_reader_version(self):
        data = json.loads(self.report.read_text())
        data["readers"][0]["version"] = "0.0.1"
        data["execution"]["environment"] += "; reader_version=0.0.1"
        # Re-seal so validate accepts the mutated identity.
        data = core.seal(data)
        fake = self.td / "fake.inkflip.json"
        fake.write_text(json.dumps(data))
        # validate may fail if digest/version diverge from semantic checks; either 2 from
        # validate or from replay version mismatch is acceptable refusal.
        out = self.td / "replay.json"
        code = main(
            ["replay", str(fake), "--source", str(self.pdf), "--profile", "native-default", "--out", str(out)]
        )
        self.assertEqual(code, EXIT_INVALID_ARGS)


class TestModelsPrepare(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.td = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_empty_object_is_not_ready(self):
        manifest = self.td / "m.json"
        manifest.write_text("{}")
        cache = self.td / "cache"
        code = main(["models", "prepare", "--manifest", str(manifest), "--cache", str(cache)])
        self.assertEqual(code, EXIT_INVALID_ARGS)

    def test_digest_verified_copy(self):
        blob = self.td / "model.bin"
        blob.write_bytes(b"hello-model")
        digest = hashlib.sha256(b"hello-model").hexdigest()
        manifest = self.td / "m.json"
        manifest.write_text(
            json.dumps(
                {
                    "kind": "inkflip_model_manifest",
                    "schema_version": "1.0.0",
                    "models": [
                        {
                            "id": "demo-model",
                            "sha256": digest,
                            "path": str(blob),
                            "purpose": "generic",
                        }
                    ],
                }
            )
        )
        cache = self.td / "cache"
        code = main(["models", "prepare", "--manifest", str(manifest), "--cache", str(cache)])
        self.assertEqual(code, EXIT_OK)
        copied = cache / "demo-model" / "model.bin"
        self.assertEqual(copied.read_bytes(), b"hello-model")

    def test_mismatch_stays_unavailable(self):
        blob = self.td / "model.bin"
        blob.write_bytes(b"hello-model")
        manifest = self.td / "m.json"
        manifest.write_text(
            json.dumps(
                {
                    "kind": "inkflip_model_manifest",
                    "schema_version": "1.0.0",
                    "models": [
                        {
                            "id": "demo-model",
                            "sha256": "0" * 64,
                            "path": str(blob),
                            "purpose": "generic",
                        }
                    ],
                }
            )
        )
        code = main(
            ["models", "prepare", "--manifest", str(manifest), "--cache", str(self.td / "cache")]
        )
        self.assertEqual(code, EXIT_PARTIAL_RUN)


class TestCompareReadersAndCancel(unittest.TestCase):
    def test_compare_readers(self):
        td = Path(tempfile.mkdtemp())
        out = td / "cmp"
        code = main(
            [
                "compare-readers",
                str(_pdf()),
                "--readers",
                "pdfium,pypdf",
                "--out",
                str(out),
            ]
        )
        self.assertIn(code, (EXIT_OK, EXIT_PARTIAL_RUN, EXIT_INCOMPARABLE))
        self.assertTrue((out / "comparison.json").is_file())
        core.validate(json.loads((out / "comparison.json").read_text()))

    def test_keyboard_interrupt_exit_130(self):
        with mock.patch("inkflip.cli.main.cmd_inspect", side_effect=KeyboardInterrupt):
            code = main(["inspect", str(_pdf()), "--out", "/tmp/never.json"])
        self.assertEqual(code, EXIT_CANCELLED)


if __name__ == "__main__":
    unittest.main()
