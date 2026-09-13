#!/usr/bin/env python3
"""T39 native CLI timings — accurately named, never a browser claim.

Local Mac runs are this host (14-core/24 GiB class), not the specified
4-core/8 GiB reference desktop. Viewport emulation is not a physical
mobile profile.

``--mode inventory`` writes a report and exits 0 even when the profile
cannot be accepted. ``--mode accept`` fails closed on missing/failed
required stages, stale/malformed evidence, unavailable required
reference profiles, or violated thresholds.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = json.loads((ROOT / "planning" / "config" / "settings.json").read_text())
FIXTURE = ROOT / "fixtures" / "public" / "mapping-control.pdf"
NATIVE_PYTHON = ROOT / "native" / ".venv" / "bin" / "python"
PINNED_NODE = ROOT / ".private" / "toolchains" / "node-v22.23.2-darwin-arm64" / "bin" / "node"
SCHEMA_VERSION = "2.0.0"
REQUIRED_CLI_STAGES = ("file_sha256", "inspect_cli", "report_html", "alignment_cli")
REFERENCE_CPUS = 4
REFERENCE_RAM = 8 * 1024**3


def percentile(values: list[float], p: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    idx = (p / 100.0) * (len(ordered) - 1)
    lo = int(idx)
    hi = min(lo + 1, len(ordered) - 1)
    frac = idx - lo
    return ordered[lo] * (1 - frac) + ordered[hi] * frac


def summarize(samples: list[float], failures: int, *, measured: bool = True) -> dict[str, Any]:
    clean = [v for v in samples if v == v]
    out: dict[str, Any] = {
        "n": len(clean),
        "failures": failures,
        "unit": "ms",
        "measured": measured,
    }
    if not measured:
        out["distribution_claim"] = "missing"
        out["note"] = "stage was not executed"
        return out
    if clean:
        out.update(
            {
                "p50": percentile(clean, 50),
                "p95": percentile(clean, 95),
                "max": max(clean),
                "mean": statistics.fmean(clean),
            }
        )
        if len(clean) < 30:
            out["distribution_claim"] = "insufficient_samples"
            out["note"] = "p50/p95 recorded but not a claimed latency distribution (<30 successful samples)"
        else:
            out["distribution_claim"] = "n>=30"
    else:
        out["distribution_claim"] = "failed"
        out["note"] = "no successful samples; latency is not claimed"
    return out


def host_identity(profile: str) -> dict[str, Any]:
    mem = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") if hasattr(os, "sysconf") else None
    cpus = os.cpu_count() or 0
    is_reference = (
        profile == "reference-desktop"
        and cpus == REFERENCE_CPUS
        and mem is not None
        and abs(mem - REFERENCE_RAM) < 512 * 1024**2
    )
    identity: dict[str, Any] = {
        "profile_requested": profile,
        "os": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python": sys.version.split()[0],
        "cpus_logical": cpus,
        "physical_memory_bytes": mem,
        "reference_desktop": {
            "logical_cpus": REFERENCE_CPUS,
            "ram_bytes": REFERENCE_RAM,
            "display": "1366x768 or 1440x1000",
        },
        "is_specified_reference_desktop": is_reference,
        "is_physical_mobile": False,
        "note": (
            "This host is not the specified 4-core/8 GiB reference desktop merely because "
            "a viewport can be emulated. Local numbers are labeled as this machine."
        ),
    }
    if profile == "reference-desktop" and not is_reference:
        identity["claimed_as_reference"] = False
        identity["gap"] = (
            "reference-desktop (4 logical CPUs, 8 GiB RAM, SSD) is not this host; "
            "measurements below are local inventory, not reference acceptance"
        )
    if profile == "mobile-emulation":
        identity["claimed_as_mobile_device"] = False
        identity["gap"] = "viewport emulation is layout/behavior only; no 4 GiB physical mobile profile ran"
    return identity


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inkflip_python() -> str:
    if NATIVE_PYTHON.is_file():
        return str(NATIVE_PYTHON)
    return sys.executable


def run_cli(argv: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "native")
    if PINNED_NODE.is_file():
        env.setdefault("INKFLIP_NODE", str(PINNED_NODE))
    return subprocess.run(
        [inkflip_python(), "-m", "inkflip.cli", *argv],
        cwd=cwd,
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )


def time_ms(fn) -> tuple[float, Any]:
    start = time.perf_counter()
    result = fn()
    return (time.perf_counter() - start) * 1000.0, result


def validate_raster_request(
    width: float,
    height: float,
    *,
    mobile: bool = False,
) -> dict[str, Any]:
    browser = SETTINGS["browser"]
    mobile_cfg = SETTINGS["mobile"]
    edge = browser["max_raster_edge"]
    pixels = mobile_cfg["max_raster_pixels"] if mobile else browser["max_raster_pixels"]
    reasons: list[str] = []
    if not (width == width and height == height and width > 0 and height > 0):
        reasons.append("dimensions must be positive and finite")
    if width > edge or height > edge:
        reasons.append(f"edge exceeds {edge}")
    if width * height > pixels:
        reasons.append(f"pixel budget exceeds {pixels}")
    return {
        "ok": not reasons,
        "reasons": reasons,
        "width": width,
        "height": height,
        "mobile": mobile,
        "pixel_budget": pixels,
        "edge_budget": edge,
        "live_buffers": browser["max_live_rasters"] if not mobile else 1,
        "ocr_workers": browser["max_ocr_workers"] if not mobile else 1,
        "mobile_ocr_pages": mobile_cfg["max_ocr_pages_per_run"],
    }


def measure_cli_stages(samples: int, out_dir: Path) -> dict[str, Any]:
    pdf = FIXTURE
    digest = sha256_file(pdf)
    hash_times: list[float] = []
    inspect_times: list[float] = []
    report_times: list[float] = []
    failures = {"hash": 0, "inspect": 0, "report": 0}
    inspect_success = 0
    report_success = 0

    with tempfile.TemporaryDirectory(prefix="inkflip-t39-") as raw:
        work = Path(raw)
        for _ in range(samples):
            elapsed, got = time_ms(lambda: sha256_file(pdf))
            if got != digest:
                failures["hash"] += 1
            else:
                hash_times.append(elapsed)
            inspect_out = work / "inspect.json"
            elapsed, proc = time_ms(
                lambda: run_cli(
                    ["inspect", str(pdf), "--out", str(inspect_out), "--pages", "1", "--replace-output"],
                    work,
                )
            )
            if proc.returncode != 0 or not inspect_out.is_file():
                failures["inspect"] += 1
                continue
            inspect_times.append(elapsed)
            inspect_success += 1
            html_out = work / "report.html"
            elapsed_html, rendered = time_ms(
                lambda: run_cli(
                    ["report", str(inspect_out), "--format", "html", "--out", str(html_out), "--replace-output"],
                    work,
                )
            )
            if rendered.returncode != 0:
                failures["report"] += 1
                continue
            report_times.append(elapsed_html)
            report_success += 1

        compare_times: list[float] = []
        compare_failures = 0
        last_compare: dict[str, Any] | None = None
        last = work / "inspect.json"
        if last.is_file():
            env = os.environ.copy()
            env["PYTHONPATH"] = str(ROOT / "native")
            if PINNED_NODE.is_file():
                env.setdefault("INKFLIP_NODE", str(PINNED_NODE))
            align_prog = (
                "import json, sys, time\n"
                "from pathlib import Path\n"
                "from inkflip.baselines.engine import _align_pages\n"
                "report = json.loads(Path(sys.argv[1]).read_text())\n"
                "n = int(sys.argv[2])\n"
                "times = []\n"
                "failures = 0\n"
                "err = None\n"
                "for _ in range(n):\n"
                "    t0 = time.perf_counter()\n"
                "    try:\n"
                "        _align_pages(report, report)\n"
                "        times.append((time.perf_counter() - t0) * 1000.0)\n"
                "    except Exception as exc:\n"
                "        failures += 1\n"
                "        err = f'{type(exc).__name__}: {exc}'\n"
                "print(json.dumps({'times': times, 'failures': failures, 'error': err}))\n"
            )
            proc = subprocess.run(
                [inkflip_python(), "-c", align_prog, str(last), str(samples)],
                capture_output=True,
                text=True,
                env=env,
                timeout=120,
            )
            if proc.returncode != 0:
                compare_failures = samples
                last_compare = {
                    "error": "align_subprocess",
                    "detail": ((proc.stderr or proc.stdout) or "")[-400:],
                }
            else:
                try:
                    payload = json.loads(proc.stdout.strip().splitlines()[-1])
                    compare_times = [float(v) for v in payload.get("times") or []]
                    compare_failures = int(payload.get("failures") or 0)
                    if payload.get("error"):
                        last_compare = {"error": "align", "detail": str(payload["error"])[:400]}
                except (json.JSONDecodeError, TypeError, ValueError) as error:
                    compare_failures = samples
                    last_compare = {"error": "align_parse", "detail": str(error)}

    return {
        "source": {
            "path": str(pdf.relative_to(ROOT)),
            "bytes": pdf.stat().st_size,
            "sha256": digest,
            "selected_pages": [0],
        },
        "stages": {
            "file_sha256": summarize(hash_times, failures["hash"]),
            "inspect_cli": summarize(inspect_times, failures["inspect"]),
            "report_html": summarize(report_times, failures["report"]),
            "alignment_cli": {
                **(
                    summarize(compare_times, compare_failures)
                    if compare_times
                    else summarize([], compare_failures, measured=compare_failures == 0)
                ),
                "note": "shared Node alignment bridge via inkflip.baselines.engine._align_pages; not JS-heap",
                "last_compare": last_compare,
            },
            "preview": summarize([], 0, measured=False),
            "render": summarize([], 0, measured=False),
            "extraction": summarize([], 0, measured=False),
            "raster": summarize([], 0, measured=False),
            "ocr": summarize([], 0, measured=False),
            "export": summarize([], 0, measured=False),
        },
        "cli_success": {
            "inspect": inspect_success,
            "report": report_success,
            "samples_requested": samples,
        },
        "budgets": {
            "browser": SETTINGS["browser"],
            "mobile": SETTINGS["mobile"],
            "native": SETTINGS["native"],
        },
        "note": (
            "CLI stages are new-process invocations. They are not persistent-browser "
            "workspace retention, product JS-heap, or replace/clear evidence. Browser "
            "behavior lives in tests/performance/budgets.spec.ts."
        ),
    }


def acceptance_problems(body: dict[str, Any], *, mode: str, profile: str) -> list[str]:
    problems: list[str] = []
    if body.get("kind") != "inkflip-performance" or body.get("schema_version") != SCHEMA_VERSION:
        problems.append("malformed or stale performance evidence (kind/schema_version)")
        return problems
    host = body.get("host") or {}
    if profile == "reference-desktop" and not host.get("is_specified_reference_desktop"):
        problems.append("required reference-desktop profile is unavailable on this host")
    if profile == "mobile-physical":
        problems.append("physical mobile profile is unavailable")
    measurement = body.get("measurement") or {}
    stages = measurement.get("stages") or {}
    required = REQUIRED_CLI_STAGES if profile in {"local-mac", "reference-desktop"} else ()
    if mode == "inventory":
        return problems
    for name in required:
        stage = stages.get(name) or {}
        if not stage.get("measured", True):
            problems.append(f"required stage {name} was not executed")
            continue
        if stage.get("n", 0) <= 0 or stage.get("distribution_claim") == "failed":
            problems.append(f"required stage {name} has no successful samples")
        if stage.get("failures", 0) and stage.get("n", 0) == 0:
            problems.append(f"required stage {name} failed")
    rss_target = SETTINGS["browser"]["measured_peak_rss_target_bytes"]
    browser = body.get("browser") or {}
    peak = (browser.get("memory") or {}).get("js_heap_used_bytes")
    if isinstance(peak, (int, float)) and peak > rss_target:
        problems.append(f"recorded JS heap {peak} exceeds measured_peak_rss_target_bytes {rss_target}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Measure Inkflip native CLI timings")
    parser.add_argument(
        "--profile",
        default="local-mac",
        choices=("reference-desktop", "local-mac", "mobile-emulation"),
    )
    parser.add_argument("--samples", type=int, default=30)
    parser.add_argument("--out", type=Path, default=ROOT / "artifacts" / "performance")
    parser.add_argument("--mode", choices=("inventory", "accept"), default="inventory")
    parser.add_argument(
        "--browser-evidence",
        type=Path,
        help="optional browser JSON produced by tests/performance/budgets.spec.ts",
    )
    args = parser.parse_args(argv)

    identity = host_identity(args.profile)
    args.out.mkdir(parents=True, exist_ok=True)
    measurement = measure_cli_stages(max(args.samples, 1), args.out)
    browser_evidence = None
    if args.browser_evidence and args.browser_evidence.is_file():
        try:
            browser_evidence = json.loads(args.browser_evidence.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            browser_evidence = {"malformed": True, "path": str(args.browser_evidence)}
    body = {
        "kind": "inkflip-performance",
        "schema_version": SCHEMA_VERSION,
        "host": identity,
        "samples_requested": args.samples,
        "mode": args.mode,
        "accepting": False,
        "contention": "caller must keep competing OCR/container jobs idle; this process does not inspect other PIDs",
        "measurement": measurement,
        "browser": browser_evidence,
    }
    problems = acceptance_problems(body, mode=args.mode, profile=args.profile)
    body["problems"] = problems
    body["accepting"] = args.mode == "accept" and not problems
    out_path = args.out / f"{args.profile}.json"
    out_path.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out_path}")
    if identity.get("gap"):
        print(identity["gap"], file=sys.stderr)
    if args.mode == "accept" and problems:
        for item in problems:
            print(f"ACCEPT-FAIL {item}", file=sys.stderr)
        return 1
    if args.mode == "inventory":
        print("inventory/report mode: not an acceptance claim", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
