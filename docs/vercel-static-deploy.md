# Vercel static publication (GitHub Actions, prebuilt upload)

Inkflip is the existing Vite browser app. This path publishes that static
tree. It does not add a database, accounts, or a replacement landing page,
and it does not run the Python command harness on Vercel.

The frozen `planning/` snapshot still describes the Cloudflare Workers
Static Assets route. That wrangler preflight remains; this file only
documents the Vercel adapter.

## Automatic production path

Reviewed **pushes to `main`** run the existing `verify` workflow. When that
job succeeds, `.github/workflows/deploy-web.yml` checks out the same SHA
and asks `scripts/github_deploy_guard.py` whether that SHA is still
`origin/main`. Stale or ineligible source events skip or fail closed before
the production build. Current SHAs then:

1. Run the frozen Bun/Python production build (`INKFLIP_TEST_HOOKS` unset)
2. `scripts/vercel_output.py prepare` + `check`
3. Run `tests/deployment/prepublish-smoke.cjs` against that dist (example
   opens, a real disagreement is visible, default JSON export/reimport,
   CSP/`worker-src` headers, no test hooks)
4. Upload an immutable candidate with
   `vercel deploy --prebuilt --prod --skip-domain` (no production alias yet)
5. Re-check `origin/main` immediately before `vercel promote`

That is the only automatic production publisher. Do **not** connect the
GitHub repo to Vercel Git integration: dashboard npm/Next defaults would
compete with this path and ship the wrong bytes. Feature branches and pull
requests must not receive the production alias.

`cancel-in-progress` on the candidate job drops superseded builds. The
promote job uses the same production lock with `cancel-in-progress: false`
so an in-flight alias change finishes, then the newest run re-checks
freshness. Cancellation does **not** retract a remotely accepted Vercel
alias; the skip-domain candidate plus the second freshness check are what
stop an older SHA from taking production after a newer main exists.

Residual race: there is no compare-and-swap on the Vercel production
alias. Between the last successful current-main comparison and `vercel
promote` returning, a newer SHA can become main. The next successful
promote of that newer SHA is what corrects production. We do not claim
ordering is absolute.

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
node tests/deployment/prepublish-smoke.cjs
bunx --bun vercel@59.16.0 deploy --prebuilt --prod --skip-domain --yes
bunx --bun vercel@59.16.0 promote <deployment-url-or-id> --yes \
  --scope jubairjashim1975gmailcoms-projects
```

`vercel.json` pins `framework`, `installCommand`, and `buildCommand` to
`null` so a dashboard rebuild is not treated as Next.js/npm.

Rollback to a previous deployment ID (when one exists):

```sh
bunx --bun vercel@59.16.0 promote <deployment-id> --scope jubairjashim1975gmailcoms-projects
```

## Checks that remain local

`scripts/vercel_output.py check` is a configuration and file-set check.
`tests/deployment/test_github_deploy.py` exercises the guard script against
stale/current SHAs and rejected events, and checks that the workflow calls
it. Existing `bun run check:static-dist` (wrangler.json + `_headers` + dist
manifest) is unchanged.
