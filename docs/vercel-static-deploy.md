# Vercel static publication (local build, prebuilt upload)

Inkflip is the existing Vite browser app. This path publishes that static
tree. It does not add a database, accounts, or a replacement landing page,
and it does not run the Python command harness on Vercel.

The frozen `planning/` snapshot still describes the Cloudflare Workers
Static Assets route. That wrangler preflight remains; this file only
documents the Vercel adapter.

## What is uploaded

A local production build (`bun run build` with `INKFLIP_TEST_HOOKS`
unset) writes `apps/web/dist/`. `scripts/vercel_output.py prepare`
copies those files into `.vercel/output/static` and writes Build Output
API v3 `config.json` routes translated from `dist/_headers`. A deployed
`_headers` text file is not equivalent: Vercel does not apply Cloudflare
header files.

Missing worker, WASM, or model paths are left as filesystem misses (404).
There is no rewrite to `index.html`. Hash routes (`#/workspace`,
`#/workspace?example=true`) stay on `/`.

`.vercel/` stays gitignored (link metadata and generated output). Source
maps are not copied.

## Commands

From a checkout that already has frozen Bun dependencies and a production
dist:

```sh
python3 scripts/distribution/record_dist.py --skip-build
python3 scripts/check_static_dist.py apps/web/dist \
  --config wrangler.json \
  --dist-manifest .private/distribution/dist-manifest.json
python3 scripts/vercel_output.py prepare
python3 scripts/vercel_output.py check
```

`vercel.json` pins `framework`, `installCommand`, and `buildCommand` to
`null` so a dashboard rebuild is not treated as Next.js/npm. Publication
uses the pinned CLI against the prepared output:

```sh
bunx --bun vercel@59.16.0 deploy --prebuilt --prod --skip-domain --yes
```

`--skip-domain` stages production bytes without moving the production
alias. After live checks, `bunx --bun vercel@59.16.0 promote <deployment>`.
The first deployment of a new project is production even without `--prod`.

These commands create or update a Vercel project; they are not recorded
here as having been run.

## Checks that remain local

`scripts/vercel_output.py check` is a configuration and file-set check.
It does not prove a public hostname. Existing `bun run check:static-dist`
(wrangler.json + `_headers` + dist manifest) is unchanged.
