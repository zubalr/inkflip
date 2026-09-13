"""P12 manifest status must not treat archive staging as experiment completion."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from check_manifest import (
    check_candidate_asset,
    decide_manifest_status,
)


class TestP12ManifestStatus(unittest.TestCase):
    def test_missing_archive_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            audit = check_candidate_asset([Path(tmp)])
        status, disposition = decide_manifest_status(audit)
        self.assertFalse(audit["present"])
        self.assertEqual(status, "blocked")
        self.assertEqual(disposition, "blocked_missing_candidate_archive")
        self.assertNotEqual(status, "completed")

    def test_verified_archive_is_staged_not_completed(self) -> None:
        """Archive digest proof is staging. Complementary-gain / browser API is not implied."""
        status, disposition = decide_manifest_status(
            {"present": True, "status": "candidate_verified"}
        )
        self.assertEqual(status, "staged")
        self.assertEqual(disposition, "candidate_archive_verified_pending_browser")
        self.assertNotEqual(status, "completed")
        self.assertNotEqual(disposition, "candidate_verified_unintegrated")

    def test_corrupt_archive_is_rejected(self) -> None:
        status, disposition = decide_manifest_status(
            {"present": True, "status": "candidate_corrupt"}
        )
        self.assertEqual(status, "blocked")
        self.assertEqual(disposition, "candidate_rejected_integrity_mismatch")

    def test_live_check_manifest_json_never_writes_completed_for_archive_only(self) -> None:
        root = Path(__file__).resolve().parents[2]
        result_path = root / "artifacts" / "P12" / "result.json"
        if not result_path.is_file():
            self.skipTest("check_manifest has not written artifacts/P12/result.json yet")
        data = json.loads(result_path.read_text(encoding="utf-8"))
        if data.get("candidate", {}).get("audit", {}).get("status") == "candidate_verified":
            browser_eval = root / "artifacts" / "P12" / "browser_evaluation.json"
            if not browser_eval.is_file():
                self.assertNotEqual(data.get("status"), "completed")


if __name__ == "__main__":
    unittest.main()
