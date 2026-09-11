# Local CLI and regression command contract

Executable name **`inkflip`**, initial CLI major version 1. All commands below are required implementation contracts, not a claim that this planning package installs a finished CLI. Bootstrap creates the command harness; T29–T35 implement these behaviors. Source and report files are never automatically uploaded.

## Commands

| Command | Required arguments / defaults | Output |
|---|---|---|
| `inkflip readers list --json` | None; installed allowlist only | Reader capabilities, exact versions/builds/model availability |
| `inkflip inspect FILE --out REPORT` | `--reader` repeatable, default `pdfium`; `--pages` default `1`; `--ocr-pages` default none; `--region x0,y0,x1,y1` optional with one page; `--profile` default native-default | One validated `.inkflip.json` evidence report |
| `inkflip compare-readers FILE --readers A,B --out DIR` | Exactly two installed reader IDs; explicit pages/default1 and optional OCR pages | Two reports plus comparison JSON and HTML |
| `inkflip models prepare --manifest FILE` | Explicit allowlisted manifest; user-authorized network setup only | Verified model cache, no document processing |
| `inkflip corpus run --manifest FILE --source-root DIR --profile ID --out DIR` | `--jobs 1`, `--resume` false; OCR only declared selected pages; paths resolve under source-root with no symlinks | Atomic per-file reports plus `index.json`, failures retained |
| `inkflip baseline create --run DIR --rules FILE --out FILE --approved-by LABEL --rationale TEXT` | No implicit overwrite; rejects incomplete invalid run unless explicit diagnostic-only baseline option | Immutable baseline with run/corpus/profile/rule identities |
| `inkflip compare LEFT RIGHT --out DIR` | Stored report, baseline or corpus paths; `--rules FILE` optional; `--mode reader_upgrade` default; `--fail-on changed` optional | Comparison JSON, human HTML and per-file links |
| `inkflip report REPORT --format html --out FILE` | JSON validated first; HTML only output conversion | Script-free portable HTML |
| `inkflip replay REPORT --source FILE --profile ID --out FILE` | Source optional only if report includes matching original; installed environment required | New actual report; original report immutable |
| `inkflip validate REPORT` | One known JSON format | Validation summary; no PDF processing or runtime installation |

Arguments use one-based page numbers and inclusive ranges `1,3-5`; reject duplicates/out-of-range entries with an explicit message before execution. The internal schema uses zero-based indices. `--region` is canonical unrotated physical points, not UI CSS coordinates; region workflow prints the selected region and padding. `--pages all` is allowed only under the native maximum page count; it does not imply OCR all pages. OCR requires explicit `--ocr-pages`, limited to 20 per run and a finite pixel/time budget. One selected region requires exactly one selected page.

`--reader tesseract` without a raster source uses PDFium and records that dependency. `compare-readers` between PDFium and pypdf preserves pypdf page-only geometry. No environment or reader choice can be read from an untrusted report as an executable path. File paths are local arguments only; no HTTP URL source support.

## Exit codes and precedence

0: requested command completed under its declared policy; reading differences are informational by default. 2: invalid arguments/configuration or invalid imported contract. 3: partial run or unsupported requested work with retained evidence. 4: no successful result due to runtime/read failure. 5: a declared acceptance rule or explicitly requested `--fail-on changed` failed. 6: incomparable runs. 130: user cancellation. Missing model is a partial/runtime capability failure, never unchanged.

For a corpus comparison, report all categories first. Exit precedence is cancellation, invalid input, runtime failure with no usable comparison, policy failure, incomparable, partial, success. Explicit policy `fail_on_error:true` or `fail_on_coverage_loss:true` produces exit5 after valid comparison construction, even when some files errored; the JSON still retains the underlying error status. Do not mask a malformed comparison input as a regression. Shell pipelines must preserve these exit codes.

## File lifecycle

No output overwrite unless `--replace-output` is explicit; baseline creation never supports that flag. Output directory must not overlap source directory. Corpus entries use controlled keys and source SHA-256; filenames never deduplicate content. The parent reads an explicit source root, rejects symlinks/path traversal, validates byte length/hash, and passes only assigned data to the child.

Per-file reports are written via exclusive temporary siblings then atomic rename. `index.json` identifies each intended file and terminal state, even if no PDF page was readable. It is a run index, not an ingestion database. Resume checks source/profile/algorithm identities and preserves successful outputs byte-for-byte; changed identities require a new run directory. A failed child receives one bounded retry only where the configured policy allows it. Never synthesize an apparently plausible extraction to fill a row.

Large native raw output may exceed the portable browser import profile. Keep complete local raw records in the corpus directory, then produce a selected portable projection with explicit omissions; do not advertise a too-large bundle as browser-reopenable. `report` and `compare` explain missing source/assets instead of resolving report-controlled paths.

## Two incompatible versions

T33 provides `scripts/install_reader_profile.py`, an explicit install-time helper. It creates isolated environments for a fixed allowlisted reader family/version and writes an owner-controlled profile with interpreter identity and artifact digest. It does not take a shell command string and is never called from `inspect` or an imported report.

For example, pypdf 5.9.0 (the exploratory version actually available here) and 6.18.0 (selected current release) run in separate venvs. A small bundled stdlib+pypdf worker wrapper is executed by each environment's interpreter; the full application's pinned dependencies are not installed into both incompatible venvs. Parent supervision wraps its canonical output. PDF.js versions likewise live in separate Node workspaces with their own lockfiles and fixed wrapper. Compare reports afterward, never load two incompatible implementations into a single process.

```sh
python scripts/install_reader_profile.py --name before --reader pypdf --version 5.9.0
python scripts/install_reader_profile.py --name after --reader pypdf --version 6.18.0
inkflip corpus run --manifest planning/contracts/examples/valid/corpus.json \
  --source-root planning/fixtures --profile before --out runs/before
inkflip corpus run --manifest planning/contracts/examples/valid/corpus.json \
  --source-root planning/fixtures --profile after --out runs/after
inkflip compare runs/before runs/after --rules quality/upgrade-rules.json --out comparisons/upgrade
```

The two install commands may use the network only because the operator explicitly invoked setup. Execution runs with network disabled. Exact resolved artifacts, distribution notices and host architecture are recorded. A profile name alone is not reproducibility.

## Baseline and acceptance rule meaning

`expected_text` means a known fixture expectation for an explicitly scoped occurrence; it is not automatically the visible truth. `stable_reading` means the maintainer chooses to disallow a change from an approved baseline in that scope; a violation is a policy regression, even if a new reader might be better. `required_coverage` prevents skip-to-green. `max_geometry_delta` is valid only between comparable geometry precision/coordinate versions. `expected_occurrence_count` catches duplicate loss but does not infer missing document truth.

When no rule applies, show changed, unchanged, unsupported, errored or incomparable. An approval action creates a new baseline file with rationale and real reviewer label, never edits the old baseline to hide failure. A negative experiment result or changed output can be valuable without being merged.

## Local/CI upgrade example

`deployment/examples/reader-upgrade.sh` is a provider-independent shell sequence to run after T33 is implemented. It prepares explicit profiles, executes two offline runs, validates outputs and compares under stated policy. `quality/upgrade-rules.json` must be generated from the approved corpus by T34, with required coverage and stable-reading rules. Tests deliberately mutate one candidate reading and delete one check, verify exit5, then verify that baseline bytes remain unchanged. No hosted CI account or upload is needed.
