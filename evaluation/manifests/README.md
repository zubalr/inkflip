# Evaluation manifests (T36, evaluation custodian)

This directory holds the frozen split manifests and the held-out
evaluation plan. It holds **no held-out label payloads** — those never
live in any checkout.

## Files

- `development.corpus.json` — contract `corpus_manifest` (split
  `development`) frozen from `fixtures/manifest.json` development PDF
  entries. Group ids are `<fixture_id>-<family>` lineage keys, so every
  variant and its control twin share one group by construction.
- `public.corpus.json` — same for the `public` fixture split, mapped to
  the contract `public_demo` split. Public/demo cases and their generated
  siblings never enter the untouched claim denominator.
- `evaluation.plan.json` — the custodian's held-out design: the 300 clean
  + 300 supported-failure page minimum across >=12 mechanism/layout groups
  (a measurement design target, not an existing dataset), the pinned
  label-store descriptor, the candidate freeze, and the declared release
  targets. The plan format cannot carry a verdict: every target reports
  UNMET until `scripts/evaluate_inspector.py evaluate` scores a real bound
  run.

## Custody rules (process-level, made structural)

- Held-out and permissioned labels resolve only via
  `scripts/evaluate_inspector.py evaluate --label-root DIR` (or
  `INKFLIP_EVAL_LABEL_ROOT`), and `DIR` must be a directory **outside the
  repository checkout**. A different folder inside the shared tree is not
  custody — the evaluator refuses in-tree label roots by construction.
- The label file must match the plan's pinned `sha256` and `label_count`;
  unattested or stale labels fail closed. Every corpus page must be
  labeled and every label must name a frozen corpus page.
- Artifacts carry label digests and aggregate counts only. The report
  serializer refuses label content (expected findings, incident/consent
  references, per-page truth) before anything is written.
- Permissioned incident labels additionally require a `consent_ref` per
  page; real incident data without consent never enters scoring.

## Commands

```sh
# Regenerate a frozen corpus manifest after a fixture-manifest change:
python3 scripts/evaluate_inspector.py emit-corpus --split development \
    --out evaluation/manifests/development.corpus.json
python3 scripts/evaluate_inspector.py emit-corpus --split public \
    --out evaluation/manifests/public.corpus.json
# Then update the pinned sha256 in evaluation.plan.json (drift is caught
# by --check and the tests).

# Verify committed manifests still match fixtures/manifest.json:
python3 scripts/evaluate_inspector.py emit-corpus --split development \
    --out evaluation/manifests/development.corpus.json --check

# Audit all split manifests for sibling leakage:
python3 scripts/evaluate_inspector.py verify-splits \
    evaluation/manifests/development.corpus.json \
    evaluation/manifests/public.corpus.json \
    evaluation/manifests/evaluation.corpus.json   # when issued

# Standing target verdicts (all UNMET until a bound run):
python3 scripts/evaluate_inspector.py status \
    --plan evaluation/manifests/evaluation.plan.json

# Score a real run (custodian only, labels outside the checkout):
python3 scripts/evaluate_inspector.py evaluate \
    --plan evaluation/manifests/evaluation.plan.json \
    --corpus evaluation.corpus.json --run run.json \
    --label-root /custodian/labels --adjudication adjudication.json \
    --out evaluation-report.json
```
