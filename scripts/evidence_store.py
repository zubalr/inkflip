"""Keep immutable validation records in local Git refs, outside source branches."""
from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import tempfile


def git(root: Path, *args: str, env: dict | None = None) -> bytes:
    result = subprocess.run(["git", *args], cwd=root, env=env, capture_output=True)
    if result.returncode:
        raise ValueError(result.stderr.decode().strip() or "Git evidence lookup failed")
    return result.stdout


def namespace(task: str) -> str:
    if not re.fullmatch(r"T[0-9]{2}", task):
        raise ValueError("invalid task namespace")
    return f"artifacts/tasks/{task}/"


def require_ancestry(root: Path, commit: str, ref: str, task: str) -> None:
    """Accept source ancestors or an evidence-only child of a source ancestor."""
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("evidence needs a full commit identity")
    try:
        git(root, "merge-base", "--is-ancestor", commit, ref)
        return
    except ValueError:
        pass
    parents = git(root, "show", "-s", "--format=%P", commit).decode().split()
    if len(parents) != 1:
        raise ValueError("evidence snapshot needs exactly one source parent")
    git(root, "merge-base", "--is-ancestor", parents[0], ref)
    changed = git(root, "diff", "--name-only", parents[0], commit).decode().splitlines()
    prefix = namespace(task)
    if not changed or any(not path.startswith(prefix) for path in changed):
        raise ValueError("evidence snapshot changes files outside its task namespace")


def current_blob(root: Path, ref: str, path: str) -> bytes:
    """Tracked evidence wins; local ignored evidence must be a regular file."""
    result = subprocess.run(["git", "cat-file", "-e", f"{ref}:{path}"], cwd=root,
                            capture_output=True)
    if result.returncode == 0:
        return git(root, "show", f"{ref}:{path}")
    git(root, "check-ignore", "--no-index", "--", path)
    local = root / path
    relative = local.relative_to(root)
    if any((root.joinpath(*relative.parts[:i])).is_symlink()
           for i in range(1, len(relative.parts) + 1)):
        raise ValueError(f"evidence must not traverse symlinks: {path}")
    if not local.is_file() or not local.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"missing local evidence: {path}")
    return local.read_bytes()


def snapshot(root: Path, task: str) -> str:
    """Archive one task without changing HEAD, the worktree or the real index."""
    prefix = namespace(task)
    folder = root / prefix
    if not folder.is_dir() or not any(folder.rglob("*")):
        raise ValueError("task evidence directory is empty or missing")
    if any(p.is_symlink() for p in [folder, folder.parent, folder.parent.parent,
                                    *folder.rglob("*")]):
        raise ValueError("evidence snapshot cannot contain symlinks")
    head = git(root, "rev-parse", "HEAD").decode().strip()
    with tempfile.TemporaryDirectory(prefix="inkflip-evidence-") as temp:
        env = {**os.environ, "GIT_INDEX_FILE": str(Path(temp) / "index")}
        git(root, "read-tree", head, env=env)
        git(root, "add", "--force", "--all", "--", prefix, env=env)
        tree = git(root, "write-tree", env=env).decode().strip()
        commit = git(root, "commit-tree", tree, "-p", head, "-m",
                     f"Record {task} validation", env=env).decode().strip()
    git(root, "update-ref", f"refs/local/validation-history/{task}/{commit}", commit)
    git(root, "update-ref", f"refs/local/validation/{task}", commit)
    return commit
