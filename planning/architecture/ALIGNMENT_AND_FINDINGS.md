# Alignment, findings and comparison semantics

Algorithm ID **region-match-v1**. This is a selected conservative default with a controlled experiment for thresholds, not a trained truth model. Raw extraction and alignment are separate packages. Neither can silently correct an arbitrary amount or choose a preferred reader.

## Normalization

`scalar-whitespace-v1` preserves all non-whitespace Unicode scalar values exactly and replaces each maximal Unicode White_Space run with a single U+0020. Leading/trailing whitespace is retained as one space rather than dropped. It does not casefold, remove combining marks, apply NFKC, remove punctuation, expand ligatures, or collapse minus signs. Every output segment carries half-open raw/normalized scalar index ranges. A many-to-one whitespace map remains inspectable. A non-whitespace string has an identity map. Empty strings have an empty map.

JavaScript offsets use `Array.from(text)` or an equivalent scalar-index table; Python string indices are Unicode scalars on supported builds. Conversion to UTF-16 selection offsets is a UI adapter operation with tests for supplementary characters. Do not run the legacy challenge normalizer. “1,000”, “1000”, “100”, “-100”, “not paid” and “paid” remain different raw/normalized values. Optional equivalence hints may explain formatting but cannot suppress raw differences without a separately named opt-in rule.

## Geometry-first candidate construction

Only occurrences on the same document/page with non-null validated geometry enter localized matching. Build a page spatial index. Candidate regions require overlapping vertical bands or polygon intersection; initial tolerances: vertical overlap >=0.5 of the smaller height and horizontal gap <=1.5× median line height, with a maximum 24 canonical points. User-selected regions are a hard scope, not an instruction to take the nearest amount anywhere on the page.

Create line fragments by native ordinal plus geometric baseline proximity; preserve source occurrence IDs. Consider contiguous groups of at most four fragments on either side to handle split/merged words. Candidate union geometry must stay within one line/region; do not glue two columns to improve text similarity. Shared rendered coordinates use canonical source transforms, never screenshots resized by eye.

Match cost is `0.65 * geometry_distance + 0.20 * order_distance + 0.15 * text_edit_distance`, each clamped to [0,1]. Geometry distance is 1 minus overlap of expanded line extents, falling back to normalized center distance within the candidate window. Order distance is relative position within the local block. Text distance is scalar Levenshtein normalized by max length, with no cheap digit/sign edits. Crucially, differing text is allowed: making text agreement a prerequisite would miss the amount demo.

Compute a minimum-cost one-to-one assignment for bounded local components. Accept only if cost <=0.45, the next competing assignment costs at least 0.12 more, and geometry/order agree on the selected block. These are starting thresholds to freeze before evaluation, not probabilities. Components >64 candidates abstain to region-level comparison rather than expensive global search. T12/E02 evaluates the default at fixed precision. A failed threshold probe falls back to explicit selected-region side-by-side text and ambiguous results, never to text-only precise matching.

Repeated identical strings at different coordinates retain separate ordinals. A tie remains `ambiguous` with all candidates accessible, not first-match-wins. Missing geometry cannot be recovered by finding the same string elsewhere. Unmatched output may indicate a reader omission, extra output, unsupported mapping or alignment failure; phrase it as “No matching reading found here”, not “Text is missing from the document.”

## Localized and page-level findings

A `reading_difference` requires two actual reader outputs and completed relevant read checks. A localized `unique` alignment requires validated geometry on both sides and a known region. If only page-level text exists, show a page-level difference without a local highlight. Ambiguous matches create an informational card with candidate readings and no exact-location claim. An OCR interpretation is explicitly “Tesseract reads the rendered region as …”, not the visible truth.

An `observed_structure` cites the supporting check and narrowly states what was measured: for example, “PDFium reports a non-painting text mode for this object.” An OCR layer is not inherently suspicious. A `mechanism_hypothesis` (“a character mapping may explain this difference”) is separate from the measured difference and must say what is unverified. A human annotation is stored separately with `origin:human_entered`; it can never modify engine output. `incomplete_check` identifies the precise missing/failed requested work.

Reading-order findings compare the preserved emitted sequence with the separately labeled geometric sequence or another actual reader. Changed order of two columns is not automatically an accessibility failure. Ligature or complex-script ambiguity can be page-level; do not remove combining marks to manufacture a clean diff.

## Grouping and ranking

Group only differences sharing page, aligned region and reader pair; preserve member occurrence IDs and raw text. Keep distinct repeated occurrences separate. Priority order: explicitly selected region, material-token changes (digits/currency/sign/negation), other text differences, order/structural information. This is review ordering, not a risk score. Show the total count and paginated access to remaining findings; no hidden “top five only” coverage. Never average OCR confidence into a document score.

Agreement copy is scoped: “These readers agree in the checked region.” If OCR never ran, say “Extracted text is ready. The rendered page has not been compared with OCR.” Zero localized findings with many ambiguous matches is not zero differences: display the ambiguity and incomplete counts separately.

## Stored-run classification

Pair files by byte digest; the manifest key is a human grouping key, not proof of identity. Default reader-upgrade comparison requires the same document digest, equivalent page/region selection, normalization/alignment versions and comparable check capabilities. Reader version is the intended differing variable. Different file bytes require explicit `document_versions` mode; report source and reader changes independently and do not claim a parser-only regression.

A comparison is `unchanged` only when comparable semantic outputs and coverage match. `changed` means measured differences without a rule-based value judgment. `improved`/`regressed` require a specific rule ID or frozen fixture expectation. Coverage loss or errors always produce an adverse rule result when the default release policy is active; fewer findings due to absent OCR cannot be improvement. Unsupported capability is visible. A changed algorithm/configuration without an explicit comparison mode yields `incomparable`, not unchanged.

Per-file classification precedence is: unrecoverable input/run error → `errored`; invalid comparability → `incomparable`; violated explicit rule/coverage loss → `regressed`; an explicit expectation that newly passes with no losses → `improved`; other measured differences → `changed`; otherwise `unchanged`. A fully unsupported pair is `unsupported`. Corpus totals show each category and denominator, not a single success score.

## Acceptance

Zero numeric/sign/negation false equivalences on hard fixtures; no incorrect page anchors; duplicate-occurrence preservation; all ambiguous ties abstain. Useful localized-finding precision target >=0.95 with a Wilson 95% lower bound >=0.90 on the frozen supported-case suite, and clean false-alert mean <=0.05 per page. Report OCR-damaged and clean populations separately. These are release targets, not achieved measurements.
