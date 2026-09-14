"""Fail-closed manual receipt checks for T37/T46/T53 (TEST-46 false-positive).

The registered acceptance command is:

    python scripts/check_manual_receipts.py <accessibility|compatibility|release>

It must not certify incomplete required coverage. Required compatibility
profiles come from planning/quality/PERFORMANCE_AND_COMPATIBILITY.md and
TEST-46, not from whichever rows a receipt happens to contain.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check_manual_receipts.py"
COMMITTED_RECEIPT = ROOT / "docs" / "compatibility" / "manual-receipt.json"


def load_checker():
    spec = importlib.util.spec_from_file_location("check_manual_receipts", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FalsePositiveReceiptTests(unittest.TestCase):
    def test_committed_partial_receipt_is_the_codex_false_positive(self):
        data = json.loads(COMMITTED_RECEIPT.read_text(encoding="utf-8"))
        self.assertEqual(data["kind"], "compatibility")
        self.assertEqual(data["status"], "partial")
        statuses = {row["id"]: row["status"] for row in data["platforms"]}
        self.assertEqual(statuses["safari"], "unavailable")
        self.assertEqual(statuses["linux-amd64-native"], "unavailable")
        self.assertIn(statuses.get("chromium"), {"executed", "unavailable", "blocked", "pending"})

    def test_acceptance_command_rejects_committed_partial_receipt(self):
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "compatibility"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        combined = proc.stdout + proc.stderr
        self.assertNotIn("compatibility: ok", combined)
        self.assertIn("incomplete", combined.lower() + proc.stderr.lower())


class CheckerContractTests(unittest.TestCase):
    def setUp(self):
        self.mod = load_checker()
        self.tmp = tempfile.TemporaryDirectory(prefix="inkflip-receipt-")
        self.root = Path(self.tmp.name)
        (self.root / "docs" / "compatibility").mkdir(parents=True)
        (self.root / "artifacts" / "P15").mkdir(parents=True)
        (self.root / "artifacts" / "gates" / "G4").mkdir(parents=True)
        (self.root / "docs" / "accessibility").mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def write_evidence(self, rel: str, body: str = "observed\n") -> str:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return rel

    def complete_compatibility_platforms(self) -> list[dict]:
        return [
            {
                "id": "chromium",
                "status": "executed",
                "evidence": [self.write_evidence("artifacts/P15/chromium.json")],
                "identity": {"browser": "Chromium 141.0.7390.54", "playwright": "1.57.0"},
            },
            {
                "id": "firefox",
                "status": "executed",
                "evidence": [self.write_evidence("artifacts/P15/firefox.json")],
                "identity": {"browser": "Firefox 143.0", "playwright": "1.57.0"},
            },
            {
                "id": "safari",
                "status": "executed",
                "evidence": [self.write_evidence("artifacts/P15/safari.json")],
                "identity": {"browser": "Safari 26.0", "device": "macOS physical"},
            },
            {
                "id": "linux-amd64-native",
                "status": "executed",
                "evidence": [self.write_evidence("artifacts/P15/linux-amd64.json")],
                "identity": {"os": "Linux x86_64", "python": "3.13.15"},
            },
        ]

    def write_kind(self, kind: str, payload: dict) -> Path:
        path = self.root / self.mod.KINDS[kind].relative_to(self.mod.ROOT)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return path

    def check(self, kind: str, mode: str = "acceptance") -> tuple[int, str]:
        return self.mod.check_kind(kind, root=self.root, mode=mode)

    def test_required_compatibility_profiles_come_from_contract_not_receipt_rows(self):
        required = [item["id"] for item in self.mod.required_profiles("compatibility")]
        self.assertEqual(
            required,
            ["chromium", "firefox", "safari", "linux-amd64-native"],
        )
        extra_only = {
            "schema_version": "1.0.0",
            "kind": "compatibility",
            "status": "complete",
            "host": {"os": "Darwin arm64", "cpu": "arm64"},
            "platforms": [
                {
                    "id": "pdfjs-node-wrapper",
                    "status": "executed",
                    "evidence": [self.write_evidence("artifacts/P15/node.json")],
                    "identity": {"runtime": "node"},
                }
            ],
        }
        self.write_kind("compatibility", extra_only)
        code, err = self.check("compatibility")
        self.assertEqual(code, 1)
        for profile in required:
            self.assertIn(profile, err)

    def test_complete_receipt_with_real_evidence_passes_acceptance(self):
        payload = {
            "schema_version": "1.0.0",
            "kind": "compatibility",
            "status": "complete",
            "host": {"os": "Darwin arm64", "cpu": "arm64", "python": "3.13.15"},
            "platforms": self.complete_compatibility_platforms()
            + [
                {
                    "id": "native-macos-arm64",
                    "status": "executed",
                    "evidence": [self.write_evidence("artifacts/P15/native.json")],
                    "identity": {"os": "macOS 26.5", "arch": "arm64"},
                }
            ],
        }
        self.write_kind("compatibility", payload)
        code, err = self.check("compatibility")
        self.assertEqual(code, 0, err)
        self.assertEqual(err, "")

    def test_webkit_automation_does_not_satisfy_safari(self):
        platforms = self.complete_compatibility_platforms()
        for row in platforms:
            if row["id"] == "safari":
                row["id"] = "webkit-safari"
                row["identity"] = {"browser": "Playwright WebKit"}
        payload = {
            "schema_version": "1.0.0",
            "kind": "compatibility",
            "status": "complete",
            "host": {"os": "Darwin arm64", "cpu": "arm64"},
            "platforms": platforms,
        }
        self.write_kind("compatibility", payload)
        code, err = self.check("compatibility")
        self.assertEqual(code, 1)
        self.assertIn("safari", err)

    def test_partial_overall_status_fails_even_if_rows_exist(self):
        payload = {
            "schema_version": "1.0.0",
            "kind": "compatibility",
            "status": "partial",
            "host": {"os": "Darwin arm64", "cpu": "arm64"},
            "platforms": self.complete_compatibility_platforms(),
        }
        self.write_kind("compatibility", payload)
        code, err = self.check("compatibility")
        self.assertEqual(code, 1)
        self.assertIn("partial", err)

    def test_missing_empty_and_malformed_evidence_fail(self):
        platforms = self.complete_compatibility_platforms()
        platforms[0]["evidence"] = ["artifacts/P15/missing-chromium.json"]
        payload = {
            "schema_version": "1.0.0",
            "kind": "compatibility",
            "status": "complete",
            "host": {"os": "Darwin arm64", "cpu": "arm64"},
            "platforms": platforms,
        }
        self.write_kind("compatibility", payload)
        code, err = self.check("compatibility")
        self.assertEqual(code, 1)
        self.assertIn("evidence", err.lower())

        platforms = self.complete_compatibility_platforms()
        empty = self.root / "artifacts" / "P15" / "empty.json"
        empty.write_text("", encoding="utf-8")
        platforms[1]["evidence"] = ["artifacts/P15/empty.json"]
        payload["platforms"] = platforms
        self.write_kind("compatibility", payload)
        code, err = self.check("compatibility")
        self.assertEqual(code, 1)
        self.assertIn("empty", err.lower())

        platforms = self.complete_compatibility_platforms()
        platforms[2]["evidence"] = "not-a-list"
        payload["platforms"] = platforms
        self.write_kind("compatibility", payload)
        code, err = self.check("compatibility")
        self.assertEqual(code, 1)

        platforms = self.complete_compatibility_platforms()
        platforms[3]["evidence"] = ["../outside.json"]
        (self.root.parent / "outside.json").write_text("nope\n", encoding="utf-8")
        payload["platforms"] = platforms
        self.write_kind("compatibility", payload)
        code, err = self.check("compatibility")
        self.assertEqual(code, 1)

    def test_symlink_evidence_fails(self):
        platforms = self.complete_compatibility_platforms()
        real = self.root / "artifacts" / "P15" / "real.json"
        link = self.root / "artifacts" / "P15" / "link.json"
        if link.exists():
            link.unlink()
        os.symlink(real, link)
        platforms[0]["evidence"] = ["artifacts/P15/link.json"]
        payload = {
            "schema_version": "1.0.0",
            "kind": "compatibility",
            "status": "complete",
            "host": {"os": "Darwin arm64", "cpu": "arm64"},
            "platforms": platforms,
        }
        self.write_kind("compatibility", payload)
        code, err = self.check("compatibility")
        self.assertEqual(code, 1)
        self.assertIn("symlink", err.lower())

    def test_identity_mismatch_and_invalid_schema_fail(self):
        payload = {
            "schema_version": "1.0.0",
            "kind": "accessibility",
            "status": "complete",
            "host": {"os": "Darwin arm64", "cpu": "arm64"},
            "platforms": self.complete_compatibility_platforms(),
        }
        self.write_kind("compatibility", payload)
        code, err = self.check("compatibility")
        self.assertEqual(code, 1)
        self.assertIn("kind", err.lower())

        payload = {
            "schema_version": "9.9.9",
            "kind": "compatibility",
            "status": "complete",
            "host": {"os": "Darwin arm64", "cpu": "arm64"},
            "platforms": self.complete_compatibility_platforms(),
        }
        self.write_kind("compatibility", payload)
        code, err = self.check("compatibility")
        self.assertEqual(code, 1)
        self.assertIn("schema", err.lower())

        platforms = self.complete_compatibility_platforms()
        platforms[0]["status"] = "shipped"
        payload = {
            "schema_version": "1.0.0",
            "kind": "compatibility",
            "status": "complete",
            "host": {"os": "Darwin arm64", "cpu": "arm64"},
            "platforms": platforms,
        }
        self.write_kind("compatibility", payload)
        code, err = self.check("compatibility")
        self.assertEqual(code, 1)
        self.assertIn("status", err.lower())

        platforms = self.complete_compatibility_platforms()
        del platforms[0]["identity"]
        payload["platforms"] = platforms
        payload["status"] = "complete"
        self.write_kind("compatibility", payload)
        code, err = self.check("compatibility")
        self.assertEqual(code, 1)
        self.assertIn("identity", err.lower())

    def test_inventory_lists_incomplete_profiles_without_certifying(self):
        payload = json.loads(COMMITTED_RECEIPT.read_text(encoding="utf-8"))
        # Inventory against the committed shape, copied into the temp tree so
        # missing evidence files are also visible as incomplete rather than
        # crashing the reporter.
        self.write_kind("compatibility", payload)
        code, err = self.check("compatibility", mode="inventory")
        self.assertEqual(code, 0, err)
        self.assertNotIn(": ok (", err)
        self.assertIn("chromium", err)
        self.assertIn("safari", err)
        self.assertIn("linux-amd64-native", err)

        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "compatibility", "--inventory"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("compatibility: ok", proc.stdout)
        self.assertIn("incomplete", (proc.stdout + proc.stderr).lower())

    def test_accessibility_and_release_missing_receipts_still_fail_closed(self):
        code, err = self.check("accessibility")
        self.assertEqual(code, 1)
        self.assertIn("missing", err.lower())
        code, err = self.check("release")
        self.assertEqual(code, 1)
        self.assertIn("missing", err.lower())

    def test_accessibility_complete_receipt_still_accepted(self):
        platforms = []
        for profile in self.mod.required_profiles("accessibility"):
            rel = f"docs/accessibility/{profile['id']}.md"
            platforms.append(
                {
                    "id": profile["id"],
                    "status": "executed",
                    "evidence": [self.write_evidence(rel)],
                    "identity": {"at": profile["id"], "os": "macOS"},
                }
            )
        payload = {
            "schema_version": "1.0.0",
            "kind": "accessibility",
            "status": "complete",
            "host": {"os": "Darwin arm64", "cpu": "arm64"},
            "platforms": platforms,
        }
        self.write_kind("accessibility", payload)
        code, err = self.check("accessibility")
        self.assertEqual(code, 0, err)

    def test_macos_release_profile_does_not_require_linux(self):
        required = [item["id"] for item in self.mod.required_profiles("compatibility", "macos")]
        self.assertEqual(required, ["chromium", "firefox"])
        payload = {
            "schema_version": "1.0.0",
            "kind": "compatibility",
            "status": "partial",
            "host": {"os": "Darwin arm64", "cpu": "arm64"},
            "platforms": [
                {
                    "id": "chromium",
                    "status": "executed",
                    "evidence": [self.write_evidence("artifacts/P15/chromium.json")],
                    "identity": {"browser": "Chromium 143.0.7499.4"},
                },
                {
                    "id": "firefox",
                    "status": "executed",
                    "evidence": [self.write_evidence("artifacts/P15/firefox.json")],
                    "identity": {"browser": "Firefox 144.0.2"},
                },
                {
                    "id": "safari",
                    "status": "unavailable",
                    "evidence": [self.write_evidence("artifacts/P15/safari-blocker.txt")],
                    "note": "safaridriver not enabled",
                },
                {
                    "id": "linux-amd64-native",
                    "status": "unavailable",
                    "evidence": [self.write_evidence("artifacts/P15/linux-blocker.txt")],
                    "note": "deferred 2026-09-13 macOS-only release",
                },
            ],
        }
        self.write_kind("compatibility", payload)
        code, err = self.mod.check_kind(
            "compatibility", root=self.root, mode="acceptance", release_profile="macos"
        )
        self.assertEqual(code, 0, err)

    def test_macos_release_profile_accessibility_defers_nvda_only(self):
        required = [item["id"] for item in self.mod.required_profiles("accessibility", "macos")]
        self.assertNotIn("screen-reader-nvda-firefox", required)
        self.assertIn("screen-reader-voiceover-safari", required)
        self.assertEqual(
            required,
            ["keyboard", "amount-alternatives", "zoom-400", "reduced-motion",
             "screen-reader-voiceover-safari"],
        )

    def test_historical_accessibility_still_requires_nvda_and_voiceover(self):
        required = [item["id"] for item in self.mod.required_profiles("accessibility")]
        self.assertIn("screen-reader-nvda-firefox", required)
        self.assertIn("screen-reader-voiceover-safari", required)
        self.assertEqual(len(required), 6)

    def test_macos_accessibility_still_fails_on_missing_voiceover(self):
        platforms = []
        for profile in self.mod.required_profiles("accessibility", "macos"):
            platforms.append(
                {
                    "id": profile["id"],
                    "status": "executed",
                    "evidence": [self.write_evidence(f"docs/accessibility/{profile['id']}.md")],
                    "identity": {"at": profile["id"], "os": "macOS"},
                }
            )
        for row in platforms:
            if row["id"] == "screen-reader-voiceover-safari":
                row["status"] = "unavailable"
        payload = {
            "schema_version": "1.0.0",
            "kind": "accessibility",
            "status": "partial",
            "host": {"os": "Darwin arm64", "cpu": "arm64"},
            "platforms": platforms,
        }
        self.write_kind("accessibility", payload)
        code, err = self.mod.check_kind(
            "accessibility", root=self.root, mode="acceptance", release_profile="macos"
        )
        self.assertEqual(code, 1)
        self.assertIn("voiceover", err.lower())
        self.assertNotIn("nvda", err.lower())

    def test_macos_accessibility_accepts_without_nvda_row(self):
        platforms = []
        for profile in self.mod.required_profiles("accessibility", "macos"):
            platforms.append(
                {
                    "id": profile["id"],
                    "status": "executed",
                    "evidence": [self.write_evidence(f"docs/accessibility/{profile['id']}.md")],
                    "identity": {"at": profile["id"], "os": "macOS"},
                }
            )
        payload = {
            "schema_version": "1.0.0",
            "kind": "accessibility",
            "status": "complete",
            "host": {"os": "Darwin arm64", "cpu": "arm64"},
            "platforms": platforms,
        }
        self.write_kind("accessibility", payload)
        code, err = self.mod.check_kind(
            "accessibility", root=self.root, mode="acceptance", release_profile="macos"
        )
        self.assertEqual(code, 0, err)
        code, err = self.check("accessibility")
        self.assertEqual(code, 1)

    def test_webkit_labelled_safari_is_forged(self):
        platforms = self.complete_compatibility_platforms()
        for row in platforms:
            if row["id"] == "safari":
                row["identity"] = {"browser": "Playwright WebKit 26.0", "automation": "webkit-safari"}
        payload = {
            "schema_version": "1.0.0",
            "kind": "compatibility",
            "status": "complete",
            "host": {"os": "Darwin arm64", "cpu": "arm64"},
            "platforms": platforms,
        }
        self.write_kind("compatibility", payload)
        code, err = self.check("compatibility")
        self.assertEqual(code, 1)
        self.assertIn("forged", err.lower())

    def test_stale_source_identity_fails(self):
        platforms = self.complete_compatibility_platforms()
        platforms[0]["identity"] = {"browser": "Chromium", "source_sha256": "stale"}
        payload = {
            "schema_version": "1.0.0",
            "kind": "compatibility",
            "status": "complete",
            "host": {"os": "Darwin arm64", "cpu": "arm64"},
            "platforms": platforms,
        }
        self.write_kind("compatibility", payload)
        code, err = self.check("compatibility")
        self.assertEqual(code, 1)
        self.assertIn("stale", err.lower())


if __name__ == "__main__":
    unittest.main()
