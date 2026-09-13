"""Source/output identity: refuse aliases including symlinks and hard links."""
from __future__ import annotations

import os
from pathlib import Path


def resolved_path(path: Path) -> Path:
    return Path(os.path.abspath(os.path.expanduser(str(path))))


def same_inode(left: Path, right: Path) -> bool:
    try:
        left_stat = os.lstat(left)
        right_stat = os.lstat(right)
    except OSError:
        return False
    if left_stat.st_ino == 0 or right_stat.st_ino == 0:
        return False
    return left_stat.st_ino == right_stat.st_ino and left_stat.st_dev == right_stat.st_dev


def paths_alias(left: Path, right: Path) -> bool:
    """True when two paths name the same bytes (resolve, symlink, or hard link)."""
    a = Path(left)
    b = Path(right)
    try:
        if a.resolve() == b.resolve():
            return True
    except OSError:
        pass
    if same_inode(a, b):
        return True
    try:
        if a.exists() and b.exists() and a.stat().st_ino == b.stat().st_ino and a.stat().st_dev == b.stat().st_dev:
            return True
    except OSError:
        pass
    return False


def refuse_output_alias(source: Path, destination: Path) -> None:
    if paths_alias(source, destination):
        raise ValueError(
            "Output path aliases the source (including symlink or hard link) "
            "and is refused regardless of overwrite flags"
        )


def directories_overlap(left: Path, right: Path) -> bool:
    try:
        a = left.resolve()
        b = right.resolve()
    except OSError:
        return False
    try:
        a.relative_to(b)
        return True
    except ValueError:
        pass
    try:
        b.relative_to(a)
        return True
    except ValueError:
        return False
