"""g78.2 semantic regression tests for the new fixture families.

Executes the consumer side of each fixture: canonical-schema validation and
failure-stage separation for F22, baseline-rule execution for F23, digest
verification for the executable F26 cache tree, rendered-ink/geometry proof
for F24, extraction mapping behavior for F13/F14. Read-only over fixtures/.
"""
from __future__ import annotations

import hashlib
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NATIVE = ROOT / "native"
FIXTURES = ROOT / "fixtures"

sys.path.insert(0, str(NATIVE))

import jsonschema  # noqa: E402

SCHEMA = json.loads((NATIVE / "inkflip/contracts/schema/inkflip.schema.json").read_text())
SOURCE_DIGEST = "a" * 64  # document digest the F22/F23 fixtures are bound to


def payload(name: str) -> dict:
    return json.loads((FIXTURES / "development" / name).read_text())


def subdoc_validator(def_name: str) -> jsonschema.Draft202012Validator:
    """Validator for one canonical $defs sub-document (Report, Baseline,
    AcceptanceRules) with the full $defs available for $ref resolution."""
    return jsonschema.Draft202012Validator(
        {"$ref": f"#/$defs/{def_name}", "$defs": SCHEMA["$defs"]}
    )


def report_validator() -> jsonschema.Draft202012Validator:
    return subdoc_validator("Report")


def rules_errors(report: dict, rules_doc: dict) -> list[str]:
    """Minimal deterministic baseline-rule interpreter over the fixture
    context: binding stage first, then per-rule occurrence-count checks."""
    errors = []
    if report["document"]["sha256"] != rules_doc["rules"][0]["document_sha256"]:
        return ["binding: report document digest does not match the baseline"]
    checks = {c["id"]: c for c in report["checks"]}
    for rule in rules_doc["rules"]:
        # Fixture convention: rule-<name> binds the check-<name> result.
        check = checks.get(rule["id"].replace("rule-", "check-", 1))
        if check is None:
            errors.append(f"coverage: required check {rule['id']} is missing")
        elif check["produced_occurrence_count"] != rule["expected_count"]:
            errors.append(
                f"count: {rule['id']} produced "
                f"{check['produced_occurrence_count']} != expected {rule['expected_count']}"
            )
    return errors


class TestF22ImportStages(unittest.TestCase):
    """Each hostile variant is rejected at its intended validation stage; the
    inert script text proves display-stage separation from schema checking."""

    def test_control_is_canonical_schema_valid(self):
        report = payload("import-security-control.json")
        report_validator().validate(report)
        self.assertEqual(report["document"]["sha256"], SOURCE_DIGEST)

    def test_unknown_key_is_rejected_at_the_schema_stage(self):
        report = payload("import-security-unknown-key.json")
        errors = list(report_validator().iter_errors(report))
        self.assertTrue(errors, "closed schema must reject the unknown key")

    def test_script_string_is_schema_valid_and_inert(self):
        report = payload("import-security-script-string.json")
        report_validator().validate(report)
        self.assertIn("<script>", report["limitations"][0])

    def test_digest_mismatch_passes_schema_fails_binding(self):
        report = payload("import-security-digest-mismatch.json")
        report_validator().validate(report)
        self.assertNotEqual(report["document"]["sha256"], SOURCE_DIGEST)

    def test_png_oversized_exceeds_any_pixel_budget(self):
        data = (FIXTURES / "development/import-security-png-oversized.png").read_bytes()
        width, height = struct.unpack(">II", data[16:24])
        self.assertGreater(width * height, 40_000_000)

    def test_png_truncated_is_undecodable(self):
        data = (FIXTURES / "development/import-security-png-truncated.png").read_bytes()
        self.assertLess(len(data), 16 + 13)  # IHDR cannot be complete


class TestF23BaselineRules(unittest.TestCase):
    """Rule-stage behavior: unchanged accepted; each declared fault fires.
    Every variant's three sub-documents must validate against the canonical
    schema ($defs/Report, $defs/Baseline, $defs/AcceptanceRules) — the
    expectation claims "all schema-valid" and this suite exercises it."""

    @staticmethod
    def errors_for(variant: str) -> list[str]:
        fixture = payload(f"baseline-misuse-{variant}.json")
        subdoc_validator("Report").validate(fixture["report"])
        subdoc_validator("Baseline").validate(fixture["baseline"])
        subdoc_validator("AcceptanceRules").validate(fixture["rules"])
        return rules_errors(fixture["report"], fixture["rules"])

    def test_every_subdocument_is_canonical_schema_valid(self):
        for variant in ("control", "coverage-loss", "mismatched-doc",
                        "silent-refresh"):
            fixture = payload(f"baseline-misuse-{variant}.json")
            for def_name, key in (("Report", "report"),
                                  ("Baseline", "baseline"),
                                  ("AcceptanceRules", "rules")):
                errors = list(
                    subdoc_validator(def_name).iter_errors(fixture[key]))
                self.assertEqual(errors, [],
                                 f"{variant}/{key} fails $defs/{def_name}: "
                                 f"{[e.message for e in errors]}")

    def test_control_passes_every_rule(self):
        self.assertEqual(self.errors_for("control"), [])

    def test_coverage_loss_fires_the_missing_check(self):
        errors = self.errors_for("coverage-loss")
        self.assertTrue(any("coverage" in e for e in errors), errors)

    def test_mismatched_doc_fails_the_binding_stage(self):
        errors = self.errors_for("mismatched-doc")
        self.assertTrue(any("binding" in e for e in errors), errors)

    def test_silent_refresh_fires_the_count_rule(self):
        errors = self.errors_for("silent-refresh")
        self.assertTrue(any("count" in e for e in errors), errors)


class TestF26CacheVerification(unittest.TestCase):
    """Executable cache-tree faults: materialize, recompute digests, compare
    against the manifest's declared requirements."""

    @staticmethod
    def verify(variant: str) -> tuple[bool, list[str]]:
        cache_fixture = payload(f"asset-cache-{variant}.json")
        manifest = cache_fixture["manifest"]
        files = cache_fixture.get("files")
        problems = []
        if files is None:
            return False, ["offline-cold: no cache files present"]
        with tempfile.TemporaryDirectory() as folder:
            for name, info in files.items():
                target = Path(folder) / name
                target.write_bytes(bytes.fromhex(info["content_hex"]))
            required = {
                "model.bin": manifest["required"]["model.sha256"],
                "worker.bin": manifest["required"]["worker.sha256"],
                "core.bin": manifest["required"]["core.sha256"],
            }
            for name, declared in required.items():
                data = (Path(folder) / name).read_bytes()
                actual = hashlib.sha256(data).hexdigest()
                if actual != declared:
                    problems.append(f"{name}: digest mismatch")
        return (not problems, problems)

    def test_control_cache_verifies(self):
        ok, problems = self.verify("control")
        self.assertTrue(ok, problems)

    def test_corrupt_model_fails_digest_verification(self):
        ok, problems = self.verify("corrupt-model")
        self.assertFalse(ok)
        self.assertTrue(any("model" in p for p in problems), problems)

    def test_stale_worker_fails_digest_verification(self):
        ok, problems = self.verify("stale-worker")
        self.assertFalse(ok)
        self.assertTrue(any("worker" in p for p in problems), problems)

    def test_stale_core_fails_digest_verification(self):
        ok, problems = self.verify("stale-core")
        self.assertFalse(ok)
        self.assertTrue(any("core" in p for p in problems), problems)

    def test_offline_cold_reports_missing_files(self):
        ok, problems = self.verify("offline-cold")
        self.assertFalse(ok)
        self.assertTrue(any("cold" in p for p in problems), problems)

    def test_offline_warm_verifies(self):
        ok, problems = self.verify("offline-warm")
        self.assertTrue(ok, problems)


class TestF24OverlapInk(unittest.TestCase):
    """Rendered proof: the border's visible ink lies inside the invisible
    text's occurrence bounds in both fixtures, while the recorded render
    modes differ (3 invisible vs 0 fill) — no verdict is derivable."""

    TEXT_BOX = (50, 110, 97, 128)  # canonical points
    PAGE = (320, 240)
    SCALE = 4

    def _render_bytes(self, path: Path) -> bytes:
        from pypdfium2 import PdfDocument

        doc = PdfDocument(path.read_bytes())
        page = doc[0]
        bitmap = page.render(scale=self.SCALE)
        pixels = bitmap.to_pil().convert("L").tobytes()
        width = bitmap.width if hasattr(bitmap, "width") else self.PAGE[0] * self.SCALE
        doc.close()
        return pixels, width

    def _ink_in_text_box(self, fixture: str):
        pixels, width = self._render_bytes(FIXTURES / "development" / fixture)
        x0, y0, x1, y1 = self.TEXT_BOX
        px0, py0 = int(x0 * self.SCALE), int((self.PAGE[1] - y1) * self.SCALE)
        px1, py1 = int(x1 * self.SCALE), int((self.PAGE[1] - y0) * self.SCALE)
        dark = 0
        for py in range(max(0, py0), min(py1, len(pixels) // width)):
            for px in range(max(0, px0), min(px1, width)):
                if pixels[py * width + px] < 200:
                    dark += 1
        return dark

    def test_border_ink_inside_invisible_text_bounds_and_modes_differ(self):
        import pypdfium2
        import pypdfium2.raw as raw

        invisible_ink = self._ink_in_text_box("overlap-ink-invisible.pdf")
        visible_ink = self._ink_in_text_box("overlap-ink-control.pdf")
        self.assertGreater(invisible_ink, 0,
                           "border ink must cross the invisible text bounds")
        self.assertGreater(visible_ink, 0)
        modes = {}
        for name in ("invisible", "control"):
            doc = pypdfium2.PdfDocument(
                (FIXTURES / "development" / f"overlap-ink-{name}.pdf").read_bytes())
            page = doc[0]
            modes[name] = raw.FPDFTextObj_GetTextRenderMode(
                raw.FPDFPage_GetObject(page.raw, 1))
            doc.close()
        self.assertEqual(modes["invisible"], 3)
        self.assertEqual(modes["control"], 0)


class TestF13F14Extraction(unittest.TestCase):
    """Constant painted glyph with map-driven extraction; Latin Identity-H
    mechanism extracts its declared logical strings."""

    def _extract(self, path: Path) -> str:
        from pypdfium2 import PdfDocument

        doc = PdfDocument(path.read_bytes())
        page = doc[0]
        tp = page.get_textpage()
        count = tp.count_chars()
        text = tp.get_text_range(0, count) if count else ""
        tp.close()
        page.close()
        doc.close()
        return text

    def test_expansion_extracts_fi_control_extracts_painted_char(self):
        expansion = self._extract(FIXTURES / "development/ligatures-expansion.pdf")
        control = self._extract(FIXTURES / "development/ligatures-control.pdf")
        self.assertEqual(expansion, "fi")
        self.assertEqual(control, "\u00a1")

    def test_latin_identity_h_extracts_declared_strings(self):
        text = self._extract(FIXTURES / "development/native-unicode-native.pdf")
        self.assertEqual(text, "$100")


if __name__ == "__main__":
    unittest.main()
