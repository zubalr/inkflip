# Product specification and journeys

## Success object

The useful object is a reading report, not a dashboard. A visitor should understand one disagreement before seeing configuration. An engineer should be able to locate a problem, retain competing readings, explain exactly what was checked, and export enough evidence for someone else to investigate. This specification defines the complete release; user research tests clarity, not permission to finish it.

## Information architecture

Hash routes are fixed and contain only public IDs: `/` landing workspace; `#/examples/<allowlisted-slug>` prepared example; `#/how` explanation; `#/developers` local CLI and report comparison entry; `#/limitations` precise scope. A personal file never creates a route containing its filename, digest, page text, annotations or report data. Workspace state is memory-only. Back navigation must not accidentally restore cleared sensitive content from an application persistence store.

The landing page contains an interactive synthetic amount crop, an obvious Page/Extracted reading control, the headline and two actions. Below it: a six-card gallery, a three-step explanation, and the developer continuation. There is no permanent navigation sidebar, KPI grid or chat. Opening an example keeps a persistent synthetic/prepared label and exposes the source PDF plus actual processing manifest. Own-file mode removes prepared labels only when live checks have really run.

## Journey A — understand the example

The visitor activates the amount example. The rendered crop is already visible; the alternative reading comes from a stored actual output, not a filename-specific rule. Flipping or Compare presents the named engine/version. “This amount reads differently” opens a compact evidence detail with both readings, the crop, check scope and limitations. “How this was checked” reveals the generator mechanism, processing manifest and whether automatic alignment/OCR were actually executed. A report download is possible without a signup. In the reference prototype, the named reader is the executed PDFium path; the finished browser gallery must be regenerated under the shipped browser profile.

## Journey B — investigate a local file

Open/drop one PDF. Display a short privacy statement before reading. Reject oversized/non-PDF/encrypted input explicitly. Parse page count without rasterizing all pages; show the first bounded preview and a page picker. Default selection is page 1 for native inspection; optional OCR preparation requires explicit consent to static model download and selected pages. A reader cannot silently choose all 1,000 pages. User can select up to profile limits, choose a region by drag or numeric/keyboard controls, and see its OCR padding.

Start creates a finite check plan. Native text appears progressively; OCR model preparation and OCR progress are separate. User can zoom/pan/rotate the view, inspect raw readings, cancel or choose another file. Cancellation keeps completed evidence but marks unfinished work. Replacement warns about unsaved reports, increments generation, clears the old workspace and never displays delayed old results. Failed OCR does not erase usable native text.

Click a finding to synchronize the source page and reading fragment. Repeated strings have numbered occurrence labels and independent locations. Ambiguous alignment exposes alternatives without snapping to the first same-value text. Unmatched text remains visible in a separate group. A page-only reader has a page-level list, not a guessed box.

## Journey C — ordinary searchable scan

A legitimate invisible OCR layer is a control, not a scary discovery. If named readings agree in the checked region, state that limited agreement. If OCR has not run, display that fact rather than “no differences”. A successfully empty native read explains that the page may still contain visible marks; it does not claim blankness. Unsupported structural checks remain visible in the coverage drawer even when other requested checks finish.

## Journey D — export and reopen

“Keep this evidence” opens the contents preview. Default selection includes only selected text, selected crop(s), relevant reader configuration, document digest, transform/coverage context and limits. Original PDF, original filename and notes default off. User sees the actual crop and a clear warning that it may reveal nearby information. Selecting original PDF changes the replay status and warning to include every page and hidden content. Download HTML for a person, JSON for reopening. No share-link/upload feature exists.

Open saved JSON locally. Validate before rendering any asset. Missing originals leave a useful evidence-only view; “Choose matching original” verifies bytes before attaching. Unsupported schema gets an explicit migration/version message. HTML is not an input format. A malicious report cannot fetch missing assets or execute a recorded command.

## Journey E — reader upgrade

The developer follows the local CLI example, creates two explicit isolated reader profiles, runs the same frozen corpus, and compares stored reports. The default view shows per-file changed/unsupported/errored/incomparable states. A known acceptance rule can mark a regression, but raw change alone cannot. Coverage loss is prominent. Open a selected file's two reports in the same viewer, inspect the anchored differences and export a review artifact. Baseline approval is a separate explicit operation, never a “fix tests” convenience.

## Empty/error states as product behavior

Empty workspace offers a live prepared example and local opener. Unsupported browser features leave the supported reading path accessible and state the missing capability. Network loss during model preparation yields an offline asset message, not a parser error. Malformed file with no successful checks yields failed, not complete. Oversized geometry stops its render before allocation; other completed checks remain. Every inactive action explains its prerequisite in adjacent text, not tooltip alone. No placeholder action is allowed in the finished release.
