# Security policy

## Scope of this document

Inkflip is a local-first PDF reading inspector: a static browser application
that processes files entirely in the user's tab, plus local Python tooling.
This page states the project's security-relevant expectations, what is
currently verified, and — verbatim honestly — what reporting channels exist.

## Security expectations of the product

- **No document egress in the browser path.** Opened files, selections,
  readings and reports never leave the browser tab automatically. This is
  verified, not assumed: a canary suite drives a marked synthetic document
  through the real production build in Chromium and asserts, per capture,
  that nothing escapes across cold/warm/offline runs
  ([tests/privacy/README.md](tests/privacy/README.md)).
- **No server compute.** The product is a static bundle; there is no
  extraction API, upload endpoint, account system or database to attack. The
  deployment preflight that will prove the deployed artifact matches this
  posture is still pending ([docs/limitations.md](docs/limitations.md)).
- **Same-origin assets.** OCR/WASM engines, language data and fonts are
  staged from the application's own origin; third-party CDNs are not part of
  the runtime trust base.
- **Strict report import.** The only externally supplied structured input
  besides the PDF itself is a saved report; it is schema-validated,
  size-bounded and adversarially tested (malformed, oversized and injection
  attempts are rejected, with dedicated hardening tests).
- **Original bytes immutable.** The tool never writes to the opened document.

## What is *not* claimed

- That a browser prevents every conceivable exfiltration channel, or that the
  canary suite covers channels beyond the ones it captures on the tested
  browsers and build.
- That the reading differences Inkflip surfaces indicate anything about a
  document's safety, authenticity or intent — they are facts about named
  reader outputs, nothing more (see [docs/limitations.md](docs/limitations.md)).
- Any completed native containment, SBOM/vulnerability gate, or deployment
  verification — those are pending tasks (T40, T47, T48) and are recorded as
  such rather than claimed.

## Supported versions

No version of Inkflip has been released yet. Security fixes apply to the
default branch of this private repository; there are no tagged, distributed
or supportable versions at this time.

## Reporting a vulnerability

**Current status: no dedicated security-reporting channel exists yet.** This
repository is private and pre-release, so there is no public tracker, security
email, or disclosure process to point to — and none is invented here.

Until a dedicated channel is recorded (planned as part of the pending
distribution work, T47):

- Do **not** open a public issue or discuss the details in any public forum.
- Contact the repository owner privately through the maintainer's existing
  personal channels (the owner identity is recorded in the repository's
  provenance records, [docs/ORIGIN.md](docs/ORIGIN.md)).
- Include: affected component (browser app / native tooling / docs claims),
  a minimal reproduction, the exact commit you tested, and your assessment
  of impact.

No response-time or remediation commitments are made or implied. When a
formal channel exists (security contact, private-vulnerability reporting on
the eventual public repository, or an advisory process), this section will
name it explicitly and this file will be the single source of truth for it.

## Hardening backlog

Security-relevant work that is specified but not yet complete is tracked in
the task tracker and summarized in
[docs/limitations.md](docs/limitations.md): native process containment and
failure recovery (T40), the SBOM/third-party notice bundle and vulnerability
gate (T47), and the static-build/CSP/deployment preflight (T48).
