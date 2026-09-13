"""Data models and exceptions for baseline creation and comparison (T34)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class BaselineError(Exception):
    """Base exception for baseline creation or validation errors."""
    pass


class BaselineOverwriteError(BaselineError):
    """Raised when attempting to overwrite an existing baseline without authorization."""
    pass


class IncompatibleRunError(BaselineError):
    """Raised when comparing incompatible runs, documents, or reader profiles."""
    pass


class RuleRegressionError(BaselineError):
    """Raised when an explicit acceptance rule is violated."""
    pass


@dataclass
class ComparisonResult:
    """Outcome of comparing runs or baselines under acceptance rules."""

    status: str  # "unchanged", "changed", "improved", "regressed", "incompatible", "errored"
    exit_code: int
    changes: list[dict[str, Any]] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    left_reports_count: int = 0
    right_reports_count: int = 0
    coverage_lost: bool = False
