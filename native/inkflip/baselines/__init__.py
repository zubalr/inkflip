"""Stored-run comparison, rules and immutable baselines (T34)."""

from .engine import compare, create_baseline, write_pair_comparison
from .models import BaselineError, BaselineOverwriteError, ComparisonResult

__all__ = [
    "BaselineError",
    "BaselineOverwriteError",
    "ComparisonResult",
    "compare",
    "create_baseline",
    "write_pair_comparison",
]
