# Repository origin and migration

**Decision: documented snapshot import, not preserved full Git ancestry.** The new product has a new canonical domain model and runtime. Importing the challenge history wholesale would obscure that boundary. A snapshot import is legitimate only when its exact origin and reused material remain explicit.

The original remote repository remains untouched. Bootstrap initializes a new local repository with no remote. The first real commit records this planning package and the approved architecture. The source import commit retains the original MIT notice from `mib-intake@94f35ce9f9beb1640ddebdc2c72aa379ecebb004` and an origin manifest; it imports **no legacy runtime module, classifier, calibration table, vocabulary, prediction file or dataset**. This is a deliberately small snapshot, not an attempt to disguise copied implementation as new work.

Retained file: original `LICENSE`, preserved under `third_party/origin/mib-intake/LICENSE` when T01 creates the target repository. Conceptually reused/independently implemented: span metadata and explicit reason retention, output/evidence separation, bounded OCR escalation, raw-box preservation and adversarial clean-twin tests. The new fixed fixture generator in this package is original and not copied from the challenge generator. Its ToUnicode/cover/geometry recipes are separate from alien visa examples.

Potential future copied code is not preauthorized by this plan. Before a port, record repository, exact commit/file, original author/notice, required license and the modifications. Preserve notice in the actual copied file and distribution. Material inspiration is acknowledged even when the code is independently written. Do not claim multiple derivative challenge implementations are independent corroboration.

## Incremental engineering history

Commit coherent capabilities: monorepo/CI; contracts/fixtures; geometry; reader adapters; live end-to-end inspection; export/import; native supervision; regression; quality/rights; release. Do not manufacture tiny commits or backdate. Feature branches/worktrees use task IDs and real base commit. PR description includes task, evidence, test commands actually run, visual review where applicable, contract changes, license impact and limitations.

Record actual agent use in `execution/receipts/<task>.json`: provider/mode/model as observable, source inputs, commit IDs, owner interventions, review outcome and failures. If a provider does not expose a field, record `not_observable`; do not invent internal chain-of-thought or autonomous hours. Real owner decisions belong in a concise build log, not a claim that every generated line was hand-authored.

## Legacy reproduction is separate

The original README's Docker invocation remains the historical recipe; it is not rerun or repaired during this planning pass. A reproduction should use the exact legacy checkout, appropriately licensed dependencies, recorded image build inputs and authorized challenge data. Do not silently upgrade the legacy stack to make it build while retaining the old score label. If it no longer reproduces, preserve that result as an environment limitation. The new inspector does not depend on resolving historical reproducibility.
