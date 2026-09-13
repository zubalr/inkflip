#!/usr/bin/env python3
"""Worker pre-push accident guard; invoke from a hook in the current worktree.

The canonical script may live outside that worktree. No Beads access or network;
this is not a security boundary against another process owned by the same user.
"""
from __future__ import annotations

import re
import subprocess
import sys

import native_followups as f

REMOTE_URL = "/home/wertyp/.local/share/homebase-factory/git/inkflip.git"
MAX_INPUT = 8192
ZERO_SHA = "0" * 40


def git(*args: str) -> str:
    result = subprocess.run(["git", *args], text=True, capture_output=True, timeout=10)
    if result.returncode:
        raise ValueError(result.stderr.strip() or "Local Git check failed")
    return result.stdout.strip()


def validate_update(line: str, branch: str, task: str) -> None:
    fields = line.split()
    if len(fields) != 4:
        raise ValueError("Expected one Git pre-push update with four fields")
    local_ref, local_sha, remote_ref, remote_sha = fields
    if local_ref not in {"HEAD", branch}:
        raise ValueError("Push HEAD or the current full task branch only")
    if remote_ref != f"refs/heads/hb/inkflip/{task}":
        raise ValueError("Push only the matching hb/inkflip task branch")
    if not all(re.fullmatch(r"[0-9a-f]{40}", sha) for sha in (local_sha, remote_sha)):
        raise ValueError("Expected full SHA-1 object IDs")
    if local_sha == ZERO_SHA or local_sha != git("rev-parse", "HEAD"):
        raise ValueError("Deletion or a candidate other than HEAD is forbidden")
    if remote_sha != ZERO_SHA:
        # Missing objects and non-ancestors both fail closed; never fetch here.
        try:
            git("merge-base", "--is-ancestor", remote_sha, local_sha)
        except ValueError as error:
            raise ValueError("Non-fast-forward update or unavailable remote commit") from error


def guard(remote: str, url: str, updates: str) -> None:
    if (remote, url) != ("handoff", REMOTE_URL):
        raise ValueError("Only handoff to the configured Homebase local relay is allowed")
    if len(updates) > MAX_INPUT:
        raise ValueError("Pre-push input exceeds the bounded update size")
    lines = [line for line in updates.splitlines() if line.strip()]
    branch = git("symbolic-ref", "--quiet", "HEAD")
    match = re.fullmatch(r"refs/heads/work/zcode/(t(?:0[1-9]|[1-4][0-9]|5[0-5]))", branch)
    if match is not None:
        task = match[1]
    else:
        prefix = "refs/heads/work/zcode/"
        if not branch.startswith(prefix):
            raise ValueError("Current branch must be a work/zcode task branch")
        task = branch.removeprefix(prefix)
        # The relay verifies the active coordinator grant before collection.
        # This offline hook only checks the exact branch/checkpoint identity.
        f.validate_id(task)
    if len(lines) > 1:
        raise ValueError("At most one nonempty update is allowed")
    # Git supplies no updates for an already-published SHA; identity checks still apply.
    if lines:
        validate_update(lines[0], branch, task)


def main() -> int:
    try:
        if len(sys.argv) != 3:
            raise ValueError("Usage: homebase_pre_push.py REMOTE URL (Git updates on stdin)")
        guard(sys.argv[1], sys.argv[2], sys.stdin.read(MAX_INPUT + 1))
    except (ValueError, OSError, subprocess.TimeoutExpired) as error:
        print(f"Homebase push blocked: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
