"""Include the shared comparison JS/TS tree in the Inkflip wheel.

The installed ``inkflip`` console script must resolve the T31 Node
comparison entrypoint without a git checkout. Paths stay relative so
``packages/compare/node/bridge.mjs`` imports keep working.
"""
from __future__ import annotations

from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

INCLUDE_SUFFIXES = {".mjs", ".ts", ".js", ".json", ".md"}
SKIP_DIR_NAMES = {".git", "node_modules", "dist", "__pycache__", ".venv"}


class CustomBuildHook(BuildHookInterface):
    PLUGIN_NAME = "custom"

    def initialize(self, version, build_data):  # type: ignore[no-untyped-def]
        native_root = Path(self.root)
        repo = native_root.parent
        mapping = (
            (repo / "packages" / "compare", "inkflip/resources/packages/compare"),
            (repo / "packages" / "contracts" / "src", "inkflip/resources/packages/contracts/src"),
            (repo / "packages" / "geometry" / "src", "inkflip/resources/packages/geometry/src"),
        )
        force = build_data.setdefault("force_include", {})
        for source, dest_root in mapping:
            if not source.is_dir():
                raise FileNotFoundError(f"packaging resource missing: {source}")
            for path in source.rglob("*"):
                if not path.is_file() or path.suffix not in INCLUDE_SUFFIXES:
                    continue
                if any(part in SKIP_DIR_NAMES for part in path.parts):
                    continue
                rel = path.relative_to(source).as_posix()
                force[str(path)] = f"{dest_root}/{rel}"
