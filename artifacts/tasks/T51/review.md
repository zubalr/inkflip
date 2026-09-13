# T51 independent review — tests/gates/g2.spec.ts

Reviewer: devin-integrator (integrator-performed; three dedicated reviewer
subagent dispatches were cancelled at the environment boundary — recorded
here for provenance). Authoring was delegated to a bounded subagent; this
review evaluates the artifact, not the author. Date: 2026-09-13. Base
spec: 4944870; merged 68b4c60; re-verified on 8b51263 (6/6 twice).

## Verdict: ACCEPT

## What was checked

1. **Real build/server/fixtures, no mocks.** beforeAll runs the pinned
   Vite production build into a task-private dist (index.html + the real
   src/offline/preview.html mount); a plain static server with the
   planned deployment headers (CSP included) serves it; an independent
   server-side access log is the ground truth. File inputs receive real
   bytes; IndexedDB/CacheStorage are real; no fetch is rerouted or
   stubbed. Verified by reading the harness + each leg.

2. **Six legs cover the frozen G2 criteria:**
   - L1: all six gallery examples — manifest.json + report.json + source
     PDF fetched same-origin and digest-verified end to end
     (reportSha === cardSha === pdfSha, finding counts matched); one card
     opened through the real UI (detail → open → import gate → viewer);
     second example deep-linked via #/workspace?example=.
   - L2: own-file journey — real F01 fixture through the real input,
     canonical region around the real $1,000 token, full
     native_text+render+OCR+alignment to a sealed report, then viewer
     controls (aria-current finding select, zoom).
   - L3: ambiguity UI — all three identical-text candidates listed, none
     pre-picked; candidate pick sticks (aria-pressed + selected
     highlight, never first-match); page-level finding keeps its notice;
     keyboard cycling.
   - L4: import/export privacy — sealed contract example through the real
     report input; privacy preview with every opt-in off; deselection
     excludes + discloses; real JSON/HTML downloads; honest replay state.
   - L5: explicit offline — plain loads register no SW and create no
     caches; explicit prepare → manifest-bound generation, ready +
     controlled; offline reload serves shell; full own-file run
     (worker-served model/worker/wasm) completes; server access log shows
     literally zero requests (strict slice assertion).
   - L6: 360px mobile — low-memory profile (OCR consent, on-demand
     preview, capped select-all, windowed list), stacked compare panes,
     no horizontal overflow.

3. **Fail-closed.** Assertions are count/status/digest equality against
   server-observed truth — no tautologies found. Zero-request offline
   assertion slices the server's own access log (app cannot fake it).

4. **Scope.** Spec adds only tests/gates/g2.spec.ts; no shared-file or
   product edits. planning/ untouched.

## Notes (non-blocking)

- The offline leg's zero-request window has no explicit service-worker
  update-check flush (cache.spec.ts needed one under worker-pollution
  timing). Passed twice at gate level; if it ever flakes with a bare
  GET /sw.js server hit, the same narrow fix applies.
- Leg timeouts (240s prepare, 180s run) are generous but bounded;
  consistent with the suite's loaded-Mac profile.

## Verification performed

- Read the full spec + gate wiring (scripts/gate.py, gates.json, T51.md).
- G2 executed twice by the integrator on merged heads: 6/6 on 68b4c60
  and 6/6 on 8b51263 (post-NODE_ENV-pin).
