#!/usr/bin/env node
/**
 * packages/compare/node/bridge.mjs — the fixed installed Node
 * entrypoint for the shared comparison bridge (T31).
 *
 * The native Python side (`native/inkflip/compare_bridge.py`) invokes
 * this file with a FIXED argv — `node <this absolute path>` — never a
 * shell, never report-selected flags. It reads ONE bounded JSON request
 * from stdin, dispatches it through `protocol.mjs` into the same
 * `@inkflip/compare` code the browser uses, and writes ONE bounded JSON
 * response object to stdout.
 *
 * Response shape (single line, UTF-8):
 *   { ok: true,  protocol, version, comparator, result }
 *   { ok: false, protocol, version, comparator, error: {code,message} }
 *
 * Every handled failure — malformed JSON, closed-schema violation,
 * rejected occurrence, oversized request — is an `ok:false` response
 * with exit 0. A nonzero exit therefore means the entrypoint itself
 * could not run (missing files, an old Node without type stripping),
 * which the Python side classifies as a capability/child failure, never
 * a comparison result.
 */

import { ContractError } from "../../contracts/src/index.ts";
import { LIMITS, PROTOCOL, PROTOCOL_VERSION, comparatorIdentity, dispatch } from "./protocol.mjs";

const decoder = new TextDecoder("utf-8", { fatal: true });

function okResponse(result) {
  return {
    ok: true,
    protocol: PROTOCOL,
    version: PROTOCOL_VERSION,
    comparator: comparatorIdentity(),
    result,
  };
}

function errorResponse(code, message) {
  return {
    ok: false,
    protocol: PROTOCOL,
    version: PROTOCOL_VERSION,
    comparator: comparatorIdentity(),
    error: { code, message: String(message).slice(0, 500) },
  };
}

/** Read all of stdin with a hard byte cap; aborts the stream on overflow. */
function readRequest() {
  return new Promise((resolve) => {
    const chunks = [];
    let total = 0;
    let settled = false;
    const done = (value) => {
      if (!settled) {
        settled = true;
        resolve(value);
      }
    };
    process.stdin.on("data", (chunk) => {
      total += chunk.length;
      if (total > LIMITS.maxStdinBytes) {
        process.stdin.destroy();
        done({ tooLarge: true });
        return;
      }
      chunks.push(chunk);
    });
    process.stdin.on("end", () => done({ body: Buffer.concat(chunks) }));
    process.stdin.on("close", () => done({ body: Buffer.concat(chunks) }));
    process.stdin.on("error", () => done({ body: Buffer.concat(chunks) }));
  });
}

function emit(response) {
  let payload = JSON.stringify(response);
  if (Buffer.byteLength(payload, "utf8") > LIMITS.maxResponseBytes) {
    payload = JSON.stringify(
      errorResponse("RESPONSE_TOO_LARGE", "response exceeds the bounded output cap"),
    );
  }
  process.stdout.write(payload + "\n", () => process.exit(0));
}

const request = await readRequest();
if (request.tooLarge) {
  emit(errorResponse("SIZE", "request exceeds the bounded input cap"));
} else {
  let response;
  try {
    let parsed;
    try {
      parsed = JSON.parse(decoder.decode(request.body));
    } catch (error) {
      if (error instanceof TypeError) {
        throw new ContractError("UNICODE", "request is not valid UTF-8");
      }
      throw new ContractError("JSON", "request is not valid JSON");
    }
    response = okResponse(dispatch(parsed));
  } catch (error) {
    if (error instanceof ContractError) {
      response = errorResponse(error.code, error.message);
    } else {
      // Internal failure: never leak paths/stacks into the response.
      response = errorResponse("INTERNAL", "comparison engine failed on a valid envelope");
    }
  }
  emit(response);
}
