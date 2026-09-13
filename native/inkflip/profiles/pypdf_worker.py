#!/usr/bin/env python3
"""Bundled stdlib+pypdf worker executed by isolated interpreters (T33).

Only the Python standard library and pypdf are imported. Extraction failures
stay terminal per page; they are never rewritten as empty completed checks.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    import pypdf
except ImportError as exc:
    sys.stderr.write(
        f"pypdf is not installed in this environment ({sys.executable}): {exc}\n"
    )
    sys.exit(3)


def describe_reader() -> dict:
    version_str = getattr(pypdf, "__version__", "unknown")
    return {
        "ok": True,
        "reader": {
            "id": "pypdf-native",
            "name": "pypdf",
            "version": version_str,
            "build": f"pypdf {version_str} (isolated interpreter: {sys.executable})",
            "adapter_version": "1.0.0",
            "method": "native_text",
            "environment": "native",
            "settings": {
                "normalization": "scalar-whitespace-v1",
                "language": None,
                "psm": None,
                "render_reader_id": None,
                "raster_dpi": None,
                "annotation_mode": "not_applicable",
            },
            "capabilities": [
                {
                    "name": "native_text",
                    "support": "supported",
                    "limits": [
                        "page-level text only; no per-word geometry is claimed or derived from visitor matrices",
                        "text from this reader is never combined with PDFium boxes by string matching",
                    ],
                },
                {
                    "name": "crop_metadata",
                    "support": "approximate",
                    "limits": [
                        "declared page dictionaries (media/crop box, /UserUnit, /Rotate) are parsed for other adapters' compensation; metadata is separate from extraction",
                    ],
                },
            ],
            "model_hashes": [],
            "limitations": [
                "version-isolated worker; executed in a separate virtual environment",
            ],
        },
        "interpreter": sys.executable,
        "python_version": sys.version,
        "pypdf_version": version_str,
    }


def extract_pdf(source_path: Path, pages: list[int]) -> dict:
    if not source_path.is_file():
        return {"ok": False, "error": f"Source file not found: {source_path}"}
    try:
        reader = pypdf.PdfReader(str(source_path))
    except Exception as exc:
        return {"ok": False, "error": f"Failed to open PDF: {exc}"}
    if reader.is_encrypted:
        return {"ok": False, "error": "Document is encrypted / password protected"}

    total_pages = len(reader.pages)
    selected = [p for p in pages if 0 <= p < total_pages] if pages else list(range(total_pages))
    page_results: list[dict] = []
    for page_index in selected:
        page = reader.pages[page_index]
        try:
            raw_text = page.extract_text() or ""
        except Exception as exc:
            page_results.append(
                {
                    "page_index": page_index,
                    "status": "failed",
                    "reason": f"extract_text failed: {type(exc).__name__}",
                    "raw_text": None,
                }
            )
            continue
        page_results.append(
            {
                "page_index": page_index,
                "status": "completed",
                "reason": None,
                "raw_text": raw_text,
            }
        )
    desc = describe_reader()
    return {
        "ok": True,
        "reader": desc["reader"],
        "pages": page_results,
        "interpreter": desc["interpreter"],
        "python_version": desc["python_version"],
        "pypdf_version": desc["pypdf_version"],
    }


def _read_request() -> dict:
    raw = sys.stdin.read()
    if not raw.strip():
        return {"action": "help"}
    return json.loads(raw)


def main() -> int:
    try:
        request = _read_request()
    except json.JSONDecodeError as exc:
        sys.stdout.write(json.dumps({"ok": False, "error": f"malformed JSON: {exc}"}) + "\n")
        return 2

    action = request.get("action")
    if action == "describe":
        sys.stdout.write(json.dumps(describe_reader()) + "\n")
        return 0
    if action == "extract":
        source = request.get("source")
        if not source:
            sys.stdout.write(json.dumps({"ok": False, "error": "source is required"}) + "\n")
            return 2
        pages = request.get("pages") or []
        if not isinstance(pages, list) or not all(isinstance(p, int) for p in pages):
            sys.stdout.write(json.dumps({"ok": False, "error": "pages must be integer indices"}) + "\n")
            return 2
        result = extract_pdf(Path(source), pages)
        sys.stdout.write(json.dumps(result) + "\n")
        return 0 if result.get("ok") else 1
    sys.stdout.write(json.dumps({"ok": False, "error": f"unknown action: {action}"}) + "\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
