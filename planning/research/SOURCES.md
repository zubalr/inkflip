# Primary-source ledger

Access date: **2026-09-11**. Source inspection is not runtime validation. These records distinguish inspected excerpts, primary documents, executed local probes and reported leads. The full attached discovery Markdown was read; missing historical CSV/ZIP files were not sought.

## S01

**mib-intake / mib/pdfio.py** — [94f35ce9f9beb1640ddebdc2c72aa379ecebb004](https://github.com/zubalr/mib-intake/blob/94f35ce9f9beb1640ddebdc2c72aa379ecebb004/mib/pdfio.py).

**source-verified**. Color/alpha/crop heuristics and Span geometry exist; no complete compositing model.

Remaining: Read source, not executed on challenge corpus.

## S02

**mib-intake / mib/extract.py** — [94f35ce9f9beb1640ddebdc2c72aa379ecebb004](https://github.com/zubalr/mib-intake/blob/94f35ce9f9beb1640ddebdc2c72aa379ecebb004/mib/extract.py).

**source-verified**. Observation loses geometry; fallback boxes are separate; value deduplication can erase occurrences.

Remaining: Relevant definitions/absorption paths inspected; not every branch exercised.

## S03

**mib-intake / mib/schema.py** — [94f35ce9f9beb1640ddebdc2c72aa379ecebb004](https://github.com/zubalr/mib-intake/blob/94f35ce9f9beb1640ddebdc2c72aa379ecebb004/mib/schema.py).

**source-verified**. Plausible fallback values meet a challenge-specific output contract.

Remaining: Do not import fallback semantics.

## S04

**mib-intake / MEMO.md** — [94f35ce9f9beb1640ddebdc2c72aa379ecebb004](https://github.com/zubalr/mib-intake/blob/94f35ce9f9beb1640ddebdc2c72aa379ecebb004/MEMO.md).

**source-verified**. 137.89 is explicitly in-sample; model-fold diagnostic has globally fitted path prior.

Remaining: No score reproduction; no private ranking.

## S05

**mib-intake / APPENDIX.md** — [94f35ce9f9beb1640ddebdc2c72aa379ecebb004](https://github.com/zubalr/mib-intake/blob/94f35ce9f9beb1640ddebdc2c72aa379ecebb004/APPENDIX.md).

**source-verified**. Output-only repairs, calibration caveats and environment-sensitive OCR matter.

Remaining: Documented gains are author reports, not reproduced results.

## S06

**mib-intake / mib/cli.py** — [94f35ce9f9beb1640ddebdc2c72aa379ecebb004](https://github.com/zubalr/mib-intake/blob/94f35ce9f9beb1640ddebdc2c72aa379ecebb004/mib/cli.py).

**source-verified**. Batch submits extraction then finalizes with corpus context and writes at end.

Remaining: Relevant lifecycle section inspected; no challenge run.

## S07

**mib-intake / mib/model.py** — [94f35ce9f9beb1640ddebdc2c72aa379ecebb004](https://github.com/zubalr/mib-intake/blob/94f35ce9f9beb1640ddebdc2c72aa379ecebb004/mib/model.py).

**source-verified**. Joblib-loaded legacy classifier, blending and safety decisions are task-specific.

Remaining: Binary was not deserialized. No new product confidence model.

## S08

**mib-intake / tools/train_adjudicator.py** — [94f35ce9f9beb1640ddebdc2c72aa379ecebb004](https://github.com/zubalr/mib-intake/blob/94f35ce9f9beb1640ddebdc2c72aa379ecebb004/tools/train_adjudicator.py).

**source-verified**. Global path probabilities and corpus context precede folds.

Remaining: Do not treat estimator CV alone as untouched end-to-end evaluation.

## S09

**mib-intake / tests/test_pdfio.py** — [94f35ce9f9beb1640ddebdc2c72aa379ecebb004](https://github.com/zubalr/mib-intake/blob/94f35ce9f9beb1640ddebdc2c72aa379ecebb004/tests/test_pdfio.py).

**source-verified**. Focused visible/white/invisible/off-crop fixtures; broader control coverage missing.

Remaining: Read, not executed in legacy environment.

## S10

**mib-intake / requirements.txt** — [94f35ce9f9beb1640ddebdc2c72aa379ecebb004](https://github.com/zubalr/mib-intake/blob/94f35ce9f9beb1640ddebdc2c72aa379ecebb004/requirements.txt).

**source-verified**. Legacy dependency pins include PyMuPDF and OCR/model stack.

Remaining: Not adopted as new product dependency lock.

## S11

**mib-intake / Dockerfile** — [94f35ce9f9beb1640ddebdc2c72aa379ecebb004](https://github.com/zubalr/mib-intake/blob/94f35ce9f9beb1640ddebdc2c72aa379ecebb004/Dockerfile).

**source-verified**. Floating base/apt inputs and no non-root USER despite offline run instructions.

Remaining: Not a proof of parser isolation or bit-reproducible image.

## S12

**mib-intake / LICENSE** — [94f35ce9f9beb1640ddebdc2c72aa379ecebb004](https://github.com/zubalr/mib-intake/blob/94f35ce9f9beb1640ddebdc2c72aa379ecebb004/LICENSE).

**source-verified**. Own source is MIT; dependency obligations remain separate.

Remaining: No blanket legal conclusion for combined stack.

## S13

**mib-intake / README.md** — [94f35ce9f9beb1640ddebdc2c72aa379ecebb004](https://github.com/zubalr/mib-intake/blob/94f35ce9f9beb1640ddebdc2c72aa379ecebb004/README.md).

**source-verified**. Historical product, source layout and license disclosures.

Remaining: README is not runtime evidence.

## S14

**Challenge evaluator** — [38ce8883dea9f87c27a8a95f134e54fe8b673064](https://github.com/8090-inc/mib-doc-challenge/blob/38ce8883dea9f87c27a8a95f134e54fe8b673064/scripts/evaluate.py).

**source-verified**. Weighted fields, blank flag normalization, unrecoverable exclusions, payoff and Brier objective explain old compromises.

Remaining: Relevant 1–240 lines inspected, not rerun.

## S15

**Vishnu visibility** — [ca1a1e24c495b08d0d6e4b92c1723389247e2ca2](https://github.com/vishnualpha/mib-doc-challenge-solution/blob/ca1a1e24c495b08d0d6e4b92c1723389247e2ca2/mib/visibility.py).

**source-verified**. Retained reasons, shared seqno, preceding fills versus later covers; thresholds are approximations.

Remaining: No reproduction; trace type must not be assumed identical to all PDF Tr values.

## S16

**Henry reader and memo** — [f9f751ee7ea779cc549c3bcff5960020c2517e72](https://github.com/henrybrewer00-dotcom/mib-doc-solution/blob/f9f751ee7ea779cc549c3bcff5960020c2517e72/mibdoc/reader.py).

**source-verified**. Reader excerpts and memo identify unrelated border ink as a failure of box-ink corroboration.

Remaining: Reader excerpts, not full file audit or runtime proof; memo and PR differ about presence features.

## S17

**Handeman watchdog tests** — [4313d28b34abc4cef4c89586060f4d3d34848c88](https://github.com/handemanai/mib-doc-challenge-solution/blob/4313d28b34abc4cef4c89586060f4d3d34848c88/tests/test_watchdog.py).

**source-verified**. Tests distinguish explicit empty success, retries, recycling and parent-supervised hangs.

Remaining: First 150 lines and reviewer guide inspected; tests not executed.

## S18

**BMD attribution** — [1846faa62473a2a5691db314ccefe6df82f15268](https://github.com/bmdhodl/mib-doc-solution/blob/1846faa62473a2a5691db314ccefe6df82f15268/ATTRIBUTION.md).

**source-verified**. Pinned derivative lineage and explicit exclusions prevent false independent-evidence claims.

Remaining: Their scores and artifact inventories are author reports.

## S19

**Arthur experiment ledger** — [80453d557e3b57d8f426bb81001a7e12ea087d90](https://github.com/arthurmichel00/mib-doc-solution/blob/80453d557e3b57d8f426bb81001a7e12ea087d90/LEVERS.md).

**source-verified**. Shipped, dormant, redundant, unproven and harmful experiments are distinct.

Remaining: Relevant ledger sections inspected, not all code or reported experiments executed.

## S20

**Selective OCR** — [1a0ccbedcafaa0d5499f7bb13a3108f754199e32](https://github.com/zeroinfinity03/mib-doc-challenge-solution/blob/1a0ccbedcafaa0d5499f7bb13a3108f754199e32/step2_ocr.py).

**source-verified**. Targeted rereading can be bounded; fixed top-band and text dedupe are template-specific.

Remaining: A replacement text without updated geometry is unsuitable for this product; no gain reproduced.

## S21

**Shrey geometry/candidate code** — [5508a8bc36faacdafbea768554923346f895a8c5](https://github.com/ShreyShingala/ocr-document-pipeline-challenge/tree/5508a8bc36faacdafbea768554923346f895a8c5).

**source-verified**. Indexed row_restore/closed_vocab/ocr excerpts provide narrow geometry leads.

Remaining: Discovery-level excerpts and PR only; not an adopted implementation.

## S22

**PDF.js API** — [selected release 6.3.289; mutable API documentation](https://mozilla.github.io/pdf.js/api/draft/module-pdfjsLib.html).

**source-verified**. getDocument/getTextContent/getViewport/RenderTask and TextItem transform are the public browser boundary.

Remaining: No glyph paint provenance promised. Exact selected browser build not executed here.

## S23

**PDF.js release** — [6.3.289](https://github.com/mozilla/pdf.js/releases/tag/v6.3.289).

**source-verified**. Published release with modern and legacy distributions.

Remaining: Download unavailable in this container; package lock/security audit and browser probe required.

## S24

**Tesseract.js API and README** — [7.0.0](https://github.com/naptha/tesseract.js/blob/v7.0.0/src/index.d.ts).

**source-verified**. Image input, explicit blocks output, createWorker options and termination; rasterize PDFs first.

Remaining: Browser worker/CSP/offline combination must be executed after npm install.

## S25

**Tesseract English data** — [65727574dfcd264acbb0c3e07860e4e9e9b22185](https://github.com/tesseract-ocr/tessdata_fast/tree/65727574dfcd264acbb0c3e07860e4e9e9b22185).

**executed**. Official tree eng blob matches installed 4,113,088-byte model used by probe. Apache-2.0 license read.

Remaining: Model is not bundled in this planning ZIP; fetch and verify exact hash at product bootstrap.

## S26

**pypdfium2 API and licensing** — [5.8.0 installed / PDFium 149.0.7825.0](https://pypdfium2.readthedocs.io/en/stable/readme.html).

**executed**. Native rendering/text are usable; concurrent PDFium threads are unsafe; wrapper/build notices separate.

Remaining: Public helper API is a support-model choice; cross-platform parity and full packaged wheel licenses gate release.

## S27

**PDFium text object API** — [public header; symbols found in installed PDFium 149.0.7825.0](https://pdfium.googlesource.com/pdfium/+/refs/heads/main/public/fpdf_edit.h).

**source-verified**. FPDFTextObj_GetTextRenderMode and FPDFTextObj_GetText are real API names.

Remaining: Availability verified, not comprehensive object-to-character binding or paint-order correctness.

## S28

**pypdf release** — [6.18.0 / source 18e4c226a4c2dd7f187854015f52e87350f84161](https://pypi.org/project/pypdf/6.18.0/).

**source-verified**. Choose current pinned pypdf for page dictionary metadata and independent page-level text. BSD-3-Clause.

Remaining: Executed exploratory pypdf was 5.9.0, not this selected version; rerun before integration.

## S29

**Vite React TS template** — [1aec41b32510681131c6fa6978ddc227fa6f3aa8](https://github.com/vitejs/vite/blob/1aec41b32510681131c6fa6978ddc227fa6f3aa8/packages/create-vite/template-react-ts/package.json).

**source-verified**. Pins usable starting families: Vite 8.3, React 19.2.8, TS 6.0.2, plugin-react 6.1.1.

Remaining: Resolve transitive lock and build; a template is not a security audit.

## S30

**Static Next.js alternative** — [inspected blob c5fa38612c66070efe46dd1aa3aae4d7b426d18f](https://github.com/vercel/next.js/blob/canary/docs/01-app/02-guides/static-exports.mdx).

**source-verified**. output:export produces static files; Next.js does not inherently require paid SSR.

Remaining: Rejected here for unnecessary conventions, not inability to host statically.

## S31

**pnpm release** — [12.3.4](https://github.com/pnpm/pnpm/releases/tag/v12.3.4).

**source-verified**. Pinned package manager; one integration owner controls lockfile.

Remaining: Registry fetch unavailable in current container.

## S32

**Ajv package** — [8.17.1](https://github.com/ajv-validator/ajv/blob/v8.17.1/package.json).

**source-verified**. MIT validator; use build-time standalone output for browser strict CSP.

Remaining: Browser compilation and compatibility test still required.

## S33

**Cloudflare static billing** — [documentation last updated 2026-04-23](https://developers.cloudflare.com/workers/static-assets/billing-and-limitations/).

**source-verified**. Static requests/storage documented without incremental charge; Worker execution billed separately.

Remaining: No account inspection, deployment or perpetual price guarantee.

## S34

**Cloudflare static setup** — [documentation accessed 2026-09-11](https://developers.cloudflare.com/workers/static-assets/get-started/).

**source-verified**. Static-site route supports local wrangler dev and deploy; deploy can be declined during setup.

Remaining: Use explicit config, not scaffold defaults that create a script.

## S35

**Cloudflare headers** — [documentation accessed 2026-09-11](https://developers.cloudflare.com/workers/static-assets/headers/).

**source-verified**. Static _headers controls response headers.

Remaining: Validate on actual preview; script-handled responses have different behavior, and none are allowed here.

## S36

**Cloudflare limits** — [documentation accessed 2026-09-11](https://developers.cloudflare.com/workers/platform/limits/).

**source-verified**. Per-asset size and number limits must be checked before upload.

Remaining: Exact current account quotas rechecked in deploy preflight; planning target per file <24 MiB.

## S37

**Wrangler release** — [4.131.0 published 2026-09-10](https://github.com/cloudflare/workers-sdk/releases/tag/wrangler%404.131.0).

**source-verified**. Pin actual Wrangler release, not monorepo latest helper package.

Remaining: Dry-run and paid-route proof not executed here.

## S38

**Devin execution capabilities** — [mutable documentation accessed 2026-09-11](https://docs.devin.ai/work-with-devin/advanced-capabilities).

**source-verified**. Managed isolated sessions are documented; operator-driven separate sessions remain a viable arrangement.

Remaining: No account entitlement, model availability, quotas or promotion permanence verified; no Devin worker was launched here.

## S39

**PyMuPDF licensing** — [accessed 2026-09-11](https://artifex.com/licensing).

**source-verified**. AGPL/commercial choice is not erased by an MIT application notice or API boundary.

Remaining: Qualified advice required for any later PyMuPDF redistribution; excluded from primary product.

## S40

**Show HN guidelines** — [accessed 2026-09-11](https://news.ycombinator.com/showhn.html).

**source-verified**. A directly tryable artifact fits the channel better than a waitlist.

Remaining: No reach, adoption or hiring prediction.

## S41

**Existing Inkflip name use** — [prior attached research; basic conflict retained](https://www.etsy.com/shop/Inkflip).

**reported**. Keep a configurable provisional identity; collision is already enough not to claim clearance.

Remaining: No trademark or domain clearance; no name search expansion required.

## S42

**WCAG 2.2** — [W3C Recommendation, accessed 2026-09-11](https://www.w3.org/TR/WCAG22/).

**source-verified**. Keyboard access, focus visibility, text alternatives, contrast and reflow motivate explicit product tests.

Remaining: Automated tests cannot establish complete conformance; manual AT/device tests are release work.

## S43

**Ajv standalone validators** — [Ajv 8 documentation, accessed 2026-09-11](https://ajv.js.org/standalone.html).

**source-verified**. Precompile trusted schemas into static validator modules rather than require runtime schema code generation.

Remaining: Exact selected schema generation/build not executed because npm retrieval is blocked.

## S44

**Legacy calibration artifact** — [94f35ce9f9beb1640ddebdc2c72aa379ecebb004](https://github.com/zubalr/mib-intake/blob/94f35ce9f9beb1640ddebdc2c72aa379ecebb004/policy/calibration.json).

**source-verified**. Artifact states 1,000 training rows, fitted path distributions and source; no transfer to new inspector confidence.

Remaining: Read JSON only. No model deserialization or benchmark reproduction.

## S45

**Evaluation framing correction** — [634daacb02a944ddf41733ddd2e969449681ec3c](https://github.com/zubalr/mib-intake/commit/634daacb02a944ddf41733ddd2e969449681ec3c).

**source-verified**. Actual commit/diff corrected globally calibrated model-fold framing; intermediate score was 137.83, not final 137.89.

Remaining: History inspection, not recreation of the evaluations.

## S46

**PR 91 shared-substrate portfolio** — [07b1c9659104e3f79b88ffba130e4a1576beefc7](https://github.com/speculator19/mib-portfolio/blob/07b1c9659104e3f79b88ffba130e4a1576beefc7/README.md).

**source-verified**. README identifies three vendored pipelines including zubalr on shared rendering/OCR; this is correlated lineage, not independent evidence.

Remaining: README inspected; reported scores, full attribution and runtime not independently audited.

<a id="s47"></a>
## S47 — RapidOCR selected experiment release

Source: https://github.com/RapidAI/RapidOCR/releases/tag/v3.8.1. Accessed 2026-09-11; release `v3.8.1`. Release metadata confirms this bounded experiment candidate exists. The default product remains Tesseract. No package installation, weight provenance audit or benchmark was executed.

Decision: Bounded optional experiment only; default unavailable until accepted. Remaining verification: Installed assets, APIs, exact weight/bundle rights, memory, geometry and useful-finding value.

<a id="s48"></a>
## S48 — EmbedPDF selected secondary-browser experiment release

Source: https://github.com/embedpdf/embed-pdf-viewer/releases/tag/v2.15.0. Accessed 2026-09-11; release `v2.15.0`. Release inventory includes pdfium-dist.tar.gz, 2,661,637 bytes, SHA-256 31cba71f5620bec3ae2aab6606f148e42cba0cd34d56cf5b54998d771e62bd42. This archive size is not an installed WASM-memory measurement. API, full bundle notices and runtime value remain the P12 experiment.

Decision: Bounded optional experiment only; default unavailable until accepted. Remaining verification: Installed assets, APIs, exact weight/bundle rights, memory, geometry and useful-finding value.
