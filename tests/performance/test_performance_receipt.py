"""Negative tests against a genuinely valid 2.2.0 receipt.

REVIEW.md: absent identity, stale browser build, dirty implementation,
unavailable/wrong-type/nonfinite/negative memory, inconsistent or
excessive failures, and absent/raw-invalid observations must fail
accept. Inventory lists the same gaps without accepting.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "performance_receipt.py"


def load_receipt():
    spec = importlib.util.spec_from_file_location("performance_receipt", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def samples_30() -> list[float]:
    return [float(10 + (i % 5)) for i in range(30)]


def stage_ok(samples: list[float] | None = None, *, failures: int = 0) -> dict:
    rec = load_receipt()
    values = samples if samples is not None else samples_30()
    body = rec.summarize(values, failures, measured=True)
    body["samples_requested"] = len(values) + failures
    return body


def valid_identity(rec, root: Path) -> dict:
    identity = rec.implementation_identity(root)
    fixture = root / "fixtures" / "public" / "mapping-control.pdf"
    settings = root / "planning" / "config" / "settings.json"
    return {
        "fixture_path": "fixtures/public/mapping-control.pdf",
        "fixture_sha256": rec.sha256_file(fixture),
        "settings_sha256": rec.sha256_file(settings),
        "implementation": identity,
        "git_head": identity.get("git_head"),
    }


def valid_browser() -> dict:
    files = [
        {"path": "index.html", "sha256": "a" * 64, "bytes": 12},
        {"path": "assets/app.js", "sha256": "b" * 64, "bytes": 40},
    ]
    rec = load_receipt()
    canonical = "".join(f"{item['path']} {item['sha256']}\n" for item in files)
    tree = rec.sha256_bytes(canonical.encode("utf-8"))
    preview = stage_ok()
    preview["proof"] = "first_rendered_page"
    return {
        "kind": "inkflip-performance-browser",
        "schema_version": "2.2.0",
        "host": {"is_specified_reference_desktop": False, "is_physical_mobile": False},
        "build": {
            "production": True,
            "vite_dev_server": False,
            "inkflip_test_hooks": True,
            "tree_sha256": tree,
            "files": files,
        },
        "stages": {
            "preview": preview,
            "render": {**stage_ok(), "proof": "first_rendered_page"},
            "extraction": stage_ok(),
            "raster": {
                "n": 1,
                "measured": True,
                "distribution_claim": "not_a_latency_distribution",
                "oversize_open_rejected": True,
                "observed": {
                    "width_px": 2000,
                    "height_px": 2000,
                    "requested_scale_px_per_pt": 20.0,
                    "used_scale_px_per_pt": 3.26,
                    "pixel_cap": 4_000_000,
                    "edge_cap": 8192,
                    "pixel_budget_hit": True,
                    "edge_budget_hit": True,
                    "limitations": [
                        "render downsampled to 3.26 px/pt by raster caps (requested 20); actual scale recorded"
                    ],
                    "fixture": "fixtures/public/mapping-control.pdf",
                    "open_status": "ok",
                },
                "live_buffer_probe": {
                    "first_claim": "ok",
                    "second_claim": "ok",
                    "third_claim": "raster_cap",
                    "live_after_two": 2,
                    "live_after_release": 1,
                    "recovered": "ok",
                },
                "ocr_worker_probe": {"cap": 1, "observed_active_peak": 1},
            },
            "ocr": {"n": 0, "failures": 0, "measured": False, "distribution_claim": "missing", "samples_ms": []},
            "export": stage_ok([12.0], failures=0),
        },
        "replace_clear_cycles": {
            "n": 10,
            "js_heap_used_bytes": [1_000_000 + i for i in range(10)],
            "process_rss_bytes": [50_000_000 + i for i in range(10)],
            "baseline": {
                "first_js_heap_used_bytes": 1_000_000,
                "last_js_heap_used_bytes": 1_000_009,
                "first_process_rss_bytes": 50_000_000,
                "last_process_rss_bytes": 50_000_009,
            },
        },
        "cancel_next_file": {"cancelled_visible": True, "next_file_pages_summary": True},
        "mobile": {"ocr_consent_visible": True, "physical_device": False},
        "memory": {
            "js_heap_used_bytes": 1_000_009,
            "process_rss_bytes": 50_000_009,
            "measured_peak_rss_bytes": 50_000_020,
            "process_rss_unavailable": False,
        },
    }


def valid_receipt(rec) -> dict:
    binding = valid_identity(rec, ROOT)
    cli = stage_ok()
    return {
        "kind": "inkflip-performance",
        "schema_version": "2.2.0",
        "host": {"is_specified_reference_desktop": False, "is_physical_mobile": False},
        "source_binding": binding,
        "measurement": {
            "stages": {
                "file_sha256": copy.deepcopy(cli),
                "inspect_cli": copy.deepcopy(cli),
                "report_html": copy.deepcopy(cli),
                "alignment_cli": copy.deepcopy(cli),
                "ocr_cli": copy.deepcopy(cli),
            }
        },
        "browser": valid_browser(),
    }


class TestValidReceiptAccepts(unittest.TestCase):
    def test_unmutated_valid_receipt_has_no_problems(self) -> None:
        rec = load_receipt()
        settings = json.loads((ROOT / "planning/config/settings.json").read_text())
        body = valid_receipt(rec)
        current = rec.source_binding(ROOT)
        problems = rec.validate_receipt(
            body, mode="accept", profile="local-mac", settings=settings, current_binding=current
        )
        self.assertEqual(problems, [], problems)


class TestNegativeMutations(unittest.TestCase):
    def setUp(self) -> None:
        self.rec = load_receipt()
        self.settings = json.loads((ROOT / "planning/config/settings.json").read_text())
        self.current = self.rec.source_binding(ROOT)
        self.body = valid_receipt(self.rec)

    def problems(self, body=None, *, mode="accept") -> list[str]:
        return self.rec.validate_receipt(
            body if body is not None else self.body,
            mode=mode,
            profile="local-mac",
            settings=self.settings,
            current_binding=self.current,
        )

    def test_absent_fixture_and_settings_identity_fails(self) -> None:
        del self.body["source_binding"]["fixture_sha256"]
        del self.body["source_binding"]["settings_sha256"]
        joined = " ".join(self.problems())
        self.assertIn("fixture sha256", joined)
        self.assertIn("settings_sha256", joined)

    def test_absent_implementation_identity_fails_even_with_git_head(self) -> None:
        self.body["source_binding"]["git_head"] = self.current.get("git_head")
        del self.body["source_binding"]["implementation"]
        joined = " ".join(self.problems())
        self.assertIn("implementation identity", joined)
        self.assertNotIn("stale source identity: receipt git_head", joined)

    def test_notes_only_git_head_mismatch_does_not_stale_matching_hashes(self) -> None:
        self.body["source_binding"]["git_head"] = "0" * 40
        self.assertEqual(self.problems(), [])

    def test_source_change_invalidates_cli_hash(self) -> None:
        self.body["source_binding"]["implementation"]["cli_sha256"] = "c" * 64
        joined = " ".join(self.problems())
        self.assertIn("stale implementation identity: cli_sha256", joined)

    def test_dirty_tree_claimed_clean_fails(self) -> None:
        self.body["source_binding"]["implementation"]["dirty"] = False
        current = copy.deepcopy(self.current)
        current["implementation"]["dirty"] = True
        problems = self.rec.validate_receipt(
            self.body,
            mode="accept",
            profile="local-mac",
            settings=self.settings,
            current_binding=current,
        )
        self.assertTrue(any("dirty" in item for item in problems), problems)

    def test_stale_browser_build_production_flag_only(self) -> None:
        self.body["browser"]["build"] = {"production": True, "vite_dev_server": False}
        joined = " ".join(self.problems())
        self.assertIn("production flag is not build identity", joined)

    def test_unavailable_memory_fails_accept_but_inventory_lists(self) -> None:
        self.body["browser"]["memory"]["process_rss_unavailable"] = True
        self.body["browser"]["memory"]["process_rss_bytes"] = None
        self.body["browser"]["memory"]["measured_peak_rss_bytes"] = None
        accept = self.problems(mode="accept")
        inventory = self.problems(mode="inventory")
        self.assertTrue(any("unavailable" in item for item in accept), accept)
        self.assertEqual(accept, inventory)
        self.assertTrue(accept)

    def test_wrong_type_nonfinite_negative_memory(self) -> None:
        cases = [
            ("js_heap_used_bytes", "nope", "wrong type"),
            ("process_rss_bytes", float("nan"), "nonfinite"),
            ("measured_peak_rss_bytes", -1, "negative"),
        ]
        for field, value, needle in cases:
            body = valid_receipt(self.rec)
            body["browser"]["memory"][field] = value
            joined = " ".join(self.problems(body))
            self.assertIn(needle, joined, field)

    def test_thirty_successes_plus_999_failures_is_not_healthy(self) -> None:
        stage = stage_ok(failures=999)
        self.body["measurement"]["stages"]["inspect_cli"] = stage
        joined = " ".join(self.problems())
        self.assertIn("failure-rate policy", joined)
        self.assertIn("999", joined)

    def test_inconsistent_failures_vs_samples_requested(self) -> None:
        stage = stage_ok()
        stage["failures"] = 4
        stage["samples_requested"] = 30
        self.body["measurement"]["stages"]["report_html"] = stage
        joined = " ".join(self.problems())
        self.assertIn("inconsistent failures", joined)

    def test_absent_and_raw_invalid_observations(self) -> None:
        stage = stage_ok()
        stage["samples_ms"] = [1.0, float("inf")] + [1.0] * 28
        stage["n"] = 30
        self.body["measurement"]["stages"]["alignment_cli"] = stage
        joined = " ".join(self.problems())
        self.assertIn("raw-invalid", joined)

        body = valid_receipt(self.rec)
        del body["measurement"]["stages"]["ocr_cli"]["samples_ms"]
        joined = " ".join(self.problems(body))
        self.assertIn("missing raw samples_ms", joined)

    def test_live_buffers_constant_is_not_proof(self) -> None:
        raster = self.body["browser"]["stages"]["raster"]
        raster["live_buffers"] = 2
        raster["live_buffer_cap_enforced"] = True
        del raster["live_buffer_probe"]
        joined = " ".join(self.problems())
        self.assertIn("restated from the configured limit", joined)

    def test_parser_error_giant_pdf_is_not_clamping(self) -> None:
        self.body["browser"]["stages"]["raster"]["parser_error"] = True
        joined = " ".join(self.problems())
        self.assertIn("parser_error", joined)

    def test_schema_21_is_stale_even_if_head_matches(self) -> None:
        self.body["schema_version"] = "2.1.0"
        self.body["source_binding"]["git_head"] = self.current.get("git_head")
        joined = " ".join(self.problems())
        self.assertIn("stale", joined)
        self.assertIn("2.1.0", joined)


class TestImplementationIdentity(unittest.TestCase):
    def test_notes_file_outside_product_paths_does_not_change_hashes(self) -> None:
        rec = load_receipt()
        before = rec.implementation_identity(ROOT)
        with tempfile.TemporaryDirectory(dir=ROOT, prefix="notes-only-") as raw:
            Path(raw, "HANDOFF.md").write_text("notes only\n", encoding="utf-8")
            after = rec.implementation_identity(ROOT)
        self.assertEqual(before["cli_sha256"], after["cli_sha256"])
        self.assertEqual(before["browser_sha256"], after["browser_sha256"])
        self.assertEqual(before["docker_sha256"], after["docker_sha256"])

    def test_product_file_change_changes_relevant_hash(self) -> None:
        rec = load_receipt()
        before = rec.hash_input_spec(ROOT, rec.CLI_INPUT_PATHS)
        native = ROOT / "native" / "inkflip" / "cli" / "main.py"
        original = native.read_bytes()
        try:
            native.write_bytes(original + b"\n# identity-probe\n")
            after = rec.hash_input_spec(ROOT, rec.CLI_INPUT_PATHS)
        finally:
            native.write_bytes(original)
        self.assertNotEqual(before, after)


class TestInventoryDoesNotAccept(unittest.TestCase):
    def test_inventory_exit_lists_unavailable_memory(self) -> None:
        rec = load_receipt()
        settings = json.loads((ROOT / "planning/config/settings.json").read_text())
        body = valid_receipt(rec)
        body["browser"]["memory"]["process_rss_unavailable"] = True
        body["browser"]["memory"]["process_rss_bytes"] = None
        problems = rec.validate_receipt(
            body,
            mode="inventory",
            profile="local-mac",
            settings=settings,
            current_binding=rec.source_binding(ROOT),
        )
        lines = rec.inventory_lines(problems, profile="local-mac", mode="inventory")
        self.assertTrue(problems)
        self.assertTrue(any("unavailable" in line for line in lines))
        self.assertTrue(any(line.startswith("performance inventory") for line in lines))


if __name__ == "__main__":
    unittest.main()
