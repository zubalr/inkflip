# T25 review — explicit offline static/model cache lifecycle

Reviewer: independent subagent (74678d86), read-only, no exec.
Implementation commits: 8bc81eb (code+spec+commands.log),
2c5ce7d (review round), fae414c (rebound run record).
Run evidence: run.json bound to 2c5ce7d — 8/8 via
`bun run test:privacy -- tests/privacy/cache.spec.ts`.

## Verdict: APPROVE-WITH-NOTES → resolved APPROVE

The reviewer's single gate (Finding 1, run-record provenance) resolved
as cosmetic: `bunx playwright test --list` on the committed files
reports exactly the recorded line numbers (cache.spec.ts
321/412/568/645; local.spec.ts 829/1218/1293/1426) — Playwright reports
transformed-source call sites, not literal `test(` declaration lines.
Same disposition as the T23 provenance question. The recorded run
faithfully executed the committed files; no spec drift, no scope leak
(`git diff c696948..HEAD` touches only owned paths + T25 artifacts).

## Findings and dispositions

- F1 [major→resolved] run.json line-map vs committed file — cosmetic
  (transformed call sites); verified via --list on committed files.
- F2 [minor→fixed 2c5ce7d] read paths (`readIndex`, `readManifestRecord`,
  `status`, `serveFromActive`) created empty owned caches via
  `caches.open` — now guarded by `caches.has`; remove semantics stay
  truthful.
- F3 [minor→fixed 2c5ce7d] `registerServiceWorker` could report
  `activated` for a worker still installing after the 15s fallback —
  timeout now returns register-failed unless state is activated.
- F4 [minor→fixed 2c5ce7d] manifest entries resolving cross-origin
  were fetched during prepare — now failed closed as
  `cross_origin_path`.
- F5 [minor→fixed 2c5ce7d] `stored` reply was a path array on failure
  vs count on success — normalized to a count.
- F6 [nit→fixed 2c5ce7d] stored responses no longer carry stale
  content-encoding/content-length for decoded bodies.
- F7–F8 [nit→accepted] orphan-prepare window (>240s) and crash-between-
  index-flip-and-sweep window — bounded, final state stays honest.
- F9 [nit→resolved] receipt.json added alongside this file.
- F10–F12 [nit→noted] tests/privacy/README.md stale ("no service
  worker ships") — out of T25 scope, flagged to docs owner; manifest
  drift vectors verified inert today; `/sw.js` Cache-Control is a
  deployment-owner consideration.

## Criteria evidence

- Cold/offline without model reports unavailable — test leg
  "cold offline" (spec): zero caches on load, register→not_prepared,
  offline prepare fails closed, ocrPrepareProbe → typed
  unavailable_offline, own-file offer → rejected event + visible error.
- Prepared offline own-file works without requests — "prepared offline"
  leg: real button click → ready+controlled+entries>100, offline reload
  through the SW, own-file run completes all four capabilities, server
  access log confirms zero requests.
- Model update cannot reuse wrong hash — store-time integrity_mismatch
  (new generation refused, old intact) + serve-time eviction via
  inkflip:cache-evicted → degraded.
- Clear/remove without forensic promise — real clear-file teardown
  events (pdfjs-document, document-object-url, probe-worker), remove
  deletes owned caches only, OFFLINE_LIMITATIONS asserted in result and
  DOM, forbidden-claims scan clean.

## Invariant check

No document/report/crop/filename/hash persists through this lifecycle
(canary exclusions asserted in every census); nothing registers or
caches on load; blob:/data:/cross-origin/unlisted paths are never
served or stored; remove is scoped, explicit, and non-forensic.
