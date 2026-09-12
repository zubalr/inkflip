# T10 bounded independent arithmetic review

Candidate: 32f098e45e862a49e5b88a1d95f6bc8836ec46da plus checkpoint 428285737268d72dd6e9ead27ace1eacfb0fc9f5 (HEAD verified). Reviewer: Codex independent bounded review. Read canonical original/AGENTS.md and docs/HOMEBASE.md, worktree guidance, NATIVE_PASSES, brief, invariants, coordinate contract and code-review skill. No source, branch, Beads, GitHub or other writer changes. Final git status clean. No OCR/browser/acceptance jobs.

Verdict: return for bounded revision; arithmetic tests pass, but eager enumeration is unnecessary resource work and arithmetic floor-equality does not establish actual render-transform fidelity. Do not accept geometry as proven by this checkpoint.

## P2: eager candidate enumeration, crop.ts:143–168

Real planCrop with page={index:0,rotation:0,canonical_size_pt:[612,792]}, raster={rasterId:'r',renderReaderId:'r',scalePxPerPt:1,widthPx:2,heightPx:2}, checkId='x', region=null, bounds={maxRasterPixels:1,maxRasterEdge:8192} returns k=.75 and output 1×1. Before returning, recordedResizeK creates 500,002 entries (500,000 fitting grid values and two fallbacks). One measured call took 7.06ms on this machine; numeric payload alone is approximately 4 MB, excluding array capacity/overhead. This is a reproduced allocation/work issue, not a claim of OOM or an unbounded loop. A 17×17 crop/cap=1 similarly generates 58,826 entries (1.39ms observed). Tight caps are supported inputs; ordinary default caps do not trigger this tiny-crop case.

For N=max(0,mHi-mLo+1), helper time and auxiliary space are Θ(N), N approximately 1e6*(hi-lo), at most about 1e6/max(cropW,cropH). For feasible downscaled positive integer dimensions max dimension is at least 2, so about 500,000 fitting values is the effective maximum. Fixed six-decimal precision makes this globally bounded; it is still gratuitous eager work. Caller crop.ts:287 onwards consumes the first acceptable entry. This directly conflicts with the user's global rule to compute independent values rather than enumerate cases.

Exact cyclomatic count under the user's named-token convention, baseline=1, nested functions counted separately: recordedResizeK=9 (5 if, 1 loop, 1 ||, 1 &&); nested fits=3 (2 &&); planCrop=26 (6 if, 1 loop, 1 ternary, 13 &&, 4 ||). Nullish coalescing is not counted by that stated convention. These are AST-counted source values, not an assertion of a configured lint threshold. No complexity ceiling should be raised.

## P1: loaded test expectation is weaker than actual resize geometry

reader.ts:291–313 passes cropWidth/cropHeight as source dimensions and outWidth/outHeight as destination dimensions to drawImage. Thus the actual axis scales are outW/cropW and outH/cropH. occurrences.ts:106 uses [resizeK,resizeK]; the recorded matrix also uses that uniform factor. The test checks floor(crop*k)==out, which establishes integer allocation consistency but does not establish those axis scales equal k.

Real planCrop main regression: 4896×6336, 4M cap -> 1758×2275, k=.359143. Actual drawImage ratios are .3590686274509804 and .3590593434343434. Inverting the destination far edge using recorded k misses the source edge by 1.0138802649635181 and 1.4758689435684573 raster pixels (divide by render px/pt for page-point error). Tiny 17×17/cap1 returns k=.088235 although drawImage uses 1/17=.058823529411764705. The 8192×4000/cap903 fallback returns 42×20,k=.005249: recorded inversion misses the source far edges by 190.47590017146194 and 189.75042865307705 pixels. This mismatch predates the fix in principle; the new midpoint selection does not resolve it and can increase it. Do not describe this checkpoint as proving exact geometry.

Source geometry checked against WHATWG HTML drawImage source/destination rectangle behavior: https://html.spec.whatwg.org/multipage/canvas.html#dom-context-2d-drawimage . Local COORDINATES.md:30 explicitly records Scale(kx,ky). No browser pixels were rendered in this bounded review; the mismatch follows directly from real planCrop results and actual drawImage arguments.

## Minimal bounded arithmetic proposal, validated in temporary files only

Retain lo/hi, six-decimal integer grid, existing floor checks and caller's positive-dimension/caps checks. Replace the exhaustive interval walk with the clamped midpoint and its immediate +1/-1 grid neighbors, retaining only in-range floor-fitting candidates, then the existing lower/upper fallbacks. Maximum five candidate values, constant work/storage independent of interval width. Midpoint is interior when the interval has width; ±1 covers endpoint FP straddling for the bounded raster sizes exercised here. No tolerance relaxation, changed goldens, cap relaxation or contract change.

Executable proposal is /private/tmp/inkflip-t10-bounded-helper.js; full temporary crop module /private/tmp/inkflip-t10-crop.ts. This proposal preserves selection order for the tested population and retains the exact final acceptance checks. Its helper has no conditional statements/loops: parent complexity 1, callback complexities 2 (range predicate), 1 (map), 3 (floor predicate). A direct return with one verification block can avoid distributing trivial functions if preferred. Do not treat empirical validation as a proof for arbitrary unsafe-integer dimensions; source currently validates integer, not safe integer.

Geometry additionally needs actual rendering to use the recorded uniform factor while retaining integer canvas allocation: render the source crop to destination (cropW*k,cropH*k) on the floor-sized output canvas, which clips the fractional right/bottom remainder. That makes the transform the same k on both axes and preserves existing floor-equality and caps. This is a source-grounded proposal, NOT browser-validated here; writer should add a lightweight geometric render check before heavy OCR. Alternatively independent realized axis factors require an explicit contract/API decision and precision analysis; do not silently replace or loosen the current contract.

## Executed evidence

- node --test tests/readers/crop-math.mjs: 12/12 pass.
- node node_modules/typescript/bin/tsc -p packages/readers-tesseract/tsconfig.json --noEmit --incremental false --composite false: exit 0, no emitted worktree files. This is the current candidate typecheck, not full tsc -b.
- node /private/tmp/inkflip-t10-probe.mjs: real planCrop cases above; extracted original helper vs constant candidate proposal matched first candidates for 24,964 combinations (w,h=2..80, cap fractions .01,.1,.5,.9). No claim of exhaustive arbitrary-number correctness.
- node --test /private/tmp/inkflip-t10-crop-math.mjs: 12/12 unchanged tests pass against temporary module containing bounded replacement and real repository dependencies.
- git rev-parse HEAD and git status --short: exact checkpoint and clean.

Checkpoint's pending heavy review remains pending; no acceptance, OCR quality, raster screenshot parity or full browser geometry result is asserted. Parent should route bounded writer revision and light render-geometry proof before reserved heavy validation.

# Follow-up: direct cap quantization experiment

TEMP ONLY; proposal /private/tmp/inkflip-t10-direct.ts, builder /private/tmp/inkflip-t10-direct-build.py, unchanged test copy /private/tmp/inkflip-t10-direct-test.mjs, case driver /private/tmp/inkflip-t10-direct-cases.mjs. No branch edits/publication. The temporary implementation quantizes the independently computed cap factor with floor(k*1e6)/1e6, then floors dimensions, rejects zero/nonfinite factor/nonpositive dimensions, verifies caps, and records nonzero right/bottom fractional clipping. Rendering proposal assessed below, not implemented or browser-executed.

Executed `node --test /private/tmp/inkflip-t10-direct-test.mjs`: 11 PASS / 1 FAIL. Only failure is test 'edge cap 9000x120 records an exactly-reproducing factor', line 124: 8191 !== 8192. Main 4896×6336 regression, subprecision fallback, all deterministic fuzz, transform and region tests pass unchanged.

Executed direct-cases driver:

| crop / pixel cap | current k, output | direct k, output | direct clipping R/B output px |
|---|---|---|---|
| 2×2 / 1 | .75, 1×1 | .5, 1×1 | 0 / 0 |
| 17×17 / 1 | .088235, 1×1 | RESOURCE_LIMIT | n/a |
| 3×3 / 1 | .5, 1×1 | RESOURCE_LIMIT | n/a |
| 4896×6336 / 4M | .359143, 1758×2275 | .359088, 1758×2275 | .094848 / .181568 |
| 8192×4000 / 903 | .005249, 42×20 | .005249, 42×20 | .999808 / .996 |
| 9000×120 / 4M, edge8192 | .910278, 8192×109 | .910222, 8191×109 | .998 / .22664 |
| 50000×100 / 4M, edge8192 | .16385, 8192×16 | .16384, 8192×16 | 0 / .384 |

Interpretation: 8192 exact width is an existing arithmetic regression expectation preserving behavior, not an explicit exact-size mandate found in COORDINATES.md, READER_ADAPTER_CONTRACT.md or the loaded browser test (which asserts <=8192 and floor equality). Thus 8191 is not independently a geometry/cap violation. Nevertheless it is an observable dimension change and must not be silently accepted by changing the assertion. More seriously, downward quantization can reject feasible positive output: floor((1/17)*1e6)/1e6=.058823 and floor(17*.058823)=0, while .058824 is six-decimal, gives 1×1 and satisfies both caps. Similarly .333334 solves 3×3/cap1. These are not genuinely unrepresentable dimensions. The rejection message in the direct experiment overclaims impossibility. With integer allocation caps, the continuous cap factor is a sufficient bound, not the greatest feasible recorded factor. A grid value above it can still floor to bounded dimensions. No explicit contractual guarantee to process every feasible factor was found, but introducing resource failure for previously valid bounded geometry is an unnecessary regression under the preservation rule.

Recommendation: retain the already validated constant-size midpoint/neighbor/fallback proposal for this bounded fix, plus actual-factor rendering and explicit clipping limitation. Do not adopt pure down-quantization or weaken the existing test. Five fixed candidates preserve current dimensions on the validated population, unlike direct quantization. The retained files remain /private/tmp/inkflip-t10-bounded-helper.js and /private/tmp/inkflip-t10-crop.ts. No broader arbitrary-integer proof or new full typecheck is claimed for these TEMP proposals.

Rendering adjustment for SWE: keep canvas width=floor(cropW*k), height=floor(cropH*k), but pass destination width=cropW*k,height=cropH*k to BOTH reader.ts drawImage branches. Record `ocr_resize_clipped` when either difference is >0, identifying right/bottom amounts in output pixels; each is in [0,1), not necessarily small in source/page units. Preserve original crop geometry and record this as an additional limitation; do not relabel fractional clipping as downsampling alone. Quantizing these fractional diagnostics to six decimals can hide a nonzero value, so presence should be decided on the actual computed difference. Existing geometry transform guards still apply; positive k alone does not guarantee matrix/inverse validation at extreme scales.

Concrete browser pixel regression to hand SWE (no OCR engine needed):

1. Exercise the production crop/encode path via its existing test seam or capture the actual PNG passed to a stub recognize boundary; do not compare two independent copies of drawImage code. Test both ImageData and CanvasImageSource input branches.
2. Construct 17×17 RGBA pixels with R=10*x, G=10*y, B=0, A=255. Plan full crop at scale1 with pixel cap1 and edge8192; bounded candidate gives k=.088235, integer canvas1×1, destination1.499995×1.499995, clipping .499995 on each edge. Disable smoothing in a focused renderer seam so the nearest-neighbor expected pixel is unambiguous. Under actual recorded scale the sole pixel center .5,.5 samples source floor(.5/k)=5 on both axes: RGBA=[50,50,0,255]. Old drawImage-to-integer-size behavior samples source (8,8): [80,80,0,255]. Assert actual decoded output bytes and 1×1 dimensions, not only call arguments. This pixel separates the implementations by 3 source pixels per axis, so it is stronger than a permissive overlay tolerance.
3. Assert clipping limitation exists with actual amounts and matrix[0]=matrix[3]=k. Separately map the known sample center back with recorded transform and check it lies inside source pixel [5,6) on each axis. Add a no-resize 17×17/cap289 case with no fractional-clipping limitation. If adding a crop-offset case, supply a nonzero source crop origin and assert the offset is restored; do not introduce padding accidentally into the fixture.
4. The first image must pass through the real output renderer, not a mock canvas. For the production smoothing setting, add a robust broad-color anchor case if required; nearest-neighbor fixture can be tested through a narrow explicit renderer option/test seam without changing production quality settings. If no safe smoothing seam exists, use the same coordinate gradient with the production smoothing mode, run real pixels to establish the expected interpolation, and avoid claiming the nearest-neighbor bytes apply unchanged.

COORDINATES.md:52/58 requires six-decimal finite transforms and independent known pixel anchors; this test addresses the latter. Source-and-contract analysis validates the proposed mapping, but the browser pixel assertion is a handoff specification and was NOT run in this light arithmetic-only follow-up. Heavy OCR remains reserved.

# Preferred final refinement: lower-edge constant candidates

Supersedes the midpoint recommendation above. TEMP implementation `/private/tmp/inkflip-t10-lower.ts`; helper `/private/tmp/inkflip-t10-lower-helper.ts`; unchanged suite copy `/private/tmp/inkflip-t10-lower-test.mjs`. Executed `node --test /private/tmp/inkflip-t10-lower-test.mjs`: **12/12 PASS**. No assertion edits. All supplied real planCrop cases also ran successfully.

Smallest tested replacement:

```ts
const lo = Math.max(outW / cropW, outH / cropH);
const m = Math.ceil(lo * 1e6);
return [m / 1e6, (m + 1) / 1e6, (m - 1) / 1e6];
```

Keep caller's bounded loop: rederive w=floor(cropW*r), h=floor(cropH*r); accept first positive integer output satisfying pixel/edge caps, else fail RESOURCE_LIMIT. Retain transform precision/finite validation. For writer clarity explicitly check finite positive r and integer w/h if extending numeric input domains; never clamp zero dimensions to one after choosing r. Existing initial ideal dimension calculation remains unchanged. Candidate generation has cyclomatic complexity 1 and exactly three values; caller has at most three iterations. No interval enumeration, midpoint, tolerance or `hi` computation. The +1 neighbor handles downward product rounding at a boundary; the -1 neighbor allows a bounded smaller realization when upward candidates violate caps. Do not require all candidates to reproduce the old ideal dimensions: 43×21 below is legitimate and caps checked. This is a bounded validated selection, not a proof of globally optimal clipping or support for unsafe-integer raster dimensions.

Measured outputs:

| crop / pixel cap | recorded k | output | actual destination size |
|---|---|---|---|
|17×17 / 1|.058824|1×1|1.000008×1.000008|
|3×3 / 1|.333334|1×1|1.000002×1.000002|
|4896×6336 / 4M|.359069|1758×2275|1758.001824×2275.061184|
|8192×4000 / 903|.00525|43×21|43.008×21|
|49×80 / 50|.1125|5×9|5.5125×9|
|9000×120 / 4M, edge8192|.910223|8192×109|8192.007×109.22676|

Parent numbers confirmed, with one precision clarification: .00525 gives a **43.008×21 destination**, not an exact 43×21 destination; the integer canvas is 43×21=903 pixels, with .008 output-pixel right clipping. The subprecision test passes unchanged, but its existing comment describing below-interval 42×20 behavior will need an honest explanatory update (not a loosened assertion).

Pair this helper with rendering destination cropW*k,cropH*k on the integer canvas in both drawImage paths and explicit nonzero right/bottom fractional-clipping limitation, as above. Temporary planner records those limits; actual browser renderer remains unchanged and untested here.

Replace the old 17×17 pixel fixture with this robust rectangular case for SWE:

- Real 49×80 source, fully opaque: all columns x<42 solid black, x>=42 solid red; same colors at every row. Full crop, scale1, pixel cap50, edge8192. Preferred real plan gives k=.1125, canvas5×9, destination5.5125×9.
- Invoke production crop/PNG path, capture/decode pixels via a stub OCR boundary (no real OCR). For a deterministic nearest-neighbor renderer seam with smoothing disabled, pixel (4,4) must be black. Its center x=4.5 maps to source x=40 under recorded k; old integer-width stretching maps it to x=44.1 and produces red. Broad color regions avoid a color-boundary sampling tie. Check both ImageData and CanvasImageSource branches.
- Assert 5×9 actual decoded dimensions, matrix axes equal .1125, right clipping .5125 and bottom clipping 0, using numerical tolerance for the diagnostic value; check inverse source location x=40. Include no-downscale control with no clipping limitation. Do not claim browser bytes validated until the real path runs. If no smoothing seam exists, establish independent production-smoothing pixel expectations with an actual browser run rather than pretending nearest-neighbor bytes apply.

Final recommendation: **lower-edge three-candidate helper + actual-k destination + explicit fractional clipping**. All 12 arithmetic tests pass; concrete render-pixel proof is the remaining writer check. No T10 branch writes or publication occurred.
