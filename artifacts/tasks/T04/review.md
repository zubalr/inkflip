# T04 Implementer Verification Notes — canonical geometry and transform conformance

**Status:** implemented, pending independent review. This file is the
implementer's own verification record, not an approval; the coordinator
replaces it with the committed independent review at acceptance time.

**Candidate:** `7cda7a60f8ad63d42a2b59f08a7d250f8e6b57bd` on
`work/devin/t04` (base `c12e680`).

## What was built

`packages/geometry/` (5 modules, ~1,150 LOC) over the T03 contract
types — nothing redefines `Matrix`/`Point`/`Box`/`Page`/`Transform`/
`Geometry`/`apply`/`inverse`/`ContractError`:

- `affine.ts` — six-component `[a,b,c,d,e,f]` composition
  (right-to-left, column vectors), determinant, contract `inverse`
  (|det| <= 1e-12 -> `ContractError('TRANSFORM')`), 6-decimal storage
  rounding with finite-only and -0 -> 0, and `checkedInverse` enforcing
  the 1e-5pt pair bound on a caller-supplied extent.
- `page.ts` — space ids (`pdf_user:pN`, `canonical:pN`, `display:pN`,
  `raster:<id>`, `ocr:<id>`, `css:<viewport>`); `effectiveViewBox`
  (CropBox ∩ MediaBox, crop defaults to media, empty intersection
  rejected); `canonicalTransform` C = [u,0,0,-u,-u·cx0,u·cy1] — UserUnit
  and the effective box enter exactly once; `displayRotation` for all
  four quarter-turns; raster scale, OCR crop/resize, viewport
  (zoom/pan) and `backingScale` (DPR only at the backing canvas);
  contract record builders for every step plus composed math helpers
  (D = R·C, P = S·R·C, O = K·T·S·R·C, recovery C·O⁻¹) and
  page-checked chain composition.
- `geometry.ts` — `makeTransform`/`makeGeometry` emitting
  schema-shaped records with semantics enforced at construction:
  stored matrix/inverse both rounded to 6dp, stored inverse within
  1e-5/component of the exact inverse (the contract validator's rule),
  storage-amplification guard (max|inverse|·5e-7 <= 2pt overlay
  budget), `polygon === null` iff `page_only`/`unknown`, degenerate
  polygons rejected, page binding via `ensurePage`/`ensureGeometryPage`.
- `polygon.ts` — shoelace area, bounds, transform, point-in-polygon,
  Sutherland–Hodgman `clipToView` returning honest
  inside/partial/outside metadata with the untouched `source` polygon
  always preserved (clipping is display metadata, never destructive).

## How the tests derive expectations independently

`tests/geometry/derive_expectations.py` builds `expected.json` with
exact `fractions.Fraction` arithmetic AND separate closed-form
per-rotation equations (the two paths are asserted to agree on a wide
grid), anchored on the published COORDINATES.md worked example. The
node suite additionally anchors display sizes on the executed PDFium
probe's rendered pixel grids — expected values are never produced by
inverting this package's own output.

`tests/geometry/report_helper.mjs` builds a minimal report so emitted
geometry runs through the real contract `validate()`.

## Executed results (see commands.log)

- `node --test tests/geometry/*.test.mjs`: 32/32, exit 0 (the
  registered acceptance command; `task_acceptance.py task T04`
  re-confirms 32/32 with no failures/evidence errors).
- `uv run --project native python -m pytest tests/geometry -q`: 6/6.
- `bun x --no-install tsc -b tsconfig.json --force`: whole
  project-reference graph compiles clean.
- `python3 tests/geometry/derive_expectations.py --check`: golden fresh.
- `bun run verify`: 48/49 — sole failure is the pre-existing base issue
  below.
- `planning/` byte-identical; `bun.lock`/`native/uv.lock` untouched;
  all changes inside `packages/geometry/` + `tests/geometry/` +
  `artifacts/tasks/T04/`.

## Known limitations (honest, none blocking the criteria)

1. **Pre-existing base failure, not T04-caused:**
   `tests/bootstrap` `test_declared_suite_with_missing_runner_fails`
   expects `run test:browser` -> "prerequisites missing". Since T02
   installed `@playwright/test`, the command now runs and fails at
   "zero tests collected" instead. T02's commands.log documents the
   identical effect with repoint proposal P2 (T01-owned file).
   Confirmed identical with all T04 changes removed. The playwright
   default glob incidentally also loads `*.test.mjs` files (contracts'
   and geometry's) — the failure predates and is independent of them.
2. **CSS/DPR criterion tail:** "p95<=2px, maximum 4px" is a
   viewer-integrated measurement; no viewer exists yet (the criterion
   itself says "once viewer integrates"). Executed now: viewport math,
   page-bound viewport records, DPR-only-at-backing-canvas, and the
   storage-rounding overlay bound (~1e-4pt ≪ 2pt). The integrated pixel
   measurement remains deferred — not fabricated.
3. **oxlint/oxfmt unavailable:** the bun isolated linker did not
   materialize `@oxlint/binding-darwin-arm64` in this environment
   (reproduced: `Cannot find module`); not part of registered
   acceptance.
4. **Node runtime:** tests ran on system Node v26.7.0; the repo pins
   22.23.2 which is not installed here.
5. **Probe coverage:** `native-probe.json` has no `geometry-control`
   record, so the pixel-grid cross-check is gated on record presence;
   the closed-form and Fraction-derived anchors cover it.
6. **Stored-inverse chain bound:** chained 6dp-rounded inverses
   accumulate ~2.3e-4pt on the exercised extent; asserted at a
   documented 1e-3pt bound (≪ 2pt overlay budget). Per-record pairs and
   exact-inverse chains hold the contract's 1e-5pt bound — the two
   quantities are asserted separately, never conflated.

## Suggested review focus

- `geometry.ts` `makeTransform` extent/default-extent design and the
  amplification guard constants.
- `page.ts` `buildPage` explicit-view agreement check (1e-5) and the
  pdf_user→canonical sign conventions against COORDINATES.md.
- `polygon.ts` `clipToView` edge-inclusive semantics and the
  inside/partial/outside classification rules.
- `derive_expectations.py` — confirm the closed-form equations are
  genuinely independent of `page.ts` (different code path, exact
  arithmetic).
