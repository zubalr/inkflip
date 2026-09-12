"""Atomic per-file artifacts and the immutable run journal (T29).

Implements the durability half of ``planning/architecture/RUNTIME_LIFECYCLE.md``
"Native supervision": every committed per-file report is written to an
exclusive temporary sibling, fsynced, then atomically renamed (with the
containing directory fsynced so the rename itself is durable). A crash at any
point can leave a ``*.tmp-*`` sibling but never a torn target file.

The journal is append-only: records are single JSON lines written with one
``os.write`` and fsynced individually. It is never rewritten, truncated or
reordered. A reader tolerates a torn final line (the write interrupted by a
kill/power loss) without "repairing" the file — immutability means ignoring
the tail, not editing it (I17).

Source discipline per the same document: legacy batch processing (s06) and
watchdog fault-injection tests (s17) inform the design; this implementation is
new code.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Iterator


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path, _chunk: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            block = handle.read(_chunk)
            if not block:
                return digest.hexdigest()
            digest.update(block)


def config_digest(value: Any) -> str:
    """SHA-256 of a deterministic JSON encoding of a job/run configuration."""
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256_bytes(canonical)


def _fsync_dir(path: Path) -> None:
    """fsync a directory entry so a rename inside it is durable (POSIX only)."""
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def atomic_write_bytes(path: Path, data: bytes) -> Path:
    """Write ``data`` to ``path`` atomically: exclusive tmp sibling -> fsync ->
    rename -> directory fsync. Returns the final path. ``path`` may already
    exist (os.replace is atomic); callers decide overwrite policy — this helper
    only guarantees that readers never see a torn file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=path.name + ".tmp-", dir=path.parent
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
        _fsync_dir(path.parent)
    except BaseException:
        try:
            tmp_path.unlink()
        except OSError:
            pass
        raise
    return path


class Journal:
    """Append-only run journal: one fsynced JSON object per line.

    The file is opened in binary append mode with no user-space buffering; each
    record is a single ``os.write`` so a line is never interleaved or partially
    flushed under normal operation. Nothing is ever rewritten — ``close`` is
    the only lifecycle operation.
    """

    def __init__(self, path: Path, run_id: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.run_id = run_id
        self._fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        # Continue sequence numbering across appended runs (resume): seq is
        # the global line number, never restarted.
        self._seq = 0
        if self.path.exists():
            with open(self.path, "rb") as existing:
                for line in existing:
                    if line.strip():
                        self._seq += 1
        self._closed = False

    def record(self, event: str, **fields: Any) -> dict:
        """Append one fsynced record; returns the stored object."""
        if self._closed:
            raise ValueError("journal is closed")
        self._seq += 1
        entry = {
            "seq": self._seq,
            "run_id": self.run_id,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "ts_mono": round(time.monotonic(), 6),
            "event": event,
            **fields,
        }
        line = (json.dumps(entry, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        os.write(self._fd, line)
        os.fsync(self._fd)
        return entry

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            os.close(self._fd)

    def __enter__(self) -> "Journal":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def read_journal(path: Path) -> Iterator[dict]:
    """Yield parsed journal records. A torn/truncated final line (partial
    write interrupted by a kill) is skipped, never repaired; complete lines
    that fail to parse raise ValueError — the journal is append-only, so a
    corrupt middle line means tampering or a real defect, not a torn tail."""
    data = Path(path).read_bytes()
    lines = data.split(b"\n")
    for index, raw in enumerate(lines):
        if not raw:
            continue  # trailing newline produces a final empty segment
        try:
            record = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            if index == len(lines) - 1:
                return  # torn final write: tolerated, not repaired
            raise ValueError(f"corrupt journal line {index + 1} in {path}")
        if not isinstance(record, dict):
            raise ValueError(f"journal line {index + 1} is not an object in {path}")
        yield record
