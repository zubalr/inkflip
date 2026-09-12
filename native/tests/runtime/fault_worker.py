"""T29 fault-injection child: real spawned worker doubles (TEST-29).

Stdlib-only scenario workers exercising the supervisor's bounds: hang,
native-like crash (real SIGSEGV), memory growth, stdout/stderr flood,
SIGTERM-ignoring, descendant leaking, deterministic report writer, empty
success, fail-once-retry, and environment capture. Every mode is bounded or
killable; none touches the network, models or reader engines.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

REPORT_NAME = "report.json"


def _write_report(payload: dict) -> None:
    Path(REPORT_NAME).write_bytes(
        (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    )


def _sleep_forever() -> None:
    while True:
        time.sleep(60)


def scenario_report(argv: list) -> int:
    # Deterministic bytes: identical invocations produce identical reports.
    text = argv[argv.index("--text") + 1] if "--text" in argv else "$100"
    _write_report({"kind": "worker-report", "text": text})
    print("report written", flush=True)
    return 0


def scenario_empty(_argv: list) -> int:
    return 0  # empty success: exit 0, no declared output


def scenario_exit_fail(argv: list) -> int:
    code = int(argv[argv.index("--code") + 1]) if "--code" in argv else 17
    print("failing on purpose", file=sys.stderr, flush=True)
    return code


def scenario_crash(_argv: list) -> int:
    # Native-like crash: die on a real signal, not a Python exception.
    os.kill(os.getpid(), signal.SIGSEGV)
    return 99  # unreachable


def scenario_hang(_argv: list) -> int:
    _sleep_forever()
    return 0


def scenario_sigint_parent(_argv: list) -> int:
    # Deliver a Ctrl-C-equivalent SIGINT to the supervising parent, then hang:
    # the parent must cancel, kill our process group and keep partial results.
    os.kill(os.getppid(), signal.SIGINT)
    _sleep_forever()
    return 0


def scenario_term_ignorer(_argv: list) -> int:
    # Native-like hang: ignores polite termination; only SIGKILL reaps it.
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    _sleep_forever()
    return 0


def scenario_flood(argv: list) -> int:
    stream = sys.stderr if "--stderr" in argv else sys.stdout
    block = "x" * 4096 + "\n"
    while True:
        stream.write(block)
        stream.flush()


def scenario_oom(argv: list) -> int:
    # Grow resident memory in chunks until the rlimit trips (Linux) or the
    # parent's RSS probe kills us (macOS); then hold so the probe sees us.
    chunk_mb = int(argv[argv.index("--chunk-mb") + 1]) if "--chunk-mb" in argv else 8
    hold = "--hold" in argv
    chunks = []
    try:
        for _ in range(512):  # up to ~4 GiB; limits stop us far earlier
            block = bytearray(chunk_mb << 20)
            for i in range(0, len(block), 4096):
                block[i] = 1
            chunks.append(block)
            time.sleep(0.02)
    except MemoryError:
        print("MemoryError: simulated allocation bound tripped", file=sys.stderr, flush=True)
        return 1
    if hold:
        _sleep_forever()
    return 0


def scenario_hang_grandchild(argv: list) -> int:
    # Spawn a same-group descendant that must die with us, then hang.
    pids_file = argv[argv.index("--pids-file") + 1]
    grandchild = subprocess.Popen(
        [sys.executable, "-c", "import time\nwhile True: time.sleep(60)"]
    )
    Path(pids_file).write_text(json.dumps({"child": os.getpid(), "grandchild": grandchild.pid}))
    _sleep_forever()
    return 0


def scenario_leak_grandchild(argv: list) -> int:
    # Spawn a same-group descendant then exit 0: the supervisor must reap the
    # stray member even though the leader completed.
    pids_file = argv[argv.index("--pids-file") + 1]
    grandchild = subprocess.Popen(
        [sys.executable, "-c", "import time\nwhile True: time.sleep(60)"]
    )
    Path(pids_file).write_text(json.dumps({"child": os.getpid(), "grandchild": grandchild.pid}))
    _write_report({"kind": "worker-report", "text": "leaker"})
    return 0


def scenario_leak_stubborn_grandchild(argv: list) -> int:
    # Spawn a same-group descendant that IGNORES SIGTERM, wait for it to
    # install its handler, then exit 0. The post-reap stray probe must
    # escalate to SIGKILL — and the ~kill_grace window it spends doing so
    # blocks the parent loop, which is what the post-reap output-overflow
    # regression test needs.
    pids_file = argv[argv.index("--pids-file") + 1]
    grandchild = subprocess.Popen(
        [
            sys.executable, "-c",
            "import signal, time\n"
            "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
            "while True: time.sleep(60)",
        ]
    )
    Path(pids_file).write_text(
        json.dumps({"child": os.getpid(), "grandchild": grandchild.pid})
    )
    time.sleep(0.3)  # let the grandchild install SIG_IGN before we exit
    _write_report({"kind": "worker-report", "text": "stubborn-leaker"})
    return 0


def scenario_delayed_flood(argv: list) -> int:
    # Sleep, then emit a single bounded burst and exit 0. With a sibling
    # blocking the parent loop (leak-stubborn-grandchild), the burst is only
    # drained by _drain_until_eof AFTER this child is reaped — exercising the
    # post-reap output-limit classification path.
    seconds = float(argv[argv.index("--seconds") + 1])
    count = int(argv[argv.index("--bytes") + 1])
    stream = sys.stderr if "--stderr" in argv else sys.stdout
    time.sleep(seconds)
    stream.write("y" * count)
    stream.flush()
    return 0


def scenario_fail_once(argv: list) -> int:
    # Fail attempt 1, succeed attempt 2: exercises the one bounded retry.
    state = Path(argv[argv.index("--state") + 1])
    if state.exists():
        _write_report({"kind": "worker-report", "text": "second-attempt"})
        return 0
    state.write_text("attempted")
    return 17


def scenario_slow_report(argv: list) -> int:
    seconds = float(argv[argv.index("--seconds") + 1])
    time.sleep(seconds)
    _write_report({"kind": "worker-report", "text": f"slept-{seconds}"})
    return 0


def scenario_env_report(_argv: list) -> int:
    # Report exactly which environment the supervisor gave us.
    _write_report({"kind": "env-report", "env_keys": sorted(os.environ)})
    return 0


SCENARIOS = {
    "report": scenario_report,
    "empty": scenario_empty,
    "exit-fail": scenario_exit_fail,
    "crash": scenario_crash,
    "hang": scenario_hang,
    "sigint-parent": scenario_sigint_parent,
    "term-ignorer": scenario_term_ignorer,
    "flood": scenario_flood,
    "oom": scenario_oom,
    "hang-grandchild": scenario_hang_grandchild,
    "leak-grandchild": scenario_leak_grandchild,
    "leak-stubborn-grandchild": scenario_leak_stubborn_grandchild,
    "delayed-flood": scenario_delayed_flood,
    "fail-once": scenario_fail_once,
    "slow-report": scenario_slow_report,
    "env-report": scenario_env_report,
}


def main() -> int:
    scenario = sys.argv[1]
    return SCENARIOS[scenario](sys.argv[2:])


if __name__ == "__main__":
    raise SystemExit(main())
