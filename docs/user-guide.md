# User guide

This guide describes the browser inspector as implemented in this snapshot.
Where behavior is deliberately conservative (OCR limits, what a finding
means), the limit is stated rather than glossed over. For what the app
cannot do yet, see [limitations.md](limitations.md).

## The idea in one paragraph

A PDF page has a visual appearance (the marks a renderer paints) and one or
more machine readings (the embedded text layer, OCR of the rendered pixels,
native reader extractions). Usually they agree. When they don't, a displayed
`$100` whose text layer says `$1,000` is the classic case, and the discrepancy
is easy to miss and hard to evidence. Inkflip renders the page, obtains named
readings, aligns them to the same coordinates, and shows disagreements as
navigable evidence you can export. A disagreement is a fact about two
readings; it is **not** a verdict about which one is correct, or about the
document's safety, honesty or legality.

## Start: Home screen

Launch the app ([quickstart.md](quickstart.md)) and open the printed URL.

- **The example gallery** shows six prepared synthetic examples, each generated
  from this repository's own fixtures and openable without any local file:
  1. *An amount changes during extraction.* The font's ToUnicode table maps
     the displayed 1 to 1,0, so visual `$100` becomes extracted `$1,000`;
     clean control files isolate the cause as text extraction.
  2. *Text covered by a white box.* The render shows nothing while
     the text layer still carries the amount.
  3. *A scan with a hidden text layer.* A searchable scan
     carries an invisible text layer over the raster; raster-only and
     shifted siblings show when readings still agree. A normal searchable
     scan is not evidence of wrongdoing.
  4. *The same page, rotated.* Identical content under
     0/90/180/270° rotation; readers must reconcile geometry through the
     recorded transforms.
  5. *Columns read in a different order.* Two columns emitted
     right-then-left; the same text arrives in a different stream order.
  6. *Repeated amounts at different positions.* Four identical amounts at distinct
     positions stay individually addressable; a string match must never
     collapse them.
  All examples are synthetic originals; behavior shown in one synthetic file
  under named reader versions is not a claim about PDFs in general.
- **Open Workspace** starts with an empty workspace for your own file.

## Open a PDF

In the workspace, **Open PDF** reads a file from your device through the
browser's file picker. The file is parsed locally in the tab; there is no
upload path (this is continuously tested — see
[privacy](#privacy-in-practice)). Opening validates the document before
anything is displayed; invalid input fails with an explicit message.

Constraints that exist today:

- one active document per workspace; use **Close Document** before opening
  another;
- the workspace is in-memory — closing the tab discards the session (saved
  JSON reports are the persistence mechanism, below).

## Read: Page, Reading, Compare

The toolbar has three view tabs plus zoom/rotate controls:

- **Page** — the rendered page image (PDF.js canvas rendering), with region
  selection for closer inspection.
- **Reading** — the machine readings for the selected page or region: the
  document's own text extraction, OCR of the rendered pixels performed by
  Tesseract.js (English; the language pack is staged from this app's own
  origin), and the accessible text-equivalent listing that names every
  reader, its version, and its occurrence-level output.
- **Compare** — the two views side by side, aligned to the same page space,
  with disagreement highlights.

OCR runs only on pages/regions you explicitly request. It is bounded (a
finite per-run page and time budget) and cancellable.

## Evidence: findings, occurrences and notes

When readings disagree — or agree in a way worth recording (duplicated
amounts, structural observations) — the app records a **finding**: what kind
of difference it is, where it is (page and region), which readers produced
which reading, and a plain-language explanation. The **Evidence Slip** panel
lists findings in document order; Prev/Next walks the document through each
one, and the page view follows.

Three rules the app enforces on itself, worth understanding before you rely
on it:

1. **A finding names readers and readings, never conclusions.** "PDFium
   returned $1,000.00, pypdf returned $10,000.00" is a finding. "This
   document is fraudulent" is not, and the app will not say anything like it.
2. **Coverage is explicit.** The panel shows what was actually read
   (which pages, whether OCR ran) alongside what was not, so silence cannot
   masquerade as a clean bill of health. Incomplete coverage is labeled
   partial, never clean.
3. **Occurrence candidates stay distinct.** When the same string appears at
   several positions, each occurrence is individually addressable by its own
   id and position — selection is by location, never by text matching, so
   identical strings are never collapsed into one. Order-only differences
   are classified separately from genuinely different readings, and text
   that no reader found is reported as unmatched rather than counted as
   missing.

You can add your own **notes** to a finding. Notes are your own words: they
are stored as human-entered annotations, never become machine readings, and
are included in an export only when you explicitly opt in.

## Cancel, replace, large documents

Analysis runs are bounded and supervised: you can **cancel** a running OCR or
reading pass, and opening a different file or region **replaces** the running
work instead of queueing behind it, so a slow job can never deliver stale
output into a view you've already moved past. Large documents stay
interactive (the reader work is per-page and lazy), and narrow windows get a
stacked layout rather than a shrunken desktop grid.

## Export and reopen

- **Choose the scope** — export the full run or a selection you control.
- **Choose what to include** — notes and page renders are opt-in and default
  off; the panel shows a pre-export preview with what will actually be
  written before anything is produced.
- **Export JSON** writes a portable report: document identity, page
  geometry, readings with reader versions, findings, chosen annotations and
  the images needed to review the evidence, with no reference to your local
  paths.
- **Export HTML** writes a script-free snapshot of the same evidence — no
  JavaScript, no external fetches — that opens in any browser and is safe to
  attach to a ticket or email.
- **Open saved report** re-opens an exported JSON report through the same
  validation boundary as a local file. Import is strict: the file must
  validate against the report schema, and deliberately hostile inputs
  (oversized strings, unexpected HTML, injected paths) are rejected — this
  is tested in the security suite, not assumed.

Exports are the intended way to hand evidence to someone else: they can open
the JSON or HTML without Inkflip, or reopen the JSON in Inkflip to continue
investigating. A reopened report can carry its original document bytes (when
the export explicitly included them), letting the recipient replay the
inspection locally — the workspace states exactly when a reopened report is
replay-ready and which source it refers to.

## Working offline

Inkflip is built to keep working without a network once prepared:

- **Prepare for offline use** downloads and integrity-checks this release's
  app, reader and model files (the exact allowlisted paths for this release —
  application shell, reader runtimes, the pinned OCR model, and the example
  assets) and stores verified copies in the browser. Every stored entry is
  digest-verified when stored and again when served; a mismatching entry is
  discarded, never served.
- Offline readiness covers exactly the prepared release files. Your documents
  never enter the offline cache; anything not on the release allowlist still
  needs the network.
- **Remove offline assets** deletes those prepared copies. It is separate
  from closing a document (which clears the document, its readings and its
  workers but keeps prepared offline assets) and from removing downloaded
  OCR data. Removal deletes the app's own caches only — browser memory, the
  HTTP cache and OS storage are beyond an app's reach.
- A cold page with nothing prepared fails with an explicit offline error
  rather than silently reaching for the network.

## Privacy in practice

Everything above runs locally in your browser tab. The project's no-egress
claim is not a slogan — it is a canary test suite
([tests/privacy/README.md](../tests/privacy/README.md)) that drives a marked
synthetic document through the real production build in Chromium and asserts,
capture by capture, that nothing about your document leaves the tab — with
the network reachable (cold/warm) and with the network fully blocked after
load (offline). Model/engine assets are served from the app's own origin, so
a prepared page keeps working offline; a cold offline start fails with an
explicit error rather than quietly needing the network.

## Supported environment

The app is developed and continuously exercised in Chromium (Playwright
drives real Chromium for the browser, privacy, accessibility and visual
suites). Other modern browsers are expected to work but are not covered by
an explicit parity task yet. There is no mobile app and no hosted service.

## Where to go next

- [limitations.md](limitations.md) — what the tool cannot establish, and
  which capabilities are still pending.
- [architecture.md](architecture.md) — how the readings, alignment and
  exports actually work.
- [distribution/README.md](distribution/README.md) — what this repository
  ships and how its license/notice evidence is organized.
- [case-study.md](case-study.md) — one investigation walked through end to
  end, with a reader-upgrade example and reproduction instructions.
