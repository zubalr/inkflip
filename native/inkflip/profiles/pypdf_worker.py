#!/usr/bin/env python3
"""Small bundled stdlib+pypdf worker wrapper executed by isolated interpreters (T33).

Only imports Python standard library and pypdf. Does not require the full
application's pinned dependencies.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

try:
    import pypdf
except ImportError as e:
    sys.stderr.write(f"pypdf is not installed in this environment ({sys.executable}): {e}\n")
    sys.exit(3)


def describe_reader() -> dict:
    version_str = getattr(pypdf, "__version__", "unknown")
    return {
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
                "version-isolated worker; executed in separate virtual environment",
            ],
        },
        "interpreter": sys.executable,
        "python_version": sys.version,
        "pypdf_version": version_str,
    }


def extract_pdf(source_path: Path, pages: list[int]) -> dict:
    if not source_path.is_file():
        return {
            "ok": False,
            "error": f"Source file not found: {source_path}"
        }

    try:
        reader = pypdf.PdfReader(str(source_path))
    except Exception as e:
        return {
            "ok": False,
            "error": f"Failed to open PDF: {e}"
        }

    if reader.is_encrypted:
        return {
            "ok": False,
            "error": "Document is encrypted / password protected"
        }

    total_pages = len(reader.pages)
    selected_pages = [p for p in pages if 0 <= p < total_pages] if pages else list(range(total_pages))

    occurrences = []
    checks = []
    transforms = []

    for p_idx in selected_pages:
        page = reader.pages[p_idx]
        try:
            raw_text = page.extract_text() or ""
        except Exception as e:
            raw_text = ""

        occ_ids = []
        if raw_text:
            occ_id = f"occ_pypdf_p{p_idx}_0"
            occ_ids.append(occ_id)
            occurrences.append({
                "id": occ_id,
                "page_index": p_idx,
                "ordinal": 0,
                "raw_text": raw_text,
                "normalized_text": raw_text,
                "geometry": {
                    "precision": "page_only",
                    "space": "canonical_page",
                    "polygon": None,
                    "transform_ids": [],
                    "basis": "pypdf extract_text page-level output; no per-word geometry claimed",
                },
                "reader_id": "pypdf-native",
                "engine_score": None,
                "source_asset_id": None,
                "raw_source_locator": f"pypdf:page[{p_idx}]:extract_text",
                "limitations": ["page-only extraction; anchors unavailable by design"],
            })

        check_id = f"chk_pypdf_p{p_idx}"
        checks.append({
            "id": check_id,
            "status": "completed",
            "reason": None,
            "produced_occurrence_count": len(occ_ids),
            "retained_occurrence_ids": occ_ids,
        })

    desc = describe_reader()
    return {
        "ok": True,
        "reader": desc["reader"],
        "occurrences": occurrences,
        "checks": checks,
        "transforms": transforms,
        "interpreter": desc["interpreter"],
        "version": desc["pypdf_version"]
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Inkflip isolated pypdf worker")
    parser.add_argument("--describe", action="store_true", help="Emit reader manifest JSON")
    parser.add_argument("--extract", action="store_true", help="Extract text from PDF")
    parser.add_argument("--source", help="Path to source PDF")
    parser.add_argument("--pages", help="Comma-separated 0-based page indices (e.g. 0,1)")
    parser.add_argument("--out", help="Destination JSON path (defaults to stdout)")

    args = parser.parse_args()

    if args.describe:
        desc = describe_reader()
        out_json = json.dumps(desc, indent=2)
        if args.out:
            Path(args.out).write_text(out_json, encoding="utf-8")
        else:
            sys.stdout.write(out_json + "\n")
        return 0

    if args.extract:
        if not args.source:
            sys.stderr.write("Error: --source is required for --extract\n")
            return 2
        pages = []
        if args.pages:
            try:
                pages = [int(p.strip()) for p in args.pages.split(",") if p.strip()]
            except ValueError:
                sys.stderr.write("Error: invalid --pages format\n")
                return 2

        result = extract_pdf(Path(args.source), pages)
        out_json = json.dumps(result, indent=2)
        if args.out:
            Path(args.out).write_text(out_json, encoding="utf-8")
        else:
            sys.stdout.write(out_json + "\n")
        return 0 if result.get("ok", True) else 1

    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
