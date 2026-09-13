"""Inkflip baseline creation and regression comparison package (T34)."""
from __future__ import annotations

from inkflip.baselines.engine import (
    EXIT_INVALID_ARGS,
    EXIT_MISSING_INPUT,
    EXIT_OK,
    EXIT_REGRESSION,
    compare,
    create_baseline,
)
from inkflip.baselines.models import (
    BaselineError,
    BaselineOverwriteError,
    ComparisonResult,
    IncompatibleRunError,
    RuleRegressionError,
)

__all__ = [
    "BaselineError",
    "BaselineOverwriteError",
    "ComparisonResult",
    "EXIT_INVALID_ARGS",
    "EXIT_MISSING_INPUT",
    "EXIT_OK",
    "EXIT_REGRESSION",
    "IncompatibleRunError",
    "RuleRegressionError",
    "compare",
    "create_baseline",
]
