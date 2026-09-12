"""T29 test driver: run a Supervisor in a real process (TEST-29).

Usage: ``python supervisor_driver.py SPEC.json OUT_DIR``

SPEC: {"jobs": [{"key": str, "worker_args": [str], "produces": str|null,
                 "wall_seconds": f|null, "memory_bytes": i|null,
                 "env": {str: str}}],
       "limits": {...}, "resume": bool, "run_result_file": str}

Builds JobSpecs whose argv is ``[sys.executable, fault_worker.py, *worker_args]``,
runs the Supervisor, and writes the RunResult JSON to ``run_result_file``.
Exits 0 even when the run cancels — the artifact is what the test inspects.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from inkflip.runtime import JobSpec, Limits, Supervisor  # noqa: E402
from inkflip.runtime.artifacts import atomic_write_bytes  # noqa: E402

WORKER = Path(__file__).resolve().parent / "fault_worker.py"


def main() -> int:
    spec = json.loads(Path(sys.argv[1]).read_text())
    out_dir = Path(sys.argv[2])
    limits = Limits(**spec.get("limits", {}))
    jobs = [
        JobSpec(
            key=j["key"],
            argv=[sys.executable, str(WORKER), *j["worker_args"]],
            produces=j.get("produces"),
            env=j.get("env", {}),
            wall_seconds=j.get("wall_seconds"),
            memory_bytes=j.get("memory_bytes"),
        )
        for j in spec["jobs"]
    ]
    result = Supervisor(out_dir, limits, resume=spec.get("resume", False)).run(jobs)
    atomic_write_bytes(
        Path(spec["run_result_file"]),
        (json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
