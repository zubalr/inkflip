#!/usr/bin/env python3
"""Prepare browser demonstration examples and manifests (T17/T21).

Derives every card's manifest from the REAL captured reports produced by
tests/gallery/capture.mjs (sealed live runs of the shipped pipeline) plus
the actual source/control PDF bytes. Nothing here fabricates a reader
result: reader identities, findings, produced counts and timing are read
verbatim out of each card's committed `report.json`.

Usage:
  python3 scripts/prepare_examples.py          # (re)generate manifests + stage PDFs
  python3 scripts/prepare_examples.py --check  # verify hashes/bytes and report binding

Layout written per card under apps/web/public/examples/<card>/:
  manifest.json   — source/control/variant files with real sha256+byte_length
  report.json …   — captured sealed reports (input; never rewritten here)
  <source>.pdf    — staged copies of the fixture PDFs (byte-verbatim)
The gallery index is emitted at apps/web/public/examples/index.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES_DIR = ROOT / "fixtures"
EXAMPLES_DIR = ROOT / "apps" / "web" / "public" / "examples"

RIGHTS = (
    "Original synthetic sample of the Inkflip project, approved under the "
    "project's MIT terms; no embedded font program; no third-party material; "
    "no private or challenge-answer data."
)

TIMING_METHOD = (
    "browser_measured",
    "Actual measured browser execution time using PDF.js and Tesseract.js "
    "(no decorative animation)",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Card specifications. `files` maps manifest keys to (fixture path, report file,
# human role). The first entry is the presented source; siblings are clean
# controls or counterexample companions actually executed by capture.mjs.
# ---------------------------------------------------------------------------
CARDS: list[dict] = [
    {
        "id": "amount",
        "family": "mapping-amount",
        "fixture_id": "F01",
        "card_title": "The amount that reads differently",
        "mechanism": (
            "Font ToUnicode maps the displayed 1 to 1,0; visual $100 becomes "
            "extracted $1,000"
        ),
        "files": [
            ("source", "public/mapping-amount.pdf", "report.json", "Source document"),
            ("control", "public/mapping-control.pdf", "report.control.json", "Clean control (renders identically)"),
            ("unicode_native", "development/native-unicode-native.pdf", "report.native-unicode-native.json", "Identity-H encoded companion"),
            ("unicode_control", "development/native-unicode-control.pdf", "report.native-unicode-control.json", "Identity-H clean control"),
        ],
    },
    {
        "id": "covered",
        "family": "covered-text",
        "fixture_id": "F02",
        "card_title": "The amount hidden under white paint",
        "mechanism": (
            "A painted white rectangle covers the printed amount; the render "
            "shows nothing while the text layer still carries it"
        ),
        "files": [
            ("source", "public/covered-amount.pdf", "report.json", "Source document"),
            ("control", "public/covered-control.pdf", "report.control.json", "Clean control"),
            ("contrast_white", "development/white-contrast-white.pdf", "report.white-contrast-white.json", "White-on-white detail companion"),
            ("contrast_control", "development/white-contrast-control.pdf", "report.white-contrast-control.json", "Contrast clean control"),
        ],
    },
    {
        "id": "scan",
        "family": "searchable-scan",
        "fixture_id": "F03",
        "card_title": "A normal scan — and its invisible-layer siblings",
        "mechanism": (
            "A searchable scan carries an invisible text layer over the raster; "
            "raster-only and shifted siblings show when readings still agree"
        ),
        "files": [
            ("source", "development/scan-correct.pdf", "report.json", "Searchable scan (correct layer)"),
            ("raster_only", "development/scan-raster-only.pdf", "report.scan-raster-only.json", "Raster-only sibling"),
            ("shifted", "development/scan-shifted.pdf", "report.scan-shifted.json", "Shifted-layer sibling"),
        ],
    },
    {
        "id": "geometry",
        "family": "origins-rotation",
        "fixture_id": "F07",
        "card_title": "The same ink at four rotations",
        "mechanism": (
            "Identical page content under 0/90/180/270 rotation; readers must "
            "reconcile geometry through the recorded transforms"
        ),
        "files": [
            ("source", "public/geometry-90.pdf", "report.json", "Source document (90°)"),
            ("rot0", "public/geometry-0.pdf", "report.geometry-0.json", "0° sibling"),
            ("rot180", "public/geometry-180.pdf", "report.geometry-180.json", "180° sibling"),
            ("rot270", "public/geometry-270.pdf", "report.geometry-270.json", "270° sibling"),
            ("control", "public/geometry-control.pdf", "report.control.json", "Clean control"),
        ],
    },
    {
        "id": "reading-order",
        "family": "reading-order",
        "fixture_id": "F12",
        "card_title": "The same readings in a different order",
        "mechanism": (
            "Two columns emitted right-then-left; the same text arrives in a "
            "different stream order without changing what was read"
        ),
        "files": [
            ("source", "public/reading-order-reordered.pdf", "report.json", "Reordered stream"),
            ("control", "public/reading-order-control.pdf", "report.control.json", "Natural-order control"),
        ],
    },
    {
        "id": "duplicates",
        "family": "duplicates",
        "fixture_id": "F11",
        "card_title": "The same $100, four times",
        "mechanism": (
            "Four identical amounts at distinct positions stay individually "
            "addressable by occurrence — a string match must never collapse them"
        ),
        "files": [
            ("source", "development/duplicates-four.pdf", "report.json", "Source document (four identical amounts)"),
            ("control", "development/duplicates-control.pdf", "report.control.json", "Clean control"),
            ("ocr_ambiguity", "development/ocr-material-sign-ambiguity.pdf", "report.ocr-material-sign-ambiguity.json", "OCR sign-ambiguity companion"),
            ("ocr_control", "development/ocr-material-control.pdf", "report.ocr-material-control.json", "OCR clean control"),
        ],
    },
]


def _load_report(card_id: str, report_file: str) -> dict:
    path = EXAMPLES_DIR / card_id / report_file
    if not path.exists():
        raise SystemExit(f"missing captured report: {path} (run tests/gallery/capture.mjs)")
    return json.loads(path.read_text())


def _readers_from(report: dict) -> dict:
    out: dict[str, dict] = {}
    for r in report.get("readers", []):
        key = r["name"].lower().replace(" ", "_").replace(".", "_")
        entry = {
            "id": r["id"],
            "name": r["name"],
            "version": r["version"],
            "adapter_version": r["adapter_version"],
            "environment": r["environment"],
            "method": r["method"],
        }
        if r.get("model_hashes"):
            entry["model_sha256"] = r["model_hashes"][0]
        out[key] = entry
    return out


def _findings_from(report: dict) -> list[dict]:
    return [
        {
            "id": f["id"],
            "title": f["title"],
            "category": f["kind"],
            "page_index": f["page_index"],
        }
        for f in report.get("findings", [])
    ]


def build_card_manifest(card: dict) -> dict:
    """Manifest derived from the real captured report + real file bytes."""
    card_dir = EXAMPLES_DIR / card["id"]
    primary_report = _load_report(card["id"], "report.json")

    files: dict[str, dict] = {}
    for key, fixture_rel, report_file, role in card["files"]:
        staged = card_dir / Path(fixture_rel).name
        if not staged.exists():
            raise SystemExit(f"missing staged pdf: {staged} — copy step must run first")
        report = _load_report(card["id"], report_file)
        sha = _sha256(staged)
        # The report's document digest must bind the actual staged bytes —
        # a mismatch means the capture ran against different input.
        if report["document"]["sha256"] != sha:
            raise SystemExit(
                f"{card['id']}/{report_file}: report document sha256 "
                f"{report['document']['sha256'][:12]} != staged file {sha[:12]}"
            )
        files[key] = {
            "filename": staged.name,
            "sha256": sha,
            "byte_length": staged.stat().st_size,
            "download_url": f"/examples/{card['id']}/{staged.name}",
            "role": role,
            "report_file": report_file,
        }

    return {
        "schema_version": "1.0.0",
        "example_id": card["id"],
        "family": card["family"],
        "fixture_id": card["fixture_id"],
        "card_title": card["card_title"],
        "mechanism": card["mechanism"],
        "rights": RIGHTS,
        "provenance": "prepared",
        "timing": {
            "duration_ms": primary_report["execution"]["duration_ms"],
            "method": TIMING_METHOD[0],
            "description": TIMING_METHOD[1],
        },
        "files": files,
        "readers": _readers_from(primary_report),
        "findings": _findings_from(primary_report),
        "report_file": "report.json",
        "report_id": primary_report["report_id"],
        "run_key": primary_report["execution"]["run_key"],
    }


def stage_card_files(card: dict) -> None:
    card_dir = EXAMPLES_DIR / card["id"]
    card_dir.mkdir(parents=True, exist_ok=True)
    for _key, fixture_rel, _report, _role in card["files"]:
        src = FIXTURES_DIR / fixture_rel
        if not src.exists():
            raise SystemExit(f"missing fixture pdf: {src}")
        dst = card_dir / src.name
        if not dst.exists() or src.read_bytes() != dst.read_bytes():
            shutil.copyfile(src, dst)


def build_index(manifests: dict[str, dict]) -> dict:
    """Gallery index: one entry per card, derived from its manifest."""
    cards = []
    for card in CARDS:
        m = manifests[card["id"]]
        cards.append(
            {
                "example_id": m["example_id"],
                "card_title": m["card_title"],
                "mechanism": m["mechanism"],
                "fixture_id": m["fixture_id"],
                "family": m["family"],
                "manifest_url": f"/examples/{card['id']}/manifest.json",
                "report_url": f"/examples/{card['id']}/{m['report_file']}",
                "source": m["files"]["source"],
                "readers": [
                    {"name": r["name"], "version": r["version"], "method": r["method"]}
                    for r in m["readers"].values()
                ],
                "finding_count": len(m["findings"]),
                "variant_count": len(m["files"]) - 1,
                "timing_ms": m["timing"]["duration_ms"],
            }
        )
    return {"schema_version": "1.0.0", "cards": cards}


def generate() -> dict[str, dict]:
    manifests: dict[str, dict] = {}
    for card in CARDS:
        stage_card_files(card)
        manifest = build_card_manifest(card)
        manifests[card["id"]] = manifest
        out = EXAMPLES_DIR / card["id"] / "manifest.json"
        out.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    index = build_index(manifests)
    (EXAMPLES_DIR / "index.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=False) + "\n"
    )
    return manifests


def check() -> int:
    """Verify every manifest entry against real bytes and its bound report."""
    errors = 0
    for card in CARDS:
        card_dir = EXAMPLES_DIR / card["id"]
        mpath = card_dir / "manifest.json"
        if not mpath.exists():
            print(f"MISSING {mpath}")
            errors += 1
            continue
        manifest = json.loads(mpath.read_text())
        for key, entry in manifest.get("files", {}).items():
            f = card_dir / entry["filename"]
            if not f.exists():
                print(f"MISSING FILE {card['id']}/{key}: {entry['filename']}")
                errors += 1
                continue
            actual = _sha256(f)
            if actual != entry["sha256"]:
                print(f"HASH MISMATCH {card['id']}/{key}: {entry['filename']}")
                errors += 1
            if f.stat().st_size != entry["byte_length"]:
                print(f"SIZE MISMATCH {card['id']}/{key}: {entry['filename']}")
                errors += 1
            rep = card_dir / entry["report_file"]
            if not rep.exists():
                print(f"MISSING REPORT {card['id']}/{key}: {entry['report_file']}")
                errors += 1
                continue
            doc_sha = json.loads(rep.read_text())["document"]["sha256"]
            if doc_sha != entry["sha256"]:
                print(f"REPORT BINDING MISMATCH {card['id']}/{key}")
                errors += 1
    if not (EXAMPLES_DIR / "index.json").exists():
        print("MISSING index.json")
        errors += 1
    if errors == 0:
        print(f"OK: {len(CARDS)} cards, all manifest entries verified")
    return 1 if errors else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="verify manifests vs bytes")
    args = ap.parse_args()
    if args.check:
        return check()
    manifests = generate()
    print(f"Generated {len(manifests)} card manifests + index.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
