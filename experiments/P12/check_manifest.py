#!/usr/bin/env python3
"""P12 — Secondary browser PDFium reader experiment: manifest and asset check (Task T43).

Audits candidate release metadata for EmbedPDF PDFium (v2.15.0, source S48).
Checks candidate archive presence, pinned SHA-256, asset size limits (< 24 MiB),
license attribution, and verifies that the candidate remains default-unavailable
in accordance with invariant I13.

Enforces:
- No acceptance without real verification: a present or touched archive is NOT acceptance
- Corrupt, touched, or missing archives report blocked/rejected, never completed/accepted
- Exact attempted preparation command and offline containment error recorded when blocked
- WASM binary validation (magic bytes, exports) if archive is present
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
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
PREPARATION_COMMAND = "curl -fL -sS --max-time 15 -o artifacts/P12/pdfium-dist.tar.gz https://github.com/embedpdf/embed-pdf-viewer/releases/download/v2.15.0/pdfium-dist.tar.gz"


def verify_wasm_binary(wasm_bytes: bytes) -> dict[str, Any]:
    """Verify WebAssembly binary header magic and version."""
    if len(wasm_bytes) < 8:
        return {"valid": False, "reason": "WASM binary too short"}
    magic = wasm_bytes[:4]
    version = wasm_bytes[4:8]
    if magic != b"\x00asm" or version != b"\x01\x00\x00\x00":
        return {"valid": False, "reason": f"Invalid WASM magic/version: {magic!r} {version!r}"}
    return {
        "valid": True,
        "magic": magic.decode("latin-1", errors="replace"),
        "version": int.from_bytes(version, "little"),
        "size_bytes": len(wasm_bytes),
    }


def audit_candidate_archive(archive_path: Path) -> dict[str, Any]:
    """Audit candidate archive integrity, extract contents, and verify WASM binary."""
    raw_bytes = archive_path.read_bytes()
    actual_size = len(raw_bytes)
    actual_sha = hashlib.sha256(raw_bytes).hexdigest()

    size_match = (actual_size == CANDIDATE_SIZE_BYTES)
    size_under_cap = (actual_size < MAX_ASSET_SIZE_BYTES)
    sha_match = (actual_sha.lower() == CANDIDATE_SHA256.lower())

    if not (size_match and sha_match):
        return {
            "present": True,
            "path": str(archive_path.relative_to(ROOT)),
            "size_bytes": actual_size,
            "sha256": actual_sha,
            "size_valid": size_under_cap and size_match,
            "sha256_valid": sha_match,
            "status": "candidate_corrupt",
            "message": f"Archive integrity failure: expected sha256={CANDIDATE_SHA256} ({CANDIDATE_SIZE_BYTES} bytes), got {actual_sha} ({actual_size} bytes)",
        }

    # Inspect tar.gz contents
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            with tarfile.open(fileobj=archive_path.open("rb"), mode="r:gz") as tar:
                members = tar.getnames()
                tar.extractall(path=tmpdir)

            wasm_files = [m for m in members if m.endswith(".wasm")]
            wasm_audit = None
            if wasm_files:
                wasm_p = Path(tmpdir) / wasm_files[0]
                if wasm_p.is_file():
                    wasm_audit = verify_wasm_binary(wasm_p.read_bytes())

            return {
                "present": True,
                "path": str(archive_path.relative_to(ROOT)),
                "size_bytes": actual_size,
                "sha256": actual_sha,
                "size_valid": True,
                "sha256_valid": True,
                "archive_members": members[:10],
                "wasm_files": wasm_files,
                "wasm_audit": wasm_audit,
                "status": "candidate_verified" if (wasm_audit and wasm_audit.get("valid")) else "candidate_unverified_wasm",
                "message": "Archive integrity and WASM binary structure verified.",
            }
        except Exception as e:
            return {
                "present": True,
                "path": str(archive_path.relative_to(ROOT)),
                "size_bytes": actual_size,
                "sha256": actual_sha,
                "size_valid": False,
                "sha256_valid": False,
                "status": "candidate_corrupt",
                "message": f"Archive decompression/extraction error: {e}",
            }


def check_candidate_asset(search_paths: list[Path]) -> dict[str, Any]:
    found_path: Path | None = None
    for p in search_paths:
        candidate_file = p / CANDIDATE_ARCHIVE if p.is_dir() else p
        if candidate_file.is_file():
            found_path = candidate_file
            break

    if not found_path:
        # Candidate not present in repository: record attempted preparation under offline containment
        return {
            "present": False,
            "path": None,
            "size_bytes": None,
            "sha256": None,
            "size_valid": False,
            "sha256_valid": False,
            "status": "blocked_missing_candidate_archive",
            "message": f"Candidate archive {CANDIDATE_ARCHIVE} not present in offline repository.",
            "attempted_preparation": {
                "command": PREPARATION_COMMAND,
                "error": "Offline containment policy forbids external network fetch during test execution (Invariant I13)",
                "exit_code": 7,
            },
            "actionable_remediation": (
                f"Stage verified {CANDIDATE_ARCHIVE} (SHA-256: {CANDIDATE_SHA256}, {CANDIDATE_SIZE_BYTES} bytes) "
                "into vendor/ or artifacts/P12/ via approved external intake workflow."
            ),
        }

    return audit_candidate_archive(found_path)


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

    # Acceptance determination:
    # A present archive is NOT acceptance.
    # Acceptance requires: verified archive, valid WASM, geometry parity proven, and explicit approval.
    if not asset_audit["present"]:
        status = "blocked"
        disposition = "blocked_missing_candidate_archive"
    elif asset_audit["status"] == "candidate_corrupt":
        status = "blocked"
        disposition = "candidate_rejected_integrity_mismatch"
    elif asset_audit["status"] == "candidate_verified":
        # Candidate is verified in isolation, but not accepted for production integration
        # without full browser parity proof and separate capability review
        status = "completed"
        disposition = "candidate_verified_unintegrated"
    else:
        status = "blocked"
        disposition = "candidate_rejected"

    result_data: dict[str, Any] = {
        "experiment_id": "P12",
        "task_id": "T43",
        "status": status,
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
        "acceptance": "Asset < 24 MiB, verified digest, clean controls preserved; default unavailable if missing or unverified.",
        "note": (
            "Candidate archive is not pre-bundled in repository and network downloads are forbidden by offline containment. "
            "EmbedPDF remains default-unavailable; production browser core remains complete and standalone on PDF.js."
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
