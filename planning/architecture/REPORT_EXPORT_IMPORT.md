# Portable evidence, export and import

## Exactly two release formats

**Human report:** self-contained `.html`, no JavaScript, no external resources, text escaped, bounded PNG images embedded as data URLs. It opens in a browser after the application tab closes. Its fixed stylesheet is hash-authorized by a meta CSP. It contains no forms, embedded PDF viewer, executable snippets, remote image URLs or document-controlled links. Users may print it using their browser; a separate PDF exporter is not promised.

**Machine report:** UTF-8 `.inkflip.json`, canonical report schema plus base64 PNG/source assets with hashes and inclusion manifest. The browser imports JSON only. ZIP, HTML, SVG and arbitrary archive import are deliberately not part of the product. This planning deliverable being a ZIP does not make archive import an application capability. Corpus output is a local directory of per-file JSONs and an index; browser users choose the specific JSON files they need.

## Inclusion profiles

| Profile | Contains | Replay semantics |
|---|---|---|
| Screenshot-only diagnostic | Explicit selected raster and captions; no claim of raw completeness | Not replayable; not the default engineer handoff |
| Evidence (default) | Selected raw readings/maps, relevant geometry/transforms/readers/check plan/results, selected PNG crops, limits, document hash | Inspectable without source; matching original required for replay |
| Replayable (explicit opt-in) | Evidence plus entire original PDF and source SHA/length | Source included; recorded reader environment/model still required |

Original filename, PDF metadata, human author label and notes default off. Original PDF defaults off. The preview lists actual counts/bytes and exclusions, shows the exact crop and warns that source inclusion exposes all pages and hidden content. A selected crop is not a redaction guarantee. Never include unrelated full-page text, thumbnails, attachments or original PDF just because they exist in memory.

Selection projection preserves check scope/results but lists only retained occurrences and the original produced count. It states that other occurrences were omitted. No missing data is filled with empty success, fabricated zero counts or guessed geometry. The projected report has a new digest and an `origin_report_id`; the source report remains immutable. Source/context required to understand the chosen finding is kept, including unresolved alternatives. A user cannot export a comparison title while silently omitting the conflicting reading it asserts.

## Limits and assets

Browser import JSON <=32 MiB, decoded asset total <=20 MiB, <=128 assets and <=4 megapixels per PNG. These limits apply before expensive parsing/decode where possible. Base64 adds overhead; the preview computes final encoded size. A 20 MiB source plus crops may exceed the bundle profile. In that case explain why and offer evidence-only export requiring the separately supplied original; do not silently reduce data or upload it. Native raw corpus storage may be larger, but portable projections must obey the browser profile.

Allow only original PDF as `source_pdf` and bounded PNG as crop/page render. No SVG or active HTML asset. SHA/length must match decoded bytes; original PDF asset must match document SHA and byte length. PNG magic and IHDR are checked before decoding, then decoded in a bounded path and reencoded without ancillary metadata/APNG. A valid checksum only proves byte identity, not safety. Product image fuzz tests must cover malformed PNG chunks and decompression abuse.

## Import trust boundary

Use strict UTF-8 JSON with duplicate-key, depth, scalar, size and finite-number checks. Validate against the bundled known schema and semantic references. Reject remote `$ref`, unknown properties/versions, command strings, resource URLs and dangerous file paths. A report cannot select executable readers, run embedded code, invoke a shell or download a model. Never mount imported HTML into the DOM.

Render strings as text nodes; use `bdi` to isolate direction. Build report navigation from validated numeric pages and safe IDs only. Do not autolink URLs extracted from documents. Missing source is an explicit state with a local chooser; validate original digest before associating it. Mismatched bytes create a new document, not a silent update. Importing a native report never contacts the machine that produced it.

## Static HTML hardening

Template markup and CSS are application-owned. Escape all title/text/annotation/reader strings. Use `script-src 'none'; connect-src 'none'; object-src 'none'; default-src 'none'; img-src data:` and a fixed stylesheet hash. Meta CSP cannot supply every response-header protection (for example frame-ancestors); do not overclaim its isolation. Hosted UI uses response headers separately. Generated HTML contains no source PDF data URL, because an HTML viewer is not the desired place to open an untrusted original automatically. Source bytes remain in the explicit JSON replay bundle.

## Reproducibility versus portability

A report can be useful while not fully replayable. Excluding sensitive original bytes is a deliberate privacy tradeoff. Reader version/build, adapter algorithm, model hashes, render settings, annotation mode, selection, transforms and coverage are retained. A local replay requires the actual source and installed compatible environment. A newly generated replay result does not overwrite the earlier report; comparison is explicit. A screenshot plus a hash cannot reproduce absent bytes.

The included `tools/export_html.py` demonstrates escaped static HTML on a validated example report. It is a planning utility, not a substitute for the finished browser export/import implementation and malicious-image tests.

## Exact disclosure categories

The machine `export.included` array distinguishes `crops` from `page_renders`. Complete-page PNGs require `page_renders`; never describe a whole page as a small selected crop. Identity, settings and coverage are mandatory report metadata and disclosed explicitly. Retained occurrence text requires `selected_text`, annotations require `annotations`, and original PDF bytes and filename each require their own opt-in category. The pre-export preview is generated from the final projected object, not from UI checkbox state alone.
