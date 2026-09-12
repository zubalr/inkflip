/**
 * packages/compare/node/protocol.mjs — request semantics for the fixed
 * shared Node comparison entrypoint (T31).
 *
 * This module is the single implementation of the bridge request
 * vocabulary. `bridge.mjs` adds only the stdin/stdout transport; the
 * in-process driver used by the cross-language golden tests calls the
 * same exported operations. Every operation dispatches to the same
 * `@inkflip/compare` modules the browser uses — normalization,
 * geometry-first alignment, frozen parameters — never a second,
 * native-only reimplementation (ADR009).
 *
 * Request shape (one bounded JSON object on stdin):
 *
 *   { "protocol": "inkflip-compare-bridge", "version": 1,
 *     "op": "describe" | "normalize" | "align", ... }
 *
 * `describe`  → comparator identity for manifests (I13).
 * `normalize` → `{ raws: [string, ...] }` → `{ results: [{text, map}] }`.
 * `align`     → `{ pages: [{page_index?, region?, left, right}] }`
 *             → `{ results: [AlignmentResult, ...] }`.
 *
 * Occurrences inside `left`/`right` carry `id`, `page_index`, `ordinal`,
 * `geometry` and either `raw` (normalized here by the shared
 * scalar-whitespace-v1 code) or a precomputed `normalized_text`. When
 * both are supplied the entrypoint recomputes and requires exact
 * agreement — a drifted port surfaces as a NORMALIZATION rejection,
 * never a silently divergent comparison.
 *
 * Error surface is ContractError with a stable code; the transport
 * wraps it as `{ ok: false, error: { code, message } }`. No request
 * field is ever mapped onto argv or a child_process call — data stays
 * data.
 */

import { ContractError } from "../../contracts/src/index.ts";
import {
  NORMALIZATION_VERSION,
  checkNormalizedView,
  normalizeText,
} from "../normalization/index.ts";
import { REGION_MATCH_V1, SCORE_SEMANTICS, alignPage } from "../alignment/index.ts";

export const PROTOCOL = "inkflip-compare-bridge";
export const PROTOCOL_VERSION = 1;
export const BRIDGE_VERSION = "1.0.0";

export const OPS = Object.freeze(["describe", "normalize", "align"]);

/** Hard protocol bounds; the Python side enforces its own tighter caps. */
export const LIMITS = Object.freeze({
  maxStdinBytes: 32 * 1024 * 1024, // mirrors contract MAX_JSON_BYTES
  maxResponseBytes: 64 * 1024 * 1024, // last-resort output bound
  maxRaws: 8192,
  maxPages: 1024,
  maxOccurrencesPerSide: 65536,
});

/** Envelope fields admitted per op — a closed message schema. */
const OP_FIELDS = Object.freeze({
  describe: new Set(),
  normalize: new Set(["raws"]),
  align: new Set(["pages"]),
});
const BASE_KEYS = new Set(["protocol", "version", "op"]);
const PAGE_KEYS = new Set(["page_index", "region", "left", "right"]);

function fail(code, message) {
  throw new ContractError(code, message);
}

/**
 * Version identity carried by every response so the caller can bind it
 * into run manifests / comparison records (I13). `node`/`platform`
 * describe the executing runtime; the algorithm ids are the frozen
 * contract versions.
 */
export function comparatorIdentity() {
  return {
    package: "@inkflip/compare",
    bridge_version: BRIDGE_VERSION,
    protocol: PROTOCOL,
    protocol_version: PROTOCOL_VERSION,
    normalization: NORMALIZATION_VERSION,
    alignment: REGION_MATCH_V1.version,
    score_semantics: SCORE_SEMANTICS,
    node: process.version,
    platform: `${process.platform}-${process.arch}`,
  };
}

/** Closed-envelope validation: unknown fields and foreign ops reject. */
export function validateEnvelope(request) {
  if (request === null || typeof request !== "object" || Array.isArray(request)) {
    fail("TYPE", "request must be a JSON object");
  }
  if (request.protocol !== PROTOCOL) {
    fail("PROTOCOL", "request is not the inkflip compare bridge protocol");
  }
  if (request.version !== PROTOCOL_VERSION) {
    fail("VERSION", "unsupported bridge protocol version");
  }
  if (typeof request.op !== "string" || !OPS.includes(request.op)) {
    fail("OP", "unknown comparison operation");
  }
  const admitted = OP_FIELDS[request.op];
  for (const key of Object.keys(request)) {
    if (!BASE_KEYS.has(key) && !admitted.has(key)) {
      fail("FIELD", `unknown request field for ${request.op}`);
    }
  }
}

/**
 * Resolve one wire occurrence to the shape alignPage reads. `raw` text
 * is normalized by the shared scalar-whitespace-v1 code; a caller-
 * supplied `normalized_text` must agree with it exactly (cross-language
 * parity enforcement, not a second normalizer).
 */
export function resolveOccurrence(occurrence, side, index) {
  const where = `${side} occurrence ${index}`;
  if (occurrence === null || typeof occurrence !== "object" || Array.isArray(occurrence)) {
    fail("TYPE", `${where} must be an object`);
  }
  let normalized_text;
  if (occurrence.raw !== undefined) {
    if (typeof occurrence.raw !== "string") {
      fail("TYPE", `${where} raw must be a string`);
    }
    normalized_text = normalizeText(occurrence.raw).text;
    if (occurrence.normalized_text !== undefined) {
      if (
        typeof occurrence.normalized_text !== "string" ||
        occurrence.normalized_text !== normalized_text
      ) {
        fail(
          "NORMALIZATION",
          `${where} normalized_text disagrees with the shared normalization of raw`,
        );
      }
    }
  } else if (occurrence.normalized_text !== undefined) {
    if (typeof occurrence.normalized_text !== "string") {
      fail("TYPE", `${where} normalized_text must be a string`);
    }
    normalized_text = occurrence.normalized_text;
  } else {
    fail("TYPE", `${where} needs raw or normalized_text`);
  }
  return {
    id: occurrence.id,
    page_index: occurrence.page_index,
    ordinal: occurrence.ordinal,
    normalized_text,
    geometry: occurrence.geometry,
  };
}

/** Resolve one page entry to `{left, right, options}` for alignPage. */
export function resolvePage(page, index) {
  const where = `page ${index}`;
  if (page === null || typeof page !== "object" || Array.isArray(page)) {
    fail("TYPE", `${where} must be an object`);
  }
  for (const key of Object.keys(page)) {
    if (!PAGE_KEYS.has(key)) {
      fail("FIELD", `${where} carries an unknown field`);
    }
  }
  if (!Array.isArray(page.left) || !Array.isArray(page.right)) {
    fail("TYPE", `${where} needs left and right occurrence arrays`);
  }
  if (
    page.left.length > LIMITS.maxOccurrencesPerSide ||
    page.right.length > LIMITS.maxOccurrencesPerSide
  ) {
    fail("SIZE", `${where} occurrence list exceeds the bounded-message cap`);
  }
  const options = {};
  if (page.page_index !== undefined) {
    options.page_index = page.page_index;
  }
  if (page.region !== undefined) {
    options.region = page.region;
  }
  return {
    left: page.left.map((o, i) => resolveOccurrence(o, "left", i)),
    right: page.right.map((o, i) => resolveOccurrence(o, "right", i)),
    options,
  };
}

export function opDescribe() {
  return { comparator: comparatorIdentity() };
}

export function opNormalize(request) {
  const raws = request.raws;
  if (!Array.isArray(raws)) {
    fail("TYPE", "normalize needs a raws array");
  }
  if (raws.length > LIMITS.maxRaws) {
    fail("SIZE", "raws exceeds the bounded-message cap");
  }
  return {
    results: raws.map((raw, index) => {
      if (typeof raw !== "string") {
        fail("TYPE", `raw ${index} must be a string`);
      }
      const view = normalizeText(raw);
      checkNormalizedView(view);
      return { text: view.text, map: view.map };
    }),
  };
}

export function opAlign(request) {
  const pages = request.pages;
  if (!Array.isArray(pages)) {
    fail("TYPE", "align needs a pages array");
  }
  if (pages.length > LIMITS.maxPages) {
    fail("SIZE", "pages exceeds the bounded-message cap");
  }
  return {
    results: pages.map((page, index) => {
      const { left, right, options } = resolvePage(page, index);
      return alignPage(left, right, options);
    }),
  };
}

/** Validated dispatch — the only entry point the transport calls. */
export function dispatch(request) {
  validateEnvelope(request);
  switch (request.op) {
    case "describe":
      return opDescribe();
    case "normalize":
      return opNormalize(request);
    default:
      return opAlign(request);
  }
}
