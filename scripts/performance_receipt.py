"""Immutable Inkflip performance-receipt validation (T39).

Benchmark generation lives in ``scripts/measure_performance.py`` and
``tests/performance/budgets.spec.ts``. This module never runs those
journeys. It only loads JSON and rejects incomplete, stale, malformed,
or self-labelled evidence.

A ``distribution_claim`` of ``n>=30`` is never proof. Successful sample
count, retained failures, finite percentiles, and raw observations must
agree. Schema 2.1.0 is required; 2.0.0 receipts are stale.
"""
from __future__ import annotations

import hashlib
import json
import math
import statistics
import subprocess
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "2.1.0"
KIND = "inkflip-performance"
BROWSER_KIND = "inkflip-performance-browser"
REQUIRED_CLI_STAGES = ("file_sha256", "inspect_cli", "report_html", "alignment_cli")
# macOS-native OCR is required on this host. linux/amd64 image OCR is proven
# separately in tests/containment/run_production.py (qemu on Apple Silicon).
REQUIRED_MAC_OCR_STAGE = "ocr_cli"
REQUIRED_BROWSER_LATENCY = ("preview", "extraction")
MIN_DISTRIBUTION_N = 30
REFERENCE_CPUS = 4
REFERENCE_RAM = 8 * 1024**3


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def derive_distribution_claim(n: int, *, measured: bool, failures: int) -> str:
    if not measured:
        return "missing"
    if n <= 0:
        return "failed" if failures else "missing"
    if n < MIN_DISTRIBUTION_N:
        return "insufficient_samples"
    return "n>=30"


def summarize(samples: list[float], failures: int, *, measured: bool = True) -> dict[str, Any]:
    clean = [float(v) for v in samples if finite_number(v)]
    out: dict[str, Any] = {
        "n": len(clean),
        "failures": int(failures),
        "unit": "ms",
        "measured": bool(measured),
        "samples_ms": clean,
        "distribution_claim": derive_distribution_claim(len(clean), measured=measured, failures=int(failures)),
    }
    if not measured:
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
        if len(clean) < MIN_DISTRIBUTION_N:
            out["note"] = (
                "p50/p95 recorded but not a claimed latency distribution "
                f"(<{MIN_DISTRIBUTION_N} successful samples)"
            )
    else:
        out["note"] = "no successful samples; latency is not claimed"
    return out


def source_binding(root: Path) -> dict[str, Any]:
    fixture = root / "fixtures" / "public" / "mapping-control.pdf"
    settings = root / "planning" / "config" / "settings.json"
    binding: dict[str, Any] = {
        "root": str(root),
        "fixture_path": "fixtures/public/mapping-control.pdf",
        "fixture_sha256": sha256_file(fixture) if fixture.is_file() else None,
        "fixture_bytes": fixture.stat().st_size if fixture.is_file() else None,
        "settings_sha256": sha256_file(settings) if settings.is_file() else None,
    }
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode == 0:
            binding["git_head"] = proc.stdout.strip()
        else:
            binding["git_head"] = None
            binding["git_head_error"] = (proc.stderr or proc.stdout or "git rev-parse failed")[:200]
    except (OSError, subprocess.TimeoutExpired) as error:
        binding["git_head"] = None
        binding["git_head_error"] = str(error)
    return binding


def load_json_object(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.is_file():
        return None, f"missing file: {path}"
    if path.stat().st_size == 0:
        return None, f"empty file: {path}"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        return None, f"malformed JSON in {path}: {error.msg} (line {error.lineno})"
    except OSError as error:
        return None, f"unreadable {path}: {error}"
    if not isinstance(data, dict):
        return None, f"{path} is not a JSON object"
    return data, None


def _stage_problems(name: str, stage: Any, *, require_distribution: bool) -> list[str]:
    problems: list[str] = []
    prefix = f"stage {name}"
    if not isinstance(stage, dict):
        return [f"{prefix} is not an object"]
    measured = stage.get("measured", True)
    if not isinstance(measured, bool):
        problems.append(f"{prefix} measured must be a boolean")
        measured = bool(measured)
    n = stage.get("n")
    failures = stage.get("failures")
    if not isinstance(n, int) or isinstance(n, bool) or n < 0:
        problems.append(f"{prefix} n must be a nonnegative integer, got {n!r}")
        n = -1
    if not isinstance(failures, int) or isinstance(failures, bool) or failures < 0:
        problems.append(f"{prefix} failures must be a nonnegative integer, got {failures!r}")
        failures = -1
    claim = stage.get("distribution_claim")
    if claim == "n>=30" and (n < MIN_DISTRIBUTION_N or not measured):
        problems.append(
            f"{prefix} self-declared distribution_claim n>=30 is not proof "
            f"(n={n}, measured={measured})"
        )
    if not measured:
        if require_distribution:
            problems.append(f"{prefix} was not executed")
        return problems
    if n == 0:
        problems.append(f"{prefix} has no successful samples")
        return problems
    samples = stage.get("samples_ms")
    if not isinstance(samples, list) or not samples:
        problems.append(f"{prefix} missing raw samples_ms (labels are not observations)")
        samples = []
    else:
        if any(not finite_number(item) for item in samples):
            problems.append(f"{prefix} samples_ms contains a non-finite value")
        finite = [float(item) for item in samples if finite_number(item)]
        if len(finite) != n:
            problems.append(f"{prefix} n={n} does not match {len(finite)} finite samples_ms")
        if finite:
            expected_p50 = percentile(finite, 50)
            expected_p95 = percentile(finite, 95)
            for key, expected in (("p50", expected_p50), ("p95", expected_p95), ("max", max(finite))):
                got = stage.get(key)
                if not finite_number(got):
                    problems.append(f"{prefix} {key} is missing or not finite")
                elif abs(float(got) - expected) > 1e-6 * max(1.0, abs(expected)):
                    problems.append(
                        f"{prefix} {key}={got} is inconsistent with samples_ms ({expected})"
                    )
    derived = derive_distribution_claim(max(n, 0), measured=True, failures=max(failures, 0))
    if isinstance(claim, str) and claim != derived:
        problems.append(f"{prefix} distribution_claim {claim!r} disagrees with derived {derived!r}")
    if require_distribution and n < MIN_DISTRIBUTION_N:
        problems.append(
            f"{prefix} needs >={MIN_DISTRIBUTION_N} successful samples for a latency distribution "
            f"(observed n={n}, failures={failures})"
        )
    return problems


def _raster_evidence_problems(stage: Any) -> list[str]:
    problems: list[str] = []
    if not isinstance(stage, dict):
        return ["stage raster is not an object"]
    if stage.get("oversize_open_rejected") and not (
        stage.get("pixel_budget_enforced") and stage.get("edge_budget_enforced")
    ):
        problems.append(
            "raster evidence is file-byte rejection only; pixel and edge budgets were not proven"
        )
    if not stage.get("pixel_budget_enforced"):
        problems.append("raster pixel budget was not exercised at a real boundary")
    if not stage.get("edge_budget_enforced"):
        problems.append("raster edge budget was not exercised at a real boundary")
    live = stage.get("live_buffers")
    if not (isinstance(live, int) and live == 2) and not stage.get("live_buffer_cap_enforced"):
        problems.append("live raster buffer cap (2) was not evidenced")
    workers = stage.get("ocr_workers")
    if workers not in (1, None) and not stage.get("ocr_worker_cap_enforced"):
        problems.append("OCR worker cap was not evidenced")
    return problems


def _memory_problems(browser: dict[str, Any], settings: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    memory = browser.get("memory") if isinstance(browser.get("memory"), dict) else {}
    heap = memory.get("js_heap_used_bytes")
    rss = memory.get("process_rss_bytes")
    if heap is not None and rss is None and memory.get("measured_peak_rss_bytes") is None:
        problems.append("JS heap is recorded without process RSS; they are not interchangeable")
    if rss is None and memory.get("process_rss_bytes") is None:
        # Allow an explicit unavailable flag only as inventory, still unmet for accept.
        if not memory.get("process_rss_unavailable"):
            problems.append("process RSS is missing (JS heap cannot substitute)")
    rss_target = settings.get("browser", {}).get("measured_peak_rss_target_bytes")
    if finite_number(rss) and finite_number(rss_target) and float(rss) > float(rss_target):
        problems.append(f"process RSS {rss} exceeds declared measured_peak_rss_target_bytes {rss_target}")
    if heap is not None and rss is not None and heap == rss:
        problems.append("JS heap and process RSS are identical; they must be distinct measurements")
    return problems


def _binding_problems(body: dict[str, Any], current: dict[str, Any] | None) -> list[str]:
    problems: list[str] = []
    binding = body.get("source_binding") or (body.get("measurement") or {}).get("source")
    if not isinstance(binding, dict):
        return ["missing source/build binding"]
    digest = binding.get("sha256") or binding.get("fixture_sha256")
    if not isinstance(digest, str) or len(digest) != 64:
        problems.append("source binding is missing fixture sha256")
    if current:
        current_digest = current.get("fixture_sha256")
        if current_digest and digest and digest != current_digest:
            problems.append(
                f"stale source identity: receipt fixture sha256 {digest} != current {current_digest}"
            )
        current_head = current.get("git_head")
        recorded_head = body.get("source_binding", {}).get("git_head") if isinstance(body.get("source_binding"), dict) else None
        if current_head and recorded_head and recorded_head != current_head:
            problems.append(
                f"stale source identity: receipt git_head {recorded_head} != current {current_head}"
            )
        current_settings = current.get("settings_sha256")
        recorded_settings = None
        if isinstance(body.get("source_binding"), dict):
            recorded_settings = body["source_binding"].get("settings_sha256")
        if current_settings and recorded_settings and recorded_settings != current_settings:
            problems.append("stale source identity: planning/config/settings.json hash does not match this tree")
    return problems


def validate_receipt(
    body: dict[str, Any],
    *,
    mode: str,
    profile: str,
    settings: dict[str, Any],
    current_binding: dict[str, Any] | None = None,
) -> list[str]:
    problems: list[str] = []
    if not isinstance(body, dict):
        return ["receipt is not a JSON object"]
    if body.get("kind") != KIND:
        problems.append(f"malformed or stale performance evidence (kind={body.get('kind')!r})")
    if body.get("schema_version") != SCHEMA_VERSION:
        problems.append(
            f"malformed or stale performance evidence (schema_version={body.get('schema_version')!r}; "
            f"required {SCHEMA_VERSION})"
        )
        # Stale receipts are not interpreted further: their n>=30 labels are not evidence.
        return problems
    host = body.get("host") if isinstance(body.get("host"), dict) else {}
    if profile == "reference-desktop" and not host.get("is_specified_reference_desktop"):
        problems.append("required reference-desktop profile is unavailable on this host")
    if profile in {"mobile-physical", "mobile"}:
        problems.append("physical mobile profile is unavailable")
    if host.get("is_specified_reference_desktop") and (
        host.get("cpus_logical") != REFERENCE_CPUS
        or not finite_number(host.get("physical_memory_bytes"))
        or abs(float(host["physical_memory_bytes"]) - REFERENCE_RAM) >= 512 * 1024**2
    ):
        problems.append("host claims specified reference desktop without matching 4-core/8 GiB identity")
    if host.get("is_physical_mobile"):
        problems.append("receipt claimed physical mobile without a physical-device profile")

    problems.extend(_binding_problems(body, current_binding))

    measurement = body.get("measurement") if isinstance(body.get("measurement"), dict) else {}
    stages = measurement.get("stages") if isinstance(measurement.get("stages"), dict) else {}
    required_cli = REQUIRED_CLI_STAGES if profile in {"local-mac", "reference-desktop"} else ()
    for name in required_cli:
        problems.extend(_stage_problems(name, stages.get(name), require_distribution=True))
    if profile == "local-mac":
        problems.extend(
            _stage_problems(REQUIRED_MAC_OCR_STAGE, stages.get(REQUIRED_MAC_OCR_STAGE), require_distribution=True)
        )

    browser = body.get("browser")
    needs_browser = profile == "local-mac"
    if needs_browser and not isinstance(browser, dict):
        problems.append("missing browser evidence")
    elif isinstance(browser, dict):
        if browser.get("kind") not in {None, BROWSER_KIND}:
            problems.append(f"browser evidence kind {browser.get('kind')!r} is not {BROWSER_KIND}")
        if browser.get("kind") == BROWSER_KIND and browser.get("schema_version") not in {None, SCHEMA_VERSION}:
            problems.append(f"stale browser evidence schema_version={browser.get('schema_version')!r}")
        if browser.get("host", {}).get("is_physical_mobile"):
            problems.append("browser evidence claimed physical mobile")
        if browser.get("host", {}).get("is_specified_reference_desktop"):
            problems.append("browser evidence claimed the 4-core/8 GiB reference on this host")
        build = browser.get("build") if isinstance(browser.get("build"), dict) else {}
        if needs_browser:
            if not build.get("production"):
                problems.append("browser evidence is not an identified production (or labelled instrumented-production) build")
            if build.get("vite_dev_server"):
                problems.append("browser evidence was collected against a Vite development server")
        browser_stages = browser.get("stages") if isinstance(browser.get("stages"), dict) else {}
        preview = browser_stages.get("preview") if isinstance(browser_stages.get("preview"), dict) else {}
        if preview.get("distribution_claim") == "n>=30" and preview.get("n", 0) < MIN_DISTRIBUTION_N:
            problems.append("browser preview self-declared n>=30 is not proof")
        if needs_browser:
            for name in REQUIRED_BROWSER_LATENCY:
                problems.extend(
                    _stage_problems(name, browser_stages.get(name), require_distribution=True)
                )
            if preview.get("proof") != "first_rendered_page":
                problems.append(
                    "preview did not prove first rendered page (pages-summary metadata is not a render)"
                )
            problems.extend(_raster_evidence_problems(browser_stages.get("raster")))
            render = browser_stages.get("render")
            if not isinstance(render, dict) or not render.get("measured"):
                problems.append("required browser stage render is unmeasured/unavailable")
            export = browser_stages.get("export")
            if not isinstance(export, dict) or not export.get("measured") or int(export.get("n") or 0) < 1:
                problems.append("browser export journey was not measured")
            ocr = browser_stages.get("ocr") if isinstance(browser_stages.get("ocr"), dict) else {}
            ocr_cli = stages.get(REQUIRED_MAC_OCR_STAGE) if isinstance(stages.get(REQUIRED_MAC_OCR_STAGE), dict) else {}
            if not ocr.get("measured") and int(ocr_cli.get("n") or 0) < MIN_DISTRIBUTION_N:
                problems.append(
                    "browser OCR is unmeasured and macOS-native ocr_cli lacks a latency distribution"
                )
            problems.extend(_memory_problems(browser, settings))
            replace = browser.get("replace_clear_cycles") if isinstance(browser.get("replace_clear_cycles"), dict) else {}
            if int(replace.get("n") or 0) < 10:
                problems.append("replace/clear cycles were not executed for at least 10 files")
            cancel = browser.get("cancel_next_file") if isinstance(browser.get("cancel_next_file"), dict) else {}
            if not cancel.get("cancelled_visible") or not cancel.get("next_file_pages_summary"):
                problems.append("cancellation/recovery was not proven")
            mobile = browser.get("mobile") if isinstance(browser.get("mobile"), dict) else {}
            if not mobile.get("ocr_consent_visible"):
                problems.append("mobile fallback/OCR consent was not visible")
            if mobile.get("physical_device"):
                problems.append("viewport emulation was labelled a physical mobile device")

    if mode == "inventory":
        # Inventory never accepts, but must still list every unmet criterion.
        return problems
    return problems


def inventory_lines(problems: list[str], *, profile: str, mode: str) -> list[str]:
    lines = [
        f"performance inventory profile={profile} mode={mode}: "
        f"{'complete' if not problems else 'incomplete/unavailable'}"
    ]
    if not problems:
        lines.append("- no unmet mandatory criteria in this receipt (inventory still does not accept)")
        return lines
    for item in problems:
        lines.append(f"- incomplete/unavailable: {item}")
    return lines
