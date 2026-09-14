# Case study: investigating a PDF that reads differently from how it looks

Try the [live example](https://inkflip-rose.vercel.app/#/workspace?example=amount).
The source PDF and captured reader outputs are included in the repository.

## The user problem

The sample PDF displays **$100**, but text extraction returns **$1,000**.
Its font maps the displayed glyphs to different characters through the
ToUnicode table. Inkflip puts the rendered page and the named reader outputs
together so the difference can be inspected and saved in a report.

## Inspect the amount example

The repository ships six prepared examples. Start with *An amount changes
during extraction* (`apps/web/public/examples/amount/`):

1. Open the example from the gallery (or **Check a PDF** with your own file).
2. The **Page** view renders `mapping-amount.pdf`: the painted amount reads
   `$100`.
3. The **Reading** view shows the PDF.js native text extraction for the same
   region: `$1,000`. The accessible text-equivalent panel names each reader,
   its version and its occurrence-level output, including the OCR reading of
   the rendered crop (`$100`).
4. **Compare** aligns both readings to the same page space; the disagreement
   is highlighted and the Differences panel records it as a finding with the
   readers' raw outputs retained.
5. Each example ships clean controls: `mapping-control.pdf` paints identical
   operators with an identity ToUnicode mapping; pixels match exactly, so
   the divergence is localized to text extraction, not rendering. The amount
   example adds native-reader controls (`native-unicode-*.pdf`) so the same
   question can be asked of the native readers.
6. **Save report** exports the selected evidence. HTML opens without Inkflip;
   JSON reopens in the app. The original PDF and notes are included only
   when selected.

Reproduce locally: [quickstart](quickstart.md) → `cd apps/web && bun run dev`
→ open the printed URL → gallery → amount card. The gallery viewer also
publishes each example's prepared report (`report.json`) and the exact
fixture digests in its `manifest.json`.

The example generator and its expectations are original to this project
(`fixtures/`, rights recorded in `fixtures/manifest.json`); behavior shown in
one synthetic file under named reader versions is not a claim about PDFs in
general.

## Compare reader versions with the native CLI

Upgrading a pipeline's PDF library is where regressions hide. The repository's
reader-upgrade example runs the same corpus through two **version-isolated**
reader profiles and compares under an explicit, immutable acceptance
baseline. This sequence was executed on 13 September 2026:

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
the same output was refused (exit 2; baselines never auto-refresh); the
reader-upgrade comparison reported **unchanged** across the pypdf 5.9.0 →
6.18.0 upgrade; `inspect`, `validate`, `report` (script-free HTML) and
`replay` all completed on the F01 fixture. The comparison separates *changed*
from *regressed*: a change is only a regression when a declared rule in the
approved baseline forbids it.

Docker recipes and the recorded image-specific checks are described in
[distribution](distribution/README.md).

## What this tool cannot tell you

- A disagreement between readers is a fact about two readings; it does not
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
- Inkflip does not repair, sanitize, certify redactions or score documents.

## Reproduction

| Claim | Reproduce with |
| --- | --- |
| Browser investigation flow | [docs/quickstart.md](quickstart.md#build-and-check); suites `bun run test:browser`, `test:a11y`, `test:visual` |
| Six prepared examples | `apps/web/public/examples/` + `scripts/prepare_examples.py --check` |
| No document egress | `bun run test:privacy` (canary: cold/warm/offline/receipt) |
| Offline prepare/remove semantics | offline cache suite (`tests/privacy/cache.spec.ts`) + user guide's *Working offline* |
| Native reader-upgrade example | sequence above; [reader-upgrade guide](READER_UPGRADE.md) |
| Distribution surface | `python3 scripts/check_distribution.py --release` |
| Deployment preflight | `python3 scripts/vercel_output.py prepare` then `python3 scripts/vercel_output.py check` after building |

## Development history

Inkflip is original code; its upstream lineage and material influences are
recorded in [ORIGIN](ORIGIN.md) and [ATTRIBUTION](ATTRIBUTION.md), and the
commit/validation history in [development-history.md](development-history.md)
is the observable record of how it was built. Licenses: project MIT
("Copyright (c) 2026 zubair"); third-party notices under
[distribution/README.md](distribution/README.md).
