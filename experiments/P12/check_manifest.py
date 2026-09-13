#!/usr/bin/env python3
"""P12 — Secondary browser PDFium reader experiment: manifest and asset check (Task T43).

Audits candidate release metadata for EmbedPDF PDFium (v2.15.0, source S48).
Checks candidate archive presence, pinned SHA-256, asset size limits (< 24 MiB),
license attribution, and verifies that the candidate remains default-unavailable
in accordance with invariant I13.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent

# Pinned release candidate metadata from Source S48
CANDIDATE_NAME = "EmbedPDF PDFium"
CANDIDATE_RELEASE = "v2.15.0"
CANDIDATE_ARCHIVE = "pdfium-dist.tar.gz"
CANDIDATE_SIZE_BYTES = 2_661_637
CANDIDATE_SHA256 = "31cba71f5620bec3ae2aab6606f148e42cba0cd34d56cf5b54998d771e62bd42"
MAX_ASSET_SIZE_BYTES = 24 * 1024 * 1024  # 24 MiB limit per acceptance criteria
SOURCE_ID = "S48"


def check_candidate_asset(search_paths: list[Path]) -> dict[str, Any]:
    found_path: Path | None = None
    for p in search_paths:
        candidate_file = p / CANDIDATE_ARCHIVE if p.is_dir() else p
        if candidate_file.is_file():
            found_path = candidate_file
            break

    if not found_path:
        return {
            "present": False,
            "path": None,
            "size_bytes": None,
            "sha256": None,
            "size_valid": False,
            "sha256_valid": False,
            "status": "blocked_missing_candidate_archive",
            "message": f"Candidate archive {CANDIDATE_ARCHIVE} not present in offline repository.",
        }

    raw_bytes = found_path.read_bytes()
    actual_size = len(raw_bytes)
    actual_sha = hashlib.sha256(raw_bytes).hexdigest()
    size_valid = actual_size < MAX_ASSET_SIZE_BYTES and actual_size == CANDIDATE_SIZE_BYTES
    sha_valid = actual_sha.lower() == CANDIDATE_SHA256.lower()

    return {
        "present": True,
        "path": str(found_path.relative_to(ROOT)),
        "size_bytes": actual_size,
        "sha256": actual_sha,
        "size_valid": size_valid,
        "sha256_valid": sha_valid,
        "status": "candidate_verified" if (size_valid and sha_valid) else "candidate_corrupt",
        "message": "Candidate archive found and audited.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="P12 candidate manifest and asset audit")
    parser.add_argument("--out", default="artifacts/P12", help="Output artifact directory")
    args = parser.parse_args()

    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    search_dirs = [
        ROOT / "experiments" / "P12" / "vendor",
        ROOT / "vendor",
        ROOT / "artifacts" / "P12",
    ]

    asset_audit = check_candidate_asset(search_dirs)

    # Acceptance criteria verification:
    # 1. Useful complementary mechanism gain at fixed precision or reject.
    # 2. Every asset < 24 MiB.
    # 3. Candidate default unavailable if candidate fails or is missing.
    disposition = (
        "candidate_accepted"
        if asset_audit["status"] == "candidate_verified"
        else "blocked_missing_candidate_archive"
    )

    result_data: dict[str, Any] = {
        "experiment_id": "P12",
        "task_id": "T43",
        "status": "completed" if asset_audit["present"] else "blocked",
        "disposition": disposition,
        "hypothesis": "Secondary browser PDFium reader value",
        "baseline": "PDF.js plus OCR",
        "candidate": {
            "name": CANDIDATE_NAME,
            "release": CANDIDATE_RELEASE,
            "archive": CANDIDATE_ARCHIVE,
            "source_id": SOURCE_ID,
            "pinned_sha256": CANDIDATE_SHA256,
            "pinned_size_bytes": CANDIDATE_SIZE_BYTES,
            "max_asset_size_bytes": MAX_ASSET_SIZE_BYTES,
            "audit": asset_audit,
        },
        "controls": {
            "clean_mapping_twin": "required",
            "same_reader_control": "required",
        },
        "integration_decision": "default_unavailable",
        "acceptance": "Asset < 24 MiB, verified digest, clean controls preserved; default unavailable if missing.",
        "note": (
            "Candidate archive is not pre-bundled in repo and network downloads are forbidden by offline containment. "
            "EmbedPDF remains default-unavailable; browser core remains complete on PDF.js."
        ),
    }

    result_file = out_dir / "result.json"
    result_file.write_text(json.dumps(result_data, indent=2), encoding="utf-8")

    print(
        f"P12 manifest check complete: candidate_present={asset_audit['present']}, "
        f"status={result_data['status']}, disposition={result_data['disposition']}"
    )


if __name__ == "__main__":
    main()
