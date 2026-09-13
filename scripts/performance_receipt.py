"""Immutable Inkflip performance-receipt validation (T39).

Benchmark generation lives in ``scripts/measure_performance.py`` and
``tests/performance/budgets.spec.ts``. This module never runs those
journeys. It only loads JSON and rejects incomplete, stale, malformed,
or self-labelled evidence.

A ``distribution_claim`` of ``n>=30`` is never proof. Successful sample
count, retained failures, finite percentiles, and raw observations must
agree. Schema 2.2.0 is required; 2.0.0 and 2.1.0 receipts are stale.

Identity is an explicit hash of product inputs, not git HEAD. A notes-only
commit (handoff, docs, receipts) does not change those hashes. An actual
runtime/source/config/fixture change does. Evidence belongs outside
tracked source; committing a receipt must not force a 30-sample rerun.
"""
from __future__ import annotations

import hashlib
import json
import math
import statistics
import subprocess
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "2.2.0"
KIND = "inkflip-performance"
BROWSER_KIND = "inkflip-performance-browser"
REQUIRED_CLI_STAGES = ("file_sha256", "inspect_cli", "report_html", "alignment_cli")
# macOS-native OCR is required on this host. linux/amd64 image OCR is proven
# separately in tests/containment/run_production.py (qemu on Apple Silicon).
REQUIRED_MAC_OCR_STAGE = "ocr_cli"
REQUIRED_BROWSER_LATENCY = ("preview", "extraction")
MIN_DISTRIBUTION_N = 30
# PERFORMANCE_AND_COMPATIBILITY.md: record failures over >=30 successful
# samples for a claimed latency distribution. Accept treats extra failures
# as an unhealthy run (30 successes + 999 failures is not healthy).
MAX_ACCEPT_FAILURES = 0
REFERENCE_CPUS = 4
REFERENCE_RAM = 8 * 1024**3

# Product inputs whose contents identify a measurement. Validator-only
# modules, tests, handoffs, and receipts are excluded so a notes-only
# commit does not invalidate CLI/browser/Docker evidence.
CLI_INPUT_PATHS = (
    "native/inkflip",
    "native/pyproject.toml",
    "planning/config/settings.json",
    "fixtures/public/mapping-control.pdf",
)
BROWSER_INPUT_PATHS = (
    "apps/web/src",
    "apps/web/index.html",
    "apps/web/vite.config.ts",
    "packages/runtime/src",
    "packages/readers-pdfjs/src",
    "packages/readers-tesseract/src",
    "packages/geometry/src",
    "packages/contracts/src",
    "planning/config/settings.json",
    "fixtures/public/mapping-control.pdf",
)
DOCKER_INPUT_PATHS = (
    "build/native/Dockerfile",
    "native/inkflip",
    "native/pyproject.toml",
    "scripts/distribution/assemble_native_image.py",
    "release/tesseract/tesseract.stamp.json",
    "release/native-wheels.manifest.json",
    "release/node/node.stamp.json",
    "release/models/model.stamp.json",
    "release/native-requirements.lock",
)
IDENTITY_SEMANTICS = (
    "cli_sha256 hashes native CLI product inputs (native/inkflip, native/pyproject.toml, "
    "planning/config/settings.json, fixtures/public/mapping-control.pdf). "
    "browser_sha256 hashes the web/runtime/reader/geometry/contracts sources plus the same "
    "settings and fixture. docker_sha256 hashes the production Dockerfile, assemble script, "
    "native product, and release stamps/lock. git_head is informational and never sufficient. "
    "Dirty means git reports uncommitted changes in those product paths at measurement time; "
    "accept still requires the content hashes to match the current tree."
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


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


def _skip_identity_file(path: Path) -> bool:
    parts = set(path.parts)
    if "node_modules" in parts or "__pycache__" in parts or ".venv" in parts:
        return True
    if path.suffix in {".pyc", ".map"}:
        return True
    return False


def iter_input_files(root: Path, spec: Iterable[str]) -> list[Path]:
    files: list[Path] = []
    for rel in spec:
        path = root / rel
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            for child in path.rglob("*"):
                if child.is_file() and not _skip_identity_file(child):
                    files.append(child)
    files.sort(key=lambda item: item.relative_to(root).as_posix())
    return files


def hash_input_spec(root: Path, spec: tuple[str, ...]) -> str:
    digest = hashlib.sha256()
    for path in iter_input_files(root, spec):
        rel = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(rel)
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def product_paths() -> tuple[str, ...]:
    return tuple(dict.fromkeys((*CLI_INPUT_PATHS, *BROWSER_INPUT_PATHS, *DOCKER_INPUT_PATHS)))


def implementation_dirty(root: Path) -> bool:
    proc = subprocess.run(
        ["git", "status", "--porcelain", "--", *product_paths()],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=20,
    )
    return bool((proc.stdout or "").strip())


def git_head(root: Path) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def implementation_identity(root: Path) -> dict[str, Any]:
    return {
        "schema": "inkflip-implementation-identity/1",
        "semantics": IDENTITY_SEMANTICS,
        "cli_sha256": hash_input_spec(root, CLI_INPUT_PATHS),
        "browser_sha256": hash_input_spec(root, BROWSER_INPUT_PATHS),
        "docker_sha256": hash_input_spec(root, DOCKER_INPUT_PATHS),
        "dirty": implementation_dirty(root),
        "git_head": git_head(root),
        "git_head_note": (
            "Informational checkout pointer only. Accept binds cli/browser/docker "
            "content hashes. A notes-only commit that does not touch product inputs "
            "keeps those hashes stable; dirty product files change the hashes."
        ),
    }


def build_artifact_identity(dist_dir: Path) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    if dist_dir.is_dir():
        for path in sorted(p for p in dist_dir.rglob("*") if p.is_file()):
            rel = path.relative_to(dist_dir).as_posix()
            digest = sha256_file(path)
            files.append({"path": rel, "sha256": digest, "bytes": path.stat().st_size})
    canonical = "".join(f"{item['path']} {item['sha256']}\n" for item in files)
    return {
        "production": True,
        "vite_dev_server": False,
        "tree_sha256": sha256_bytes(canonical.encode("utf-8")),
        "file_count": len(files),
        "files": files,
    }


def source_binding(root: Path) -> dict[str, Any]:
    fixture = root / "fixtures" / "public" / "mapping-control.pdf"
    settings = root / "planning" / "config" / "settings.json"
    identity = implementation_identity(root)
    binding: dict[str, Any] = {
        "root": str(root),
        "fixture_path": "fixtures/public/mapping-control.pdf",
        "fixture_sha256": sha256_file(fixture) if fixture.is_file() else None,
        "fixture_bytes": fixture.stat().st_size if fixture.is_file() else None,
        "settings_sha256": sha256_file(settings) if settings.is_file() else None,
        "implementation": identity,
        "git_head": identity.get("git_head"),
    }
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
    requested = stage.get("samples_requested")
    if requested is not None:
        if not isinstance(requested, int) or isinstance(requested, bool) or requested < 0:
            problems.append(f"{prefix} samples_requested must be a nonnegative integer")
        elif n >= 0 and failures >= 0 and n + failures != requested:
            problems.append(
                f"{prefix} inconsistent failures: n={n} + failures={failures} != samples_requested={requested}"
            )
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
    if require_distribution and failures > MAX_ACCEPT_FAILURES:
        problems.append(
            f"{prefix} failure-rate policy: mandatory Mac latency stages require "
            f"{MAX_ACCEPT_FAILURES} failures (observed failures={failures}, n={n}; "
            "30 successes plus extra failures is not a healthy run)"
        )
    samples = stage.get("samples_ms")
    if not isinstance(samples, list) or not samples:
        problems.append(f"{prefix} missing raw samples_ms (labels are not observations)")
        samples = []
    else:
        if any(not finite_number(item) for item in samples):
            problems.append(f"{prefix} samples_ms contains a non-finite or raw-invalid observation")
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
    if stage.get("open_status") == "parser_error" or stage.get("parser_error"):
        problems.append(
            "raster evidence is parser_error on an invalid/giant PDF; that does not prove clamping"
        )
    observed = stage.get("observed") if isinstance(stage.get("observed"), dict) else {}
    width = observed.get("width_px", stage.get("canvas_width"))
    height = observed.get("height_px", stage.get("canvas_height"))
    requested_scale = observed.get("requested_scale_px_per_pt")
    used_scale = observed.get("used_scale_px_per_pt")
    limitations = observed.get("limitations") or stage.get("limitations") or []
    pixel_cap = observed.get("pixel_cap", 4_000_000)
    edge_cap = observed.get("edge_cap", 8192)
    if not (finite_number(width) and finite_number(height) and float(width) > 0 and float(height) > 0):
        problems.append("raster pixel/edge budgets were not observed on a rendered page")
    else:
        pixels = float(width) * float(height)
        if pixels > float(pixel_cap):
            problems.append(f"observed raster {width}x{height} exceeds pixel cap {pixel_cap}")
        if max(float(width), float(height)) > float(edge_cap):
            problems.append(f"observed raster edge exceeds cap {edge_cap}")
        hit_pixel = bool(observed.get("pixel_budget_hit")) or (
            finite_number(requested_scale)
            and finite_number(used_scale)
            and float(requested_scale) > float(used_scale)
            and any("downsample" in str(item).lower() or "raster cap" in str(item).lower() for item in limitations)
        )
        if not hit_pixel and not stage.get("pixel_budget_enforced"):
            problems.append("raster pixel budget was not exercised at a real boundary")
        elif not hit_pixel and stage.get("pixel_budget_enforced") and not (
            finite_number(requested_scale) and finite_number(used_scale) and float(requested_scale) > float(used_scale)
        ):
            problems.append("raster pixel budget flag is not backed by a requested-vs-clamped scale observation")
        hit_edge = bool(observed.get("edge_budget_hit")) or (
            finite_number(requested_scale)
            and finite_number(used_scale)
            and float(requested_scale) > float(used_scale)
        )
        if not hit_edge and not stage.get("edge_budget_enforced"):
            problems.append("raster edge budget was not exercised at a real boundary")
    if stage.get("oversize_open_rejected") and not (
        finite_number(width) and finite_number(requested_scale)
    ):
        problems.append(
            "raster evidence is file-byte rejection only; pixel and edge budgets were not proven"
        )
    probe = stage.get("live_buffer_probe") if isinstance(stage.get("live_buffer_probe"), dict) else {}
    third = probe.get("third_claim")
    live_after_two = probe.get("live_after_two")
    if third != "raster_cap" or live_after_two != 2:
        if stage.get("live_buffers") == 2 or stage.get("live_buffer_cap_enforced"):
            problems.append(
                "live raster buffer cap was restated from the configured limit, not observed "
                "(need third_claim=raster_cap and live_after_two=2)"
            )
        else:
            problems.append("live raster buffer cap (2) was not evidenced by a third-claim refusal")
    workers = stage.get("ocr_worker_probe") if isinstance(stage.get("ocr_worker_probe"), dict) else {}
    worker_cap = workers.get("cap", stage.get("ocr_workers"))
    peak = workers.get("observed_active_peak")
    if not (worker_cap == 1 and finite_number(peak) and float(peak) >= 0):
        if stage.get("ocr_worker_cap_enforced") or stage.get("ocr_workers") == 1:
            problems.append("OCR worker cap flag is not backed by an observed active-worker peak")
        else:
            problems.append("OCR worker cap was not evidenced")
    elif finite_number(peak) and float(peak) > 1:
        problems.append(f"observed OCR workers {peak} exceeded cap 1")
    return problems


def _typed_memory_problems(label: str, value: Any, *, required: bool) -> list[str]:
    if value is None:
        return [f"{label} is missing"] if required else []
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return [f"{label} has wrong type {type(value).__name__}"]
    if not math.isfinite(float(value)):
        return [f"{label} is nonfinite"]
    if float(value) < 0:
        return [f"{label} is negative"]
    return []


def _memory_problems(browser: dict[str, Any], settings: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    memory = browser.get("memory") if isinstance(browser.get("memory"), dict) else {}
    heap = memory.get("js_heap_used_bytes")
    rss = memory.get("process_rss_bytes")
    peak = memory.get("measured_peak_rss_bytes")
    if memory.get("process_rss_unavailable") is True:
        problems.append(
            "process RSS is marked unavailable; inventory may list this, accept still requires measured RSS"
        )
    problems.extend(_typed_memory_problems("JS heap", heap, required=True))
    problems.extend(_typed_memory_problems("process RSS", rss, required=True))
    problems.extend(_typed_memory_problems("peak RSS", peak, required=True))
    if finite_number(heap) and finite_number(rss) and heap == rss:
        problems.append("JS heap and process RSS are identical; they must be distinct measurements")
    if finite_number(heap) and finite_number(peak) and heap == peak:
        problems.append("JS heap and peak RSS are identical; they must be distinct measurements")
    if finite_number(rss) and finite_number(peak) and float(peak) < float(rss):
        problems.append("peak RSS is below the recorded process RSS")
    rss_target = settings.get("browser", {}).get("measured_peak_rss_target_bytes")
    compare = peak if finite_number(peak) else rss
    if finite_number(compare) and finite_number(rss_target) and float(compare) > float(rss_target):
        problems.append(
            f"process RSS/peak {compare} exceeds declared measured_peak_rss_target_bytes {rss_target}"
        )
    return problems


def _implementation_from_body(body: dict[str, Any]) -> dict[str, Any] | None:
    binding = body.get("source_binding")
    if isinstance(binding, dict) and isinstance(binding.get("implementation"), dict):
        return binding["implementation"]
    if isinstance(body.get("implementation"), dict):
        return body["implementation"]
    return None


def _digest_field(value: Any) -> str | None:
    if isinstance(value, str) and len(value) == 64 and all(ch in "0123456789abcdef" for ch in value.lower()):
        return value.lower()
    return None


def _binding_problems(body: dict[str, Any], current: dict[str, Any] | None) -> list[str]:
    problems: list[str] = []
    binding = body.get("source_binding") or (body.get("measurement") or {}).get("source")
    if not isinstance(binding, dict):
        return ["missing source/build binding"]
    digest = _digest_field(binding.get("sha256") or binding.get("fixture_sha256"))
    if digest is None:
        problems.append("source binding is missing fixture sha256")
    settings_digest = _digest_field(binding.get("settings_sha256"))
    if settings_digest is None:
        problems.append("source binding is missing settings_sha256")
    identity = _implementation_from_body(body)
    if not isinstance(identity, dict):
        problems.append("missing implementation identity (git HEAD is not a substitute)")
        identity = {}
    for key in ("cli_sha256", "browser_sha256", "docker_sha256"):
        if _digest_field(identity.get(key)) is None:
            problems.append(f"missing implementation {key}")
    if "dirty" not in identity or not isinstance(identity.get("dirty"), bool):
        problems.append("implementation dirty flag is missing (HEAD does not identify a dirty tree)")
    if current:
        current_digest = _digest_field(current.get("fixture_sha256"))
        if digest is None:
            pass
        elif current_digest and digest != current_digest:
            problems.append(
                f"stale source identity: receipt fixture sha256 {digest} != current {current_digest}"
            )
        elif not current_digest:
            problems.append("current tree is missing fixture sha256; cannot verify source binding")
        current_settings = _digest_field(current.get("settings_sha256"))
        if settings_digest is None:
            pass
        elif current_settings and settings_digest != current_settings:
            problems.append("stale source identity: planning/config/settings.json hash does not match this tree")
        elif not current_settings:
            problems.append("current tree is missing settings_sha256; cannot verify source binding")
        current_impl = current.get("implementation") if isinstance(current.get("implementation"), dict) else {}
        for key in ("cli_sha256", "browser_sha256", "docker_sha256"):
            recorded = _digest_field(identity.get(key))
            expected = _digest_field(current_impl.get(key))
            if recorded and expected and recorded != expected:
                problems.append(
                    f"stale implementation identity: {key} {recorded} != current {expected}"
                )
            elif recorded and not expected:
                problems.append(f"current tree is missing implementation {key}")
        if current_impl.get("dirty") is True and identity.get("dirty") is False:
            problems.append(
                "measured implementation is dirty but the receipt claims a clean tree"
            )
    return problems


def _browser_build_problems(build: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    if build.get("production") and not build.get("tree_sha256") and not build.get("files"):
        problems.append(
            "browser production flag is not build identity; bind actual built bytes (tree_sha256/files)"
        )
    if not build.get("production"):
        problems.append("browser evidence is not an identified production (or labelled instrumented-production) build")
    if build.get("vite_dev_server"):
        problems.append("browser evidence was collected against a Vite development server")
    tree = _digest_field(build.get("tree_sha256"))
    files = build.get("files")
    if tree is None and not (isinstance(files, list) and files):
        problems.append("browser evidence is missing built-artifact identity")
    if isinstance(files, list):
        for entry in files:
            if not isinstance(entry, dict) or _digest_field(entry.get("sha256")) is None:
                problems.append("browser build file list contains an entry without sha256")
                break
        if files and tree:
            canonical = "".join(
                f"{item.get('path')} {str(item.get('sha256')).lower()}\n"
                for item in files
                if isinstance(item, dict)
            )
            expected = sha256_bytes(canonical.encode("utf-8"))
            if expected != tree:
                problems.append("browser build tree_sha256 does not match hashed file list")
    return problems


def _baseline_problems(browser: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    replace = browser.get("replace_clear_cycles") if isinstance(browser.get("replace_clear_cycles"), dict) else {}
    baseline = replace.get("baseline") if isinstance(replace.get("baseline"), dict) else {}
    if int(replace.get("n") or 0) < 10:
        problems.append("replace/clear cycles were not executed for at least 10 files")
        return problems
    if not isinstance(baseline, dict) or "first_js_heap_used_bytes" not in baseline:
        problems.append("replace/clear cycles did not record baseline-return measurements")
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
            problems.extend(_browser_build_problems(build))
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
            problems.extend(_baseline_problems(browser))
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
