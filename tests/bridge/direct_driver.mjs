/**
 * tests/bridge/direct_driver.mjs — the in-process (browser-path) leg of
 * the TEST-31 cross-language goldens.
 *
 * `native/tests/bridge` sends the SAME case payload to this driver and
 * to `native/inkflip/compare_bridge.py` -> `packages/compare/node/
 * bridge.mjs`. This driver calls the shared `@inkflip/compare` code
 * IN-PROCESS — what a browser caller does — while the bridge spawns the
 * fixed entrypoint. Both sides share `protocol.mjs`'s occurrence
 * resolution, so the golden comparison isolates the wire boundary:
 * Python->spawned-Node must produce byte-identical results to a direct
 * in-process call.
 *
 * Input (stdin):  `{ "op": "normalize"|"align", "raws"|"pages": ... }`
 * Output (stdout): the op's result payload (`{"results": [...]}`),
 * without the bridge envelope/comparator block.
 */

import { opAlign, opNormalize } from "../../packages/compare/node/protocol.mjs";

const chunks = [];
for await (const chunk of process.stdin) {
  chunks.push(chunk);
}
const request = JSON.parse(Buffer.concat(chunks).toString("utf8"));

let result;
if (request.op === "normalize") {
  result = opNormalize({ raws: request.raws });
} else if (request.op === "align") {
  result = opAlign({ pages: request.pages });
} else {
  throw new Error(`unknown driver op ${request.op}`);
}
process.stdout.write(JSON.stringify(result) + "\n");
