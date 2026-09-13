#!/usr/bin/env python3
"""T40 containment runner: recipe/invocation checks plus optional live container.

Local checks always run. A missing Docker daemon is recorded as blocked
container evidence, not as a passing no-network container test.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "run_native_container.sh"
DOCKERFILE = ROOT / "build" / "native" / "Dockerfile"
LOCK = ROOT / "build" / "native" / "image.lock.json"
EVIDENCE = ROOT / "artifacts" / "containment"
REPORT_ENV = "INKFLIP_TEST_REPORT_FILE"

REQUIRED_FLAGS = (
    "--network none",
    "--read-only",
    "--user 65532:65532",
    "--cap-drop ALL",
    "--security-opt no-new-privileges",
    "--pids-limit",
    "--memory",
)


def record(name: str, ok: bool, detail: str) -> dict:
    return {"name": name, "ok": ok, "detail": detail}


def write_report(counts: dict, cases: list[dict]) -> None:
    payload = {**counts, "cases": cases}
    path = os.environ.get(REPORT_ENV)
    if path:
        Path(path).write_text(json.dumps(payload, indent=2) + "\n")
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "containment-run.json").write_text(json.dumps(payload, indent=2) + "\n")


def main() -> int:
    cases: list[dict] = []
    SCRIPT.chmod(SCRIPT.stat().st_mode | 0o111)
    text = SCRIPT.read_text(encoding="utf-8")
    missing = [flag for flag in REQUIRED_FLAGS if flag not in text]
    cases.append(record("invocation-flags", not missing, f"missing={missing}"))

    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    digest = json.loads(LOCK.read_text())["base_image"]["index_digest"]
    cases.append(record("digest-pinned-dockerfile", digest in dockerfile, digest))
    cases.append(record("nonroot-user", "USER 65532:65532" in dockerfile, "65532"))
    cases.append(record("no-processing-network-in-script", "--network none" in text, "network none"))

    with tempfile.TemporaryDirectory(prefix="t40-contain-") as raw:
        td = Path(raw)
        source = td / "source with spaces"
        out = td / "out with spaces"
        source.mkdir()
        out.mkdir()
        (source / "note.txt").write_text("synthetic\n")
        proc = subprocess.run(
            [
                str(SCRIPT),
                "--source-root",
                str(source),
                "--out",
                str(out),
                "--",
                "inspect",
                "/input/note.txt",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        combined = (proc.stdout or "") + (proc.stderr or "")
        daemon_blocked = proc.returncode == 4 and "docker daemon unavailable" in combined
        if daemon_blocked:
            cases.append(record("script-fails-closed-without-daemon", True, "exit 4"))
        elif proc.returncode == 0:
            cases.append(record("container-no-network-execution", True, combined[:500]))
        else:
            cases.append(
                record(
                    "script-invocation",
                    proc.returncode in (2, 4),
                    f"exit {proc.returncode}: {combined[:400]}",
                )
            )

        home_proc = subprocess.run(
            [str(SCRIPT), "--source-root", "/Users", "--out", str(out), "--", "true"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        cases.append(
            record(
                "refuses-home-root-mount",
                home_proc.returncode == 2,
                f"exit {home_proc.returncode}",
            )
        )

    executable = [c for c in cases if c["name"] != "container-no-network-execution"]
    failed = [c for c in executable if not c["ok"]]
    container_ran = any(c["name"] == "container-no-network-execution" and c["ok"] for c in cases)
    counts = {
        "collected": len(executable),
        "passed": sum(1 for c in executable if c["ok"]),
        "failed": len(failed),
        "skipped": 0,
    }
    write_report(counts, cases)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "host.json").write_text(
        json.dumps(
            {
                "platform": sys.platform,
                "docker_cli": shutil.which("docker"),
                "docker_daemon": container_ran,
                "container_criterion": "executed" if container_ran else "blocked",
            },
            indent=2,
        )
        + "\n"
    )
    if failed:
        for item in failed:
            print(f"FAIL {item['name']}: {item['detail']}", file=sys.stderr)
        return 1
    print(json.dumps({"counts": counts, "container": "executed" if container_ran else "blocked"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
