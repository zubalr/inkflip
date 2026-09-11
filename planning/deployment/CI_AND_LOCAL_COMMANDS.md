# Early CI and local command contract

T01 creates a checked command harness and a minimal early CI job. Tasks add tests in their owned modules. At no stage may a command exit successfully because its test list is empty. The same commands must run locally; hosted CI is a convenience, not a hosted ingestion service or prerequisite to using the CLI.

| Command | Meaning / evidence |
|---|---|
| `pnpm verify` | Typecheck all shared packages/web; lint; unit/contract suite; generated-type drift |
| `pnpm test:browser` | Playwright core own-file/fixture/cancel/replace/export flow across chosen engines |
| `pnpm test:privacy` | Cold/warm/offline canary network + storage capture on built site |
| `pnpm test:a11y` | Automated accessible component checks plus receipt requirement for manual AT |
| `pnpm test:visual` | Approved desktop/narrow/reduced-motion/error-state screenshots; no auto-update |
| `pnpm test:fixtures` | Regenerate controlled fixtures and assert byte/source manifest expectations |
| `pnpm test:regression` | Baseline immutability, coverage loss, invalid comparison, rule exit behavior |
| `uv run --project native python -m pytest` | Native adapter/CLI/process/resource/import tests |
| `pnpm build` | Static and shared Node build only; no deployment |
| `python scripts/check_static_dist.py apps/web/dist --config wrangler.json` | No dynamic server artifact/paid bindings; hashes/sizes/notices/external asset allowlist |
| `python scripts/gate.py G1` through `G5` | Execute registered tests and verify actual evidence; G5 needs explicit deployed target |

PR lanes: fast deterministic contracts/math/copy first; browser/native integration next; expensive cross-device/fault/evaluation on relevant merged candidates and release. This is dependency/resource scheduling, not reduced test coverage. Cache keys include lockfile, environment and fixture identity. Tests involving imported/untrusted content run without secrets and cannot upload private artifacts. Pull-request workflows must not use privileged `pull_request_target` to execute untrusted code.

The example GitHub workflow in `deployment/examples/ci.yml` is deliberately credential-free with read-only repository permission. Its action revisions are illustrative major tags until T02 resolves full commit SHAs; that unresolved supply-chain pin blocks publishing the workflow as hardened. No claim of secure pinning is made for a template. The provider-independent shell example is sufficient for local operation.

Visual/golden/acceptance baseline changes require an independent reviewer and rationale showing the underlying behavior. Workers may not delete assertions, loosen thresholds, blanket-skip browsers or replace expected values simply to make tests green. CI must fail on unexplained skips in required profiles. Report exact run/skip counts and platform, not only a green badge.
