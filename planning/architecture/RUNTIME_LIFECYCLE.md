# Browser and native lifecycle

Canonical limits: [settings.json](../config/settings.json). State labels are shared with [copy](../product/copy.json). These are runtime safety/usability limits, not development effort budgets.

## State machine

```text
idle -> validating_file -> loading_metadata -> selecting
selecting -> preparing_assets -> running
selecting -> running                     (all needed assets already available)
running -> complete | partial | failed | cancelled
terminal -> selecting                   (new explicit run/retry on same file)
any -> clearing -> idle
any file state -> clearing -> validating_file (replacement)
```

`running` has a finite check DAG: metadata → selected native extraction/render → optional OCR → alignment. Extraction and a bounded render can proceed independently; OCR cannot start before its raster and assets exist. Each check state is queued/running/terminal; terminal values are completed/unsupported/timeout/cancelled/failed/skipped. The immutable plan enumerates intended checks before work starts. Queued work cancelled by the user receives a terminal cancelled result. A completed read returning no occurrences is not a skipped read.

Terminal run status: complete only when every planned check completed; cancelled when user cancellation was requested; failed when no check completed and at least one failed/timed out; otherwise partial when any requested work is not completed. Reports contain partial evidence regardless of overall state. Full document coverage is separately computed from selected pages and page count; complete on one selected page is never “document clear”.

## Identity and stale-result prevention

Maintain monotonically increasing `generation` in the coordinator. Increment it **before** closing old handles, terminating workers or beginning replacement. Every worker message includes generation, document hash, run key, job ID and strictly increasing sequence number. Reject a message unless all five match the active registry and sequence exceeds last accepted. Terminal jobs reject late chunks. A worker's local filename is never identity.

Cancellation first updates visible UI, then marks pending work cancelled, cancels RenderTasks, aborts fetches, terminates OCR/alignment workers, destroys PDF document/worker handles, and invalidates message listeners. Preserve only already validated completed-check evidence. Show “Cancelled — completed results kept.” At the 500 ms termination target, the old generation is unreachable from presentation even if browser cleanup lags. The application cannot promise the browser instantly releases every native allocation.

## Backpressure and progress

At most one active render, one OCR worker and two live raster buffers. At most 256 occurrences per message and two unacknowledged chunks. Transfer ArrayBuffers where possible; do not repeatedly clone full-page RGBA data. The receiving worker must prove document and raster identity before using a transferred slot. Acknowledgment is a capacity signal, not a success finding. Oversized output terminates that check as resource_limit with previously completed unrelated checks retained.

Progress is stage-specific: assets bytes received/declared length; pages selected/rendered; OCR engine progress with an indeterminate state when the engine gives no denominator; comparison regions handled. Do not display a unified exact percentage from mixed units. Announce stage transitions politely, not every OCR progress tick. The displayed selected-page total never silently increases after a user starts a run.

## Asset and cache states

`not_prepared`, `downloading`, `verifying`, `ready_memory`, `ready_cached`, `failed_integrity`, `unavailable_offline` are distinct. The English model's exact bytes/hash are in the asset manifest. Downloads are static same-origin requests with no document identifiers. Verify before committing a model to cache. A mismatched cache entry is deleted and reported; retry requires a fresh download. No background model download on a landing-page view.

Static model caching may survive Clear. Document bytes, crops, findings and filenames do not enter IndexedDB, CacheStorage, localStorage or service-worker caches. There is a separate “Remove downloaded OCR data” action. File replacement terminates OCR so its image memory does not persist into another file; same-file runs may reuse a healthy initialized model. Clear nulls state, revokes all owned object URLs, disconnects observers, removes canvases and calls close/destroy on owned resources. Do not claim forensic secure erasure.

## Failure taxonomy and retry

Encrypted input → unsupported, no network password prompt. Malformed parser failure → failed read with native text/render states independent. Missing model → model unavailable, not unreadable page. OCR completion with poor/no text → `unreadable_pixels` informational, not model crash. Unsupported clipping/structural inspection → explicit unsupported check. A page exceeding the raster pixel cap is downsampled only after recording actual scale and user-visible warning; impossible geometry is rejected.

Allow one transient retry for initialization/worker crash, only with a fresh worker and remaining run budget. No automatic retry on user cancellation, encrypted input, unsupported feature or known integrity failure. A user-requested rerun is a new execution and run plan if settings changed. Completed outputs are never retroactively overwritten by a retry with different settings; they become another reading.

## Native supervision

The parent maintains queued/running/terminal records and writes each validated per-file report to a temporary sibling file, fsyncs, then atomically renames. On crash, retain the durable tail and resume only missing/failed selected jobs on explicit `--resume`; successful files are checked by hash/config and never rerun silently. One task failing does not poison the whole corpus.

Each child owns a process group, private scratch directory, immutable source bytes and fixed output cap. Parent wall-clock deadline terminates the process group, waits, then force-kills if necessary; a stuck native call cannot rely only on SIGALRM. Limit subprocess stdout/stderr; errors disclose type and safe reason, not source text or arbitrary paths. Default native jobs=1; more jobs require explicit CPU/RAM-aware admission. The CLI is not a hosted worker fleet.

Source discipline: [legacy batch](../research/SOURCES.md#s06), [watchdog tests](../research/SOURCES.md#s17), [PDFium threading](../research/SOURCES.md#s26). The own implementation is new and must be fault-injected, not merely described as robust.
