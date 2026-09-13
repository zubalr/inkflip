# PDF.js Node Reader Profile Wrapper (T33)

Fixed, isolated Node entrypoint for executing PDF.js reader operations outside the browser.

## Protocol & Invocation

- **Fixed Invocation**: `node packages/readers-pdfjs/node/bridge.mjs`
- **Communication**: Single bounded JSON request on `stdin`, single-line JSON response on `stdout`.
- **Security Invariants**:
  - No shell execution or dynamic command construction.
  - No network access or remote resource loading.
  - Strict input size limits (maximum 32MB request payload).
  - Clean error classification: handled schema/file/parse errors yield `{ ok: false, ... }` with exit code `0`. Nonzero exit signals process or environment failure only.
