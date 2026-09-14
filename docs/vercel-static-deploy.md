# Vercel static publication (GitHub Actions, prebuilt upload)

Inkflip is the existing Vite browser app. This path publishes that static
tree. It does not add a database, accounts, or a replacement landing page,
and it does not run the Python command harness on Vercel.

The frozen `planning/` snapshot still describes the Cloudflare Workers
Static Assets route. That wrangler preflight remains; this file only
documents the Vercel adapter.

## Automatic production path

Reviewed **pushes to `main`** run the existing `verify` workflow. When that
job succeeds, `.github/workflows/deploy-web.yml` checks out the same SHA,
runs the frozen Bun/Python production build, `scripts/vercel_output.py
prepare` + `check`, and `vercel deploy --prebuilt --prod` to the existing
`inkflip` project (`prj_sEtj12msmLcppTxQu8qpbqiXJrL0`).

That is the only automatic production publisher. Do **not** connect the
GitHub repo to Vercel Git integration: dashboard npm/Next defaults would
compete with this path and ship the wrong bytes. Feature branches and pull
requests must not receive the production alias. Concurrency group
`vercel-production` cancels an older in-flight publish so it cannot
overwrite a newer one.

The GitHub Actions secret `VERCEL_TOKEN` is a project-scoped token. Jobs
must not echo it. The `production` GitHub Environment is the deploy gate.

## What is uploaded

A production build (`bun run build` with `INKFLIP_TEST_HOOKS` unset) writes
`apps/web/dist/`. `scripts/vercel_output.py prepare` copies those files into
`.vercel/output/static` and writes Build Output API v3 `config.json` routes
translated from `dist/_headers`. A deployed `_headers` text file is not
equivalent: Vercel does not apply Cloudflare header files.

Missing worker, WASM, or model paths are left as filesystem misses (404).
There is no rewrite to `index.html`. Hash routes (`#/workspace`,
`#/workspace?example=true`) stay on `/`.

`.vercel/` stays gitignored (link metadata and generated output). Source
maps are not copied.

## Local commands (rollback / manual)

From a checkout that already has frozen Bun dependencies and a production
dist:

```sh
python3 scripts/vercel_output.py prepare
python3 scripts/vercel_output.py check
bunx --bun vercel@59.16.0 deploy --prebuilt --prod --yes
```

`vercel.json` pins `framework`, `installCommand`, and `buildCommand` to
`null` so a dashboard rebuild is not treated as Next.js/npm.

Rollback to a previous deployment ID (when one exists):

```sh
bunx --bun vercel@59.16.0 promote <deployment-id> --scope jubairjashim1975gmailcoms-projects
```

## Checks that remain local

`scripts/vercel_output.py check` is a configuration and file-set check.
`tests/deployment/test_github_deploy.py` pins the workflow guards. Existing
`bun run check:static-dist` (wrangler.json + `_headers` + dist manifest) is
unchanged.
