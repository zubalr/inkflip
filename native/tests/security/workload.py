"""Owned synthetic workload for T40 containment tests.

Hang, crash, stdout flood, path-escape attempt and a successful report.
Launched as a real child of the supervisor — not a mocked argv string.
"""
from __future__ import annotations

import json
import os
import signal
import sys
import time
from pathlib import Path

REPORT = "report.json"


def write_report(payload: dict) -> None:
    Path(REPORT).write_bytes(
        (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    )


def main() -> int:
    mode = sys.argv[1]
    if mode == "ok":
        text = sys.argv[2] if len(sys.argv) > 2 else "synthetic-ok"
        write_report({"kind": "t40-workload", "text": text, "pid": os.getpid()})
        print("ok", flush=True)
        return 0
    if mode == "hang":
        while True:
            time.sleep(60)
    if mode == "sigint-parent":
        os.kill(os.getppid(), signal.SIGINT)
        while True:
            time.sleep(60)
    if mode == "crash":
        os.kill(os.getpid(), signal.SIGSEGV)
        return 99
    if mode == "flood":
        block = "x" * 4096 + "\n"
        while True:
            sys.stdout.write(block)
            sys.stdout.flush()
    if mode == "tmpdir-write":
        dest = Path(os.environ["TMPDIR"]) / "scratch-write.txt"
        dest.write_text("in-scratch\n")
        write_report({"kind": "t40-workload", "tmpdir": os.environ.get("TMPDIR"), "wrote": str(dest)})
        return 0
    raise SystemExit(f"unknown mode {mode!r}")


if __name__ == "__main__":
    raise SystemExit(main())
