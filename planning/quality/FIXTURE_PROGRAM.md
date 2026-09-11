# Reproducible fixture program

Canonical catalog: [fixture-catalog.json](fixture-catalog.json). Each family defines a mechanism, generator recipe, controls, expected observation type, grouping/split rules and test IDs. The seven already generated PDFs are public-probe fixtures, not untouched evaluation. `fixtures/generated-manifest.json` records their actual bytes/hashes.

## Generator discipline

Use fixed original PDF recipes for small structural cases, with deterministic object ordering, no creation timestamp/random document ID unless explicitly testing that field, and stable metadata. The amount mapping/cover/geometry generator is included and executed. Do not make a generic payload generator or fetch external documents from input URLs. Generator expectations come from intended PDF structure and independent render checks, not the parser being tested.

Each recipe writes source PDF, a machine expectation file and a manifest with generator source hash, recipe/version/seed, family/group ID, rights, expected readers/checks and control counterpart. Expectations are not baked into application logic. Public prepared reports are produced by the real reader pipeline and include its environment, never by copying expected labels into output. Different reader outputs on the covered-text example are retained as observed behavior rather than “corrected” to an attractive demo.

For searchable scans, first generate an original clean printed page, render to a raster under a named build, then create a new PDF containing the raster plus a correctly positioned invisible text layer. Compare it with raster-only and deliberately displaced-layer siblings, all in the same split. Native mode observation alone must not become an alarm on the correct scan.

Non-Latin fixture text is original. Native preservation tests include Arabic logical text with combining marks, CJK and supplementary Unicode; English OCR is not applied as a claimed supported recognizer for them. Acquire script fonts from a rights-cleared pinned source only after exact hash/license verification, and retain notices for embedded resources. No arbitrary local font file is redistributed by this planning package.

## Structural and OCR controls

White-on-dark must be a negative control for white-on-white detection. A preceding dark fill and a later cover are different paint-order mechanisms. Partial cover, clipping path, rotated text, transparency and optional content are controls for overclaiming rectangular heuristics, not promises of full compositing reconstruction. An invisible text box crossing a visible border defeats naive box-ink visibility inference. A damaged OCR region needs a clean counterpart and an adjacent-field crop trap; selecting the wrong neighbor is a failed finding even if the returned number looks plausible.

Geometry families combine known fiducials with nonzero/negative origins, all rotations, varied UserUnit and bounded raster scales. A fixture must test actual displayed anchors, not only algebraic inverses. Repeated strings vary position, count, reader segmentation and emission order. Missing/malformed mapping is distinguished from missing visible marks.

## Failure and security fixtures

Generate controlled encrypted/malformed/oversized PDFs; do not bundle live exploit code. Worker faults use fake readers and controlled child processes that hang/crash under the test supervisor's strict deadline. JSON import attacks include unknown schema/keys, duplicate keys, deep nesting, invalid references, corrupted digest/base64, giant PNG dimensions, SVG disguised as PNG, script-like text, unsafe paths and baseline misuse. These are fixed test cases with no real secrets or external exfiltration destination.

## Rights and lifecycle

Original synthetic material is approved under the selected MIT terms. Real permissioned incidents keep consent/reuse terms outside public builds unless explicit redistribution is granted. Minimized synthetic reproductions are preferred for public issue reports. Never copy unrelated private Project files into a fixture directory. A release fixture manifest is immutable; changed recipes receive new version/hash and the prior result remains distinguishable.

Fixture generation failures block the affected sample/claim. The app must not read a sidecar label as a real result. T05 establishes common generator APIs; nonowners propose additions through owned family directories, and the integrator serializes the shared manifest.
