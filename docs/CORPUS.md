# Inkflip Corpus Execution, Manifest & Resume

The Inkflip corpus execution engine provides supervised, reproducible batch inspection across curated PDF corpora under strict containment and sandboxing guarantees.

## Corpus Manifest

A corpus manifest is a sealed JSON file conforming to `inkflip.schema.json` under the `CorpusManifest` definition.

### Manifest Structure

```json
{
  "kind": "corpus_manifest",
  "schema_version": "1.0.0",
  "source_root_policy": "explicit_local_root_no_symlinks",
  "split": "public_demo",
  "entries": [
    {
      "key": "doc-001",
      "source_path": "finance/quarterly_report.pdf",
      "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      "group_id": "earnings-reports",
      "pages": [0, 1, 2],
      "ocr_pages": [1]
    }
  ]
}
```

### Manifest Fields
- `kind`: Must be `"corpus_manifest"`.
- `schema_version`: Must be semantic version (e.g. `"1.0.0"`).
- `source_root_policy`: Must be `"explicit_local_root_no_symlinks"`. Symlinks in the root path or entries are strictly forbidden.
- `split`: One of `development`, `public_demo`, `evaluation`, or `permissioned`.
- `entries`: Array of distinct `CorpusEntry` items.
  - `key`: Unique document identifier matching `^[a-z0-9_.-]{1,128}$`. Keys remain distinct even if filenames or source paths collide.
  - `source_path`: Relative POSIX path from `source_root`. Cannot be absolute or contain directory traversal (`..`).
  - `sha256`: Hexadecimal SHA-256 digest of source PDF bytes. Verified prior to execution.
  - `group_id`: Optional group classification matching `^[a-z][a-z0-9_-]{0,95}$`.
  - `pages`: 0-based list of page indices to process (non-negative integers).
  - `ocr_pages`: Optional 0-based subset of pages for OCR.

## Root Containment & Security Invariants

The corpus runner enforces strict isolation and containment boundaries:
1. **Source Root Containment**:
   - `source_root` cannot be a symlink or contain symlinked path components.
   - All entry source paths must resolve strictly within the designated `source_root`.
   - Any path escaping the source root or traversing via `..` raises `ContainmentError` immediately.
2. **Cryptographic Integrity**:
   - Every source PDF is hashed with SHA-256 before processing.
   - Any byte disparity against the manifest's declared `sha256` raises `IntegrityError`.
3. **Subprocess Isolation**:
   - Each job runs in an isolated subprocess managed by `inkflip.runtime.Supervisor`.
   - Disposable per-job scratch directories prevent state pollution across documents.

## CLI Usage

```bash
uv run --project native python -m inkflip.cli corpus run \
  --manifest /path/to/manifest.json \
  --source-root /path/to/corpus/pdfs \
  --profile native \
  --out /path/to/output_dir \
  [--resume] \
  [--jobs 1]
```

### Arguments:
- `--manifest PATH`: Path to validated `corpus_manifest.json`.
- `--source-root DIR`: Root directory containing referenced corpus PDF files.
- `--profile PROFILE`: Execution profile ID (`native`, `desktop`, `mobile`).
- `--out DIR`: Destination directory for output artifacts (`index.json`, `journal.jsonl`, `<key>.inkflip.json`).
- `--resume`: Optional flag to resume an incomplete or interrupted run. Skips already completed jobs whose configuration digests match.
- `--jobs N`: Concurrency level (default: 1). Multi-job concurrency requires explicit CPU and RAM admission.

## Output Artifacts

Upon execution, the output directory contains:

1. **Per-Document Reports** (`<key>.inkflip.json`):
   - Atomic written, schema-valid Inkflip evidence reports for each processed document.
   - Preserves deterministic hashes and evidence trees.
2. **Structured Journal** (`journal.jsonl`):
   - Append-only NDJSON log recording run events (`run_started`, `job_started`, `job_terminal`, `run_terminal`).
   - Monotonically increasing sequence numbers, UTC timestamps, and exact attempt counts.
3. **Run Index** (`index.json`):
   - Consolidated index of all planned jobs, statuses (`completed`, `failed`, `skipped`), run metadata, limits, and runtime platform.
   - Deterministic alphabetical key ordering.

## Crash Resilience & Validated Resume

- **Failure Isolation**: A crash, timeout, or abnormal termination in one document never deletes, corrupts, or invalidates completed reports of other documents.
- **Atomic Persistence**: Reports are staged in temp files and atomically renamed upon successful completion.
- **Validated Resume**:
  - When `--resume` is supplied, `run_corpus` checks the existing `index.json`.
  - For each completed job, it validates that the output report exists and that the job configuration digest matches.
  - Completed jobs are marked `skipped` without re-running or mutating existing report bytes.
  - Only interrupted or failed jobs are retried.
