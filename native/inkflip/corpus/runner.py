"""Supervised corpus execution with identity-bound resume (T32)."""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

from inkflip.cli.inspect import ALGORITHM_ID
from inkflip.cli.paths import directories_overlap
from inkflip.contracts import core
from inkflip.corpus.manifest import (
    CorpusError,
    CorpusEntry,
    load_and_validate_manifest,
)
from inkflip.profiles import BUILTIN_PROFILE_NAMES, default_profiles_dir, load_profile
from inkflip.runtime import JobSpec, Limits, RunResult, Supervisor, SupervisionError
from inkflip.runtime.artifacts import atomic_write_bytes

_NATIVE_ROOT = Path(__file__).resolve().parents[2]


def _profile_identity(profile_name: str) -> tuple[str, str]:
    if profile_name in BUILTIN_PROFILE_NAMES:
        return profile_name, hashlib.sha256(f"builtin:{profile_name}".encode()).hexdigest()
    profile = load_profile(profile_name, base_dir=default_profiles_dir())
    return profile.name, profile.profile_sha256


def _validate_committed_report(data: bytes) -> None:
    report = core.loads_strict(data)
    core.validate(report)


def run_corpus(
    manifest_path: Path | str,
    source_root: Path | str,
    profile: str,
    out_dir: Path | str,
    jobs: int = 1,
    resume: bool = False,
    limits: Limits | None = None,
) -> RunResult:
    manifest_path = Path(manifest_path).resolve()
    source_root = Path(source_root).resolve()
    out_dir = Path(out_dir).resolve()
    if directories_overlap(source_root, out_dir):
        raise CorpusError("Output directory must not overlap source-root")

    manifest_data, entries, manifest_sha = load_and_validate_manifest(manifest_path, source_root)
    profile_name, profile_sha = _profile_identity(profile)
    profiles_dir = str(default_profiles_dir().resolve())
    settings_sha = hashlib.sha256(
        json.dumps(
            {"profile": profile_name, "algorithm": ALGORITHM_ID, "jobs": jobs},
            sort_keys=True,
        ).encode()
    ).hexdigest()

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
            "--profile",
            profile_name,
        ]
        if entry.pages is not None:
            argv.extend(["--pages", ",".join(str(page + 1) for page in entry.pages)])
        env = {
            "PYTHONPATH": str(_NATIVE_ROOT),
            "INKFLIP_PROFILES_DIR": profiles_dir,
            "INKFLIP_SOURCE_SHA256": entry.sha256,
            "INKFLIP_MANIFEST_SHA256": manifest_sha,
            "INKFLIP_PROFILE_SHA256": profile_sha,
            "INKFLIP_ALGORITHM_ID": ALGORITHM_ID,
            "INKFLIP_SETTINGS_SHA256": settings_sha,
        }
        job_specs.append(
            JobSpec(
                key=entry.key,
                argv=argv,
                produces="report.json",
                env=env,
            )
        )

    if limits is None:
        limits = Limits(jobs=jobs, wall_seconds=180.0, memory_bytes=1 << 30)
    supervisor = Supervisor(
        out_dir,
        limits,
        resume=resume,
        validate_report=_validate_committed_report,
    )
    try:
        result = supervisor.run(job_specs)
    except SupervisionError as exc:
        raise CorpusError(str(exc)) from exc

    identity = {
        "kind": "inkflip-corpus-identity",
        "corpus_manifest_sha256": manifest_sha,
        "profile_sha256": profile_sha,
        "profile_name": profile_name,
        "algorithm_id": ALGORITHM_ID,
        "settings_sha256": settings_sha,
        "intended_keys": [entry.key for entry in entries],
        "source_root": str(source_root),
        "manifest_path": str(manifest_path),
        "split": manifest_data.get("split"),
    }
    atomic_write_bytes(
        out_dir / "identity.json",
        (json.dumps(identity, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )
    return result
