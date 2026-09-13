"""Shared Node comparison bridge (T31).

The native comparison path invokes the shared TypeScript comparison
package as an installed, fixed executable protocol instead of
reimplementing alignment in Python
(``planning/architecture/TARGET_ARCHITECTURE.md`` — "browser/native
finding semantics genuinely shared", ADR009). This module is the Python
half of that protocol:

* **Fixed argv** — ``[resolved node, <repo>/packages/compare/node/
  bridge.mjs]`` with ``shell=False``. The entrypoint path is resolved
  from this module's location, never from request or report data; the
  request travels on stdin as one bounded JSON message. No request field
  can become an argument, environment override, plugin or profile
  selection — there is no argv-construction path for data to reach.
* **Bounded local JSON messages** — the request is capped before spawn;
  stdout and stderr are drained through a ``selectors`` pump that counts
  every byte and kills the child's process group the moment either
  stream exceeds its cap (honest ``output_limit``, never truncation).
  A wall deadline bounds the whole exchange and a private scratch dir is
  the child's only ``TMPDIR``.
* **Missing Node is a capability error** — absent/non-executable node,
  a missing entrypoint or an exec ``ENOENT`` raises
  :class:`BridgeCapabilityError`. The bridge has no Python fallback
  algorithm: a comparison that cannot run on the shared engine is a
  failure, not a divergent approximation.
* **Comparator version rides every response** — the entrypoint stamps
  normalization/alignment/bridge/protocol versions plus the Node runtime
  identity on every reply; :meth:`BridgeResult.manifest_entry` renders
  that identity for run manifests and comparison records (I13).

Failure taxonomy (:meth:`CompareBridge` calls raise
:class:`BridgeError` with a stable ``reason``): ``capability``,
``spawn_error``, ``timeout``, ``output_limit``, ``request_too_large``,
``exit``, ``crash``, ``protocol_error`` and ``remote_<code>`` when the
shared engine rejected a well-formed request (``remote_type``,
``remote_normalization``, ``remote_field`` …). Reason/detail strings
follow the supervision rule — safe templates only, never child stream
text; a bounded stderr tail is exposed separately on the exception as
``stderr_tail`` for the caller to log or drop.

POSIX only, matching the parent supervision model (process-group kill,
``start_new_session``). A container/supervised corpus remains the
hardened route for untrusted corpora; this bridge exchanges data with
its own fixed entrypoint only.
"""
from __future__ import annotations

import json
import os
import re
import selectors
import shutil
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

BRIDGE_PROTOCOL = "inkflip-compare-bridge"
BRIDGE_PROTOCOL_VERSION = 1
BRIDGE_VERSION = "1.0.0"  # this Python adapter's version

REPO_ROOT = Path(__file__).resolve().parents[2]
_PACKAGED_ENTRYPOINT = (
    Path(__file__).resolve().parent
    / "resources"
    / "packages"
    / "compare"
    / "node"
    / "bridge.mjs"
)
_CHECKOUT_ENTRYPOINT = REPO_ROOT / "packages" / "compare" / "node" / "bridge.mjs"
ENTRYPOINT = _PACKAGED_ENTRYPOINT if _PACKAGED_ENTRYPOINT.is_file() else _CHECKOUT_ENTRYPOINT

_CHUNK = 65536
_STDERR_SAMPLE_BYTES = 8192
_KILL_GRACE_SECONDS = 5.0
_REMOTE_CODE_RE = re.compile(r"[A-Z][A-Z0-9_]{0,63}")


class BridgeError(Exception):
    """Typed bridge failure carrying a stable machine-readable reason.

    ``stderr_tail`` is a bounded, untrusted sample of the child's stderr
    for caller-side diagnostics; it is deliberately excluded from
    ``detail`` so reasons stay safe templates.
    """

    def __init__(self, reason: str, detail: str, *, stderr_tail: bytes = b""):
        self.reason = reason
        self.detail = detail
        self.stderr_tail = stderr_tail
        super().__init__(f"{reason}: {detail}")


class BridgeCapabilityError(BridgeError):
    """The installed Node runtime or comparison entrypoint is unavailable.

    Raised for a missing/non-executable node, an absent entrypoint and a
    spawn-time ``ENOENT``. There is no fallback comparison algorithm —
    this is always a typed failure, never a degraded result.
    """


@dataclass(frozen=True)
class BridgeLimits:
    """Runtime bounds for one request/response exchange."""

    wall_seconds: float = 60.0
    max_request_bytes: int = 16 << 20  # stdin JSON message cap
    max_response_bytes: int = 16 << 20  # stdout JSON message cap
    max_stderr_bytes: int = 1 << 20  # stderr flood cap


@dataclass(frozen=True)
class BridgeResult:
    """One successful exchange: the op payload plus comparator identity.

    ``comparator`` is the shared engine's version block (package, bridge
    and protocol versions, frozen algorithm ids, Node runtime); record
    it wherever run/comparison manifests keep source and adapter
    identity (I13).
    """

    comparator: dict
    result: dict

    @property
    def results(self) -> list:
        """The `results` list of normalize/align payloads."""
        return self.result.get("results", [])

    def manifest_entry(self) -> dict:
        """Manifest-ready comparator identity block (I13)."""
        c = self.comparator
        return {
            "name": c.get("package", "@inkflip/compare"),
            "role": "comparator",
            "bridge_version": c.get("bridge_version"),
            "protocol": c.get("protocol"),
            "protocol_version": c.get("protocol_version"),
            "normalization": c.get("normalization"),
            "alignment": c.get("alignment"),
            "score_semantics": c.get("score_semantics"),
            "node": c.get("node"),
            "platform": c.get("platform"),
        }


def _resolve_node(node: str | os.PathLike | None) -> str:
    """Resolve the Node runtime: explicit install path, image layout, or PATH."""
    if node is None:
        env = os.environ.get("INKFLIP_NODE")
        if env:
            node = env
        else:
            for candidate in (
                Path("/app/node/bin/node"),
                Path("/opt/node/bin/node"),
            ):
                if candidate.is_file() and os.access(candidate, os.X_OK):
                    return str(candidate)
            found = shutil.which("node")
            if found is None:
                raise BridgeCapabilityError(
                    "capability",
                    "node runtime not found on PATH; install Node to enable "
                    "native comparisons (the shared comparator has no "
                    "Python fallback)",
                )
            return found
    path = str(node)
    if not os.path.isfile(path):
        raise BridgeCapabilityError(
            "capability", "configured node runtime path does not exist"
        )
    if not os.access(path, os.X_OK):
        raise BridgeCapabilityError(
            "capability", "configured node runtime path is not executable"
        )
    return path


def _resolve_entrypoint(entrypoint: str | os.PathLike | None) -> str:
    """The fixed installed entrypoint; an override exists for tests and
    explicit installation layouts, never for request/report data."""
    if entrypoint is not None:
        path = Path(entrypoint)
    else:
        env = os.environ.get("INKFLIP_COMPARE_BRIDGE")
        path = Path(env) if env else ENTRYPOINT
    if not path.is_file():
        raise BridgeCapabilityError(
            "capability",
            "shared comparison entrypoint is not installed at "
            "packages/compare/node/bridge.mjs (or the packaged "
            "inkflip/resources/packages/compare/node/bridge.mjs)",
        )
    return str(path)


class CompareBridge:
    """One fixed-argv channel to the shared Node comparison entrypoint.

    ``node`` is an explicit runtime path or None for ``shutil.which``.
    ``limits`` bounds every exchange. ``spawn`` is the subprocess
    factory (``subprocess.Popen``); tests inject it for fault-injection
    children — production callers never do.
    """

    def __init__(
        self,
        node: str | os.PathLike | None = None,
        *,
        entrypoint: str | os.PathLike | None = None,
        limits: BridgeLimits | None = None,
        spawn=None,
    ):
        if os.name != "posix":
            raise BridgeCapabilityError(
                "capability",
                "the comparison bridge requires POSIX process groups",
            )
        self._limits = limits or BridgeLimits()
        for name, value in (
            ("wall_seconds", self._limits.wall_seconds),
            ("max_request_bytes", self._limits.max_request_bytes),
            ("max_response_bytes", self._limits.max_response_bytes),
            ("max_stderr_bytes", self._limits.max_stderr_bytes),
        ):
            if not isinstance(value, (int, float)) or value <= 0:
                raise BridgeError(
                    "configuration", f"bridge limit {name} must be positive"
                )
        self._spawn = spawn or subprocess.Popen
        self._node = _resolve_node(node)
        self._entrypoint = _resolve_entrypoint(entrypoint)

    # -- public operations ---------------------------------------------------

    def describe(self) -> BridgeResult:
        """Comparator version identity without running a comparison."""
        return self._exchange("describe", {})

    def normalize(self, raws) -> BridgeResult:
        """scalar-whitespace-v1 normalized views for a list of raw strings.

        Result payload: ``{"results": [{"text", "map"}, ...]}`` — the same
        contract fields a report's ``normalized_text``/``normalization_map``
        carry, computed by the shared TypeScript code only.
        """
        return self._exchange("normalize", {"raws": list(raws)})

    def align(self, pages) -> BridgeResult:
        """region-match-v1 alignment for a list of page descriptors.

        Each page is ``{"left": [...], "right": [...], "page_index"?,
        "region"?}``; occurrences carry ``id``, ``page_index``, ``ordinal``,
        ``geometry`` and ``raw`` (normalized by the shared TS code) or a
        parity-checked ``normalized_text``. Result payload:
        ``{"results": [AlignmentResult, ...]}``.
        """
        return self._exchange("align", {"pages": list(pages)})

    # -- transport -------------------------------------------------------------

    def _argv(self) -> list:
        """The fixed argv: runtime + entrypoint, nothing else."""
        return [self._node, self._entrypoint]

    def _child_env(self, scratch: Path) -> dict:
        """Minimal environment: locale + private TMPDIR. NODE_OPTIONS is
        deliberately absent — no ambient variable may inject flags into
        the fixed runtime invocation."""
        return {
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "TMPDIR": str(scratch),
        }

    def _exchange(self, op: str, fields: dict) -> BridgeResult:
        body = {
            "protocol": BRIDGE_PROTOCOL,
            "version": BRIDGE_PROTOCOL_VERSION,
            "op": op,
            **fields,
        }
        try:
            request = json.dumps(
                body,
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError, UnicodeError) as error:
            raise BridgeError(
                "type",
                f"request is not JSON-serializable ({type(error).__name__})",
            ) from error
        if len(request) > self._limits.max_request_bytes:
            raise BridgeError(
                "request_too_large",
                f"request is {len(request)} bytes; the bounded-message cap "
                f"is {self._limits.max_request_bytes}",
            )
        scratch = Path(tempfile.mkdtemp(prefix="inkflip-compare-"))
        try:
            try:
                proc = self._spawn(
                    self._argv(),
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=self._child_env(scratch),
                    cwd=str(scratch),
                    shell=False,
                    start_new_session=True,
                    close_fds=True,
                )
            except FileNotFoundError as error:
                raise BridgeCapabilityError(
                    "capability",
                    "node runtime could not be executed (ENOENT)",
                ) from error
            except PermissionError as error:
                raise BridgeCapabilityError(
                    "capability",
                    "node runtime could not be executed (permission denied)",
                ) from error
            except OSError as error:
                raise BridgeError(
                    "spawn_error",
                    f"could not spawn the comparison runtime "
                    f"(errno {error.errno})",
                ) from error
            stdout, stderr_tail = self._pump(proc, request)
            # _pump always reaps with a bounded wait before returning.
            rc = proc.returncode
            if rc is not None and rc < 0:
                raise BridgeError(
                    "crash",
                    f"comparator died on {_sig_name(-rc)}",
                    stderr_tail=stderr_tail,
                )
            if rc:
                raise BridgeError(
                    "exit",
                    f"comparator exited {rc} without a response",
                    stderr_tail=stderr_tail,
                )
            return self._decode(stdout, stderr_tail)
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

    def _pump(self, proc, request: bytes) -> tuple[bytes, bytes]:
        """Bounded request/response exchange.

        Drains stdout/stderr through a selector loop that counts every
        byte; either stream over its cap — or the wall deadline — kills
        the child's whole process group and raises a typed error. The
        retained stdout buffer can therefore never exceed
        ``max_response_bytes + one chunk``.
        """
        limits = self._limits
        deadline = time.monotonic() + limits.wall_seconds
        selector = selectors.DefaultSelector()
        pending = memoryview(request)
        offset = 0
        out = bytearray()
        err = bytearray()
        counts = {"stdout": 0, "stderr": 0}
        try:
            os.set_blocking(proc.stdout.fileno(), False)
            os.set_blocking(proc.stderr.fileno(), False)
            selector.register(
                proc.stdout.fileno(), selectors.EVENT_READ, "stdout"
            )
            selector.register(
                proc.stderr.fileno(), selectors.EVENT_READ, "stderr"
            )
            os.set_blocking(proc.stdin.fileno(), False)
            selector.register(
                proc.stdin.fileno(), selectors.EVENT_WRITE, "stdin"
            )
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self._kill_group(proc)
                    raise BridgeError(
                        "timeout",
                        f"comparator exceeded the "
                        f"{limits.wall_seconds}s wall budget",
                        stderr_tail=bytes(err),
                    )
                for key, _mask in selector.select(min(remaining, 0.25)):
                    if key.data == "stdin":
                        try:
                            written = os.write(
                                key.fd, pending[offset : offset + _CHUNK]
                            )
                        except OSError:
                            written = -1
                        if written < 0:
                            selector.unregister(key.fd)
                            _close_quietly(proc.stdin)
                        else:
                            offset += written
                            if offset >= len(pending):
                                selector.unregister(key.fd)
                                _close_quietly(proc.stdin)
                    else:
                        try:
                            chunk = os.read(key.fd, _CHUNK)
                        except OSError:
                            chunk = b""
                        if not chunk:
                            selector.unregister(key.fd)
                            continue
                        counts[key.data] += len(chunk)
                        if key.data == "stdout":
                            if counts["stdout"] <= limits.max_response_bytes:
                                out += chunk
                            if counts["stdout"] > limits.max_response_bytes:
                                self._kill_group(proc)
                                raise BridgeError(
                                    "output_limit",
                                    f"comparator stdout exceeded the "
                                    f"{limits.max_response_bytes}-byte cap",
                                    stderr_tail=bytes(err),
                                )
                        else:
                            if len(err) < _STDERR_SAMPLE_BYTES:
                                err += chunk[: _STDERR_SAMPLE_BYTES - len(err)]
                            if counts["stderr"] > limits.max_stderr_bytes:
                                self._kill_group(proc)
                                raise BridgeError(
                                    "output_limit",
                                    f"comparator stderr exceeded the "
                                    f"{limits.max_stderr_bytes}-byte cap",
                                    stderr_tail=bytes(err),
                                )
            try:
                proc.wait(
                    timeout=max(0.001, deadline - time.monotonic())
                )
            except subprocess.TimeoutExpired:
                self._kill_group(proc)
                raise BridgeError(
                    "timeout",
                    f"comparator exceeded the {limits.wall_seconds}s "
                    f"wall budget",
                    stderr_tail=bytes(err),
                )
            return bytes(out), bytes(err)
        finally:
            selector.close()
            for stream in (proc.stdin, proc.stdout, proc.stderr):
                _close_quietly(stream)

    def _kill_group(self, proc) -> None:
        """SIGKILL the child's whole process group, then reap the leader."""
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                proc.kill()
            except OSError:
                pass
        try:
            proc.wait(timeout=_KILL_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            pass

    def _decode(self, stdout: bytes, stderr_tail: bytes) -> BridgeResult:
        """Validate the bounded response envelope and surface it.

        The contract validator (with its pinned jsonschema dependency) is
        imported lazily so importing this module — e.g. to probe Node
        capability — never requires third-party packages.
        """
        from inkflip.contracts import ContractError, loads_strict

        try:
            message = loads_strict(stdout)
        except ContractError as error:
            raise BridgeError(
                "protocol_error",
                f"comparator response is not bounded JSON ({error.code})",
                stderr_tail=stderr_tail,
            ) from error
        if (
            not isinstance(message, dict)
            or message.get("protocol") != BRIDGE_PROTOCOL
            or message.get("version") != BRIDGE_PROTOCOL_VERSION
            or "ok" not in message
        ):
            raise BridgeError(
                "protocol_error",
                "comparator response envelope is invalid",
                stderr_tail=stderr_tail,
            )
        if message["ok"] is True:
            result = message.get("result")
            comparator = message.get("comparator")
            if not isinstance(result, dict) or not isinstance(comparator, dict):
                raise BridgeError(
                    "protocol_error",
                    "comparator success response is malformed",
                    stderr_tail=stderr_tail,
                )
            return BridgeResult(comparator=comparator, result=result)
        if message["ok"] is False:
            error = message.get("error")
            if (
                isinstance(error, dict)
                and isinstance(error.get("code"), str)
                and isinstance(error.get("message"), str)
                and _REMOTE_CODE_RE.fullmatch(error["code"])
            ):
                raise BridgeError(
                    f"remote_{error['code'].lower()}",
                    error["message"][:200],
                    stderr_tail=stderr_tail,
                )
            raise BridgeError(
                "remote_error",
                "comparator rejected the request",
                stderr_tail=stderr_tail,
            )
        raise BridgeError(
            "protocol_error",
            "comparator response has no ok status",
            stderr_tail=stderr_tail,
        )


def _sig_name(signo: int) -> str:
    try:
        return signal.Signals(signo).name
    except (ValueError, KeyError):
        return f"SIG{signo}"


def _close_quietly(stream) -> None:
    try:
        stream.close()
    except OSError:
        pass


__all__ = [
    "BRIDGE_PROTOCOL",
    "BRIDGE_PROTOCOL_VERSION",
    "BRIDGE_VERSION",
    "ENTRYPOINT",
    "REPO_ROOT",
    "BridgeCapabilityError",
    "BridgeError",
    "BridgeLimits",
    "BridgeResult",
    "CompareBridge",
]
