"""Baseline and comparison error types (T34)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class BaselineError(Exception):
    """Invalid baseline creation or comparison input."""


class BaselineOverwriteError(BaselineError):
    """Baseline path already exists; overwrite is prohibited."""


@dataclass
class ComparisonResult:
    status: str
    exit_code: int
    changes: list[dict[str, Any]] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    left_reports_count: int = 0
    right_reports_count: int = 0
    coverage_lost: bool = False
    incomparable: bool = False
    artifacts: list[str] = field(default_factory=list)
