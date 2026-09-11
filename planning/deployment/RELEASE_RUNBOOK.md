# Build, release and rollback runbook

These commands run in the target implementation repository after the tasks have created the application harness. No remote mutation or paid provisioning occurred during planning.

## Local verification

```sh
pnpm install --frozen-lockfile
uv sync --project native --frozen
pnpm verify
pnpm test:browser
pnpm test:privacy
pnpm test:a11y
pnpm test:visual
uv run --project native python -m pytest
pnpm build
python scripts/check_static_dist.py apps/web/dist --config wrangler.json
pnpm exec wrangler dev --config wrangler.json
```

Preparation/install is explicit and may access package registries. Inspection and native container tests run with network blocked after verified assets are available. `pnpm build` must not enable cloud services or deploy. `check_static_dist.py` rejects any main/script/bindings, unexpected external URLs, oversize assets and missing model/license manifest. Verify public examples against the built asset versions, not a development cache.

## Freeze a release candidate

On the merged integration branch: run all gate tests; record actual commit, lock hashes, model/build hashes, browsers/OS/AT, geometry metrics, no-egress capture, native fixture results, acceptance-rule results, SBOM/notices and exact limitations. Scan for private incident data, secrets, uploaded files, accidental absolute host paths and unreviewed generated docs. Archive the exact `dist` tree and native artifacts with manifest/checksums. There are no placeholder asset hashes in a releasable build.

The release manifest binds each public claim to evidence. The owner approves publication, license and domain/account selection. Do not invent approvals from an unattended worker session. G1–G4 must pass before public launch actions; unresolved experimental candidates are explicitly rejected or unavailable, not silently shipped.

## Deploy, only after owner authorization

```sh
pnpm exec wrangler deploy --config wrangler.json --dry-run
# Owner authenticates through the approved secure local mechanism.
pnpm exec wrangler deploy --config wrangler.json
```

Use the exact pinned Wrangler 4.131.0 family or a documented compatible security patch. Never place tokens in shell history/prompt files. A narrow environment secret or owner-operated login is acceptable. Capture deployed version ID and static artifact hash. Run route/header/no-egress/offline checks against the selected hostname. If owner input is absent, deployment remains blocked while local artifacts remain complete.

## Rollback

Preferred universal rollback for this asset-only project: restore the previously archived, checksum-verified static `dist` and its exact config, then redeploy with the same reviewed uploader. This avoids assuming a version command supports every asset/config change. Where current Cloudflare version rollback is verified for the actual deployment, it can be used with the recorded version ID and the same post-rollback checks. Neither path edits user reports or baseline files.

Steps: stop launch promotion; identify the last accepted artifact from the release ledger; verify its checksum; redeploy that exact static tree; verify index/model compatibility, headers, absence of scripts/bindings and privacy canary; document the rollback and affected capability. Do not delete an old report or refresh goldens to conceal the defect. A compromised model/build requires invalidating its static cache identity and an explicit correction notice.

## Final completion

Tag a real release only after G5 actual-route checks and owner approval. Publish source, static self-host artifact, native installation/replay docs, fixed example PDFs/manifests, notices and known limits. Record real agent/owner/reviewer contributions. No adoption, benchmark or hiring claim is implied by releasing a specification or a tagged build.
