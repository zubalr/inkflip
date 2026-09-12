# Independent Peer Review — T24 (approved)

**Reviewer:** devin-review-t24 (SWE-2 subagent, independent — did not write this code)
**Candidate reviewed:** `fd649bb` on `work/devin/t24` (implementation `2300cb62415a5fc40957b15f6bb7d9c971e3010a`, base `c12e680`)
**Date:** 2026-09-12 · **Verdict: approved**

## Per-criterion verdicts — all PASS

- Controlled oversized/truncated/HTML/SVG/polyglot/prototype/path inputs fail before dangerous allocation: pipeline order verified size → sniff → loadsStrict → bounds → prototype audit → validate → asset audit; archive/polyglot rejected pre-decode; no TOCTOU (pure functions).
- Bounded fuzz receipts: 172 accepted / 828 rejected / 0 crashes / 0 egress / 0 unexpected reproduced exactly; `stream_sha256 c779dbd9…` byte-identical to committed receipt; deterministic on seeds 1234/42/7.
- HTML export opens script-free: guard holds for the shipped pipeline (findings F1–F2 tracked as follow-up).
- No archive decompression surface: only inflate call is bounded PNG IDAT; zTXt/iCCP never inflated.

## Adversarial substantiation (91-check probe + targeted runs)

- PNG codec cross-validated against node:zlib and an INDEPENDENT Adam7/filter encoder: pixel-exact on all color types/bit depths/filters; caps enforced at IHDR before allocation; CRC verified; bombs/truncated/polyglot rejected; re-encode bounded, ancillary-free.
- Inflate: 1200 valid streams byte-identical to zlib; 200 mutations 0 crashes/0 false accepts.
- HTML guard: on*/srcdoc/formaction/data/action/ping/manifest forbidden; entity-encoded javascript: caught; svg/math/template/noscript forbidden; CSP-substring gap noted below.
- Prototype keys rejected at any depth; parser materializes __proto__ via defineProperty — pollution impossible.
- Egress tripwires armed (fetch/WebSocket/XHR/net/tls/dgram/spawn) all throw EGRESS — verified firing.
- Reruns: node 79/79; task_acceptance T24 exit 0 failures=[]; fuzz tallies match receipt incl. SOURCE×3.
- Scope: only allowed paths + artifacts; planning/ untouched; no lockfile/dep changes; receipt cites only task-local paths.

## Findings (non-blocking; tracked for T16/hardening follow-up)

- F1 MEDIUM-LOW: CSP validated by substring — `default-src 'none' *` passes while browsers drop 'none'. Unreachable through the fixed-CSP double today; token-level directive validation needed before T16 exporter reuses the guard (html_guard.ts:120-125).
- F2 LOW: FORBIDDEN_CSS literal-substring misses escapes/comments (`@\69mport`, `url/**/`), `vbscript:` absent, unclosed <style> unscanned — all CSP-backstopped today.
- F3 LOW/INFO: PNG decoder tolerates spec violations (2nd IHDR ignored, PLTE after IDAT, ancillary-split IDAT) — self-consistent, no boundary impact.
- F4 INFO: empty deflate distance table false-rejects (zlib accepts) — safe direction.
- F5 nits: key-length bound, data_base64 exemption by key name, surrogate mapping asymmetry, checkHashes=false footgun, prefix-only src check.
- F6 process: packages/reports scaffold not yet wired into workspace exports (integration reconciliation); html_export_double raw-fallback dead-code footgun.

## Verdict: approved

All acceptance criteria substantiated under independent adversarial probing; every claimed count and the fuzz stream hash reproduced byte-exact; scope/evidence clean.
