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

Requests (URL/method/**all request headers**/post body), responses
(URL/status), request failures (URL/method/error/headers), WebSockets,
the fetch/XHR/beacon/worker/service-worker/WebRTC/WebTransport/
form.submit egress tripwire (installed via `addInitScript`), console
messages, page errors, dialogs (recorded then dismissed — any dialog is
a violation), downloads (filename, bytes, sha256), storage
(local/session/IDB keys + value hashes/CacheStorage/service workers),
journey legs, an independent **server-side** access log
(method/path/query/status/**request headers**), and the mode
(`cold`/`warm`/`offline`/`online`, `offline` flag, surface page).

## Canary model

A generated PDF plus journey values form **11 greppable markers**:
filename, visible text, hidden Info string, user note (+ bare token),
hostile-payload-free variants, document sha256, pdf base64 head, raster
pixel sha256, report id, run key, export filename. Every capture channel
is scanned for every marker in raw, percent, base64, base64url, hex and
digest-base64 spellings — first in-test (`assertCaptureClean`), then
again offline by the inspector, which additionally scans the
cross-channel concatenation, a whitespace-collapsed variant and
base64-decoded payloads (markers split across log lines or wrapped
inside base64'd JSON are caught). The receipt and the redacted capture
copies (`artifacts/tasks/T15/capture/`) carry `<marker:id>` tokens and
marker digests — never marker material. Report-derived markers declare
`allowed_channels: ["downloads"]` in the private manifest; that policy
is echoed into the committed receipt per marker id.

## Inspector

`scripts/inspect_network_receipt.py` (stdlib only) re-validates the raw
captures and **fails closed on absent evidence**: every capture must
carry the full channel key set, nonempty named legs, a storage snapshot
and captured request headers; every non-offline capture must record at
least one request; the union of legs must cover
open/error/render/OCR/export/reopen/clear. Content checks: same-origin +
path allowlist applied to requests, request failures, responses and the
server log; read-only methods; no query strings/fragments; empty
websocket/beacon/service-worker/WebRTC/WebTransport/form.submit/dialog
channels (unrecognized egress kinds are violations, not skips); no
canary material in any channel; document-free storage (only the
sha256-verified staged model slot may persist); completed legs per mode;
cold fixed-asset census; model-fetch provenance derived from the wire
(cold = one served model fetch, warm = zero model requests, offline =
zero served model paths); and a literal census of external URLs inside
the built bundles (telemetry/collector literals or literals also seen
in runtime traffic are violations; vendor spec links, xmlns namespaces
and overridden CDN defaults are census-only — the runtime capture is
the authority). Exit 0 only when every check passes.

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
- WebRTC/WebTransport are tripwired at construction and asserted unused
  (verified absent from the built bundles); frames inside an
  already-open data channel are not separately captured — the guarantee
  is constructor-level.
- Log-channel scans are bounded by capture truncation (console/page-error
  2000 chars, leg/egress/dialog details and ws frames 1000); network
  carriers are closed by method/query/allowlist/header checks, so the
  residual escape window is log-text only — shrunk further by the
  inspector's joined and base64-decoded sweeps.
