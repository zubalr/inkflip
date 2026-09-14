# Feature and verification reference

The browser app is published at [inkflip-rose.vercel.app](https://inkflip-rose.vercel.app).
This page maps its behavior to source and checks. Test results apply to the
revision and environment where they ran.

| Behavior | Source and checks |
| --- | --- |
| Six synthetic examples with recorded readings | `apps/web/public/examples/`; `python3 scripts/prepare_examples.py --check` |
| Browser-local document processing | `apps/web/src/features/open/`; `bun run test:privacy` |
| Explicit offline preparation and removal | `tests/privacy/cache.spec.ts`; [user guide](../user-guide.md) |
| Portable HTML and JSON reports with selectable content | `tests/reports/selection.spec.ts`; `tests/browser/export.spec.ts` |
| Repeated occurrences and ambiguous matches | `tests/browser/ambiguity.spec.ts`; `apps/web/src/features/viewer/occurrences/` |
| Native reader-upgrade comparisons and immutable baselines | `tests/examples/test_reader_upgrade.py`; [reader-upgrade guide](../READER_UPGRADE.md) |
| Static deployment with browser smoke checks | `.github/workflows/deploy-web.yml`; `tests/deployment/prepublish-smoke.cjs` |
| Distribution inventory and notices | `scripts/check_distribution.py`; [distribution reference](../distribution/README.md) |
| Automated accessibility flows | `tests/a11y/`; [accessibility flows](../accessibility/flows.md) |

The amount example demonstrates one synthetic PDF whose painted `$100`
extracts as `$1,000` under the named readers. It is not a result about all
PDFs or a test of document authenticity. Manual accessibility review,
cross-device performance claims and native-image qualification have their
own limits, described in [limitations](../limitations.md).

The 14 September browser deployment passed verification, the production
build and browser smoke checks before promotion:
[GitHub Actions run](https://github.com/zubalr/inkflip/actions/runs/34867919566).
