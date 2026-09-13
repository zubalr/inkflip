"""Inkflip corpus execution runner (T32).

Coordinates supervised execution of corpus manifests with:
- Strict path containment
- Atomic per-file reports
- Terminal index.json and journal.jsonl
- Validated resume preserving byte-identical reports
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_NATIVE_ROOT = Path(__file__).resolve().parents[2]
if str(_NATIVE_ROOT) not in sys.path:
    sys.path.insert(0, str(_NATIVE_ROOT))

from inkflip.corpus.manifest import (
    ContainmentError,
    CorpusError,
    IntegrityError,
    ManifestValidationError,
    load_and_validate_manifest,
)
from inkflip.runtime import JobSpec, Limits, RunResult, Supervisor, SupervisionError


def run_corpus(
    manifest_path: Path | str,
    source_root: Path | str,
    profile: str,
    out_dir: Path | str,
    jobs: int = 1,
    resume: bool = False,
    limits: Limits | None = None,
) -> RunResult:
    """Execute corpus run over a validated manifest within contained source root.

    Writes:
      <out_dir>/journal.jsonl
      <out_dir>/index.json
      <out_dir>/reports/<key>.json
    """
    manifest_path = Path(manifest_path).resolve()
    source_root = Path(source_root).resolve()
    out_dir = Path(out_dir).resolve()

    manifest_data, entries = load_and_validate_manifest(manifest_path, source_root)

    job_specs: list[JobSpec] = []
    for entry in entries:
        argv = [
            sys.executable,
            "-m",
            "inkflip.cli",
            "inspect",
            str(entry.resolved_path),
            "--out",
            "report.json",
        ]
        if entry.pages is not None:
            pages_arg = ",".join(str(p + 1) for p in entry.pages)
            argv.extend(["--pages", pages_arg])
        if entry.ocr_pages is not None:
            ocr_pages_arg = ",".join(str(p + 1) for p in entry.ocr_pages)
            argv.extend(["--ocr-pages", ocr_pages_arg])

        argv.extend(["--profile", profile])

        job_specs.append(
            JobSpec(
                key=entry.key,
                argv=argv,
                produces="report.json",
                env={"PYTHONPATH": str(_NATIVE_ROOT)},
            )
        )

    if limits is None:
        limits = Limits(jobs=jobs, wall_seconds=120.0, memory_bytes=1 << 29)
    else:
        limits.jobs = jobs

    supervisor = Supervisor(out_dir, limits, resume=resume)
    result = supervisor.run(job_specs)
    return result
