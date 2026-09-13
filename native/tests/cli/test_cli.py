"""T30 Native CLI tests (TEST-30).

Verifies the inkflip CLI commands and contracts:
- readers list
- inspect
- validate
- report
- replay
- compare-readers
- models prepare
- Exit codes: 0 (OK), 2 (invalid args/config/contract), 3 (partial run),
  4 (read/runtime failure), 6 (incomparable), 130 (cancellation).
"""
from __future__ import annotations

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

from inkflip.cli.main import (
    EXIT_CANCELLED,
    EXIT_INCOMPARABLE,
    EXIT_INVALID_ARGS,
    EXIT_OK,
    EXIT_PARTIAL_RUN,
    EXIT_POLICY_FAILURE,
    EXIT_READ_FAILURE,
    IncomparableError,
    PartialRunError,
    build_parser,
    main,
)
from inkflip.contracts import core, validate


class TestCliReadersList(unittest.TestCase):
    """Test `inkflip readers list --json` (exit 0)."""

    def test_readers_list_json(self):
        buf = io.StringIO()
        with mock.patch("sys.stdout", buf):
            code = main(["readers", "list", "--json"])
        self.assertEqual(code, EXIT_OK)
        data = json.loads(buf.getvalue())
        self.assertIn("readers", data)
        readers = data["readers"]
        self.assertGreaterEqual(len(readers), 3)
        ids = [r["reader"]["id"] for r in readers]
        self.assertIn("pdfium-native", ids)
        self.assertIn("pypdf-native", ids)
        self.assertIn("tesseract-native", ids)


class TestCliInspect(unittest.TestCase):
    """Test `inkflip inspect` with various flags and validations."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.td = Path(self.tmp_dir.name)
        self.fixture_pdf = FIXTURES / "public" / "geometry-control.pdf"
        self.assertTrue(self.fixture_pdf.exists())

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_inspect_default_pdfium_exit_0(self):
        out_file = self.td / "out.inkflip.json"
        code = main(["inspect", str(self.fixture_pdf), "--out", str(out_file)])
        self.assertEqual(code, EXIT_OK)
        self.assertTrue(out_file.exists())
        data = json.loads(out_file.read_text(encoding="utf-8"))
        validate(data)
        self.assertEqual(data["kind"], "report")
        self.assertEqual(len(data["readers"]), 1)
        self.assertEqual(data["readers"][0]["id"], "pdfium-native")
        self.assertGreaterEqual(len(data["occurrences"]), 1)

    def test_inspect_pypdf_reader_exit_0(self):
        out_file = self.td / "out_pypdf.inkflip.json"
        code = main([
            "inspect", str(self.fixture_pdf),
            "--out", str(out_file),
            "--reader", "pypdf",
        ])
        self.assertEqual(code, EXIT_OK)
        self.assertTrue(out_file.exists())
        data = json.loads(out_file.read_text(encoding="utf-8"))
        validate(data)
        self.assertEqual(data["readers"][0]["id"], "pypdf-native")

    def test_inspect_embed_source_exit_0(self):
        out_file = self.td / "out_embedded.inkflip.json"
        code = main([
            "inspect", str(self.fixture_pdf),
            "--out", str(out_file),
            "--embed-source",
        ])
        self.assertEqual(code, EXIT_OK)
        self.assertTrue(out_file.exists())
        data = json.loads(out_file.read_text(encoding="utf-8"))
        validate(data)
        self.assertEqual(data["export"]["mode"], "replayable")
        self.assertEqual(data["export"]["replay"], "source_included_environment_required")
        self.assertIn("source_pdf", data["export"]["included"])
        self.assertIsNotNone(data["document"]["source_asset_id"])

    def test_inspect_refuses_overwrite_without_replace_flag_exit_2(self):
        out_file = self.td / "existing.json"
        out_file.write_text("{}", encoding="utf-8")
        code = main(["inspect", str(self.fixture_pdf), "--out", str(out_file)])
        self.assertEqual(code, EXIT_INVALID_ARGS)

    def test_inspect_allows_overwrite_with_replace_flag_exit_0(self):
        out_file = self.td / "existing.json"
        out_file.write_text("{}", encoding="utf-8")
        code = main([
            "inspect", str(self.fixture_pdf),
            "--out", str(out_file),
            "--replace-output",
        ])
        self.assertEqual(code, EXIT_OK)
        data = json.loads(out_file.read_text(encoding="utf-8"))
        validate(data)

    def test_inspect_refuses_remote_url_exit_2(self):
        out_file = self.td / "out.json"
        code = main(["inspect", "https://example.com/test.pdf", "--out", str(out_file)])
        self.assertEqual(code, EXIT_INVALID_ARGS)

    def test_inspect_refuses_unknown_reader_exit_2(self):
        out_file = self.td / "out.json"
        code = main([
            "inspect", str(self.fixture_pdf),
            "--out", str(out_file),
            "--reader", "arbitrary_executable",
        ])
        self.assertEqual(code, EXIT_INVALID_ARGS)

    def test_inspect_refuses_duplicate_pages_exit_2(self):
        out_file = self.td / "out.json"
        code = main([
            "inspect", str(self.fixture_pdf),
            "--out", str(out_file),
            "--pages", "1,1",
        ])
        self.assertEqual(code, EXIT_INVALID_ARGS)

    def test_inspect_refuses_inverted_range_exit_2(self):
        out_file = self.td / "out.json"
        code = main([
            "inspect", str(self.fixture_pdf),
            "--out", str(out_file),
            "--pages", "3-1",
        ])
        self.assertEqual(code, EXIT_INVALID_ARGS)

    def test_inspect_refuses_ocr_pages_outside_selection_exit_2(self):
        out_file = self.td / "out.json"
        code = main([
            "inspect", str(self.fixture_pdf),
            "--out", str(out_file),
            "--pages", "1",
            "--ocr-pages", "2",
        ])
        self.assertEqual(code, EXIT_INVALID_ARGS)

    def test_inspect_refuses_region_on_multi_page_exit_2(self):
        out_file = self.td / "out.json"
        # geometry-control has 1 page, so requesting 1-2 would fail on page bounds, but testing parser directly
        code = main([
            "inspect", str(self.fixture_pdf),
            "--out", str(out_file),
            "--pages", "1",
            "--region", "100,100,50,50",  # inverted bounds
        ])
        self.assertEqual(code, EXIT_INVALID_ARGS)

    def test_inspect_refuses_output_matching_source_exit_2(self):
        code = main(["inspect", str(self.fixture_pdf), "--out", str(self.fixture_pdf)])
        self.assertEqual(code, EXIT_INVALID_ARGS)


class TestCliValidate(unittest.TestCase):
    """Test `inkflip validate` (exit 0 on valid, 2 on invalid contract/syntax, 4 on read fail)."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.td = Path(self.tmp_dir.name)
        self.fixture_pdf = FIXTURES / "public" / "geometry-control.pdf"

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_validate_valid_report_exit_0(self):
        out_file = self.td / "valid.inkflip.json"
        main(["inspect", str(self.fixture_pdf), "--out", str(out_file)])
        code = main(["validate", str(out_file)])
        self.assertEqual(code, EXIT_OK)

    def test_validate_invalid_json_exit_2(self):
        bad_json = self.td / "bad.json"
        bad_json.write_text("{ unquoted_key: 123 ", encoding="utf-8")
        code = main(["validate", str(bad_json)])
        self.assertEqual(code, EXIT_INVALID_ARGS)

    def test_validate_schema_mismatch_exit_2(self):
        bad_report = self.td / "invalid_schema.json"
        bad_report.write_text(
            json.dumps({"kind": "report", "schema_version": "1.0.0"}),
            encoding="utf-8",
        )
        code = main(["validate", str(bad_report)])
        self.assertEqual(code, EXIT_INVALID_ARGS)

    def test_validate_missing_file_exit_4(self):
        code = main(["validate", str(self.td / "nonexistent.json")])
        self.assertEqual(code, EXIT_READ_FAILURE)


class TestCliReport(unittest.TestCase):
    """Test `inkflip report` HTML export."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.td = Path(self.tmp_dir.name)
        self.fixture_pdf = FIXTURES / "public" / "geometry-control.pdf"
        self.report_file = self.td / "report.inkflip.json"
        main(["inspect", str(self.fixture_pdf), "--out", str(self.report_file)])

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_report_html_export_exit_0(self):
        html_out = self.td / "report.html"
        code = main([
            "report", str(self.report_file),
            "--format", "html",
            "--out", str(html_out),
        ])
        self.assertEqual(code, EXIT_OK)
        self.assertTrue(html_out.exists())
        content = html_out.read_text(encoding="utf-8")
        self.assertIn("<!doctype html>", content)
        self.assertIn("Content-Security-Policy", content)
        self.assertIn("default-src 'none'", content)
        self.assertNotIn("<script", content.lower())

    def test_report_unsupported_format_exit_2(self):
        html_out = self.td / "report.txt"
        # ArgumentParser choices=['html'] will reject with exit 2
        code = main([
            "report", str(self.report_file),
            "--format", "unsupported",
            "--out", str(html_out),
        ])
        self.assertEqual(code, EXIT_INVALID_ARGS)


class TestCliReplay(unittest.TestCase):
    """Test `inkflip replay` source and hash verifications."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.td = Path(self.tmp_dir.name)
        self.fixture_pdf = FIXTURES / "public" / "geometry-control.pdf"
        self.other_pdf = FIXTURES / "public" / "covered-control.pdf"

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_replay_with_embedded_source_exit_0(self):
        embedded_rep = self.td / "embedded.inkflip.json"
        main(["inspect", str(self.fixture_pdf), "--out", str(embedded_rep), "--embed-source"])
        replay_out = self.td / "replayed.inkflip.json"
        code = main([
            "replay", str(embedded_rep),
            "--profile", "native",
            "--out", str(replay_out),
        ])
        self.assertEqual(code, EXIT_OK)
        self.assertTrue(replay_out.exists())
        data = json.loads(replay_out.read_text(encoding="utf-8"))
        validate(data)
        self.assertEqual(data["export"]["origin_report_id"], json.loads(embedded_rep.read_text())["report_id"])

    def test_replay_with_explicit_source_exit_0(self):
        evidence_rep = self.td / "evidence.inkflip.json"
        main(["inspect", str(self.fixture_pdf), "--out", str(evidence_rep)])
        replay_out = self.td / "replayed.inkflip.json"
        code = main([
            "replay", str(evidence_rep),
            "--source", str(self.fixture_pdf),
            "--profile", "native",
            "--out", str(replay_out),
        ])
        self.assertEqual(code, EXIT_OK)
        self.assertTrue(replay_out.exists())
        data = json.loads(replay_out.read_text(encoding="utf-8"))
        validate(data)

    def test_replay_refuses_mismatched_source_hash_exit_2(self):
        evidence_rep = self.td / "evidence.inkflip.json"
        main(["inspect", str(self.fixture_pdf), "--out", str(evidence_rep)])
        replay_out = self.td / "replayed.inkflip.json"
        code = main([
            "replay", str(evidence_rep),
            "--source", str(self.other_pdf),  # different PDF
            "--profile", "native",
            "--out", str(replay_out),
        ])
        self.assertEqual(code, EXIT_INVALID_ARGS)

    def test_replay_refuses_missing_source_when_not_embedded_exit_2(self):
        evidence_rep = self.td / "evidence.inkflip.json"
        main(["inspect", str(self.fixture_pdf), "--out", str(evidence_rep)])
        replay_out = self.td / "replayed.inkflip.json"
        code = main([
            "replay", str(evidence_rep),
            "--profile", "native",
            "--out", str(replay_out),
        ])
        self.assertEqual(code, EXIT_INVALID_ARGS)


class TestCliCompareReaders(unittest.TestCase):
    """Test `inkflip compare-readers`."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.td = Path(self.tmp_dir.name)
        self.fixture_pdf = FIXTURES / "public" / "geometry-control.pdf"

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_compare_readers_valid_exit_0(self):
        out_dir = self.td / "comparison_dir"
        code = main([
            "compare-readers", str(self.fixture_pdf),
            "--readers", "pdfium,pypdf",
            "--out", str(out_dir),
        ])
        self.assertEqual(code, EXIT_OK)
        self.assertTrue((out_dir / "report_pdfium.inkflip.json").exists())
        self.assertTrue((out_dir / "report_pypdf.inkflip.json").exists())
        self.assertTrue((out_dir / "comparison.json").exists())
        self.assertTrue((out_dir / "comparison.html").exists())
        comp_data = json.loads((out_dir / "comparison.json").read_text(encoding="utf-8"))
        validate(comp_data)

    def test_compare_readers_invalid_count_exit_2(self):
        out_dir = self.td / "comparison_dir"
        code = main([
            "compare-readers", str(self.fixture_pdf),
            "--readers", "pdfium",
            "--out", str(out_dir),
        ])
        self.assertEqual(code, EXIT_INVALID_ARGS)


class TestCliModelsPrepare(unittest.TestCase):
    """Test `inkflip models prepare`."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.td = Path(self.tmp_dir.name)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_models_prepare_valid_manifest_exit_0(self):
        manifest = self.td / "manifest.json"
        manifest.write_text(json.dumps({"models": []}), encoding="utf-8")
        code = main(["models", "prepare", "--manifest", str(manifest)])
        self.assertEqual(code, EXIT_OK)

    def test_models_prepare_missing_manifest_exit_2(self):
        code = main(["models", "prepare", "--manifest", str(self.td / "missing.json")])
        self.assertEqual(code, EXIT_INVALID_ARGS)


class TestCliExitCodes(unittest.TestCase):
    """Test explicit exit codes: 3, 4, 6, 130."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.td = Path(self.tmp_dir.name)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_exit_3_partial_run_missing_model(self):
        with mock.patch("inkflip.readers.tesseract.model_digest", return_value=(None, None)):
            fixture_pdf = FIXTURES / "public" / "geometry-control.pdf"
            code = main([
                "inspect", str(fixture_pdf),
                "--out", str(self.td / "out.json"),
                "--reader", "tesseract",
            ])
            self.assertEqual(code, EXIT_PARTIAL_RUN)

    def test_exit_4_runtime_read_failure_nonexistent(self):
        code = main([
            "inspect", str(self.td / "does_not_exist.pdf"),
            "--out", str(self.td / "out.json"),
        ])
        self.assertEqual(code, EXIT_READ_FAILURE)

    def test_exit_4_runtime_read_failure_malformed_header(self):
        bad_pdf = self.td / "not_a_pdf.txt"
        bad_pdf.write_text("Hello world", encoding="utf-8")
        code = main([
            "inspect", str(bad_pdf),
            "--out", str(self.td / "out.json"),
        ])
        self.assertEqual(code, EXIT_READ_FAILURE)

    def test_exit_4_runtime_read_failure_encrypted(self):
        enc_pdf = FIXTURES / "development" / "bad-pdf-encrypted.pdf"
        if enc_pdf.exists():
            code = main([
                "inspect", str(enc_pdf),
                "--out", str(self.td / "out.json"),
            ])
            self.assertEqual(code, EXIT_READ_FAILURE)

    def test_exit_6_incomparable(self):
        # Trigger IncomparableError in a CLI action
        with mock.patch("inkflip.cli.main.cmd_compare_readers", side_effect=IncomparableError("Incomparable runs")):
            fixture_pdf = FIXTURES / "public" / "geometry-control.pdf"
            code = main([
                "compare-readers", str(fixture_pdf),
                "--readers", "pdfium,pypdf",
                "--out", str(self.td / "comp"),
            ])
            self.assertEqual(code, EXIT_INCOMPARABLE)

    def test_exit_130_cancelled(self):
        with mock.patch("inkflip.cli.main.cmd_inspect", side_effect=KeyboardInterrupt):
            fixture_pdf = FIXTURES / "public" / "geometry-control.pdf"
            code = main([
                "inspect", str(fixture_pdf),
                "--out", str(self.td / "out.json"),
            ])
            self.assertEqual(code, EXIT_CANCELLED)


if __name__ == "__main__":
    unittest.main()
