"""Invoke a verified isolated reader profile without a shell (T33)."""
from __future__ import annotations

import json
import os
import signal
import subprocess
import threading
from pathlib import Path
from typing import Any

from inkflip.profiles.models import ProfileError, ReaderProfile

_OFFLINE_ENV_BLOCKLIST = (
    "http_proxy",
    "https_proxy",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "all_proxy",
    "FTP_PROXY",
    "ftp_proxy",
)


def offline_child_env() -> dict[str, str]:
    env = {
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONIOENCODING": "utf-8",
        "NO_PROXY": "*",
        "no_proxy": "*",
    }
    path = os.environ.get("PATH")
    if path:
        env["PATH"] = path
    for key, value in os.environ.items():
        if key in _OFFLINE_ENV_BLOCKLIST:
            continue
        if key.startswith("INKFLIP_"):
            env[key] = value
    return env


# Bounded child I/O. A worker is untrusted input: `capture_output=True` alone
# would let an arbitrarily large or flooding response exhaust memory before any
# validation runs, so both streams are drained against a hard cap and the whole
# process group is killed on overflow or deadline.
_MAX_STDOUT_BYTES = 8 * 1024 * 1024
_MAX_STDERR_BYTES = 64 * 1024
_READ_CHUNK = 65536
_DIAGNOSTIC_CHARS = 400


class _DuplicatedField(Exception):
    """A JSON object in a worker response repeated a member name."""


def _no_duplicate_members(items):
    seen: dict[str, Any] = {}
    for key, value in items:
        if key in seen:
            raise _DuplicatedField(key)
        seen[key] = value
    return seen


def _bounded_read(stream, limit: int, sink: list[bytes], overflow: list[bool]) -> None:
    total = 0
    try:
        while True:
            chunk = stream.read(_READ_CHUNK)
            if not chunk:
                break
            if total < limit:
                keep = min(len(chunk), limit - total)
                sink.append(chunk[:keep])
                total += keep
            if total >= limit:
                overflow[0] = True
    except (OSError, ValueError):
        pass
    finally:
        try:
            stream.close()
        except Exception:
            pass


def _kill_group(pgid: int) -> None:
    """SIGKILL an entire worker process group, ignoring a group that is gone."""
    try:
        os.killpg(pgid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        pass


def _terminate(proc: subprocess.Popen, pgid: int) -> None:
    """Kill the worker's whole process group; descendants must not survive.

    The group id is captured while the leader is alive, so this also reaps a
    grandchild that the worker spawned and then abandoned: the leader may have
    exited already, but the group still exists and is still signalled.
    """
    try:
        os.killpg(pgid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        pass
    if proc.poll() is None:
        try:
            proc.kill()
        except OSError:
            pass
    try:
        proc.wait(timeout=5.0)
    except Exception:
        pass


def _run_child(argv: list[str], payload: bytes, timeout: float) -> tuple[int, bytes, bytes, str | None]:
    """Run one worker with bounded capture. Returns (rc, stdout, stderr, fault)."""
    try:
        proc = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            env=offline_child_env(),
            start_new_session=True,
        )
    except OSError as exc:
        raise ProfileError(f"Failed to execute profile worker: {exc}") from exc

    try:
        pgid = os.getpgid(proc.pid)
    except OSError:
        pgid = proc.pid

    out_sink: list[bytes] = []
    err_sink: list[bytes] = []
    out_overflow = [False]
    err_overflow = [False]
    readers = [
        threading.Thread(target=_bounded_read, args=(proc.stdout, _MAX_STDOUT_BYTES, out_sink, out_overflow)),
        threading.Thread(target=_bounded_read, args=(proc.stderr, _MAX_STDERR_BYTES, err_sink, err_overflow)),
    ]
    for thread in readers:
        thread.daemon = True
        thread.start()

    writer = threading.Thread(target=_write_stdin, args=(proc, payload))
    writer.daemon = True
    writer.start()

    fault: str | None = None
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        fault = f"timed out after {timeout}s"
    # The leader has exited or the deadline passed. Kill the group *before*
    # joining the readers: a descendant the worker spawned and abandoned still
    # holds the inherited stdout/stderr pipes open, so without this the readers
    # block until their join timeout and a valid response would be lost.
    _kill_group(pgid)
    for thread in readers:
        thread.join(timeout=5.0)
    writer.join(timeout=5.0)

    if fault is None and out_overflow[0]:
        fault = f"stdout exceeded the {_MAX_STDOUT_BYTES}-byte capture bound"
    if fault is None and err_overflow[0]:
        fault = f"stderr exceeded the {_MAX_STDERR_BYTES}-byte capture bound"
    if fault is not None:
        _terminate(proc, pgid)
        raise ProfileError(f"Profile worker {fault}")

    _terminate(proc, pgid)  # reaps leftovers, including abandoned descendants
    return proc.returncode, b"".join(out_sink), b"".join(err_sink), None


def _write_stdin(proc: subprocess.Popen, payload: bytes) -> None:
    try:
        if proc.stdin is not None:
            proc.stdin.write(payload)
            proc.stdin.close()
    except (OSError, ValueError, BrokenPipeError):
        pass


def _diagnostic(stderr: bytes) -> str:
    text = stderr.decode("utf-8", "replace").strip()
    text = text.replace("\x00", "")
    if not text:
        return ""
    return f": {text[:_DIAGNOSTIC_CHARS]}"


class ProfileAdapter:
    """Runs the bundled wrapper under the profile's recorded interpreter."""

    def __init__(self, profile: ReaderProfile):
        self.profile = profile

    def _argv(self) -> list[str]:
        return [str(self.profile.executable), str(self.profile.wrapper_path)]

    def _run(self, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        """Run one request and return a contract-validated response object.

        Every exit path is typed. A worker is never trusted to describe its own
        success: a nonzero exit is a failure regardless of the payload, and
        `ok` must be the literal boolean true.
        """
        request = json.dumps(payload).encode("utf-8")
        returncode, stdout, stderr, _fault = _run_child(self._argv(), request, timeout)
        detail = _diagnostic(stderr)
        text = stdout.decode("utf-8", "replace").strip()

        if not text:
            raise ProfileError(f"Profile worker returned no response (exit {returncode}){detail}")
        try:
            data = json.loads(text, object_pairs_hook=_no_duplicate_members)
        except _DuplicatedField as exc:
            raise ProfileError(f"Profile worker repeated a JSON member {exc.args[0]!r} (exit {returncode})") from exc
        except json.JSONDecodeError as exc:
            raise ProfileError(
                f"Profile worker returned non-JSON (exit {returncode}): {exc}{detail}"
            ) from exc
        if not isinstance(data, dict):
            raise ProfileError(
                f"Profile worker response must be a JSON object, got {type(data).__name__} "
                f"(exit {returncode}){detail}"
            )

        if returncode != 0:
            # Unconditional: a nonzero exit can never be reported as success,
            # even when the payload claims ok:true or carries plausible results.
            reason = data.get("error") or (detail.lstrip(": ") or f"exit {returncode}")
            raise ProfileError(f"Profile worker failed (exit {returncode}): {reason}")

        ok = data.get("ok")
        if ok is not True:
            reason = data.get("error") or (detail.lstrip(": ") or f"ok={ok!r}")
            raise ProfileError(f"Profile worker did not report success (exit {returncode}): {reason}")
        return data

    def _require_reader_identity(self, data: dict[str, Any], action: str) -> dict[str, Any]:
        reader = data.get("reader")
        if not isinstance(reader, dict):
            raise ProfileError(f"Profile worker {action} response is missing a reader object")
        version = reader.get("version") or data.get("pypdf_version")
        if not version:
            raise ProfileError(f"Profile worker {action} response is missing a reader version")
        if version != self.profile.version:
            raise ProfileError(
                f"Installed runtime identity mismatch: profile {self.profile.version}, worker {version}"
            )
        if not reader.get("id") and not reader.get("name"):
            raise ProfileError(f"Profile worker {action} response is missing a reader id or name")
        return reader

    @staticmethod
    def _require_pages(data: dict[str, Any], action: str) -> list[dict[str, Any]]:
        pages = data.get("pages")
        if not isinstance(pages, list):
            raise ProfileError(
                f"Profile worker {action} response is missing a pages list "
                f"(got {type(pages).__name__})"
            )
        for entry in pages:
            if not isinstance(entry, dict):
                raise ProfileError(f"Profile worker {action} page entry is not an object")
            if not isinstance(entry.get("page_index"), int):
                raise ProfileError(f"Profile worker {action} page entry is missing page_index")
            if entry.get("status") not in ("completed", "failed"):
                raise ProfileError(
                    f"Profile worker {action} page entry has unsupported status {entry.get('status')!r}"
                )
            if entry.get("status") == "completed" and not isinstance(entry.get("raw_text"), str):
                raise ProfileError(f"Profile worker {action} completed page is missing raw_text")
        return pages

    def describe(self) -> dict[str, Any]:
        data = self._run({"action": "describe"}, timeout=30.0)
        self._require_reader_identity(data, "describe")
        return data

    def extract(self, source_path: Path, pages: list[int] | None = None) -> dict[str, Any]:
        if not source_path.is_file():
            raise ProfileError(f"Source PDF does not exist: {source_path}")
        data = self._run(
            {
                "action": "extract",
                "source": str(source_path),
                "pdf_path": str(source_path),
                "pages": list(pages or []),
            },
            timeout=120.0,
        )
        self._require_reader_identity(data, "extract")
        self._require_pages(data, "extract")
        return data
