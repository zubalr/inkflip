# tests/privacy — T15 own-file no-egress suite

Proves invariant **I08** — *local file data, names, hashes, crops and
reports never leave the browser automatically* — against the **real
built artifacts**, not a dev server and not mocks.

## Layout

- `local.spec.ts` — the suite. Builds the production bundles, serves them
  over loopback with the planned deployment `_headers` (CSP included),
  drives a generated canary PDF through the real flow in real Chromium,
  captures every observable channel, and asserts no canary material
  escapes.
- `harness/privacy.html` + `harness/mount.tsx` — a **test-owned page**
  that binds the real production collaborators (the T09 pdf.js adapter,
  the T10 `TesseractOcrReader`, the T16 `ExportPanel` + export engine, the
  contracts seal/normalize helpers). It plays the same role the feature
  preview mounts play for T08/T22 while app composition (T13) is
  unlanded — an honest documented limitation, not a stub: nothing at the
  contract surface is faked.
- `dist/` — the two-pass Vite build output (pass 1: shipped app +
  open/import preview mounts; pass 2: the privacy harness page). Ignored
  by git; rebuilt every run.
- `.private/` — raw captures, the canary descriptor and the canary PDF.
  Task-private and git-ignored; **contains live canary material**.

## Command

```sh
bun run test:privacy -- tests/privacy/local.spec.ts
```

Tests (4, single worker — ordering matters):

1. **cold** — boot the shipped `index.html`, open the canary through the
   real open mount, run plan/error/render/native-text/OCR/export/reopen/
   clear legs through the harness mount, export JSON + HTML via the real
   download path, reopen through the real import mount.
2. **warm** — second run in the same context: the verified IndexedDB
   model slot is reused (provenance `cache` at prepare, `memory` inside
   the open handle), zero model-asset refetches.
3. **offline** — the already-loaded page completes open→OCR→export with
   all network blocked (zero server hits, zero request failures; browser
   cache request events for fixed assets are expected and allowed), and
   a cold offline context fails specifically as
   `unavailable_offline`/`missing_model` rather than silently.
4. **receipt** — runs `python3 scripts/inspect_network_receipt.py`
  offline over every capture; the committed receipt carries marker
  digests only.

## What is captured (per capture file)

Requests (URL/method/headers/post body), responses, request failures,
WebSockets, the fetch/XHR/beacon/worker/service-worker egress tripwire
(installed via `addInitScript`), console messages, page errors, downloads
(filename, bytes, sha256), storage (local/session/IDB keys + value
hashes/CacheStorage/service workers), an independent **server-side**
access log, journey legs, and the mode (`cold`/`warm`/`offline`,
`offline` flag, surface page).

## Canary model

A generated PDF plus journey values form the marker set: filename,
visible text, hidden Info string, document sha256, raster pixel digest,
a user note, the report id, the export filename, and a hostile SVG-ish
payload line. Every capture channel is scanned for every marker in raw,
percent, base64, base64url and hex encodings — first in-test
(`assertCaptureClean`), then again offline by the inspector. The receipt
and the redacted capture copies (`artifacts/tasks/T15/capture/`) carry
`<marker:id>` tokens and marker digests — never marker material.

## Inspector

`scripts/inspect_network_receipt.py` (stdlib only) re-validates the raw
captures: same-origin + path allowlist for requests, read-only methods,
no query strings/fragments, empty websocket/beacon/service-worker
channels, no canary material in any channel, document-free storage (only
the sha256-verified staged model slot may persist), completed journey
legs per mode, cold fixed-asset census, and a literal census of external
URLs inside the built bundles (telemetry/collector literals or literals
also seen in runtime traffic are violations; vendor spec links, xmlns
namespaces and overridden CDN defaults are census-only — the runtime
capture is the authority). Exit 0 only when every check passes.

## Known limitations (recorded in the receipt)

- App composition (T13) has not landed: `index.html` is the shipped
  scaffold, so the suite sequentially drives the real built feature
  mounts (open preview → harness page → import preview) rather than one
  composed shell.
- Browser automation cannot see every OS/browser process channel;
  release-profile proof additionally needs a proxy/firewall capture per
  the planning scenario.
- No service worker ships: offline support means an already-loaded page
  with prepared assets (verified here); cold offline navigation has no
  app shell to load and is not claimed.
