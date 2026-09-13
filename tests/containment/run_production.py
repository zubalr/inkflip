#!/usr/bin/env python3
"""Live T40 cases against the hashed production image (not Dockerfile.checkout).

Usage:
  python3 tests/containment/run_production.py
  python3 tests/containment/run_production.py --rebuild

The image ABI is linux/amd64. On Apple Silicon OrbStack this is qemu
emulation and must be labeled as such — not native x86_64 reference
performance. Homebase docker.sock was permission-denied for this user.
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
DOCKERFILE = ROOT / "build" / "native" / "Dockerfile"
SCRIPT = ROOT / "scripts" / "run_native_container.sh"
EVIDENCE = ROOT / "artifacts" / "containment"
FIXTURE = ROOT / "fixtures" / "public" / "mapping-control.pdf"
FIXTURE_AMOUNT = ROOT / "fixtures" / "public" / "mapping-amount.pdf"
IMAGE = os.environ.get("INKFLIP_NATIVE_IMAGE", "inkflip-native:nrf-prod")
PLATFORM = "linux/amd64"


def record(name: str, ok: bool, detail: str) -> dict:
    return {"name": name, "ok": bool(ok), "detail": detail}


def docker_arch() -> dict:
    inspect = subprocess.run(
        ["docker", "info", "--format", "{{.Architecture}} {{.OSType}}"],
        capture_output=True,
        text=True,
    )
    host = platform.machine()
    return {
        "host_machine": host,
        "docker_architecture_line": (inspect.stdout or "").strip(),
        "requested_platform": PLATFORM,
        "emulated": host in {"arm64", "aarch64"},
        "note": "linux/amd64 on Apple Silicon OrbStack is qemu; not native x86_64 reference performance",
    }


def image_exists() -> bool:
    proc = subprocess.run(
        ["docker", "image", "inspect", IMAGE],
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0


def build_image() -> tuple[bool, str]:
    proc = subprocess.run(
        [
            "docker",
            "build",
            "--platform",
            PLATFORM,
            "-f",
            str(DOCKERFILE),
            "-t",
            IMAGE,
            ".",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    log = ((proc.stdout or "") + (proc.stderr or ""))[-4000:]
    return proc.returncode == 0, log


def restricted(
    extra: list[str],
    *,
    source: Path,
    out: Path,
    entrypoint: list[str] | None = None,
    timeout: int = 60,
    name: str | None = None,
) -> subprocess.CompletedProcess:
    cmd = ["docker", "run", "--rm", "--platform", PLATFORM]
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
        cmd.append(IMAGE)
        cmd.extend(entrypoint[1:])
        cmd.extend(extra)
    else:
        cmd.append(IMAGE)
        cmd.extend(extra)
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        if name:
            subprocess.run(["docker", "rm", "-f", name], capture_output=True, text=True)
        raise


def main(argv: list[str] | None = None) -> int:
    rebuild = "--rebuild" in (argv or sys.argv[1:])
    cases: list[dict] = []
    arch = docker_arch()
    EVIDENCE.mkdir(parents=True, exist_ok=True)

    if rebuild or not image_exists():
        built, log = build_image()
        cases.append(record("production-image-build", built, log[-800:]))
        if not built:
            payload = {"counts": {"failed": 1}, "cases": cases, "architecture": arch}
            (EVIDENCE / "production-run.json").write_text(json.dumps(payload, indent=2) + "\n")
            print(log, file=sys.stderr)
            return 1
    else:
        cases.append(record("production-image-build", True, f"reused {IMAGE}"))

    inspect_img = subprocess.run(
        [
            "docker",
            "image",
            "inspect",
            IMAGE,
            "--format",
            "{{.Id}} {{.Os}}/{{.Architecture}} {{.Size}}",
        ],
        capture_output=True,
        text=True,
    )
    cases.append(
        record(
            "production-image-linux-amd64",
            inspect_img.returncode == 0 and "linux/amd64" in inspect_img.stdout,
            inspect_img.stdout.strip() + inspect_img.stderr[:200],
        )
    )

    with tempfile.TemporaryDirectory(prefix="t40-prod-") as raw:
        td = Path(raw)
        source = td / "source with spaces"
        out = td / "out with spaces"
        source.mkdir()
        out.mkdir()
        shutil.copyfile(FIXTURE, source / "mapping-control.pdf")
        shutil.copyfile(FIXTURE_AMOUNT, source / "mapping-amount.pdf")
        (source / "huge.bin").write_bytes(b"%PDF-1.4\n" + b"A" * (2_000_000))
        source_before = (source / "mapping-control.pdf").read_bytes()

        inspect = subprocess.run(
            [
                str(SCRIPT),
                "--source-root",
                str(source),
                "--out",
                str(out),
                "--image",
                IMAGE,
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
        report = out / "report.json"
        ok = inspect.returncode == 0 and report.is_file()
        cases.append(
            record(
                "production-inspect",
                ok,
                ((inspect.stdout or "") + (inspect.stderr or ""))[-800:],
            )
        )
        neighbor = b""
        if report.is_file():
            neighbor = report.read_bytes()

        node = restricted(
            [],
            source=source,
            out=out,
            entrypoint=["/opt/node/bin/node", "-e", "process.stdout.write(process.version)"],
        )
        cases.append(
            record(
                "production-node-unpacked",
                node.returncode == 0 and node.stdout.startswith("v22."),
                f"exit {node.returncode} stdout={node.stdout!r} stderr={node.stderr[-200:]!r}",
            )
        )

        model = restricted(
            [],
            source=source,
            out=out,
            entrypoint=[
                "python",
                "-c",
                "from pathlib import Path; p=Path('/app/models/tessdata/eng.traineddata'); print(p.is_file(), p.stat().st_size)",
            ],
        )
        cases.append(
            record(
                "production-model-present",
                model.returncode == 0 and model.stdout.strip().startswith("True"),
                (model.stdout + model.stderr)[-300:],
            )
        )

        checkout = restricted(
            [],
            source=source,
            out=out,
            entrypoint=[
                "python",
                "-c",
                "from pathlib import Path; import sys; sys.exit(0 if not Path('/app/native').exists() else 3)",
            ],
        )
        cases.append(
            record(
                "production-no-checkout-tree",
                checkout.returncode == 0,
                f"exit {checkout.returncode} {checkout.stderr[-200:]}",
            )
        )

        uid = restricted(
            [],
            source=source,
            out=out,
            entrypoint=["python", "-c", "import os; print(os.getuid())"],
        )
        cases.append(
            record(
                "production-nonroot-uid",
                uid.returncode == 0 and uid.stdout.strip() == "65532",
                (uid.stdout + uid.stderr)[:200],
            )
        )

        try:
            net = restricted(
                [],
                source=source,
                out=out,
                entrypoint=[
                    "python",
                    "-c",
                    "import socket; socket.create_connection(('1.1.1.1', 80), 2)",
                ],
                timeout=15,
            )
            cases.append(
                record(
                    "production-no-egress",
                    net.returncode != 0,
                    (net.stdout + net.stderr)[-300:],
                )
            )
        except subprocess.TimeoutExpired:
            cases.append(record("production-no-egress", True, "connect timed out under --network none"))

        write_input = restricted(
            [],
            source=source,
            out=out,
            entrypoint=["python", "-c", "open('/input/escape.txt','w').write('nope')"],
        )
        cases.append(
            record(
                "production-readonly-input",
                write_input.returncode != 0,
                (write_input.stdout + write_input.stderr)[-300:],
            )
        )

        crash = restricted(
            [],
            source=source,
            out=out,
            entrypoint=["python", "-c", "import os; os._exit(99)"],
        )
        cases.append(record("production-crash", crash.returncode == 99, f"exit {crash.returncode}"))

        try:
            hang = restricted(
                [],
                source=source,
                out=out,
                entrypoint=["python", "-c", "import time; time.sleep(60)"],
                timeout=5,
                name="inkflip-nrf-hang",
            )
            cases.append(record("production-timeout", False, f"exit {hang.returncode} expected timeout"))
        except subprocess.TimeoutExpired:
            cases.append(record("production-timeout", True, "killed after 5s wall timeout"))

        oversize = restricted(
            ["inspect", "/input/huge.bin", "--out", "/output/huge.json"],
            source=source,
            out=out,
            timeout=60,
        )
        cases.append(
            record(
                "production-oversize-input-fails-closed",
                oversize.returncode != 0,
                f"exit {oversize.returncode} {(oversize.stdout + oversize.stderr)[-400:]}",
            )
        )

        second = restricted(
            [
                "inspect",
                "/input/mapping-amount.pdf",
                "--out",
                "/output/neighbor.json",
            ],
            source=source,
            out=out,
            timeout=90,
        )
        neighbor_out = out / "neighbor.json"
        cases.append(
            record(
                "production-neighbor-corpus-preserved",
                second.returncode == 0
                and neighbor_out.is_file()
                and (not neighbor or report.read_bytes() == neighbor),
                f"exit {second.returncode} neighbor={neighbor_out.is_file()} prior_intact={report.is_file()}",
            )
        )

        tesseract = restricted(
            [
                "inspect",
                "/input/mapping-control.pdf",
                "--reader",
                "tesseract",
                "--out",
                "/output/ocr.json",
            ],
            source=source,
            out=out,
            timeout=90,
        )
        # Missing tesseract binary is honest missing-capability; a crash is not.
        cases.append(
            record(
                "production-tesseract-missing-or-completes",
                tesseract.returncode in {0, 1, 2, 3, 4, 5, 6},
                f"exit {tesseract.returncode} {(tesseract.stdout + tesseract.stderr)[-400:]}",
            )
        )

        cases.append(
            record(
                "production-source-bytes-unchanged",
                (source / "mapping-control.pdf").read_bytes() == source_before,
                str(source),
            )
        )

    failed = [c for c in cases if not c["ok"]]
    counts = {
        "collected": len(cases),
        "passed": sum(1 for c in cases if c["ok"]),
        "failed": len(failed),
        "image": IMAGE,
        "architecture": arch,
    }
    payload = {"counts": counts, "cases": cases}
    (EVIDENCE / "production-run.json").write_text(json.dumps(payload, indent=2) + "\n")
    (EVIDENCE / "production-host.json").write_text(json.dumps(arch, indent=2) + "\n")
    if failed:
        for item in failed:
            print(f"FAIL {item['name']}: {item['detail']}", file=sys.stderr)
        return 1
    print(json.dumps(counts, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
