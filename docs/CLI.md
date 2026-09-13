# Inkflip Native CLI Reference

The **`inkflip`** command-line interface provides local, offline inspection, reader comparison, report rendering, and replay for PDF documents.

## Invocation

The CLI can be invoked via Python module execution within the native environment:

```bash
uv run --project native python -m inkflip.cli <command> [options]
```

## Commands

### 1. Readers List

List installed, allowlisted PDF reading adapters and their capability manifests:

```bash
inkflip readers list --json
```

- **Output**: JSON object listing installed readers (`pdfium-native`, `pypdf-native`, `tesseract-native`) with exact versions, builds, settings, capabilities, limits, and model hashes.
- **Exit code**: `0` on success.

### 2. Inspect

Inspect a local PDF file and produce a sealed, schema-valid `.inkflip.json` evidence report:

```bash
inkflip inspect FILE --out REPORT [options]
```

#### Options:
- `--out REPORT`: (Required) Destination path for output report JSON.
- `--reader READER`: (Repeatable, default: `pdfium`) Reader adapter to run (`pdfium`, `pypdf`, `tesseract`).
- `--pages PAGES`: (Default: `1`) 1-based page specification (e.g. `1`, `1,3-5`, `all`). Max 1000 pages.
- `--ocr-pages OCR_PAGES`: 1-based subset of selected pages for OCR (max 20 pages per run).
- `--region x0,y0,x1,y1`: Canonical physical point coordinates (`x0 < x1`, `y0 < y1`). Requires exactly 1 selected page.
- `--profile PROFILE`: (Default: `native-default`) Execution profile ID (`native`, `desktop`, `mobile`).
- `--embed-source`: Embed original PDF bytes in the report as base64 asset for self-contained replays.
- `--replace-output`: Permit overwriting an existing output file.

### 3. Validate

Validate an existing `.inkflip.json` report without re-reading the PDF or executing reader runtimes:

```bash
inkflip validate REPORT
```

- **Validation**: Verifies bounds, JSON Schema conformance, transform references, raw/normalized text mappings, privacy disclosures, and cryptographic report/run hashes.
- **Exit codes**:
  - `0`: Valid report.
  - `2`: Schema error, contract failure, or invalid JSON syntax.
  - `4`: Report file missing or unreadable.

### 4. Report (HTML Export)

Convert an existing `.inkflip.json` evidence report into a portable, standalone HTML report:

```bash
inkflip report REPORT --format html --out FILE [options]
```

- **Format**: Strictly `html`.
- **Security**: Strict Content Security Policy (`default-src 'none'; img-src data:; style-src 'sha256-...'; base-uri 'none'; form-action 'none'`). Contains no external scripts, remote web fonts, or tracking links.
- **Exit codes**:
  - `0`: HTML exported successfully.
  - `2`: Invalid arguments or invalid report schema.
  - `4`: Missing or unreadable report.

### 5. Replay

Re-execute document extraction using the parameters recorded in an existing report:

```bash
inkflip replay REPORT --profile ID --out FILE [options]
```

#### Options:
- `--source FILE`: Path to original PDF source. Optional only if the original report embeds the source PDF.
- `--profile ID`: (Required) Execution profile for replay.
- `--out FILE`: (Required) Output path for the newly generated replay report.
- `--replace-output`: Allow overwriting an existing file.

- **Integrity**: Refuses mismatched source bytes/SHA-256 against `document.sha256`. Links origin via `export.origin_report_id`.
- **Exit codes**:
  - `0`: Replay completed successfully.
  - `2`: Missing source, hash mismatch, or invalid input report.
  - `4`: Source file or report unreadable.

### 6. Compare Readers

Run two allowlisted readers against the same document and produce side-by-side reports and comparison records:

```bash
inkflip compare-readers FILE --readers A,B --out DIR [options]
```

- **Arguments**: `--readers` must specify exactly two comma-separated reader IDs (e.g. `pdfium,pypdf`).
- **Output Directory**: Creates:
  - `report_A.inkflip.json`: Individual report for reader A.
  - `report_B.inkflip.json`: Individual report for reader B.
  - `comparison.json`: Sealed comparison artifact conforming to `inkflip.schema.json`.
  - `comparison.html`: Summary HTML view.
- **Exit codes**: `0` on completion; differences are classified as `changed` or `unchanged` in the artifacts.

### 7. Models Prepare

Validate and verify local machine-learning / OCR model cache manifests:

```bash
inkflip models prepare --manifest MANIFEST
```

- **Security**: Local-only validation; network setup is user-authorized only and never triggered silently during document inspection.

---

## Exit Codes and Precedence

Exit code semantics are strictly enforced:

| Code | Meaning | Examples |
|---|---|---|
| `0` | Success | Command completed under its declared policy. Reading differences are informational. |
| `2` | Invalid arguments / Contract error | Unknown reader, duplicate/out-of-range pages, invalid region, overwriting without `--replace-output`, schema violation, hash mismatch, remote URL rejected. |
| `3` | Partial run / Unsupported capability | Missing OCR language model (e.g. Tesseract `eng.traineddata`), unsupported feature. |
| `4` | Runtime / Read failure | File not found, non-PDF file header, encrypted/password-protected document, corrupt stream. |
| `5` | Policy failure | Declared acceptance rule failure or `--fail-on changed` regression. |
| `6` | Incomparable runs | Attempting to compare runs with differing source documents or incompatible schemas. |
| `130` | User cancellation | SIGINT / `KeyboardInterrupt`. |

## File Lifecycle Invariants

1. **Atomic sibling writes**: Reports and HTML files are written to unique temporary sibling files and renamed atomically into place.
2. **No silent overwrites**: Existing destination files are never overwritten unless `--replace-output` is explicitly passed.
3. **Local-first & privacy**: No external network requests, analytics, or telemetry. File paths must be local filesystem paths (HTTP/HTTPS URLs are rejected).
