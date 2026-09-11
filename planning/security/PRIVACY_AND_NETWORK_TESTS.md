# Privacy and network verification

The claim to earn is **the application's own-file route does not transmit document bytes, text, filenames, hashes, crops, notes or reports**. This does not mean the host receives no IP address or ordinary connection metadata, nor does it imply a trusted website can never be compromised.

## Default data lifetime

Source bytes, parsed structures, raw text, crops and reports exist in memory. No document persistence in localStorage, sessionStorage, IndexedDB, CacheStorage or application service-worker caches. URLs contain only fixed public route/example IDs. Logs contain bounded stage/error codes and resource counters only; debug dumps of content require explicit local export and inclusion preview. No crash-reporting SDK, session replay, analytics, telemetry beacon, remote logger, web sharing API or social auto-post.

The original File remains immutable. Clear/replacement increments generation first, stops work, drops references, clears canvases, terminates OCR and revokes owned Blob URLs. Static model cache is separate and explicitly removable. Browser process memory, OS swap, downloaded files and browser download history cannot be forensically erased by the app; copy states that limitation. Browser-back behavior and bfcache restoration are tested: a cleared workspace cannot be revived by application state. Listen to pagehide to stop work; restore only an empty workspace or still-open in-memory state explicitly consistent with the user's clear action.

## Asset request policy

Only application-owned allowlisted static GETs are permitted: JS/CSS/workers/WASM, exact model paths, approved CMaps/standard-font assets and prepared example files. No query parameter may contain document identity or text. A PDF string resembling a URL is inert data. PDF links/actions/attachments do not auto-open. Font and image resources required by the renderer come from the package or PDF bytes, not arbitrary URLs. After explicit offline preparation, repeat the supported own-file workflow with all network blocked.

The service worker, if enabled, intercepts only exact static manifest paths. It must never cache `blob:`, imported JSON, local source objects or an arbitrary request. Cached static assets are hash-bound to a release. Cache failure is explicit; do not label a partially prepared browser as offline-ready.

## Executable privacy scenario (product T15/T24/T25)

Create an original canary PDF whose name, visible text, hidden string, document hash, crop pixels and note each contain separate unique markers. Use only test markers, not real secrets. Capture the browser context's requests, request bodies, query strings, WebSockets, beacons, service-worker traffic and console output from navigation through file opening, OCR prep, comparison, export, import, retry, clear and replacement. Include a prepared cached run and cold-cache run.

Assertions: request URLs/methods equal the static allowlist; no POST/PUT or unexpected websocket; none of the filename/text/hash markers appear in network or default logs; response-driven script list matches build assets; imported report triggers no asset URL fetch; clear leaves no document keys in storage; offline run succeeds with already prepared assets and fails specifically as missing assets without them. A network trace should also compare cropped binary payload hashes, not only string matching. Browser automation cannot see every OS/browser process channel; record this limit and use a proxy/firewall capture for the release profile.

Test encoded variants (URL/base64/JSON escapes), console exceptions, malicious HTML-like text, unexpected CDN/font fallback and dev-tool production leakage. Explicit user navigation to the Source link is a separate normal outbound action; the app must not attach document parameters or referrer content. File downloads are local and must not become upload shares.

## Deployed boundary

Disable Cloudflare Web Analytics/RUM injection, Zaraz, Rocket Loader and unrelated third-party injection on the selected hostname where enabled. Verify the actual response/DOM/network rather than assuming repository config controls account-wide features. Production CSP is a response header. A local development server with HMR is not privacy proof for the release artifact. Inspect the built static site and the actual public route separately.

Any unexpected document transmission blocks the privacy claim and release, even if it came from a helpful debug integration. Remove the path, invalidate affected artifacts, rerun the full scenario and document the correction. Never explain it away as “still local processing”.
