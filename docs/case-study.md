# Case study: investigating a PDF that reads differently from how it looks

*Prepared 2026-09-13 against the `work/zcode/static-release-finish` snapshot.
Every claim links to a reproducible command or test in this repository. No
deployment, adoption, or final-gate success is claimed; the native image and
final visual polish were pending at this date (details in
[limitations](limitations.md) and [launch/CLAIMS-INDEX.md](launch/CLAIMS-INDEX.md)).*

## The user problem

An engineer debugging a document pipeline sees a rendered invoice that says
**$100** while their text-extraction step reads **$1,000**. Both readings are
"correct" — one comes from the marks a renderer paints, the other from the
font's ToUnicode table mapping glyphs to different characters. Screenshots
and copy-paste don't settle it; a ticket with just two numbers invites
argument. What the engineer needs is evidence: the page, both readings named
with their sources, the exact region they came from, and a portable artifact
a second person can open.

## One real synthetic investigation

The repository ships six prepared examples; the opening one is *The amount
that reads differently* (`apps/web/public/examples/amount/`):

1. Open the example from the gallery (or `Open Workspace` with your own PDF).
2. The **Page** view renders `mapping-amount.pdf`: the painted amount reads
   `$100`.
3. The **Reading** view shows the PDF.js native text extraction for the same
   region: `$1,000`. The accessible text-equivalent panel names each reader,
   its version and its occurrence-level output, including the OCR reading of
   the rendered crop (`$100`).
4. **Compare** aligns both readings to the same page space; the disagreement
   is highlighted and the Evidence Slip records it as a finding with the
   readers' raw outputs retained.
5. Each example ships clean controls: `mapping-control.pdf` paints identical
   operators with an identity ToUnicode mapping — pixels match exactly, so
   the divergence is localized to text extraction, not rendering. The amount
   example adds native-reader controls (`native-unicode-*.pdf`) so the same
   question can be asked of the native readers.
6. **Export** writes a portable JSON report or a script-free HTML snapshot —
   scope chosen by the user, notes and page renders opt-in — that a second
   person can open without Inkflip, or reopen in Inkflip to continue.

Reproduce locally: [quickstart](quickstart.md) → `cd apps/web && bun run dev`
→ open the printed URL → gallery → amount card. The gallery viewer also
publishes each example's prepared report (`report.json`) and the exact
fixture digests in its `manifest.json`.

The example generator and its expectations are original to this project
(`fixtures/`, rights recorded in `fixtures/manifest.json`); behavior shown in
one synthetic file under named reader versions is not a claim about PDFs in
general.

## A real reader-upgrade example (native, source-preview)

Upgrading a pipeline's PDF library is where regressions hide. The repository's
reader-upgrade example runs the same corpus through two **version-isolated**
reader profiles and compares under an explicit, immutable acceptance
baseline. On 2026-09-13 this exact sequence was executed on the yielded
native delivery (`work/cursor/native-completion` at `7875076` — merged-state
acceptance pending):

```sh
python scripts/install_reader_profile.py --name before --reader pypdf --version 5.9.0
python scripts/install_reader_profile.py --name after  --reader pypdf --version 6.18.0
inkflip corpus run --manifest examples/reader-upgrade/corpus.json \
  --source-root planning/fixtures --profile before --out runs/before
inkflip corpus run --manifest examples/reader-upgrade/corpus.json \
  --source-root planning/fixtures --profile after  --out runs/after
inkflip baseline create --run runs/before --rules examples/reader-upgrade/upgrade-rules.json \
  --out baselines/before.json --approved-by local-reviewer \
  --rationale 'Explicit local reader upgrade acceptance policy'
inkflip compare baselines/before.json runs/after --rules examples/reader-upgrade/upgrade-rules.json \
  --out comparisons/upgrade
```

Observed on that date: both corpus runs completed; `--resume` re-ran
idempotently; baseline creation succeeded and a second creation attempt over
the same output was refused (exit 2 — baselines never auto-refresh); the
reader-upgrade comparison reported **unchanged** across the pypdf 5.9.0 →
6.18.0 upgrade; `inspect`, `validate`, `report` (script-free HTML) and
`replay` all completed on the F01 fixture. The comparison separates *changed*
from *regressed*: a change is only a regression when a declared rule in the
approved baseline forbids it.

This capability is **source-preview on the yielded native branch**, not yet
merged main-line or accepted release capability, and the container image
that will carry it is still pending.

## What this tool cannot tell you

- A disagreement between readers is a fact about two readings — it does not
  identify which is correct, and it is never a judgment about a document's
  safety, authenticity or intent.
- OCR reads rendered pixels (English model, bounded per-run budget); it is
  evidence with a named engine and version, not ground truth.
- Coverage is finite and shown: silence on unchecked pages means nothing.
- Alignment abstains when correspondence is ambiguous; an abstention is
  honesty, not a score.
- Offline readiness covers exactly the release's prepared files; documents
  never enter the offline cache. The no-egress claim is the tested browser
  path on the tested builds ([tests/privacy/README.md](../tests/privacy/README.md)),
  not a general security guarantee.
- No repair, sanitization, redaction certification, fraud detection or
  document scoring — by design.

## Reproduction

| Claim | Reproduce with |
| --- | --- |
| Browser investigation flow | [docs/quickstart.md](quickstart.md#build-and-check); suites `bun run test:browser`, `test:a11y`, `test:visual` |
| Six prepared examples | `apps/web/public/examples/` + `scripts/prepare_examples.py --check` |
| No document egress | `bun run test:privacy` (canary: cold/warm/offline/receipt) |
| Offline prepare/remove semantics | offline cache suite (`tests/privacy/cache.spec.ts`) + user guide's *Working offline* |
| Native reader-upgrade example | sequence above on the yielded native delivery; the companion CLI/CORPUS/READER_UPGRADE guides are delivered on that branch and arrive in the tree with its merge |
| Distribution surface | `python3 scripts/check_distribution.py --release` |
| Deployment preflight | `python3 scripts/check_static_dist.py apps/web/dist --config wrangler.json` |

## Development history

Inkflip is original code; its upstream lineage and material influences are
recorded in [ORIGIN](ORIGIN.md) and [ATTRIBUTION](ATTRIBUTION.md), and the
commit/validation history in [development-history.md](development-history.md)
is the observable record of how it was built. Licenses: project MIT
("Copyright (c) 2026 zubair"); third-party notices under
[distribution/README.md](distribution/README.md).
