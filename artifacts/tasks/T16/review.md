# T16 independent review — portable JSON + escaped HTML export foundation

- **Reviewer:** independent read-only reviewer (Devin Local subagent, coordinator-requested)
- **Candidate:** `35f524b13a093e106301c344933919a079321da3` (impl `ff91745`, tests+evidence HEAD; worker evidence `335c2cb` on `work/devin/t16`)
- **Review branch/checkout:** `review/devin/t16` @ `worktrees/review-devin-t16`
- **Verdict: approved** — all six acceptance criteria independently verified; findings are low-severity test-effectiveness / disclosure / evidence-precision items, none blocking.

## Reproduced commands (this worktree, real counts)

| Command | Worker claim | Reproduced |
|---|---|---|
| `node --test tests/reports/export.test.mjs` | 15/15 pass, exit 0 | **15/15 pass, 0 fail/skip, exit 0** |
| `python3 scripts/task_acceptance.py task T16` | re-runs registered command, 15/15 | commands_run=1, failures=[], 15/15, exit 0 |
| `bun x --no-install tsc -b packages/reports` | exit 0 | exit 0 (composite decl. build incl. `export/**/*.ts`) |
| `bun x --no-install oxlint <touched dirs>` | 0 warnings/errors | 0 warnings, 0 errors, 96 rules, 10 files |
| `bun x --no-install oxfmt --check <touched dirs>` | formatted | all matched files correctly formatted |
| `bun x --no-install tsc -p apps/web/tsconfig.json --noEmit` | 467 errors, all baseline | **466** total; measured **397** without `features/export` (moved dir out), +69 in feature (67× TS7026, 2× TS7016 — all missing-React-typings noise). Zero non-baseline diagnostics in feature: confirmed. Worker's total/baseline figures off by one/~70 (F5). |
| `python3 scripts/task_acceptance.py run verify` | 49+2+65 + self-check 16 | 49 OK, 2 OK, 65 OK, self-check 16 commands — no regressions |

## Criterion-by-criterion audit

**1. Preview equals decoded contents — PASS.** `buildExportPreview` measures the sealed projected `Report` object (preview.ts:98-209): counts/bytes computed from `report.*`, asset bytes from actually decoding each `data_base64` payload, `included`/`omissions` copied from `export.*` of the same object `serializeReportJson`/`renderReportHtml` consume. Test decodes via `loadsStrict` and re-verifies every figure against the decoded artifact. `htmlBytes` is `null` unless the caller supplies the rendered document (controller omits it — panel doesn't display it).

**2. Inclusion allowlist — PASS.** `ExportRequest` is inclusion-only: unknown request keys ignored (probed `{evilRequestField:true}` → ignored); default profile keeps `selected_text/crops/document_hash/settings/coverage`, drops `source_pdf/filename/annotations/page_renders`. Opt-ins require literal `true`/explicit values (`annotations:"yes"` stays off). Unknown selection ids fail `SELECTION` closed; bad `scope`/`sourcePdf` types fail `SCHEMA`/`TYPE`/`SOURCE`. Unlisted members on kept entities are not stripped — they trip the closed schema at `validate(projected)` → fail closed (probed `evil_extra` on an occurrence → SCHEMA throw). `export.included` is derived from projected content, never the request (selection.ts:163-188).

**3. Raw text/geometry/coverage survive — PASS.** Kept occurrences are carried whole via `structuredClone`+filter — `raw_text`, `normalized_text`, `normalization_map`, `geometry` (precision/polygon/basis/transform_ids), `engine_score`, `raw_source_locator` verbatim; recompute-vs-verbatim checked by test (normalize() equality + deepEqual) and by `validate`'s NORMALIZATION rule (raw↔map consistency enforced, so tampering fails). `produced_occurrence_count` preserved; `retained_occurrence_ids` pruned to kept set. Plan scope (`selected_pages`, `checks`, `budget`, versions), readers/settings/model_hashes, referenced transforms and pages preserved; regions pruned only when unreferenced, disclosed.

**4. Script-like strings escaped — PASS.** `renderReportHtml` validates the report then runs `assertScriptFreeHtml` on final bytes (html.ts:304-362). Every report-controlled string goes through `escapeHtml`/`text()` (NUL→U+FFFD); report strings reach only text nodes/`<bdi>`, never attribute contexts (dynamic attributes are app constants + base64). Independent adversarial run: 9 payloads (`</script><script>`, `"/><img onerror>`, `<style>` breakout, `data:text/html`, meta-refresh, math-unicode, NUL) × 15 string slots → 0 unescaped leaks, 0 active markup, guard enforced; `sanitizePng` re-encode (never stored bytes) confirmed byte-unequal to a hostile-chunk payload by test. CSP: `styleHash()` derives `style-src 'sha256-…'` from the same `EXPORT_CSS` constant the `<style>` block emits; the guard independently re-hashes the stylesheet body and compares — drift impossible. `default-src/script-src/connect-src/object-src 'none'`, `img-src data:` with strict PNG data-URL decode in the guard.

**5. Determinism — PASS.** Identical inputs → byte-identical JSON+HTML (test + reproduced). `MEMBER_ORDER`/`CHILD_DEF` verified complete against `planning/contracts/inkflip.schema.json` property order for all 21 object shapes; all non-CHILD_DEF members are primitive/tuple arrays — canonical output is genuinely input-order-independent (verified under real key reversal and interleave permutations; see F1 on the committed test). Excluded run-timing fields — `report_id`, `execution.execution_id`, `started_at`, `duration_ms` — are exactly what `reportDigest` excludes (core.ts:558-568), documented in serialize.ts header; `run_key` is content-derived and stable; `exportFileName` = `inkflip-{mode}-{report_id[:12]}`, no user data.

**6. Source PDF opt-in — PASS.** Default/`null`: no `source_pdf` asset, `source_asset_id` nulled, "Original PDF excluded." recorded. `Uint8Array` opt-in bound to `document.sha256`/`byte_length` (mismatch/tamper → `SOURCE`); `'carry'` reuses only an embedded `source_pdf` whose payload re-verifies; `'carry'` with unusable bytes → `requestedSourceMissing` + evidence-only. HTML embeds `image/png` only — no `data:application/pdf`, verified by test.

**7. Missing bytes → evidence-only — PASS.** `usablePayload` (decode+length+sha256) gates every asset; failures → `missingAssetIds` + omissions line; mode can only be `evidence`/`diagnostic` without a verified source asset; orphaned `source_asset_id` links nulled + `unlinkedOccurrenceIds` disclosed. Reproduced.

**8. Web feature — PASS.** `ExportEngine` is a structural port mirroring `packages/reports/export` member-for-member (project/preview/serializeJson/renderHtml/fileName) — same decoupling as `state/store.ts` (`StoreHost`), documented rationale identical (apps/web tsconfig cannot resolve cross-package `.ts`). Confirmed **not mounted**: `App.tsx` is the bootstrap scaffold, no `features/export` import anywhere; mounting belongs to app composition (T13) — appropriate for this scope. CSS module uses only central tokens (all 24 vars verified in `tokens.css`); Button/Notice prop usage matches existing signatures.

**9. Scope — PASS with adjudication.** `git diff f83a2d4...HEAD` = 14 files: 6 under `packages/reports/export/`, 5 under `apps/web/src/features/export/`, 1 test — all owned — plus `packages/reports/package.json` (`+"./export"` subpath only) and `packages/reports/tsconfig.json` (`+"export/**/*.ts"` include only). Both flagged by the worker, purely additive, required for `tsc -b` compilation and workspace importability, alter no existing entry/behavior. **Adjudicated: sanctioned minimal wiring, stands.** No lockfile/routing/planning/golden/other-module changes; `planning/` byte-identical (verify suite's snapshot test passes).

## Findings

- **F1 — low — tests/reports/export.test.mjs:533-545.** `scramble` uses `Object.keys(v).sort(() => 0.5)`; a constant comparator does **not** permute keys under V8 (verified empirically, Node 26: order preserved for 8- and 16-key objects). The "byte-stable under member reordering" test is therefore **vacuous** — it serializes an identically-ordered clone twice. Implementation independently proven byte-stable under real reversal/interleave permutations, so this is a test-effectiveness defect, not a code defect. Recommend a real deterministic permutation.
- **F2 — low — packages/reports/export/selection.ts:392-418.** Omission disclosure is asymmetric: excluded `page_render`s get "Full-page images excluded." but dropped `crop`s get **no** omission line (verified: `{crops:"none", occurrences:"none"}` drops `a_crop` with zero crop-specific line); explicitly deselected findings likewise get no line (`omittedFindingIds` counts only kept-but-unsupported). `export.included` and preview counts still disclose honestly; the `omissions` channel is incomplete for these categories.
- **F3 — low — packages/reports/export/selection.ts:57-63.** `OccurrenceSelection` doc claims cited occurrences are unioned in "in every case" — false for `"none"` (nothing is unioned; unsupported findings are omitted+disclosed instead). Semantics are correct; the comment overstates.
- **F4 — low — packages/reports/export/preview.ts:159-203.** `withinLimits` enforces `jsonBytes`/`assetCount`/`decodedAssetBytes` but the exposed `limits.pngPixels` is **never checked** (nor per-asset bytes, PNG edge, or string-length bounds — no PNG decode in preview). A bundle violating the declared pixel limit reports `withinLimits:true` yet the T24 import gate would reject it; the "explain, never silently reduce" promise silently fails for that class. Edge case.
- **F5 — low — artifacts evidence.** commands.log/receipt claim "467 errors, all baseline"; measured 466 total = 397 pre-existing + 69 feature. Substantive claim (zero non-baseline diagnostics in the feature) is accurate; the totals are imprecise.
- **F6 — low — packages/reports/export/html.ts:33-44 + receipt attribution.** `EXPORT_CSS` is the `planning/tools/export_html.py` stylesheet carried over verbatim plus three added rules (`h3`, `.warn`, `ul`), and the document template/copy is a close port of that reference. The receipt's "no code was copied — docs/ATTRIBUTION.md needs no update" is imprecise; the file is an assigned task input so reuse is legitimate, but `required_updates` ("docs/ATTRIBUTION.md for material reuse/inspiration") arguably applies or the claim should be corrected.
- **F7 — info — apps/web/src/features/export/ExportPanel.tsx:117-124.** `useState(controller.state)` does not refresh when `controller` is recreated on `engine`/`source` prop change — stale preview until next interaction. Unmounted module; later-task concern.
- **F8 — info — apps/web/src/features/export/controller.ts:132-147.** When the provider yields no bytes and no embedded source exists, `'carry'` is rewritten to `null` before `engine.project`, so the exported artifact cannot distinguish "not requested" from "requested but unavailable" (UI does disclose via `sourceUnavailable`; `requestedSourceMissing` only records the embedded-asset case).
- **F9 — info — packages/reports/export/selection.ts:232-253.** A `>~21 MiB` document's source opt-in produces a base64 payload exceeding `MAX_STRING_LENGTH`; `projectReport` throws `ContractError('SIZE')` at final `validate` rather than yielding an explainable `withinLimits:false` preview. Fail-closed and surfaced via `controller.error`; coarser than the contract's "explain why and offer evidence-only" wording.

## Not verified / out of review reach

- Browser runtime behavior of `ExportPanel`/`ExportController` (unmounted; no browser test exists; apps/web tsc cannot fully typecheck due to the pre-existing missing-`@types/react` baseline — all 69 feature diagnostics confirmed baseline-class, but a non-baseline type error *could* hide in the noise; oxlint is the only clean signal on those files).
- Visual/accessibility review of rendered HTML in a real browser (guard is lexical).
- `bun run build`/Vite bundling of the feature (no composition to bundle it yet).
- Fuzz coverage of `sanitizePng` re-encode beyond the single hostile-chunk case in tests (T24 owns the bounded-PNG suite).
- Evidence commit `335c2cb` files were read from `work/devin/t16`; this branch holds the identical source tree at `35f524b`.


---

## Delta review — 2026-09-13, evaluated `412fb9b2`

- **Reviewer:** devin-coordinator (acceptance refresh; not the implementing worker for this delta's shared changes)
- **Scope delta:** Owned files unchanged. The composition added `features/inspect/engines.ts`
`createExportEngine` — a consumer-side adapter implementing the T16
`ExportEngine` port (`project`/`preview`/`serializeJson`/`renderHtml`/
`fileName`); the export package itself was not modified. Export behavior
re-verified end-to-end via the G1 journey (JSON + HTML downloads, omission
defaults, script-free HTML) and this suite's 15/15.
- **Fresh run:** Re-ran all registered commands at `412fb9b2`: **15/15 green**, zero failures.
- **Verdict:** prior review stands; delta introduces no acceptance-relevant regression.
