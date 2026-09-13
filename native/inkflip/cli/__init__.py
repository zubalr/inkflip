"""Inkflip native CLI package."""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure native directory is in sys.path when imported as inkflip.cli
_NATIVE_ROOT = Path(__file__).resolve().parents[2]
if str(_NATIVE_ROOT) not in sys.path:
    sys.path.insert(0, str(_NATIVE_ROOT))

from inkflip.cli.main import main

__all__ = ["main"]
