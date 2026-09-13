"""Inkflip CLI entrypoint for `python -m inkflip.cli`."""
from __future__ import annotations

import sys
from pathlib import Path

_NATIVE_ROOT = Path(__file__).resolve().parents[2]
if str(_NATIVE_ROOT) not in sys.path:
    sys.path.insert(0, str(_NATIVE_ROOT))

from inkflip.cli.main import main

if __name__ == "__main__":
    sys.exit(main())
