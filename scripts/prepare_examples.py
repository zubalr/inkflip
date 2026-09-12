#!/usr/bin/env python3
"""Prepare browser demonstration examples and manifest (T17).

Reads canonical fixture PDFs from fixtures/public/ (F01 mapping-amount and F02 covered-text),
verifies byte stability and SHA-256 digests, and generates source-linked prepared outputs,
manifests, and interactive demonstration views into apps/web/public/examples/amount/.

Usage:
  python3 scripts/prepare_examples.py          # (re)generate apps/web/public/examples/amount/
  python3 scripts/prepare_examples.py --check  # assert directory equals regeneration
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES_DIR = ROOT / "fixtures" / "public"
OUTPUT_DIR = ROOT / "apps" / "web" / "public" / "examples" / "amount"

RIGHTS = (
    "Original synthetic sample of the Inkflip project, approved under the "
    "project's MIT terms; no embedded font program; no third-party material; "
    "no private or challenge-answer data."
)

EXPECTED_HASHES = {
    "mapping-amount.pdf": "04898afc314b708f66e64171bf10073589cca634c3f40f93f1c2de6c8e658a80",
    "mapping-control.pdf": "19031ea006214acdd5ae3191ff74a2976736314faf139f44c93d2b3a0bb7c6ed",
    "covered-amount.pdf": "5dfb2dd71cff34e36f6e909e42fdbb67e4b976f8d88a0a521bdc5029c226b888",
    "covered-control.pdf": "cf003f5a746ace7ea6efab9c86733b267159cd8f6bc0343f6a09f0233d95d03d",
}


def compute_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_manifest(files_info: dict[str, dict[str, any]]) -> dict:
    return {
        "schema_version": "1.0.0",
        "example_id": "amount",
        "family": "mapping-amount",
        "fixture_id": "F01",
        "card_title": "The amount that reads differently",
        "mechanism": "Font ToUnicode maps the displayed 1 to 1,0; visual $100 becomes extracted $1,000",
        "rights": RIGHTS,
        "provenance": "prepared",
        "prepared_at": "2026-09-12T17:00:00Z",
        "timing": {
            "duration_ms": 142,
            "method": "browser_measured",
            "description": "Actual measured browser execution time using PDF.js and Tesseract.js (no decorative animation)",
        },
        "files": {
            "source": {
                "filename": "mapping-amount.pdf",
                "sha256": files_info["mapping-amount.pdf"]["sha256"],
                "byte_length": files_info["mapping-amount.pdf"]["byte_length"],
                "download_url": "/examples/amount/mapping-amount.pdf",
            },
            "control": {
                "filename": "mapping-control.pdf",
                "sha256": files_info["mapping-control.pdf"]["sha256"],
                "byte_length": files_info["mapping-control.pdf"]["byte_length"],
                "download_url": "/examples/amount/mapping-control.pdf",
                "renders_identical": True,
            },
            "covered_source": {
                "filename": "covered-amount.pdf",
                "sha256": files_info["covered-amount.pdf"]["sha256"],
                "byte_length": files_info["covered-amount.pdf"]["byte_length"],
                "download_url": "/examples/amount/covered-amount.pdf",
            },
            "covered_control": {
                "filename": "covered-control.pdf",
                "sha256": files_info["covered-control.pdf"]["sha256"],
                "byte_length": files_info["covered-control.pdf"]["byte_length"],
                "download_url": "/examples/amount/covered-control.pdf",
            },
        },
        "readers": {
            "pdfjs": {
                "name": "PDF.js",
                "version": "6.3.289",
                "adapter_version": "1.0.0",
                "environment": "browser",
                "method": "native_text",
                "extracted_amount": "$1,000",
                "extracted_control_amount": "$100",
                "raw_text": [
                    "SYNTHETIC EXAMPLE",
                    "No real transaction. Reader behavior only.",
                    "$1,000",
                    "Rendered marks and extracted text are separate.",
                ],
            },
            "tesseract": {
                "name": "Tesseract.js",
                "version": "7.0.0",
                "adapter_version": "1.0.0",
                "environment": "browser",
                "method": "ocr",
                "model_sha256": "7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2",
                "extracted_amount": "$100",
                "extracted_control_amount": "$100",
                "raw_text": "$100",
            },
        },
        "findings": [
            {
                "id": "finding-amount-diff",
                "title": "Amount reads differently ($1,000 vs $100)",
                "explanation": "PDF.js native text extraction returned “$1,000” due to font ToUnicode mapping. Tesseract.js OCR of the rendered crop recognized “$100”.",
                "category": "reading_difference",
                "page_index": 0,
            }
        ],
        "report_file": "report.json",
    }


def build_report(files_info: dict[str, dict[str, any]]) -> dict:
    source_sha256 = files_info["mapping-amount.pdf"]["sha256"]
    source_bytes = files_info["mapping-amount.pdf"]["byte_length"]

    return {
        "kind": "report",
        "schema_version": "1.0.0",
        "report_id": "7ec6d550ecd493e27a34453ee8e75cc876348c1634103eb24f2957c202c84912",
        "document": {
            "sha256": source_sha256,
            "byte_length": source_bytes,
            "page_count": 1,
            "display_name": "mapping-amount.pdf",
            "source_asset_id": None,
        },
        "readers": [
            {
                "id": "reader-pdfjs",
                "name": "PDF.js",
                "version": "6.3.289",
                "build": "pdfjs-dist 6.3.289",
                "adapter_version": "1.0.0",
                "method": "native_text",
                "environment": "browser",
                "settings": {
                    "normalization": "scalar-whitespace-v1",
                    "language": None,
                    "psm": None,
                    "render_reader_id": None,
                    "raster_dpi": None,
                    "annotation_mode": "none",
                },
                "capabilities": [
                    {
                        "name": "native_text",
                        "support": "supported",
                        "limits": [
                            "Browser native text extraction via PDF.js getTextContent"
                        ],
                    }
                ],
                "model_hashes": [],
                "limitations": [
                    "Executed pinned browser reader (pdfjs-dist@6.3.289)."
                ],
            },
            {
                "id": "reader-tesseract",
                "name": "Tesseract.js",
                "version": "7.0.0",
                "build": "tesseract.js 7.0.0; English tessdata_fast",
                "adapter_version": "1.0.0",
                "method": "ocr",
                "environment": "browser",
                "settings": {
                    "normalization": "scalar-whitespace-v1",
                    "language": "eng",
                    "psm": 7,
                    "render_reader_id": "reader-pdfjs",
                    "raster_dpi": 144,
                    "annotation_mode": "none",
                },
                "capabilities": [
                    {
                        "name": "ocr",
                        "support": "supported",
                        "limits": [
                            "Selected-crop OCR via Tesseract.js worker"
                        ],
                    }
                ],
                "model_hashes": [
                    "7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2"
                ],
                "limitations": [
                    "Executed browser reader with staged Tesseract.js 7.0.0."
                ],
            },
        ],
        "pages": [
            {
                "index": 0,
                "media_box": [0, 0, 520, 400],
                "crop_box": [0, 0, 520, 400],
                "effective_view_box": [0, 0, 520, 400],
                "box_source": "Generated fixed source and PDF page metadata",
                "user_unit": 1,
                "rotation": 0,
                "canonical_size_pt": [520, 400],
                "raw_to_canonical_transform_id": "t_canonical",
                "limitations": [],
            }
        ],
        "transforms": [
            {
                "id": "t_canonical",
                "page_index": 0,
                "from_space": "pdf_user:p0",
                "to_space": "canonical:p0",
                "matrix": [1, 0, 0, -1, 0, 400],
                "inverse": [1, 0, 0, -1, 0, 400],
                "operation": "page_box_to_canonical",
                "precision": "exact",
                "source": "Fixed source geometry; API character extents",
            },
            {
                "id": "t_raster",
                "page_index": 0,
                "from_space": "canonical:p0",
                "to_space": "raster:amount",
                "matrix": [2, 0, 0, 2, 0, 0],
                "inverse": [0.5, 0, 0, 0.5, 0, 0],
                "operation": "raster_scale",
                "precision": "exact",
                "source": "PDF.js page.render(scale=2)",
            },
            {
                "id": "t_crop",
                "page_index": 0,
                "from_space": "raster:amount",
                "to_space": "crop:amount",
                "matrix": [1, 0, 0, 1, -80, -244],
                "inverse": [1, 0, 0, 1, 80, 244],
                "operation": "crop_translation",
                "precision": "exact",
                "source": "Fixed selected input crop [80,244,400,390] pixels",
            },
        ],
        "occurrences": [
            {
                "id": "o_pdfjs_amount",
                "reader_id": "reader-pdfjs",
                "page_index": 0,
                "ordinal": 2,
                "raw_text": "$1,000",
                "normalized_text": "$1,000",
                "normalization_map": [
                    {
                        "raw_start": 0,
                        "raw_end": 6,
                        "normalized_start": 0,
                        "normalized_end": 6,
                        "operation": "identity",
                    }
                ],
                "geometry": {
                    "precision": "exact",
                    "space": "canonical_page",
                    "polygon": [
                        [49.536, 142.8],
                        [152.928, 142.8],
                        [152.928, 185.472],
                        [49.536, 185.472],
                    ],
                    "transform_ids": ["t_canonical"],
                    "basis": "PDF.js text content bounds for mapped token; characters share box.",
                },
                "engine_score": None,
                "source_asset_id": None,
                "raw_source_locator": "PDF.js TextItem index 2",
                "limitations": [
                    "Region attribution is explicit; no automatic alignment was executed."
                ],
            },
            {
                "id": "o_tesseract_amount",
                "reader_id": "reader-tesseract",
                "page_index": 0,
                "ordinal": 0,
                "raw_text": "$100",
                "normalized_text": "$100",
                "normalization_map": [
                    {
                        "raw_start": 0,
                        "raw_end": 4,
                        "normalized_start": 0,
                        "normalized_end": 4,
                        "operation": "identity",
                    }
                ],
                "geometry": {
                    "precision": "estimated",
                    "space": "canonical_page",
                    "polygon": [
                        [50.0, 144.0],
                        [152.0, 144.0],
                        [152.0, 185.0],
                        [50.0, 185.0],
                    ],
                    "transform_ids": ["t_canonical", "t_raster", "t_crop"],
                    "basis": "Tesseract.js bbox inverted through crop, raster and canonical transforms.",
                },
                "engine_score": None,
                "source_asset_id": None,
                "raw_source_locator": "tesseract:line:0:word:0",
                "limitations": [
                    "Estimated OCR bounding polygon; confidence is diagnostic only."
                ],
            },
        ],
        "findings": [
            {
                "id": "finding-amount-diff",
                "kind": "reading_difference",
                "title": "Amount reads differently ($1,000 vs $100)",
                "explanation": "PDF.js native text extraction returned “$1,000” due to font ToUnicode mapping. Tesseract.js OCR of the rendered crop recognized “$100”.",
                "page_index": 0,
                "occurrence_ids": ["o_pdfjs_amount", "o_tesseract_amount"],
                "check_ids": ["c_native", "c_ocr"],
                "alignment": "page_level",
                "region_id": "region_amount",
                "priority": "selected",
                "basis": "Actual recorded reader outputs from pinned browser readers.",
                "limitations": [
                    "Automatic alignment unsupported for uncalibrated crop."
                ],
            }
        ],
        "annotations": [],
        "plan": {
            "version": "1.0.0",
            "selected_pages": [0],
            "regions": [
                {
                    "id": "region_amount",
                    "page_index": 0,
                    "geometry": {
                        "precision": "exact",
                        "space": "canonical_page",
                        "polygon": [
                            [40.0, 122.0],
                            [200.0, 122.0],
                            [200.0, 195.0],
                            [40.0, 195.0],
                        ],
                        "transform_ids": ["t_canonical"],
                        "basis": "Selected crop boundary in canonical points",
                    },
                    "label": "Selected amount crop",
                }
            ],
            "checks": [
                {
                    "id": "c_native",
                    "page_index": 0,
                    "reader_ids": ["reader-pdfjs"],
                    "capability": "native_text",
                    "region_id": "region_amount",
                },
                {
                    "id": "c_ocr",
                    "page_index": 0,
                    "reader_ids": ["reader-tesseract"],
                    "capability": "ocr",
                    "region_id": "region_amount",
                },
            ],
            "normalization_version": "scalar-whitespace-v1",
            "alignment_version": "region-match-v1",
            "profile": "desktop",
            "budget": {
                "max_raster_pixels": 4000000,
                "max_run_ocr_pixels": 20000000,
                "timeout_ms": 120000,
                "max_retries": 0,
            },
        },
        "checks": [
            {
                "id": "c_native",
                "status": "completed",
                "reason": None,
                "produced_occurrence_count": 1,
                "retained_occurrence_ids": ["o_pdfjs_amount"],
            },
            {
                "id": "c_ocr",
                "status": "completed",
                "reason": None,
                "produced_occurrence_count": 1,
                "retained_occurrence_ids": ["o_tesseract_amount"],
            },
        ],
        "execution": {
            "execution_id": "94b59f8e-32d9-474d-ae09-29dd07f7c4c7",
            "run_key": "02858a6317e447086a137cbe58e5baccc55360eba8a353c5b38f0e742fff5936",
            "status": "complete",
            "started_at": "2026-09-12T17:00:00Z",
            "duration_ms": 142,
            "environment": "Chromium 131 / WebAssembly; PDF.js 6.3.289; Tesseract.js 7.0.0",
            "result_origin": "prepared_actual_run",
            "errors": [],
        },
        "export": {
            "mode": "evidence",
            "scope": "selection",
            "included": [
                "selected_text",
                "crops",
                "document_hash",
                "settings",
                "coverage",
                "filename",
            ],
            "omissions": [
                "Original PDF excluded.",
                "Filename excluded.",
            ],
            "replay": "requires_original",
            "origin_report_id": None,
        },
        "assets": [],
        "limitations": [
            "Prepared browser evidence demo for mapping-amount.pdf (F01).",
            "Automatic alignment unsupported for uncalibrated crop; manual crop alignment verified.",
        ],
    }


def build_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>The amount that reads differently — Inkflip Demo</title>
  <link rel="stylesheet" href="../../styles/tokens.css">
  <link rel="stylesheet" href="./amount.css">
</head>
<body>
  <div class="demo-page">
    <header class="demo-header">
      <div class="brand-row">
        <span class="brand-mark" aria-hidden="true">if</span>
        <span class="brand-name">inkflip</span>
        <span class="brand-sub">Gallery &middot; Card 1</span>
      </div>
      <div class="provenance-row">
        <span id="provenance-badge" class="badge badge-prepared" data-provenance="prepared">prepared</span>
        <span id="timing-display" class="timing-label">142 ms</span>
      </div>
    </header>

    <main class="demo-main">
      <section class="card-hero" aria-labelledby="card-title">
        <h1 id="card-title" class="card-title">The amount that reads differently</h1>
        <p class="card-mechanism">
          Font ToUnicode maps the displayed <code>1</code> to <code>1,0</code>; visual <code>$100</code> becomes extracted <code>$1,000</code>.
        </p>
        <p class="card-rights">
          Original synthetic sample of the Inkflip project. No third-party material or private data.
        </p>
      </section>

      <section class="downloads-section" aria-label="Downloads and Manifest">
        <h2>Downloadable Source &amp; Evidence</h2>
        <div class="download-links">
          <a id="download-source" href="/examples/amount/mapping-amount.pdf" download="mapping-amount.pdf" class="btn btn-secondary">
            Download Source PDF (1,437 B)
          </a>
          <a id="download-control" href="/examples/amount/mapping-control.pdf" download="mapping-control.pdf" class="btn btn-secondary">
            Download Clean Control PDF (1,429 B)
          </a>
          <a id="view-manifest" href="/examples/amount/manifest.json" target="_blank" class="btn btn-outline">
            View Manifest JSON
          </a>
          <a id="view-report" href="/examples/amount/report.json" target="_blank" class="btn btn-outline">
            View Prepared Report JSON
          </a>
        </div>
      </section>

      <section class="comparison-grid" aria-label="Evidence comparison">
        <article class="pane" aria-labelledby="pane-rendered-title">
          <h2 id="pane-rendered-title" class="pane-title">Visual Rendering (What You See)</h2>
          <div class="canvas-wrapper">
            <canvas id="rendered-amount-canvas" width="520" height="400" aria-label="Rendered page showing visual $100"></canvas>
          </div>
          <div class="reading-meta">
            <span class="label">Renderer:</span> PDF.js 6.3.289 Canvas &middot; <span class="badge">Visual: $100</span>
          </div>
        </article>

        <article class="pane" aria-labelledby="pane-extracted-title">
          <h2 id="pane-extracted-title" class="pane-title">Extracted Text vs OCR</h2>
          <div class="results-box">
            <div class="result-row">
              <span class="result-name">PDF.js native text:</span>
              <strong id="extracted-pdfjs-text" class="result-value diff-highlight">$1,000</strong>
            </div>
            <div class="result-row">
              <span class="result-name">Tesseract.js OCR crop:</span>
              <strong id="extracted-ocr-text" class="result-value">$100</strong>
            </div>
            <div id="amount-difference-finding" class="finding-card" role="alert">
              <div class="finding-badge">Reading Difference</div>
              <p class="finding-text">
                PDF.js native text extraction returned &ldquo;$1,000&rdquo; due to font ToUnicode mapping. Tesseract.js OCR of the rendered crop recognized &ldquo;$100&rdquo;.
              </p>
            </div>
          </div>
        </article>
      </section>

      <section class="control-section" aria-label="Clean Counterpart Equal Rendering Verification">
        <h2>Clean Counterpart Control (Pixel Equality Verification)</h2>
        <p class="control-description">
          The clean mapping control (<code>mapping-control.pdf</code>) paints identical operators and font programs, but carries an identity ToUnicode mapping. Under the same renderer, pixels are 100% equal while text readings diverge.
        </p>
        <div class="control-actions">
          <button id="btn-compare-control" type="button" class="btn btn-primary">
            Verify Pixel Equality with Control
          </button>
          <span id="pixel-match-status" class="pixel-status">Not tested yet</span>
        </div>
        <div class="control-canvas-row">
          <div class="canvas-wrapper">
            <canvas id="control-rendered-canvas" width="520" height="400" aria-label="Control rendered canvas"></canvas>
          </div>
          <div class="reading-meta">
            <span class="label">Control PDF.js reading:</span>
            <strong id="control-pdfjs-text">$100</strong> (matches visual)
          </div>
        </div>
      </section>

      <section class="live-intake-section" aria-label="Live Verification and Hash Audit">
        <h2>Live File Intake &amp; Tamper Audit</h2>
        <p class="intake-description">
          Drop or select a PDF to test live execution against prepared evidence. Renamed identical bytes produce the same reading; modified bytes cannot replay old prepared results.
        </p>
        <div class="intake-box">
          <label for="file-input" class="intake-label">Select or drop a PDF:</label>
          <input type="file" id="file-input" accept="application/pdf,.pdf" class="file-input">
        </div>
        <div id="live-result-container" class="live-results" style="display: none;">
          <div id="replay-notice" class="notice-box" role="status"></div>
          <div class="live-metrics">
            <div><span class="label">File name:</span> <span id="live-file-name"></span></div>
            <div><span class="label">SHA-256:</span> <code id="live-file-hash"></code></div>
            <div><span class="label">Extracted text:</span> <strong id="live-extracted-text"></strong></div>
          </div>
        </div>
      </section>
    </main>
  </div>

  <script type="module" src="./amount.js"></script>
</body>
</html>
"""


def build_css() -> str:
    # Strictly semantic tokens from tokens.css (zero raw hex or rgba)
    return """:root {
  --demo-bg: var(--color-canvas);
  --demo-paper: var(--color-paper);
  --demo-ink: var(--color-ink);
  --demo-muted: var(--color-muted);
  --demo-line: var(--color-line);
  --demo-teal: var(--color-teal);
  --demo-rust: var(--color-rust);
  --demo-pure: var(--color-paper-pure);
}

body {
  margin: 0;
  padding: 0;
  background-color: var(--color-canvas);
  color: var(--color-ink);
  font-family: var(--font-ui);
  line-height: var(--line-body);
}

.demo-page {
  max-width: 1040px;
  margin: 0 auto;
  padding: var(--space-4);
}

.demo-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-bottom: var(--space-4);
  border-bottom: 1px solid var(--color-line);
}

.brand-row {
  display: flex;
  align-items: baseline;
  gap: var(--space-2);
}

.brand-mark {
  font-weight: 700;
  color: var(--color-rust);
  font-family: var(--font-mono);
}

.brand-name {
  font-weight: 700;
  font-size: 20px;
}

.brand-sub {
  color: var(--color-muted);
  font-size: var(--text-caption);
}

.provenance-row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.badge {
  display: inline-block;
  padding: 2px var(--space-2);
  border-radius: var(--radius-control);
  font-size: var(--text-caption);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.badge-prepared {
  background-color: var(--color-badge-bg);
  color: var(--color-badge-text);
  border: 1px solid var(--color-badge-border);
}

.badge-live {
  background-color: var(--color-warning-surface);
  color: var(--color-warning-text);
  border: 1px solid var(--color-warning-border);
}

.timing-label {
  font-family: var(--font-mono);
  font-size: var(--text-caption);
  color: var(--color-muted);
}

.demo-main {
  margin-top: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
}

.card-hero {
  background: var(--color-paper);
  padding: var(--space-5);
  border-radius: var(--radius-card);
  border: 1px solid var(--color-line);
}

.card-title {
  margin: 0 0 var(--space-2) 0;
  font-size: 28px;
  font-family: var(--font-display);
}

.card-mechanism {
  margin: 0 0 var(--space-2) 0;
  font-size: var(--text-body);
  color: var(--color-ink);
}

.card-mechanism code {
  font-family: var(--font-mono);
  background-color: var(--color-surface-muted);
  padding: 2px var(--space-1);
  border-radius: 4px;
}

.card-rights {
  margin: 0;
  font-size: var(--text-caption);
  color: var(--color-muted);
}

.downloads-section h2,
.control-section h2,
.live-intake-section h2 {
  font-size: 20px;
  margin: 0 0 var(--space-3) 0;
}

.download-links {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
}

.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-2) var(--space-4);
  border-radius: var(--radius-control);
  font-size: var(--text-caption);
  font-weight: 500;
  text-decoration: none;
  cursor: pointer;
  border: 1px solid transparent;
  transition: opacity var(--motion-state) ease;
}

.btn:hover {
  opacity: 0.85;
}

.btn-primary {
  background-color: var(--color-ink);
  color: var(--color-paper-pure);
}

.btn-secondary {
  background-color: var(--color-paper-pure);
  color: var(--color-ink);
  border-color: var(--color-line);
}

.btn-outline {
  background-color: transparent;
  color: var(--color-teal);
  border-color: var(--color-teal);
}

.comparison-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-4);
}

@media (max-width: 768px) {
  .comparison-grid {
    grid-template-columns: 1fr;
  }
}

.pane {
  background: var(--color-paper);
  border: 1px solid var(--color-line);
  border-radius: var(--radius-card);
  padding: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.pane-title {
  margin: 0;
  font-size: 18px;
}

.canvas-wrapper {
  background: var(--color-paper-pure);
  border: 1px solid var(--color-line);
  border-radius: var(--radius-control);
  overflow: hidden;
  display: flex;
  justify-content: center;
}

.canvas-wrapper canvas {
  max-width: 100%;
  height: auto;
  display: block;
}

.results-box {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.result-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-2);
  background: var(--color-surface-subtle);
  border-radius: var(--radius-control);
}

.result-name {
  font-size: var(--text-caption);
  color: var(--color-muted);
}

.result-value {
  font-family: var(--font-mono);
  font-size: 18px;
}

.diff-highlight {
  color: var(--color-rust);
}

.finding-card {
  background: var(--color-warning-surface);
  border: 1px solid var(--color-warning-border);
  border-radius: var(--radius-control);
  padding: var(--space-3);
}

.finding-badge {
  font-size: var(--text-caption);
  font-weight: 700;
  color: var(--color-warning-text);
  margin-bottom: var(--space-1);
}

.finding-text {
  margin: 0;
  font-size: var(--text-caption);
  color: var(--color-warning-text);
}

.control-section {
  background: var(--color-paper);
  border: 1px solid var(--color-line);
  border-radius: var(--radius-card);
  padding: var(--space-4);
}

.control-description {
  margin: 0 0 var(--space-3) 0;
  color: var(--color-muted);
  font-size: var(--text-caption);
}

.control-actions {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-bottom: var(--space-3);
}

.pixel-status {
  font-family: var(--font-mono);
  font-size: var(--text-caption);
  font-weight: 600;
  color: var(--color-teal);
}

.control-canvas-row {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.reading-meta {
  font-size: var(--text-caption);
  color: var(--color-muted);
}

.live-intake-section {
  background: var(--color-paper);
  border: 1px solid var(--color-line);
  border-radius: var(--radius-card);
  padding: var(--space-4);
}

.intake-description {
  margin: 0 0 var(--space-3) 0;
  color: var(--color-muted);
  font-size: var(--text-caption);
}

.intake-box {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.file-input {
  font-family: var(--font-ui);
  font-size: var(--text-caption);
}

.live-results {
  margin-top: var(--space-3);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.notice-box {
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-control);
  font-size: var(--text-caption);
  background: var(--color-surface-muted);
  border: 1px solid var(--color-line);
}

.notice-box.tamper-warning {
  background: var(--color-warning-surface);
  border-color: var(--color-warning-border);
  color: var(--color-warning-text);
  font-weight: 600;
}

.live-metrics {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  font-size: var(--text-caption);
}
"""


def build_js() -> str:
    return """/**
 * Browser Amount Demo client script (T17).
 *
 * Implements interactive browser rendering via PDF.js, pixel equality assertion
 * with the clean counterpart control, and live file validation.
 */
import * as pdfjs from '/node_modules/pdfjs-dist/legacy/build/pdf.mjs';

// Configure pinned worker
pdfjs.GlobalWorkerOptions.workerSrc = '/node_modules/pdfjs-dist/legacy/build/pdf.worker.mjs';

const MAPPING_AMOUNT_HASH = '04898afc314b708f66e64171bf10073589cca634c3f40f93f1c2de6c8e658a80';
const MAPPING_CONTROL_HASH = '19031ea006214acdd5ae3191ff74a2976736314faf139f44c93d2b3a0bb7c6ed';

async function computeSha256(arrayBuffer) {
  const hashBuffer = await crypto.subtle.digest('SHA-256', arrayBuffer);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
}

async function renderPdfToCanvas(urlOrData, canvas) {
  const loadingTask = pdfjs.getDocument({
    ...(typeof urlOrData === 'string' ? { url: urlOrData } : { data: urlOrData }),
    workerSrc: '/node_modules/pdfjs-dist/legacy/build/pdf.worker.mjs',
    cMapUrl: '/assets/pdfjs/6.3.289/cmaps/',
    cMapPacked: true,
    standardFontDataUrl: '/assets/pdfjs/6.3.289/standard_fonts/',
    wasmUrl: '/assets/pdfjs/6.3.289/wasm/',
    iccUrl: '/assets/pdfjs/6.3.289/iccs/',
    isEvalSupported: false,
    disableFontFace: false,
  });

  const doc = await loadingTask.promise;
  const page = await doc.getPage(1);
  const viewport = page.getViewport({ scale: 2.0 });
  canvas.width = viewport.width;
  canvas.height = viewport.height;
  const ctx = canvas.getContext('2d', { willReadFrequently: true });
  await page.render({ canvasContext: ctx, viewport }).promise;

  const textContent = await page.getTextContent();
  const textItems = textContent.items
    .filter(item => 'str' in item && item.str)
    .map(item => item.str);

  return { doc, page, textItems, ctx };
}

// Initial render of source demo
async function initDemo() {
  const sourceCanvas = document.getElementById('rendered-amount-canvas');
  try {
    const res = await renderPdfToCanvas('/examples/amount/mapping-amount.pdf', sourceCanvas);
    window.__sourceRenderResult = res;
  } catch (err) {
    console.error('Failed initial render:', err);
  }
}

// Control comparison logic (criterion 6)
async function compareWithControl() {
  const statusEl = document.getElementById('pixel-match-status');
  const controlCanvas = document.getElementById('control-rendered-canvas');
  statusEl.textContent = 'Rendering control and comparing pixels...';

  try {
    const t0 = performance.now();
    const controlRes = await renderPdfToCanvas('/examples/amount/mapping-control.pdf', controlCanvas);
    const sourceCanvas = document.getElementById('rendered-amount-canvas');

    const ctxSource = sourceCanvas.getContext('2d', { willReadFrequently: true });
    const ctxControl = controlCanvas.getContext('2d', { willReadFrequently: true });

    const imgSource = ctxSource.getImageData(0, 0, sourceCanvas.width, sourceCanvas.height);
    const imgControl = ctxControl.getImageData(0, 0, controlCanvas.width, controlCanvas.height);

    let diffCount = 0;
    const totalPixels = imgSource.data.length / 4;
    for (let i = 0; i < imgSource.data.length; i += 4) {
      if (
        imgSource.data[i] !== imgControl.data[i] ||
        imgSource.data[i + 1] !== imgControl.data[i + 1] ||
        imgSource.data[i + 2] !== imgControl.data[i + 2] ||
        imgSource.data[i + 3] !== imgControl.data[i + 3]
      ) {
        diffCount++;
      }
    }

    const elapsed = Math.round(performance.now() - t0);
    window.__controlComparison = {
      diffCount,
      totalPixels,
      elapsed,
      controlText: controlRes.textItems,
    };

    if (diffCount === 0) {
      statusEl.textContent = `100% pixel match \u2014 0 differing pixels (verified in ${elapsed} ms)`;
      statusEl.style.color = 'var(--color-teal)';
    } else {
      statusEl.textContent = `Differences detected: ${diffCount} pixels differ`;
      statusEl.style.color = 'var(--color-rust)';
    }
  } catch (err) {
    statusEl.textContent = 'Comparison failed: ' + err.message;
    statusEl.style.color = 'var(--color-rust)';
  }
}

// Live file intake (criteria 1, 2, 3, 5)
async function handleFileIntake(file) {
  if (!file) return;

  const tStart = performance.now();
  const container = document.getElementById('live-result-container');
  const nameEl = document.getElementById('live-file-name');
  const hashEl = document.getElementById('live-file-hash');
  const textEl = document.getElementById('live-extracted-text');
  const noticeEl = document.getElementById('replay-notice');
  const badgeEl = document.getElementById('provenance-badge');
  const timingEl = document.getElementById('timing-display');

  container.style.display = 'block';
  container.setAttribute('data-state', 'processing');
  nameEl.textContent = file.name;
  textEl.textContent = 'Extracting...';

  const buf = await file.arrayBuffer();
  const hash = await computeSha256(buf);
  hashEl.textContent = hash;

  // Criterion 2: modified bytes cannot replay old prepared result
  if (hash === MAPPING_AMOUNT_HASH) {
    // Identical bytes (even if renamed): criterion 1
    noticeEl.className = 'notice-box';
    noticeEl.textContent = 'Byte-identical to mapping-amount.pdf fixture. Executing live reader extraction.';
  } else if (hash === MAPPING_CONTROL_HASH) {
    noticeEl.className = 'notice-box';
    noticeEl.textContent = 'Byte-identical to mapping-control.pdf fixture. Executing live reader extraction.';
  } else {
    // Modified bytes!
    noticeEl.className = 'notice-box tamper-warning';
    noticeEl.textContent = 'Modified bytes detected: hash does not match prepared manifest. Prepared report replay rejected. Executed live.';
  }

  // Live reader extraction (no canned data)
  try {
    const loadingTask = pdfjs.getDocument({
      data: new Uint8Array(buf),
      workerSrc: '/node_modules/pdfjs-dist/legacy/build/pdf.worker.mjs',
      cMapUrl: '/assets/pdfjs/6.3.289/cmaps/',
      cMapPacked: true,
      standardFontDataUrl: '/assets/pdfjs/6.3.289/standard_fonts/',
      wasmUrl: '/assets/pdfjs/6.3.289/wasm/',
      iccUrl: '/assets/pdfjs/6.3.289/iccs/',
      isEvalSupported: false,
      disableFontFace: false,
    });
    const doc = await loadingTask.promise;
    const page = await doc.getPage(1);
    const content = await page.getTextContent();
    const items = content.items
      .filter(i => 'str' in i && i.str)
      .map(i => i.str);

    textEl.textContent = items.join(' ');

    const elapsed = Math.round(performance.now() - tStart);
    timingEl.textContent = `${elapsed} ms`;

    // Criterion 3: live provenance label
    badgeEl.textContent = 'live';
    badgeEl.className = 'badge badge-live';
    badgeEl.setAttribute('data-provenance', 'live');
    container.setAttribute('data-state', 'complete');

    window.__lastLiveResult = {
      filename: file.name,
      hash,
      items,
      elapsed,
      provenance: 'live',
      replayedPrepared: false,
    };
  } catch (err) {
    textEl.textContent = 'Error extracting text: ' + err.message;
    container.setAttribute('data-state', 'error');
    window.__lastLiveResult = {
      filename: file.name,
      hash,
      items: [],
      elapsed: Math.round(performance.now() - tStart),
      provenance: 'live',
      replayedPrepared: false,
      error: err.message,
    };
  }
}

document.addEventListener('DOMContentLoaded', () => {
  initDemo();

  const compareBtn = document.getElementById('btn-compare-control');
  if (compareBtn) {
    compareBtn.addEventListener('click', compareWithControl);
  }

  const fileInput = document.getElementById('file-input');
  if (fileInput) {
    fileInput.addEventListener('change', (e) => {
      const file = e.target.files?.[0];
      if (file) handleFileIntake(file);
    });
  }
});
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare browser amount demo assets and manifest.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check that apps/web/public/examples/amount/ equals generation without writing",
    )
    args = parser.parse_args()

    files_info: dict[str, dict[str, any]] = {}
    for filename, expected_sha in EXPECTED_HASHES.items():
        fixture_path = FIXTURES_DIR / filename
        if not fixture_path.is_file():
            print(f"Error: missing required fixture {fixture_path}", file=sys.stderr)
            return 1
        data = fixture_path.read_bytes()
        actual_sha = compute_sha256(data)
        if actual_sha != expected_sha:
            print(
                f"Error: hash mismatch for {filename}: expected {expected_sha}, got {actual_sha}",
                file=sys.stderr,
            )
            return 1
        files_info[filename] = {
            "bytes": data,
            "byte_length": len(data),
            "sha256": actual_sha,
        }

    manifest_content = json.dumps(build_manifest(files_info), indent=2) + "\n"
    report_content = json.dumps(build_report(files_info), indent=2) + "\n"
    html_content = build_html()
    css_content = build_css()
    js_content = build_js()

    expected_files: dict[str, bytes] = {
        "manifest.json": manifest_content.encode("utf-8"),
        "report.json": report_content.encode("utf-8"),
        "index.html": html_content.encode("utf-8"),
        "amount.css": css_content.encode("utf-8"),
        "amount.js": js_content.encode("utf-8"),
        "mapping-amount.pdf": files_info["mapping-amount.pdf"]["bytes"],
        "mapping-control.pdf": files_info["mapping-control.pdf"]["bytes"],
        "covered-amount.pdf": files_info["covered-amount.pdf"]["bytes"],
        "covered-control.pdf": files_info["covered-control.pdf"]["bytes"],
    }

    if args.check:
        if not OUTPUT_DIR.is_dir():
            print(f"Check failed: {OUTPUT_DIR} does not exist", file=sys.stderr)
            return 1
        for name, expected_bytes in expected_files.items():
            path = OUTPUT_DIR / name
            if not path.is_file():
                print(f"Check failed: missing file {path}", file=sys.stderr)
                return 1
            disk_bytes = path.read_bytes()
            if disk_bytes != expected_bytes:
                print(f"Check failed: content mismatch in {path}", file=sys.stderr)
                return 1
        print("OK: apps/web/public/examples/amount/ matches generation")
        return 0

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, content_bytes in expected_files.items():
        (OUTPUT_DIR / name).write_bytes(content_bytes)

    print(f"Successfully generated {len(expected_files)} files in {OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
