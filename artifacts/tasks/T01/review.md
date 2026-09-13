# Independent native setup and T01 peer review

Reviewer: `codex-native-review` (independent read-only review). Verdict: **approved for the reviewed candidate; no remaining actionable findings**. Prior P1 is resolved. This review covers native setup changes and revalidates T01 bootstrap behavior; it does not itself close T01 or grant product/release acceptance.

## P1 resolution

`criterion_evidence` now requires nonempty explicit path lists and validates task namespaces. `evidence_digests` reads and rejects absent/empty files. The builder hashes the union of criterion-specific evidence and preserves each criterion’s references. Executed regression coverage rejects narrative, missing, empty and cross-task evidence; an extra manual artifact is bound and later tampering invalidates acceptance. Documentation consistently separates narrative `detail` from evidence paths.

## Fresh checks

- `PYTHONDONTWRITEBYTECODE=1 python3 scripts/task_acceptance.py task T01`: exit 0; collected/passed 49, failed/skipped 0. This executes the effective T01 command through the recorded interpreter mapping. No `--report` or acceptance receipt was generated.
- Native-bootstrap: 2/2 passed. Coordination: 29/29 passed. Registry self-check: 16 commands, exit 0. `git diff HEAD --check`: exit 0.
- Full candidate file hashes remained unchanged during and after these checks (excluding concurrent Beads audit data).

## T01 criteria and scope

1. **Documented command surface:** manifests, package boundaries, isolated Bun configuration, bootstrap entry and registry checks pass. Scaffold remains explicitly unfinished. Dependency installation, Linux product builds and real browser/native feature acceptance belong to later tasks.
2. **Missing/empty runners fail:** tests exercise missing/empty registry, unknown commands, absent Playwright prerequisite, unimplemented fixtures, zero collected tests and required skips/failures; a positive temporary suite confirms the harness does not simply reject everything.
3. **Origin/planning preservation:** independently verified all 301 files in planning/SHA256SUMS.txt; no planning diff from HEAD. Retained license bytes equal the original Git blob at `94f35ce9f9beb1640ddebdc2c72aa379ecebb004`, SHA-256 `3f1e48ee93685ecf2c49f768ad888dc47859b057f3b90c9f04f132315edf0c6d`. Original checkout HEAD and pre-existing modified Dockerfile status match the historical T01 evidence. Current Dockerfile/diff hashes are in the supplementary origin record. This review made no writes there; historical byte preservation beyond the recorded evidence cannot be reconstructed retrospectively.
4. **No unintended network/achievement actions:** inspected registry, harness and CI. No dependency install, remote publishing or deployment commands occur in acceptance/CI; `bun x` uses `--no-install`. GitHub CI necessarily downloads its checkout action and repository, so “no network” here means no extra application/dependency/publishing network action, not zero network traffic. The separately invoked native setup/bootstrap tools intentionally fetch/push under owner approval and are not acceptance registry entries. Missing application runners remain honest failures; bootstrap success is not release evidence.

## Parent handoff

The parent may commit this review as `artifacts/tasks/T01/peer-review.md` and setup evidence after matching the candidate hashes below. Refresh the T01 worker receipt to explicit task-local evidence path lists (its existing narrative format correctly fails the new builder). Commit implementation/review, run fresh committed T01 acceptance with `--report`, bind actual task-local logs/origin evidence, and generate/validate the receipt. This uncommitted-candidate check is review evidence, not a replacement for that post-commit run. No repository edits, Beads writes, commits, network calls or receipt generation were performed by this reviewer.

Native provider execution, Linux binary installation and live Dolt roundtrip were not independently rerun; those remain the parent’s separately gathered setup evidence. Prompt-owned budgets/resume/scope/review rules are sufficient; no daemon enforcement requested.

## Evidence outputs

- `/private/tmp/inkflip-native-rereview-check-1.log` through `-5.log`: actual check output.
- `/private/tmp/inkflip-t01-origin-revalidation.json`: direct origin and planning measurements.
- `/private/tmp/inkflip-native-rereview-manifest.json`: complete checked candidate file SHA-256 manifest and commands.

## Exact candidate

Repository: `/Users/zubair/Code/Projects/pdf project/original`

Base HEAD: `f62f183b77ef2db16670245b5b5fa5096f424a3f`. Candidate is HEAD plus the listed worktree files; no candidate commit yet.

| File | SHA-256 |
| --- | --- |
| `.beads/README.md` | `e186327b16af3ec9aa2dc6fb4871ba177176a34cb446b49e9750f95537f3a4e1` |
| `.beads/interactions.jsonl` | `668f2ae28853b4d47470657ba5d933ad301c3a301c14b55a3ccdf7b9b7b82945` |
| `AGENTS.md` | `e4ea978b7aba1bb229469b6bacb85991324c0cb993030c8ec0349d39c58f8fd0` |
| `START_HERE.md` | `46c131df5b99c91acf392c44a06f6d0b4d1395f0d793198023118558b7fb3237` |
| `docs/ACCEPTANCE.md` | `503cf51e20ee472cd6fef5d0e814745069e8e5e16c1850ca3dc63d3ebd0a2633` |
| `docs/COORDINATION.md` | `7111278d91e9672fa92269677f7ee0db8ab047a4cfc769a87cfb0e4517f65559` |
| `docs/NATIVE_PASSES.md` | `c673f932d1d1b7db5edc8c9f837c4957579a140203d5f51fbaea12d7068e5a9e` |
| `execution/passes.json` | `c6422bc374f260499be118fea44d87fdd49641ac49d69bd44c4adc5753db41c1` |
| `prompts/ANTIGRAVITY.md` | `3ae796dadd1351ba9f97985726d18058dfe8270f9ec599dab85e752b3cb20cc4` |
| `prompts/DEVIN.md` | `d6366b62914118e0437298e14307e39b6cb8214d7f5872df623f3801436a2e78` |
| `prompts/T01.md` | `5b5ec615eaf9e329dc42a78181ab7073ee3b0dc2685f5d5fef5d4d4e99edf014` |
| `prompts/T02.md` | `fc0bde77f667583d32fa520e04ea1e5b393da602fc27f45d983382f655eee73b` |
| `prompts/T03.md` | `938ff9b2792f60be449728352e8bec6405f7204cdf9383ed22362289454b3505` |
| `prompts/T05.md` | `716852a0a448fe896c971446f6e4776e840a76083321b0f43c9d2cde71fb7b88` |
| `prompts/T06.md` | `967876ed8cf85efdbb7951af0f67cd708a3b4f4fb3759c59c24bd672a620e946` |
| `prompts/ZCODE.md` | `e1f332e3f704559f573de06796fff5275a88a3ab4654164dadeb308b9421c326` |
| `scripts/acceptance_receipts.py` | `0fed79999d09273d29c540756ebd51c16595ee9968eef5009b4a486e11e51d93` |
| `scripts/bootstrap_beads.py` | `99d6213ee6bda9a5311d9f22544383ace017e5cf5994f364ea27b028eb5fa491` |
| `scripts/native_pass.py` | `d5a15d8763b1668f1e1c4ee776e506051cf2d7a28277a42d174c442ee9c5b5ff` |
| `tests/bootstrap/test_receipts.py` | `757b334f86d9265032b7c28e57d19d1f5c28eac496ef189f3cbee29c34473123` |
| `tests/coordination/test_native_pass.py` | `163fbf223f3ea5ee1b6155cbddb69a7335ef2ca8a6d85201411eebbb0637eabb` |

---

# Supplemental T01 independent review

Reviewer: codex-sync-review; assigned Bead: pdf-native-sync-review (not mutated).
Verdict: APPROVE bounded fix. No actionable findings.

Scope: current HEAD diff in scripts/native_pass.py and tests/coordination/test_native_pass.py, in /Users/zubair/Code/Projects/pdf project/original. HEAD inspected: eaf6dad30ef314179e7f4c07b91e25f3c420d640. This supplements the previously approved candidate identified by the requester as edeb82f; it does not re-review that candidate or certify overall T01 acceptance.

Exact reviewed Git blob hashes:
- scripts/native_pass.py: c5dd866477cee9e8f7257fcc7eeb52c76247923d
- tests/coordination/test_native_pass.py: 7c677ff6907eda3a45b578a66ff5aa1b219d5bb3

The metadata copy retains all existing fields and nested JSON values, replacing only execution with the structured grant. The synchronized read and update remain inside the canonical admission lock. Full-object replacement is appropriate under the documented sole integration writer: this does not provide cross-clone concurrent-write merging, nor does the contract allow such writers. Integrator, published clean main, readiness, ownership, scope and capacity checks remain intact. The update retains --claim and the task-specific actor; publication still precedes printing the launch grant. No new dispatch bypass or broadened write authority was introduced.

Independent verification:
- Installed bd version 1.2.2 (6c124203e); inspected bd update --help.
- Actual disposable embedded Beads database at /private/tmp/native-sync-review-cqhix694: reproduced --set-metadata execution=<JSON> storing a string, then confirmed --metadata JSON stores execution as an object, preserves nested metadata including false/null/list values and a sibling field, and --claim sets in_progress with assignee zcode-t05.
- Independently inspected the new dispatch-to-status regression. All 30 coordination tests passed using PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/coordination -v.
- Ran that regression against pre-fix HEAD source loaded in memory: reproduced precisely AttributeError: 'str' object has no attribute 'get'. The changed source passes it.
- git diff --check passed.

Limits: the parent's full local-mirror transport/branch/acceptance/resume rerun was still underway at review time and is not claimed here. This fix prevents newly dispatched malformed grants; it does not migrate already persisted string grants. No repository files, existing Beads state, network or production state were mutated by this reviewer. Only disposable temporary test state and this report were written.

---

# Supplemental exact-candidate review

Reviewer: `codex-local-review`
Candidate: `52f6b920f0c870a9c34f92904aa6f17903435920`
Base: `ed50b1d07b8e21b650cb34b43051767ac164473f`
Repository: `/Users/zubair/Code/Projects/pdf project/original`

**Verdict: APPROVE the bounded Local coordinator change. No material findings.** This is independent supplemental review of the exact committed candidate, not provider execution evidence or T01 closure.

The eight-file diff preserves the existing dispatcher contract: local status uses canonical read-only Beads access and the shared admission lock without remote pulls; only the coordinator dispatches from clean, published main and publishes grants. The shared Git role flag is accurately documented as an accident guard. Existing readiness, ownership, capacity, predecessor-receipt and publication checks are unchanged. Local task worktrees leave canonical main available for integration.

The routing instructions match current [Local documentation](https://docs.devin.ai/desktop/devin-local) and [subagent documentation](https://docs.devin.ai/cli/subagents): general inherits the parent model, explore/default routing is separate, conversation history is not inherited, workflows are unsupported, and foreground resume permits native approval. Cloud and paid fallback remain explicitly unauthorized. The [pricing page](https://devin.ai/pricing) confirms the Desktop/CLI SWE-2 offer through October 10, 2026; [quota documentation](https://docs.devin.ai/desktop/accounts/quota) excludes free models from quota consumption. These pages were fetched during this review; account configuration and actual provider routing were not exercised.

Checks actually performed:

- Inspected the complete committed diff, repository guidance, `native_pass.py`, canonical Beads access, acceptance freshness implementation, existing T01 independent reviews, receipt and origin-revalidation record.
- Ran `PYTHONDONTWRITEBYTECODE=1 python3 scripts/task_acceptance.py run verify`: 49 bootstrap, 2 native-bootstrap and 30 coordination tests passed; registry self-check covered 16 commands. Log: `/private/tmp/inkflip-local-review-checks.log`. The nested one-test skipped output is an intentional harness negative-case fixture, not a skipped required suite test.
- `git diff --check ed50b1d..52f6b92` passed. Independently verified all 301 planning manifest hashes. No committed changes to planning or retained origin notices/license in this candidate; historical original-repository preservation remains supported by the existing evidence, not a newly claimed historical measurement.
- Direct freshness check of the candidate's existing T01 acceptance receipt rejects it with `stale receipt: validation inputs changed (AGENTS.md)`. The changed guidance is reviewed and approved here; the coordinator must finish its already-planned fresh run/receipt binding before dispatch relies on T01 acceptance. This report does not make the old receipt current.

Repository and Beads were not mutated by this reviewer. Concurrent coordinator edits to T01 run/receipt evidence were observed and excluded from the committed review scope. No applications, Cloud sessions, external-provider reviews, commits, pushes, or live Beads transport were launched. Prepared app folders and provider execution remain the coordinator's separate verification responsibility.


---

## Delta review — 2026-09-13, evaluated `412fb9b2`

- **Reviewer:** devin-coordinator (acceptance refresh; not the implementing worker for this delta's shared changes)
- **Scope delta:** Owned scope delta since the original review: `scripts/gate.py`,
`scripts/native_pass.py`, `config/acceptance-commands.json`, the bootstrap and
coordination suites changed via the workbench-admission merge (`879ff3b`) and
the receipt-freshness work. `execution/overrides.json` gained a command
adaptation (fixtures suite under the pinned uv env). Reviewed the gate staleness
logic and command registry while refreshing these receipts: the gate correctly
flagged all stale receipts rather than silently accepting them.
- **Fresh run:** Re-ran all registered commands at `412fb9b2`: **56/56 green**, zero failures.
- **Verdict:** prior review stands; delta introduces no acceptance-relevant regression.
