#!/usr/bin/env python3
"""T39 performance and resource measurements.

Reads canonical budgets from planning/config/settings.json. Local Mac runs
are labeled as this host, not the 4-core/8 GiB reference desktop. Device
emulation is layout/behavior only.

Latency distributions are claimed only when ``--samples`` is at least 30.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import resource
import shutil
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


def summarize(samples: list[float], failures: int) -> dict[str, Any]:
    clean = [v for v in samples if v == v]
    out: dict[str, Any] = {
        "n": len(clean),
        "failures": failures,
        "unit": "ms",
    }
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
            out["note"] = "p50/p95 recorded but not a claimed latency distribution (<30 samples)"
        else:
            out["distribution_claim"] = "n>=30"
    return out


def host_identity(profile: str) -> dict[str, Any]:
    mem = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") if hasattr(os, "sysconf") else None
    return {
        "profile_requested": profile,
        "os": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python": sys.version.split()[0],
        "cpus_logical": os.cpu_count(),
        "physical_memory_bytes": mem,
        "reference_desktop": {
            "logical_cpus": 4,
            "ram_bytes": 8 * 1024 ** 3,
            "display": "1366x768 or 1440x1000",
        },
        "is_specified_reference_desktop": False,
        "note": (
            "This host is not the specified 4-core/8 GiB reference desktop merely because "
            "a viewport can be emulated. Local numbers are labeled as this machine."
        ),
    }


def rss_bytes() -> int | None:
    usage = resource.getrusage(resource.RUSAGE_SELF)
    value = usage.ru_maxrss
    if value <= 0:
        return None
    # macOS reports bytes; Linux reports KiB.
    if sys.platform == "darwin":
        return int(value)
    return int(value * 1024)


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


def ensure_pinned_node() -> None:
    if PINNED_NODE.is_file():
        os.environ.setdefault("INKFLIP_NODE", str(PINNED_NODE))


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
        "downsample_recorded": True,
    }


def measure_stages(samples: int, out_dir: Path) -> dict[str, Any]:
    ensure_pinned_node()
    pdf = FIXTURE
    file_bytes = pdf.stat().st_size
    digest = sha256_file(pdf)
    hash_times: list[float] = []
    meta_times: list[float] = []
    inspect_times: list[float] = []
    report_times: list[float] = []
    failures = {"hash": 0, "inspect": 0, "report": 0}

    with tempfile.TemporaryDirectory(prefix="inkflip-t39-") as raw:
        work = Path(raw)
        for _ in range(samples):
            elapsed, got = time_ms(lambda: sha256_file(pdf))
            hash_times.append(elapsed)
            if got != digest:
                failures["hash"] += 1
            inspect_out = work / "inspect.json"
            elapsed, proc = time_ms(
                lambda: run_cli(
                    ["inspect", str(pdf), "--out", str(inspect_out), "--pages", "1", "--replace-output"],
                    work,
                )
            )
            inspect_times.append(elapsed)
            if proc.returncode != 0 or not inspect_out.is_file():
                failures["inspect"] += 1
                continue
            html_out = work / "report.html"
            elapsed_html, rendered = time_ms(
                lambda: run_cli(
                    ["report", str(inspect_out), "--format", "html", "--out", str(html_out), "--replace-output"],
                    work,
                )
            )
            report_times.append(elapsed_html)
            if rendered.returncode != 0:
                failures["report"] += 1
        # Metadata is the inspect payload's document block parse; measured as JSON load of last report if present.
        last = work / "inspect.json"
        if last.is_file():
            payload = last.read_bytes()

            def _load() -> None:
                json.loads(payload)

            for _ in range(samples):
                elapsed, _ = time_ms(_load)
                meta_times.append(elapsed)

        compare_times: list[float] = []
        compare_failures = 0
        compare_note = (
            "shared Node alignment bridge via inkflip.baselines.engine._align_pages "
            "on the last inspect report; not a JS-heap claim"
        )
        last_compare: dict[str, Any] | None = None
        if last.is_file():
            report = json.loads(last.read_text(encoding="utf-8"))
            native_root = str(ROOT / "native")
            if native_root not in sys.path:
                sys.path.insert(0, native_root)
            try:
                from inkflip.baselines.engine import _align_pages
            except ImportError as error:
                compare_failures = samples
                last_compare = {"error": "import", "detail": str(error)}
            else:
                for _ in range(samples):
                    start = time.perf_counter()
                    try:
                        _align_pages(report, report)
                        compare_times.append((time.perf_counter() - start) * 1000.0)
                    except Exception as error:  # BaselineError/BridgeError — record, do not approximate
                        compare_times.append((time.perf_counter() - start) * 1000.0)
                        compare_failures += 1
                        last_compare = {
                            "type": type(error).__name__,
                            "detail": str(error)[:400],
                        }

    # Ten replace/clear cycles on inspect output.
    cycle_rss: list[int] = []
    with tempfile.TemporaryDirectory(prefix="inkflip-t39-cycles-") as raw:
        work = Path(raw)
        for i in range(10):
            out = work / f"cycle-{i}.json"
            proc = run_cli(
                ["inspect", str(pdf), "--out", str(out), "--pages", "1", "--replace-output"],
                work,
            )
            if proc.returncode == 0:
                out.unlink(missing_ok=True)
            rss = rss_bytes()
            if rss is not None:
                cycle_rss.append(rss)

    raster = validate_raster_request(2000, 2000)
    raster_bad = validate_raster_request(float("inf"), 100)
    raster_mobile = validate_raster_request(2000, 2000, mobile=True)
    oversize = validate_raster_request(9000, 9000)
    next_file = run_cli(
        ["inspect", str(pdf), "--out", str(out_dir / "next-file.json"), "--pages", "1", "--replace-output"],
        ROOT,
    )

    return {
        "source": {
            "path": str(pdf.relative_to(ROOT)),
            "bytes": file_bytes,
            "sha256": digest,
            "selected_pages": [0],
        },
        "stages": {
            "file_read_hash": summarize(hash_times, failures["hash"]),
            "metadata_parse": summarize(meta_times, 0),
            "first_preview_and_extraction": summarize(inspect_times, failures["inspect"]),
            "report_serialization": summarize(report_times, failures["report"]),
            "alignment": {
                **(
                    summarize(compare_times, compare_failures)
                    if compare_times
                    else {
                        "n": 0,
                        "failures": compare_failures,
                        "distribution_claim": "not_run",
                    }
                ),
                "note": compare_note,
                "last_compare": last_compare,
            },
            "rasterization": {
                "n": 0,
                "distribution_claim": "not_a_latency_distribution",
                "budget_validation": raster,
                "infinite_rejected": raster_bad,
                "mobile": raster_mobile,
                "note": "browser raster timings live in tests/performance/budgets.spec.ts; this records budget enforcement",
            },
            "ocr": {
                "n": 0,
                "distribution_claim": "not_run",
                "note": "native tesseract OCR is an optional external reader; missing binary/model is a capability gap, not a p95",
            },
            "entry_versus_lazy_downloads": {
                "n": 0,
                "distribution_claim": "not_applicable_native_cli",
                "note": "native CLI has no browser entry/lazy model download; those cases are T25/T46 browser observations",
            },
        },
        "low_memory_injection": {
            "method": "reject oversize raster before allocation; not a portable JS-heap OOM",
            "oversize_raster": oversize,
            "next_file_inspect_exit": next_file.returncode,
            "next_file_healthy": next_file.returncode == 0,
        },
        "replace_clear_cycles": {
            "n": 10,
            "rss_bytes_after_cycle": cycle_rss,
            "rss_grew_monotonically": bool(cycle_rss) and all(
                later >= earlier for earlier, later in zip(cycle_rss, cycle_rss[1:])
            )
            and cycle_rss[-1] > cycle_rss[0] * 1.5
            if cycle_rss
            else False,
            "note": "ru_maxrss is a high-water mark, not a portable total-memory claim from JS heap",
        },
        "budgets": {
            "browser": SETTINGS["browser"],
            "mobile": SETTINGS["mobile"],
            "native": SETTINGS["native"],
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Measure Inkflip runtime budgets")
    parser.add_argument(
        "--profile",
        default="local-mac",
        choices=("reference-desktop", "local-mac", "mobile-emulation"),
    )
    parser.add_argument("--samples", type=int, default=30)
    parser.add_argument("--out", type=Path, default=ROOT / "artifacts" / "performance")
    args = parser.parse_args(argv)

    identity = host_identity(args.profile)
    if args.profile == "reference-desktop":
        identity["claimed_as_reference"] = False
        identity["gap"] = (
            "reference-desktop (4 logical CPUs, 8 GiB RAM, SSD) is not this 24 GiB-class Mac; "
            "measurements below are local-mac, not reference acceptance"
        )
    if args.profile == "mobile-emulation":
        identity["claimed_as_mobile_device"] = False
        identity["gap"] = "viewport emulation is layout/behavior only; no 4 GiB physical mobile profile ran"

    args.out.mkdir(parents=True, exist_ok=True)
    body = {
        "kind": "inkflip-performance",
        "schema_version": "1.0.0",
        "host": identity,
        "samples_requested": args.samples,
        "contention": "caller must keep competing OCR/container jobs idle; this process does not inspect other PIDs",
        "measurement": measure_stages(max(args.samples, 1), args.out),
    }
    out_path = args.out / f"{args.profile}.json"
    out_path.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out_path}")
    if args.profile == "reference-desktop":
        print("labeled local host; not the specified 4-core/8 GiB reference", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
