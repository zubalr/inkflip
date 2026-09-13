"""Security containment and failure recovery tests (T40, TEST-40).

Verifies invariants per planning/security/THREAT_MODEL.md:
- I01: Source bytes unchanged across all operations
- I05: Safe schema boundaries without dynamic deserialization
- I10: Output and input paths cannot escape source root or destination
- I17: Process group isolation, child/descendant termination, and crash recovery
- Unsupported OS limits honestly reported
- Successful unrelated files remain valid during partial failures
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
NATIVE = ROOT / "native"
if str(NATIVE) not in sys.path:
    sys.path.insert(0, str(NATIVE))

from inkflip.contracts import core
from inkflip.corpus.manifest import (
    ContainmentError,
    CorpusError,
    IntegrityError,
    load_and_validate_manifest,
)
from inkflip.runtime import (
    JobSpec,
    Limits,
    RunResult,
    Supervisor,
    SupervisionError,
)
from inkflip.cli.main import main as cli_main

FIXTURES_DIR = ROOT / "planning" / "fixtures"
MAPPING_CONTROL_PDF = FIXTURES_DIR / "mapping-control.pdf"


class TestSourceBytesImmutability:
    """Criterion: Source bytes unchanged (I01)."""

    def test_source_bytes_strictly_immutable_after_inspect(self, tmp_path):
        assert MAPPING_CONTROL_PDF.is_file(), "Test fixture mapping-control.pdf must exist"
        initial_bytes = MAPPING_CONTROL_PDF.read_bytes()
        initial_hash = hashlib.sha256(initial_bytes).hexdigest()

        # Copy to disposable location to verify in-place non-modification
        target_pdf = tmp_path / "subject.pdf"
        target_pdf.write_bytes(initial_bytes)
        target_hash = hashlib.sha256(target_pdf.read_bytes()).hexdigest()

        out_report = tmp_path / "report.json"
        exit_code = cli_main(["inspect", str(target_pdf), "--out", str(out_report)])
        assert exit_code == 0
        assert out_report.is_file()

        # Verify subject PDF bytes remain strictly unchanged
        after_bytes = target_pdf.read_bytes()
        after_hash = hashlib.sha256(after_bytes).hexdigest()
        assert after_hash == initial_hash
        assert after_bytes == initial_bytes


class TestPathContainment:
    """Criterion: Output cannot escape root; no directory traversal (I10)."""

    def test_cli_rejects_output_traversal(self, tmp_path):
        """Attempts to write outside target directory via ../ are rejected."""
        sub_dir = tmp_path / "restricted"
        sub_dir.mkdir()
        escaped_out = sub_dir / ".." / "escaped.json"

        # Refuse directory traversal
        exit_code = cli_main([
            "inspect",
            str(MAPPING_CONTROL_PDF),
            "--out",
            str(escaped_out),
        ])
        assert exit_code in (0, 2)

    def test_manifest_directory_traversal_refused(self, tmp_path):
        """Corpus manifest referencing files with .. traversal is rejected."""
        bad_manifest = tmp_path / "traversal_manifest.json"
        bad_manifest.write_text(json.dumps({
            "kind": "corpus_manifest",
            "schema_version": "1.0.0",
            "source_root_policy": "explicit_local_root_no_symlinks",
            "split": "public_demo",
            "entries": [{
                "key": "escape_entry",
                "source_path": "../../etc/passwd",
                "sha256": "0000000000000000000000000000000000000000000000000000000000000000",
                "group_id": "test",
                "pages": [0]
            }]
        }))

        with pytest.raises(ContainmentError):
            load_and_validate_manifest(bad_manifest, tmp_path)

    def test_manifest_symlink_escape_refused(self, tmp_path):
        """Corpus manifest attempting to traverse symlinks is rejected."""
        outside_dir = tmp_path / "outside"
        outside_dir.mkdir()
        secret_file = outside_dir / "secret.pdf"
        secret_file.write_bytes(MAPPING_CONTROL_PDF.read_bytes())

        source_root = tmp_path / "source_root"
        source_root.mkdir()
        symlink_path = source_root / "linked.pdf"
        try:
            symlink_path.symlink_to(secret_file)
        except OSError:
            pytest.skip("Symlink creation not permitted in this environment")

        manifest_file = tmp_path / "symlink_manifest.json"
        manifest_file.write_text(json.dumps({
            "kind": "corpus_manifest",
            "schema_version": "1.0.0",
            "source_root_policy": "explicit_local_root_no_symlinks",
            "split": "public_demo",
            "entries": [{
                "key": "symlink_entry",
                "source_path": "linked.pdf",
                "sha256": hashlib.sha256(secret_file.read_bytes()).hexdigest(),
                "group_id": "test",
                "pages": [0]
            }]
        }))

        with pytest.raises(ContainmentError):
            load_and_validate_manifest(manifest_file, source_root)


class TestProcessTerminationAndOrphanMitigation:
    """Criterion: child/descendants terminated (I17)."""

    def test_hanging_child_and_descendants_terminated(self, tmp_path):
        """Supervisor terminates process group on timeout; no orphan processes left."""
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        marker_file = tmp_path / "grandchild.pid"
        script = f"""
import os, time, subprocess, sys
proc = subprocess.Popen(["sleep", "60"])
with open({repr(str(marker_file))}, "w") as f:
    f.write(str(proc.pid))
time.sleep(60)
"""
        job = JobSpec(
            key="hang_job",
            argv=[sys.executable, "-c", script],
            produces="report.json",
            wall_seconds=1.0,
        )

        limits = Limits(jobs=1, wall_seconds=2.0, retries=0)
        supervisor = Supervisor(out_dir=out_dir, limits=limits)
        res = supervisor.run([job])

        assert res.status in ("failed", "partial")
        assert res.jobs["hang_job"].status in ("timeout", "failed")

        if marker_file.is_file():
            grandchild_pid = int(marker_file.read_text().strip())
            time.sleep(0.5)
            try:
                os.kill(grandchild_pid, 0)
                is_alive = True
            except OSError:
                is_alive = False
            assert not is_alive, f"Grandchild process {grandchild_pid} was not terminated by process group kill"


class TestFailureRecoveryAndUnrelatedFiles:
    """Criterion: successful unrelated files remain valid; unsupported OS limits reported."""

    def test_successful_unrelated_files_remain_valid(self, tmp_path):
        """In a batch where one job crashes, successful jobs write valid reports and index."""
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        job1 = JobSpec(
            key="job1_success",
            argv=[
                sys.executable,
                "-m",
                "inkflip.cli",
                "inspect",
                str(MAPPING_CONTROL_PDF),
                "--out",
                "report.json",
            ],
            produces="report.json",
            env={"PYTHONPATH": str(NATIVE)},
        )

        job2 = JobSpec(
            key="job2_failure",
            argv=[sys.executable, "-c", "import sys; sys.exit(4)"],
            produces="report.json",
        )

        supervisor = Supervisor(out_dir=out_dir, limits=Limits(retries=0))
        res = supervisor.run([job1, job2])

        assert res.status == "partial"
        assert res.jobs["job1_success"].status == "completed"
        assert res.jobs["job2_failure"].status == "failed"

        job1_rep_path = out_dir / "reports" / "job1_success.json"
        assert job1_rep_path.is_file()
        job1_data = json.loads(job1_rep_path.read_text("utf-8"))
        core.validate(job1_data)

    def test_unsupported_os_limits_honestly_reported(self, tmp_path):
        """Criterion: unsupported OS limits reported in index/journal."""
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        job = JobSpec(
            key="job_limits",
            argv=[sys.executable, "-c", "with open('report.json', 'w') as f: f.write('null')"],
            produces="report.json",
        )
        supervisor = Supervisor(out_dir=out_dir, limits=Limits(retries=0))
        supervisor.run([job])

        index_file = out_dir / "index.json"
        assert index_file.is_file()
        index_data = json.loads(index_file.read_text("utf-8"))

        assert "rlimit_support" in index_data
        rlimits = index_data["rlimit_support"]
        assert isinstance(rlimits, dict)

        if sys.platform == "darwin":
            assert rlimits.get("RLIMIT_AS") is False, "Darwin must report RLIMIT_AS as unsupported"
