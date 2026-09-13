#!/usr/bin/env python3
"""T40 containment runner: recipe/invocation checks plus optional live container.

Local checks always run. A missing Docker daemon is recorded as blocked
container evidence, not as a passing no-network container test.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "run_native_container.sh"
DOCKERFILE = ROOT / "build" / "native" / "Dockerfile"
DOCKERFILE_CHECKOUT = ROOT / "build" / "native" / "Dockerfile.checkout"
LOCK = ROOT / "build" / "native" / "image.lock.json"
EVIDENCE = ROOT / "artifacts" / "containment"
FIXTURE = ROOT / "fixtures" / "public" / "mapping-control.pdf"
REPORT_ENV = "INKFLIP_TEST_REPORT_FILE"
IMAGE_TAG = "inkflip-native:t40"

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


def docker_ok() -> tuple[bool, str]:
    if not shutil.which("docker"):
        return False, "docker executable not found"
    proc = subprocess.run(["docker", "info"], capture_output=True, text=True)
    if proc.returncode != 0:
        return False, (proc.stderr or proc.stdout or "docker info failed")[:400]
    return True, "docker info ok"


def docker_arch() -> dict:
    inspect = subprocess.run(
        ["docker", "info", "--format", "{{.Architecture}} {{.OSType}}"],
        capture_output=True,
        text=True,
    )
    host = platform.machine()
    reported = (inspect.stdout or "").strip()
    emulated = False
    if "x86_64" in reported or "amd64" in reported:
        emulated = host in {"arm64", "aarch64"}
    return {
        "host_machine": host,
        "docker_architecture_line": reported,
        "emulated": emulated,
        "note": "linux/arm64 is native on Apple Silicon OrbStack; linux/amd64 would be emulated",
    }


def build_checkout_image() -> tuple[bool, str]:
    proc = subprocess.run(
        [
            "docker",
            "build",
            "-f",
            str(DOCKERFILE_CHECKOUT),
            "-t",
            IMAGE_TAG,
            ".",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    log = ((proc.stdout or "") + (proc.stderr or ""))[-1500:]
    return proc.returncode == 0, log


def restricted_docker(
    extra: list[str],
    *,
    source: Path,
    out: Path,
    entrypoint: list[str] | None = None,
    timeout: int = 30,
    name: str | None = None,
) -> subprocess.CompletedProcess:
    cmd = [
        "docker",
        "run",
        "--rm",
    ]
    if name:
        cmd.extend(["--name", name])
    cmd.extend(
        [
            "--network",
            "none",
            "--read-only",
            "--user",
            "65532:65532",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--pids-limit",
            "64",
            "--memory",
            "512m",
            "--cpus",
            "1",
            "--tmpfs",
            "/tmp:rw,exec,nosuid,size=64m",
            "--mount",
            f"type=bind,src={source},dst=/input,readonly",
            "--mount",
            f"type=bind,src={out},dst=/output",
            "--tmpfs",
            "/scratch:rw,exec,nosuid,size=64m",
            "-e",
            "HOME=/tmp",
            "-e",
            "TMPDIR=/scratch",
            "-w",
            "/output",
        ]
    )
    if entrypoint:
        cmd.extend(["--entrypoint", entrypoint[0]])
        cmd.append(IMAGE_TAG)
        cmd.extend(entrypoint[1:])
        cmd.extend(extra)
    else:
        cmd.append(IMAGE_TAG)
        cmd.extend(extra)
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        if name:
            subprocess.run(["docker", "rm", "-f", name], capture_output=True, text=True)
        raise


def live_container_cases(source: Path, out: Path) -> list[dict]:
    cases: list[dict] = []
    built, build_log = build_checkout_image()
    cases.append(record("checkout-image-build", built, build_log[:500]))
    if not built:
        return cases

    inspect = subprocess.run(
        [
            str(SCRIPT),
            "--source-root",
            str(source),
            "--out",
            str(out),
            "--image",
            IMAGE_TAG,
            "--",
            "inspect",
            "/input/mapping-control.pdf",
            "--out",
            "/output/report.json",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    combined = (inspect.stdout or "") + (inspect.stderr or "")
    report = out / "report.json"
    ok = inspect.returncode == 0 and report.is_file()
    cases.append(record("container-no-network-execution", ok, combined[-500:]))
    if report.is_file():
        cases.append(record("retained-unrelated-output", True, str(report)))
        before = report.read_bytes()
    else:
        before = b""

    try:
        uid = restricted_docker(
            [],
            source=source,
            out=out,
            entrypoint=["python", "-c", "import os; print(os.getuid())"],
        )
        cases.append(
            record(
                "container-nonroot-uid",
                uid.returncode == 0 and uid.stdout.strip() == "65532",
                (uid.stdout + uid.stderr)[:200],
            )
        )
    except subprocess.TimeoutExpired as exc:
        cases.append(record("container-nonroot-uid", False, f"timeout {exc}"))

    try:
        net = restricted_docker(
            [],
            source=source,
            out=out,
            entrypoint=[
                "python",
                "-c",
                "import socket; socket.create_connection(('1.1.1.1', 80), 2)",
            ],
            timeout=10,
        )
        blocked = net.returncode != 0
        cases.append(record("container-no-egress", blocked, (net.stdout + net.stderr)[-300:]))
    except subprocess.TimeoutExpired:
        cases.append(record("container-no-egress", True, "connect timed out under --network none"))

    try:
        write_input = restricted_docker(
            [],
            source=source,
            out=out,
            entrypoint=["python", "-c", "open('/input/escape.txt','w').write('nope')"],
        )
        cases.append(
            record(
                "container-readonly-input",
                write_input.returncode != 0,
                (write_input.stdout + write_input.stderr)[-300:],
            )
        )
    except subprocess.TimeoutExpired as exc:
        cases.append(record("container-readonly-input", False, f"timeout {exc}"))

    try:
        crash = restricted_docker(
            [],
            source=source,
            out=out,
            entrypoint=["python", "-c", "import os; os._exit(99)"],
        )
        cases.append(record("container-crash-injection", crash.returncode == 99, f"exit {crash.returncode}"))
    except subprocess.TimeoutExpired as exc:
        cases.append(record("container-crash-injection", False, f"timeout {exc}"))

    try:
        hang = restricted_docker(
            [],
            source=source,
            out=out,
            entrypoint=["python", "-c", "import time; time.sleep(60)"],
            timeout=5,
            name="inkflip-t40-hang",
        )
        cases.append(record("container-hang-injection", False, f"exit {hang.returncode} (expected timeout)"))
    except subprocess.TimeoutExpired:
        cases.append(record("container-hang-injection", True, "killed after 5s wall timeout"))

    try:
        flood = restricted_docker(
            [],
            source=source,
            out=out,
            entrypoint=["python", "-c", "print('A'*1_000_000)"],
            timeout=10,
        )
        cases.append(
            record(
                "container-stdout-flood-injection",
                flood.returncode == 0 and len(flood.stdout) >= 1_000_000,
                f"exit {flood.returncode} stdout={len(flood.stdout)}",
            )
        )
    except subprocess.TimeoutExpired as exc:
        cases.append(record("container-stdout-flood-injection", False, f"timeout {exc}"))

    if before:
        cases.append(record("unchanged-prior-output", report.read_bytes() == before, str(report)))
    source_pdf = source / "mapping-control.pdf"
    cases.append(
        record(
            "unchanged-source-bytes",
            source_pdf.read_bytes() == FIXTURE.read_bytes(),
            str(source_pdf),
        )
    )
    return cases


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
    checkout = DOCKERFILE_CHECKOUT.read_text(encoding="utf-8")
    cases.append(record("checkout-entrypoint-inkflip", 'ENTRYPOINT ["inkflip"]' in checkout, "inkflip"))

    with tempfile.TemporaryDirectory(prefix="t40-contain-") as raw:
        td = Path(raw)
        source = td / "source with spaces"
        out = td / "out with spaces"
        source.mkdir()
        out.mkdir()
        shutil.copyfile(FIXTURE, source / "mapping-control.pdf")
        source_before = (source / "mapping-control.pdf").read_bytes()

        daemon, daemon_detail = docker_ok()
        if not daemon:
            proc = subprocess.run(
                [
                    str(SCRIPT),
                    "--source-root",
                    str(source),
                    "--out",
                    str(out),
                    "--",
                    "inspect",
                    "/input/mapping-control.pdf",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            combined = (proc.stdout or "") + (proc.stderr or "")
            cases.append(
                record(
                    "script-fails-closed-without-daemon",
                    proc.returncode == 4 and "docker daemon unavailable" in combined,
                    f"exit {proc.returncode}: {combined[:300]}",
                )
            )
        else:
            cases.extend(live_container_cases(source, out))

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
        cases.append(
            record(
                "host-source-untouched",
                (source / "mapping-control.pdf").read_bytes() == source_before,
                str(source),
            )
        )

    live_names = {
        "container-no-network-execution",
        "container-nonroot-uid",
        "container-no-egress",
        "container-readonly-input",
        "container-crash-injection",
        "container-hang-injection",
        "container-stdout-flood-injection",
    }
    failed = [c for c in cases if not c["ok"]]
    container_ran = any(c["name"] == "container-no-network-execution" and c["ok"] for c in cases)
    counts = {
        "collected": len(cases),
        "passed": sum(1 for c in cases if c["ok"]),
        "failed": len(failed),
        "skipped": 0,
        "live_container_cases": sum(1 for c in cases if c["name"] in live_names),
    }
    write_report(counts, cases)
    host = {
        "platform": sys.platform,
        "docker_cli": shutil.which("docker"),
        "docker_daemon": daemon,
        "container_criterion": "executed" if container_ran else "blocked",
        "image": IMAGE_TAG if container_ran else None,
        "architecture": docker_arch() if daemon else {"host_machine": platform.machine(), "emulated": None},
        "daemon_detail": daemon_detail,
    }
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "host.json").write_text(json.dumps(host, indent=2) + "\n")
    if failed:
        for item in failed:
            print(f"FAIL {item['name']}: {item['detail']}", file=sys.stderr)
        return 1
    print(json.dumps({"counts": counts, "container": host["container_criterion"], "arch": host["architecture"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
