# Static Cloudflare deployment and cost boundary

## Actual selected route

Deploy Vite's completed static tree using **Workers Static Assets without a Worker script**. Copy `wrangler.example.json` to the new repository's `wrangler.json` and `_headers` into the built static root. No `main`, bindings, functions, SSR plugin, R2/D1/Queues/Containers/Workers AI, scheduled job or upload endpoint. The name is configurable; local development requires no account. A compatibility date is a provider configuration version, not a development deadline.

Cloudflare documents static asset requests/storage separately from billed Worker script execution. This design avoids the application's dynamic compute path rather than relying on an admission counter or alert as a spending cap. It does not cap unrelated account usage or guarantee unchanged provider prices. Static model files are served as ordinary versioned assets, not R2 objects or a Worker proxy. [Billing](../research/SOURCES.md#s33), [setup](../research/SOURCES.md#s34).

Build locally or in an explicitly approved CI system. Do not automatically enable Cloudflare Builds, Workers Cache, analytics or other potentially metered/injected features during bootstrap. The existing Workers Paid subscription is an owner-supplied fact, not a claim about remaining included quota.

## Routes and headers

The application uses hash navigation. Public example IDs are allowlisted; user file/report identifiers never enter paths, queries or hashes. `/index.html#/examples/mapping-amount` is a static request for index.html. `html_handling:none` and `not_found_handling:none` leave unknown network paths as 404 instead of invoking a dynamic catch-all. Provide an explicit static root index behavior and test `/`, `/index.html`, the six sample assets, a missing path and a URL-looking document string on actual preview.

The CSP allows same-origin JS/WASM/workers/assets only, no frames/objects/forms, no JavaScript unsafe-eval, and no unrelated remote origins. `style-src-attr 'unsafe-inline'` is a deliberate limited concession for geometric inline styles; it does not authorize untrusted markup or remote styles. PDF.js font loading should use modern FontFace support; if the selected CSP/engine combination fails, use the tested `disableFontFace` rendering fallback and record its appearance/performance tradeoff rather than adding a wildcard script policy. Browser Ajv validators are compiled at build time so runtime eval is unnecessary.

Tesseract's worker URL is same-origin with `workerBlobURL:false`; PDF.js main and worker match exactly. No cross-origin isolation headers are copied by default: the selected single-threaded scalar/SIMD WASM route does not require SharedArrayBuffer. COOP/COEP may be explored only in a separately tested configuration, with a non-isolated fallback and explicit browser behavior. [Headers](../research/SOURCES.md#s35), [reader API](../research/SOURCES.md#s24).

## Assets, caches and provider limits

Every static file must be <24 MiB (project margin below the provider's documented per-asset ceiling, rechecked at deploy). The English model is 4,113,088 bytes, below that target. Core WASM, CMaps and standard-font assets are enumerated and individually hashed from the actual package. Do not assume a model's compressed size equals provider-stored size or decoded memory. If an optional experimental model exceeds the per-file or total cold-download target, keep it native/experimental; do not introduce a paid storage service silently.

Hashed `/assets/` and `/models/` paths are immutable. `index.html` and `release.json` revalidate. Service worker caches only an exact static manifest and exposes offline readiness; no local documents enter cache. Retain previous release static artifacts for rollback and report reproduction. Old assets are removed only after their release package is archived and users can identify the old reader environment. [Limits](../research/SOURCES.md#s36).

## Verify the real path

T48 validates configuration and built bundle locally; G5 verifies the selected hostname after explicit owner deployment. Capture request/response headers and browser network, confirm no Worker script artifact/bindings exist in deployed configuration, and inspect available account invocation metrics for the test window. Metrics alone are not a mathematical proof of zero possible charges. Unknown paths and model requests must still be static/404, not function invocations. Disable account-level script injection and rerun the privacy canary on the actual hostname.

No Cloudflare deployment was performed in this planning pass. Published pricing/routing documentation is source-verified; the actual account and deployed route are owner/execution gates, not completed checks.
