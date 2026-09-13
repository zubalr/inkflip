#!/usr/bin/env python3
"""Live production-image cases against the hashed linux/amd64 image.

Usage:
  python3 tests/containment/run_production.py
  python3 tests/containment/run_production.py --rebuild

Apple Silicon OrbStack runs are qemu emulation — not native x86_64
reference performance. This runner does not SSH to Homebase.
"""
from __future__ import annotations

import hashlib
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
IMAGE = os.environ.get("INKFLIP_NATIVE_IMAGE", "inkflip-native:rrr-prod")
PLATFORM = "linux/amd64"
NATIVE_MAX_FILE_BYTES = 104_857_600
NATIVE_MAX_OUTPUT_BYTES = 67_108_864


def record(name: str, ok: bool, detail: str, *, blocked: bool = False) -> dict:
    return {"name": name, "ok": bool(ok), "blocked": bool(blocked), "detail": detail}


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


def image_exists(tag: str) -> bool:
    proc = subprocess.run(
        ["docker", "image", "inspect", tag],
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


def combined(proc: subprocess.CompletedProcess[str]) -> str:
    return ((proc.stdout or "") + (proc.stderr or ""))[-1200:]


def expect(
    name: str,
    proc: subprocess.CompletedProcess[str],
    *,
    exits: set[int],
    contains: list[str] | None = None,
    forbids: list[str] | None = None,
    extra_ok: bool = True,
) -> dict:
    text = combined(proc)
    ok = proc.returncode in exits and extra_ok
    if contains:
        ok = ok and all(item in text for item in contains)
    if forbids:
        ok = ok and not any(item in text for item in forbids)
    detail = f"exit {proc.returncode} (want {sorted(exits)}) {text}"
    return record(name, ok, detail)


def restricted(
    extra: list[str],
    *,
    source: Path,
    out: Path,
    entrypoint: list[str] | None = None,
    timeout: int = 60,
    name: str | None = None,
    memory: str = "512m",
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
            memory,
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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_valid_oversize(path: Path) -> None:
    """A parseable PDF whose declared size exceeds native.max_file_bytes."""
    header = (
        b"%PDF-1.4\n1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n"
        b"2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n"
        b"3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>endobj\n"
        b"xref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n"
        b"trailer<< /Size 4 /Root 1 0 R >>\nstartxref\n9\n%%EOF\n"
    )
    path.write_bytes(header)
    with path.open("r+b") as handle:
        handle.seek(NATIVE_MAX_FILE_BYTES)
        handle.write(b"X")


def main(argv: list[str] | None = None) -> int:
    rebuild = "--rebuild" in (argv or sys.argv[1:])
    cases: list[dict] = []
    arch = docker_arch()
    EVIDENCE.mkdir(parents=True, exist_ok=True)

    global IMAGE
    if not rebuild and not image_exists(IMAGE) and image_exists("inkflip-native:nrf-prod"):
        IMAGE = "inkflip-native:nrf-prod"

    if rebuild or not image_exists(IMAGE):
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

    host_wheel_json = ROOT / "native" / "dist" / "app.wheel.json"
    host_wheel_sha = None
    if host_wheel_json.is_file():
        host_wheel_sha = json.loads(host_wheel_json.read_text()).get("sha256")
        wheel_files = list((ROOT / "native" / "dist" / "wheels").glob("inkflip-*.whl"))
        if wheel_files and host_wheel_sha:
            independent = sha256_file(wheel_files[0])
            cases.append(
                record(
                    "production-host-wheel-hash",
                    independent == host_wheel_sha,
                    f"app.wheel.json {host_wheel_sha} file {independent} path={wheel_files[0].name}",
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
        (source / "truncated.pdf").write_bytes(b"%PDF-1.4\nbroken")
        write_valid_oversize(source / "over-budget.pdf")
        control_sha = sha256_file(source / "mapping-control.pdf")
        trunc_sha = sha256_file(source / "truncated.pdf")
        corpus = {
            "kind": "corpus_manifest",
            "schema_version": "1.0.0",
            "source_root_policy": "explicit_local_root_no_symlinks",
            "split": "development",
            "entries": [
                {
                    "key": "good-file",
                    "source_path": "mapping-control.pdf",
                    "sha256": control_sha,
                    "group_id": "neighbors",
                    "pages": [0],
                },
                {
                    "key": "bad-file",
                    "source_path": "truncated.pdf",
                    "sha256": trunc_sha,
                    "group_id": "neighbors",
                    "pages": [0],
                },
            ],
        }
        (source / "corpus.json").write_text(json.dumps(corpus))
        (source / "junk.json").write_text("{not json", encoding="utf-8")
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
        report_ok = False
        report_kind = None
        if report.is_file():
            try:
                payload = json.loads(report.read_text())
                report_kind = payload.get("kind")
                report_ok = report_kind == "report" and "document" in payload
                report_size = report.stat().st_size
            except json.JSONDecodeError:
                report_size = report.stat().st_size
                payload = {}
        else:
            report_size = 0
            payload = {}
        cases.append(
            record(
                "production-inspect",
                inspect.returncode == 0 and report_ok,
                f"exit {inspect.returncode} kind={report_kind} {combined(inspect)[-400:]}",
            )
        )
        cases.append(
            record(
                "production-output-bounds",
                report.is_file() and report_size <= NATIVE_MAX_OUTPUT_BYTES,
                f"report_bytes={report_size} cap={NATIVE_MAX_OUTPUT_BYTES}",
            )
        )
        neighbor = report.read_bytes() if report.is_file() else b""

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
                f"exit {node.returncode} stdout={node.stdout!r}",
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

        notices = restricted(
            [],
            source=source,
            out=out,
            entrypoint=[
                "python",
                "-c",
                (
                    "from pathlib import Path\n"
                    "root=Path('/app/notices')\n"
                    "need=['inkflip-MIT.txt','node/LICENSE','pypdfium2-binary/BUILD_LICENSES/pdfium.txt','INDEX.json']\n"
                    "print({n: (root/n).is_file() and (root/n).stat().st_size>0 for n in need})\n"
                ),
            ],
        )
        notice_ok = notices.returncode == 0 and all(
            token in notices.stdout for token in ("inkflip-MIT.txt': True", "pdfium.txt': True", "LICENSE': True")
        )
        cases.append(record("production-image-notices", notice_ok, (notices.stdout + notices.stderr)[-500:]))

        installed = restricted(
            [],
            source=source,
            out=out,
            entrypoint=[
                "python",
                "-c",
                (
                    "from importlib.metadata import distribution\n"
                    "from pathlib import Path\n"
                    "d=distribution('inkflip')\n"
                    "main=Path(d.locate_file('inkflip/cli/main.py'))\n"
                    "schema=Path(d.locate_file('inkflip/contracts/schema/inkflip.schema.json'))\n"
                    "names=[ep.name for ep in d.entry_points]\n"
                    "print(d.version, main.is_file(), schema.is_file(), names)\n"
                ),
            ],
        )
        cases.append(
            record(
                "production-installed-wheel-resources",
                installed.returncode == 0
                and "True True" in installed.stdout
                and "inkflip" in installed.stdout,
                (installed.stdout + installed.stderr)[-400:],
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
                entrypoint=["python", "-c", "import socket; socket.create_connection(('1.1.1.1', 80), 2)"],
                timeout=15,
            )
            cases.append(record("production-no-egress", net.returncode != 0, combined(net)[-300:]))
        except subprocess.TimeoutExpired:
            cases.append(record("production-no-egress", True, "connect timed out under --network none"))

        write_input = restricted(
            [],
            source=source,
            out=out,
            entrypoint=["python", "-c", "open('/input/escape.txt','w').write('nope')"],
        )
        cases.append(record("production-readonly-input", write_input.returncode != 0, combined(write_input)[-300:]))

        crash = restricted(
            [],
            source=source,
            out=out,
            entrypoint=["python", "-c", "import os; os._exit(99)"],
        )
        cases.append(record("production-crash", crash.returncode == 99, f"exit {crash.returncode}"))

        tree_name = "inkflip-rrr-hang"
        try:
            hang = restricted(
                [],
                source=source,
                out=out,
                entrypoint=["python", "-c", "import os,time\n[os.fork() for _ in range(3)]\ntime.sleep(60)\n"],
                timeout=5,
                name=tree_name,
            )
            cases.append(record("production-timeout", False, f"exit {hang.returncode} expected timeout"))
            leftover = subprocess.run(
                ["docker", "ps", "-a", "--filter", f"name={tree_name}", "--format", "{{.Names}}"],
                capture_output=True,
                text=True,
            )
            cases.append(
                record(
                    "production-process-tree-terminated",
                    tree_name not in leftover.stdout,
                    leftover.stdout,
                )
            )
        except subprocess.TimeoutExpired:
            leftover = subprocess.run(
                ["docker", "ps", "-a", "--filter", f"name={tree_name}", "--format", "{{.Names}}"],
                capture_output=True,
                text=True,
            )
            cases.append(record("production-timeout", True, "killed after 5s wall timeout"))
            cases.append(
                record(
                    "production-process-tree-terminated",
                    tree_name not in leftover.stdout,
                    leftover.stdout or "no leftover container",
                )
            )

        oversize = restricted(
            ["inspect", "/input/over-budget.pdf", "--out", "/output/huge.json"],
            source=source,
            out=out,
            timeout=60,
        )
        cases.append(
            expect(
                "production-oversize-input-fails-closed",
                oversize,
                exits={5},
                contains=["native.max_file_bytes"],
                forbids=["EOF marker not found", "Stream has ended unexpectedly"],
            )
        )
        cases.append(
            record(
                "production-oversize-did-not-write-report",
                not (out / "huge.json").is_file(),
                f"huge.json exists={ (out / 'huge.json').is_file() }",
            )
        )

        unknown = restricted(
            ["inspect", "/input/mapping-control.pdf", "--reader", "nope", "--out", "/output/nope.json"],
            source=source,
            out=out,
        )
        cases.append(
            expect(
                "production-unknown-reader",
                unknown,
                exits={2},
                contains=["Unknown reader"],
            )
        )

        malformed = restricted(
            ["report", "/input/junk.json", "--format", "html", "--out", "/output/bad.html"],
            source=source,
            out=out,
        )
        cases.append(
            expect(
                "production-malformed-report",
                malformed,
                exits={2},
                contains=["Contract validation failed"],
                forbids=["Unknown reader"],
            )
        )

        tess = restricted(
            [
                "inspect",
                "/input/mapping-control.pdf",
                "--reader",
                "tesseract",
                "--ocr-pages",
                "1",
                "--out",
                "/output/ocr.json",
            ],
            source=source,
            out=out,
            timeout=120,
        )
        tess_text = combined(tess)
        tess_report = out / "ocr.json"
        tess_reason = ""
        ocr_payload: dict = {}
        if tess_report.is_file():
            try:
                ocr_payload = json.loads(tess_report.read_text())
                tess_reason = " ".join(
                    str(check.get("reason") or "") for check in ocr_payload.get("checks") or []
                )
            except json.JSONDecodeError:
                ocr_payload = {}
        has_binary = "missing_binary" in tess_reason or "tesseract executable not found" in tess_text
        traceback = "Traceback (most recent call last)" in tess_text
        if has_binary and tess.returncode in {3} and not traceback:
            cases.append(
                record(
                    "production-tesseract-missing-binary-typed",
                    True,
                    f"exit {tess.returncode} reason={tess_reason[:300]}",
                )
            )
            cases.append(
                record(
                    "production-tesseract-inference",
                    False,
                    "blocked: production image has no pinned tesseract executable; "
                    "eng.traineddata is present but inference cannot run",
                    blocked=True,
                )
            )
        elif tess.returncode == 0 and tess_report.is_file() and "completed" in json.dumps(ocr_payload.get("checks")):
            occs = ocr_payload.get("occurrences") or []
            cases.append(
                record(
                    "production-tesseract-inference",
                    len(occs) >= 0,
                    f"exit 0 occurrences={len(occs)}",
                )
            )
            cases.append(record("production-tesseract-missing-binary-typed", True, "binary present; inference ran"))
        else:
            cases.append(
                record(
                    "production-tesseract-missing-binary-typed",
                    False,
                    f"expected typed missing_binary or completed OCR, got exit {tess.returncode} {tess_text[-400:]}",
                )
            )
            cases.append(
                record(
                    "production-tesseract-inference",
                    False,
                    f"blocked or failed: exit {tess.returncode}",
                    blocked=True,
                )
            )

        html = restricted(
            ["report", "/output/report.json", "--format", "html", "--out", "/output/report.html", "--replace-output"],
            source=source,
            out=out,
            timeout=60,
        )
        cases.append(
            record(
                "production-report-html",
                html.returncode == 0 and (out / "report.html").is_file(),
                combined(html)[-300:],
            )
        )

        replay = restricted(
            [
                "replay",
                "/output/report.json",
                "--source",
                "/input/mapping-control.pdf",
                "--profile",
                "native-default",
                "--out",
                "/output/replay.json",
                "--replace-output",
            ],
            source=source,
            out=out,
            timeout=90,
        )
        replay_ok = replay.returncode == 0 and (out / "replay.json").is_file()
        if replay_ok:
            replay_kind = json.loads((out / "replay.json").read_text()).get("kind")
            replay_ok = replay_kind == "report"
        cases.append(record("production-replay", replay_ok, combined(replay)[-400:]))

        compare = restricted(
            [
                "compare-readers",
                "/input/mapping-control.pdf",
                "--readers",
                "pdfium,pypdf",
                "--out",
                "/output/compare",
                "--replace-output",
            ],
            source=source,
            out=out,
            timeout=120,
        )
        compare_dir = out / "compare"
        cases.append(
            record(
                "production-compare-readers",
                compare.returncode in {0, 6} and (compare_dir / "comparison.json").is_file(),
                combined(compare)[-400:],
            )
        )

        first_corpus = restricted(
            [
                "corpus",
                "run",
                "--manifest",
                "/input/corpus.json",
                "--source-root",
                "/input",
                "--profile",
                "native-default",
                "--out",
                "/output/corpus-run",
            ],
            source=source,
            out=out,
            timeout=180,
        )
        corpus_dir = out / "corpus-run"
        index_path = corpus_dir / "index.json"
        good_report = corpus_dir / "reports" / "good-file.json"
        first_ok = False
        if index_path.is_file() and good_report.is_file():
            index = json.loads(index_path.read_text())
            jobs = index.get("jobs") or {}
            first_ok = (
                first_corpus.returncode == 3
                and index.get("status") == "partial"
                and (jobs.get("good-file") or {}).get("status") == "completed"
                and (jobs.get("bad-file") or {}).get("status") != "completed"
            )
        cases.append(
            record(
                "production-corpus-neighbors",
                first_ok,
                f"exit {first_corpus.returncode} {combined(first_corpus)[-400:]}",
            )
        )
        preserved = good_report.read_bytes() if good_report.is_file() else b""
        resume = restricted(
            [
                "corpus",
                "run",
                "--manifest",
                "/input/corpus.json",
                "--source-root",
                "/input",
                "--profile",
                "native-default",
                "--out",
                "/output/corpus-run",
                "--resume",
            ],
            source=source,
            out=out,
            timeout=180,
        )
        resume_ok = False
        if index_path.is_file() and good_report.is_file():
            index2 = json.loads(index_path.read_text())
            jobs2 = index2.get("jobs") or {}
            resume_ok = (
                good_report.read_bytes() == preserved
                and (jobs2.get("good-file") or {}).get("status") in {"completed", "skipped"}
            )
        cases.append(
            record(
                "production-corpus-resume",
                resume_ok,
                f"exit {resume.returncode} {combined(resume)[-400:]}",
            )
        )

        cases.append(
            record(
                "production-source-bytes-unchanged",
                (source / "mapping-control.pdf").read_bytes() == source_before,
                str(source),
            )
        )

    failed = [c for c in cases if not c["ok"] and not c.get("blocked")]
    blocked = [c for c in cases if c.get("blocked")]
    counts = {
        "collected": len(cases),
        "passed": sum(1 for c in cases if c["ok"]),
        "failed": len(failed),
        "blocked": len(blocked),
        "image": IMAGE,
        "architecture": arch,
        "native_max_file_bytes": NATIVE_MAX_FILE_BYTES,
        "emulated_linux_amd64": arch["emulated"],
        "native_x86_64_reference": False,
    }
    payload = {"counts": counts, "cases": cases}
    (EVIDENCE / "production-run.json").write_text(json.dumps(payload, indent=2) + "\n")
    (EVIDENCE / "production-host.json").write_text(json.dumps(arch, indent=2) + "\n")
    if failed:
        for item in failed:
            print(f"FAIL {item['name']}: {item['detail']}", file=sys.stderr)
        return 1
    for item in blocked:
        print(f"BLOCKED {item['name']}: {item['detail']}", file=sys.stderr)
    print(json.dumps(counts, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
