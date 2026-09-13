# Node PDF.js profile wrapper

Fixed argv: `node packages/readers-pdfjs/node/bridge.mjs`.

The wrapper loads the workspace-locked `pdfjs-dist@6.3.289` legacy build,
configures the paired worker, and runs `getDocument` / `getTextContent`.
It records the actual `pdfjs.version`. It does not stub extraction, does
not hardcode a success version, and does not fetch over the network.

Install this workspace independently:

```sh
cd packages/readers-pdfjs/node && bun install --frozen-lockfile
```
