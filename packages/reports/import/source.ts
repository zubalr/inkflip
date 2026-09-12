/**
 * Explicit local source association (I09).
 *
 * An evidence-mode export deliberately carries no original PDF bytes.
 * Replay may bind a source only when the user explicitly selects a local
 * file whose bytes verify byte-for-byte against the recorded document
 * identity (`document.byte_length` + `document.sha256`). A matching
 * hash alone is never sufficient — the actual bytes must be present.
 * A mismatch is a hard failure: the candidate is never attached, never
 * remembered, and replay stays blocked.
 *
 * This check performs no I/O and does not open the bytes as a document;
 * it only proves the bytes *are* the recorded original.
 */
import { sha256 } from "../../contracts/src/index.ts";
import type { Report } from "../../contracts/src/index.ts";

const HEX = "0123456789abcdef";

function toHex(bytes: Uint8Array): string {
  return Array.from(bytes, (b) => HEX[b >> 4]! + HEX[b & 0x0f]!).join("");
}

export type SourceCheck =
  | { readonly ok: true; readonly sha256: string; readonly byteLength: number }
  | {
      readonly ok: false;
      readonly kind: "source_mismatch";
      readonly detail: string;
    };

/**
 * Verify a locally selected file's bytes against the report's recorded
 * document identity. Cheap size rejection happens first so a wrong file
 * never even reaches the digest.
 */
export function verifySourceCandidate(report: Report, bytes: Uint8Array): SourceCheck {
  const document = report.document;
  if (bytes.length !== document.byte_length) {
    return {
      ok: false,
      kind: "source_mismatch",
      detail: "source:length-mismatch",
    };
  }
  const digest = toHex(sha256(bytes));
  if (digest !== document.sha256) {
    return {
      ok: false,
      kind: "source_mismatch",
      detail: "source:sha256-mismatch",
    };
  }
  return { ok: true, sha256: digest, byteLength: bytes.length };
}
