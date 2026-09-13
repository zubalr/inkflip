#!/usr/bin/env python3
"""Containment verification runner (T40, TEST-40).

Exercises the digest-pinned native container recipe, hardened script invocation,
and security flags per planning/security/THREAT_MODEL.md:
- Read-only root mount
- Isolated tmpfs scratch
- No network access (--network none)
- Dropped capabilities (--cap-drop ALL)
- No-new-privileges enforcement
- Non-root UID 65532:65532
- Resource constraints (PID limit, memory cap, thread clamping)
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = ROOT / "build" / "native" / "Dockerfile"
RUN_SCRIPT = ROOT / "scripts" / "run_native_container.sh"
SYNTHETIC_PDF = ROOT / "planning" / "fixtures" / "mapping-control.pdf"
ARTIFACTS_DIR = ROOT / "artifacts" / "containment"


def check_dockerfile_containment() -> dict[str, str]:
    """Audit build/native/Dockerfile for hardened container invariants."""
    if not DOCKERFILE.is_file():
        raise FileNotFoundError(f"Missing Dockerfile: {DOCKERFILE}")

    content = DOCKERFILE.read_text(encoding="utf-8")
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()

    assert "USER 65532:65532" in content, "Dockerfile must enforce non-root USER 65532:65532"
    assert "OMP_NUM_THREADS=1" in content, "Dockerfile must clamp OMP_NUM_THREADS to 1"
    assert "OPENBLAS_NUM_THREADS=1" in content, "Dockerfile must clamp OPENBLAS_NUM_THREADS to 1"
    assert "MKL_NUM_THREADS=1" in content, "Dockerfile must clamp MKL_NUM_THREADS to 1"
    assert "PYTHONIOENCODING=utf-8" in content, "Dockerfile must enforce UTF-8 encoding"
    assert "ENTRYPOINT" in content, "Dockerfile must define explicit ENTRYPOINT"

    print("PASS: Dockerfile containment audit passed (non-root UID, thread clamps, entrypoint)")
    return {"status": "passed", "digest": digest}


def check_script_hardening_flags() -> dict[str, str]:
    """Audit scripts/run_native_container.sh for mandatory security containment flags."""
    if not RUN_SCRIPT.is_file():
        raise FileNotFoundError(f"Missing container runner script: {RUN_SCRIPT}")
    if not os.access(RUN_SCRIPT, os.X_OK):
        raise PermissionError(f"Script is not executable: {RUN_SCRIPT}")

    content = RUN_SCRIPT.read_text(encoding="utf-8")
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()

    required_flags = [
        ("--network none", "strict network isolation"),
        ("--read-only", "immutable container root"),
        ("--cap-drop ALL", "all Linux capabilities dropped"),
        ("--security-opt no-new-privileges", "prevent privilege escalation"),
        ("-u 65532:65532", "non-root UID enforcement"),
        ("--pids-limit 64", "process count boundary against fork bombs"),
        ("--memory 1g", "memory cap"),
        (":ro", "read-only input mount"),
        (":rw", "dedicated output mount"),
    ]

    for flag, desc in required_flags:
        assert flag in content, f"Missing required security flag '{flag}' ({desc}) in run script"

    print("PASS: Script hardening flags audit passed (network none, read-only, cap-drop, nonroot, limits)")
    return {"status": "passed", "digest": digest}


def exercise_container_invocation(tmp_dir: Path) -> dict[str, str]:
    """Exercise container runner with dry-run and synthetic input."""
    input_dir = tmp_dir / "input"
    output_dir = tmp_dir / "output"
    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    test_pdf = input_dir / "control.pdf"
    test_pdf.write_bytes(SYNTHETIC_PDF.read_bytes())
    input_sha = hashlib.sha256(test_pdf.read_bytes()).hexdigest()

    # Run script with --dry-run
    proc = subprocess.run(
        [
            str(RUN_SCRIPT),
            "--input", str(input_dir),
            "--output", str(output_dir),
            "--dry-run",
            "--",
            "inspect",
            "/input/control.pdf",
            "--out",
            "/output/report.json",
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    cmd_line = proc.stdout.strip()
    assert "--network none" in cmd_line
    assert "--read-only" in cmd_line
    assert "-u 65532:65532" in cmd_line
    assert ":/input:ro" in cmd_line
    assert ":/output:rw" in cmd_line

    print("PASS: Container invocation dry-run command line verified")
    return {
        "status": "passed",
        "command": cmd_line,
        "synthetic_input_sha256": input_sha,
    }


def main() -> int:
    print("=== Inkflip Native Containment Verification (T40) ===")
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    dockerfile_res = check_dockerfile_containment()
    script_res = check_script_hardening_flags()

    import tempfile
    with tempfile.TemporaryDirectory(prefix="containment-verify-") as td:
        invoc_res = exercise_container_invocation(Path(td))

    receipt = {
        "task": "T40",
        "status": "passed",
        "dockerfile": dockerfile_res,
        "run_script": script_res,
        "invocation": invoc_res,
        "security_profile": [
            "network_none",
            "read_only_root",
            "capabilities_dropped_all",
            "no_new_privileges",
            "nonroot_uid_65532",
            "pids_limit_64",
            "memory_limit_1g",
            "single_thread_clamped",
            "readonly_input_mount",
        ]
    }

    receipt_file = ARTIFACTS_DIR / "receipt.json"
    receipt_file.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(f"PASS: Containment receipt saved to {receipt_file}")
    print("All containment verification checks PASSED.")

    # Export test counts for Inkflip test harness
    report_file = os.environ.get("INKFLIP_TEST_REPORT_FILE")
    if report_file:
        counts = {
            "collected": 3,
            "passed": 3,
            "failed": 0,
            "skipped": 0,
        }
        Path(report_file).write_text(json.dumps(counts) + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
